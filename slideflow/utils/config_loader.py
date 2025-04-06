import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.auth.credentials import Credentials
from typing import Optional, List, Dict, Any, Callable

def get_credentials(path: Optional[str] = None, scopes: Optional[List[str]] = None) -> Credentials:
    """
    Loads Google service account credentials.

    Retrieves credentials from a service account JSON file either from the provided 
    path or from the `SERVICE_ACCOUNT_PATH` environment variable. The credentials are 
    scoped for Google APIs, such as Drive and Slides.

    Args:
        path: Optional path to the service account JSON key file. If not provided,
            the function uses the `SERVICE_ACCOUNT_PATH` environment variable.
        scopes: Optional list of OAuth scopes to request. Defaults to Drive and 
            Slides API scopes.

    Returns:
        Credentials: An authorized `google.auth.credentials.Credentials` object.
    """
    service_account_path = path or os.getenv('SERVICE_ACCOUNT_PATH')
    default_scopes = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/presentations'
    ]
    return service_account.Credentials.from_service_account_file(
        service_account_path,
        scopes = scopes or default_scopes
    )

def resolve_functions(obj: Any, registry: Dict[str, Callable]) -> Any:
    """
    Recursively replaces string references in a config object with callable functions.

    Traverses a nested structure (composed of dictionaries, lists, and strings)
    and replaces any string that matches a key in the provided registry with
    the corresponding function.

    This is commonly used to dynamically inject functions (like chart builders,
    preprocessors, or text formatters) based on string references in configuration files.

    Args:
        obj: The input structure, which may contain nested dictionaries, lists,
            and strings referencing callable names.
        registry: A dictionary mapping string keys to actual callable functions.

    Returns:
        Any: The input structure with all matching string references replaced
        with callables from the registry.
    """
    if isinstance(obj, dict):
        return {k: resolve_functions(v, registry) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [resolve_functions(i, registry) for i in obj]
    elif isinstance(obj, str) and obj in registry:
        return registry[obj]
    else:
        return obj

def build_services(credentials: Optional[Credentials] = None) -> Dict[str, Any]:
    """
    Initializes and returns authenticated Google Drive and Slides service clients.

    Uses the provided credentials or defaults to loading them from the environment
    or a specified service account file. Returns both service clients in a dictionary
    for easy access throughout the application.

    Args:
        credentials: Optional `google.oauth2.service_account.Credentials` object.
            If not provided, credentials will be loaded using `get_credentials()`.

    Returns:
        dict: A dictionary containing:
            - 'drive_service': Authenticated Google Drive API client.
            - 'slides_service': Authenticated Google Slides API client.
    """
    credentials = credentials or get_credentials()
    drive_service = build('drive', 'v3', credentials = credentials)
    slides_service = build('slides', 'v1', credentials = credentials)
    return {'drive_service': drive_service, 'slides_service': slides_service}
