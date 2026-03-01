"""Core result models for workbook build workflows."""

from typing import List, Optional

from pydantic import BaseModel, Field


class WorkbookTabResult(BaseModel):
    """Result for a single workbook tab operation."""

    tab_name: str
    mode: str
    status: str
    rows_written: int = 0
    rows_skipped: int = 0
    run_key: Optional[str] = None
    error: Optional[str] = None


class WorkbookBuildResult(BaseModel):
    """Aggregated workbook build result."""

    workbook_id: str
    workbook_url: str
    status: str
    tab_results: List[WorkbookTabResult] = Field(default_factory=list)

    @property
    def tabs_total(self) -> int:
        return len(self.tab_results)

    @property
    def tabs_succeeded(self) -> int:
        return sum(1 for tab in self.tab_results if tab.status == "success")

    @property
    def tabs_failed(self) -> int:
        return sum(1 for tab in self.tab_results if tab.status == "error")

    @property
    def idempotent_skips(self) -> int:
        return sum(tab.rows_skipped for tab in self.tab_results)
