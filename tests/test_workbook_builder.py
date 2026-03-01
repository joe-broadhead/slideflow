from pathlib import Path

import pandas as pd

import slideflow.workbooks.builder as workbook_builder_module
from slideflow.workbooks.builder import WorkbookBuilder, dataframe_to_sheet_rows
from slideflow.workbooks.config import WorkbookConfig


class _FakeProvider:
    def __init__(self, fail_tab: str | None = None):
        self.fail_tab = fail_tab
        self.calls = []
        self.append_calls = []
        self.finalized_ids = []
        self._seen_run_keys = set()

    def create_or_open_workbook(self, title: str) -> str:
        assert title == "Weekly KPI Snapshot"
        return "sheet_123"

    def write_replace_rows(self, workbook_id, tab_name, start_cell, rows):
        if self.fail_tab == tab_name:
            raise RuntimeError("tab write failed")
        self.calls.append(
            {
                "workbook_id": workbook_id,
                "tab_name": tab_name,
                "start_cell": start_cell,
                "rows": rows,
            }
        )
        return len(rows)

    def write_append_rows(self, workbook_id, tab_name, start_cell, rows, run_key):
        if self.fail_tab == tab_name:
            raise RuntimeError("tab write failed")
        dedupe_key = (tab_name, run_key)
        if dedupe_key in self._seen_run_keys:
            return 0, len(rows)
        self._seen_run_keys.add(dedupe_key)
        self.append_calls.append(
            {
                "workbook_id": workbook_id,
                "tab_name": tab_name,
                "start_cell": start_cell,
                "rows": rows,
                "run_key": run_key,
            }
        )
        return len(rows), 0

    def finalize_workbook(self, workbook_id: str):
        self.finalized_ids.append(workbook_id)

    def get_workbook_url(self, workbook_id: str) -> str:
        return f"https://docs.google.com/spreadsheets/d/{workbook_id}"


def _workbook_payload(csv_path: Path):
    return {
        "provider": {"type": "google_sheets", "config": {}},
        "workbook": {
            "title": "Weekly KPI Snapshot",
            "tabs": [
                {
                    "name": "kpi_current",
                    "mode": "replace",
                    "start_cell": "A1",
                    "include_header": True,
                    "data_source": {
                        "type": "csv",
                        "name": "kpi_source",
                        "file_path": str(csv_path),
                    },
                }
            ],
        },
    }


def test_dataframe_to_sheet_rows_normalizes_nan_values():
    df = pd.DataFrame({"month": ["Jan", "Feb"], "value": [10.0, float("nan")]})

    rows = dataframe_to_sheet_rows(df, include_header=True)

    assert rows[0] == ["month", "value"]
    assert rows[1] == ["Jan", 10.0]
    assert rows[2] == ["Feb", None]


def test_workbook_builder_build_success(tmp_path, monkeypatch):
    csv_path = tmp_path / "kpi.csv"
    csv_path.write_text("month,value\nJan,10\nFeb,20\n", encoding="utf-8")
    config = WorkbookConfig.model_validate(_workbook_payload(csv_path))

    fake_provider = _FakeProvider()
    monkeypatch.setattr(
        workbook_builder_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _config: fake_provider),
    )

    result = WorkbookBuilder.from_config(config).build()

    assert result.status == "success"
    assert result.workbook_id == "sheet_123"
    assert result.tabs_total == 1
    assert result.tabs_succeeded == 1
    assert result.tabs_failed == 0
    assert result.tab_results[0].rows_written == 2
    assert fake_provider.finalized_ids == ["sheet_123"]
    assert fake_provider.calls[0]["rows"][0] == ["month", "value"]


def test_workbook_builder_collects_tab_errors_without_aborting(tmp_path, monkeypatch):
    csv_path = tmp_path / "kpi.csv"
    csv_path.write_text("month,value\nJan,10\n", encoding="utf-8")
    payload = _workbook_payload(csv_path)
    payload["workbook"]["tabs"].append(
        {
            "name": "failing_tab",
            "mode": "replace",
            "start_cell": "A1",
            "include_header": True,
            "data_source": {
                "type": "csv",
                "name": "kpi_source_fail",
                "file_path": str(csv_path),
            },
        }
    )
    config = WorkbookConfig.model_validate(payload)

    fake_provider = _FakeProvider(fail_tab="failing_tab")
    monkeypatch.setattr(
        workbook_builder_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _config: fake_provider),
    )

    result = WorkbookBuilder.from_config(config).build()

    assert result.status == "error"
    assert result.tabs_total == 2
    assert result.tabs_succeeded == 1
    assert result.tabs_failed == 1
    assert [tab.tab_name for tab in result.tab_results] == [
        "kpi_current",
        "failing_tab",
    ]
    assert result.tab_results[1].error == "tab write failed"


def test_workbook_builder_append_mode_tracks_idempotent_skips(tmp_path, monkeypatch):
    csv_path = tmp_path / "kpi.csv"
    csv_path.write_text("month,value\nJan,10\nFeb,20\n", encoding="utf-8")
    payload = _workbook_payload(csv_path)
    payload["workbook"]["tabs"][0]["mode"] = "append"
    payload["workbook"]["tabs"][0]["idempotency_key"] = "week_2026_09"
    config = WorkbookConfig.model_validate(payload)

    fake_provider = _FakeProvider()
    monkeypatch.setattr(
        workbook_builder_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _config: fake_provider),
    )

    first_result = WorkbookBuilder.from_config(config).build()
    second_result = WorkbookBuilder.from_config(config).build()

    assert first_result.status == "success"
    assert first_result.tab_results[0].run_key == "week_2026_09"
    assert first_result.tab_results[0].rows_written == 2
    assert first_result.idempotent_skips == 0

    assert second_result.status == "success"
    assert second_result.tab_results[0].rows_written == 0
    assert second_result.tab_results[0].rows_skipped == 2
    assert second_result.idempotent_skips == 2
    assert fake_provider.append_calls[0]["rows"][0] == ["Jan", "10"]
