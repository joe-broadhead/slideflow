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
    ...     credentials_path="/path/to/service_account.json",
    ...     template_id="1ABC123_template_id_XYZ789",
    ...     share_with=["viewer@example.com"],
    ...     share_role="reader"
    ... )
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
import time
import threading
from pathlib import Path
from pydantic import Field
from typing import List, Tuple, Optional, Literal, Dict, Any, Callable

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials

from slideflow.presentations.providers.base import (
    PresentationProvider, 
    PresentationProviderConfig
)
from slideflow.constants import GoogleSlides
from slideflow.utilities.exceptions import AuthenticationError
from slideflow.utilities.logging import get_logger, log_api_operation

logger = get_logger(__name__)
_folder_creation_lock = threading.Lock()
_folder_id_cache = {}

class GoogleSlidesProviderConfig(PresentationProviderConfig):
    """Configuration model for Google Slides presentation provider.
    
    This configuration class defines all parameters needed to configure the
    Google Slides provider, including authentication credentials, template
    settings, Drive folder organization, and default sharing permissions.
    
    Attributes:
        provider_type: Always "google_slides" for this provider.
        credentials_path: Path to Google service account credentials JSON file.
        template_id: Optional Google Slides template ID to copy from when creating presentations.
        drive_folder_id: Optional Google Drive folder ID for organizing uploaded chart images.
        presentation_folder_id: Optional Google Drive folder ID for organizing created presentations.
        share_with: List of email addresses to automatically share presentations with.
        share_role: Default permission role for shared presentations.
        
    Example:
        >>> config = GoogleSlidesProviderConfig(
        ...     provider_type="google_slides",
        ...     credentials_path="/path/to/service_account.json",
        ...     template_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        ...     drive_folder_id="1FolderID_for_images",
        ...     presentation_folder_id="1FolderID_for_presentations",
        ...     share_with=["team@company.com", "manager@company.com"],
        ...     share_role="reader"
        ... )
    """
    provider_type: Literal["google_slides"] = "google_slides"
    credentials_path: str = Field(..., description = "Path to Google service account credentials")
    template_id: Optional[str] = Field(None, description = "Google Slides template ID to copy from")
    presentation_folder_id: Optional[str] = Field(None, description = "Google Drive folder ID for presentations")
    new_folder_name: Optional[str] = Field(None, description="Name for a new subfolder to be created in the presentation_folder_id.")
    new_folder_name_fn: Optional[Callable] = Field(None, description="Function to generate the new subfolder name dynamically.")
    share_with: List[str] = Field(default_factory = list, description = "Email addresses to share presentation with")
    share_role: str = Field(GoogleSlides.PERMISSION_WRITER, description = "Permission role: reader, writer, or commenter")

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
        ...     credentials_path="/path/to/service_account.json"
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
        'https://www.googleapis.com/auth/presentations',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.file'
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
        if os.path.exists(config.credentials_path) and os.path.isfile(config.credentials_path):
            credentials_path = Path(config.credentials_path)

            if not credentials_path.exists():
                raise AuthenticationError(f"Credentials file not found: {config.credentials_path}")
            
            credentials = Credentials.from_service_account_file(
                str(credentials_path),
                scopes = self.SCOPES
            )
        else:
            try:
                credentials_data = json.loads(env_var_value)

                credentials = Credentials.from_service_account_info(
                    str(config.credentials_path),
                    scopes = self.SCOPES
                )
            else:
                raise AuthenticationError(f"Credentials string not recognized as valid: {config.credentials_path}")
        
        self.slides_service = build('slides', 'v1', credentials = credentials)
        self.drive_service = build('drive', 'v3', credentials = credentials)
    
    def create_presentation(
        self, 
        name: str, 
        template_id: Optional[str] = None
    ) -> str:
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
        self, 
        presentation_id: str,
        image_data: bytes, 
        filename: str
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
        height: float
    ) -> None:
        """Insert chart image into Google Slides slide.
        
        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            image_url: URL of the chart image
            x, y: Position coordinates
            width, height: Chart dimensions
        """
        requests = [{
            'createImage': {
                'url': image_url,
                'elementProperties': {
                    'pageObjectId': slide_id,
                    'size': {
                        'width': {'magnitude': width, 'unit': 'PT'},
                        'height': {'magnitude': height, 'unit': 'PT'}
                    },
                    'transform': {
                        'scaleX': 1,
                        'scaleY': 1,
                        'translateX': x,
                        'translateY': y,
                        'unit': 'PT'
                    }
                }
            }
        }]
        
        self._batch_update(presentation_id, requests)
    
    def replace_text_in_slide(
        self,
        presentation_id: str, 
        slide_id: str,
        placeholder: str,
        replacement: str
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
        requests = [{
            'replaceAllText': {
                'containsText': {
                    'text': placeholder,
                    'matchCase': True
                },
                'replaceText': replacement,
                'pageObjectIds': [slide_id]
            }
        }]
        
        response = self._batch_update(presentation_id, requests)
        
        # Extract number of replacements from response
        if 'replies' in response and response['replies']:
            reply = response['replies'][0]
            if 'replaceAllText' in reply:
                return reply['replaceAllText'].get('occurrencesChanged', 0)
        
        return 0
    
    def share_presentation(
        self,
        presentation_id: str,
        emails: List[str], 
        role: str = GoogleSlides.PERMISSION_WRITER
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
                    permission = {
                        'type': 'user',
                        'role': role,
                        'emailAddress': email
                    }
                    self.drive_service.permissions().create(
                        fileId = presentation_id,
                        body = permission,
                        sendNotificationEmail=True,
                        supportsAllDrives=True
                    ).execute()
                    logger.info(f"Shared presentation with {email} as {role}")
            except HttpError as error:
                logger.error(f"Error sharing presentation: {error}")
                raise
    
    def get_presentation_url(self, presentation_id: str) -> str:
        """Get the public URL for a Google Slides presentation.
        
        Args:
            presentation_id: ID of the presentation
            
        Returns:
            Public URL to access the presentation
        """
        return f"https://docs.google.com/presentation/d/{presentation_id}"

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
                resp = (
                    self.drive_service.files()
                    .list(
                        q=query,
                        pageSize=1,
                        fields="files(id)",
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )
                files = resp.get("files", [])
                if files:
                    folder_id = files[0]["id"]
                    logger.info("Using existing destination folder '%s' (id=%s)", folder_name, folder_id)
                    _folder_id_cache[cache_key] = folder_id
                    return folder_id

                # Create the folder
                new_folder = (
                    self.drive_service.files()
                    .create(
                        body={
                            "name": folder_name,
                            "mimeType": "application/vnd.google-apps.folder",
                            "parents": [parent_folder_id],
                        },
                        fields="id",
                        supportsAllDrives=True,
                    )
                    .execute()
                )
                folder_id = new_folder.get("id")
                logger.info("Created destination folder '%s' (id=%s)", folder_name, folder_id)
                _folder_id_cache[cache_key] = folder_id
                return folder_id

            except HttpError as e:
                # Don’t block the workflow—fall back to the parent
                logger.error("Find/create destination folder failed for '%s': %s", folder_name, e)
                return parent_folder_id

    
    def _create_presentation(self, title: str) -> str:
        """Create new presentation."""
        start_time = time.time()
        try:
            body = {'title': title}
            presentation = self.slides_service.presentations().create(body=body).execute()
            presentation_id = presentation.get('presentationId')

            destination_folder_id = self._get_or_create_destination_folder()
            
            # Move to folder if specified
            if destination_folder_id:
                try:
                    # Get the file to update its parents
                    file = self.drive_service.files().get(fileId=presentation_id, fields='parents', supportsAllDrives=True).execute()
                    previous_parents = ",".join(file.get('parents'))
                    self.drive_service.files().update(
                        fileId=presentation_id,
                        addParents=destination_folder_id,
                        removeParents=previous_parents,
                        fields='id, parents',
                        supportsAllDrives=True
                    ).execute()
                except HttpError as e:
                    logger.warning(
                        f"Presentation {presentation_id} created, but failed to move to folder "
                        f"'{destination_folder_id}'. Please check if the folder exists "
                        f"and the service account has permissions. Error: {e}"
                    )
            
            duration = time.time() - start_time
            log_api_operation("google_slides", "create_presentation", True, duration, 
                            title = title, presentation_id = presentation_id, 
                            folder_id = destination_folder_id or "none")
            return presentation_id
        except HttpError as error:
            duration = time.time() - start_time
            log_api_operation("google_slides", "create_presentation", False, duration, 
                            error = str(error), title = title)
            raise
    
    def _copy_template(self, template_id: str, title: str) -> str:
        """Copy template presentation."""
        try:
            destination_folder_id = self._get_or_create_destination_folder()
            body = {"name": title}
            if destination_folder_id:
                body["parents"] = [destination_folder_id]
                
            copied = self.drive_service.files().copy(
                fileId=template_id,
                body=body,
                supportsAllDrives=True
            ).execute()
            presentation_id = copied.get("id")
            logger.info(f"Copied template to '{title}' with ID: {presentation_id}")
            return presentation_id
        except HttpError as error:
            logger.error(f"Error copying template: {error}")
            raise
    
    def _upload_image_to_drive(self, image_bytes: bytes, filename: str) -> Tuple[str, str]:
        """Upload image to Google Drive and return public URL and file ID."""
        start_time = time.time()
        try:
            file_metadata = {"name": filename}
            
            media = MediaIoBaseUpload(
                io.BytesIO(image_bytes),
                mimetype = "image/png",
                resumable = True
            )
            
            uploaded_file = self.drive_service.files().create(
                body = file_metadata,
                media_body = media,
                fields = 'id',
                supportsAllDrives = True
            ).execute()
            
            file_id = uploaded_file.get('id')

            # Make public
            self.drive_service.permissions().create(
                fileId = file_id,
                body = {
                    'role': 'reader',
                    'type': 'anyone'
                },
                supportsAllDrives = True
            ).execute()

            time.sleep(2)

            public_url = f"https://drive.google.com/uc?id={file_id}"
            duration = time.time() - start_time
            log_api_operation("google_drive", "upload_image", True, duration,
                            filename = filename, file_id = file_id, size_bytes = len(image_bytes))
            return public_url, file_id
            
        except HttpError as error:
            duration = time.time() - start_time
            log_api_operation("google_drive", "upload_image", False, duration,
                            error = str(error), filename = filename)
            raise
    
    def _batch_update(self, presentation_id: str, requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute batch of slide updates."""
        if not requests:
            return {}
        
        start_time = time.time()
        try:
            body = {'requests': requests}
            response = self.slides_service.presentations().batchUpdate(
                presentationId = presentation_id,
                body = body
            ).execute()
            duration = time.time() - start_time
            log_api_operation("google_slides", "batch_update", True, duration,
                            presentation_id = presentation_id, requests_count = len(requests))
            return response
        except HttpError as error:
            duration = time.time() - start_time
            log_api_operation("google_slides", "batch_update", False, duration,
                            error = str(error), presentation_id = presentation_id, requests_count = len(requests))
            raise

    def delete_chart_image(self, file_id: str) -> None:
        """Delete an image from Google Drive."""
        try:
            self.drive_service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            logger.info(f"Deleted chart image with file_id: {file_id}")
        except HttpError as error:
            logger.error(f"Error deleting file {file_id}: {error}")
            # Do not re-raise, we want to continue cleanup