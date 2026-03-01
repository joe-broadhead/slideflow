import json
import os
from typing import Optional, Sequence

from slideflow.constants import Environment
from slideflow.utilities.exceptions import AuthenticationError
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)


def _normalize_credentials_source(value: Optional[str]) -> Optional[str]:
    """Normalize credential source values and treat sentinel nulls as missing."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if trimmed.lower() == "null":
        return None
    return trimmed


def handle_google_credentials(
    credentials: Optional[str] = None,
    env_var_names: Optional[Sequence[str]] = None,
) -> dict:
    """Handle Google credentials from config and environment variables."""

    clean_credentials = _normalize_credentials_source(credentials)

    env_sources = list(env_var_names or [Environment.GOOGLE_SLIDEFLOW_CREDENTIALS])

    creds_source = clean_credentials
    if not creds_source:
        for env_name in env_sources:
            env_value = _normalize_credentials_source(os.getenv(env_name))
            if env_value:
                creds_source = env_value
                break

    if not creds_source:
        expected_sources = ", ".join(env_sources)
        raise AuthenticationError(
            "Credentials not provided and no supported credential environment "
            f"variables were set ({expected_sources})."
        )

    if os.path.exists(creds_source) and os.path.isfile(creds_source):
        try:
            with open(creds_source, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise AuthenticationError(
                "Credentials file is not a valid JSON."
            ) from error
    else:
        try:
            return json.loads(creds_source)
        except json.JSONDecodeError as error:
            raise AuthenticationError(
                "Credentials string provided was not valid"
            ) from error
