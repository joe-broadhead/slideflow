"""Base abstractions for workbook providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Tuple

from pydantic import BaseModel, Field


class WorkbookProviderConfig(BaseModel):
    """Base configuration for workbook providers."""

    provider_type: str = Field(..., description="Workbook provider type")


class WorkbookProvider(ABC):
    """Abstract base class for workbook providers."""

    def __init__(self, config: WorkbookProviderConfig):
        self.config = config

    def run_preflight_checks(self) -> List[Tuple[str, bool, str]]:
        """Return provider-specific health checks."""
        return []

    @abstractmethod
    def create_or_open_workbook(self, title: str) -> str:
        """Create a workbook or return an existing workbook id."""
        raise NotImplementedError

    @abstractmethod
    def write_replace_rows(
        self,
        workbook_id: str,
        tab_name: str,
        start_cell: str,
        rows: List[List[Any]],
    ) -> int:
        """Replace rows in a target tab and return number of rows written."""
        raise NotImplementedError

    @abstractmethod
    def write_append_rows(
        self,
        workbook_id: str,
        tab_name: str,
        start_cell: str,
        rows: List[List[Any]],
        run_key: str,
    ) -> Tuple[int, int]:
        """Append rows with idempotency and return (rows_written, rows_skipped)."""
        raise NotImplementedError

    @abstractmethod
    def write_summary_text(
        self,
        workbook_id: str,
        tab_name: str,
        anchor_cell: str,
        text: str,
        clear_range: str | None = None,
    ) -> None:
        """Write a summary string to a tab/cell, optionally clearing a range first."""
        raise NotImplementedError

    @abstractmethod
    def read_cell_text(
        self,
        workbook_id: str,
        tab_name: str,
        anchor_cell: str,
    ) -> str | None:
        """Read the current text value at a target cell."""
        raise NotImplementedError

    def finalize_workbook(self, workbook_id: str) -> None:
        """Run provider-specific finalize hooks after tab writes."""
        del workbook_id

    @abstractmethod
    def get_workbook_url(self, workbook_id: str) -> str:
        """Return user-facing URL for the workbook."""
        raise NotImplementedError
