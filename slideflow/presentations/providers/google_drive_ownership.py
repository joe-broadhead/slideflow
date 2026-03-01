"""Shared ownership-transfer helpers for Google Drive-backed providers."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple


def normalize_transfer_owner_email(value: Optional[str]) -> Optional[str]:
    """Normalize and validate an optional ownership-transfer target email."""
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1]:
        raise ValueError("transfer_ownership_to must be a valid email address")

    return normalized


def append_transfer_owner_preflight_check(
    checks: List[Tuple[str, bool, str]],
    transfer_owner: Optional[str],
) -> None:
    """Append a standardized transfer-target check when configured."""
    owner = (transfer_owner or "").strip()
    if not owner:
        return

    target_valid = "@" in owner and "." in owner.rsplit("@", 1)[-1]
    checks.append(
        (
            "ownership_transfer_target_valid",
            target_valid,
            (
                f"Ownership transfer target '{owner}' looks valid"
                if target_valid
                else "transfer_ownership_to must be a valid email address"
            ),
        )
    )


def is_shared_drive_file(
    execute_request: Callable[[Any], Dict[str, Any]],
    drive_service: Any,
    file_id: str,
) -> bool:
    """Return True when a Drive file is backed by a Shared Drive."""
    metadata = execute_request(
        drive_service.files().get(
            fileId=file_id,
            fields="id,driveId",
            supportsAllDrives=True,
        )
    )
    return bool(metadata.get("driveId"))


def transfer_drive_file_ownership(
    execute_request: Callable[[Any], Dict[str, Any]],
    drive_service: Any,
    file_id: str,
    new_owner_email: str,
) -> None:
    """Transfer ownership of a Drive file to a user."""
    permission = {
        "type": "user",
        "role": "owner",
        "emailAddress": new_owner_email,
    }
    execute_request(
        drive_service.permissions().create(
            fileId=file_id,
            body=permission,
            transferOwnership=True,
            sendNotificationEmail=True,
            supportsAllDrives=False,
        )
    )
