"""
Google Slides Presentation Provider

Implementation of the PresentationProvider interface for Google Slides.
"""

import io
import time
from pathlib import Path
from typing import List, Tuple, Optional, Literal, Dict, Any
from pydantic import Field

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials

from slideflow.presentations.providers.base import (
    PresentationProvider, 
    PresentationProviderConfig
)
from slideflow.utilities.exceptions import AuthenticationError
from slideflow.constants import GoogleSlides
from slideflow.utilities.logging import get_logger, log_api_operation

logger = get_logger(__name__)


class GoogleSlidesProviderConfig(PresentationProviderConfig):
    """Configuration for Google Slides provider."""
    provider_type: Literal["google_slides"] = "google_slides"
    credentials_path: str = Field(..., description="Path to Google service account credentials")
    template_id: Optional[str] = Field(None, description="Google Slides template ID to copy from")
    drive_folder_id: Optional[str] = Field(None, description="Google Drive folder ID for storing images")
    presentation_folder_id: Optional[str] = Field(None, description="Google Drive folder ID for presentations")
    share_with: List[str] = Field(default_factory=list, description="Email addresses to share presentation with")
    share_role: str = Field(GoogleSlides.PERMISSION_WRITER, description="Permission role: reader, writer, or commenter")


class GoogleSlidesProvider(PresentationProvider):
    """Google Slides implementation of PresentationProvider."""
    
    SCOPES = [
        'https://www.googleapis.com/auth/presentations',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.file'
    ]
    
    def __init__(self, config: GoogleSlidesProviderConfig):
        """Initialize Google Slides provider.
        
        Args:
            config: Google Slides specific configuration
        """
        super().__init__(config)
        self.config: GoogleSlidesProviderConfig = config
        
        # Initialize Google API services
        credentials_path = Path(config.credentials_path)
        if not credentials_path.exists():
            raise AuthenticationError(f"Credentials file not found: {config.credentials_path}")

        credentials = Credentials.from_service_account_file(
            str(credentials_path),
            scopes=self.SCOPES
        )

        self.slides_service = build('slides', 'v1', credentials=credentials)
        self.drive_service = build('drive', 'v3', credentials=credentials)
    
    def create_presentation(self, 
                          name: str, 
                          template_id: Optional[str] = None) -> str:
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
    
    def upload_chart_image(self, 
                          presentation_id: str,
                          image_data: bytes, 
                          filename: str) -> Tuple[str, str]:
        """Upload chart image to Google Drive.
        
        Args:
            presentation_id: ID of the presentation (for folder context)
            image_data: Chart image as bytes
            filename: Name for the image file
            
        Returns:
            Tuple of (image_url, public_url)
        """
        url = self._upload_image_to_drive(image_data, filename)
        return (url, url)  # Both URLs are the same for Google Drive
    
    def insert_chart_to_slide(self,
                             presentation_id: str,
                             slide_id: str, 
                             image_url: str,
                             x: float,
                             y: float,
                             width: float, 
                             height: float) -> None:
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
    
    def replace_text_in_slide(self,
                             presentation_id: str, 
                             slide_id: str,
                             placeholder: str,
                             replacement: str) -> int:
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
    
    def share_presentation(self,
                          presentation_id: str,
                          emails: List[str], 
                          role: str = GoogleSlides.PERMISSION_WRITER) -> None:
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
                        fileId=presentation_id,
                        body=permission,
                        sendNotificationEmail=True
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
    
    # Private helper methods
    
    def _create_presentation(self, title: str) -> str:
        """Create new presentation."""
        start_time = time.time()
        try:
            body = {'title': title}
            presentation = self.slides_service.presentations().create(body=body).execute()
            presentation_id = presentation.get('presentationId')
            
            # Move to folder if specified
            if self.config.presentation_folder_id:
                file_metadata = {'parents': [self.config.presentation_folder_id]}
                self.drive_service.files().update(
                    fileId=presentation_id,
                    body=file_metadata,
                    addParents=self.config.presentation_folder_id,
                    fields='id, parents'
                ).execute()
            
            duration = time.time() - start_time
            log_api_operation("google_slides", "create_presentation", True, duration, 
                            title=title, presentation_id=presentation_id, 
                            folder_id=self.config.presentation_folder_id or "none")
            return presentation_id
        except HttpError as error:
            duration = time.time() - start_time
            log_api_operation("google_slides", "create_presentation", False, duration, 
                            error=str(error), title=title)
            raise
    
    def _copy_template(self, template_id: str, title: str) -> str:
        """Copy template presentation."""
        try:
            body = {'name': title}
            if self.config.presentation_folder_id:
                body['parents'] = [self.config.presentation_folder_id]
                
            copied = self.drive_service.files().copy(
                fileId=template_id,
                body=body
            ).execute()
            presentation_id = copied.get('id')
            logger.info(f"Copied template to '{title}' with ID: {presentation_id}")
            return presentation_id
        except HttpError as error:
            logger.error(f"Error copying template: {error}")
            raise
    
    def _upload_image_to_drive(self, image_bytes: bytes, filename: str) -> str:
        """Upload image to Google Drive and return public URL."""
        start_time = time.time()
        try:
            file_metadata = {'name': filename}
            if self.config.drive_folder_id:
                file_metadata['parents'] = [self.config.drive_folder_id]
            
            media = MediaIoBaseUpload(
                io.BytesIO(image_bytes),
                mimetype='image/png',
                resumable=True
            )
            
            uploaded_file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = uploaded_file.get('id')

            # Make public
            self.drive_service.permissions().create(
                fileId=file_id,
                body={
                    'role': 'reader',
                    'type': 'anyone'
                }
            ).execute()

            public_url = f"https://drive.google.com/uc?id={file_id}"
            duration = time.time() - start_time
            log_api_operation("google_drive", "upload_image", True, duration,
                            filename=filename, file_id=file_id, size_bytes=len(image_bytes))
            return public_url
            
        except HttpError as error:
            duration = time.time() - start_time
            log_api_operation("google_drive", "upload_image", False, duration,
                            error=str(error), filename=filename)
            raise
    
    def _batch_update(self, presentation_id: str, requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute batch of slide updates."""
        if not requests:
            return {}
        
        start_time = time.time()
        try:
            body = {'requests': requests}
            response = self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id,
                body=body
            ).execute()
            duration = time.time() - start_time
            log_api_operation("google_slides", "batch_update", True, duration,
                            presentation_id=presentation_id, requests_count=len(requests))
            return response
        except HttpError as error:
            duration = time.time() - start_time
            log_api_operation("google_slides", "batch_update", False, duration,
                            error=str(error), presentation_id=presentation_id, requests_count=len(requests))
            raise