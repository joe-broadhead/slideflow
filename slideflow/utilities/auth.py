import json
import os
from typing import Optional, Sequence

from slideflow.constants import Environment
from slideflow.utilities.exceptions import AuthenticationError
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)


def handle_google_credentials(
    credentials: Optional[str] = None,
    env_var_names: Optional[Sequence[str]] = None,
) -> dict:
    """Handle Google credentials from config and environment variables."""

    clean_credentials = None if (credentials == "null") else credentials

    env_sources = list(env_var_names or [Environment.GOOGLE_SLIDEFLOW_CREDENTIALS])

    creds_source = clean_credentials
    if not creds_source:
        for env_name in env_sources:
            env_value = os.getenv(env_name)
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
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise AuthenticationError("Credentials file is not a valid JSON.")
    else:
        try:
            return json.loads(creds_source)
        except json.JSONDecodeError:
            raise AuthenticationError("Credentials string provided was not valid")
