"""Central redaction helpers for logs, errors, and machine-readable output."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "***REDACTED***"

_SENSITIVE_KEY_NAMES = {
    "access_token",
    "api_key",
    "authorization",
    "auth_token",
    "client_email",
    "client_secret",
    "credential",
    "credentials",
    "credentials_json",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "service_account",
    "token",
}

_NON_SECRET_KEY_NAMES = {
    "run_key",
}

_SENSITIVE_URL_PARAMS = {
    "access_token",
    "api_key",
    "auth_token",
    "client_secret",
    "credential",
    "credentials",
    "key",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}

_URL_USERINFO_RE = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<userinfo>[^/@\s]+@)"
)
_URL_QUERY_SECRET_RE = re.compile(
    r"(?P<prefix>[?&](?:"
    + "|".join(sorted(re.escape(param) for param in _SENSITIVE_URL_PARAMS))
    + r")=)(?P<value>[^&#\s]+)",
    re.IGNORECASE,
)
_AUTH_HEADER_RE = re.compile(
    r"\b(?P<prefix>authorization\s*[:=]\s*)"
    r"(?:(?P<scheme>[A-Za-z][A-Za-z0-9._-]*)\s+)?(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(
    r"\b(?P<scheme>bearer|basic)\s+(?P<value>[A-Za-z0-9._~+/\-=]+)",
    re.IGNORECASE,
)
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_SENSITIVE_FIELD_RE = re.compile(
    r"(?P<prefix>\b(?:[A-Z0-9_]*TOKEN|[A-Z0-9_]*SECRET|[A-Z0-9_]*KEY|"
    r"access_token|api_key|auth_token|client_email|client_secret|"
    r"credentials?|credentials_json|password|private_key|refresh_token)"
    r"\b\s*[:=]\s*)(?P<quote>[\"']?)(?P<value>[^&\"'\s,;)}]+)(?P=quote)",
    re.IGNORECASE,
)


def _normalize_key(key: object) -> str:
    key_text = str(key).strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", key_text).strip("_")
    return normalized


def is_sensitive_key(key: object) -> bool:
    """Return whether a mapping key conventionally carries sensitive data."""
    normalized = _normalize_key(key)
    if normalized in _NON_SECRET_KEY_NAMES:
        return False
    if normalized in _SENSITIVE_KEY_NAMES:
        return True
    return normalized.endswith(("_token", "_secret", "_key", "_credentials"))


def redact_text(text: str) -> str:
    """Redact common secret patterns in free-form text."""
    redacted = _PRIVATE_KEY_BLOCK_RE.sub(REDACTED, text)
    redacted = _URL_USERINFO_RE.sub(
        lambda match: f"{match.group('scheme')}***@", redacted
    )
    redacted = _URL_QUERY_SECRET_RE.sub(
        lambda match: f"{match.group('prefix')}{REDACTED}",
        redacted,
    )
    redacted = _AUTH_HEADER_RE.sub(
        _redact_authorization_header,
        redacted,
    )
    redacted = _BEARER_RE.sub(
        lambda match: f"{match.group('scheme')} {REDACTED}",
        redacted,
    )
    redacted = _SENSITIVE_FIELD_RE.sub(
        lambda match: (
            f"{match.group('prefix')}{match.group('quote')}"
            f"{REDACTED}{match.group('quote')}"
        ),
        redacted,
    )
    return redacted


def _redact_authorization_header(match: re.Match[str]) -> str:
    scheme = match.group("scheme")
    if scheme:
        return f"{match.group('prefix')}{scheme} {REDACTED}"
    return f"{match.group('prefix')}{REDACTED}"


def redact_value(value: Any, *, key: object | None = None) -> Any:
    """Recursively redact sensitive values while preserving payload shape."""
    if key is not None and is_sensitive_key(key):
        return None if value is None else REDACTED

    if isinstance(value, Mapping):
        return {
            mapping_key: redact_value(mapping_value, key=mapping_key)
            for mapping_key, mapping_value in value.items()
        }

    if isinstance(value, list):
        return [redact_value(item) for item in value]

    if isinstance(value, tuple):
        return [redact_value(item) for item in value]

    if isinstance(value, str):
        return redact_text(value)

    return value
