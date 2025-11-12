
import os
import json
from slideflow.utilities.exceptions import AuthenticationError
from slideflow.constants import Environment
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)

def handle_google_credentials(credentials: str = None) -> dict:
    """Handle Google credentials from config or environment variable."""

    clean_credentials = None if ( credentials == 'null' ) else credentials

    creds_source = clean_credentials or os.getenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS)

    if not creds_source:
        raise AuthenticationError(
            f"Credentials not provided and {Environment.GOOGLE_SLIDEFLOW_CREDENTIALS} environment variable not set."
        )

    if os.path.exists(creds_source) and os.path.isfile(creds_source):
        try:
            with open(creds_source, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise AuthenticationError("Credentials file is not a valid JSON.")
    else:
        try:
            return json.loads(creds_source)
        except json.JSONDecodeError:
            raise AuthenticationError("Credentials string provided was not valid")
