import os
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pytest
import yaml  # type: ignore[import-untyped]

from slideflow.workbooks.builder import WorkbookBuilder
from slideflow.workbooks.providers.google_sheets import (
    GoogleSheetsProvider,
    GoogleSheetsProviderConfig,
)

pytestmark = pytest.mark.live_google_sheets


def _require_first_env(var_names: Iterable[str], reason: str) -> str:
    for var_name in var_names:
        value = os.getenv(var_name)
        if value:
            return value
    pytest.skip(reason)
    raise RuntimeError("unreachable")


def _parse_optional_email_list(var_name: str) -> List[str]:
    raw = os.getenv(var_name, "")
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture(scope="session")
def live_provider() -> GoogleSheetsProvider:
    if os.getenv("SLIDEFLOW_RUN_LIVE") != "1":
        pytest.skip("SLIDEFLOW_RUN_LIVE != 1; skipping live Google Sheets tests.")

    credentials = _require_first_env(
        ["GOOGLE_SHEETS_CREDENTIALS", "GOOGLE_SLIDEFLOW_CREDENTIALS"],
        "GOOGLE_SHEETS_CREDENTIALS/GOOGLE_SLIDEFLOW_CREDENTIALS is not set.",
    )
    workbook_folder_id = _require_first_env(
        [
            "SLIDEFLOW_LIVE_SHEETS_FOLDER_ID",
            "SLIDEFLOW_LIVE_PRESENTATION_FOLDER_ID",
            "SLIDEFLOW_LIVE_DOCUMENT_FOLDER_ID",
        ],
        "SLIDEFLOW_LIVE_SHEETS_FOLDER_ID is not set.",
    )
    drive_folder_id = os.getenv("SLIDEFLOW_LIVE_DRIVE_FOLDER_ID", workbook_folder_id)
    requests_per_second = float(os.getenv("SLIDEFLOW_LIVE_RPS", "1.0"))

    config = GoogleSheetsProviderConfig(
        credentials=credentials,
        drive_folder_id=drive_folder_id,
        requests_per_second=requests_per_second,
    )
    return GoogleSheetsProvider(config)


def _trash_files(provider: GoogleSheetsProvider, file_ids: Iterable[str]) -> None:
    for file_id in file_ids:
        if not file_id:
            continue
        try:
            provider._execute_request(
                provider.drive_service.files().update(
                    fileId=file_id,
                    body={"trashed": True},
                    supportsAllDrives=True,
                )
            )
        except Exception:
            # Best-effort cleanup for live tests.
            pass


def _tab_result(result, tab_name: str):
    for tab in result.tab_results:
        if tab.tab_name == tab_name:
            return tab
    raise AssertionError(f"Expected tab result for '{tab_name}'")


def _read_values(
    provider: GoogleSheetsProvider, workbook_id: str, a1_range: str
) -> List[List[Any]]:
    response = provider._execute_request(
        provider.sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=workbook_id,
            range=a1_range,
        )
    )
    return response.get("values", []) if isinstance(response, dict) else []


def _write_config(config_path: Path, payload: Dict[str, Any]) -> None:
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@pytest.mark.live_google_sheets
def test_live_google_sheets_replace_and_append_idempotent(
    live_provider: GoogleSheetsProvider, tmp_path: Path
):
    created_file_ids: List[str] = []
    share_with = _parse_optional_email_list("SLIDEFLOW_LIVE_SHARE_EMAIL")
    keep_artifacts = _is_truthy(
        os.getenv("SLIDEFLOW_LIVE_KEEP_ARTIFACTS", "1" if share_with else "0")
    )
    share_role = os.getenv("SLIDEFLOW_LIVE_SHARE_ROLE", "reader")

    replace_data = tmp_path / "replace_data.csv"
    replace_data.write_text("month,value\nJan,10\nFeb,20\n", encoding="utf-8")
    append_data = tmp_path / "append_data.csv"
    append_data.write_text("month,value\nMar,30\nApr,40\n", encoding="utf-8")

    workbook_title = f"slideflow live sheets {uuid.uuid4().hex[:8]}"
    run_key = "week_2026_09"

    provider_config: Dict[str, Any] = {
        "credentials": live_provider.config.credentials,
        "drive_folder_id": live_provider.config.drive_folder_id,
    }
    if share_with:
        provider_config["share_with"] = share_with
        provider_config["share_role"] = share_role

    config_payload: Dict[str, Any] = {
        "provider": {
            "type": "google_sheets",
            "config": provider_config,
        },
        "workbook": {
            "title": workbook_title,
            "tabs": [
                {
                    "name": "kpi_current",
                    "mode": "replace",
                    "start_cell": "A1",
                    "include_header": True,
                    "data_source": {
                        "type": "csv",
                        "name": "replace_source",
                        "file_path": str(replace_data),
                    },
                },
                {
                    "name": "kpi_history",
                    "mode": "append",
                    "start_cell": "A1",
                    "include_header": False,
                    "idempotency_key": run_key,
                    "data_source": {
                        "type": "csv",
                        "name": "append_source",
                        "file_path": str(append_data),
                    },
                },
            ],
        },
    }

    config_path = tmp_path / "live_google_sheets.yml"
    _write_config(config_path, config_payload)
    first_result = WorkbookBuilder.from_yaml(config_path).build()

    workbook_id = first_result.workbook_id
    created_file_ids.append(workbook_id)

    assert first_result.status == "success"
    assert first_result.tabs_total == 2
    assert first_result.tabs_failed == 0
    assert first_result.workbook_url.endswith(workbook_id)

    first_append = _tab_result(first_result, "kpi_history")
    assert first_append.status == "success"
    assert first_append.rows_written == 2
    assert first_append.rows_skipped == 0
    assert first_append.run_key == run_key

    # Second run targets the same workbook to verify append idempotency.
    second_provider_config = dict(provider_config)
    second_provider_config["spreadsheet_id"] = workbook_id
    second_payload = dict(config_payload)
    second_payload["provider"] = {
        "type": "google_sheets",
        "config": second_provider_config,
    }
    second_config_path = tmp_path / "live_google_sheets_rerun.yml"
    _write_config(second_config_path, second_payload)
    second_result = WorkbookBuilder.from_yaml(second_config_path).build()

    assert second_result.status == "success"
    second_append = _tab_result(second_result, "kpi_history")
    assert second_append.rows_written == 0
    assert second_append.rows_skipped == 2

    current_values = _read_values(live_provider, workbook_id, "'kpi_current'!A1:B3")
    assert current_values[0] == ["month", "value"]
    assert ["Jan", "10"] in current_values
    assert ["Feb", "20"] in current_values

    history_values = _read_values(live_provider, workbook_id, "'kpi_history'!A1:B4")
    assert ["Mar", "30"] in history_values
    assert ["Apr", "40"] in history_values
    assert len(history_values) == 2

    metadata_values = _read_values(
        live_provider,
        workbook_id,
        "'_slideflow_meta'!A1:D20",
    )
    assert metadata_values and metadata_values[0][:2] == ["tab_name", "run_key"]
    matching_metadata = [
        row
        for row in metadata_values[1:]
        if len(row) >= 2 and row[0] == "kpi_history" and row[1] == run_key
    ]
    assert len(matching_metadata) == 1

    if share_with:
        print(
            "Shared rendered workbook with "
            f"{', '.join(share_with)} ({share_role}): {first_result.workbook_url}"
        )

    if not keep_artifacts:
        _trash_files(live_provider, created_file_ids)
    else:
        print(
            "Retaining live test artifacts (set SLIDEFLOW_LIVE_KEEP_ARTIFACTS=0 "
            "for auto-cleanup)."
        )
