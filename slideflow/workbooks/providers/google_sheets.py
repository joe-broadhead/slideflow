"""Google Sheets workbook provider implementation."""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Literal, Optional, Tuple

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import Field

from slideflow.constants import Environment, GoogleSlides
from slideflow.utilities.auth import handle_google_credentials
from slideflow.utilities.exceptions import AuthenticationError, RenderingError
from slideflow.utilities.logging import get_logger
from slideflow.utilities.rate_limiter import RateLimiter
from slideflow.workbooks.providers.base import WorkbookProvider, WorkbookProviderConfig

logger = get_logger(__name__)
_sheets_rate_limiter: Optional[RateLimiter] = None
_rate_limiter_lock = threading.Lock()


def _get_rate_limiter(rps: float, force_update: bool = False) -> RateLimiter:
    """Get or create the global Google Sheets API rate limiter."""
    global _sheets_rate_limiter
    with _rate_limiter_lock:
        if _sheets_rate_limiter is None:
            _sheets_rate_limiter = RateLimiter(rps)
        elif force_update:
            _sheets_rate_limiter.set_rate(rps)
        return _sheets_rate_limiter


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

        try:
            credentials = Credentials.from_service_account_info(
                loaded_credentials, scopes=self.SCOPES
            )
        except Exception as error_msg:  # pragma: no cover - exercised via tests
            raise AuthenticationError(f"Credentials authentication failed: {error_msg}")

        self.sheets_service = build("sheets", "v4", credentials=credentials)
        self.drive_service = build("drive", "v3", credentials=credentials)
        self.rate_limiter = _get_rate_limiter(self.config.requests_per_second)

    def _execute_request(self, request):
        """Execute Google API request with shared rate limiting."""
        self.rate_limiter.wait()
        return request.execute(num_retries=3)

    def run_preflight_checks(self) -> List[Tuple[str, bool, str]]:
        has_credentials = bool(self.config.credentials) or bool(
            os.getenv(Environment.GOOGLE_SHEETS_CREDENTIALS)
            or os.getenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS)
        )
        checks: List[Tuple[str, bool, str]] = [
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
                self.sheets_service is not None,
                (
                    "Google Sheets API client initialized"
                    if self.sheets_service is not None
                    else "Google Sheets API client is not initialized"
                ),
            ),
            (
                "drive_service_initialized",
                self.drive_service is not None,
                (
                    "Google Drive API client initialized"
                    if self.drive_service is not None
                    else "Google Drive API client is not initialized"
                ),
            ),
            (
                "rate_limiter_initialized",
                self.rate_limiter is not None,
                (
                    f"Rate limiter configured at {self.config.requests_per_second} rps"
                    if self.rate_limiter is not None
                    else "Rate limiter is not initialized"
                ),
            ),
        ]
        return checks

    def create_or_open_workbook(self, title: str) -> str:
        if self.config.spreadsheet_id:
            return self.config.spreadsheet_id

        response = self._execute_request(
            self.sheets_service.spreadsheets().create(
                body={"properties": {"title": title}},
                fields="spreadsheetId",
            )
        )
        spreadsheet_id = str(response.get("spreadsheetId", "")).strip()
        if not spreadsheet_id:
            raise RenderingError("Failed to create Google Sheet: missing spreadsheetId")

        if self.config.drive_folder_id:
            self._move_file_to_folder(spreadsheet_id, self.config.drive_folder_id)

        return spreadsheet_id

    def _move_file_to_folder(self, file_id: str, folder_id: str) -> None:
        metadata = self._execute_request(
            self.drive_service.files().get(
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
        self._execute_request(self.drive_service.files().update(**request_kwargs))

    def _sheet_range(self, tab_name: str, range_part: str) -> str:
        escaped_tab_name = tab_name.replace("'", "''")
        return f"'{escaped_tab_name}'!{range_part}"

    def _fetch_sheet_titles(self, workbook_id: str) -> Dict[str, int]:
        response = self._execute_request(
            self.sheets_service.spreadsheets().get(
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
        self._execute_request(
            self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=workbook_id,
                body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
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

        clear_range = self._sheet_range(tab_name, "A:ZZZ")
        self._execute_request(
            self.sheets_service.spreadsheets()
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
            self.sheets_service.spreadsheets()
            .values()
            .update(
                spreadsheetId=workbook_id,
                range=target_range,
                valueInputOption="RAW",
                body={"values": rows},
            )
        )
        return len(rows)

    def finalize_workbook(self, workbook_id: str) -> None:
        if not self.config.share_with:
            return

        for email in self.config.share_with:
            permission = {
                "type": "user",
                "role": self.config.share_role,
                "emailAddress": email,
            }
            try:
                self._execute_request(
                    self.drive_service.permissions().create(
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
