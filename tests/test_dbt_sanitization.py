from pathlib import Path

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
