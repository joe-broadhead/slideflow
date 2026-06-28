"""Shared Google Drive permission helpers."""

from __future__ import annotations

from slideflow.constants import GoogleSlides

ALLOWED_GOOGLE_SHARE_ROLES = (
    GoogleSlides.PERMISSION_READER,
    GoogleSlides.PERMISSION_WRITER,
    GoogleSlides.PERMISSION_COMMENTER,
)


def normalize_google_share_role(value: str) -> str:
    """Normalize and validate a Google Drive share role."""
    role = value.strip().lower() if isinstance(value, str) else ""
    if role not in ALLOWED_GOOGLE_SHARE_ROLES:
        allowed = ", ".join(ALLOWED_GOOGLE_SHARE_ROLES)
        raise ValueError(f"share_role must be one of: {allowed}")
    return role
