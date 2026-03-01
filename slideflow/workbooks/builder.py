"""Builder for workbook pipelines."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal
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
    if isinstance(value, Decimal):
        # Google Sheets API payloads must be JSON serializable scalars.
        return float(value)
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
    # Catch NaN-like scalar sentinels without importing pandas/numpy directly.
    try:
        if value != value:  # noqa: PLR0124
            return None
    except Exception:
        pass
    return value


def dataframe_to_sheet_rows(df: Any, include_header: bool) -> List[List[Any]]:
    """Convert a DataFrame-like object to list-of-rows for Sheets API writes."""
    rows: List[List[Any]] = []
    raw_columns = getattr(df, "columns", None)
    columns = list(raw_columns) if raw_columns is not None else []
    if include_header and columns:
        rows.append([str(column) for column in columns])

    raw_values = getattr(df, "values", None)
    if raw_values is None:
        iterable_rows: List[Any] = []
    elif hasattr(raw_values, "tolist") and callable(getattr(raw_values, "tolist")):
        iterable_rows = list(raw_values.tolist())
    else:
        iterable_rows = list(raw_values)

    for row in iterable_rows:
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


def _column_label_to_index(column_label: str) -> int:
    """Convert an A1 column label (A, Z, AA) to a 1-based index."""
    index = 0
    for char in column_label:
        if char < "A" or char > "Z":
            raise ValueError(f"Invalid A1 column label '{column_label}'")
        index = (index * 26) + (ord(char) - ord("A") + 1)
    return index


def _split_a1_cell(cell_ref: str) -> tuple[str, int]:
    """Split an A1 cell reference into (column_label, row_number)."""
    cell = cell_ref.strip().upper()
    split_index = 0
    while split_index < len(cell) and cell[split_index].isalpha():
        split_index += 1
    if split_index == 0 or split_index >= len(cell):
        raise ValueError(f"Invalid A1 cell reference '{cell_ref}'")
    column_label = cell[:split_index]
    row_text = cell[split_index:]
    if not row_text.isdigit() or row_text.startswith("0"):
        raise ValueError(f"Invalid A1 row index in '{cell_ref}'")
    return column_label, int(row_text)


def _cell_ref_to_indexes(cell_ref: str) -> tuple[int, int]:
    """Convert A1 cell reference into (column_index, row_index)."""
    column_label, row_number = _split_a1_cell(cell_ref)
    return _column_label_to_index(column_label), row_number


def _range_to_bounds(cell_range: str) -> tuple[int, int, int, int]:
    """Convert an A1 range string into (min_col, min_row, max_col, max_row)."""
    start_ref, end_ref = cell_range.split(":", maxsplit=1)
    start_col, start_row = _cell_ref_to_indexes(start_ref)
    end_col, end_row = _cell_ref_to_indexes(end_ref)
    return (
        min(start_col, end_col),
        min(start_row, end_row),
        max(start_col, end_col),
        max(start_row, end_row),
    )


def _rows_to_bounds(
    start_cell: str, rows: List[List[Any]]
) -> tuple[int, int, int, int] | None:
    """Return data bounds for rows written from start_cell, or None when empty."""
    if not rows:
        return None
    max_width = max((len(row) for row in rows), default=0)
    if max_width <= 0:
        return None
    start_col, start_row = _cell_ref_to_indexes(start_cell)
    end_col = start_col + max_width - 1
    end_row = start_row + len(rows) - 1
    return start_col, start_row, end_col, end_row


def _bounds_overlap(
    first_bounds: tuple[int, int, int, int],
    second_bounds: tuple[int, int, int, int],
) -> bool:
    """Return True when two rectangular bounds overlap."""
    first_min_col, first_min_row, first_max_col, first_max_row = first_bounds
    second_min_col, second_min_row, second_max_col, second_max_row = second_bounds
    columns_overlap = (
        first_min_col <= second_max_col and second_min_col <= first_max_col
    )
    rows_overlap = first_min_row <= second_max_row and second_min_row <= first_max_row
    return columns_overlap and rows_overlap


def _cell_in_bounds(cell_ref: str, bounds: tuple[int, int, int, int]) -> bool:
    """Return True when the given A1 cell lies inside bounds."""
    column, row = _cell_ref_to_indexes(cell_ref)
    min_col, min_row, max_col, max_row = bounds
    return min_col <= column <= max_col and min_row <= row <= max_row


def _history_summary_text(existing_text: str | None, generated_summary: str) -> str:
    """Append a timestamped history entry to existing summary content."""
    timestamp = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    entry = f"[{timestamp}] {generated_summary}"
    if existing_text:
        return f"{existing_text}\n\n{entry}"
    return entry


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
        tab_write_bounds: Dict[str, tuple[int, int, int, int]] = {}

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
                bounds = _rows_to_bounds(tab.start_cell, rows)
                tab_dataframes[tab.name] = df
                if tab.mode == "replace" and bounds is not None:
                    tab_write_bounds[tab.name] = bounds
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
            source_bounds = tab_write_bounds.get(summary.source_tab)

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

            if placement.type == "same_sheet" and source_bounds is not None:
                if _cell_in_bounds(target_cell, source_bounds):
                    summary_results.append(
                        WorkbookSummaryResult(
                            name=summary.name,
                            source_tab=summary.source_tab,
                            placement_type=placement.type,
                            target_tab=target_tab,
                            target_cell=target_cell,
                            status="error",
                            error=(
                                "Summary anchor cell overlaps rendered tab data range "
                                f"for tab '{summary.source_tab}'"
                            ),
                        )
                    )
                    continue
                if placement.clear_range:
                    clear_bounds = _range_to_bounds(placement.clear_range)
                    if _bounds_overlap(clear_bounds, source_bounds):
                        summary_results.append(
                            WorkbookSummaryResult(
                                name=summary.name,
                                source_tab=summary.source_tab,
                                placement_type=placement.type,
                                target_tab=target_tab,
                                target_cell=target_cell,
                                status="error",
                                error=(
                                    "Summary clear_range overlaps rendered tab data "
                                    f"range for tab '{summary.source_tab}'"
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
                text_to_write = generated_summary
                clear_range_to_write = placement.clear_range
                if summary.mode == "history":
                    existing_text = self.provider.read_cell_text(
                        workbook_id=workbook_id,
                        tab_name=target_tab,
                        anchor_cell=target_cell,
                    )
                    text_to_write = _history_summary_text(
                        existing_text, generated_summary
                    )
                    clear_range_to_write = None

                self.provider.write_summary_text(
                    workbook_id=workbook_id,
                    tab_name=target_tab,
                    anchor_cell=target_cell,
                    text=text_to_write,
                    clear_range=clear_range_to_write,
                )
                summary_results.append(
                    WorkbookSummaryResult(
                        name=summary.name,
                        source_tab=summary.source_tab,
                        placement_type=placement.type,
                        target_tab=target_tab,
                        target_cell=target_cell,
                        status="success",
                        chars_written=len(text_to_write),
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
