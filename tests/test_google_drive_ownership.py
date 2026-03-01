from __future__ import annotations

from typing import Any, Dict, List

import pytest

from slideflow.presentations.providers.google_drive_ownership import (
    append_transfer_owner_preflight_check,
    is_shared_drive_file,
    normalize_transfer_owner_email,
    transfer_drive_file_ownership,
)


def test_normalize_transfer_owner_email_handles_missing_values():
    assert normalize_transfer_owner_email(None) is None
    assert normalize_transfer_owner_email("") is None
    assert normalize_transfer_owner_email("   ") is None


def test_normalize_transfer_owner_email_trims_valid_email():
    assert normalize_transfer_owner_email(" owner@example.com ") == "owner@example.com"


@pytest.mark.parametrize("value", ["ownerexample.com", "owner@", "owner@localhost"])
def test_normalize_transfer_owner_email_rejects_invalid_email(value: str):
    with pytest.raises(ValueError, match="transfer_ownership_to"):
        normalize_transfer_owner_email(value)


def test_append_transfer_owner_preflight_check_skips_empty_value():
    checks = [("existing", True, "ok")]
    append_transfer_owner_preflight_check(checks, None)
    append_transfer_owner_preflight_check(checks, "  ")
    assert checks == [("existing", True, "ok")]


def test_append_transfer_owner_preflight_check_appends_valid_and_invalid():
    checks: List[tuple[str, bool, str]] = []
    append_transfer_owner_preflight_check(checks, "owner@example.com")
    append_transfer_owner_preflight_check(checks, "not-an-email")

    assert checks[0] == (
        "ownership_transfer_target_valid",
        True,
        "Ownership transfer target 'owner@example.com' looks valid",
    )
    assert checks[1] == (
        "ownership_transfer_target_valid",
        False,
        "transfer_ownership_to must be a valid email address",
    )


class _FilesApi:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


class _PermissionsApi:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


class _DriveService:
    def __init__(self):
        self.files_api = _FilesApi()
        self.permissions_api = _PermissionsApi()

    def files(self):
        return self.files_api

    def permissions(self):
        return self.permissions_api


def test_is_shared_drive_file_detects_shared_drive():
    service = _DriveService()
    captured_requests: List[Dict[str, Any]] = []

    def _execute_request(request):
        captured_requests.append(request)
        return {"id": "file-1", "driveId": "drive-123"}

    assert is_shared_drive_file(_execute_request, service, "file-1") is True
    assert captured_requests[0]["fileId"] == "file-1"
    assert captured_requests[0]["fields"] == "id,driveId"
    assert captured_requests[0]["supportsAllDrives"] is True


def test_is_shared_drive_file_detects_non_shared_drive():
    service = _DriveService()

    def _execute_request(_request):
        return {"id": "file-2"}

    assert is_shared_drive_file(_execute_request, service, "file-2") is False


def test_transfer_drive_file_ownership_builds_expected_drive_permission_request():
    service = _DriveService()
    captured_requests: List[Dict[str, Any]] = []

    def _execute_request(request):
        captured_requests.append(request)
        return {"id": "permission-1"}

    transfer_drive_file_ownership(
        _execute_request,
        service,
        file_id="file-3",
        new_owner_email="owner@example.com",
    )

    assert len(captured_requests) == 1
    request_payload = captured_requests[0]
    assert request_payload["fileId"] == "file-3"
    assert request_payload["transferOwnership"] is True
    assert request_payload["sendNotificationEmail"] is True
    assert request_payload["supportsAllDrives"] is False
    assert request_payload["body"] == {
        "type": "user",
        "role": "owner",
        "emailAddress": "owner@example.com",
    }
