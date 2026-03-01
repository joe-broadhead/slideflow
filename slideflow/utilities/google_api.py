"""Shared Google API utility helpers for providers."""

from __future__ import annotations

import io
import time
from typing import Any, Callable, Dict, Optional, Tuple, Type

from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaIoBaseUpload

from slideflow.utilities.exceptions import AuthenticationError
from slideflow.utilities.rate_limiter import RateLimiter


def build_service_account_credentials(
    loaded_credentials: Dict[str, Any],
    scopes: list[str],
    credentials_cls: Type[Credentials] = Credentials,
) -> Credentials:
    """Construct Google service-account credentials with consistent errors."""
    try:
        return credentials_cls.from_service_account_info(
            loaded_credentials, scopes=scopes
        )
    except Exception as error_msg:
        raise AuthenticationError(
            f"Credentials authentication failed: {error_msg}"
        ) from error_msg


def execute_rate_limited_request(
    request: Any, rate_limiter: RateLimiter, num_retries: int = 3
) -> Any:
    """Execute a Google API request through a shared rate-limited wrapper."""
    rate_limiter.wait()
    return request.execute(num_retries=num_retries)


def upload_png_to_drive(
    *,
    drive_service: Any,
    execute_request: Callable[[Any], Any],
    image_bytes: bytes,
    filename: str,
    destination_folder_id: Optional[str],
    sharing_mode: str,
    permission_delay_seconds: float,
    resumable: bool,
    on_restricted_file: Optional[Callable[[str], None]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Tuple[str, str]:
    """Upload PNG bytes to Drive and return (public_url, file_id)."""
    file_metadata: Dict[str, Any] = {"name": filename}
    if destination_folder_id:
        file_metadata["parents"] = [destination_folder_id]

    media = MediaIoBaseUpload(
        io.BytesIO(image_bytes),
        mimetype="image/png",
        resumable=resumable,
    )

    uploaded_file = execute_request(
        drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
    )
    file_id = uploaded_file.get("id")

    if sharing_mode == "public":
        execute_request(
            drive_service.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True,
            )
        )
        if permission_delay_seconds > 0:
            sleep_fn(permission_delay_seconds)
    elif on_restricted_file is not None:
        on_restricted_file(file_id)

    return f"https://drive.google.com/uc?id={file_id}", file_id
