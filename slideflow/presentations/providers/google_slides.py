"""Google Slides presentation provider for Slideflow.

This module provides a concrete implementation of the PresentationProvider
interface for Google Slides. It handles authentication with Google APIs,
presentation creation and management, chart image upload and insertion,
text replacement, and sharing operations using the Google Slides API v1.

The Google Slides provider includes:
    - Service account authentication for server applications
    - Presentation creation with optional template copying
    - Image upload to Google Drive with public URL generation
    - Chart insertion with precise positioning and sizing
    - Text replacement operations with occurrence tracking
    - Presentation sharing with configurable permissions
    - Comprehensive error handling and API operation logging

Authentication:
    The provider uses Google service account credentials for authentication,
    requiring appropriate scopes for Google Slides, Google Drive, and file
    operations. Credentials must be provided via a service account JSON file.

Required Scopes:
    - https://www.googleapis.com/auth/presentations: For Slides API access
    - https://www.googleapis.com/auth/drive: For Drive operations and sharing
    - https://www.googleapis.com/auth/drive.file: For file upload and management

Example:
    Using the Google Slides provider:

    >>> from slideflow.presentations.providers.google_slides import GoogleSlidesProvider
    >>> from slideflow.presentations.providers.google_slides import GoogleSlidesProviderConfig
    >>>
    >>> # Create configuration
    >>> config = GoogleSlidesProviderConfig(
    ...     provider_type="google_slides",
    ...     credentials="/path/to/service_account.json",
    ...     template_id="1ABC123_template_id_XYZ789",
    ...     share_with=["viewer@example.com"],
    ...     share_role="reader"    ... )
    >>>
    >>> # Create provider
    >>> provider = GoogleSlidesProvider(config)
    >>>
    >>> # Create presentation from template
    >>> presentation_id = provider.create_presentation("Monthly Report")
    >>>
    >>> # Upload and insert chart
    >>> with open("chart.png", "rb") as f:
    ...     image_data = f.read()
    >>> image_url, public_url = provider.upload_chart_image(
    ...     presentation_id, image_data, "sales_chart.png"
    ... )
    >>> provider.insert_chart_to_slide(
    ...     presentation_id, "slide_1", image_url,
    ...     x=100, y=100, width=400, height=300
    ... )
    >>>
    >>> # Replace text in slide
    >>> replacements = provider.replace_text_in_slide(
    ...     presentation_id, "slide_1", "{{MONTH}}", "March"
    ... )
    >>>
    >>> # Get presentation URL
    >>> url = provider.get_presentation_url(presentation_id)
    >>> print(f"View presentation: {url}")
"""

import io
import os
import threading
import time
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from pydantic import Field, field_validator

from slideflow.citations import CitationEntry, format_citation_line
from slideflow.constants import Environment, GoogleSlides, Timing
from slideflow.presentations.providers.base import (
    PresentationProvider,
    PresentationProviderConfig,
)
from slideflow.presentations.providers.google_drive_ownership import (
    append_transfer_owner_preflight_check,
    is_shared_drive_file,
    normalize_transfer_owner_email,
    transfer_drive_file_ownership,
)
from slideflow.utilities.auth import handle_google_credentials
from slideflow.utilities.exceptions import AuthenticationError
from slideflow.utilities.logging import get_logger, log_api_operation
from slideflow.utilities.rate_limiter import RateLimiter

logger = get_logger(__name__)
_folder_creation_lock = threading.Lock()
_folder_id_cache: Dict[Tuple[str, str], str] = {}
_api_rate_limiter: Optional[RateLimiter] = None
_rate_limiter_lock = threading.Lock()


def _get_rate_limiter(rps: float, force_update: bool = False) -> RateLimiter:
    """Get or create the global rate limiter."""
    global _api_rate_limiter
    with _rate_limiter_lock:
        if _api_rate_limiter is None:
            _api_rate_limiter = RateLimiter(rps)
        elif force_update:
            _api_rate_limiter.set_rate(rps)
        return _api_rate_limiter


class GoogleSlidesProviderConfig(PresentationProviderConfig):
    """Configuration model for Google Slides presentation provider.

    This configuration class defines all parameters needed to configure the
    Google Slides provider, including authentication credentials, template
    settings, Drive folder organization, and default sharing permissions.

    Attributes:
        provider_type: Always "google_slides" for this provider.
        credentials: Path to Google service account credentials JSON file.
        template_id: Optional Google Slides template ID to copy from when creating presentations.
        drive_folder_id: Optional Google Drive folder ID for organizing uploaded chart images.
        presentation_folder_id: Optional Google Drive folder ID for organizing created presentations.
        new_folder_name: Optional name for a new subfolder to be created.
        new_folder_name_fn: Optional function to generate the new subfolder name dynamically.
        share_with: List of email addresses to automatically share presentations with.
        share_role: Default permission role for shared presentations.
        requests_per_second: Maximum number of API requests per second (default: 1.0).

    Example:
        >>> config = GoogleSlidesProviderConfig(
        ...     provider_type="google_slides",
        ...     credentials="/path/to/service_account.json",
        ...     requests_per_second=1.0
        ... )
    """

    provider_type: Literal["google_slides"] = "google_slides"
    credentials: Optional[str] = Field(
        None,
        description="Google service account credentials as a file path or a JSON string.",
    )
    template_id: Optional[str] = Field(
        None, description="Google Slides template ID to copy from"
    )
    drive_folder_id: Optional[str] = Field(
        None, description="Google Drive folder ID for organizing uploaded chart images."
    )
    presentation_folder_id: Optional[str] = Field(
        None, description="Google Drive folder ID for presentations"
    )
    new_folder_name: Optional[str] = Field(
        None,
        description="Name for a new subfolder to be created in the presentation_folder_id.",
    )
    new_folder_name_fn: Optional[Callable] = Field(
        None, description="Function to generate the new subfolder name dynamically."
    )
    share_with: List[str] = Field(
        default_factory=list, description="Email addresses to share presentation with"
    )
    share_role: str = Field(
        GoogleSlides.PERMISSION_WRITER,
        description="Permission role: reader, writer, or commenter",
    )
    requests_per_second: float = Field(
        1.0, gt=0, description="Maximum number of API requests per second"
    )
    strict_cleanup: bool = Field(
        False,
        description="If true, fail rendering when uploaded chart images cannot be cleaned up.",
    )
    chart_image_sharing_mode: Literal["public", "restricted"] = Field(
        "public",
        description=(
            "Chart image sharing mode. 'public' grants anyone:reader (default); "
            "'restricted' skips public sharing for tighter access control."
        ),
    )
    transfer_ownership_to: Optional[str] = Field(
        None,
        description="Optional email address that should become the owner after rendering completes.",
    )
    transfer_ownership_strict: bool = Field(
        False,
        description="If true, fail rendering when ownership transfer fails.",
    )

    @field_validator("transfer_ownership_to")
    @classmethod
    def _validate_transfer_ownership_to(cls, value: Optional[str]) -> Optional[str]:
        return normalize_transfer_owner_email(value)


class GoogleSlidesProvider(PresentationProvider):
    """Google Slides presentation provider implementation.

    This provider implements the PresentationProvider interface for Google Slides,
    providing comprehensive access to Google Slides API functionality including
    presentation creation, template copying, image upload and insertion, text
    replacement, and sharing operations.

    The provider integrates with both Google Slides API and Google Drive API to
    provide complete presentation management capabilities, including file organization
    and permission management.

    Authentication:
        Uses Google service account credentials with OAuth2 for authentication.
        Requires appropriate IAM permissions and API scopes for both Slides and
        Drive APIs.

    Performance:
        All API operations are logged with timing metrics for monitoring and
        optimization. The provider handles rate limiting and provides detailed
        error information for troubleshooting.

    Example:
        >>> config = GoogleSlidesProviderConfig(
        ...     provider_type="google_slides",
        ...     credentials="/path/to/service_account.json"
        ... )
        >>> provider = GoogleSlidesProvider(config)
        >>>
        >>> # Create presentation
        >>> presentation_id = provider.create_presentation("Q4 Report")
        >>>
        >>> # Upload and insert chart
        >>> with open("chart.png", "rb") as f:
        ...     image_data = f.read()
        >>> image_url, public_url = provider.upload_chart_image(
        ...     presentation_id, image_data, "revenue_chart.png"
        ... )
        >>> provider.insert_chart_to_slide(
        ...     presentation_id, "slide_1", image_url,
        ...     x=50, y=50, width=400, height=300
        ... )
    """

    SCOPES = [
        "https://www.googleapis.com/auth/presentations",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
    ]

    def __init__(self, config: GoogleSlidesProviderConfig):
        """Initialize Google Slides provider with authentication.

        Sets up authenticated Google API service clients for both Slides and Drive
        APIs using the provided service account credentials.

        Args:
            config: GoogleSlidesProviderConfig containing authentication and
                configuration parameters.

        Raises:
            AuthenticationError: If credentials file is not found or invalid.
            APIError: If Google API service initialization fails.
        """
        super().__init__(config)
        self.config: GoogleSlidesProviderConfig = config

        # Initialize Google API services
        loaded_credentials = handle_google_credentials(config.credentials)

        try:
            credentials = Credentials.from_service_account_info(
                loaded_credentials, scopes=self.SCOPES
            )
        except Exception as error_msg:
            raise AuthenticationError(
                f"Credentials authentication failed: {error_msg}"
            ) from error_msg

        self.slides_service = build("slides", "v1", credentials=credentials)
        self.drive_service = build("drive", "v3", credentials=credentials)

        self.rate_limiter = _get_rate_limiter(self.config.requests_per_second)

    def _execute_request(self, request):
        """Execute a Google API request with rate limiting."""
        self.rate_limiter.wait()
        return request.execute(num_retries=3)

    @staticmethod
    def _dimension_to_points(dimension: Optional[Dict[str, Any]]) -> Optional[int]:
        """Convert Google Slides dimension objects to points."""
        if not isinstance(dimension, dict):
            return None

        magnitude = dimension.get("magnitude")
        unit = str(dimension.get("unit", "PT")).upper()

        if magnitude is None:
            return None
        try:
            magnitude_value = float(str(magnitude))
        except (TypeError, ValueError):
            return None

        if unit == "EMU":
            return int(magnitude_value / 12700)
        if unit == "PT":
            return int(magnitude_value)
        return None

    def run_preflight_checks(self) -> List[Tuple[str, bool, str]]:
        """Run Google provider preflight checks used by CLI doctor/build."""
        has_credentials = bool(self.config.credentials) or bool(
            os.getenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS)
        )
        checks: List[Tuple[str, bool, str]] = [
            (
                "google_credentials_present",
                has_credentials,
                (
                    "Credentials found in config or GOOGLE_SLIDEFLOW_CREDENTIALS"
                    if has_credentials
                    else "Missing credentials in config and environment"
                ),
            ),
            (
                "slides_service_initialized",
                self.slides_service is not None,
                (
                    "Google Slides API client initialized"
                    if self.slides_service is not None
                    else "Google Slides API client is not initialized"
                ),
            ),
            (
                "drive_service_initialized",
                self.drive_service is not None,
                (
                    "Google Drive API client initialized"
                    if self.drive_service is not None
                    else "Google Drive API client is not initialized"
                ),
            ),
            (
                "rate_limiter_initialized",
                self.rate_limiter is not None,
                (
                    f"Rate limiter configured at {self.config.requests_per_second} rps"
                    if self.rate_limiter is not None
                    else "Rate limiter is not initialized"
                ),
            ),
        ]

        append_transfer_owner_preflight_check(
            checks,
            getattr(self.config, "transfer_ownership_to", None),
        )

        return checks

    def create_presentation(self, name: str, template_id: Optional[str] = None) -> str:
        """Create a new Google Slides presentation.

        Args:
            name: Name of the presentation
            template_id: Optional template to copy from (overrides config default)

        Returns:
            Presentation ID
        """
        template_to_use = template_id or self.config.template_id

        if template_to_use:
            return self._copy_template(template_to_use, name)
        else:
            return self._create_presentation(name)

    def upload_chart_image(
        self, presentation_id: str, image_data: bytes, filename: str
    ) -> Tuple[str, str]:
        """Upload chart image to Google Drive.

        Args:
            presentation_id: ID of the presentation (for folder context)
            image_data: Chart image as bytes
            filename: Name for the image file

        Returns:
            Tuple of (image_url, file_id)
        """
        url, file_id = self._upload_image_to_drive(image_data, filename)
        return (url, file_id)

    def insert_chart_to_slide(
        self,
        presentation_id: str,
        slide_id: str,
        image_url: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        """Insert chart image into Google Slides slide.

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            image_url: URL of the chart image
            x, y: Position coordinates
            width, height: Chart dimensions
        """
        requests = [
            {
                "createImage": {
                    "url": image_url,
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {
                            "width": {"magnitude": width, "unit": "PT"},
                            "height": {"magnitude": height, "unit": "PT"},
                        },
                        "transform": {
                            "scaleX": 1,
                            "scaleY": 1,
                            "translateX": x,
                            "translateY": y,
                            "unit": "PT",
                        },
                    },
                }
            }
        ]

        self._batch_update(presentation_id, requests)

    def replace_text_in_slide(
        self, presentation_id: str, slide_id: str, placeholder: str, replacement: str
    ) -> int:
        """Replace text in Google Slides slide.

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            placeholder: Text to replace
            replacement: Replacement text

        Returns:
            Number of replacements made
        """
        requests = [
            {
                "replaceAllText": {
                    "containsText": {"text": placeholder, "matchCase": True},
                    "replaceText": replacement,
                    "pageObjectIds": [slide_id],
                }
            }
        ]

        response = self._batch_update(presentation_id, requests)

        # Extract number of replacements from response
        if "replies" in response and response["replies"]:
            reply = response["replies"][0]
            if "replaceAllText" in reply:
                return reply["replaceAllText"].get("occurrencesChanged", 0)

        return 0

    def _get_speaker_notes_targets(
        self, presentation_id: str
    ) -> Dict[str, Tuple[str, int]]:
        """Return slide -> (speaker_notes_shape_id, insertion_index) map."""
        response = self._execute_request(
            self.slides_service.presentations().get(
                presentationId=presentation_id,
                fields=(
                    "slides(objectId,"
                    "slideProperties(notesPage(notesProperties(speakerNotesObjectId),"
                    "pageElements(objectId,shape(text(textElements(endIndex))))),"
                    "notesPage(notesProperties(speakerNotesObjectId),"
                    "pageElements(objectId,shape(text(textElements(endIndex)))))"
                    "))"
                ),
            )
        )

        targets: Dict[str, Tuple[str, int]] = {}
        for slide in response.get("slides", []):
            if not isinstance(slide, dict):
                continue
            slide_id = slide.get("objectId")
            slide_properties = slide.get("slideProperties", {})
            if not isinstance(slide_properties, dict):
                slide_properties = {}
            notes_page = slide_properties.get("notesPage")
            if not isinstance(notes_page, dict):
                legacy_notes_page = slide.get("notesPage", {})
                notes_page = (
                    legacy_notes_page if isinstance(legacy_notes_page, dict) else {}
                )
            if not isinstance(notes_page, dict) or not slide_id:
                continue

            notes_properties = notes_page.get("notesProperties", {})
            if not isinstance(notes_properties, dict):
                continue
            speaker_object_id = notes_properties.get("speakerNotesObjectId")
            if not speaker_object_id:
                continue

            insertion_index = 0
            for element in notes_page.get("pageElements", []):
                if not isinstance(element, dict):
                    continue
                if element.get("objectId") != speaker_object_id:
                    continue
                shape = element.get("shape", {})
                text = shape.get("text", {}) if isinstance(shape, dict) else {}
                text_elements = (
                    text.get("textElements", []) if isinstance(text, dict) else []
                )
                end_indexes: List[int] = []
                for entry in text_elements:
                    if not isinstance(entry, dict):
                        continue
                    end_index = entry.get("endIndex")
                    if isinstance(end_index, int):
                        end_indexes.append(end_index)
                if end_indexes:
                    insertion_index = max(max(end_indexes) - 1, 0)
                break

            targets[str(slide_id)] = (str(speaker_object_id), insertion_index)
        return targets

    def render_citations(
        self,
        presentation_id: str,
        citations_by_scope: Dict[str, List[Dict[str, Any]]],
        location: str,
    ) -> None:
        """Render source citations into slide speaker notes."""
        if not citations_by_scope:
            return

        notes_targets = self._get_speaker_notes_targets(presentation_id)
        if not notes_targets:
            logger.warning("No speaker notes targets found for presentation citations")
            return

        if location == "document_end":
            combined: List[Dict[str, Any]] = []
            seen: set[str] = set()
            for citations in citations_by_scope.values():
                for citation in citations:
                    source_id = str(citation.get("source_id", ""))
                    if source_id in seen:
                        continue
                    seen.add(source_id)
                    combined.append(citation)
            first_slide_id = next(iter(notes_targets.keys()))
            scope_mapping = {first_slide_id: combined}
        else:
            scope_mapping = citations_by_scope

        requests: List[Dict[str, Any]] = []
        for scope_id, citations in scope_mapping.items():
            target = notes_targets.get(scope_id)
            if not target or not citations:
                continue
            object_id, insertion_index = target
            lines = ["", "Sources"]
            for citation_payload in citations:
                entry = self._validate_citation_payload(
                    citation_payload,
                    scope_id=scope_id,
                    location=location,
                )
                if entry is None:
                    continue
                lines.append(format_citation_line(entry))
            if len(lines) <= 2:
                continue

            requests.append(
                {
                    "insertText": {
                        "objectId": object_id,
                        "insertionIndex": insertion_index,
                        "text": "\n".join(lines),
                    }
                }
            )

        if requests:
            self._batch_update(presentation_id, requests)

    def _validate_citation_payload(
        self,
        citation_payload: Dict[str, Any],
        *,
        scope_id: str,
        location: str,
    ) -> Optional[CitationEntry]:
        try:
            return CitationEntry.model_validate(citation_payload)
        except Exception as error:
            source_id = (
                citation_payload.get("source_id", "<missing>")
                if isinstance(citation_payload, dict)
                else "<missing>"
            )
            provider = (
                citation_payload.get("provider", "<missing>")
                if isinstance(citation_payload, dict)
                else "<missing>"
            )
            logger.warning(
                "Skipping invalid citation for scope '%s' (location=%s, source_id=%s, provider=%s): %s",
                scope_id,
                location,
                source_id,
                provider,
                error,
            )
            return None

    def share_presentation(
        self,
        presentation_id: str,
        emails: List[str],
        role: str = GoogleSlides.PERMISSION_WRITER,
    ) -> None:
        """Share Google Slides presentation with users.

        Args:
            presentation_id: ID of the presentation
            emails: List of email addresses to share with
            role: Permission role (reader, writer, commenter)
        """
        if emails:
            try:
                for email in emails:
                    permission = {"type": "user", "role": role, "emailAddress": email}
                    self._execute_request(
                        self.drive_service.permissions().create(
                            fileId=presentation_id,
                            body=permission,
                            sendNotificationEmail=True,
                            supportsAllDrives=True,
                        )
                    )
                    logger.info(f"Shared presentation with {email} as {role}")
            except HttpError as error:
                logger.error(f"Error sharing presentation: {error}")
                raise

    def _is_shared_drive_file(self, file_id: str) -> bool:
        """Return True when the file is backed by a Shared Drive."""
        return is_shared_drive_file(
            execute_request=self._execute_request,
            drive_service=self.drive_service,
            file_id=file_id,
        )

    def transfer_presentation_ownership(
        self, presentation_id: str, new_owner_email: str
    ) -> None:
        """Transfer ownership of a generated presentation to another user.

        Ownership transfer is only supported for files in My Drive.
        """
        if self._is_shared_drive_file(presentation_id):
            raise ValueError(
                "Ownership transfer is not supported for files in Shared Drives"
            )

        transfer_drive_file_ownership(
            execute_request=self._execute_request,
            drive_service=self.drive_service,
            file_id=presentation_id,
            new_owner_email=new_owner_email,
        )
        logger.info(
            "Transferred presentation ownership to %s (presentation_id=%s)",
            new_owner_email,
            presentation_id,
        )

    def get_presentation_url(self, presentation_id: str) -> str:
        """Get the public URL for a Google Slides presentation.

        Args:
            presentation_id: ID of the presentation

        Returns:
            Public URL to access the presentation
        """
        return f"https://docs.google.com/presentation/d/{presentation_id}"

    def get_presentation_page_size(
        self, presentation_id: str
    ) -> Optional[Tuple[int, int]]:
        """Get presentation page size in points when available."""
        start = time.time()
        success = False

        try:
            response = self._execute_request(
                self.slides_service.presentations().get(
                    presentationId=presentation_id, fields="pageSize"
                )
            )

            page_size = response.get("pageSize", {})
            width_pt = self._dimension_to_points(page_size.get("width"))
            height_pt = self._dimension_to_points(page_size.get("height"))

            if width_pt is None or height_pt is None:
                logger.warning(
                    "Unable to determine page size for presentation '%s'; "
                    "using fallback dimensions",
                    presentation_id,
                )
                return None

            success = True
            return width_pt, height_pt
        except Exception as error:
            logger.warning(
                "Failed to fetch page size for presentation '%s': %s",
                presentation_id,
                error,
            )
            return None
        finally:
            log_api_operation(
                "google_slides",
                "get_page_size",
                success=success,
                duration=time.time() - start,
                presentation_id=presentation_id,
            )

    def _get_or_create_destination_folder(self) -> Optional[str]:
        """Find or create a dynamic subfolder for the presentation."""
        parent_folder_id = self.config.presentation_folder_id
        folder_name = self.config.new_folder_name
        folder_name_fn = self.config.new_folder_name_fn

        if folder_name_fn and callable(folder_name_fn):
            folder_name = folder_name_fn(folder_name)

        if not parent_folder_id or not folder_name:
            return parent_folder_id

        cache_key = (parent_folder_id, folder_name)
        if cache_key in _folder_id_cache:
            return _folder_id_cache[cache_key]

        with _folder_creation_lock:
            if cache_key in _folder_id_cache:
                return _folder_id_cache[cache_key]

            # Escape single quotes for Drive query
            escaped = str(folder_name).replace("'", r"\'")

            try:
                # Look up an existing folder with that name under the parent
                query = (
                    f"'{parent_folder_id}' in parents and "
                    "mimeType = 'application/vnd.google-apps.folder' and "
                    f"name = '{escaped}' and trashed = false"
                )
                resp = self._execute_request(
                    self.drive_service.files().list(
                        q=query,
                        pageSize=1,
                        fields="files(id)",
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                )
                files = resp.get("files", [])
                if files:
                    folder_id = files[0]["id"]
                    logger.info(
                        "Using existing destination folder '%s' (id=%s)",
                        folder_name,
                        folder_id,
                    )
                    _folder_id_cache[cache_key] = folder_id
                    return folder_id

                # Create the folder
                new_folder = self._execute_request(
                    self.drive_service.files().create(
                        body={
                            "name": folder_name,
                            "mimeType": "application/vnd.google-apps.folder",
                            "parents": [parent_folder_id],
                        },
                        fields="id",
                        supportsAllDrives=True,
                    )
                )
                folder_id = new_folder.get("id")
                logger.info(
                    "Created destination folder '%s' (id=%s)", folder_name, folder_id
                )
                _folder_id_cache[cache_key] = folder_id
                return folder_id

            except HttpError as e:
                # Don’t block the workflow—fall back to the parent
                logger.error(
                    "Find/create destination folder failed for '%s': %s", folder_name, e
                )
                return parent_folder_id

    def _create_presentation(self, title: str) -> str:
        """Create new presentation."""
        start_time = time.time()
        try:
            body = {"title": title}
            presentation = self._execute_request(
                self.slides_service.presentations().create(body=body)
            )
            presentation_id = presentation.get("presentationId")

            destination_folder_id = self._get_or_create_destination_folder()

            # Move to folder if specified
            if destination_folder_id:
                try:
                    # Get the file to update its parents
                    file = self._execute_request(
                        self.drive_service.files().get(
                            fileId=presentation_id,
                            fields="parents",
                            supportsAllDrives=True,
                        )
                    )
                    previous_parents = ",".join(file.get("parents"))
                    self._execute_request(
                        self.drive_service.files().update(
                            fileId=presentation_id,
                            addParents=destination_folder_id,
                            removeParents=previous_parents,
                            fields="id, parents",
                            supportsAllDrives=True,
                        )
                    )
                except HttpError as e:
                    logger.warning(
                        f"Presentation {presentation_id} created, but failed to move to folder "
                        f"'{destination_folder_id}'. Please check if the folder exists "
                        f"and the service account has permissions. Error: {e}"
                    )

            duration = time.time() - start_time
            log_api_operation(
                "google_slides",
                "create_presentation",
                True,
                duration,
                title=title,
                presentation_id=presentation_id,
                folder_id=destination_folder_id or "none",
            )
            return presentation_id
        except HttpError as error:
            duration = time.time() - start_time
            log_api_operation(
                "google_slides",
                "create_presentation",
                False,
                duration,
                error=str(error),
                title=title,
            )
            raise

    def _copy_template(self, template_id: str, title: str) -> str:
        """Copy template presentation."""
        try:
            destination_folder_id = self._get_or_create_destination_folder()
            body: Dict[str, Any] = {"name": title}
            if destination_folder_id:
                body["parents"] = [destination_folder_id]

            copied = self._execute_request(
                self.drive_service.files().copy(
                    fileId=template_id, body=body, supportsAllDrives=True
                )
            )
            presentation_id = copied.get("id")
            logger.info(f"Copied template to '{title}' with ID: {presentation_id}")
            return presentation_id
        except HttpError as error:
            logger.error(f"Error copying template: {error}")
            raise

    def _upload_image_to_drive(
        self, image_bytes: bytes, filename: str
    ) -> Tuple[str, str]:
        """Upload image to Google Drive and return public URL and file ID."""
        start_time = time.time()
        try:
            # Prioritize dedicated image folder, fallback to presentation folder
            destination_folder_id = (
                self.config.drive_folder_id or self._get_or_create_destination_folder()
            )

            file_metadata: Dict[str, Any] = {"name": filename}
            if destination_folder_id:
                file_metadata["parents"] = [destination_folder_id]

            media = MediaIoBaseUpload(
                io.BytesIO(image_bytes), mimetype="image/png", resumable=True
            )

            uploaded_file = self._execute_request(
                self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                )
            )

            file_id = uploaded_file.get("id")

            sharing_mode = getattr(self.config, "chart_image_sharing_mode", "public")
            if sharing_mode == "public":
                self._execute_request(
                    self.drive_service.permissions().create(
                        fileId=file_id,
                        body={"role": "reader", "type": "anyone"},
                        supportsAllDrives=True,
                    )
                )
                if Timing.GOOGLE_DRIVE_PERMISSION_PROPAGATION_DELAY_S > 0:
                    time.sleep(Timing.GOOGLE_DRIVE_PERMISSION_PROPAGATION_DELAY_S)
            else:
                logger.info(
                    "Chart image sharing mode is restricted; skipping public Drive permission "
                    "(file_id=%s).",
                    file_id,
                )

            public_url = f"https://drive.google.com/uc?id={file_id}"
            duration = time.time() - start_time
            log_api_operation(
                "google_drive",
                "upload_image",
                True,
                duration,
                filename=filename,
                file_id=file_id,
                size_bytes=len(image_bytes),
            )
            return public_url, file_id

        except HttpError as error:
            duration = time.time() - start_time
            log_api_operation(
                "google_drive",
                "upload_image",
                False,
                duration,
                error=str(error),
                filename=filename,
            )
            raise

    def _batch_update(
        self, presentation_id: str, requests: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute batch of slide updates."""
        if not requests:
            return {}

        start_time = time.time()
        try:
            body = {"requests": requests}
            response = self._execute_request(
                self.slides_service.presentations().batchUpdate(
                    presentationId=presentation_id, body=body
                )
            )
            duration = time.time() - start_time
            log_api_operation(
                "google_slides",
                "batch_update",
                True,
                duration,
                presentation_id=presentation_id,
                requests_count=len(requests),
            )
            return response
        except HttpError as error:
            duration = time.time() - start_time
            error_details = (
                error.content.decode("utf-8")
                if hasattr(error, "content")
                else str(error)
            )
            log_api_operation(
                "google_slides",
                "batch_update",
                False,
                duration,
                error=error_details,
                presentation_id=presentation_id,
                requests_count=len(requests),
            )
            logger.error(
                f"Batch update failed for presentation {presentation_id}. Error details: {error_details}"
            )
            raise

    def delete_chart_image(self, file_id: str) -> None:
        """Delete (trash) an image from Google Drive."""
        try:
            # Try to move to trash first (requires fewer permissions than delete)
            body = {"trashed": True}
            self._execute_request(
                self.drive_service.files().update(
                    fileId=file_id, body=body, supportsAllDrives=True
                )
            )
            logger.info(f"Trashed chart image with file_id: {file_id}")
        except HttpError as error:
            if error.resp.status == 403:
                logger.warning(
                    f"Could not trash chart image {file_id} (Permission denied). "
                    "Service Account may lack 'Content Manager' role on the Shared Drive. "
                    "File remains in Drive."
                )
            else:
                logger.error(f"Error trashing file {file_id}: {error}")
            # Do not re-raise, we want to continue cleanup
