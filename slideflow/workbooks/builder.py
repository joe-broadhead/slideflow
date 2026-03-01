"""Builder for workbook pipelines."""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from slideflow.utilities.config import ConfigLoader
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.utilities.error_messages import safe_error_line
from slideflow.utilities.logging import get_logger
from slideflow.workbooks.base import WorkbookBuildResult, WorkbookTabResult
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


class WorkbookBuilder:
    """Build workbook artifacts from validated workbook configuration."""

    def __init__(self, config: WorkbookConfig):
        self.config = config
        self.provider = WorkbookProviderFactory.create_provider(config.provider)

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

        for tab in self.config.workbook.tabs:
            try:
                df = tab.data_source.fetch_data()
                df = apply_data_transforms(tab.data_transforms, df)
                rows = dataframe_to_sheet_rows(df, include_header=tab.include_header)
                rows_written_payload = self.provider.write_replace_rows(
                    workbook_id=workbook_id,
                    tab_name=tab.name,
                    start_cell=tab.start_cell,
                    rows=rows,
                )
                data_rows_written = max(
                    0,
                    rows_written_payload - (1 if tab.include_header and rows else 0),
                )
                tab_results.append(
                    WorkbookTabResult(
                        tab_name=tab.name,
                        mode=tab.mode,
                        status="success",
                        rows_written=data_rows_written,
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

        self.provider.finalize_workbook(workbook_id)
        workbook_url = self.provider.get_workbook_url(workbook_id)
        status = (
            "error" if any(tab.status == "error" for tab in tab_results) else "success"
        )

        return WorkbookBuildResult(
            workbook_id=workbook_id,
            workbook_url=workbook_url,
            status=status,
            tab_results=tab_results,
        )
