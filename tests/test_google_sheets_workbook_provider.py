from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Set, Tuple

import pytest

import slideflow.workbooks.providers.google_sheets as sheets_provider_module
from slideflow.workbooks.config import RESERVED_METADATA_TAB


def _provider_without_init() -> sheets_provider_module.GoogleSheetsProvider:
    return object.__new__(sheets_provider_module.GoogleSheetsProvider)


def _minimal_sheets_service():
    values_api = SimpleNamespace(
        get=lambda **kwargs: ("values.get", kwargs),
        update=lambda **kwargs: ("values.update", kwargs),
        append=lambda **kwargs: ("values.append", kwargs),
        clear=lambda **kwargs: ("values.clear", kwargs),
    )
    spreadsheets_api = SimpleNamespace(
        values=lambda: values_api,
        get=lambda **kwargs: ("spreadsheets.get", kwargs),
        batchUpdate=lambda **kwargs: ("spreadsheets.batchUpdate", kwargs),
    )
    return SimpleNamespace(spreadsheets=lambda: spreadsheets_api)


def _minimal_drive_service():
    files_api = SimpleNamespace(get=lambda **kwargs: ("drive.files.get", kwargs))
    return SimpleNamespace(files=lambda: files_api)


def test_load_run_key_cache_populates_and_reuses_cache():
    provider = _provider_without_init()
    provider._run_key_cache = {}
    provider.sheets_service = _minimal_sheets_service()
    ensured: List[str] = []

    def _ensure_metadata_tab(workbook_id: str) -> None:
        ensured.append(workbook_id)

    def _sheet_range(tab_name: str, range_part: str) -> str:
        return f"{tab_name}!{range_part}"

    provider._ensure_metadata_tab = _ensure_metadata_tab
    provider._sheet_range = _sheet_range

    def _exec(_request):
        return {"values": [["kpi_current", "wk_1"], ["bad_row"], ["kpi_other", "wk_2"]]}

    provider._execute_request = _exec

    keys_first = provider._load_run_key_cache("sheet_123")
    keys_second = provider._load_run_key_cache("sheet_123")

    assert keys_first == {("kpi_current", "wk_1"), ("kpi_other", "wk_2")}
    assert keys_second == keys_first
    assert ensured == ["sheet_123"]


def test_record_run_key_appends_metadata_and_updates_cache():
    provider = _provider_without_init()
    provider._run_key_cache = {}
    provider.sheets_service = _minimal_sheets_service()

    def _sheet_range(tab_name: str, range_part: str) -> str:
        return f"{tab_name}!{range_part}"

    provider._sheet_range = _sheet_range
    requests: List[Tuple[str, Dict[str, Any]]] = []

    def _exec(request):
        requests.append(request)
        return {}

    provider._execute_request = _exec

    provider._record_run_key(
        workbook_id="sheet_123",
        tab_name="kpi_current",
        run_key="wk_1",
        rows_written=2,
    )

    assert ("kpi_current", "wk_1") in provider._run_key_cache["sheet_123"]
    assert requests and requests[0][0] == "values.append"
    assert requests[0][1]["spreadsheetId"] == "sheet_123"
    assert requests[0][1]["range"] == f"{RESERVED_METADATA_TAB}!A1"


def test_write_append_rows_skips_when_run_key_already_recorded():
    provider = _provider_without_init()
    provider.sheets_service = _minimal_sheets_service()

    def _ensure_sheet_exists(workbook_id: str, tab_name: str) -> None:
        del workbook_id, tab_name

    def _load_run_key_cache(_workbook_id: str) -> Set[Tuple[str, str]]:
        return {("kpi_current", "wk_1")}

    def _record_run_key(**_kwargs) -> None:
        raise AssertionError("should not record duplicate run key")

    def _sheet_range(tab_name: str, range_part: str) -> str:
        return f"{tab_name}!{range_part}"

    provider._ensure_sheet_exists = _ensure_sheet_exists
    provider._load_run_key_cache = _load_run_key_cache
    provider._record_run_key = _record_run_key
    provider._sheet_range = _sheet_range
    requests: List[Tuple[str, Dict[str, Any]]] = []

    def _exec(request):
        requests.append(request)
        return {}

    provider._execute_request = _exec

    rows_written, rows_skipped = provider.write_append_rows(
        workbook_id="sheet_123",
        tab_name="kpi_current",
        start_cell="A1",
        rows=[[1], [2], [3]],
        run_key="wk_1",
    )

    assert rows_written == 0
    assert rows_skipped == 3
    assert requests == []


def test_write_append_rows_appends_and_records_new_run_key():
    provider = _provider_without_init()
    provider.sheets_service = _minimal_sheets_service()

    def _ensure_sheet_exists(workbook_id: str, tab_name: str) -> None:
        del workbook_id, tab_name

    provider._ensure_sheet_exists = _ensure_sheet_exists
    run_keys: Set[Tuple[str, str]] = set()

    def _load_run_key_cache(_workbook_id: str) -> Set[Tuple[str, str]]:
        return run_keys

    provider._load_run_key_cache = _load_run_key_cache
    recorded: List[Tuple[str, str, str, int]] = []

    def _record_run_key(
        workbook_id: str, tab_name: str, run_key: str, rows_written: int
    ) -> None:
        recorded.append((workbook_id, tab_name, run_key, rows_written))

    def _sheet_range(tab_name: str, range_part: str) -> str:
        return f"{tab_name}!{range_part}"

    provider._record_run_key = _record_run_key
    provider._sheet_range = _sheet_range
    requests: List[Tuple[str, Dict[str, Any]]] = []

    def _exec(request):
        requests.append(request)
        return {}

    provider._execute_request = _exec

    rows_written, rows_skipped = provider.write_append_rows(
        workbook_id="sheet_123",
        tab_name="kpi_current",
        start_cell="B2",
        rows=[[1], [2]],
        run_key="wk_2",
    )

    assert rows_written == 2
    assert rows_skipped == 0
    assert requests and requests[0][0] == "values.append"
    assert requests[0][1]["range"] == "kpi_current!B2"
    assert recorded == [("sheet_123", "kpi_current", "wk_2", 2)]


def test_write_append_rows_cleans_reserved_key_when_data_append_fails():
    provider = _provider_without_init()
    provider.sheets_service = _minimal_sheets_service()

    def _ensure_sheet_exists(workbook_id: str, tab_name: str) -> None:
        del workbook_id, tab_name

    provider._ensure_sheet_exists = _ensure_sheet_exists
    run_keys: Set[Tuple[str, str]] = set()
    provider._load_run_key_cache = lambda _workbook_id: run_keys

    reserved: List[Tuple[str, str]] = []
    removed: List[Tuple[str, str]] = []

    def _record_run_key(
        workbook_id: str, tab_name: str, run_key: str, rows_written: int
    ) -> None:
        del workbook_id, rows_written
        reserved.append((tab_name, run_key))
        run_keys.add((tab_name, run_key))

    def _remove_run_key_record(workbook_id: str, tab_name: str, run_key: str) -> None:
        del workbook_id
        removed.append((tab_name, run_key))
        run_keys.discard((tab_name, run_key))

    provider._record_run_key = _record_run_key
    provider._remove_run_key_record = _remove_run_key_record
    provider._sheet_range = lambda tab_name, range_part: f"{tab_name}!{range_part}"

    def _exec(request):
        if request[0] == "values.append":
            raise RuntimeError("append failed")
        return {}

    provider._execute_request = _exec

    with pytest.raises(RuntimeError, match="append failed"):
        provider.write_append_rows(
            workbook_id="sheet_123",
            tab_name="kpi_current",
            start_cell="A1",
            rows=[[1], [2]],
            run_key="wk_3",
        )

    assert reserved == [("kpi_current", "wk_3")]
    assert removed == [("kpi_current", "wk_3")]
    assert ("kpi_current", "wk_3") not in run_keys


def test_write_append_rows_keeps_reserved_key_if_cleanup_fails():
    provider = _provider_without_init()
    provider.sheets_service = _minimal_sheets_service()

    def _ensure_sheet_exists(workbook_id: str, tab_name: str) -> None:
        del workbook_id, tab_name

    provider._ensure_sheet_exists = _ensure_sheet_exists
    run_keys: Set[Tuple[str, str]] = set()
    provider._load_run_key_cache = lambda _workbook_id: run_keys

    def _record_run_key(
        workbook_id: str, tab_name: str, run_key: str, rows_written: int
    ) -> None:
        del workbook_id, rows_written
        run_keys.add((tab_name, run_key))

    def _remove_run_key_record(workbook_id: str, tab_name: str, run_key: str) -> None:
        del workbook_id, tab_name, run_key
        raise RuntimeError("cleanup failed")

    provider._record_run_key = _record_run_key
    provider._remove_run_key_record = _remove_run_key_record
    provider._sheet_range = lambda tab_name, range_part: f"{tab_name}!{range_part}"

    def _exec(request):
        if request[0] == "values.append":
            raise RuntimeError("append failed")
        return {}

    provider._execute_request = _exec

    with pytest.raises(RuntimeError, match="append failed"):
        provider.write_append_rows(
            workbook_id="sheet_123",
            tab_name="kpi_current",
            start_cell="A1",
            rows=[[1]],
            run_key="wk_4",
        )

    assert ("kpi_current", "wk_4") in run_keys


def test_run_preflight_checks_with_spreadsheet_and_folder_access():
    provider = _provider_without_init()
    provider.config = SimpleNamespace(
        credentials="{}",
        requests_per_second=1.0,
        spreadsheet_id="sheet_123",
        drive_folder_id="folder_456",
    )
    provider.sheets_service = _minimal_sheets_service()
    provider.drive_service = _minimal_drive_service()
    provider.rate_limiter = object()

    requests: List[Tuple[str, Dict[str, Any]]] = []

    def _exec(request):
        requests.append(request)
        if request[0] == "spreadsheets.get":
            return {"spreadsheetId": "sheet_123"}
        if request[0] == "drive.files.get":
            return {
                "id": "folder_456",
                "mimeType": "application/vnd.google-apps.folder",
                "trashed": False,
            }
        return {}

    provider._execute_request = _exec
    checks = provider.run_preflight_checks()
    check_map = {name: ok for name, ok, _ in checks}

    assert check_map["google_sheets_credentials_present"] is True
    assert check_map["spreadsheet_access"] is True
    assert check_map["drive_folder_access"] is True
    assert [req[0] for req in requests] == ["spreadsheets.get", "drive.files.get"]


def test_run_preflight_checks_reports_spreadsheet_access_failure():
    provider = _provider_without_init()
    provider.config = SimpleNamespace(
        credentials="{}",
        requests_per_second=1.0,
        spreadsheet_id="sheet_123",
        drive_folder_id=None,
    )
    provider.sheets_service = _minimal_sheets_service()
    provider.drive_service = _minimal_drive_service()
    provider.rate_limiter = object()

    def _exec(request):
        if request[0] == "spreadsheets.get":
            raise RuntimeError("not found")
        return {}

    provider._execute_request = _exec
    checks = provider.run_preflight_checks()
    check_details = {name: detail for name, _ok, detail in checks}
    check_map = {name: ok for name, ok, _detail in checks}

    assert check_map["spreadsheet_access"] is False
    assert "not found" in check_details["spreadsheet_access"]


def test_write_summary_text_clears_range_before_write():
    provider = _provider_without_init()
    provider.sheets_service = _minimal_sheets_service()
    provider._ensure_sheet_exists = lambda workbook_id, tab_name: None
    provider._sheet_range = lambda tab_name, range_part: f"{tab_name}!{range_part}"
    requests: List[Tuple[str, Dict[str, Any]]] = []

    def _exec(request):
        requests.append(request)
        return {}

    provider._execute_request = _exec

    provider.write_summary_text(
        workbook_id="sheet_123",
        tab_name="kpi_current",
        anchor_cell="H2",
        text="Summary text",
        clear_range="H2:H20",
    )

    assert requests[0][0] == "values.clear"
    assert requests[0][1]["range"] == "kpi_current!H2:H20"
    assert requests[1][0] == "values.update"
    assert requests[1][1]["range"] == "kpi_current!H2"
    assert requests[1][1]["body"]["values"] == [["Summary text"]]


def test_write_summary_text_writes_without_clear_range():
    provider = _provider_without_init()
    provider.sheets_service = _minimal_sheets_service()
    provider._ensure_sheet_exists = lambda workbook_id, tab_name: None
    provider._sheet_range = lambda tab_name, range_part: f"{tab_name}!{range_part}"
    requests: List[Tuple[str, Dict[str, Any]]] = []

    def _exec(request):
        requests.append(request)
        return {}

    provider._execute_request = _exec

    provider.write_summary_text(
        workbook_id="sheet_123",
        tab_name="summary",
        anchor_cell="A1",
        text="Weekly summary",
    )

    assert len(requests) == 1
    assert requests[0][0] == "values.update"
    assert requests[0][1]["range"] == "summary!A1"
    assert requests[0][1]["body"]["values"] == [["Weekly summary"]]
