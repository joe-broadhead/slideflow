import builtins
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import slideflow.data.connectors.dbt as dbt_module
from slideflow.utilities.exceptions import DataSourceError


def _reset_dbt_caches() -> None:
    dbt_module._compiled_projects_cache.clear()
    dbt_module._compiled_projects_last_access.clear()
    dbt_module._compilation_inflight.clear()
    dbt_module._compilation_failures.clear()
    dbt_module._compiled_projects_in_use.clear()
    dbt_module._pending_cleanup_dirs.clear()


def test_sanitize_git_url_redacts_embedded_credentials():
    url = "https://mytoken@github.com/org/repo.git"
    redacted = dbt_module._sanitize_git_url(url)

    assert redacted == "https://***@github.com/org/repo.git"


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


def test_resolve_managed_clone_dir_includes_compile_inputs_in_identity(tmp_path):
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

    assert baseline != different_target
    assert baseline != different_vars
    assert baseline != different_profile


def test_get_compiled_project_keeps_variant_clone_paths_isolated(monkeypatch, tmp_path):
    _reset_dbt_caches()

    def _fake_clone(_url, clone_dir, _branch):
        clone_dir.mkdir(parents=True, exist_ok=True)

    class _Runner:
        def invoke(self, _args):
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


def test_get_compiled_project_does_not_change_process_cwd(monkeypatch, tmp_path):
    _reset_dbt_caches()

    def _fake_clone(_url, clone_dir, _branch):
        clone_dir.mkdir(parents=True, exist_ok=True)

    invoke_args = []

    class _Runner:
        def invoke(self, args):
            invoke_args.append(args)
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
        clone_dir.mkdir(parents=True, exist_ok=True)
        (clone_dir / "profiles.yml").write_text("default: {}")

    invoke_args = []

    class _Runner:
        def invoke(self, args):
            invoke_args.append(args)
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
    assert str(compiled_path) in invoke_args[0]
    assert str(compiled_path) in invoke_args[1]


def test_get_compiled_project_raises_when_dbt_compile_reports_failure(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()

    def _fake_clone(_url, clone_dir, _branch):
        clone_dir.mkdir(parents=True, exist_ok=True)

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
        clone_dir.mkdir(parents=True, exist_ok=True)

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


def test_get_compiled_project_retries_after_failure_backoff_expiry(
    monkeypatch, tmp_path
):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_COMPILE_FAILURE_BACKOFF_S", "0")
    compile_calls = 0

    def _fake_clone(_url, clone_dir, _branch):
        clone_dir.mkdir(parents=True, exist_ok=True)

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
        clone_dir.mkdir(parents=True, exist_ok=True)

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
        clone_dir.mkdir(parents=True, exist_ok=True)

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
        clone_dir.mkdir(parents=True, exist_ok=True)

    class _Runner:
        def invoke(self, args):
            nonlocal compile_calls
            if args[0] == "compile":
                with counter_lock:
                    compile_calls += 1
                time.sleep(0.05)
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

    def _write_compiled_artifacts(clone_dir):
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
        def invoke(self, _args):
            return SimpleNamespace(success=True)

    monkeypatch.setattr(dbt_module, "_clone_repo", _fake_clone)
    monkeypatch.setattr(dbt_module, "dbtRunner", _Runner)

    first_about_to_open = threading.Event()
    allow_first_open = threading.Event()
    us_manifest_path = (us_clone_dir / "target" / "manifest.json").resolve()
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
    errors: list[BaseException] = []

    def _run(name: str, connector: dbt_module.DBTManifestConnector) -> None:
        try:
            sql = connector.get_compiled_query("metrics_model")
            assert sql is not None
            results[name] = sql
        except BaseException as error:  # pragma: no cover - assertion helper path
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
        clone_dir.mkdir(parents=True, exist_ok=True)

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

    assert clone_counts[str(us_path)] == 1


def test_get_compiled_project_prunes_old_entries(monkeypatch, tmp_path):
    _reset_dbt_caches()
    monkeypatch.setenv("SLIDEFLOW_DBT_CACHE_MAX_ENTRIES", "2")

    def _fake_clone(_url, clone_dir, _branch):
        clone_dir.mkdir(parents=True, exist_ok=True)

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
