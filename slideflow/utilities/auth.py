
import os
import json
from slideflow.utilities.exceptions import AuthenticationError
from slideflow.constants import Environment

def handle_google_credentials(credentials: str = None) -> dict:
    """Handle Google credentials from config or environment variable.

    Args:
        credentials: The credentials from the config.

    Returns:
        The valid credentials.

    Raises:
        AuthenticationError: If the credentials are not valid.
    """
    if credentials is None:
        environment_credentials = os.getenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS)
        if environment_credentials is None:
            raise AuthenticationError(f"Credentials not provided and {Environment.GOOGLE_SLIDEFLOW_CREDENTIALS} environment variable not set.")
        elif os.path.exists(environment_credentials) and os.path.isfile(environment_credentials):
            try:
                with open(environment_credentials, 'r') as f:
                    parsed_credentials = json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise AuthenticationError("Credentials file is not a valid JSON.")
        else:
            try:
                parsed_credentials = json.loads(environment_credentials)
            except json.JSONDecodeError:
                raise AuthenticationError("Credentials string provided was not valid")
    elif os.path.exists(credentials) and os.path.isfile(credentials):
        try:
            with open(credentials, 'r') as f:
                parsed_credentials= json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise AuthenticationError("Credentials file is not a valid JSON.")
    else:
        try:
            parsed_credentials = json.loads(credentials)
        except json.JSONDecodeError:
            raise AuthenticationError("Credentials string provided was not valid")
    
    return parsed_credentials
