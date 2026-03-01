from decimal import Decimal
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
        self.summary_calls = []
        self.summary_reads = []
        self.finalized_ids = []
        self._seen_run_keys = set()
        self._cell_text = {}

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

    def write_summary_text(
        self, workbook_id, tab_name, anchor_cell, text, clear_range=None
    ):
        if self.fail_tab == tab_name:
            raise RuntimeError("summary write failed")
        self._cell_text[(tab_name, anchor_cell)] = text
        self.summary_calls.append(
            {
                "workbook_id": workbook_id,
                "tab_name": tab_name,
                "anchor_cell": anchor_cell,
                "text": text,
                "clear_range": clear_range,
            }
        )

    def read_cell_text(self, workbook_id, tab_name, anchor_cell):
        self.summary_reads.append(
            {
                "workbook_id": workbook_id,
                "tab_name": tab_name,
                "anchor_cell": anchor_cell,
            }
        )
        return self._cell_text.get((tab_name, anchor_cell))

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


def test_dataframe_to_sheet_rows_handles_pandas_index_without_truthiness_error():
    class _AmbiguousColumns:
        def __iter__(self):
            return iter(["region", "gmv"])

        def __bool__(self):
            raise ValueError("ambiguous truth value")

    class _DataFrameLike:
        columns = _AmbiguousColumns()
        values = []

    df = _DataFrameLike()

    rows = dataframe_to_sheet_rows(df, include_header=True)

    assert rows == [["region", "gmv"]]


def test_dataframe_to_sheet_rows_normalizes_decimal_values():
    df = pd.DataFrame({"region": ["WEUR"], "gmv": [Decimal("123.45")]})

    rows = dataframe_to_sheet_rows(df, include_header=True)

    assert rows[0] == ["region", "gmv"]
    assert rows[1] == ["WEUR", 123.45]


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
    payload["workbook"]["tabs"][0]["include_header"] = False
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


def test_workbook_builder_generates_and_writes_same_sheet_summary(
    tmp_path, monkeypatch
):
    csv_path = tmp_path / "kpi.csv"
    csv_path.write_text("month,value\nJan,10\nFeb,20\n", encoding="utf-8")
    payload = _workbook_payload(csv_path)
    payload["workbook"]["summaries"] = [
        {
            "name": "kpi_summary",
            "source_tab": "kpi_current",
            "provider": "openai",
            "provider_args": {"model": "gpt-4o-mini"},
            "prompt": "Summarize the latest metrics",
            "placement": {
                "type": "same_sheet",
                "tab_name": "kpi_current",
                "anchor_cell": "H2",
                "clear_range": "H2:H20",
            },
        }
    ]
    config = WorkbookConfig.model_validate(payload)

    fake_provider = _FakeProvider()
    monkeypatch.setattr(
        workbook_builder_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _config: fake_provider),
    )

    class _FakeAIProvider:
        def __init__(self):
            self.prompts = []

        def generate_text(self, prompt: str):
            self.prompts.append(prompt)
            return "AI summary output"

    ai_provider = _FakeAIProvider()
    monkeypatch.setattr(
        workbook_builder_module,
        "create_ai_provider",
        lambda provider_name, **kwargs: ai_provider,
    )

    result = WorkbookBuilder.from_config(config).build()

    assert result.status == "success"
    assert result.summaries_total == 1
    assert result.summaries_succeeded == 1
    assert result.summaries_failed == 0
    assert result.summary_results[0].chars_written == len("AI summary output")
    assert fake_provider.summary_calls == [
        {
            "workbook_id": "sheet_123",
            "tab_name": "kpi_current",
            "anchor_cell": "H2",
            "text": "AI summary output",
            "clear_range": "H2:H20",
        }
    ]
    assert "Data:" in ai_provider.prompts[0]


def test_workbook_builder_marks_error_when_summary_write_fails(tmp_path, monkeypatch):
    csv_path = tmp_path / "kpi.csv"
    csv_path.write_text("month,value\nJan,10\n", encoding="utf-8")
    payload = _workbook_payload(csv_path)
    payload["workbook"]["summaries"] = [
        {
            "name": "kpi_summary",
            "source_tab": "kpi_current",
            "provider": "openai",
            "provider_args": {"model": "gpt-4o-mini"},
            "prompt": "Summarize",
            "placement": {
                "type": "summary_tab",
                "tab_name": "summary",
            },
        }
    ]
    config = WorkbookConfig.model_validate(payload)

    fake_provider = _FakeProvider(fail_tab="summary")
    monkeypatch.setattr(
        workbook_builder_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _config: fake_provider),
    )

    class _FakeAIProvider:
        def generate_text(self, prompt: str):
            del prompt
            return "AI summary output"

    monkeypatch.setattr(
        workbook_builder_module,
        "create_ai_provider",
        lambda provider_name, **kwargs: _FakeAIProvider(),
    )

    result = WorkbookBuilder.from_config(config).build()

    assert result.status == "error"
    assert result.tabs_failed == 0
    assert result.summaries_failed == 1
    assert result.summary_results[0].status == "error"
    assert result.summary_results[0].error == "summary write failed"


def test_workbook_builder_history_mode_appends_timestamped_summary(
    tmp_path, monkeypatch
):
    csv_path = tmp_path / "kpi.csv"
    csv_path.write_text("month,value\nJan,10\n", encoding="utf-8")
    payload = _workbook_payload(csv_path)
    payload["workbook"]["summaries"] = [
        {
            "name": "kpi_history_summary",
            "source_tab": "kpi_current",
            "provider": "openai",
            "provider_args": {"model": "gpt-4o-mini"},
            "prompt": "Summarize trend",
            "mode": "history",
            "placement": {
                "type": "same_sheet",
                "tab_name": "kpi_current",
                "anchor_cell": "H2",
            },
        }
    ]
    config = WorkbookConfig.model_validate(payload)

    fake_provider = _FakeProvider()
    fake_provider._cell_text[("kpi_current", "H2")] = "Existing summary block"
    monkeypatch.setattr(
        workbook_builder_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _config: fake_provider),
    )

    class _FakeAIProvider:
        def generate_text(self, prompt: str):
            del prompt
            return "New summary output"

    monkeypatch.setattr(
        workbook_builder_module,
        "create_ai_provider",
        lambda provider_name, **kwargs: _FakeAIProvider(),
    )

    result = WorkbookBuilder.from_config(config).build()

    assert result.status == "success"
    assert result.summaries_succeeded == 1
    assert len(fake_provider.summary_reads) == 1
    write_payload = fake_provider.summary_calls[0]
    assert write_payload["clear_range"] is None
    assert "Existing summary block" in write_payload["text"]
    assert "New summary output" in write_payload["text"]
    assert write_payload["text"].count("\n\n") == 1


def test_workbook_builder_append_source_can_write_summary_to_summary_tab(
    tmp_path, monkeypatch
):
    csv_path = tmp_path / "kpi.csv"
    csv_path.write_text("month,value\nJan,10\nFeb,20\n", encoding="utf-8")
    payload = _workbook_payload(csv_path)
    payload["workbook"]["tabs"][0]["mode"] = "append"
    payload["workbook"]["tabs"][0]["include_header"] = False
    payload["workbook"]["tabs"][0]["idempotency_key"] = "wk_10"
    payload["workbook"]["summaries"] = [
        {
            "name": "append_summary",
            "source_tab": "kpi_current",
            "provider": "openai",
            "provider_args": {},
            "prompt": "Summarize append source",
            "placement": {
                "type": "summary_tab",
                "tab_name": "summary",
            },
        }
    ]
    config = WorkbookConfig.model_validate(payload)

    fake_provider = _FakeProvider()
    monkeypatch.setattr(
        workbook_builder_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _config: fake_provider),
    )

    class _FakeAIProvider:
        def generate_text(self, prompt: str):
            del prompt
            return "Append summary output"

    monkeypatch.setattr(
        workbook_builder_module,
        "create_ai_provider",
        lambda provider_name, **kwargs: _FakeAIProvider(),
    )

    result = WorkbookBuilder.from_config(config).build()

    assert result.status == "success"
    assert result.tabs_succeeded == 1
    assert result.summaries_succeeded == 1
    assert fake_provider.summary_calls[0]["tab_name"] == "summary"
    assert fake_provider.summary_calls[0]["text"] == "Append summary output"


def test_workbook_builder_marks_error_when_same_sheet_anchor_overlaps_data(
    tmp_path, monkeypatch
):
    csv_path = tmp_path / "kpi.csv"
    csv_path.write_text("month,value\nJan,10\nFeb,20\n", encoding="utf-8")
    payload = _workbook_payload(csv_path)
    payload["workbook"]["summaries"] = [
        {
            "name": "anchor_overlap_summary",
            "source_tab": "kpi_current",
            "provider": "openai",
            "provider_args": {},
            "prompt": "Summarize",
            "placement": {
                "type": "same_sheet",
                "tab_name": "kpi_current",
                "anchor_cell": "A2",
            },
        }
    ]
    config = WorkbookConfig.model_validate(payload)

    fake_provider = _FakeProvider()
    monkeypatch.setattr(
        workbook_builder_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _config: fake_provider),
    )
    monkeypatch.setattr(
        workbook_builder_module,
        "create_ai_provider",
        lambda provider_name, **kwargs: (_ for _ in ()).throw(
            AssertionError("AI provider should not run when anchor overlaps tab data")
        ),
    )

    result = WorkbookBuilder.from_config(config).build()

    assert result.status == "error"
    assert result.summaries_failed == 1
    assert "anchor cell overlaps rendered tab data range" in (
        result.summary_results[0].error or ""
    )


def test_workbook_builder_marks_error_when_same_sheet_clear_range_overlaps_data(
    tmp_path, monkeypatch
):
    csv_path = tmp_path / "kpi.csv"
    csv_path.write_text("month,value\nJan,10\nFeb,20\n", encoding="utf-8")
    payload = _workbook_payload(csv_path)
    payload["workbook"]["summaries"] = [
        {
            "name": "range_overlap_summary",
            "source_tab": "kpi_current",
            "provider": "openai",
            "provider_args": {},
            "prompt": "Summarize",
            "placement": {
                "type": "same_sheet",
                "tab_name": "kpi_current",
                "anchor_cell": "H2",
                "clear_range": "B2:B3",
            },
        }
    ]
    config = WorkbookConfig.model_validate(payload)

    fake_provider = _FakeProvider()
    monkeypatch.setattr(
        workbook_builder_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _config: fake_provider),
    )
    monkeypatch.setattr(
        workbook_builder_module,
        "create_ai_provider",
        lambda provider_name, **kwargs: (_ for _ in ()).throw(
            AssertionError("AI provider should not run when clear_range overlaps data")
        ),
    )

    result = WorkbookBuilder.from_config(config).build()

    assert result.status == "error"
    assert result.summaries_failed == 1
    assert "clear_range overlaps rendered tab data range" in (
        result.summary_results[0].error or ""
    )


def test_workbook_builder_marks_error_when_summary_source_tab_has_no_data(
    tmp_path, monkeypatch
):
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
    payload["workbook"]["summaries"] = [
        {
            "name": "failing_tab_summary",
            "source_tab": "failing_tab",
            "provider": "openai",
            "provider_args": {},
            "prompt": "Summarize",
            "placement": {
                "type": "summary_tab",
                "tab_name": "summary",
            },
        }
    ]
    config = WorkbookConfig.model_validate(payload)

    fake_provider = _FakeProvider(fail_tab="failing_tab")
    monkeypatch.setattr(
        workbook_builder_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _config: fake_provider),
    )
    monkeypatch.setattr(
        workbook_builder_module,
        "create_ai_provider",
        lambda provider_name, **kwargs: (_ for _ in ()).throw(
            AssertionError("AI provider should not be created when source tab fails")
        ),
    )

    result = WorkbookBuilder.from_config(config).build()

    assert result.status == "error"
    assert result.tabs_failed == 1
    assert result.summaries_failed == 1
    assert result.summary_results[0].status == "error"
    assert "did not produce data" in (result.summary_results[0].error or "")
