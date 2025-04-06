import logging
from pydantic import BaseModel, Field
from typing import List, Union, Optional, Any, Dict

from slideflow.chart.chart import Chart
from slideflow.data.data_manager import DataManager
from slideflow.replacements.text import TextReplacement
from slideflow.replacements.table import TableReplacement
from slideflow.presentation.utils import convert_dimensions, apply_alignment

logger = logging.getLogger(__name__)

class Slide(BaseModel):
    """
    Represents a Google Slide containing charts and text/table replacements.

    This model is used to define the structure and dynamic content of a slide,
    including positioning details and contextual information.

    Attributes:
        slide_id (str): Identifier for the slide within the Google Slides presentation.
        charts (List[Chart]): Charts to be added to the slide.
        replacements (List[Union[TextReplacement, TableReplacement]]): Text or table replacements on the slide.
        page_width_pt (Optional[float]): Page width in points. Used for alignment and layout.
        page_height_pt (Optional[float]): Page height in points. Used for alignment and layout.
        slides_app (Optional[dict]): Metadata from the Google Slides API used to compute relative dimensions.
        context (Optional[Dict[str, str]]): Optional contextual parameters used to parameterize content.
    """
    slide_id: str = Field(..., description = 'Identifier for the slide')
    charts: List[Chart] = Field(
        default_factory = list,
        description = 'Charts to be added to the slide'
    )
    replacements: List[Union[TextReplacement, TableReplacement]] = Field(
        default_factory = list,
        description = 'List of text and table replacements on the slide'
    )
    page_width_pt: Optional[float] = Field(
        default = None,
        description = 'Page width in points (for alignment)'
    )
    page_height_pt: Optional[float] = Field(
        default = None,
        description = 'Page height in points (for alignment)'
    )
    slides_app: Optional[dict] = Field(
        default = None,
        description = 'Optional Slides API app state used for relative positioning'
    )
    context: Optional[Dict[str, str]] = None

    def get_chart_requests(
        self,
        presentation_id: str,
        drive_service: Any,
        data_manager: DataManager
    ) -> None:
        """
        Generates chart insertion requests for a Google Slide.

        This method prepares the batchUpdate request payload for inserting all
        charts into the slide. It also collects the Drive file IDs for cleanup.

        Args:
            presentation_id (str): The ID of the Google Slides presentation.
            drive_service (Any): The authenticated Google Drive API service client.
            data_manager (DataManager): The data manager used to retrieve chart data.

        Returns:
            dict: A dictionary containing:
                - 'requests': List of chart insertion requests for batchUpdate.
                - 'ids': List of uploaded Drive file IDs (for deletion later).
        """
        requests = []
        ids = []

        for chart in self.charts:
            x, y, width, height = self._compute_chart_dimensions(chart)
            x, y = apply_alignment(x, y, width, height, chart.alignment, self.page_width_pt, self.page_height_pt)

            file_id, image_url = chart.generate_chart_image(data_manager, drive_service)
            ids.append(file_id)

            logger.info(
                f'Inserting chart {chart.object_id} on slide {self.slide_id} '
                f'in presentation {presentation_id} at ({x}, {y}) with size ({width}x{height})'
            )

            request = self._build_insert_chart_request(chart.object_id, image_url, x, y, width, height)
            requests.append(request)

        return {'requests': requests, 'ids': ids}

    def ger_replacement_requests(self, data_manager: DataManager) -> None:
        """
        Generates replacement requests for text and table placeholders.

        This method builds a list of Google Slides API `replaceAllText` requests
        based on the slide's defined replacements.

        Args:
            data_manager (DataManager): Data manager used to retrieve data
            for replacements.

        Returns:
            List[dict]: A list of replaceAllText request objects to be used
            with the Google Slides API `batchUpdate` method.
        """
        requests = []

        for replacement in self.replacements:
            if isinstance(replacement, TextReplacement):
                replacement_text = self._get_text_replacement(replacement, data_manager)
                requests.append(self._build_text_replacement_request(replacement.placeholder, replacement_text))

            elif isinstance(replacement, TableReplacement):
                replacements = self._get_table_replacements(replacement, data_manager)
                for placeholder, new_text in replacements.items():
                    requests.append(self._build_text_replacement_request(placeholder, str(new_text)))

        return requests or []

    def _compute_chart_dimensions(self, chart: Chart) -> tuple:
        """
        Computes the pixel dimensions and position for a chart.

        This method converts the chart's x, y, width, and height values into
        pixel units (points), accounting for the specified dimensions format.
        If the format is 'relative', it uses the slide's app metadata to
        compute the actual values.

        Args:
            chart (Chart): The chart whose dimensions should be calculated.

        Returns:
            tuple: A tuple of (x, y, width, height) in points.
        """
        if chart.dimensions_format == 'relative':
            return convert_dimensions(
                chart.x, chart.y, chart.width, chart.height,
                chart.dimensions_format,
                self.slides_app
            )
        return convert_dimensions(
            chart.x, chart.y, chart.width, chart.height,
            chart.dimensions_format
        )

    def _build_insert_chart_request(
        self,
        object_id: str, 
        image_url: str,
        x: float, 
        y: float, 
        width: float, 
        height: float
    ) -> dict:
        """
        Builds a Google Slides API request to insert a chart image on the slide.

        Args:
            object_id (str): The unique ID for the image element on the slide.
            image_url (str): A publicly accessible URL of the chart image.
            x (float): The X coordinate (in points) for the image position.
            y (float): The Y coordinate (in points) for the image position.
            width (float): The width of the image (in points).
            height (float): The height of the image (in points).

        Returns:
            dict: A request payload for the `batchUpdate` call to create an image.
        """
        return {
            'createImage': {
                'objectId': object_id,
                'url': image_url,
                'elementProperties': {
                    'pageObjectId': self.slide_id,
                    'size': {
                        'height': {'magnitude': height, 'unit': 'PT'},
                        'width': {'magnitude': width, 'unit': 'PT'},
                    },
                    'transform': {
                        'translateX': x,
                        'translateY': y,
                        'scaleX': 1,
                        'scaleY': 1,
                        'unit': 'PT'
                    }
                }
            }
        }

    def _build_text_replacement_request(self, placeholder: str, replacement_text: str) -> dict:
        """
        Builds a Google Slides API request to replace text on a specific slide.

        Args:
            placeholder (str): The placeholder text to search for (e.g., "{{STORE_CODE}}").
            replacement_text (str): The text that will replace the placeholder.

        Returns:
            dict: A request payload for the `batchUpdate` call to perform the text replacement.
        """
        return {
            'replaceAllText': {
                'containsText': {'text': placeholder, 'matchCase': True},
                'replaceText': replacement_text,
                'pageObjectIds': [self.slide_id]
            }
        }

    def _get_text_replacement(self, replacement: TextReplacement, data_manager: DataManager) -> str:
        """
        Resolves the final text to replace a placeholder using static or computed logic.

        If a data source is defined, it is loaded and passed to the value function or static replacement.
        Otherwise, the replacement is resolved without data.

        Args:
            replacement (TextReplacement): The text replacement configuration.
            data_manager (DataManager): The data manager used to load any required data sources.

        Returns:
            str: The computed or static text replacement value.
        """
        if replacement.data_source:
            data = data_manager.get_data(replacement.data_source)
            return replacement.get_replacement(data)
        return replacement.get_replacement()

    def _get_table_replacements(self, replacement: TableReplacement, data_manager: DataManager) -> dict:
        """
        Generates placeholder-to-text mappings for table replacements.

        If a data source is defined, it is used to generate replacements using a transformation
        function or default formatting. Otherwise, static replacements defined in the config
        are returned directly.

        Args:
            replacement (TableReplacement): The table replacement configuration.
            data_manager (DataManager): The data manager used to load the data source if specified.

        Returns:
            dict: A dictionary mapping placeholder keys to replacement values.
        """
        if replacement.data_source:
            data = data_manager.get_data(replacement.data_source)
            return replacement.get_table_replacements(data)
        return replacement.replacements
