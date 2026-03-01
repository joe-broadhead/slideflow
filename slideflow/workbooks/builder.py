"""Builder for workbook pipelines."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from slideflow.ai.registry import create_provider as create_ai_provider
from slideflow.utilities.config import ConfigLoader
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.utilities.error_messages import safe_error_line
from slideflow.utilities.logging import get_logger
from slideflow.workbooks.base import (
    WorkbookBuildResult,
    WorkbookSummaryResult,
    WorkbookTabResult,
)
from slideflow.workbooks.config import WorkbookConfig
from slideflow.workbooks.providers.factory import WorkbookProviderFactory

logger = get_logger(__name__)


def _normalize_cell_value(value: Any) -> Any:
    """Convert DataFrame cell values into Google Sheets-compatible scalar values."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return _normalize_cell_value(value.item())
        except Exception:
            return str(value)
    return value


def dataframe_to_sheet_rows(df: Any, include_header: bool) -> List[List[Any]]:
    """Convert a DataFrame-like object to list-of-rows for Sheets API writes."""
    rows: List[List[Any]] = []
    columns = list(getattr(df, "columns", []) or [])
    if include_header and columns:
        rows.append([str(column) for column in columns])

    for row in list(getattr(df, "values", []) or []):
        rows.append([_normalize_cell_value(value) for value in list(row)])

    return rows


def _dataframe_records_for_prompt(df: Any) -> List[Dict[str, Any]]:
    """Convert DataFrame-like data into normalized records for summary prompts."""
    to_dict = getattr(df, "to_dict", None)
    if callable(to_dict):
        try:
            records = to_dict(orient="records")
        except TypeError:
            records = to_dict("records")
        if isinstance(records, list):
            normalized: List[Dict[str, Any]] = []
            for record in records:
                if isinstance(record, dict):
                    normalized.append(
                        {
                            str(key): _normalize_cell_value(value)
                            for key, value in record.items()
                        }
                    )
            return normalized
    return []


class WorkbookBuilder:
    """Build workbook artifacts from validated workbook configuration."""

    def __init__(self, config: WorkbookConfig):
        self.config = config
        self.provider = WorkbookProviderFactory.create_provider(config.provider)
        self._summary_provider_cache: Dict[tuple[str, str], Any] = {}

    @classmethod
    def from_yaml(
        cls,
        yaml_path: Path,
        registry_paths: Optional[List[Path]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> "WorkbookBuilder":
        loader = ConfigLoader(
            yaml_path=yaml_path,
            registry_paths=registry_paths or [],
            params=params or {},
        )
        config = WorkbookConfig.model_validate(loader.config)
        return cls(config)

    @classmethod
    def from_config(cls, config: WorkbookConfig) -> "WorkbookBuilder":
        return cls(config)

    def build(self) -> WorkbookBuildResult:
        workbook_id = self.provider.create_or_open_workbook(self.config.workbook.title)
        tab_results: List[WorkbookTabResult] = []
        summary_results: List[WorkbookSummaryResult] = []
        tab_dataframes: Dict[str, Any] = {}

        for tab in self.config.workbook.tabs:
            try:
                df = tab.data_source.fetch_data()
                df = apply_data_transforms(tab.data_transforms, df)
                run_key = tab.idempotency_key if tab.mode == "append" else None
                if tab.mode == "append":
                    # Avoid duplicate headers on repeated append runs.
                    rows = dataframe_to_sheet_rows(df, include_header=False)
                    rows_written_payload, rows_skipped_payload = (
                        self.provider.write_append_rows(
                            workbook_id=workbook_id,
                            tab_name=tab.name,
                            start_cell=tab.start_cell,
                            rows=rows,
                            run_key=run_key or "",
                        )
                    )
                    data_rows_written = rows_written_payload
                else:
                    rows = dataframe_to_sheet_rows(
                        df, include_header=tab.include_header
                    )
                    rows_written_payload = self.provider.write_replace_rows(
                        workbook_id=workbook_id,
                        tab_name=tab.name,
                        start_cell=tab.start_cell,
                        rows=rows,
                    )
                    rows_skipped_payload = 0
                    data_rows_written = max(
                        0,
                        rows_written_payload
                        - (1 if tab.include_header and rows else 0),
                    )
                tab_dataframes[tab.name] = df
                tab_results.append(
                    WorkbookTabResult(
                        tab_name=tab.name,
                        mode=tab.mode,
                        status="success",
                        rows_written=data_rows_written,
                        rows_skipped=rows_skipped_payload,
                        run_key=run_key,
                    )
                )
            except Exception as error:
                error_message = safe_error_line(error)
                logger.error(
                    "Workbook tab build failed for tab '%s': %s",
                    tab.name,
                    error_message,
                )
                tab_results.append(
                    WorkbookTabResult(
                        tab_name=tab.name,
                        mode=tab.mode,
                        status="error",
                        error=error_message,
                    )
                )

        for summary in self.config.workbook.summaries:
            placement = summary.placement
            target_tab = placement.tab_name or summary.source_tab
            target_cell = placement.anchor_cell or "A1"
            source_df = tab_dataframes.get(summary.source_tab)

            if source_df is None:
                summary_results.append(
                    WorkbookSummaryResult(
                        name=summary.name,
                        source_tab=summary.source_tab,
                        placement_type=placement.type,
                        target_tab=target_tab,
                        target_cell=target_cell,
                        status="error",
                        error=(
                            f"Summary source tab '{summary.source_tab}' did not produce "
                            "data for this run"
                        ),
                    )
                )
                continue

            try:
                records = _dataframe_records_for_prompt(source_df)
                prompt = f"{summary.prompt}\n\nData:\n{records}"
                provider_cache_key = (
                    summary.provider,
                    json.dumps(summary.provider_args, sort_keys=True, default=str),
                )
                if provider_cache_key not in self._summary_provider_cache:
                    self._summary_provider_cache[provider_cache_key] = (
                        create_ai_provider(
                            summary.provider,
                            **summary.provider_args,
                        )
                    )
                summary_provider = self._summary_provider_cache[provider_cache_key]
                generated_summary = str(summary_provider.generate_text(prompt)).strip()

                self.provider.write_summary_text(
                    workbook_id=workbook_id,
                    tab_name=target_tab,
                    anchor_cell=target_cell,
                    text=generated_summary,
                    clear_range=placement.clear_range,
                )
                summary_results.append(
                    WorkbookSummaryResult(
                        name=summary.name,
                        source_tab=summary.source_tab,
                        placement_type=placement.type,
                        target_tab=target_tab,
                        target_cell=target_cell,
                        status="success",
                        chars_written=len(generated_summary),
                    )
                )
            except Exception as error:
                error_message = safe_error_line(error)
                logger.error(
                    "Workbook summary generation failed for summary '%s': %s",
                    summary.name,
                    error_message,
                )
                summary_results.append(
                    WorkbookSummaryResult(
                        name=summary.name,
                        source_tab=summary.source_tab,
                        placement_type=placement.type,
                        target_tab=target_tab,
                        target_cell=target_cell,
                        status="error",
                        error=error_message,
                    )
                )

        self.provider.finalize_workbook(workbook_id)
        workbook_url = self.provider.get_workbook_url(workbook_id)
        status = (
            "error"
            if any(tab.status == "error" for tab in tab_results)
            or any(summary.status == "error" for summary in summary_results)
            else "success"
        )

        return WorkbookBuildResult(
            workbook_id=workbook_id,
            workbook_url=workbook_url,
            status=status,
            tab_results=tab_results,
            summary_results=summary_results,
        )
