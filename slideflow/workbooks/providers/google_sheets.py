"""Google Sheets workbook provider implementation."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import Field

from slideflow.constants import Environment, GoogleSlides
from slideflow.utilities.auth import handle_google_credentials
from slideflow.utilities.exceptions import RenderingError
from slideflow.utilities.google_api import (
    build_service_account_credentials,
    execute_rate_limited_request,
)
from slideflow.utilities.logging import get_logger
from slideflow.utilities.rate_limiter import RateLimiter
from slideflow.workbooks.config import RESERVED_METADATA_TAB
from slideflow.workbooks.providers.base import WorkbookProvider, WorkbookProviderConfig

logger = get_logger(__name__)
_sheets_rate_limiters: Dict[float, RateLimiter] = {}
_rate_limiter_lock = threading.Lock()


def _get_rate_limiter(rps: float) -> RateLimiter:
    """Get or create a shared Google Sheets API rate limiter for a target rate."""
    global _sheets_rate_limiters
    rps_key = round(float(rps), 6)
    with _rate_limiter_lock:
        if rps_key not in _sheets_rate_limiters:
            _sheets_rate_limiters[rps_key] = RateLimiter(rps_key)
        return _sheets_rate_limiters[rps_key]


class GoogleSheetsProviderConfig(WorkbookProviderConfig):
    """Configuration model for Google Sheets workbook provider."""

    provider_type: Literal["google_sheets"] = "google_sheets"
    credentials: Optional[str] = Field(
        None,
        description="Google credentials as a file path or JSON string.",
    )
    spreadsheet_id: Optional[str] = Field(
        None,
        description="Existing spreadsheet id to reuse instead of creating one.",
    )
    drive_folder_id: Optional[str] = Field(
        None,
        description="Optional Drive folder id where created spreadsheets should be moved.",
    )
    share_with: List[str] = Field(
        default_factory=list,
        description="Email addresses to share workbook with after build.",
    )
    share_role: str = Field(
        GoogleSlides.PERMISSION_READER,
        description="Permission role: reader, writer, or commenter.",
    )
    requests_per_second: float = Field(
        1.0,
        gt=0,
        description="Maximum Google API requests per second.",
    )


class GoogleSheetsProvider(WorkbookProvider):
    """Google Sheets provider for workbook builds."""

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
    ]
    _METADATA_HEADERS = ["tab_name", "run_key", "rows_written", "recorded_at"]

    def __init__(self, config: GoogleSheetsProviderConfig):
        super().__init__(config)
        self.config: GoogleSheetsProviderConfig = config

        loaded_credentials = handle_google_credentials(
            config.credentials,
            env_var_names=[
                Environment.GOOGLE_SHEETS_CREDENTIALS,
                Environment.GOOGLE_SLIDEFLOW_CREDENTIALS,
            ],
        )

        credentials = build_service_account_credentials(
            loaded_credentials, self.SCOPES, credentials_cls=Credentials
        )

        self._credentials = credentials
        self._thread_local_services = threading.local()

        # Preserve existing attributes for compatibility and preflight checks.
        self.sheets_service = build("sheets", "v4", credentials=credentials)
        self.drive_service = build("drive", "v3", credentials=credentials)
        self._thread_local_services.sheets_service = self.sheets_service
        self._thread_local_services.drive_service = self.drive_service
        self.rate_limiter = _get_rate_limiter(self.config.requests_per_second)
        self._run_key_cache: Dict[str, Set[Tuple[str, str]]] = {}
        self._workbook_locks: Dict[str, threading.RLock] = {}
        self._workbook_locks_guard = threading.Lock()

    def _execute_request(self, request):
        """Execute Google API request with shared rate limiting."""
        return execute_rate_limited_request(request, self.rate_limiter, num_retries=3)

    def _workbook_lock(self, workbook_id: str) -> threading.RLock:
        """Return a per-workbook lock for append/idempotency critical sections."""
        # Keep compatibility with tests that bypass __init__ via object.__new__.
        if not hasattr(self, "_workbook_locks"):
            self._workbook_locks = {}
        if not hasattr(self, "_workbook_locks_guard"):
            self._workbook_locks_guard = threading.Lock()

        with self._workbook_locks_guard:
            if workbook_id not in self._workbook_locks:
                self._workbook_locks[workbook_id] = threading.RLock()
            return self._workbook_locks[workbook_id]

    def _sheets_api(self):
        """Return a thread-local Sheets client, falling back to legacy attributes."""
        if not hasattr(self, "_thread_local_services") or not hasattr(
            self, "_credentials"
        ):
            sheets_service = getattr(self, "sheets_service", None)
            if sheets_service is None:
                raise RenderingError("Google Sheets API client is not initialized")
            return sheets_service

        sheets_service = getattr(self._thread_local_services, "sheets_service", None)
        if sheets_service is None:
            sheets_service = build("sheets", "v4", credentials=self._credentials)
            self._thread_local_services.sheets_service = sheets_service
        return sheets_service

    def _drive_api(self):
        """Return a thread-local Drive client, falling back to legacy attributes."""
        if not hasattr(self, "_thread_local_services") or not hasattr(
            self, "_credentials"
        ):
            drive_service = getattr(self, "drive_service", None)
            if drive_service is None:
                raise RenderingError("Google Drive API client is not initialized")
            return drive_service

        drive_service = getattr(self._thread_local_services, "drive_service", None)
        if drive_service is None:
            drive_service = build("drive", "v3", credentials=self._credentials)
            self._thread_local_services.drive_service = drive_service
        return drive_service

    def _base_preflight_checks(self) -> List[Tuple[str, bool, str]]:
        """Return credential/service/rate-limiter baseline preflight checks."""
        sheets_service = getattr(self, "sheets_service", None)
        drive_service = getattr(self, "drive_service", None)
        rate_limiter = getattr(self, "rate_limiter", None)
        has_credentials = bool(self.config.credentials) or bool(
            os.getenv(Environment.GOOGLE_SHEETS_CREDENTIALS)
            or os.getenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS)
        )
        return [
            (
                "google_sheets_credentials_present",
                has_credentials,
                (
                    "Credentials found in config or supported environment variables"
                    if has_credentials
                    else "Missing credentials in config and environment"
                ),
            ),
            (
                "sheets_service_initialized",
                sheets_service is not None,
                (
                    "Google Sheets API client initialized"
                    if sheets_service is not None
                    else "Google Sheets API client is not initialized"
                ),
            ),
            (
                "drive_service_initialized",
                drive_service is not None,
                (
                    "Google Drive API client initialized"
                    if drive_service is not None
                    else "Google Drive API client is not initialized"
                ),
            ),
            (
                "rate_limiter_initialized",
                rate_limiter is not None,
                (
                    f"Rate limiter configured at {self.config.requests_per_second} rps"
                    if rate_limiter is not None
                    else "Rate limiter is not initialized"
                ),
            ),
        ]

    def _spreadsheet_access_check(self) -> Tuple[str, bool, str]:
        """Verify that configured spreadsheet_id is readable."""
        try:
            sheets_api = self._sheets_api()
            response = self._execute_request(
                sheets_api.spreadsheets().get(
                    spreadsheetId=self.config.spreadsheet_id,
                    fields="spreadsheetId,properties/title",
                )
            )
            sheet_id = (
                response.get("spreadsheetId")
                if isinstance(response, dict)
                else self.config.spreadsheet_id
            )
            return (
                "spreadsheet_access",
                True,
                f"Accessible spreadsheet_id '{sheet_id}'",
            )
        except Exception as error:
            return (
                "spreadsheet_access",
                False,
                f"Cannot access spreadsheet_id '{self.config.spreadsheet_id}': {error}",
            )

    def _spreadsheet_write_access_check(self) -> Tuple[str, bool, str]:
        """Verify that configured spreadsheet_id is writable via Drive."""
        try:
            drive_api = self._drive_api()
            write_response = self._execute_request(
                drive_api.files().get(
                    fileId=self.config.spreadsheet_id,
                    fields="id,trashed,capabilities(canEdit)",
                    supportsAllDrives=True,
                )
            )
            capabilities = (
                write_response.get("capabilities", {})
                if isinstance(write_response, dict)
                else {}
            )
            can_edit = bool(
                isinstance(capabilities, dict) and capabilities.get("canEdit", False)
            )
            is_trashed = (
                bool(write_response.get("trashed"))
                if isinstance(write_response, dict)
                else False
            )
            return (
                "spreadsheet_write_access",
                can_edit and not is_trashed,
                (
                    f"Spreadsheet '{self.config.spreadsheet_id}' is writable"
                    if can_edit and not is_trashed
                    else (
                        f"Spreadsheet '{self.config.spreadsheet_id}' is not writable "
                        "(missing canEdit capability or file is trashed)"
                    )
                ),
            )
        except Exception as error:
            return (
                "spreadsheet_write_access",
                False,
                f"Cannot verify write access for spreadsheet_id '{self.config.spreadsheet_id}': {error}",
            )

    def _drive_folder_access_checks(self) -> List[Tuple[str, bool, str]]:
        """Verify that configured drive_folder_id exists and is writable."""
        try:
            drive_api = self._drive_api()
            response = self._execute_request(
                drive_api.files().get(
                    fileId=self.config.drive_folder_id,
                    fields="id,mimeType,name,trashed,capabilities(canAddChildren,canEdit)",
                    supportsAllDrives=True,
                )
            )
            mime_type = response.get("mimeType") if isinstance(response, dict) else ""
            is_folder = mime_type == "application/vnd.google-apps.folder"
            is_trashed = (
                bool(response.get("trashed")) if isinstance(response, dict) else False
            )
            access_check = (
                "drive_folder_access",
                is_folder and not is_trashed,
                (
                    f"Accessible Drive folder '{self.config.drive_folder_id}'"
                    if is_folder and not is_trashed
                    else f"Configured drive_folder_id '{self.config.drive_folder_id}' is not an active folder"
                ),
            )

            capabilities = (
                response.get("capabilities", {}) if isinstance(response, dict) else {}
            )
            can_write_folder = bool(
                isinstance(capabilities, dict)
                and (
                    capabilities.get("canAddChildren", False)
                    or capabilities.get("canEdit", False)
                )
            )
            write_check = (
                "drive_folder_write_access",
                is_folder and not is_trashed and can_write_folder,
                (
                    f"Drive folder '{self.config.drive_folder_id}' is writable"
                    if is_folder and not is_trashed and can_write_folder
                    else (
                        f"Drive folder '{self.config.drive_folder_id}' is not writable "
                        "(missing canAddChildren/canEdit capability, or folder invalid)"
                    )
                ),
            )
            return [access_check, write_check]
        except Exception as error:
            return [
                (
                    "drive_folder_access",
                    False,
                    f"Cannot access drive_folder_id '{self.config.drive_folder_id}': {error}",
                ),
                (
                    "drive_folder_write_access",
                    False,
                    f"Cannot verify write access for drive_folder_id '{self.config.drive_folder_id}': {error}",
                ),
            ]

    def run_preflight_checks(self) -> List[Tuple[str, bool, str]]:
        checks = self._base_preflight_checks()
        if (
            getattr(self, "sheets_service", None) is not None
            and self.config.spreadsheet_id
        ):
            checks.append(self._spreadsheet_access_check())
        if (
            getattr(self, "drive_service", None) is not None
            and self.config.spreadsheet_id
        ):
            checks.append(self._spreadsheet_write_access_check())
        if (
            getattr(self, "drive_service", None) is not None
            and self.config.drive_folder_id
        ):
            checks.extend(self._drive_folder_access_checks())
        return checks

    def create_or_open_workbook(self, title: str) -> str:
        if self.config.spreadsheet_id:
            return self.config.spreadsheet_id

        spreadsheet_id = ""
        created_via_sheets_api = False
        sheets_api = self._sheets_api()
        try:
            response = self._execute_request(
                sheets_api.spreadsheets().create(
                    body={"properties": {"title": title}},
                    fields="spreadsheetId",
                )
            )
            spreadsheet_id = str(response.get("spreadsheetId", "")).strip()
            created_via_sheets_api = True
        except HttpError as error:
            # Some org/shared-drive setups can deny spreadsheets.create while
            # still allowing Drive file creation in the target folder.
            if self.config.drive_folder_id:
                logger.warning(
                    "spreadsheets.create failed (%s). Falling back to Drive file creation in folder '%s'.",
                    error,
                    self.config.drive_folder_id,
                )
                spreadsheet_id = self._create_sheet_in_folder_via_drive(
                    title=title,
                    folder_id=self.config.drive_folder_id,
                )
            else:
                raise RenderingError(f"Failed to create Google Sheet: {error}")

        if not spreadsheet_id:
            raise RenderingError("Failed to create Google Sheet: missing spreadsheetId")

        if created_via_sheets_api and self.config.drive_folder_id:
            self._move_file_to_folder(spreadsheet_id, self.config.drive_folder_id)

        return spreadsheet_id

    def _create_sheet_in_folder_via_drive(self, title: str, folder_id: str) -> str:
        drive_api = self._drive_api()
        response = self._execute_request(
            drive_api.files().create(
                body={
                    "name": title,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                    "parents": [folder_id],
                },
                fields="id",
                supportsAllDrives=True,
            )
        )
        spreadsheet_id = str(response.get("id", "")).strip()
        if not spreadsheet_id:
            raise RenderingError(
                "Failed to create Google Sheet via Drive API: missing file id"
            )
        return spreadsheet_id

    def _move_file_to_folder(self, file_id: str, folder_id: str) -> None:
        drive_api = self._drive_api()
        metadata = self._execute_request(
            drive_api.files().get(
                fileId=file_id,
                fields="parents",
                supportsAllDrives=True,
            )
        )
        parents = metadata.get("parents", []) if isinstance(metadata, dict) else []
        request_kwargs: Dict[str, Any] = {
            "fileId": file_id,
            "addParents": folder_id,
            "fields": "id,parents",
            "supportsAllDrives": True,
        }
        if parents:
            request_kwargs["removeParents"] = ",".join(parents)
        self._execute_request(drive_api.files().update(**request_kwargs))

    def _sheet_range(self, tab_name: str, range_part: str) -> str:
        escaped_tab_name = tab_name.replace("'", "''")
        return f"'{escaped_tab_name}'!{range_part}"

    def _fetch_sheet_titles(self, workbook_id: str) -> Dict[str, int]:
        sheets_api = self._sheets_api()
        response = self._execute_request(
            sheets_api.spreadsheets().get(
                spreadsheetId=workbook_id,
                fields="sheets(properties(sheetId,title))",
            )
        )
        titles: Dict[str, int] = {}
        for sheet in response.get("sheets", []) if isinstance(response, dict) else []:
            if not isinstance(sheet, dict):
                continue
            properties = sheet.get("properties", {})
            if not isinstance(properties, dict):
                continue
            title = properties.get("title")
            sheet_id = properties.get("sheetId")
            if isinstance(title, str) and isinstance(sheet_id, int):
                titles[title] = sheet_id
        return titles

    def _ensure_sheet_exists(self, workbook_id: str, tab_name: str) -> None:
        titles = self._fetch_sheet_titles(workbook_id)
        if tab_name in titles:
            return
        sheets_api = self._sheets_api()
        self._execute_request(
            sheets_api.spreadsheets().batchUpdate(
                spreadsheetId=workbook_id,
                body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
            )
        )

    def _ensure_metadata_tab(self, workbook_id: str) -> None:
        titles = self._fetch_sheet_titles(workbook_id)
        sheets_api = self._sheets_api()
        if RESERVED_METADATA_TAB not in titles:
            self._execute_request(
                sheets_api.spreadsheets().batchUpdate(
                    spreadsheetId=workbook_id,
                    body={
                        "requests": [
                            {
                                "addSheet": {
                                    "properties": {"title": RESERVED_METADATA_TAB}
                                }
                            }
                        ]
                    },
                )
            )

        header_range = self._sheet_range(RESERVED_METADATA_TAB, "A1:D1")
        self._execute_request(
            sheets_api.spreadsheets()
            .values()
            .update(
                spreadsheetId=workbook_id,
                range=header_range,
                valueInputOption="RAW",
                body={"values": [self._METADATA_HEADERS]},
            )
        )

    def _load_run_key_cache(self, workbook_id: str) -> Set[Tuple[str, str]]:
        if workbook_id in self._run_key_cache:
            return self._run_key_cache[workbook_id]

        self._ensure_metadata_tab(workbook_id)
        sheets_api = self._sheets_api()
        metadata_range = self._sheet_range(RESERVED_METADATA_TAB, "A2:B")
        response = self._execute_request(
            sheets_api.spreadsheets()
            .values()
            .get(
                spreadsheetId=workbook_id,
                range=metadata_range,
            )
        )
        values = response.get("values", []) if isinstance(response, dict) else []
        keys: Set[Tuple[str, str]] = set()
        for row in values:
            if not isinstance(row, list) or len(row) < 2:
                continue
            tab_name, run_key = row[0], row[1]
            if isinstance(tab_name, str) and isinstance(run_key, str):
                keys.add((tab_name, run_key))
        self._run_key_cache[workbook_id] = keys
        return keys

    def _record_run_key(
        self,
        workbook_id: str,
        tab_name: str,
        run_key: str,
        rows_written: int,
    ) -> None:
        metadata_range = self._sheet_range(RESERVED_METADATA_TAB, "A1")
        recorded_at = datetime.now(timezone.utc).isoformat()
        sheets_api = self._sheets_api()
        self._execute_request(
            sheets_api.spreadsheets()
            .values()
            .append(
                spreadsheetId=workbook_id,
                range=metadata_range,
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={
                    "values": [[tab_name, run_key, str(rows_written), recorded_at]],
                },
            )
        )
        self._run_key_cache.setdefault(workbook_id, set()).add((tab_name, run_key))

    def _remove_run_key_record(
        self, workbook_id: str, tab_name: str, run_key: str
    ) -> None:
        metadata_range = self._sheet_range(RESERVED_METADATA_TAB, "A2:B")
        sheets_api = self._sheets_api()
        response = self._execute_request(
            sheets_api.spreadsheets()
            .values()
            .get(
                spreadsheetId=workbook_id,
                range=metadata_range,
            )
        )
        values = response.get("values", []) if isinstance(response, dict) else []
        matched_row_numbers: List[int] = []
        for index, row in enumerate(values, start=2):
            if not isinstance(row, list) or len(row) < 2:
                continue
            if row[0] == tab_name and row[1] == run_key:
                matched_row_numbers.append(index)

        for row_number in matched_row_numbers:
            row_range = self._sheet_range(
                RESERVED_METADATA_TAB, f"A{row_number}:D{row_number}"
            )
            self._execute_request(
                sheets_api.spreadsheets()
                .values()
                .clear(
                    spreadsheetId=workbook_id,
                    range=row_range,
                    body={},
                )
            )

    def write_replace_rows(
        self,
        workbook_id: str,
        tab_name: str,
        start_cell: str,
        rows: List[List[Any]],
    ) -> int:
        self._ensure_sheet_exists(workbook_id, tab_name)

        sheets_api = self._sheets_api()
        clear_range = self._sheet_range(tab_name, "A:ZZZ")
        self._execute_request(
            sheets_api.spreadsheets()
            .values()
            .clear(
                spreadsheetId=workbook_id,
                range=clear_range,
                body={},
            )
        )

        if not rows:
            return 0

        target_range = self._sheet_range(tab_name, start_cell)
        self._execute_request(
            sheets_api.spreadsheets()
            .values()
            .update(
                spreadsheetId=workbook_id,
                range=target_range,
                valueInputOption="RAW",
                body={"values": rows},
            )
        )
        return len(rows)

    def write_append_rows(
        self,
        workbook_id: str,
        tab_name: str,
        start_cell: str,
        rows: List[List[Any]],
        run_key: str,
    ) -> Tuple[int, int]:
        workbook_lock = self._workbook_lock(workbook_id)
        with workbook_lock:
            self._ensure_sheet_exists(workbook_id, tab_name)
            run_keys = self._load_run_key_cache(workbook_id)
            dedupe_key = (tab_name, run_key)
            if dedupe_key in run_keys:
                return 0, len(rows)

            # Reserve the run key first so retries won't duplicate append writes.
            self._record_run_key(
                workbook_id=workbook_id,
                tab_name=tab_name,
                run_key=run_key,
                rows_written=len(rows),
            )

            try:
                if rows:
                    sheets_api = self._sheets_api()
                    target_range = self._sheet_range(tab_name, start_cell)
                    self._execute_request(
                        sheets_api.spreadsheets()
                        .values()
                        .append(
                            spreadsheetId=workbook_id,
                            range=target_range,
                            valueInputOption="RAW",
                            insertDataOption="INSERT_ROWS",
                            body={"values": rows},
                        )
                    )
            except Exception:
                try:
                    self._remove_run_key_record(workbook_id, tab_name, run_key)
                    self._run_key_cache.setdefault(workbook_id, set()).discard(
                        dedupe_key
                    )
                except Exception as cleanup_error:
                    logger.error(
                        "Failed to clean up reserved run key after append failure "
                        "(workbook_id=%s, tab=%s, run_key=%s): %s",
                        workbook_id,
                        tab_name,
                        run_key,
                        cleanup_error,
                    )
                raise
            return len(rows), 0

    def write_summary_text(
        self,
        workbook_id: str,
        tab_name: str,
        anchor_cell: str,
        text: str,
        clear_range: str | None = None,
    ) -> None:
        self._ensure_sheet_exists(workbook_id, tab_name)
        sheets_api = self._sheets_api()

        if clear_range:
            self._execute_request(
                sheets_api.spreadsheets()
                .values()
                .clear(
                    spreadsheetId=workbook_id,
                    range=self._sheet_range(tab_name, clear_range),
                    body={},
                )
            )

        self._execute_request(
            sheets_api.spreadsheets()
            .values()
            .update(
                spreadsheetId=workbook_id,
                range=self._sheet_range(tab_name, anchor_cell),
                valueInputOption="RAW",
                body={"values": [[text]]},
            )
        )

    def read_cell_text(
        self,
        workbook_id: str,
        tab_name: str,
        anchor_cell: str,
    ) -> str | None:
        self._ensure_sheet_exists(workbook_id, tab_name)
        sheets_api = self._sheets_api()
        response = self._execute_request(
            sheets_api.spreadsheets()
            .values()
            .get(
                spreadsheetId=workbook_id,
                range=self._sheet_range(tab_name, anchor_cell),
            )
        )
        values = response.get("values", []) if isinstance(response, dict) else []
        if not values or not isinstance(values[0], list) or not values[0]:
            return None
        value = values[0][0]
        return str(value) if value is not None else None

    def finalize_workbook(self, workbook_id: str) -> None:
        if not self.config.share_with:
            return

        drive_api = self._drive_api()
        for email in self.config.share_with:
            permission = {
                "type": "user",
                "role": self.config.share_role,
                "emailAddress": email,
            }
            try:
                self._execute_request(
                    drive_api.permissions().create(
                        fileId=workbook_id,
                        body=permission,
                        sendNotificationEmail=True,
                        supportsAllDrives=True,
                    )
                )
                logger.info(
                    "Shared spreadsheet with %s as %s",
                    email,
                    self.config.share_role,
                )
            except HttpError as error:
                raise RenderingError(
                    f"Failed sharing spreadsheet with {email}: {error}"
                )

    def get_workbook_url(self, workbook_id: str) -> str:
        return f"https://docs.google.com/spreadsheets/d/{workbook_id}"
