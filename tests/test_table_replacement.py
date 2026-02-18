import pytest
from pydantic import ValidationError

from slideflow.replacements.table import TableFormattingOptions, TableReplacement


def test_table_replacement_requires_data_source_or_static_replacements():
    with pytest.raises(ValidationError):
        TableReplacement(type="table", prefix="MISSING_")


def test_table_replacement_runtime_guard_when_validation_is_bypassed():
    replacement = TableReplacement.model_construct(
        type="table",
        prefix="BYPASS_",
        data_source=None,
        replacements=None,
        formatting=TableFormattingOptions(),
        data_transforms=None,
    )

    with pytest.raises(ValueError, match="no data"):
        replacement.get_replacement()


def test_table_replacement_returns_static_mapping_unchanged():
    mapping = {"{{STATUS_CURRENT}}": "Active", "{{STATUS_COUNT}}": "42"}
    replacement = TableReplacement(type="table", prefix="STATUS_", replacements=mapping)

    assert replacement.get_replacement() == mapping
