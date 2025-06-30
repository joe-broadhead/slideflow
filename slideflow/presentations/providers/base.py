"""
Abstract Base Classes for Presentation Providers

Defines the interface that all presentation providers must implement,
enabling support for multiple platforms while maintaining consistent APIs.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field


class ProviderSlideResult(BaseModel):
    """Result from slide operations in a presentation provider."""
    slide_id: str
    chart_urls: List[Tuple[str, str]]  # (image_url, public_url) pairs
    replacements_made: int


class ProviderPresentationResult(BaseModel):
    """Result from presentation operations in a presentation provider."""
    presentation_id: str
    presentation_url: str
    slide_results: List[ProviderSlideResult]
    
    @property
    def total_charts_generated(self) -> int:
        """Total number of charts generated across all slides."""
        return sum(len(slide.chart_urls) for slide in self.slide_results)
    
    @property 
    def total_replacements_made(self) -> int:
        """Total number of replacements made across all slides."""
        return sum(slide.replacements_made for slide in self.slide_results)


class PresentationProviderConfig(BaseModel):
    """Base configuration for presentation providers."""
    provider_type: str = Field(..., description="Type of presentation provider")
    

class PresentationProvider(ABC):
    """Abstract base class for all presentation providers."""
    
    def __init__(self, config: PresentationProviderConfig):
        """Initialize the presentation provider.
        
        Args:
            config: Provider-specific configuration
        """
        self.config = config
    
    @abstractmethod
    def create_presentation(self, 
                          name: str, 
                          template_id: Optional[str] = None) -> str:
        """Create a new presentation.
        
        Args:
            name: Name of the presentation
            template_id: Optional template to copy from
            
        Returns:
            Presentation ID
        """
        pass
    
    @abstractmethod
    def upload_chart_image(self, 
                          presentation_id: str,
                          image_data: bytes, 
                          filename: str) -> Tuple[str, str]:
        """Upload a chart image to the presentation platform.
        
        Args:
            presentation_id: ID of the presentation
            image_data: Chart image as bytes
            filename: Name for the image file
            
        Returns:
            Tuple of (image_url, public_url)
        """
        pass
    
    @abstractmethod
    def insert_chart_to_slide(self,
                             presentation_id: str,
                             slide_id: str, 
                             image_url: str,
                             x: float,
                             y: float,
                             width: float, 
                             height: float) -> None:
        """Insert a chart image into a slide.
        
        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            image_url: URL of the chart image
            x, y: Position coordinates
            width, height: Chart dimensions
        """
        pass
    
    @abstractmethod
    def replace_text_in_slide(self,
                             presentation_id: str, 
                             slide_id: str,
                             placeholder: str,
                             replacement: str) -> int:
        """Replace text in a slide.
        
        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            placeholder: Text to replace
            replacement: Replacement text
            
        Returns:
            Number of replacements made
        """
        pass
    
    @abstractmethod
    def share_presentation(self,
                          presentation_id: str,
                          emails: List[str], 
                          role: str = "writer") -> None:
        """Share the presentation with users.
        
        Args:
            presentation_id: ID of the presentation
            emails: List of email addresses to share with
            role: Permission role (reader, writer, commenter)
        """
        pass
    
    @abstractmethod
    def get_presentation_url(self, presentation_id: str) -> str:
        """Get the public URL for a presentation.
        
        Args:
            presentation_id: ID of the presentation
            
        Returns:
            Public URL to access the presentation
        """
        pass