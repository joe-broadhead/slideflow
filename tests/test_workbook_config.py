from copy import deepcopy

import pytest
from pydantic import ValidationError

from slideflow.workbooks.config import WorkbookConfig


def _base_workbook_config():
    return {
        "provider": {"type": "google_sheets", "config": {}},
        "workbook": {
            "title": "Weekly KPI Snapshot",
            "tabs": [
                {
                    "name": "kpi_current",
                    "mode": "replace",
                    "data_source": {
                        "type": "csv",
                        "name": "kpi_source",
                        "file_path": "kpi.csv",
                    },
                }
            ],
        },
    }


def _add_tab_local_summary(
    payload: dict,
    *,
    tab_name: str = "kpi_current",
    summary_name: str = "kpi_summary",
    mode: str = "latest",
    placement_type: str = "same_sheet",
    target_tab: str | None = "kpi_current",
    anchor_cell: str | None = "H2",
    clear_range: str | None = None,
):
    tabs = payload["workbook"]["tabs"]
    tab = next(item for item in tabs if item["name"] == tab_name)
    placement: dict = {"type": placement_type}
    if target_tab is not None:
        placement["target_tab"] = target_tab
    if anchor_cell is not None:
        placement["anchor_cell"] = anchor_cell
    if clear_range is not None:
        placement["clear_range"] = clear_range

    tab["ai"] = {
        "summaries": [
            {
                "type": "ai_text",
                "config": {
                    "name": summary_name,
                    "provider": "openai",
                    "provider_args": {"model": "gpt-4o-mini"},
                    "prompt": "Summarize weekly changes",
                    "mode": mode,
                    "placement": placement,
                },
            }
        ]
    }


def test_workbook_config_accepts_minimal_valid_payload():
    parsed = WorkbookConfig.model_validate(_base_workbook_config())

    assert parsed.provider.type == "google_sheets"
    assert parsed.workbook.tabs[0].start_cell == "A1"
    assert parsed.workbook.tabs[0].mode == "replace"


def test_workbook_config_append_mode_requires_idempotency_key():
    payload = _base_workbook_config()
    payload["workbook"]["tabs"][0]["mode"] = "append"
    payload["workbook"]["tabs"][0]["include_header"] = False

    with pytest.raises(ValidationError, match="idempotency_key"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_append_mode_rejects_include_header_true():
    payload = _base_workbook_config()
    payload["workbook"]["tabs"][0]["mode"] = "append"
    payload["workbook"]["tabs"][0]["idempotency_key"] = "wk_1"
    payload["workbook"]["tabs"][0]["include_header"] = True

    with pytest.raises(ValidationError, match="include_header"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_requires_unique_tab_names():
    payload = _base_workbook_config()
    payload["workbook"]["tabs"].append(deepcopy(payload["workbook"]["tabs"][0]))

    with pytest.raises(ValidationError, match="must be unique"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_same_sheet_summary_target_mismatch():
    payload = _base_workbook_config()
    _add_tab_local_summary(payload, placement_type="same_sheet", target_tab="other_tab")

    with pytest.raises(ValidationError, match="must match source tab"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_summary_tab_without_target_tab():
    payload = _base_workbook_config()
    _add_tab_local_summary(
        payload,
        placement_type="summary_tab",
        target_tab=None,
        anchor_cell=None,
    )

    with pytest.raises(
        ValidationError,
        match="target_tab is required when placement.type='summary_tab'",
    ):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_same_sheet_summary_range_overlap():
    payload = _base_workbook_config()
    _add_tab_local_summary(
        payload,
        placement_type="same_sheet",
        target_tab="kpi_current",
        anchor_cell="H2",
        clear_range="A1:A10",
    )

    with pytest.raises(ValidationError, match="clear_range cannot include"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_history_mode_with_clear_range():
    payload = _base_workbook_config()
    _add_tab_local_summary(
        payload,
        summary_name="kpi_summary_history",
        mode="history",
        placement_type="same_sheet",
        target_tab="kpi_current",
        anchor_cell="H2",
        clear_range="H2:H20",
    )

    with pytest.raises(ValidationError, match="not allowed when mode='history'"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_same_sheet_summary_for_append_mode_source():
    payload = _base_workbook_config()
    payload["workbook"]["tabs"][0]["mode"] = "append"
    payload["workbook"]["tabs"][0]["include_header"] = False
    payload["workbook"]["tabs"][0]["idempotency_key"] = "wk_1"
    _add_tab_local_summary(
        payload,
        summary_name="append_same_sheet_summary",
        placement_type="same_sheet",
        target_tab="kpi_current",
        anchor_cell="H2",
    )

    with pytest.raises(ValidationError, match="not supported for append-mode"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_reserved_tab_name():
    payload = _base_workbook_config()
    payload["workbook"]["tabs"][0]["name"] = "_slideflow_meta"

    with pytest.raises(ValidationError, match="reserved tab name"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_removed_workbook_summaries():
    payload = _base_workbook_config()
    payload["workbook"]["summaries"] = []

    with pytest.raises(ValidationError, match="workbook.summaries is removed"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_removed_placement_tab_name():
    payload = _base_workbook_config()
    tab = payload["workbook"]["tabs"][0]
    tab["ai"] = {
        "summaries": [
            {
                "type": "ai_text",
                "config": {
                    "name": "kpi_summary",
                    "provider": "openai",
                    "provider_args": {},
                    "prompt": "Summarize",
                    "placement": {
                        "type": "same_sheet",
                        "tab_name": "kpi_current",
                        "anchor_cell": "H2",
                    },
                },
            }
        ]
    }

    with pytest.raises(ValidationError, match="placement.tab_name is removed"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_duplicate_summary_names_across_tabs():
    payload = _base_workbook_config()
    payload["workbook"]["tabs"].append(
        {
            "name": "kpi_secondary",
            "mode": "replace",
            "data_source": {
                "type": "csv",
                "name": "kpi_source_secondary",
                "file_path": "kpi_2.csv",
            },
        }
    )
    _add_tab_local_summary(
        payload, tab_name="kpi_current", summary_name="duplicate_name"
    )
    _add_tab_local_summary(
        payload,
        tab_name="kpi_secondary",
        summary_name="duplicate_name",
        target_tab="kpi_secondary",
    )

    with pytest.raises(ValidationError, match="Summary names must be unique"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_non_ai_text_summary_type():
    payload = _base_workbook_config()
    payload["workbook"]["tabs"][0]["ai"] = {
        "summaries": [
            {
                "type": "text",
                "config": {
                    "name": "kpi_summary",
                    "provider": "openai",
                    "provider_args": {},
                    "prompt": "Summarize",
                    "placement": {"type": "same_sheet", "anchor_cell": "H2"},
                },
            }
        ]
    }

    with pytest.raises(ValidationError, match="ai_text"):
        WorkbookConfig.model_validate(payload)
