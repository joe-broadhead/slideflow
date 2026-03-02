from __future__ import annotations

import threading
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
        create=lambda **kwargs: ("spreadsheets.create", kwargs),
        batchUpdate=lambda **kwargs: ("spreadsheets.batchUpdate", kwargs),
    )
    return SimpleNamespace(spreadsheets=lambda: spreadsheets_api)


def _minimal_drive_service():
    files_api = SimpleNamespace(
        get=lambda **kwargs: ("drive.files.get", kwargs),
        create=lambda **kwargs: ("drive.files.create", kwargs),
        update=lambda **kwargs: ("drive.files.update", kwargs),
    )
    return SimpleNamespace(files=lambda: files_api)


def test_get_rate_limiter_reuses_existing_limiter_for_same_rate(monkeypatch):
    monkeypatch.setattr(sheets_provider_module, "_sheets_rate_limiters", {})

    first = sheets_provider_module._get_rate_limiter(1.0)
    second = sheets_provider_module._get_rate_limiter(1.0)

    assert first is second


def test_get_rate_limiter_creates_distinct_limiters_for_distinct_rates(monkeypatch):
    monkeypatch.setattr(sheets_provider_module, "_sheets_rate_limiters", {})

    one_rps = sheets_provider_module._get_rate_limiter(1.0)
    two_rps = sheets_provider_module._get_rate_limiter(2.0)

    assert one_rps is not two_rps


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


def test_write_append_rows_is_thread_safe_for_duplicate_run_keys():
    provider = _provider_without_init()
    provider.sheets_service = _minimal_sheets_service()

    def _ensure_sheet_exists(workbook_id: str, tab_name: str) -> None:
        del workbook_id, tab_name

    provider._ensure_sheet_exists = _ensure_sheet_exists

    run_keys: Set[Tuple[str, str]] = set()
    run_keys_lock = threading.Lock()

    def _load_run_key_cache(_workbook_id: str) -> Set[Tuple[str, str]]:
        return run_keys

    provider._load_run_key_cache = _load_run_key_cache

    recorded: List[Tuple[str, str]] = []

    def _record_run_key(
        workbook_id: str, tab_name: str, run_key: str, rows_written: int
    ) -> None:
        del workbook_id, rows_written
        with run_keys_lock:
            run_keys.add((tab_name, run_key))
            recorded.append((tab_name, run_key))

    provider._record_run_key = _record_run_key
    provider._remove_run_key_record = lambda workbook_id, tab_name, run_key: None
    provider._sheet_range = lambda tab_name, range_part: f"{tab_name}!{range_part}"

    append_calls = 0
    append_calls_lock = threading.Lock()

    def _exec(request):
        nonlocal append_calls
        if request[0] == "values.append":
            with append_calls_lock:
                append_calls += 1
        return {}

    provider._execute_request = _exec

    results: List[Tuple[int, int]] = []

    def _worker() -> None:
        outcome = provider.write_append_rows(
            workbook_id="sheet_123",
            tab_name="kpi_current",
            start_cell="A1",
            rows=[[1]],
            run_key="wk_concurrent",
        )
        results.append(outcome)

    workers = [threading.Thread(target=_worker), threading.Thread(target=_worker)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert sorted(results) == [(0, 1), (1, 0)]
    assert append_calls == 1
    assert recorded == [("kpi_current", "wk_concurrent")]


def test_provider_uses_thread_local_google_clients(monkeypatch):
    provider = _provider_without_init()
    provider._credentials = object()
    provider._thread_local_services = threading.local()

    created: List[Tuple[str, int]] = []
    sequence = {"value": 0}

    def _fake_build(api_name: str, _version: str, credentials: Any):
        del credentials
        sequence["value"] += 1
        marker = sequence["value"]
        created.append((api_name, marker))
        return {"api": api_name, "marker": marker}

    monkeypatch.setattr(sheets_provider_module, "build", _fake_build)

    main_sheets_first = provider._sheets_api()
    main_sheets_second = provider._sheets_api()
    main_drive_first = provider._drive_api()
    main_drive_second = provider._drive_api()

    thread_results: Dict[str, Any] = {}

    def _worker() -> None:
        worker_sheets_first = provider._sheets_api()
        worker_sheets_second = provider._sheets_api()
        worker_drive_first = provider._drive_api()
        worker_drive_second = provider._drive_api()
        thread_results["sheets_first"] = worker_sheets_first
        thread_results["sheets_second"] = worker_sheets_second
        thread_results["drive_first"] = worker_drive_first
        thread_results["drive_second"] = worker_drive_second

    worker = threading.Thread(target=_worker)
    worker.start()
    worker.join()

    assert main_sheets_first is main_sheets_second
    assert main_drive_first is main_drive_second
    assert thread_results["sheets_first"] is thread_results["sheets_second"]
    assert thread_results["drive_first"] is thread_results["drive_second"]
    assert main_sheets_first is not thread_results["sheets_first"]
    assert main_drive_first is not thread_results["drive_first"]

    assert created.count(("sheets", main_sheets_first["marker"])) == 1
    assert created.count(("drive", main_drive_first["marker"])) == 1
    assert created.count(("sheets", thread_results["sheets_first"]["marker"])) == 1
    assert created.count(("drive", thread_results["drive_first"]["marker"])) == 1


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
            file_id = request[1].get("fileId")
            if file_id == "sheet_123":
                return {
                    "id": "sheet_123",
                    "trashed": False,
                    "capabilities": {"canEdit": True},
                }
            return {
                "id": "folder_456",
                "mimeType": "application/vnd.google-apps.folder",
                "trashed": False,
                "capabilities": {"canAddChildren": True},
            }
        return {}

    provider._execute_request = _exec
    checks = provider.run_preflight_checks()
    check_map = {name: ok for name, ok, _ in checks}

    assert check_map["google_sheets_credentials_present"] is True
    assert check_map["spreadsheet_access"] is True
    assert check_map["spreadsheet_write_access"] is True
    assert check_map["drive_folder_access"] is True
    assert check_map["drive_folder_write_access"] is True
    assert [req[0] for req in requests] == [
        "spreadsheets.get",
        "drive.files.get",
        "drive.files.get",
    ]


def test_base_preflight_checks_returns_expected_core_entries():
    provider = _provider_without_init()
    provider.config = SimpleNamespace(credentials=None, requests_per_second=2.0)
    provider.sheets_service = object()
    provider.drive_service = object()
    provider.rate_limiter = object()

    checks = provider._base_preflight_checks()
    check_map = {name: ok for name, ok, _ in checks}

    assert len(checks) == 4
    assert check_map["google_sheets_credentials_present"] is False
    assert check_map["sheets_service_initialized"] is True
    assert check_map["drive_service_initialized"] is True
    assert check_map["rate_limiter_initialized"] is True


def test_drive_folder_access_checks_return_dual_failures_on_lookup_error():
    provider = _provider_without_init()
    provider.config = SimpleNamespace(drive_folder_id="folder_456")
    provider.drive_service = _minimal_drive_service()
    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        RuntimeError("drive denied")
    )

    checks = provider._drive_folder_access_checks()
    check_map = {name: ok for name, ok, _ in checks}
    check_details = {name: detail for name, _ok, detail in checks}

    assert check_map["drive_folder_access"] is False
    assert check_map["drive_folder_write_access"] is False
    assert "drive denied" in check_details["drive_folder_access"]
    assert "drive denied" in check_details["drive_folder_write_access"]


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
    assert check_map["spreadsheet_write_access"] is False
    assert "not writable" in check_details["spreadsheet_write_access"]


def test_run_preflight_checks_write_lookup_failure_does_not_flip_spreadsheet_access():
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
            return {"spreadsheetId": "sheet_123"}
        if request[0] == "drive.files.get":
            raise RuntimeError("drive denied")
        return {}

    provider._execute_request = _exec
    checks = provider.run_preflight_checks()
    check_details = {name: detail for name, _ok, detail in checks}
    check_map = {name: ok for name, ok, _detail in checks}
    spreadsheet_access_entries = [
        name for name, _ok, _detail in checks if name == "spreadsheet_access"
    ]

    assert spreadsheet_access_entries == ["spreadsheet_access"]
    assert check_map["spreadsheet_access"] is True
    assert check_map["spreadsheet_write_access"] is False
    assert "drive denied" in check_details["spreadsheet_write_access"]


def test_create_or_open_workbook_falls_back_to_drive_create_on_sheets_create_failure(
    monkeypatch,
):
    provider = _provider_without_init()
    provider.config = SimpleNamespace(
        spreadsheet_id=None,
        drive_folder_id="folder_456",
    )
    provider.sheets_service = _minimal_sheets_service()
    provider.drive_service = _minimal_drive_service()

    # Exercise fallback path without constructing google HttpError payloads.
    monkeypatch.setattr(sheets_provider_module, "HttpError", RuntimeError)

    requests: List[Tuple[str, Dict[str, Any]]] = []

    def _exec(request):
        requests.append(request)
        if request[0] == "spreadsheets.create":
            raise RuntimeError("forbidden")
        if request[0] == "drive.files.create":
            return {"id": "sheet_via_drive"}
        return {}

    provider._execute_request = _exec

    workbook_id = provider.create_or_open_workbook("Weekly KPI Snapshot")

    assert workbook_id == "sheet_via_drive"
    assert [req[0] for req in requests] == ["spreadsheets.create", "drive.files.create"]


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


def test_read_cell_text_returns_value_when_present():
    provider = _provider_without_init()
    provider.sheets_service = _minimal_sheets_service()
    provider._ensure_sheet_exists = lambda workbook_id, tab_name: None
    provider._sheet_range = lambda tab_name, range_part: f"{tab_name}!{range_part}"

    requests: List[Tuple[str, Dict[str, Any]]] = []

    def _exec(request):
        requests.append(request)
        return {"values": [["Existing text"]]}

    provider._execute_request = _exec

    value = provider.read_cell_text(
        workbook_id="sheet_123",
        tab_name="summary",
        anchor_cell="A1",
    )

    assert value == "Existing text"
    assert requests and requests[0][0] == "values.get"
    assert requests[0][1]["range"] == "summary!A1"


def test_read_cell_text_returns_none_when_cell_empty():
    provider = _provider_without_init()
    provider.sheets_service = _minimal_sheets_service()
    provider._ensure_sheet_exists = lambda workbook_id, tab_name: None
    provider._sheet_range = lambda tab_name, range_part: f"{tab_name}!{range_part}"
    provider._execute_request = lambda request: {"values": []}

    value = provider.read_cell_text(
        workbook_id="sheet_123",
        tab_name="summary",
        anchor_cell="A1",
    )

    assert value is None
