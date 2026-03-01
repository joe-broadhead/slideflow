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
            "summaries": [],
        },
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


def test_workbook_config_rejects_same_sheet_summary_tab_mismatch():
    payload = _base_workbook_config()
    payload["workbook"]["summaries"] = [
        {
            "name": "kpi_summary",
            "source_tab": "kpi_current",
            "provider": "openai",
            "prompt": "Summarize weekly changes",
            "placement": {
                "type": "same_sheet",
                "tab_name": "other_tab",
                "anchor_cell": "H2",
            },
        }
    ]

    with pytest.raises(ValidationError, match="must match source_tab"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_same_sheet_summary_range_overlap():
    payload = _base_workbook_config()
    payload["workbook"]["summaries"] = [
        {
            "name": "kpi_summary",
            "source_tab": "kpi_current",
            "provider": "openai",
            "prompt": "Summarize weekly changes",
            "placement": {
                "type": "same_sheet",
                "tab_name": "kpi_current",
                "anchor_cell": "H2",
                "clear_range": "A1:A10",
            },
        }
    ]

    with pytest.raises(ValidationError, match="clear_range cannot include"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_history_mode_with_clear_range():
    payload = _base_workbook_config()
    payload["workbook"]["summaries"] = [
        {
            "name": "kpi_summary_history",
            "source_tab": "kpi_current",
            "provider": "openai",
            "prompt": "Summarize weekly changes",
            "mode": "history",
            "placement": {
                "type": "same_sheet",
                "tab_name": "kpi_current",
                "anchor_cell": "H2",
                "clear_range": "H2:H20",
            },
        }
    ]

    with pytest.raises(ValidationError, match="not allowed when mode='history'"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_same_sheet_summary_for_append_mode_source():
    payload = _base_workbook_config()
    payload["workbook"]["tabs"][0]["mode"] = "append"
    payload["workbook"]["tabs"][0]["include_header"] = False
    payload["workbook"]["tabs"][0]["idempotency_key"] = "wk_1"
    payload["workbook"]["summaries"] = [
        {
            "name": "append_same_sheet_summary",
            "source_tab": "kpi_current",
            "provider": "openai",
            "prompt": "Summarize append data",
            "placement": {
                "type": "same_sheet",
                "tab_name": "kpi_current",
                "anchor_cell": "H2",
            },
        }
    ]

    with pytest.raises(ValidationError, match="not supported for append-mode"):
        WorkbookConfig.model_validate(payload)


def test_workbook_config_rejects_reserved_tab_name():
    payload = _base_workbook_config()
    payload["workbook"]["tabs"][0]["name"] = "_slideflow_meta"

    with pytest.raises(ValidationError, match="reserved tab name"):
        WorkbookConfig.model_validate(payload)
