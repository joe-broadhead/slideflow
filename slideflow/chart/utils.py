from PIL import Image
from io import BytesIO
from typing import Any, Tuple
from googleapiclient.http import MediaIoBaseUpload

def generate_figure_image(fig: Any, width: float, height: float) -> BytesIO:
    """
    Generates a compressed PNG image from a Plotly figure object.

    The function scales the figure size to pixels, renders it to a PNG image buffer,
    compresses it using Pillow for reduced size, and returns a BytesIO stream of the result.

    Args:
        fig (Any): A Plotly figure object.
        width (float): Desired width of the image in points.
        height (float): Desired height of the image in points.

    Returns:
        BytesIO: A buffer containing the compressed PNG image data.
    """
    CONVERSION_FACTOR = 1.33
    px_width = int(width * CONVERSION_FACTOR)
    px_height = int(height * CONVERSION_FACTOR)
    
    buf = BytesIO()
    fig.write_image(buf, format = 'png', width = px_width, height = px_height, scale = 2)
    buf.seek(0)
    
    image = Image.open(buf)
    compressed_buf = BytesIO()
    image.save(compressed_buf, format = 'PNG', optimize = True)
    compressed_buf.seek(0)
    
    return compressed_buf

def upload_image_to_drive(drive_service, image_buf, name: str = 'chart.png') -> Tuple[str, str]:
    """
    Uploads an image buffer to Google Drive and sets it to be publicly accessible.

    The uploaded file will have the specified name and be assigned a public 'reader' permission.
    Returns the file ID and a shareable public URL.

    Args:
        drive_service: An authenticated Google Drive API service instance.
        image_buf (BytesIO): A buffer containing image data (e.g., PNG).
        name (str, optional): The name of the file in Drive. Defaults to 'chart.png'.

    Returns:
        Tuple[str, str]: A tuple containing the file ID and the public URL to access the image.
    """
    media = MediaIoBaseUpload(image_buf, mimetype = 'image/png')
    file_metadata = {'name': name, 'mimeType': 'image/png'}
    uploaded_file = drive_service.files().create(
        body = file_metadata,
        media_body = media,
        fields = 'id'
    ).execute()

    file_id = uploaded_file['id']
    drive_service.permissions().create(
        fileId = file_id,
        body = {'type': 'anyone', 'role': 'reader'}
    ).execute()

    public_url = f'https://drive.google.com/uc?id={file_id}'
    return file_id, public_url
