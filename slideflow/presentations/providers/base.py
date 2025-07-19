"""Base classes and interfaces for presentation providers in Slideflow.

This module provides the foundational abstractions for the presentation provider
system, including the base PresentationProvider class and result models. These
classes establish the contract that all concrete provider implementations must
follow for consistent presentation operations across different platforms.

The base system provides:
    - Abstract interface for presentation operations
    - Result models for tracking operation outcomes
    - Configuration base classes for provider setup
    - Type-safe operation definitions with comprehensive documentation

Example:
    Creating a custom provider:
    
    >>> from slideflow.presentations.providers.base import PresentationProvider
    >>> from slideflow.presentations.providers.base import PresentationProviderConfig
    >>> 
    >>> class MyProviderConfig(PresentationProviderConfig):
    ...     provider_type: str = "my_provider"
    ...     api_key: str
    >>> 
    >>> class MyProvider(PresentationProvider):
    ...     def __init__(self, config: MyProviderConfig):
    ...         super().__init__(config)
    ...         self.api_key = config.api_key
    ...     
    ...     def create_presentation(self, name: str, template_id: Optional[str] = None) -> str:
    ...         # Implementation for creating presentations
    ...         return "new_presentation_id"
"""

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple

class ProviderSlideResult(BaseModel):
    """Result model for individual slide operations in presentation providers.
    
    This model captures the outcomes of operations performed on a single slide,
    including chart insertions and text replacements. It provides tracking
    capabilities for monitoring the success and extent of slide modifications.
    
    Attributes:
        slide_id: Unique identifier for the slide that was modified.
        chart_urls: List of tuples containing (image_url, public_url) pairs
            for charts that were inserted into the slide.
        replacements_made: Number of text replacements performed on the slide.
        
    Example:
        >>> slide_result = ProviderSlideResult(
        ...     slide_id="slide_123",
        ...     chart_urls=[("https://example.com/chart1.png", "https://public.com/chart1")],
        ...     replacements_made=3
        ... )
        >>> print(f"Slide {slide_result.slide_id} had {slide_result.replacements_made} replacements")
    """
    slide_id: str
    chart_urls: List[Tuple[str, str]]
    replacements_made: int

class ProviderPresentationResult(BaseModel):
    """Result model for complete presentation operations.
    
    This model aggregates the results of all operations performed on a presentation,
    providing a comprehensive summary of what was accomplished including chart
    generation, text replacements, and presentation metadata.
    
    Attributes:
        presentation_id: Unique identifier for the presentation.
        presentation_url: Public URL where the presentation can be accessed.
        slide_results: List of ProviderSlideResult objects, one for each slide
            that was modified during the operation.
    
    Example:
        >>> presentation_result = ProviderPresentationResult(
        ...     presentation_id="pres_123",
        ...     presentation_url="https://docs.google.com/presentation/d/pres_123",
        ...     slide_results=[
        ...         ProviderSlideResult(slide_id="slide_1", chart_urls=[], replacements_made=2),
        ...         ProviderSlideResult(slide_id="slide_2", chart_urls=[("url1", "pub1")], replacements_made=1)
        ...     ]
        ... )
        >>> print(f"Total charts: {presentation_result.total_charts_generated}")
        >>> print(f"Total replacements: {presentation_result.total_replacements_made}")
    """
    presentation_id: str
    presentation_url: str
    slide_results: List[ProviderSlideResult]
    
    @property
    def total_charts_generated(self) -> int:
        """Calculate total number of charts generated across all slides.
        
        Returns:
            Sum of all chart URLs from all slide results.
        """
        return sum(len(slide.chart_urls) for slide in self.slide_results)
    
    @property 
    def total_replacements_made(self) -> int:
        """Calculate total number of text replacements made across all slides.
        
        Returns:
            Sum of all replacements made from all slide results.
        """
        return sum(slide.replacements_made for slide in self.slide_results)

class PresentationProviderConfig(BaseModel):
    """Base configuration model for presentation providers.
    
    This class provides the foundation for all presentation provider configuration
    models. It defines the common fields and behavior that all provider configs
    must implement, ensuring consistent configuration handling across different
    presentation platforms.
    
    Attributes:
        provider_type: String identifier for the type of provider. This is used
            by the factory system to determine which provider class to instantiate.
    
    Example:
        Creating a custom provider configuration:
        
        >>> class MyProviderConfig(PresentationProviderConfig):
        ...     provider_type: str = "my_provider"
        ...     api_key: str = Field(..., description="API key for authentication")
        ...     base_url: str = Field("https://api.example.com", description="API base URL")
        >>> 
        >>> config = MyProviderConfig(
        ...     provider_type="my_provider",
        ...     api_key="secret123"
        ... )
    """
    provider_type: str = Field(..., description = "Type of presentation provider")

class PresentationProvider(ABC):
    """Abstract base class for all presentation providers in Slideflow.
    
    This class defines the interface that all presentation providers must implement
    to integrate with the Slideflow presentation system. It provides a consistent
    API for presentation operations across different platforms and services.
    
    The provider system follows a consistent pattern where each provider:
    1. Accepts a configuration object in its constructor
    2. Implements all abstract methods for presentation operations
    3. Handles platform-specific authentication and API interactions
    4. Returns standardized result objects for operation tracking
    
    Platform Integration:
        Providers handle their own authentication mechanisms, which may include
        API keys, OAuth tokens, service account credentials, or other
        platform-specific authentication methods. They also manage the translation
        between Slideflow's generic operations and platform-specific API calls.
    
    Example:
        Creating a presentation provider:
        
        >>> class CustomProvider(PresentationProvider):
        ...     def __init__(self, config: CustomProviderConfig):
        ...         super().__init__(config)
        ...         self.api_client = APIClient(config.api_key)
        ...     
        ...     def create_presentation(self, name: str, template_id: Optional[str] = None) -> str:
        ...         response = self.api_client.create_presentation(name, template_id)
        ...         return response['id']
        
        Using the provider:
        
        >>> config = CustomProviderConfig(provider_type="custom", api_key="key123")
        >>> provider = CustomProvider(config)
        >>> presentation_id = provider.create_presentation("My Report")
        >>> print(f"Created: {presentation_id}")
    """
    
    def __init__(self, config: PresentationProviderConfig):
        """Initialize the presentation provider with configuration.
        
        Args:
            config: Provider-specific configuration object that contains
                all necessary parameters for provider operation including
                authentication credentials and platform-specific settings.
        """
        self.config = config
    
    @abstractmethod
    def create_presentation(
        self, 
        name: str, 
        template_id: Optional[str] = None
    ) -> str:
        """Create a new presentation on the platform.
        
        Creates a new presentation with the specified name and optionally
        copies from a template. The implementation should handle platform-specific
        presentation creation and return a unique identifier for the new presentation.
        
        Args:
            name: The title/name for the new presentation.
            template_id: Optional platform-specific template identifier to copy from.
                If provided, the new presentation will be based on this template.
            
        Returns:
            Platform-specific unique identifier for the created presentation.
            
        Raises:
            AuthenticationError: If authentication fails or is required.
            PlatformError: If the platform API returns an error.
            TemplateNotFoundError: If template_id is provided but doesn't exist.
            
        Example:
            >>> provider = MyProvider(config)
            >>> presentation_id = provider.create_presentation("Q3 Report")
            >>> print(f"Created presentation: {presentation_id}")
            >>> 
            >>> # With template
            >>> templated_id = provider.create_presentation("Q4 Report", "template_123")
        """
        pass
    
    @abstractmethod
    def upload_chart_image(
        self, 
        presentation_id: str,
        image_data: bytes, 
        filename: str
    ) -> Tuple[str, str]:
        """Upload a chart image to the presentation platform.
        
        Uploads an image (typically a chart or graph) to the platform's storage
        system and returns URLs for accessing the image. The implementation should
        handle platform-specific upload mechanisms and ensure the image is accessible
        for insertion into presentation slides.
        
        Args:
            presentation_id: Unique identifier of the presentation context.
                Some platforms may use this for organizing uploaded assets.
            image_data: Raw image data as bytes. Typically PNG or JPEG format.
            filename: Desired filename for the uploaded image, including extension.
            
        Returns:
            Tuple containing (image_url, public_url) where:
                - image_url: Platform-internal URL for the uploaded image
                - public_url: Publicly accessible URL for the image (may be same as image_url)
                
        Raises:
            AuthenticationError: If authentication fails or is required.
            UploadError: If the image upload fails due to platform constraints.
            InvalidImageError: If the image data is corrupted or unsupported format.
            
        Example:
            >>> with open("chart.png", "rb") as f:
            ...     image_data = f.read()
            >>> image_url, public_url = provider.upload_chart_image(
            ...     "presentation_123", 
            ...     image_data, 
            ...     "monthly_sales_chart.png"
            ... )
            >>> print(f"Uploaded to: {public_url}")
        """
        pass
    
    @abstractmethod
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
        """Insert a chart image into a specific slide.
        
        Places an uploaded image (typically a chart or graph) into a slide at the
        specified position and size. The implementation should handle platform-specific
        image insertion APIs and coordinate systems.
        
        Args:
            presentation_id: Unique identifier of the presentation.
            slide_id: Unique identifier of the target slide within the presentation.
            image_url: URL of the uploaded image to insert (from upload_chart_image).
            x: Horizontal position coordinate for the image placement. Units depend
                on platform (typically points or pixels).
            y: Vertical position coordinate for the image placement.
            width: Width of the inserted image in platform-specific units.
            height: Height of the inserted image in platform-specific units.
            
        Raises:
            AuthenticationError: If authentication fails or is required.
            NotFoundError: If presentation_id or slide_id doesn't exist.
            InvalidImageError: If image_url is inaccessible or invalid.
            PositionError: If coordinates or dimensions are out of slide bounds.
            
        Example:
            >>> # Insert chart at top-left corner, 400x300 points
            >>> provider.insert_chart_to_slide(
            ...     "presentation_123",
            ...     "slide_1", 
            ...     "https://example.com/chart.png",
            ...     x=50, y=50, width=400, height=300
            ... )
        """
        pass
    
    @abstractmethod
    def replace_text_in_slide(
        self,
        presentation_id: str, 
        slide_id: str,
        placeholder: str,
        replacement: str
    ) -> int:
        """Replace text in a specific slide.
        
        Searches for occurrences of placeholder text within the specified slide
        and replaces them with the replacement text. The implementation should
        handle platform-specific text replacement APIs and return the count
        of successful replacements.
        
        Args:
            presentation_id: Unique identifier of the presentation.
            slide_id: Unique identifier of the target slide within the presentation.
            placeholder: Text string to search for and replace. Should be an exact
                match (case-sensitive unless platform specifies otherwise).
            replacement: Text string to replace the placeholder with.
            
        Returns:
            Number of text replacements that were successfully made in the slide.
            Returns 0 if no occurrences of the placeholder were found.
            
        Raises:
            AuthenticationError: If authentication fails or is required.
            NotFoundError: If presentation_id or slide_id doesn't exist.
            TextError: If text replacement operation fails.
            
        Example:
            >>> # Replace placeholder with actual data
            >>> replacements = provider.replace_text_in_slide(
            ...     "presentation_123",
            ...     "slide_1",
            ...     "{{COMPANY_NAME}}",
            ...     "Acme Corporation"
            ... )
            >>> print(f"Made {replacements} text replacements")
        """
        pass
    
    @abstractmethod
    def share_presentation(
        self,
        presentation_id: str,
        emails: List[str], 
        role: str = "writer"
    ) -> None:
        """Share the presentation with specified users.
        
        Grants access to the presentation for the specified email addresses with
        the given permission level. The implementation should handle platform-specific
        sharing mechanisms and permission systems.
        
        Args:
            presentation_id: Unique identifier of the presentation to share.
            emails: List of email addresses to grant access to. Each email should
                be a valid email address format.
            role: Permission level to grant. Common values include:
                - "reader": View-only access
                - "writer": Full edit access
                - "commenter": Can view and add comments
                Platform-specific roles may vary.
                
        Raises:
            AuthenticationError: If authentication fails or is required.
            NotFoundError: If presentation_id doesn't exist.
            PermissionError: If current user lacks sharing permissions.
            InvalidEmailError: If any email address is invalid.
            SharingError: If sharing operation fails for platform-specific reasons.
            
        Example:
            >>> # Share with read-only access
            >>> provider.share_presentation(
            ...     "presentation_123",
            ...     ["viewer1@example.com", "viewer2@example.com"],
            ...     role="reader"
            ... )
            >>> 
            >>> # Share with edit access
            >>> provider.share_presentation(
            ...     "presentation_123",
            ...     ["editor@example.com"],
            ...     role="writer"
            ... )
        """
        pass
    
    @abstractmethod
    def get_presentation_url(self, presentation_id: str) -> str:
        """Get the public URL for accessing a presentation.
        
        Returns a URL that can be used to view or edit the presentation in the
        platform's web interface. The URL should be publicly accessible to users
        who have been granted appropriate permissions.
        
        Args:
            presentation_id: Unique identifier of the presentation.
            
        Returns:
            Public URL string that opens the presentation in the platform's
            web interface. Users may need appropriate permissions to access.
            
        Raises:
            AuthenticationError: If authentication fails or is required.
            NotFoundError: If presentation_id doesn't exist.
            URLError: If URL generation fails for platform-specific reasons.
            
        Example:
            >>> url = provider.get_presentation_url("presentation_123")
            >>> print(f"View presentation at: {url}")
            >>> # Example output: "https://docs.google.com/presentation/d/presentation_123"
        """
        pass
