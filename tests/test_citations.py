from __future__ import annotations

from slideflow.citations import (
    CitationEntry,
    CitationRegistry,
    build_repo_file_url,
    canonical_repo_web_url,
    format_citation_line,
    sanitize_repo_url,
)
from slideflow.data.connectors.databricks import DatabricksSourceConfig
from slideflow.data.connectors.dbt import (
    DBTCompiledModelInfo,
    _build_dbt_citation_entries,
)
from slideflow.data.connectors.duckdb import DuckDBSourceConfig


def test_repo_url_helpers_normalize_and_sanitize():
    assert (
        sanitize_repo_url("https://token123@github.com/org/repo.git")
        == "https://github.com/org/repo.git"
    )
    assert canonical_repo_web_url("git@github.com:org/repo.git") == (
        "https://github.com/org/repo"
    )
    assert canonical_repo_web_url("ssh://git@gitlab.com/org/repo.git") == (
        "https://gitlab.com/org/repo"
    )


def test_build_repo_file_url_supports_common_hosts():
    assert (
        build_repo_file_url(
            repo_web_url="https://github.com/org/repo",
            ref="abc123",
            file_path="models/staging/model.sql",
        )
        == "https://github.com/org/repo/blob/abc123/models/staging/model.sql"
    )
    assert (
        build_repo_file_url(
            repo_web_url="https://gitlab.com/org/repo",
            ref="main",
            file_path="models/model.sql",
        )
        == "https://gitlab.com/org/repo/-/blob/main/models/model.sql"
    )


def test_build_repo_file_url_rejects_substring_host_confusion():
    assert (
        build_repo_file_url(
            repo_web_url="https://notgithub.com/org/repo",
            ref="main",
            file_path="models/model.sql",
        )
        is None
    )


def test_citation_registry_dedupes_and_tracks_scope_usage():
    registry = CitationRegistry(max_items=2, dedupe=True)
    one = CitationEntry(
        source_id="src-1",
        provider="duckdb",
        display_name="First",
    )
    two = CitationEntry(
        source_id="src-2",
        provider="duckdb",
        display_name="Second",
    )
    three = CitationEntry(
        source_id="src-3",
        provider="duckdb",
        display_name="Third",
    )

    registry.add(one, scope_id="slide-1")
    registry.add(one, scope_id="slide-1")
    registry.add(two, scope_id="slide-1")
    registry.add(three, scope_id="slide-2")

    summary = registry.summary(enabled=True, total_sources=4)
    assert summary.emitted_sources == 2
    assert summary.truncated is True
    assert summary.citations_by_scope["slide-1"] == ["src-1", "src-2"]
    assert "slide-2" not in summary.citations_by_scope


def test_format_citation_line_prefers_file_url_then_fallback():
    with_file = CitationEntry(
        source_id="src-file",
        provider="csv",
        display_name="CSV File",
        file_url="https://example.com/path/file.sql",
    )
    with_fallback = CitationEntry(
        source_id="src-id",
        provider="csv",
        display_name="CSV Id",
    )
    assert (
        format_citation_line(with_file)
        == "- CSV File: https://example.com/path/file.sql"
    )
    assert format_citation_line(with_fallback) == "- CSV Id: src-id"


def test_query_text_opt_in_for_sql_connectors():
    databricks_source = DatabricksSourceConfig(
        name="sales_dbx",
        type="databricks",
        query="SELECT * FROM sales",
    )
    duckdb_source = DuckDBSourceConfig(
        name="sales_duckdb",
        type="duckdb",
        query="SELECT * FROM sales",
    )

    dbx_without_text = databricks_source.get_citation_entries(
        mode="execution", include_query_text=False
    )[0]
    dbx_with_text = databricks_source.get_citation_entries(
        mode="execution", include_query_text=True
    )[0]
    duck_without_text = duckdb_source.get_citation_entries(
        mode="execution", include_query_text=False
    )[0]
    duck_with_text = duckdb_source.get_citation_entries(
        mode="execution", include_query_text=True
    )[0]

    assert "query_text" not in dbx_without_text.metadata
    assert dbx_with_text.metadata["query_text"] == "SELECT * FROM sales"
    assert "query_text" not in duck_without_text.metadata
    assert duck_with_text.metadata["query_text"] == "SELECT * FROM sales"


def test_dbt_citation_entries_include_query_text_only_when_enabled():
    model_info = DBTCompiledModelInfo(
        sql_text="select * from analytics.orders",
        unique_id="model.pkg.orders",
        alias="orders",
        package_name="pkg",
        model_name="orders",
        compiled_path="target/compiled/orders.sql",
        model_path="models/orders.sql",
        repo_url="https://github.com/org/repo",
        file_url="https://github.com/org/repo/blob/main/models/orders.sql",
        ref="main",
    )

    without_text = _build_dbt_citation_entries(
        source_name="orders_source",
        provider="databricks_dbt",
        mode="execution",
        model_info=model_info,
        include_query_text=False,
    )
    with_text = _build_dbt_citation_entries(
        source_name="orders_source",
        provider="databricks_dbt",
        mode="execution",
        model_info=model_info,
        include_query_text=True,
    )

    assert "query_text" not in without_text[0].metadata
    assert with_text[0].metadata["query_text"] == "select * from analytics.orders"
