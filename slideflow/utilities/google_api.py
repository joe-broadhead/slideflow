"""Shared Google API utility helpers for providers."""

from __future__ import annotations

import io
import time
from typing import Any, Callable, Dict, Optional, Tuple, Type

from google.oauth2.service_account import Credentials
from googleapiclient.http import HttpRequest, MediaIoBaseUpload

from slideflow.constants import Defaults
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


def apply_user_agent_header(
    headers: Optional[Dict[str, Any]],
    user_agent: str = Defaults.CLIENT_USER_AGENT,
) -> Dict[str, Any]:
    """Return headers with a Slideflow user-agent token added/preserved.

    If a User-Agent already exists and does not include Slideflow, append
    Slideflow to preserve upstream caller metadata.
    """
    merged: Dict[str, Any] = dict(headers or {})
    user_agent_key = next(
        (key for key in merged.keys() if key.lower() == "user-agent"), None
    )
    if user_agent_key is None:
        merged["User-Agent"] = user_agent
        return merged

    existing = str(merged.get(user_agent_key, "")).strip()
    if user_agent.lower() not in existing.lower():
        merged[user_agent_key] = (
            f"{existing} {user_agent}".strip() if existing else user_agent
        )
    return merged


def slideflow_google_request_builder(
    http: Any, *args: Any, **kwargs: Any
) -> HttpRequest:
    """Build Google API requests with Slideflow User-Agent tagging."""
    kwargs["headers"] = apply_user_agent_header(kwargs.get("headers"))
    return HttpRequest(http, *args, **kwargs)


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
