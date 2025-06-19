from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Any, Tuple, Callable, Annotated

from slideflow.presentation.user import User
from slideflow.presentation.slide import Slide
from slideflow.data.data_manager import DataManager


class Presentation(BaseModel):
    """
    Represents a Google Slides presentation composed of one or more slides,
    optionally shared with users and generated from a template.

    Attributes:
        name (str): The title of the presentation. Can include format placeholders (e.g., "{store_code}").
        name_fn (Callable[..., str], optional): A function that modifies or computes the final name based on parameters.
        template_id (str): The ID of the Google Slides template to copy from.
        presentation_id (str, optional): The ID of the newly created Google Slides presentation. Set after the template is copied.
        slides (List[Slide]): A list of slide definitions to render into the presentation.
        users (List[User]): A list of users with access to the presentation, including permission levels.

        slides_service (Any, optional): An authenticated Google Slides API service instance (runtime-only).
        drive_service (Any, optional): An authenticated Google Drive API service instance (runtime-only).
    """

    name: Annotated[str, Field(description = 'The name for the presentation')]
    name_fn: Annotated[Optional[Callable[..., str]], Field(default = lambda name: name, description = 'Function to compute the presentation name')]
    template_id: Annotated[str, Field(description = 'Google Slides template presentation ID')]
    presentation_id: Annotated[Optional[str], Field(default = None, description = 'Google Slides presentation ID (set after copying the template)')]
    slides: Annotated[List[Slide], Field(default_factory = list, description = 'List of slides in the presentation')]
    users: Annotated[List[User], Field(default_factory = list, description = 'Users with access to the presentation')]

    # Runtime-only fields (excluded from serialization)
    slides_service: Annotated[Optional[Any], Field(default = None, exclude = True, description = 'Service used to interact with Slides API')]
    drive_service: Annotated[Optional[Any], Field(default = None, exclude = True, description = 'Service used to interact with Drive API')]

    model_config = {
        'arbitrary_types_allowed': True
    }

    @model_validator(mode = 'after')
    def add_meta_fields_to_slides(self) -> "Presentation":
        """
        Adds metadata to each slide after the model is validated.

        This method populates each slide with:
        - `page_width_pt`: The width of the presentation page in points.
        - `page_height_pt`: The height of the presentation page in points.
        - `slides_app`: The full Google Slides API app state of the presentation.

        Returns:
            Presentation: The updated presentation instance with enriched slide metadata.
        
        Notes:
            This method only runs if `presentation_id` is set, meaning the presentation
            has already been created or copied from a template.
        """
        if not self.presentation_id:
            return self

        slides_app = self.get_presentation()
        page_width_pt, page_height_pt = self.get_page_dimensions()
        for slide in self.slides:
            slide.page_width_pt = page_width_pt
            slide.page_height_pt = page_height_pt
            slide.slides_app = slides_app
        return self

    def copy_presentation(self) -> dict:
        """
        Copies the template presentation using the Drive API and updates the presentation ID.

        This method uses the `template_id` to create a new presentation file in Google Drive,
        setting its name using `name_fn(self.name)`. The resulting presentation ID is stored
        in `self.presentation_id` for future operations.

        Returns:
            dict: The metadata of the newly copied presentation, as returned by the Drive API.
        """
        copied = self.drive_service.files().copy(
            fileId = self.template_id,
            body = {'name': self.name_fn(self.name)}
        ).execute()
        self.presentation_id = copied.get('id')
        return copied

    def get_presentation(self) -> dict:
        """
        Retrieves the full metadata of the current presentation from the Slides API.

        This includes information such as slide dimensions, layout, and all slide objects.
        The method requires that `self.presentation_id` is already set, either by copying
        a template or assigning an existing presentation ID.

        Raises:
            ValueError: If `presentation_id` is not set.

        Returns:
            dict: The full presentation metadata as returned by the Slides API.
        """
        if not self.presentation_id:
            raise ValueError('Presentation ID is not set. Copy a template first or set an existing presentation_id.')
        return self.slides_service.presentations().get(
            presentationId = self.presentation_id
        ).execute()

    def share_presentation(self) -> None:
        """
        Shares the presentation with all specified users via the Google Drive API.

        For each user listed in `self.users`, this method creates a permission on
        the presentation file with the user's email and assigned role. It does not
        send notification emails.

        Raises:
            googleapiclient.errors.HttpError: If the Drive API call fails.
        """
        for user in self.users:
            self.drive_service.permissions().create(
                fileId = self.presentation_id,
                body = {
                    'type': 'user',
                    'role': user.role,
                    'emailAddress': user.email
                },
                sendNotificationEmail = False
            ).execute()

    def get_page_dimensions(self) -> Tuple[float, float]:
        """
        Extracts the page width and height (in points) from the presentation metadata.

        This method retrieves the presentation metadata using the Slides API and converts
        the slide dimensions to points. If the units are in EMUs, they are converted using
        the factor (1 pt = 12700 EMUs).

        Returns:
            Tuple[float, float]: A tuple containing the page width and height in points.

        Raises:
            ValueError: If the presentation ID is not set.
            googleapiclient.errors.HttpError: If the Slides API call fails.
        """
        slides_app = self.get_presentation()

        def convert_dimension(dim_info: dict) -> float:
            return dim_info['magnitude'] / 12700 if dim_info['unit'] == 'EMU' else dim_info['magnitude']

        width = convert_dimension(slides_app['pageSize']['width'])
        height = convert_dimension(slides_app['pageSize']['height'])

        return width, height

    def process_slides(
        self,
        slides_service: Any,
        drive_service: Any,
        data_manager: DataManager = DataManager()
    ) -> None:
        """
        Applies chart insertions and content replacements to each slide in the presentation.

        This method collects all requests for inserting charts and performing text or table
        replacements from each slide. It then submits the requests in a single batch to the
        Slides API. After processing the slides, any temporary image files created in Google
        Drive for the charts are deleted.

        Args:
            slides_service (Any): The Google Slides API service client.
            drive_service (Any): The Google Drive API service client.
            data_manager (DataManager): Optional. The data manager used to retrieve data sources 
                for charts and replacements. Defaults to a new `DataManager()` instance.

        Raises:
            googleapiclient.errors.HttpError: If the batch update or Drive file deletion fails.
        """
        charts = []
        file_ids = []
        replacements = []

        for slide in self.slides:
            chart_requests = slide.get_chart_requests(self.presentation_id, drive_service, data_manager)
            charts.extend(chart_requests.get('requests', []))
            file_ids.extend(chart_requests.get('ids', []))

            replacement_requests = slide.get_replacement_requests(data_manager)
            replacements.extend(replacement_requests)

        slides_service.presentations().batchUpdate(
            presentationId = self.presentation_id,
            body = {'requests': [*charts, *replacements]}
        ).execute()

        for id in file_ids:
            drive_service.files().delete(fileId = id).execute()
