from __future__ import annotations

from pathlib import Path

from scripts.ci.check_secret_hygiene import scan_paths


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_secret_hygiene_rejects_tracked_credential_filenames(tmp_path: Path) -> None:
    credentials = _write(
        tmp_path / "google-credentials.json",
        '{"type": "service_account", "private_key": "fake"}',
    )

    findings = scan_paths([credentials], root=tmp_path)

    assert any(
        "tracked credential/key filename" in finding.reason for finding in findings
    )


def test_secret_hygiene_rejects_private_keys_and_provider_tokens(
    tmp_path: Path,
) -> None:
    private_key = "-----BEGIN " "PRIVATE KEY-----abc-----END " "PRIVATE KEY-----"
    client_secret = "GOCSPX-" + ("a" * 32)
    api_key = "sk-proj-" + ("b" * 32)
    config = _write(
        tmp_path / "config.yml",
        "\n".join(
            [
                f'private_key: "{private_key}"',
                f'client_secret: "{client_secret}"',
                f"api_key: '{api_key}'",
            ]
        ),
    )

    findings = scan_paths([config], root=tmp_path)
    reasons = {finding.reason for finding in findings}

    assert "private key block" in reasons
    assert "Google OAuth client secret" in reasons
    assert "OpenAI API key" in reasons


def test_secret_hygiene_allows_documented_placeholders(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "example.yml",
        "\n".join(
            [
                'credentials: "/absolute/path/service-account.json"',
                'client_secret: "secret-value"',
                'api_key: "<provider-api-key>"',
                'refresh_token: "${REFRESH_TOKEN}"',
            ]
        ),
    )

    assert scan_paths([config], root=tmp_path) == []
