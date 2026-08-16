import builtins
import json
import multiprocessing
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

import slideflow.data.connectors.dbt as dbt_module
from slideflow.data.cache import get_data_cache
from slideflow.utilities.exceptions import DataSourceError


def _reset_dbt_caches() -> None:
    dbt_module._prepared_workspaces_cache.clear()
    dbt_module._prepared_workspaces_last_access.clear()
    dbt_module._prepared_workspace_generations.clear()
    dbt_module._workspace_preparation_inflight.clear()
    dbt_module._prepared_workspaces_in_use.clear()
    dbt_module._pending_workspace_cleanup_dirs.clear()
    dbt_module._compiled_projects_cache.clear()
    dbt_module._compiled_projects_last_access.clear()
    dbt_module._compiled_project_generations.clear()
    dbt_module._compilation_inflight.clear()
    dbt_module._compilation_failures.clear()
    dbt_module._compiled_projects_in_use.clear()
    dbt_module._pending_cleanup_dirs.clear()
    dbt_module._cleanup_in_progress_dirs.clear()
    dbt_module._cleanup_failures.clear()
    dbt_module._workspace_file_locks.clear()
    dbt_module._manifest_index_cache.clear()
    dbt_module._manifest_index_inflight.clear()
    dbt_module._compiled_project_coverage.clear()
    dbt_module._selection_locks.clear()


@pytest.fixture(autouse=True)
def _stable_fake_checkout_revision(monkeypatch):
    """Keep unit-test clones lightweight while production requires real Git."""
    monkeypatch.setattr(
        dbt_module, "_resolve_checkout_revision", lambda _clone_dir: "test-revision"
    )


def _write_fake_dbt_project(clone_dir: Path) -> None:
    clone_dir.mkdir(parents=True, exist_ok=True)
    (clone_dir / "dbt_project.yml").write_text("name: test_project\nversion: 1.0\n")


def _hold_workspace_process_lock(
    workspace: str,
    acquired: Any,
    release: Any,
) -> None:
    clone_dir = dbt_module._resolve_managed_clone_dir(
        workspace,
        "https://github.com/org/repo.git",
        "main",
    )
    with dbt_module._workspace_process_lock(clone_dir):
        acquired.set()
        release.wait(10)


def _enter_workspace_process_lock(workspace: str, entered: Any) -> None:
    clone_dir = dbt_module._resolve_managed_clone_dir(
        workspace,
        "https://github.com/org/repo.git",
        "main",
    )
    with dbt_module._workspace_process_lock(clone_dir):
        entered.set()


def _copy_seeded_target_to_invocation(args: list[str]) -> None:
    """Make no-op dbt runners materialize fake-clone artifacts per target path."""
    if "--target-path" not in args or "--project-dir" not in args:
        return
    source = Path(args[args.index("--project-dir") + 1]) / "target"
    destination = Path(args[args.index("--target-path") + 1])
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def _write_compiled_dbt_project(
    project_dir: Path,
    *,
    alias: str = "metrics_model",
    compiled_path: str = "target/compiled.sql",
    sql: str = "select 1 as answer",
) -> None:
    _write_fake_dbt_project(project_dir)
    compiled_file = project_dir / compiled_path
    compiled_file.parent.mkdir(parents=True, exist_ok=True)
    compiled_file.write_text(sql)
    manifest = {
        "nodes": {
            "model.project.metrics": {
                "resource_type": "model",
                "alias": alias,
                "compiled_path": compiled_path,
                "original_file_path": "models/metrics.sql",
                "package_name": "project",
                "name": "metrics",
            }
        }
    }
    (project_dir / "target").mkdir(parents=True, exist_ok=True)
    (project_dir / "target" / "manifest.json").write_text(json.dumps(manifest))


def test_prepare_models_batches_exact_sorted_selectors(monkeypatch, tmp_path):
    _reset_dbt_caches()
    invocations = []

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "target" / "compiled").mkdir(parents=True, exist_ok=True)
        for name in ("model_a", "model_b"):
            (clone_dir / "target" / "compiled" / f"{name}.sql").write_text(
                f"select '{name}'"
            )
        manifest = {
            "nodes": {
                f"model.analytics.{name}": {
                    "resource_type": "model",
                    "alias": f"alias_{name}",
                    "package_name": "analytics",
                    "name": name,
                    "compiled_path": f"target/compiled/{name}.sql",
                }
                for name in ("model_a", "model_b")
            }
        }
        (clone_dir / "target" / "manifest.json").write_text(json.dumps(manifest))

    class _Runner:
        def invoke(self, args):
            invocations.append(list(args))
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
    )

    connector.prepare_models(
        [
            ("alias_model_b", None, None, None),
            ("alias_model_a", None, None, None),
            ("alias_model_a", None, None, None),
        ]
    )
    assert [args[0] for args in invocations] == ["deps", "parse", "compile"]
    compile_args = invocations[-1]
    assert compile_args[compile_args.index("--select") + 1] == (
        "analytics.model_a analytics.model_b"
    )

    assert connector.get_compiled_query("alias_model_a") == "select 'model_a'"
    assert connector.get_compiled_query("alias_model_b") == "select 'model_b'"
    assert [args[0] for args in invocations].count("compile") == 1


@pytest.mark.integration
def test_scoped_compile_ignores_unrelated_execute_time_failure(tmp_path):
    try:
        version("dbt-core")
        version("dbt-duckdb")
        version("gitpython")
    except PackageNotFoundError:
        pytest.skip("dbt and GitPython integration extras are not installed")

    repo_dir = tmp_path / "source_repo"
    models_dir = repo_dir / "models"
    models_dir.mkdir(parents=True)
    (repo_dir / "dbt_project.yml").write_text(
        "name: analytics\nversion: '1.0'\nconfig-version: 2\n"
        "profile: analytics\nmodel-paths: ['models']\n",
        encoding="utf-8",
    )
    (repo_dir / "profiles.yml").write_text(
        "analytics:\n  target: dev\n  outputs:\n    dev:\n"
        f"      type: duckdb\n      path: {tmp_path / 'warehouse.duckdb'}\n"
        "      threads: 1\n",
        encoding="utf-8",
    )
    (models_dir / "ephemeral_parent.sql").write_text(
        "{{ config(materialized='ephemeral') }} select 1 as value\n",
        encoding="utf-8",
    )
    (models_dir / "model_a.sql").write_text(
        "{{ config(alias='alias_a') }} select * from {{ ref('ephemeral_parent') }}\n",
        encoding="utf-8",
    )
    (models_dir / "model_b.sql").write_text(
        "{{ config(alias='alias_b') }} select 2 as value\n",
        encoding="utf-8",
    )
    (models_dir / "unrelated.sql").write_text(
        "{% if execute %}{{ exceptions.raise_compiler_error('unrelated failure') }}"
        "{% endif %} select 3 as value\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", "Slideflow Tests"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "fixture"],
        check=True,
        capture_output=True,
    )

    script = f"""
from slideflow.data.connectors.dbt import DBTManifestConnector
connector = DBTManifestConnector(
    package_url={str(repo_dir)!r},
    project_dir={str(tmp_path / "workspace")!r},
    target='dev',
)
connector.prepare_models([
    ('alias_a', None, None, None),
    ('alias_b', None, None, None),
])
print(connector.get_compiled_query('alias_a'))
print(connector.get_compiled_query('alias_b'))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "select" in result.stdout.lower()
    assert "select 2" in result.stdout.lower()


@pytest.mark.integration
def test_multi_source_vars_share_workspace_and_isolate_artifacts(tmp_path):
    try:
        version("dbt-core")
        version("dbt-duckdb")
        version("gitpython")
    except PackageNotFoundError:
        pytest.skip("dbt and GitPython integration extras are not installed")

    repo_dir = tmp_path / "source_repo"
    models_dir = repo_dir
    models_dir.mkdir(parents=True)
    (repo_dir / "dbt_project.yml").write_text(
        "name: analytics\nversion: '1.0'\nconfig-version: 2\n"
        "profile: analytics\nmodel-paths: ['.']\n",
        encoding="utf-8",
    )
    (repo_dir / "profiles.yml").write_text(
        "analytics:\n  target: dev\n  outputs:\n    dev:\n"
        f"      type: duckdb\n      path: {tmp_path / 'warehouse.duckdb'}\n"
        "      threads: 1\n",
        encoding="utf-8",
    )
    for suffix in ("a", "b"):
        (models_dir / f"model_{suffix}.sql").write_text(
            "{{ config(alias='alias_" + suffix + "') }} "
            "select '{{ var(\"region\") }}' as region, '" + suffix + "' as analysis\n",
            encoding="utf-8",
        )
    subprocess.run(["git", "init", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", "Slideflow Tests"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "fixture"],
        check=True,
        capture_output=True,
    )

    workspace = tmp_path / "workspace"
    script = f"""
import json
from pathlib import Path
from slideflow.data.connectors.dbt import DBTManifestConnector

workspace = Path({str(workspace)!r})
connectors = {{
    region: DBTManifestConnector(
        package_url={str(repo_dir)!r},
        project_dir=str(workspace),
        target='dev',
        vars={{'region': region}},
    )
    for region in ('US', 'CA')
}}
requests = [
    ('alias_a', None, None, None),
    ('alias_b', None, None, None),
    ('alias_a', None, None, None),
]
for connector in connectors.values():
    connector.prepare_models(requests)
payload = {{
    region: [
        connector.get_compiled_query('alias_a'),
        connector.get_compiled_query('alias_b'),
    ]
    for region, connector in connectors.items()
}}
clones = list((workspace / '.slideflow_dbt_clones').iterdir())
payload['clone_count'] = len(clones)
variant_roots = list((workspace / '.slideflow_dbt_targets').iterdir())
payload['variant_count'] = len(list(variant_roots[0].iterdir()))
payload['artifacts_outside_clone'] = not variant_roots[0].is_relative_to(clones[0])
print(json.dumps(payload))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["clone_count"] == 1
    assert payload["variant_count"] == 2
    assert payload["artifacts_outside_clone"] is True
    assert all("'US' as region" in sql for sql in payload["US"])
    assert all("'CA' as region" in sql for sql in payload["CA"])
    assert "'a' as analysis" in payload["US"][0]
    assert "'b' as analysis" in payload["US"][1]


def test_sanitize_git_url_redacts_embedded_credentials():
    url = "https://mytoken@github.com/org/repo.git"
    redacted = dbt_module._sanitize_git_url(url)

    assert redacted == "https://***@github.com/org/repo.git"


def test_require_dbt_runner_class_raises_without_optional_dependency(monkeypatch):
    monkeypatch.setattr(dbt_module, "dbtRunner", None)

    with pytest.raises(DataSourceError, match=r"slideflow-presentations\[dbt\]"):
        dbt_module._require_dbt_runner_class()


def test_require_repo_class_raises_without_optional_dependency(monkeypatch):
    monkeypatch.setattr(dbt_module, "Repo", None)

    with pytest.raises(DataSourceError, match=r"slideflow-presentations\[dbt\]"):
        dbt_module._require_repo_class()


def test_clone_repo_error_message_redacts_token_value(monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_PAT", "secret-token-123")

    def _raise_clone(url, _clone_dir, **kwargs):
        raise RuntimeError(f"clone failed for {url}")

    monkeypatch.setattr(dbt_module.Repo, "clone_from", staticmethod(_raise_clone))

    with pytest.raises(DataSourceError) as exc_info:
        dbt_module._clone_repo(
            "https://$GIT_PAT@github.com/org/repo.git",
            tmp_path / "repo",
            branch=None,
        )

    message = str(exc_info.value)
    assert "secret-token-123" not in message
    assert "https://***@github.com/org/repo.git" in message


def test_compile_false_uses_existing_compiled_project_without_clone_or_dbt(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    project_dir = tmp_path / "compiled_project"
    _write_compiled_dbt_project(project_dir, sql="select 42 as answer")

    def _unexpected_clone(*_args, **_kwargs):
        raise AssertionError("compile:false must not clone repositories")

    class _UnexpectedRunner:
        def __init__(self):
            raise AssertionError("compile:false must not create dbtRunner")

    monkeypatch.setattr(dbt_module, "_clone_repo", _unexpected_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _UnexpectedRunner)

    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(project_dir),
        branch="main",
        target="prod",
        compile=False,
    )

    assert connector.get_compiled_query("metrics_model") == "select 42 as answer"


def test_compile_false_requires_existing_manifest(tmp_path):
    _reset_dbt_caches()
    project_dir = tmp_path / "missing_manifest"

    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(project_dir),
        target="prod",
        compile=False,
    )

    with pytest.raises(DataSourceError, match=r"compile:false requires.*manifest"):
        connector.get_compiled_query("metrics_model")


def test_compile_false_requires_manifest_compiled_file(tmp_path):
    _reset_dbt_caches()
    project_dir = tmp_path / "missing_compiled_file"
    (project_dir / "target").mkdir(parents=True)
    manifest = {
        "nodes": {
            "model.project.metrics": {
                "resource_type": "model",
                "alias": "metrics_model",
                "compiled_path": "target/missing.sql",
            }
        }
    }
    (project_dir / "target" / "manifest.json").write_text(json.dumps(manifest))

    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(project_dir),
        target="prod",
        compile=False,
    )

    with pytest.raises(DataSourceError, match=r"compile:false requires compiled SQL"):
        connector.get_compiled_query("metrics_model")


def test_resolve_managed_clone_dir_rejects_protected_roots():
    with pytest.raises(DataSourceError, match="protected project_dir"):
        dbt_module._resolve_managed_clone_dir(
            project_dir="/",
            package_url="https://github.com/org/repo.git",
            branch=None,
        )


def test_resolve_managed_clone_dir_uses_managed_workspace(tmp_path):
    clone_dir = dbt_module._resolve_managed_clone_dir(
        project_dir=str(tmp_path / "workspace"),
        package_url="https://github.com/org/repo.git",
        branch="main",
    )

    assert clone_dir.parent.name == ".slideflow_dbt_clones"
    assert clone_dir.parent.exists()


def test_get_compiled_project_allows_target_named_path_inside_repo(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    invocations = []

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)
        (clone_dir / ".slideflow_dbt_targets").mkdir(parents=True)

    class _Runner:
        def invoke(self, args):
            invocations.append(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    compiled_dir = dbt_module._get_compiled_project(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
        vars={"country": "US"},
    )

    assert [args[0] for args in invocations] == ["deps", "compile"]
    assert compiled_dir.parent.parent.name == ".slideflow_dbt_targets"
    assert ".slideflow_dbt_clones" not in compiled_dir.parts


def test_resolve_managed_clone_dir_excludes_compile_variant_inputs(tmp_path):
    workspace = str(tmp_path / "workspace")
    package_url = "https://github.com/org/repo.git"
    branch = "main"

    baseline = dbt_module._resolve_managed_clone_dir(
        project_dir=workspace,
        package_url=package_url,
        branch=branch,
        target="prod",
        vars={"as_of_date": "2026-02-18"},
        profiles_dir="/tmp/profiles_a",
        profile_name="default",
    )
    different_target = dbt_module._resolve_managed_clone_dir(
        project_dir=workspace,
        package_url=package_url,
        branch=branch,
        target="dev",
        vars={"as_of_date": "2026-02-18"},
        profiles_dir="/tmp/profiles_a",
        profile_name="default",
    )
    different_vars = dbt_module._resolve_managed_clone_dir(
        project_dir=workspace,
        package_url=package_url,
        branch=branch,
        target="prod",
        vars={"as_of_date": "2026-02-19"},
        profiles_dir="/tmp/profiles_a",
        profile_name="default",
    )
    different_profile = dbt_module._resolve_managed_clone_dir(
        project_dir=workspace,
        package_url=package_url,
        branch=branch,
        target="prod",
        vars={"as_of_date": "2026-02-18"},
        profiles_dir="/tmp/profiles_b",
        profile_name="analytics",
    )

    assert baseline == different_target
    assert baseline == different_vars
    assert baseline != different_profile
    assert dbt_module._resolve_managed_compile_dir(
        baseline, "prod", {"as_of_date": "2026-02-18"}
    ) != dbt_module._resolve_managed_compile_dir(
        baseline, "dev", {"as_of_date": "2026-02-18"}
    )
    assert dbt_module._resolve_managed_compile_dir(
        baseline, "prod", {"as_of_date": "2026-02-18"}
    ) != dbt_module._resolve_managed_compile_dir(
        baseline, "prod", {"as_of_date": "2026-02-19"}
    )


def test_workspace_identity_distinguishes_absent_from_literal_defaults(tmp_path):
    workspace = str(tmp_path / "workspace")
    package_url = "https://github.com/org/repo.git"

    absent_key = dbt_module._workspace_cache_key(
        package_url, workspace, None, None, None
    )
    literal_key = dbt_module._workspace_cache_key(
        package_url, workspace, "default", None, "default"
    )
    absent_dir = dbt_module._resolve_managed_clone_dir(workspace, package_url, None)
    literal_dir = dbt_module._resolve_managed_clone_dir(
        workspace, package_url, "default", profile_name="default"
    )

    assert absent_key != literal_key
    assert absent_dir != literal_dir
    assert (
        dbt_module._workspace_cache_key(package_url, workspace, "", "", "")
        == absent_key
    )


def test_concurrent_literal_default_and_absent_branch_use_distinct_workspaces(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_paths = []
    clone_lock = threading.Lock()

    def _fake_clone(_url, clone_dir, _branch):
        with clone_lock:
            clone_paths.append(clone_dir)
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    def _worker(branch):
        return dbt_module._get_compiled_project(
            package_url="https://github.com/org/repo.git",
            project_dir=str(tmp_path / "workspace"),
            branch=branch,
            target="prod",
            vars=None,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = list(executor.map(_worker, (None, "default")))

    assert len(set(clone_paths)) == 2
    assert dbt_module._source_clone_dir(paths[0]) != dbt_module._source_clone_dir(
        paths[1]
    )


def test_managed_compile_dir_is_a_sibling_of_clone_tree(tmp_path):
    clone_dir = dbt_module._resolve_managed_clone_dir(
        str(tmp_path / "workspace"),
        "https://github.com/org/repo.git",
        "main",
    )
    compiled_dir = dbt_module._resolve_managed_compile_dir(
        clone_dir, "prod", {"country": "US"}
    )

    assert (
        compiled_dir.parent.parent == tmp_path / "workspace" / ".slideflow_dbt_targets"
    )
    assert dbt_module._source_clone_dir(compiled_dir) == clone_dir
    assert not compiled_dir.is_relative_to(clone_dir)


def test_clone_cleanup_invalidates_sibling_manifest_indexes(tmp_path):
    _reset_dbt_caches()
    clone_dir = dbt_module._resolve_managed_clone_dir(
        str(tmp_path / "workspace"),
        "https://github.com/org/repo.git",
        "main",
    )
    compiled_dir = dbt_module._resolve_managed_compile_dir(
        clone_dir, "prod", {"country": "US"}
    )
    clone_dir.mkdir(parents=True)
    compiled_dir.mkdir(parents=True)
    manifest_key = compiled_dir.resolve()
    dbt_module._manifest_index_cache[manifest_key] = dbt_module._ManifestIndex({}, {})

    dbt_module._cleanup_managed_clone_dir(clone_dir)

    assert manifest_key not in dbt_module._manifest_index_cache
    assert not clone_dir.exists()
    assert not compiled_dir.exists()


def test_clone_cleanup_does_not_follow_symlinked_artifact_namespace(tmp_path):
    clone_dir = dbt_module._resolve_managed_clone_dir(
        str(tmp_path / "workspace"),
        "https://github.com/org/repo.git",
        "main",
    )
    clone_dir.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("preserve")
    target_root = clone_dir.parent.parent / ".slideflow_dbt_targets"
    target_root.symlink_to(external, target_is_directory=True)

    dbt_module._cleanup_managed_clone_dir(clone_dir)

    assert sentinel.read_text() == "preserve"
    assert target_root.is_symlink()


@pytest.mark.parametrize("symlink_level", ["namespace", "workspace", "variant"])
def test_get_compiled_project_rejects_symlinked_artifact_paths(
    monkeypatch, tmp_path, symlink_level
):
    _reset_dbt_caches()
    workspace = tmp_path / "workspace"
    package_url = "https://github.com/org/repo.git"
    clone_dir = dbt_module._resolve_managed_clone_dir(
        str(workspace), package_url, "main"
    )
    compiled_dir = dbt_module._resolve_managed_compile_dir(
        clone_dir, "prod", {"country": "US"}
    )
    external = tmp_path / f"external-{symlink_level}"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("preserve")

    if symlink_level == "namespace":
        compiled_dir.parent.parent.symlink_to(external, target_is_directory=True)
    elif symlink_level == "workspace":
        compiled_dir.parent.parent.mkdir()
        compiled_dir.parent.symlink_to(external, target_is_directory=True)
    else:
        compiled_dir.parent.mkdir(parents=True)
        compiled_dir.symlink_to(external, target_is_directory=True)

    def _fake_clone(_url, path, _branch):
        _write_fake_dbt_project(path)

    invocations = []

    class _Runner:
        def invoke(self, args):
            invocations.append(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    with pytest.raises(DataSourceError, match="must not be a symlink"):
        dbt_module._get_compiled_project(
            package_url=package_url,
            project_dir=str(workspace),
            branch="main",
            target="prod",
            vars={"country": "US"},
        )

    assert [args[0] for args in invocations] == ["deps"]
    assert sentinel.read_text() == "preserve"


def test_cached_compile_path_rejects_symlink_replacement(monkeypatch, tmp_path):
    _reset_dbt_caches()

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": {"country": "US"},
    }
    compiled_dir = dbt_module._get_compiled_project(**kwargs)
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("preserve")
    shutil.rmtree(compiled_dir)
    compiled_dir.symlink_to(external, target_is_directory=True)

    with pytest.raises(DataSourceError, match="must not be a symlink"):
        dbt_module._get_compiled_project(**kwargs)

    assert sentinel.read_text() == "preserve"


def test_cached_compile_reprepares_externally_deleted_source_clone(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_calls = 0
    invocations = []
    project_dir_states = []

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        clone_calls += 1
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            invocations.append(list(args))
            if "--project-dir" in args:
                project_dir = Path(args[args.index("--project-dir") + 1])
                project_dir_states.append(project_dir.is_dir())
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": {"country": "US"},
        "parse_only": True,
    }

    compiled_dir = dbt_module._get_compiled_project(**kwargs)
    source_dir = dbt_module._source_clone_dir(compiled_dir)
    dbt_module._ensure_selected_compilation(
        clone_dir=compiled_dir,
        package_url=kwargs["package_url"],
        project_dir=kwargs["project_dir"],
        branch=kwargs["branch"],
        target=kwargs["target"],
        vars=kwargs["vars"],
        profiles_dir=None,
        profile_name=None,
        selectors=("model.project.existing_selector",),
    )
    shutil.rmtree(source_dir)

    refreshed_dir = dbt_module._get_compiled_project(**kwargs)
    cache_key = dbt_module._project_cache_key(
        kwargs["package_url"],
        kwargs["project_dir"],
        kwargs["branch"],
        kwargs["target"],
        kwargs["vars"],
        None,
        None,
    )
    assert dbt_module._compiled_project_coverage[cache_key] == frozenset()
    dbt_module._ensure_selected_compilation(
        clone_dir=refreshed_dir,
        package_url=kwargs["package_url"],
        project_dir=kwargs["project_dir"],
        branch=kwargs["branch"],
        target=kwargs["target"],
        vars=kwargs["vars"],
        profiles_dir=None,
        profile_name=None,
        selectors=("model.project.new_selector",),
    )

    assert refreshed_dir == compiled_dir
    assert source_dir.is_dir()
    assert clone_calls == 2
    assert [args[0] for args in invocations] == [
        "deps",
        "parse",
        "compile",
        "deps",
        "parse",
        "compile",
    ]
    assert all(project_dir_states)
    assert str(source_dir) in invocations[-1]
    assert invocations[-1][invocations[-1].index("--select") + 1] == (
        "model.project.new_selector"
    )


def test_workspace_refresh_invalidates_every_compiled_variant(monkeypatch, tmp_path):
    _reset_dbt_caches()
    clone_generation = 0

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_generation
        clone_generation += 1
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "generation.txt").write_text(str(clone_generation))

    class _Runner:
        def invoke(self, args):
            if "--target-path" in args:
                source = Path(args[args.index("--project-dir") + 1])
                target_path = Path(args[args.index("--target-path") + 1])
                target_path.mkdir(parents=True, exist_ok=True)
                (target_path / "generation.txt").write_text(
                    (source / "generation.txt").read_text()
                )
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "parse_only": True,
    }

    us_path = dbt_module._get_compiled_project(vars={"country": "US"}, **kwargs)
    ca_path = dbt_module._get_compiled_project(vars={"country": "CA"}, **kwargs)
    ca_key = dbt_module._project_cache_key(
        kwargs["package_url"],
        kwargs["project_dir"],
        kwargs["branch"],
        kwargs["target"],
        {"country": "CA"},
        None,
        None,
    )
    dbt_module._compiled_project_coverage[ca_key] = frozenset({"old.selector"})
    source_dir = dbt_module._source_clone_dir(us_path)
    shutil.rmtree(source_dir)

    refreshed_us = dbt_module._get_compiled_project(vars={"country": "US"}, **kwargs)

    assert ca_key not in dbt_module._compiled_projects_cache
    assert ca_key not in dbt_module._compiled_project_coverage
    assert not ca_path.exists()

    refreshed_ca = dbt_module._get_compiled_project(vars={"country": "CA"}, **kwargs)
    assert clone_generation == 2
    assert (refreshed_us / "target" / "generation.txt").read_text() == "2"
    assert (refreshed_ca / "target" / "generation.txt").read_text() == "2"


def test_workspace_refresh_waits_for_active_sibling_variant_lease(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        clone_calls += 1
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
    }
    us_path = dbt_module._get_compiled_project(vars={"country": "US"}, **kwargs)
    dbt_module._get_compiled_project(vars={"country": "CA"}, **kwargs)
    refresh_finished = threading.Event()
    refresh_errors = []

    with dbt_module._compiled_project_lease(
        vars={"country": "CA"}, **kwargs
    ) as leased_ca:
        shutil.rmtree(dbt_module._source_clone_dir(us_path))

        def _refresh():
            try:
                dbt_module._get_compiled_project(vars={"country": "US"}, **kwargs)
            except Exception as error:  # pragma: no cover - assertion helper path
                refresh_errors.append(error)
            finally:
                refresh_finished.set()

        refresh_thread = threading.Thread(target=_refresh)
        refresh_thread.start()
        assert not refresh_finished.wait(0.1)
        assert leased_ca.exists()

    refresh_thread.join(timeout=5)

    assert refresh_finished.is_set()
    assert refresh_errors == []
    assert clone_calls == 2


@pytest.mark.parametrize("child_name", ["target", "logs"])
def test_selected_compile_rejects_concrete_output_symlink(
    monkeypatch, tmp_path, child_name
):
    _reset_dbt_caches()
    invocations: list[list[str]] = []

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            invocations.append(list(args))
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": {"country": "US"},
        "parse_only": True,
    }
    compiled_dir = dbt_module._get_compiled_project(**kwargs)
    child = compiled_dir / child_name
    shutil.rmtree(child)
    external = tmp_path / f"external-{child_name}"
    external.mkdir()
    child.symlink_to(external, target_is_directory=True)

    with pytest.raises(DataSourceError, match="must not be a symlink"):
        dbt_module._ensure_selected_compilation(
            clone_dir=compiled_dir,
            package_url=kwargs["package_url"],
            project_dir=kwargs["project_dir"],
            branch=kwargs["branch"],
            target=kwargs["target"],
            vars=kwargs["vars"],
            profiles_dir=None,
            profile_name=None,
            selectors=("model.project.metrics",),
        )

    assert [args[0] for args in invocations] == ["deps", "parse"]


def test_dbt_deps_rejects_concrete_log_symlink(monkeypatch, tmp_path):
    _reset_dbt_caches()
    workspace = str(tmp_path / "workspace")
    package_url = "https://github.com/org/repo.git"
    clone_dir = dbt_module._resolve_managed_clone_dir(workspace, package_url, "main")
    deps_log = dbt_module._resolve_deps_log_dir(clone_dir)
    deps_log.parent.mkdir(parents=True)
    external = tmp_path / "external-deps"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("preserve")
    deps_log.symlink_to(external, target_is_directory=True)
    invocations = []

    def _fake_clone(_url, path, _branch):
        _write_fake_dbt_project(path)

    class _Runner:
        def invoke(self, args):
            invocations.append(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    with pytest.raises(DataSourceError, match="must not be a symlink"):
        dbt_module._get_compiled_project(
            package_url=package_url,
            project_dir=workspace,
            branch="main",
            target="prod",
            vars=None,
        )

    assert invocations == []
    assert sentinel.read_text() == "preserve"


def test_prepared_workspace_marker_mismatch_reprepares_all_variants(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        clone_calls += 1
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": {"country": "US"},
    }
    compiled_dir = dbt_module._get_compiled_project(**kwargs)
    marker_path = dbt_module._prepared_marker_path(
        dbt_module._source_clone_dir(compiled_dir)
    )
    marker = json.loads(marker_path.read_text())
    marker["identity"] = "wrong-workspace"
    marker_path.write_text(json.dumps(marker))

    dbt_module._get_compiled_project(**kwargs)

    assert clone_calls == 2


def test_workspace_process_lock_excludes_other_processes(tmp_path):
    _reset_dbt_caches()
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    release = context.Event()
    entered = context.Event()
    workspace = str(tmp_path / "workspace")
    holder = context.Process(
        target=_hold_workspace_process_lock,
        args=(workspace, acquired, release),
    )
    waiter = context.Process(
        target=_enter_workspace_process_lock,
        args=(workspace, entered),
    )

    holder.start()
    assert acquired.wait(10), "first process did not acquire the workspace lock"
    waiter.start()
    assert not entered.wait(0.2)
    release.set()
    holder.join(timeout=10)
    waiter.join(timeout=10)

    assert holder.exitcode == 0
    assert waiter.exitcode == 0
    assert entered.is_set()


def test_workspace_process_lock_rejects_symlinked_namespace(tmp_path):
    _reset_dbt_caches()
    workspace = tmp_path / "workspace"
    clone_dir = dbt_module._resolve_managed_clone_dir(
        str(workspace),
        "https://github.com/org/repo.git",
        "main",
    )
    external = tmp_path / "external-locks"
    external.mkdir()
    lock_root = workspace / ".slideflow_dbt_locks"
    lock_root.symlink_to(external, target_is_directory=True)

    with pytest.raises(DataSourceError, match="must not be a symlink"):
        with dbt_module._workspace_process_lock(clone_dir):
            pass


def test_pending_workspace_cleanup_restarts_after_releasing_prepared_lease(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    workspace = str(tmp_path / "workspace")
    package_url = "https://github.com/org/repo.git"
    workspace_key = dbt_module._workspace_cache_key(
        package_url, workspace, "main", None, None
    )
    clone_dir = dbt_module._resolve_managed_clone_dir(workspace, package_url, "main")
    compiled_dir = dbt_module._resolve_managed_compile_dir(clone_dir, "prod", None)
    injected = False

    def _fake_clone(_url, path, _branch):
        _write_fake_dbt_project(path)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    real_get_prepared = dbt_module._get_prepared_workspace

    def _inject_pending_cleanup(**kwargs):
        nonlocal injected
        prepared = real_get_prepared(**kwargs)
        if not injected:
            injected = True
            with dbt_module._cache_lock:
                dbt_module._invalidate_workspace_locked(workspace_key, prepared)
                dbt_module._pending_cleanup_dirs.add(compiled_dir)
        return prepared

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    monkeypatch.setattr(dbt_module, "_get_prepared_workspace", _inject_pending_cleanup)
    result: list[Path] = []
    errors: list[BaseException] = []

    def _worker():
        try:
            result.append(
                dbt_module._get_compiled_project(
                    package_url=package_url,
                    project_dir=workspace,
                    branch="main",
                    target="prod",
                    vars=None,
                )
            )
        except BaseException as error:  # pragma: no cover - assertion helper
            errors.append(error)

    worker = threading.Thread(target=_worker)
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert errors == []
    assert len(result) == 1
    assert result[0].is_dir()
    assert dbt_module._prepared_workspaces_in_use == {}


@pytest.mark.parametrize("marker_payload", [[], "invalid", 7, None])
def test_non_object_preparation_marker_rebuilds_without_attribute_error(
    monkeypatch, tmp_path, marker_payload
):
    _reset_dbt_caches()
    clone_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        clone_calls += 1
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": None,
    }
    compiled_dir = dbt_module._get_compiled_project(**kwargs)
    marker_path = dbt_module._prepared_marker_path(
        dbt_module._source_clone_dir(compiled_dir)
    )
    marker_path.write_text(json.dumps(marker_payload))

    rebuilt = dbt_module._get_compiled_project(**kwargs)

    assert rebuilt.is_dir()
    assert clone_calls == 2


def test_prepared_workspace_requires_project_file_and_matching_checkout(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_calls = 0
    revision = "revision-1"

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        clone_calls += 1
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    monkeypatch.setattr(
        dbt_module, "_resolve_checkout_revision", lambda _path: revision
    )
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": None,
    }
    compiled_dir = dbt_module._get_compiled_project(**kwargs)
    source_dir = dbt_module._source_clone_dir(compiled_dir)
    (source_dir / "dbt_project.yml").unlink()

    dbt_module._get_compiled_project(**kwargs)
    assert clone_calls == 2

    revision = "revision-2"
    dbt_module._get_compiled_project(**kwargs)
    assert clone_calls == 3


def test_external_generation_change_invalidates_siblings_before_new_variant(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        clone_calls += 1
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
    }
    us_path = dbt_module._get_compiled_project(vars={"country": "US"}, **kwargs)
    marker_path = dbt_module._prepared_marker_path(
        dbt_module._source_clone_dir(us_path)
    )
    marker = json.loads(marker_path.read_text())
    marker["generation"] = "externally-replaced"
    marker_path.write_text(json.dumps(marker))

    ca_path = dbt_module._get_compiled_project(vars={"country": "CA"}, **kwargs)

    assert clone_calls == 2
    assert not us_path.exists()
    assert ca_path.exists()


def test_cleanup_reservation_blocks_reuse_until_deletion_finishes(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_dir = dbt_module._resolve_managed_clone_dir(
        str(tmp_path / "workspace"),
        "https://github.com/org/repo.git",
        "main",
    )
    compiled_dir = dbt_module._resolve_managed_compile_dir(clone_dir, "prod", None)
    compiled_dir.mkdir(parents=True)
    started = threading.Event()
    allow_delete = threading.Event()
    real_rmtree = shutil.rmtree

    def _blocking_rmtree(path):
        if Path(path) == compiled_dir:
            started.set()
            assert allow_delete.wait(5)
        real_rmtree(path)

    monkeypatch.setattr(dbt_module.shutil, "rmtree", _blocking_rmtree)
    with dbt_module._cache_lock:
        dbt_module._pending_cleanup_dirs.add(compiled_dir)

    cleanup_thread = threading.Thread(target=dbt_module._cleanup_ready_managed_dirs)
    cleanup_thread.start()
    assert started.wait(5)

    waiter_finished = threading.Event()

    def _waiter():
        dbt_module._wait_for_managed_cleanup(compiled_dir, workspace=False)
        waiter_finished.set()

    waiter = threading.Thread(target=_waiter)
    waiter.start()
    assert not waiter_finished.wait(0.1)
    allow_delete.set()
    cleanup_thread.join(timeout=5)
    waiter.join(timeout=5)

    assert waiter_finished.is_set()
    assert compiled_dir not in dbt_module._pending_cleanup_dirs
    assert not compiled_dir.exists()


def test_cleanup_failure_keeps_reservation_until_retry_succeeds(monkeypatch, tmp_path):
    _reset_dbt_caches()
    clone_dir = dbt_module._resolve_managed_clone_dir(
        str(tmp_path / "workspace"),
        "https://github.com/org/repo.git",
        "main",
    )
    compiled_dir = dbt_module._resolve_managed_compile_dir(clone_dir, "prod", None)
    compiled_dir.mkdir(parents=True)
    cleanup_attempts = 0
    real_cleanup = dbt_module._cleanup_managed_compile_dir

    def _flaky_cleanup(path):
        nonlocal cleanup_attempts
        cleanup_attempts += 1
        if cleanup_attempts == 1:
            return False
        return real_cleanup(path)

    monkeypatch.setattr(dbt_module, "_cleanup_managed_compile_dir", _flaky_cleanup)
    with dbt_module._cache_lock:
        dbt_module._pending_cleanup_dirs.add(compiled_dir)

    dbt_module._wait_for_managed_cleanup(compiled_dir, workspace=False)

    assert cleanup_attempts == 2
    assert compiled_dir not in dbt_module._pending_cleanup_dirs
    assert compiled_dir not in dbt_module._cleanup_failures
    assert not compiled_dir.exists()


def test_workspace_failure_cleanup_finishes_before_retry_waiter_recreates_path(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_COMPILE_FAILURE_BACKOFF_S", "0")
    cleanup_started = threading.Event()
    allow_cleanup = threading.Event()
    clone_calls = 0
    real_cleanup = dbt_module._cleanup_managed_clone_dir

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        clone_calls += 1
        _write_fake_dbt_project(clone_dir)
        if clone_calls == 1:
            raise DataSourceError("clone failed after creating workspace")

    def _blocking_cleanup(clone_dir):
        if not cleanup_started.is_set():
            cleanup_started.set()
            assert allow_cleanup.wait(5)
        return real_cleanup(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "_cleanup_managed_clone_dir", _blocking_cleanup)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": None,
    }
    first_errors: list[BaseException] = []
    retry_results: list[Path] = []

    def _first():
        try:
            dbt_module._get_compiled_project(**kwargs)
        except BaseException as error:  # pragma: no cover - assertion helper
            first_errors.append(error)

    def _retry():
        retry_results.append(dbt_module._get_compiled_project(**kwargs))

    first = threading.Thread(target=_first)
    first.start()
    assert cleanup_started.wait(5)
    retry = threading.Thread(target=_retry)
    retry.start()
    time.sleep(0.1)

    assert clone_calls == 1
    assert retry.is_alive()
    allow_cleanup.set()
    first.join(timeout=5)
    retry.join(timeout=5)

    assert not first.is_alive()
    assert not retry.is_alive()
    assert len(first_errors) == 1
    assert clone_calls == 2
    assert len(retry_results) == 1
    assert retry_results[0].is_dir()


def test_compile_failure_cleanup_finishes_before_retry_waiter_reuses_variant(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_COMPILE_FAILURE_BACKOFF_S", "0")
    cleanup_started = threading.Event()
    allow_cleanup = threading.Event()
    compile_calls = 0
    real_cleanup = dbt_module._cleanup_managed_compile_dir

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    def _blocking_cleanup(compiled_dir):
        if not cleanup_started.is_set():
            cleanup_started.set()
            assert allow_cleanup.wait(5)
        return real_cleanup(compiled_dir)

    class _Runner:
        def invoke(self, args):
            nonlocal compile_calls
            if args[0] == "deps":
                return SimpleNamespace(success=True)
            compile_calls += 1
            if compile_calls == 1:
                return SimpleNamespace(
                    success=False, exception=RuntimeError("transient compile failure")
                )
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "_cleanup_managed_compile_dir", _blocking_cleanup)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": None,
    }
    first_errors: list[BaseException] = []
    retry_results: list[Path] = []

    def _first():
        try:
            dbt_module._get_compiled_project(**kwargs)
        except BaseException as error:  # pragma: no cover - assertion helper
            first_errors.append(error)

    def _retry():
        retry_results.append(dbt_module._get_compiled_project(**kwargs))

    first = threading.Thread(target=_first)
    first.start()
    assert cleanup_started.wait(5)
    retry = threading.Thread(target=_retry)
    retry.start()
    time.sleep(0.1)

    assert compile_calls == 1
    assert retry.is_alive()
    allow_cleanup.set()
    first.join(timeout=5)
    retry.join(timeout=5)

    assert not first.is_alive()
    assert not retry.is_alive()
    assert len(first_errors) == 1
    assert compile_calls == 2
    assert len(retry_results) == 1
    assert retry_results[0].is_dir()


def test_compile_stops_when_existing_variant_cannot_be_removed(monkeypatch, tmp_path):
    _reset_dbt_caches()
    workspace = str(tmp_path / "workspace")
    package_url = "https://github.com/org/repo.git"
    clone_dir = dbt_module._resolve_managed_clone_dir(workspace, package_url, "main")
    compiled_dir = dbt_module._resolve_managed_compile_dir(clone_dir, "prod", None)
    compiled_dir.mkdir(parents=True)

    def _fake_clone(_url, path, _branch):
        _write_fake_dbt_project(path)

    invocations = []

    class _Runner:
        def invoke(self, args):
            invocations.append(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    monkeypatch.setattr(dbt_module.shutil, "rmtree", lambda _path: None)

    with pytest.raises(DataSourceError, match="Failed to safely reset"):
        dbt_module._get_compiled_project(
            package_url=package_url,
            project_dir=workspace,
            branch="main",
            target="prod",
            vars=None,
        )

    assert [args[0] for args in invocations] == ["deps"]


def test_get_compiled_project_reuses_clone_and_deps_across_isolated_vars(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_calls = 0
    invocations: list[list[str]] = []

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        clone_calls += 1
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            invocations.append(list(args))
            return None

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    workspace = str(tmp_path / "workspace")
    package_url = "https://github.com/org/repo.git"
    branch = "main"

    path_a = dbt_module._get_compiled_project(
        package_url=package_url,
        project_dir=workspace,
        branch=branch,
        target="prod",
        vars={"country": "US"},
        profiles_dir=None,
        profile_name=None,
    )
    path_b = dbt_module._get_compiled_project(
        package_url=package_url,
        project_dir=workspace,
        branch=branch,
        target="prod",
        vars={"country": "CA"},
        profiles_dir=None,
        profile_name=None,
    )
    path_a_again = dbt_module._get_compiled_project(
        package_url=package_url,
        project_dir=workspace,
        branch=branch,
        target="prod",
        vars={"country": "US"},
        profiles_dir=None,
        profile_name=None,
    )

    assert path_a != path_b
    assert path_a_again == path_a
    assert dbt_module._source_clone_dir(path_a) == dbt_module._source_clone_dir(path_b)
    assert clone_calls == 1
    assert [args[0] for args in invocations].count("deps") == 1
    assert [args[0] for args in invocations].count("compile") == 2
    assert str(path_a / "target") in invocations[1]
    assert str(path_b / "target") in invocations[2]


def test_get_compiled_project_does_not_change_process_cwd(monkeypatch, tmp_path):
    _reset_dbt_caches()

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    invoke_args = []

    class _Runner:
        def invoke(self, args):
            invoke_args.append(args)
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    chdir_calls = []
    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    monkeypatch.setattr(dbt_module.os, "chdir", lambda path: chdir_calls.append(path))

    compiled_path = dbt_module._get_compiled_project(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
        vars={"country": "US"},
        profiles_dir=None,
        profile_name=None,
    )

    assert compiled_path.exists()
    assert chdir_calls == []
    assert invoke_args
    assert "--project-dir" in invoke_args[0]
    assert "--project-dir" in invoke_args[1]


def test_get_compiled_project_uses_project_root_profiles_when_present(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "profiles.yml").write_text("default: {}")

    invoke_args = []

    class _Runner:
        def invoke(self, args):
            invoke_args.append(args)
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    compiled_path = dbt_module._get_compiled_project(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
        vars={"country": "US"},
        profiles_dir=None,
        profile_name=None,
    )

    assert compiled_path.exists()
    assert invoke_args
    assert "--profiles-dir" in invoke_args[0]
    assert "--profiles-dir" in invoke_args[1]
    source_dir = dbt_module._source_clone_dir(compiled_path)
    assert str(source_dir) in invoke_args[0]
    assert str(source_dir) in invoke_args[1]
    assert str(compiled_path / "target") in invoke_args[1]


def test_get_compiled_project_raises_when_dbt_compile_reports_failure(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            if args[0] == "deps":
                return SimpleNamespace(success=True)
            return SimpleNamespace(
                success=False, exception=RuntimeError("compile boom")
            )

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    with pytest.raises(DataSourceError, match="dbt compile failed"):
        dbt_module._get_compiled_project(
            package_url="https://github.com/org/repo.git",
            project_dir=str(tmp_path / "workspace"),
            branch="main",
            target="prod",
            vars={"country": "US"},
            profiles_dir=None,
            profile_name=None,
        )

    assert dbt_module._compiled_projects_cache == {}
    assert dbt_module._compilation_inflight == {}


def test_get_compiled_project_caches_failure_and_fails_fast_for_same_key(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    compile_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            nonlocal compile_calls
            if args[0] == "deps":
                return SimpleNamespace(success=True)
            compile_calls += 1
            return SimpleNamespace(
                success=False, exception=RuntimeError("profiles path missing")
            )

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": {"country": "US"},
        "profiles_dir": None,
        "profile_name": None,
    }

    with pytest.raises(DataSourceError, match="dbt compile failed"):
        dbt_module._get_compiled_project(**kwargs)
    with pytest.raises(DataSourceError, match="dbt compile failed"):
        dbt_module._get_compiled_project(**kwargs)

    assert compile_calls == 1


def test_compile_failure_isolated_from_other_vars(monkeypatch, tmp_path):
    _reset_dbt_caches()
    clone_calls = 0
    deps_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        clone_calls += 1
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            nonlocal deps_calls
            if args[0] == "deps":
                deps_calls += 1
                return SimpleNamespace(success=True)
            vars_payload = args[args.index("--vars") + 1]
            if json.loads(vars_payload)["country"] == "US":
                return SimpleNamespace(
                    success=False, exception=RuntimeError("US compile failed")
                )
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "profiles_dir": None,
        "profile_name": None,
    }

    with pytest.raises(DataSourceError, match="US compile failed"):
        dbt_module._get_compiled_project(vars={"country": "US"}, **kwargs)
    ca_path = dbt_module._get_compiled_project(vars={"country": "CA"}, **kwargs)

    assert ca_path.exists()
    assert clone_calls == 1
    assert deps_calls == 1


def test_get_compiled_project_retries_after_failure_backoff_expiry(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_COMPILE_FAILURE_BACKOFF_S", "0")
    compile_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            nonlocal compile_calls
            if args[0] == "deps":
                return SimpleNamespace(success=True)
            compile_calls += 1
            if compile_calls == 1:
                return SimpleNamespace(
                    success=False, exception=RuntimeError("transient compile error")
                )
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": {"country": "US"},
        "profiles_dir": None,
        "profile_name": None,
    }

    with pytest.raises(DataSourceError, match="dbt compile failed"):
        dbt_module._get_compiled_project(**kwargs)

    compiled_path = dbt_module._get_compiled_project(**kwargs)
    assert compiled_path.exists()
    assert compile_calls == 2


def test_get_compiled_project_caches_failure_for_waiting_threads(monkeypatch, tmp_path):
    _reset_dbt_caches()
    compile_calls = 0
    counter_lock = threading.Lock()
    start_barrier = threading.Barrier(4)

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            nonlocal compile_calls
            if args[0] == "deps":
                return SimpleNamespace(success=True)
            with counter_lock:
                compile_calls += 1
            time.sleep(0.05)
            return SimpleNamespace(
                success=False, exception=RuntimeError("profiles path missing")
            )

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "vars": {"country": "US"},
        "profiles_dir": None,
        "profile_name": None,
    }

    def _worker():
        start_barrier.wait()
        with pytest.raises(DataSourceError, match="dbt compile failed"):
            dbt_module._get_compiled_project(**kwargs)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _i: _worker(), range(4)))

    assert compile_calls == 1


def test_get_compiled_project_bounds_failure_cache_entries(monkeypatch, tmp_path):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_COMPILE_FAILURE_BACKOFF_S", "3600")
    monkeypatch.setenv("SLIDEFLOW_DBT_FAILURE_CACHE_MAX_ENTRIES", "2")

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            if args[0] == "deps":
                return SimpleNamespace(success=True)
            return SimpleNamespace(
                success=False, exception=RuntimeError("persistent compile error")
            )

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    workspace = str(tmp_path / "workspace")
    for country in ("US", "CA", "MX"):
        with pytest.raises(DataSourceError, match="dbt compile failed"):
            dbt_module._get_compiled_project(
                package_url="https://github.com/org/repo.git",
                project_dir=workspace,
                branch="main",
                target="prod",
                vars={"country": country},
                profiles_dir=None,
                profile_name=None,
            )

    assert len(dbt_module._compilation_failures) == 2


def test_get_compiled_project_single_flight_deduplicates_concurrent_compiles(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_calls = 0
    compile_calls = 0
    counter_lock = threading.Lock()
    start_barrier = threading.Barrier(4)

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        with counter_lock:
            clone_calls += 1
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            nonlocal compile_calls
            if args[0] == "compile":
                with counter_lock:
                    compile_calls += 1
                time.sleep(0.05)
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    def _worker():
        start_barrier.wait()
        return dbt_module._get_compiled_project(
            package_url="https://github.com/org/repo.git",
            project_dir=str(tmp_path / "workspace"),
            branch="main",
            target="prod",
            vars={"country": "US"},
            profiles_dir=None,
            profile_name=None,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _i: _worker(), range(4)))

    assert clone_calls == 1
    assert compile_calls == 1
    assert all(result == results[0] for result in results)


def test_concurrent_vars_single_flight_shared_workspace_preparation(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_calls = 0
    deps_calls = 0
    compile_calls = 0
    counter_lock = threading.Lock()
    start_barrier = threading.Barrier(2)

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        with counter_lock:
            clone_calls += 1
        time.sleep(0.05)
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, args):
            nonlocal deps_calls, compile_calls
            with counter_lock:
                if args[0] == "deps":
                    deps_calls += 1
                elif args[0] == "compile":
                    compile_calls += 1
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    def _worker(country):
        start_barrier.wait()
        return dbt_module._get_compiled_project(
            package_url="https://github.com/org/repo.git",
            project_dir=str(tmp_path / "workspace"),
            branch="main",
            target="prod",
            vars={"country": country},
            profiles_dir=None,
            profile_name=None,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(_worker, ("US", "CA")))

    assert clone_calls == 1
    assert deps_calls == 1
    assert compile_calls == 2
    assert results[0] != results[1]
    assert dbt_module._source_clone_dir(results[0]) == dbt_module._source_clone_dir(
        results[1]
    )


def test_manifest_connector_single_flight_deduplicates_concurrent_manifest_reads(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_calls = 0
    compile_calls = 0
    counter_lock = threading.Lock()
    start_barrier = threading.Barrier(4)

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        with counter_lock:
            clone_calls += 1
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "target").mkdir(parents=True, exist_ok=True)
        (clone_dir / "target" / "compiled.sql").write_text("select 1 as answer")
        manifest = {
            "nodes": {
                "model.project.metrics": {
                    "resource_type": "model",
                    "alias": "metrics_model",
                    "compiled_path": "target/compiled.sql",
                }
            }
        }
        (clone_dir / "target" / "manifest.json").write_text(json.dumps(manifest))

    class _Runner:
        def invoke(self, args):
            nonlocal compile_calls
            if args[0] == "compile":
                with counter_lock:
                    compile_calls += 1
                time.sleep(0.05)
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
        vars={"country": "US"},
    )

    def _worker():
        start_barrier.wait()
        return connector.get_compiled_query("metrics_model")

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _i: _worker(), range(4)))

    assert clone_calls == 1
    assert compile_calls == 1
    assert results == ["select 1 as answer"] * 4


def test_manifest_lookup_ambiguous_alias_requires_disambiguation(monkeypatch, tmp_path):
    _reset_dbt_caches()

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "target").mkdir(parents=True, exist_ok=True)
        (clone_dir / "target" / "us.sql").write_text("select 'US' as country")
        (clone_dir / "target" / "eu.sql").write_text("select 'EU' as country")
        manifest = {
            "nodes": {
                "model.pkg_a.metrics_us": {
                    "resource_type": "model",
                    "alias": "metrics_model",
                    "package_name": "pkg_a",
                    "name": "metrics_us",
                    "compiled_path": "target/us.sql",
                },
                "model.pkg_b.metrics_eu": {
                    "resource_type": "model",
                    "alias": "metrics_model",
                    "package_name": "pkg_b",
                    "name": "metrics_eu",
                    "compiled_path": "target/eu.sql",
                },
            }
        }
        (clone_dir / "target" / "manifest.json").write_text(json.dumps(manifest))

    class _Runner:
        def invoke(self, args):
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
        vars={"country": "US"},
    )

    with pytest.raises(DataSourceError, match="Ambiguous dbt model alias"):
        connector.get_compiled_query("metrics_model")


def test_manifest_lookup_supports_alias_disambiguation_selectors(monkeypatch, tmp_path):
    _reset_dbt_caches()

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "target").mkdir(parents=True, exist_ok=True)
        (clone_dir / "target" / "us.sql").write_text("select 'US' as country")
        (clone_dir / "target" / "eu.sql").write_text("select 'EU' as country")
        manifest = {
            "nodes": {
                "model.pkg_a.metrics_us": {
                    "resource_type": "model",
                    "alias": "metrics_model",
                    "package_name": "pkg_a",
                    "name": "metrics_us",
                    "compiled_path": "target/us.sql",
                },
                "model.pkg_b.metrics_eu": {
                    "resource_type": "model",
                    "alias": "metrics_model",
                    "package_name": "pkg_b",
                    "name": "metrics_eu",
                    "compiled_path": "target/eu.sql",
                },
            }
        }
        (clone_dir / "target" / "manifest.json").write_text(json.dumps(manifest))

    class _Runner:
        def invoke(self, args):
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
        vars={"country": "US"},
    )

    by_unique_id = connector.get_compiled_query(
        "metrics_model", model_unique_id="model.pkg_b.metrics_eu"
    )
    assert by_unique_id == "select 'EU' as country"

    by_package_name = connector.get_compiled_query(
        "metrics_model", model_package_name="pkg_a"
    )
    assert by_package_name == "select 'US' as country"

    by_model_name = connector.get_compiled_query(
        "metrics_model", model_selector_name="metrics_eu"
    )
    assert by_model_name == "select 'EU' as country"


def test_manifest_lookup_reuses_manifest_index_for_repeated_queries(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    load_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "target").mkdir(parents=True, exist_ok=True)
        (clone_dir / "target" / "compiled.sql").write_text("select 1 as answer")
        manifest = {
            "nodes": {
                "model.project.metrics": {
                    "resource_type": "model",
                    "alias": "metrics_model",
                    "compiled_path": "target/compiled.sql",
                }
            }
        }
        (clone_dir / "target" / "manifest.json").write_text(json.dumps(manifest))

    class _Runner:
        def invoke(self, args):
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    original_loader = dbt_module._load_manifest_index

    def _counting_loader(clone_dir):
        nonlocal load_calls
        load_calls += 1
        return original_loader(clone_dir)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    monkeypatch.setattr(dbt_module, "_load_manifest_index", _counting_loader)

    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
        vars={"country": "US"},
    )

    first = connector.get_compiled_query("metrics_model")
    second = connector.get_compiled_query("metrics_model")

    assert first == "select 1 as answer"
    assert second == "select 1 as answer"
    assert load_calls == 2


def test_manifest_index_is_rebuilt_without_recloning_when_variant_is_missing(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        nonlocal clone_calls
        clone_calls += 1
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "target").mkdir(parents=True, exist_ok=True)
        if clone_calls == 1:
            compiled_name = "compiled_first.sql"
            sql_text = "select 'first' as version"
        else:
            compiled_name = "compiled_second.sql"
            sql_text = "select 'second' as version"
        (clone_dir / "target" / compiled_name).write_text(sql_text)
        manifest = {
            "nodes": {
                "model.project.metrics": {
                    "resource_type": "model",
                    "alias": "metrics_model",
                    "compiled_path": f"target/{compiled_name}",
                }
            }
        }
        (clone_dir / "target" / "manifest.json").write_text(json.dumps(manifest))

    class _Runner:
        def invoke(self, args):
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
        vars={"country": "US"},
    )

    first = connector.get_compiled_query("metrics_model")
    assert first == "select 'first' as version"

    with dbt_module._cache_lock:
        cached_clone_dir = next(iter(dbt_module._compiled_projects_cache.values()))
    shutil.rmtree(cached_clone_dir)

    second = connector.get_compiled_query("metrics_model")
    assert second == "select 'first' as version"
    assert clone_calls == 1


def test_manifest_index_single_flight_deduplicates_parallel_reads_on_warm_cache(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    start_barrier = threading.Barrier(4)
    load_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "target").mkdir(parents=True, exist_ok=True)
        (clone_dir / "target" / "compiled.sql").write_text("select 1 as answer")
        manifest = {
            "nodes": {
                "model.project.metrics": {
                    "resource_type": "model",
                    "alias": "metrics_model",
                    "compiled_path": "target/compiled.sql",
                }
            }
        }
        (clone_dir / "target" / "manifest.json").write_text(json.dumps(manifest))

    class _Runner:
        def invoke(self, args):
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
        vars={"country": "US"},
    )

    assert connector.get_compiled_query("metrics_model") == "select 1 as answer"
    dbt_module._manifest_index_cache.clear()
    dbt_module._manifest_index_inflight.clear()

    original_loader = dbt_module._load_manifest_index

    def _counting_loader(clone_dir):
        nonlocal load_calls
        load_calls += 1
        time.sleep(0.05)
        return original_loader(clone_dir)

    monkeypatch.setattr(dbt_module, "_load_manifest_index", _counting_loader)

    def _worker():
        start_barrier.wait()
        return connector.get_compiled_query("metrics_model")

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _i: _worker(), range(4)))

    assert results == ["select 1 as answer"] * 4
    assert load_calls == 1


def test_manifest_index_single_flight_recovers_after_loader_failure(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir(parents=True, exist_ok=True)
    start_barrier = threading.Barrier(2)
    calls = 0
    call_lock = threading.Lock()

    success_index = dbt_module._ManifestIndex(
        by_alias={},
        by_unique_id={},
    )

    def _flaky_loader(_clone_dir):
        nonlocal calls
        with call_lock:
            calls += 1
            call_number = calls
        if call_number == 1:
            time.sleep(0.05)
            raise DataSourceError("manifest load failed")
        return success_index

    monkeypatch.setattr(dbt_module, "_load_manifest_index", _flaky_loader)

    results = []
    errors = []

    def _worker():
        start_barrier.wait()
        try:
            results.append(dbt_module._get_manifest_index(clone_dir))
        except Exception as error:  # pragma: no cover - assertion helper path
            errors.append(error)

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not t1.is_alive()
    assert not t2.is_alive()
    assert calls == 2
    assert len(results) == 1
    assert results[0] is success_index
    assert len(errors) == 1
    assert isinstance(errors[0], DataSourceError)


def test_manifest_lookup_returns_none_when_compiled_file_is_missing(
    monkeypatch, tmp_path, caplog
):
    _reset_dbt_caches()

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "target").mkdir(parents=True, exist_ok=True)
        manifest = {
            "nodes": {
                "model.project.metrics": {
                    "resource_type": "model",
                    "alias": "metrics_model",
                    "compiled_path": "target/missing.sql",
                }
            }
        }
        (clone_dir / "target" / "manifest.json").write_text(json.dumps(manifest))

    class _Runner:
        def invoke(self, args):
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    connector = dbt_module.DBTManifestConnector(
        package_url="https://github.com/org/repo.git",
        project_dir=str(tmp_path / "workspace"),
        branch="main",
        target="prod",
        vars={"country": "US"},
    )

    caplog.set_level("WARNING")
    sql = connector.get_compiled_query("metrics_model")

    assert sql is None
    assert "Missing compiled file for metrics_model" in caplog.text


def test_databricks_connector_forwards_manifest_disambiguation_selectors(monkeypatch):
    captured = {}

    class _ManifestStub:
        def __init__(self, **kwargs):
            captured["manifest_init"] = kwargs

        def get_compiled_query(self, model_alias, **kwargs):
            captured["model_alias"] = model_alias
            captured["selectors"] = kwargs
            return "select 1 as answer"

    class _ExecutorStub:
        def execute(self, sql_query):
            captured["sql"] = sql_query
            return "ok"

    monkeypatch.setattr(dbt_module, "DBTManifestConnector", _ManifestStub)
    monkeypatch.setattr(
        dbt_module.DBTDatabricksConnector,
        "sql_executor_factory",
        lambda: _ExecutorStub(),
    )

    connector = dbt_module.DBTDatabricksConnector(
        model_alias="metrics_model",
        model_unique_id="model.pkg.metrics_eu",
        model_package_name="pkg",
        model_selector_name="metrics_eu",
        package_url="https://github.com/org/repo.git",
        project_dir="/tmp/workspace",
        branch="main",
        target="prod",
    )

    result = connector.fetch_data()

    assert result == "ok"
    assert captured["sql"] == "select 1 as answer"
    assert captured["model_alias"] == "metrics_model"
    assert captured["selectors"] == {
        "model_unique_id": "model.pkg.metrics_eu",
        "model_package_name": "pkg",
        "model_selector_name": "metrics_eu",
    }


@pytest.mark.parametrize(
    ("connector_cls", "extra_kwargs"),
    [
        (
            dbt_module.DBTDatabricksConnector,
            {},
        ),
        (
            dbt_module.DBTBigQueryConnector,
            {"project_id": "project", "location": "US"},
        ),
        (
            dbt_module.DBTDuckDBConnector,
            {"database": "/tmp/warehouse.duckdb"},
        ),
        (
            dbt_module.DBTRedshiftConnector,
            {
                "host": "redshift.example.com",
                "database": "analytics",
                "user": "report_user",
                "password": "secret",
            },
        ),
    ],
)
def test_dbt_warehouse_connectors_share_missing_compiled_model_guard(
    monkeypatch, connector_cls, extra_kwargs
):
    class _ManifestStub:
        def __init__(self, **_kwargs):
            pass

        def get_compiled_query(self, _model_alias, **_selectors):
            return None

    class _ExecutorStub:
        def execute(self, _sql_query):
            raise AssertionError("Executor should not run when compiled SQL is missing")

    monkeypatch.setattr(dbt_module, "DBTManifestConnector", _ManifestStub)
    monkeypatch.setattr(
        dbt_module, "BigQuerySQLExecutor", lambda **_kwargs: _ExecutorStub()
    )
    monkeypatch.setattr(
        dbt_module, "DuckDBSQLExecutor", lambda **_kwargs: _ExecutorStub()
    )
    monkeypatch.setattr(
        dbt_module, "RedshiftSQLExecutor", lambda **_kwargs: _ExecutorStub()
    )
    monkeypatch.setattr(
        dbt_module.DBTDatabricksConnector,
        "sql_executor_factory",
        lambda: _ExecutorStub(),
    )

    connector = connector_cls(
        model_alias="metrics_model",
        package_url="https://github.com/org/repo.git",
        project_dir="/tmp/workspace",
        **extra_kwargs,
    )

    with pytest.raises(DataSourceError, match="No compiled model 'metrics_model'"):
        connector.fetch_data()


def test_composable_dbt_source_config_resolves_to_databricks_connector():
    config = dbt_module.DBTSourceConfig(
        name="metrics",
        type="dbt",
        model_alias="metrics_model",
        model_unique_id="model.pkg.metrics_model",
        model_package_name="pkg",
        model_selector_name="metrics_model",
        dbt={
            "package_url": "https://github.com/org/repo.git",
            "project_dir": "/tmp/workspace",
            "profile_name": "analytics",
            "branch": "main",
            "target": "prod",
            "vars": {"country": "US"},
            "compile": False,
            "profiles_dir": "/tmp/profiles",
        },
        warehouse={"type": "databricks"},
    )

    connector = config.get_connector()

    assert isinstance(connector, dbt_module.DBTDatabricksConnector)
    assert connector.model_alias == "metrics_model"
    assert connector.model_unique_id == "model.pkg.metrics_model"
    assert connector.model_package_name == "pkg"
    assert connector.model_selector_name == "metrics_model"
    assert connector.package_url == "https://github.com/org/repo.git"
    assert connector.project_dir == "/tmp/workspace"
    assert connector.profile_name == "analytics"
    assert connector.branch == "main"
    assert connector.target == "prod"
    assert connector.vars == {"country": "US"}
    assert connector.compile is False
    assert connector.profiles_dir == "/tmp/profiles"


def test_legacy_and_composable_dbt_configs_resolve_equivalent_connectors():
    legacy = dbt_module.DBTDatabricksSourceConfig(
        name="metrics_legacy",
        type="databricks_dbt",
        model_alias="metrics_model",
        model_unique_id="model.pkg.metrics_model",
        model_package_name="pkg",
        model_selector_name="metrics_model",
        package_url="https://github.com/org/repo.git",
        project_dir="/tmp/workspace",
        profile_name="analytics",
        branch="main",
        target="prod",
        vars={"country": "US"},
        compile=False,
        profiles_dir="/tmp/profiles",
    )
    composable = dbt_module.DBTSourceConfig(
        name="metrics_composable",
        type="dbt",
        model_alias="metrics_model",
        model_unique_id="model.pkg.metrics_model",
        model_package_name="pkg",
        model_selector_name="metrics_model",
        dbt={
            "package_url": "https://github.com/org/repo.git",
            "project_dir": "/tmp/workspace",
            "profile_name": "analytics",
            "branch": "main",
            "target": "prod",
            "vars": {"country": "US"},
            "compile": False,
            "profiles_dir": "/tmp/profiles",
        },
        warehouse={"type": "databricks"},
    )

    legacy_connector = legacy.get_connector()
    composable_connector = composable.get_connector()

    assert isinstance(legacy_connector, dbt_module.DBTDatabricksConnector)
    assert isinstance(composable_connector, dbt_module.DBTDatabricksConnector)

    parity_fields = (
        "model_alias",
        "model_unique_id",
        "model_package_name",
        "model_selector_name",
        "package_url",
        "project_dir",
        "profile_name",
        "branch",
        "target",
        "vars",
        "compile",
        "profiles_dir",
    )
    assert {field: getattr(legacy_connector, field) for field in parity_fields} == {
        field: getattr(composable_connector, field) for field in parity_fields
    }


def test_legacy_and_composable_dbt_configs_fetch_with_runtime_parity(monkeypatch):
    cache = get_data_cache()
    cache.enable()
    cache.clear()
    connector_calls: list[dict[str, Any]] = []

    def _fake_fetch(self):
        connector_calls.append(
            {
                "model_alias": self.model_alias,
                "model_unique_id": self.model_unique_id,
                "model_package_name": self.model_package_name,
                "model_selector_name": self.model_selector_name,
                "package_url": self.package_url,
                "project_dir": self.project_dir,
                "profile_name": self.profile_name,
                "branch": self.branch,
                "target": self.target,
                "vars": self.vars,
                "compile": self.compile,
                "profiles_dir": self.profiles_dir,
            }
        )
        return pd.DataFrame({"value": [1], "source": ["dbt"]})

    monkeypatch.setattr(dbt_module.DBTDatabricksConnector, "fetch_data", _fake_fetch)

    legacy = dbt_module.DBTDatabricksSourceConfig(
        name="metrics_legacy",
        type="databricks_dbt",
        model_alias="metrics_model",
        model_unique_id="model.pkg.metrics_model",
        model_package_name="pkg",
        model_selector_name="metrics_model",
        package_url="https://github.com/org/repo.git",
        project_dir="/tmp/workspace",
        profile_name="analytics",
        branch="main",
        target="prod",
        vars={"country": "US"},
        compile=False,
        profiles_dir="/tmp/profiles",
    )
    composable = dbt_module.DBTSourceConfig(
        name="metrics_composable",
        type="dbt",
        model_alias="metrics_model",
        model_unique_id="model.pkg.metrics_model",
        model_package_name="pkg",
        model_selector_name="metrics_model",
        dbt={
            "package_url": "https://github.com/org/repo.git",
            "project_dir": "/tmp/workspace",
            "profile_name": "analytics",
            "branch": "main",
            "target": "prod",
            "vars": {"country": "US"},
            "compile": False,
            "profiles_dir": "/tmp/profiles",
        },
        warehouse={"type": "databricks"},
    )

    legacy_first = legacy.fetch_data()
    legacy_second = legacy.fetch_data()
    composable_first = composable.fetch_data()
    composable_second = composable.fetch_data()

    assert legacy_first.to_dict(orient="records") == composable_first.to_dict(
        orient="records"
    )
    assert legacy_first is not legacy_second
    assert composable_first is not composable_second
    assert legacy_first.to_dict(orient="records") == legacy_second.to_dict(
        orient="records"
    )
    assert composable_first.to_dict(orient="records") == composable_second.to_dict(
        orient="records"
    )
    assert len(connector_calls) == 2
    assert connector_calls[0] == connector_calls[1]

    cache.clear()


def test_composable_dbt_source_config_fetch_data_routes_and_caches(monkeypatch):
    cache = get_data_cache()
    cache.enable()
    cache.clear()
    call_count = 0

    def _fake_fetch(self):
        nonlocal call_count
        call_count += 1
        return pd.DataFrame({"value": [1]})

    monkeypatch.setattr(dbt_module.DBTDatabricksConnector, "fetch_data", _fake_fetch)

    config = dbt_module.DBTSourceConfig(
        name="metrics",
        type="dbt",
        model_alias="metrics_model",
        dbt={
            "package_url": "https://github.com/org/repo.git",
            "project_dir": "/tmp/workspace",
        },
        warehouse={"type": "databricks"},
    )

    first = config.fetch_data()
    second = config.fetch_data()

    assert call_count == 1
    assert first is not second
    assert first.to_dict(orient="records") == second.to_dict(orient="records")

    cache.clear()


def test_composable_dbt_source_config_rejects_unknown_warehouse():
    with pytest.raises(ValidationError, match="Input should be"):
        dbt_module.DBTSourceConfig(
            name="metrics",
            type="dbt",
            model_alias="metrics_model",
            dbt={
                "package_url": "https://github.com/org/repo.git",
                "project_dir": "/tmp/workspace",
            },
            warehouse={"type": "snowflake"},
        )


def test_parallel_model_fetches_with_low_cache_do_not_delete_active_manifest(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_CACHE_MAX_ENTRIES", "1")

    package_url = "https://github.com/org/repo.git"
    workspace = str(tmp_path / "workspace")
    branch = "main"
    target = "prod"

    us_clone_dir = dbt_module._resolve_managed_clone_dir(
        project_dir=workspace,
        package_url=package_url,
        branch=branch,
        target=target,
        vars={"country": "US"},
        profiles_dir=None,
        profile_name=None,
    )
    us_compiled_dir = dbt_module._resolve_managed_compile_dir(
        us_clone_dir, target, {"country": "US"}
    )

    def _write_compiled_artifacts(clone_dir):
        _write_fake_dbt_project(clone_dir)
        (clone_dir / "target").mkdir(parents=True, exist_ok=True)
        (clone_dir / "target" / "compiled.sql").write_text("select 1 as answer")
        manifest = {
            "nodes": {
                "model.project.metrics": {
                    "resource_type": "model",
                    "alias": "metrics_model",
                    "compiled_path": "target/compiled.sql",
                }
            }
        }
        (clone_dir / "target" / "manifest.json").write_text(json.dumps(manifest))

    def _fake_clone(_url, clone_dir, _branch):
        _write_compiled_artifacts(clone_dir)

    class _Runner:
        def invoke(self, args):
            _copy_seeded_target_to_invocation(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    first_about_to_open = threading.Event()
    allow_first_open = threading.Event()
    us_manifest_path = (us_compiled_dir / "target" / "manifest.json").resolve()
    real_open = builtins.open

    def _open_proxy(file, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if "r" in mode:
            try:
                candidate = Path(file).resolve()
            except Exception:
                candidate = None
            if candidate == us_manifest_path and not first_about_to_open.is_set():
                first_about_to_open.set()
                assert allow_first_open.wait(5), "Timed out waiting for parallel fetch"
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _open_proxy)

    us_connector = dbt_module.DBTManifestConnector(
        package_url=package_url,
        project_dir=workspace,
        branch=branch,
        target=target,
        vars={"country": "US"},
    )
    ca_connector = dbt_module.DBTManifestConnector(
        package_url=package_url,
        project_dir=workspace,
        branch=branch,
        target=target,
        vars={"country": "CA"},
    )

    results: dict[str, str] = {}
    errors: list[Exception] = []

    def _run(name: str, connector: dbt_module.DBTManifestConnector) -> None:
        try:
            sql = connector.get_compiled_query("metrics_model")
            assert sql is not None
            results[name] = sql
        except Exception as error:  # pragma: no cover - assertion helper path
            errors.append(error)

    us_thread = threading.Thread(target=_run, args=("us", us_connector))
    us_thread.start()

    assert first_about_to_open.wait(5), "US fetch never reached manifest read"

    ca_thread = threading.Thread(target=_run, args=("ca", ca_connector))
    ca_thread.start()
    ca_thread.join(timeout=5)
    assert not ca_thread.is_alive(), "CA fetch did not complete in time"

    allow_first_open.set()
    us_thread.join(timeout=5)
    assert not us_thread.is_alive(), "US fetch did not complete in time"

    assert errors == []
    assert results["us"] == "select 1 as answer"
    assert results["ca"] == "select 1 as answer"


def test_in_use_cache_entry_is_not_evicted_or_recompiled_for_same_key(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_CACHE_MAX_ENTRIES", "1")
    clone_counts: Counter[str] = Counter()
    count_lock = threading.Lock()

    def _fake_clone(_url, clone_dir, _branch):
        with count_lock:
            clone_counts[str(clone_dir)] += 1
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    kwargs = {
        "package_url": "https://github.com/org/repo.git",
        "project_dir": str(tmp_path / "workspace"),
        "branch": "main",
        "target": "prod",
        "profiles_dir": None,
        "profile_name": None,
    }

    with dbt_module._compiled_project_lease(
        vars={"country": "US"}, **kwargs
    ) as us_path:
        _ = dbt_module._get_compiled_project(vars={"country": "CA"}, **kwargs)
        us_path_again = dbt_module._get_compiled_project(
            vars={"country": "US"}, **kwargs
        )

        with dbt_module._cache_lock:
            cached_paths = set(dbt_module._compiled_projects_cache.values())
            in_use_count = dbt_module._compiled_projects_in_use.get(us_path, 0)

        assert us_path_again == us_path
        assert us_path in cached_paths
        assert in_use_count > 0

    assert clone_counts[str(dbt_module._source_clone_dir(us_path))] == 1


def test_lease_release_reprunes_compiled_then_prepared_caches(monkeypatch, tmp_path):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_CACHE_MAX_ENTRIES", "1")

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    workspace = str(tmp_path / "workspace")
    first = dbt_module._get_compiled_project(
        package_url="https://github.com/org/repo-a.git",
        project_dir=workspace,
        branch="main",
        target="prod",
        vars=None,
        acquire_lease=True,
    )
    second = dbt_module._get_compiled_project(
        package_url="https://github.com/org/repo-b.git",
        project_dir=workspace,
        branch="main",
        target="prod",
        vars=None,
        acquire_lease=True,
    )

    assert len(dbt_module._compiled_projects_cache) == 2
    assert len(dbt_module._prepared_workspaces_cache) == 2

    dbt_module._release_compiled_project_lease(first)

    assert len(dbt_module._compiled_projects_cache) == 1
    assert len(dbt_module._prepared_workspaces_cache) == 1
    assert not first.exists()
    assert not dbt_module._source_clone_dir(first).exists()
    assert second.exists()

    dbt_module._release_compiled_project_lease(second)


def test_get_compiled_project_prunes_old_entries(monkeypatch, tmp_path):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_CACHE_MAX_ENTRIES", "2")

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    workspace = str(tmp_path / "workspace")
    paths = []
    for country in ("US", "CA", "MX"):
        path = dbt_module._get_compiled_project(
            package_url="https://github.com/org/repo.git",
            project_dir=workspace,
            branch="main",
            target="prod",
            vars={"country": country},
            profiles_dir=None,
            profile_name=None,
        )
        paths.append(path)
        time.sleep(0.01)

    assert len(dbt_module._compiled_projects_cache) == 2
    assert len(dbt_module._compiled_projects_last_access) == 2
    assert not paths[0].exists()
    assert paths[1].exists()
    assert paths[2].exists()


def test_cache_prunes_unreferenced_shared_workspaces(monkeypatch, tmp_path):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_CACHE_MAX_ENTRIES", "1")

    def _fake_clone(_url, clone_dir, _branch):
        _write_fake_dbt_project(clone_dir)

    class _Runner:
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)
    paths = []
    for package in ("repo-a", "repo-b"):
        paths.append(
            dbt_module._get_compiled_project(
                package_url=f"https://github.com/org/{package}.git",
                project_dir=str(tmp_path / "workspace"),
                branch="main",
                target="prod",
                vars={"country": "US"},
            )
        )

    assert len(dbt_module._compiled_projects_cache) == 1
    assert len(dbt_module._prepared_workspaces_cache) == 1
    assert not dbt_module._source_clone_dir(paths[0]).exists()
    assert dbt_module._source_clone_dir(paths[1]).exists()


def test_clone_repo_refuses_to_delete_unmanaged_existing_path(tmp_path):
    unmanaged_clone_dir = tmp_path / "existing_clone"
    unmanaged_clone_dir.mkdir()

    with pytest.raises(
        DataSourceError, match="Refusing to delete unmanaged DBT clone directory"
    ):
        dbt_module._clone_repo(
            "https://github.com/org/repo.git",
            unmanaged_clone_dir,
            branch=None,
        )


def test_clone_repo_allows_managed_clone_directory_cleanup(monkeypatch, tmp_path):
    clone_dir = dbt_module._resolve_managed_clone_dir(
        project_dir=str(tmp_path / "workspace"),
        package_url="https://github.com/org/repo.git",
        branch=None,
    )
    clone_dir.mkdir(parents=True, exist_ok=True)
    (clone_dir / "old_file.txt").write_text("stale")

    called = {}

    def _clone(url, destination, **kwargs):
        called["url"] = url
        called["destination"] = destination
        called["kwargs"] = kwargs
        destination.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(dbt_module.Repo, "clone_from", staticmethod(_clone))

    dbt_module._clone_repo(
        "https://github.com/org/repo.git",
        clone_dir,
        branch="main",
    )

    assert called["url"] == "https://github.com/org/repo.git"
    assert called["destination"] == clone_dir
    assert called["kwargs"] == {"branch": "main"}
