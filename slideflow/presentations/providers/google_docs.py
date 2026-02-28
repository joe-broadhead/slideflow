"""Google Docs provider scaffold for Slideflow newsletter workflows.

This module introduces the `google_docs` provider type and core provider wiring.
It intentionally focuses on provider plumbing and safe defaults; advanced
section-marker newsletter behavior is implemented in follow-up work.
"""

from __future__ import annotations

import io
import os
import threading
import time
from typing import Any, Dict, List, Literal, Optional, Tuple

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from pydantic import Field

from slideflow.constants import Environment, GoogleSlides, Timing
from slideflow.presentations.providers.base import (
    PresentationProvider,
    PresentationProviderConfig,
)
from slideflow.utilities.auth import handle_google_credentials
from slideflow.utilities.exceptions import AuthenticationError
from slideflow.utilities.logging import get_logger
from slideflow.utilities.rate_limiter import RateLimiter

logger = get_logger(__name__)
_docs_rate_limiter: Optional[RateLimiter] = None
_rate_limiter_lock = threading.Lock()


def _get_rate_limiter(rps: float, force_update: bool = False) -> RateLimiter:
    """Get or create the global Google Docs API rate limiter."""
    global _docs_rate_limiter
    with _rate_limiter_lock:
        if _docs_rate_limiter is None:
            _docs_rate_limiter = RateLimiter(rps)
        elif force_update:
            _docs_rate_limiter.set_rate(rps)
        return _docs_rate_limiter


class GoogleDocsProviderConfig(PresentationProviderConfig):
    """Configuration for the Google Docs provider."""

    provider_type: Literal["google_docs"] = "google_docs"
    credentials: Optional[str] = Field(
        None,
        description="Google credentials as a file path or JSON string.",
    )
    template_id: Optional[str] = Field(
        None,
        description="Google Docs template ID to copy from when creating documents.",
    )
    document_folder_id: Optional[str] = Field(
        None,
        description="Google Drive folder ID for created documents.",
    )
    drive_folder_id: Optional[str] = Field(
        None,
        description="Google Drive folder ID for uploaded chart images.",
    )
    section_marker_prefix: str = Field(
        "{{SECTION:",
        description="Section marker prefix for marker-based section resolution.",
    )
    section_marker_suffix: str = Field(
        "}}",
        description="Section marker suffix for marker-based section resolution.",
    )
    remove_section_markers: bool = Field(
        False,
        description="Whether to remove section markers after rendering.",
    )
    default_chart_width_pt: float = Field(
        GoogleSlides.DEFAULT_CHART_WIDTH,
        gt=0,
        description="Default inline chart width for docs insertion.",
    )
    share_with: List[str] = Field(
        default_factory=list,
        description="Email addresses to share the generated document with.",
    )
    share_role: str = Field(
        GoogleSlides.PERMISSION_WRITER,
        description="Share role: reader, writer, or commenter.",
    )
    requests_per_second: float = Field(
        1.0,
        gt=0,
        description="Maximum Google API requests per second.",
    )
    strict_cleanup: bool = Field(
        False,
        description="If true, fail rendering when chart image cleanup fails.",
    )


class GoogleDocsProvider(PresentationProvider):
    """Google Docs provider implementation.

    This provider currently supports baseline operations and intentionally keeps
    slide-scoped/marker-scoped rendering behavior for a follow-up iteration.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
    ]

    def __init__(self, config: GoogleDocsProviderConfig):
        super().__init__(config)
        self.config: GoogleDocsProviderConfig = config

        loaded_credentials = handle_google_credentials(
            config.credentials,
            env_var_names=[
                Environment.GOOGLE_DOCS_CREDENTIALS,
                Environment.GOOGLE_SLIDEFLOW_CREDENTIALS,
            ],
        )

        try:
            credentials = Credentials.from_service_account_info(
                loaded_credentials, scopes=self.SCOPES
            )
        except Exception as error_msg:  # pragma: no cover - exercised via tests
            raise AuthenticationError(f"Credentials authentication failed: {error_msg}")

        self.docs_service = build("docs", "v1", credentials=credentials)
        self.drive_service = build("drive", "v3", credentials=credentials)
        self.rate_limiter = _get_rate_limiter(self.config.requests_per_second)

    def _execute_request(self, request):
        """Execute Google API request with shared rate limiting."""
        self.rate_limiter.wait()
        return request.execute(num_retries=3)

    def run_preflight_checks(self) -> List[Tuple[str, bool, str]]:
        has_credentials = bool(self.config.credentials) or bool(
            os.getenv(Environment.GOOGLE_DOCS_CREDENTIALS)
            or os.getenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS)
        )

        checks: List[Tuple[str, bool, str]] = [
            (
                "google_docs_credentials_present",
                has_credentials,
                (
                    "Credentials found in config or supported environment variables"
                    if has_credentials
                    else "Missing credentials in config and environment"
                ),
            ),
            (
                "docs_service_initialized",
                self.docs_service is not None,
                (
                    "Google Docs API client initialized"
                    if self.docs_service is not None
                    else "Google Docs API client is not initialized"
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
        return checks

    def create_presentation(self, name: str, template_id: Optional[str] = None) -> str:
        template_to_use = template_id or self.config.template_id
        if template_to_use:
            return self._copy_template(template_to_use, name)
        return self._create_document(name)

    def upload_chart_image(
        self, presentation_id: str, image_data: bytes, filename: str
    ) -> Tuple[str, str]:
        del presentation_id
        return self._upload_image_to_drive(image_data, filename)

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
        """Insert chart inline in document.

        `slide_id` and positional arguments are accepted for interface
        compatibility and are intentionally ignored in this baseline phase.
        """
        del slide_id, x, y

        insert_index = self._get_document_insert_index(presentation_id)
        requests = [
            {
                "insertInlineImage": {
                    "uri": image_url,
                    "location": {"index": insert_index},
                    "objectSize": {
                        "width": {"magnitude": width, "unit": "PT"},
                        "height": {"magnitude": height, "unit": "PT"},
                    },
                }
            }
        ]
        self._execute_request(
            self.docs_service.documents().batchUpdate(
                documentId=presentation_id, body={"requests": requests}
            )
        )

    def _get_document_insert_index(self, document_id: str) -> int:
        """Resolve a safe inline-image insertion index for a Google Doc."""
        minimum_insert_index = 1
        try:
            document = self._execute_request(
                self.docs_service.documents().get(
                    documentId=document_id, fields="body/content/endIndex"
                )
            )
        except HttpError as error:
            logger.warning(
                "Could not resolve document insertion index for %s: %s. "
                "Using fallback index %s.",
                document_id,
                error,
                minimum_insert_index,
            )
            return minimum_insert_index

        if not isinstance(document, dict):
            return minimum_insert_index
        body = document.get("body", {})
        if not isinstance(body, dict):
            return minimum_insert_index
        content = body.get("content", [])
        if not isinstance(content, list):
            return minimum_insert_index

        for element in reversed(content):
            if not isinstance(element, dict):
                continue
            end_index = element.get("endIndex")
            if isinstance(end_index, int):
                return max(minimum_insert_index, end_index - 1)
        return minimum_insert_index

    def replace_text_in_slide(
        self, presentation_id: str, slide_id: str, placeholder: str, replacement: str
    ) -> int:
        """Replace text in document.

        `slide_id` is accepted for interface compatibility and is intentionally
        ignored in this baseline phase.
        """
        del slide_id

        response = self._execute_request(
            self.docs_service.documents().batchUpdate(
                documentId=presentation_id,
                body={
                    "requests": [
                        {
                            "replaceAllText": {
                                "containsText": {
                                    "text": placeholder,
                                    "matchCase": True,
                                },
                                "replaceText": replacement,
                            }
                        }
                    ]
                },
            )
        )

        replies = response.get("replies", []) if isinstance(response, dict) else []
        if replies and isinstance(replies[0], dict):
            replace_result = replies[0].get("replaceAllText")
            if isinstance(replace_result, dict):
                occurrences = replace_result.get("occurrencesChanged")
                if isinstance(occurrences, int):
                    return occurrences
        return 0

    def share_presentation(
        self, presentation_id: str, emails: List[str], role: str = "writer"
    ) -> None:
        if not emails:
            return

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

    def get_presentation_url(self, presentation_id: str) -> str:
        return f"https://docs.google.com/document/d/{presentation_id}"

    def delete_chart_image(self, file_id: str) -> None:
        try:
            self._execute_request(
                self.drive_service.files().update(
                    fileId=file_id, body={"trashed": True}, supportsAllDrives=True
                )
            )
            logger.info(f"Trashed chart image with file_id: {file_id}")
        except HttpError as error:
            status = getattr(getattr(error, "resp", None), "status", None)
            if status == 403:
                logger.warning(
                    "Could not trash chart image %s due to permission constraints.",
                    file_id,
                )
            else:
                logger.error("Error trashing file %s: %s", file_id, error)
            if self.config.strict_cleanup:
                raise

    def _create_document(self, title: str) -> str:
        created = self._execute_request(
            self.docs_service.documents().create(body={"title": title})
        )
        document_id = created.get("documentId")
        destination_folder_id = self.config.document_folder_id
        if destination_folder_id:
            self._move_file_to_folder(document_id, destination_folder_id)
        return document_id

    def _copy_template(self, template_id: str, title: str) -> str:
        body: Dict[str, Any] = {"name": title}
        if self.config.document_folder_id:
            body["parents"] = [self.config.document_folder_id]
        copied = self._execute_request(
            self.drive_service.files().copy(
                fileId=template_id, body=body, supportsAllDrives=True
            )
        )
        return copied.get("id")

    def _move_file_to_folder(self, file_id: str, folder_id: str) -> None:
        file_details = self._execute_request(
            self.drive_service.files().get(
                fileId=file_id, fields="parents", supportsAllDrives=True
            )
        )
        previous_parents = ",".join(file_details.get("parents", []))
        self._execute_request(
            self.drive_service.files().update(
                fileId=file_id,
                addParents=folder_id,
                removeParents=previous_parents,
                fields="id, parents",
                supportsAllDrives=True,
            )
        )

    def _upload_image_to_drive(
        self, image_bytes: bytes, filename: str
    ) -> Tuple[str, str]:
        file_metadata: Dict[str, Any] = {"name": filename}
        if self.config.drive_folder_id:
            file_metadata["parents"] = [self.config.drive_folder_id]

        media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype="image/png")
        uploaded_file = self._execute_request(
            self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
        )

        file_id = uploaded_file.get("id")
        self._execute_request(
            self.drive_service.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True,
            )
        )
        if Timing.GOOGLE_DRIVE_PERMISSION_PROPAGATION_DELAY_S > 0:
            time.sleep(Timing.GOOGLE_DRIVE_PERMISSION_PROPAGATION_DELAY_S)
        public_url = f"https://drive.google.com/uc?id={file_id}"
        return public_url, file_id
