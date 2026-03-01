"""Workbook configuration models for sheet generation workflows."""

import re
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from slideflow.data.connectors import DataSourceConfig

RESERVED_METADATA_TAB = "_slideflow_meta"
_CELL_REF_PATTERN = re.compile(r"^[A-Z]+[1-9][0-9]*$")
_CELL_RANGE_PATTERN = re.compile(r"^[A-Z]+[1-9][0-9]*:[A-Z]+[1-9][0-9]*$")


def _normalize_cell_reference(value: str) -> str:
    cell = value.strip().upper()
    if not _CELL_REF_PATTERN.fullmatch(cell):
        raise ValueError(
            f"Invalid cell reference '{value}'. Expected A1 notation like 'A1'."
        )
    return cell


def _normalize_cell_range(value: str) -> str:
    cell_range = value.strip().upper()
    if not _CELL_RANGE_PATTERN.fullmatch(cell_range):
        raise ValueError(
            f"Invalid cell range '{value}'. Expected A1 range notation like 'A1:B10'."
        )
    return cell_range


def _column_index(column_name: str) -> int:
    index = 0
    for char in column_name:
        index = (index * 26) + (ord(char) - ord("A") + 1)
    return index


def _cell_to_indexes(cell_ref: str) -> tuple[int, int]:
    match = re.fullmatch(r"(?P<column>[A-Z]+)(?P<row>[1-9][0-9]*)", cell_ref)
    if match is None:
        raise ValueError(f"Invalid cell reference '{cell_ref}'")
    column = _column_index(match.group("column"))
    row = int(match.group("row"))
    return column, row


def _range_contains_cell(cell_range: str, cell_ref: str) -> bool:
    start_ref, end_ref = cell_range.split(":", maxsplit=1)
    start_column, start_row = _cell_to_indexes(start_ref)
    end_column, end_row = _cell_to_indexes(end_ref)
    column, row = _cell_to_indexes(cell_ref)
    min_column, max_column = sorted((start_column, end_column))
    min_row, max_row = sorted((start_row, end_row))
    return min_column <= column <= max_column and min_row <= row <= max_row


class WorkbookProviderConfig(BaseModel):
    """Provider selector for workbook outputs."""

    model_config = ConfigDict(extra="forbid")

    type: Annotated[
        Literal["google_sheets"],
        Field(..., description="Workbook provider type"),
    ]
    config: Annotated[
        Dict[str, Any],
        Field(default_factory=dict, description="Provider-specific options"),
    ]


class WorkbookTabSpec(BaseModel):
    """Tab-level workbook write configuration."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(..., description="Tab name")]
    mode: Annotated[
        Literal["replace", "append"],
        Field(default="replace", description="Write mode for this tab"),
    ]
    start_cell: Annotated[
        str,
        Field(default="A1", description="Top-left anchor for writes in A1 notation"),
    ]
    include_header: Annotated[
        bool,
        Field(default=True, description="Whether to include header row in output"),
    ]
    data_source: Annotated[
        DataSourceConfig,
        Field(..., description="Data source configuration"),
    ]
    data_transforms: Annotated[
        List[Dict[str, Any]],
        Field(default_factory=list, description="Optional transform pipeline"),
    ]
    idempotency_key: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Template key for append dedupe; required for append mode",
        ),
    ]

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("workbook.tabs[].name cannot be empty")
        if normalized == RESERVED_METADATA_TAB:
            raise ValueError(
                f"workbook.tabs[].name cannot use reserved tab name '{RESERVED_METADATA_TAB}'"
            )
        return normalized

    @field_validator("start_cell")
    @classmethod
    def _validate_start_cell(cls, value: str) -> str:
        return _normalize_cell_reference(value)

    @field_validator("idempotency_key")
    @classmethod
    def _normalize_idempotency_key(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_append_requires_idempotency(self):
        if self.mode == "append" and not self.idempotency_key:
            raise ValueError(
                "workbook.tabs[].idempotency_key is required when mode='append'"
            )
        if self.mode == "append" and self.include_header:
            raise ValueError(
                "workbook.tabs[].include_header must be false when mode='append'"
            )
        return self


class WorkbookSummaryPlacement(BaseModel):
    """Placement configuration for workbook summaries."""

    model_config = ConfigDict(extra="forbid")

    type: Annotated[
        Literal["same_sheet", "summary_tab"],
        Field(..., description="Summary destination strategy"),
    ]
    tab_name: Annotated[
        Optional[str],
        Field(default=None, description="Target tab name for summary output"),
    ]
    anchor_cell: Annotated[
        Optional[str],
        Field(default=None, description="Target cell anchor for summary output"),
    ]
    clear_range: Annotated[
        Optional[str],
        Field(
            default=None, description="Optional range to clear before writing summary"
        ),
    ]

    @field_validator("tab_name")
    @classmethod
    def _normalize_tab_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("anchor_cell")
    @classmethod
    def _normalize_anchor_cell(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_cell_reference(value)

    @field_validator("clear_range")
    @classmethod
    def _normalize_clear_range(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_cell_range(value)

    @model_validator(mode="after")
    def _validate_required_fields(self):
        if self.type == "same_sheet":
            if not self.tab_name:
                raise ValueError(
                    "workbook.summaries[].placement.tab_name is required when "
                    "placement.type='same_sheet'"
                )
            if not self.anchor_cell:
                raise ValueError(
                    "workbook.summaries[].placement.anchor_cell is required when "
                    "placement.type='same_sheet'"
                )
        if self.type == "summary_tab" and not self.tab_name:
            raise ValueError(
                "workbook.summaries[].placement.tab_name is required when "
                "placement.type='summary_tab'"
            )
        return self


class WorkbookSummarySpec(BaseModel):
    """Summary generation configuration for workbook tabs."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(..., description="Summary name")]
    source_tab: Annotated[str, Field(..., description="Tab supplying summary data")]
    provider: Annotated[str, Field(..., description="AI provider identifier")]
    provider_args: Annotated[
        Dict[str, Any],
        Field(default_factory=dict, description="Provider-specific args"),
    ]
    prompt: Annotated[str, Field(..., description="Summary generation prompt")]
    placement: Annotated[
        WorkbookSummaryPlacement,
        Field(..., description="Summary placement configuration"),
    ]
    mode: Annotated[
        Literal["latest", "history"],
        Field(default="latest", description="Summary write behavior"),
    ]

    @field_validator("name", "source_tab", "provider", "prompt")
    @classmethod
    def _normalize_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Summary string fields cannot be empty")
        return normalized


class WorkbookSpec(BaseModel):
    """Workbook-level configuration."""

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(..., description="Workbook title")]
    tabs: Annotated[
        List[WorkbookTabSpec],
        Field(..., min_length=1, description="Workbook tab write definitions"),
    ]
    summaries: Annotated[
        List[WorkbookSummarySpec],
        Field(default_factory=list, description="Optional summary definitions"),
    ]

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("workbook.title cannot be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_cross_references(self):
        tab_by_name: Dict[str, WorkbookTabSpec] = {}
        duplicate_tab_names = set()
        for tab in self.tabs:
            if tab.name in tab_by_name:
                duplicate_tab_names.add(tab.name)
            tab_by_name[tab.name] = tab

        if duplicate_tab_names:
            raise ValueError(
                "workbook.tabs[].name values must be unique; duplicates: "
                + ", ".join(sorted(duplicate_tab_names))
            )

        for summary in self.summaries:
            if summary.source_tab not in tab_by_name:
                raise ValueError(
                    "workbook.summaries[].source_tab must reference an existing tab; "
                    f"got '{summary.source_tab}'"
                )

            placement = summary.placement
            target_tab = placement.tab_name
            if target_tab == RESERVED_METADATA_TAB:
                raise ValueError(
                    f"workbook.summaries[].placement.tab_name cannot use reserved tab "
                    f"name '{RESERVED_METADATA_TAB}'"
                )

            if placement.type == "same_sheet":
                if target_tab != summary.source_tab:
                    raise ValueError(
                        "workbook.summaries[].placement.tab_name must match "
                        "source_tab when placement.type='same_sheet'"
                    )

                source_tab = tab_by_name[summary.source_tab]
                if placement.anchor_cell == source_tab.start_cell:
                    raise ValueError(
                        "Summary anchor cell cannot overlap the tab data start_cell"
                    )
                if placement.clear_range and _range_contains_cell(
                    placement.clear_range,
                    source_tab.start_cell,
                ):
                    raise ValueError(
                        "Summary clear_range cannot include the tab data start_cell"
                    )

        return self


class WorkbookConfig(BaseModel):
    """Root workbook pipeline configuration."""

    model_config = ConfigDict(extra="forbid")

    provider: Annotated[
        WorkbookProviderConfig,
        Field(..., description="Workbook provider configuration"),
    ]
    workbook: Annotated[
        WorkbookSpec,
        Field(..., description="Workbook artifact configuration"),
    ]
    registry: Annotated[
        Optional[List[str]],
        Field(None, description="Paths to custom function registry files"),
    ]

    @field_validator("registry", mode="before")
    @classmethod
    def _normalize_registry(cls, value: Any) -> Optional[List[str]]:
        if value is None:
            return None
        if isinstance(value, (str, Path)):
            return [str(value)]
        if isinstance(value, list):
            return [str(path) for path in value]
        return value
