import pytest

import slideflow.data.connectors.dbt as dbt_module
from slideflow.utilities.exceptions import DataSourceError


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
