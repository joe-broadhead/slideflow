from slideflow.utilities.redaction import REDACTED, redact_text, redact_value


def test_redact_value_recursively_masks_sensitive_keys_and_url_credentials():
    private_key = "-----BEGIN " "PRIVATE KEY-----abc-----END " "PRIVATE KEY-----"
    payload = {
        "safe": "visible",
        "api_token": "token-123",
        "nested": [
            {
                "client_email": "svc@example.com",
                "private_key": private_key,
                "url": "https://user@example.com/path?access_token=abc&x=1",
            }
        ],
    }

    redacted = redact_value(payload)

    assert redacted["safe"] == "visible"
    assert redacted["api_token"] == REDACTED
    assert redacted["nested"][0]["client_email"] == REDACTED
    assert redacted["nested"][0]["private_key"] == REDACTED
    assert redacted["nested"][0]["url"] == (
        f"https://***@example.com/path?access_token={REDACTED}&x=1"
    )


def test_redact_text_masks_auth_headers_bearer_tokens_and_key_value_pairs():
    message = (
        "Authorization: Bearer raw-token "
        "client_secret=secret-value "
        "url=https://token@example.com/repo.git"
    )

    redacted = redact_text(message)

    assert "raw-token" not in redacted
    assert "secret-value" not in redacted
    assert "token@example.com" not in redacted
    assert f"Bearer {REDACTED}" in redacted
    assert f"client_secret={REDACTED}" in redacted
    assert "https://***@example.com/repo.git" in redacted


def test_redact_text_masks_non_bearer_authorization_schemes():
    redacted = redact_text("Authorization: token gh_secret123")

    assert "gh_secret123" not in redacted
    assert f"Authorization: token {REDACTED}" == redacted


def test_redact_value_preserves_non_secret_operational_keys():
    redacted = redact_value({"run_key": "append-2026-06-28", "api_key": "secret"})

    assert redacted["run_key"] == "append-2026-06-28"
    assert redacted["api_key"] == REDACTED
