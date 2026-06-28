import json
import os
import warnings
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from slideflow.constants import Environment
from slideflow.utilities.exceptions import AuthenticationError
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class GoogleCredentialsLoadResult:
    """Resolved Google credentials plus non-sensitive source metadata."""

    credentials: Any
    source_type: str
    source_name: str
    project_id: Optional[str] = None


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


def _google_auth_source_type_for_env(env_name: str) -> str:
    normalized = env_name.strip().lower()
    return f"env_{normalized}"


def _source_looks_like_file(value: str) -> bool:
    return os.path.exists(value) and os.path.isfile(value)


def resolve_google_credentials_source(
    credentials: Optional[str] = None,
    env_var_names: Optional[Sequence[str]] = None,
    *,
    include_adc: bool = True,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve the configured Google credential source without loading secrets.

    Returns ``(source_value, source_type, source_name)`` where ``source_type`` is
    suitable for diagnostics and intentionally avoids including credential
    payloads or local file paths.
    """

    clean_credentials = _normalize_credentials_source(credentials)
    if clean_credentials:
        return (
            clean_credentials,
            (
                "explicit_path"
                if _source_looks_like_file(clean_credentials)
                else "explicit_json"
            ),
            "provider.config.credentials",
        )

    env_sources = list(env_var_names or [Environment.GOOGLE_SLIDEFLOW_CREDENTIALS])
    for env_name in env_sources:
        env_value = _normalize_credentials_source(os.getenv(env_name))
        if env_value:
            return env_value, _google_auth_source_type_for_env(env_name), env_name

    if include_adc:
        adc_path = _normalize_credentials_source(
            os.getenv(Environment.GOOGLE_APPLICATION_CREDENTIALS)
        )
        if adc_path:
            return (
                adc_path,
                _google_auth_source_type_for_env(
                    Environment.GOOGLE_APPLICATION_CREDENTIALS
                ),
                Environment.GOOGLE_APPLICATION_CREDENTIALS,
            )
        return None, "adc_default", "google.auth.default"

    return None, None, None


def describe_google_credentials_source(
    credentials: Optional[str] = None,
    env_var_names: Optional[Sequence[str]] = None,
    *,
    include_adc: bool = True,
) -> str:
    """Return the non-sensitive Google credential source label."""

    _, source_type, _ = resolve_google_credentials_source(
        credentials,
        env_var_names,
        include_adc=include_adc,
    )
    return source_type or "missing"


def _load_google_credentials_from_mapping(
    google_auth: Any,
    payload: dict[str, Any],
    scopes: Optional[Sequence[str]],
    *,
    allow_generic_loader: bool,
) -> tuple[Any, Optional[str]]:
    credential_type = str(payload.get("type", "")).strip()
    if credential_type == "service_account":
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(
            payload,
            scopes=list(scopes or []),
        )
        project_id = getattr(credentials, "project_id", None) or payload.get(
            "project_id"
        )
        return credentials, project_id if isinstance(project_id, str) else None

    if not allow_generic_loader:
        raise AuthenticationError(
            "Non-service-account Google credential JSON contains active "
            "credential configuration and must be supplied through trusted "
            "environment credentials, such as GOOGLE_APPLICATION_CREDENTIALS "
            "or provider credential environment variables."
        )

    # google-auth's generic loader is the supported cross-type path for
    # external_account/WIF variants. It is only enabled for trusted runtime
    # sources such as environment variables and ADC files, not repository YAML.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The load_credentials_from_dict method is deprecated.*",
            category=DeprecationWarning,
        )
        return google_auth.load_credentials_from_dict(
            payload,
            scopes=list(scopes or []),
        )


def _load_google_credentials_from_file(
    google_auth: Any,
    filename: str,
    scopes: Optional[Sequence[str]],
    *,
    allow_generic_loader: bool,
) -> tuple[Any, Optional[str]]:
    try:
        with open(filename, "r", encoding="utf-8") as credential_file:
            payload = json.load(credential_file)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise AuthenticationError("Credentials file is not a valid JSON.") from error

    if not isinstance(payload, dict):
        raise AuthenticationError("Credentials file must contain a JSON object.")

    return _load_google_credentials_from_mapping(
        google_auth,
        payload,
        scopes,
        allow_generic_loader=allow_generic_loader,
    )


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


def load_google_credentials(
    credentials: Optional[str] = None,
    scopes: Optional[Sequence[str]] = None,
    env_var_names: Optional[Sequence[str]] = None,
) -> GoogleCredentialsLoadResult:
    """Load Google credentials from explicit config, env vars, or ADC.

    The precedence is:

    1. ``provider.config.credentials`` as a file path or raw JSON
    2. provider-specific credential env vars, then shared Slideflow env vars
    3. ``GOOGLE_APPLICATION_CREDENTIALS`` file path
    4. ``google.auth.default``

    Service-account JSON can be loaded from explicit config. Generic Google auth
    payloads such as external-account / Workload Identity Federation JSON are
    loaded only from trusted runtime sources such as environment variables,
    ``GOOGLE_APPLICATION_CREDENTIALS``, or runtime ADC.
    """

    try:
        import google.auth
    except ImportError as error:  # pragma: no cover - dependency is core runtime
        raise AuthenticationError(
            "google-auth is required for Google provider credentials."
        ) from error

    source_value, source_type, source_name = resolve_google_credentials_source(
        credentials,
        env_var_names,
        include_adc=True,
    )
    if source_type is None or source_name is None:
        expected_sources = ", ".join(
            list(env_var_names or [Environment.GOOGLE_SLIDEFLOW_CREDENTIALS])
            + [Environment.GOOGLE_APPLICATION_CREDENTIALS, "ADC default credentials"]
        )
        raise AuthenticationError(
            "Credentials not provided and no supported credential environment "
            f"variables were set ({expected_sources})."
        )

    try:
        allow_generic_loader = source_name != "provider.config.credentials"
        if source_type == "explicit_path":
            assert source_value is not None
            loaded_credentials, project_id = _load_google_credentials_from_file(
                google.auth,
                source_value,
                scopes,
                allow_generic_loader=allow_generic_loader,
            )
        elif source_type == "explicit_json":
            try:
                payload = json.loads(source_value or "")
            except json.JSONDecodeError as error:
                raise AuthenticationError(
                    "Credentials string provided was not valid"
                ) from error
            if not isinstance(payload, dict):
                raise AuthenticationError(
                    "Credentials string must contain a JSON object."
                )
            loaded_credentials, project_id = _load_google_credentials_from_mapping(
                google.auth,
                payload,
                scopes,
                allow_generic_loader=allow_generic_loader,
            )
        elif source_type == _google_auth_source_type_for_env(
            Environment.GOOGLE_APPLICATION_CREDENTIALS
        ):
            assert source_value is not None
            loaded_credentials, project_id = _load_google_credentials_from_file(
                google.auth,
                source_value,
                scopes,
                allow_generic_loader=allow_generic_loader,
            )
        elif source_type == "adc_default":
            loaded_credentials, project_id = google.auth.default(
                scopes=list(scopes or [])
            )
        else:
            if source_value and _source_looks_like_file(source_value):
                loaded_credentials, project_id = _load_google_credentials_from_file(
                    google.auth,
                    source_value,
                    scopes,
                    allow_generic_loader=allow_generic_loader,
                )
            else:
                try:
                    payload = json.loads(source_value or "")
                except json.JSONDecodeError as error:
                    raise AuthenticationError(
                        "Credentials string provided was not valid"
                    ) from error
                if not isinstance(payload, dict):
                    raise AuthenticationError(
                        "Credentials string must contain a JSON object."
                    )
                loaded_credentials, project_id = _load_google_credentials_from_mapping(
                    google.auth,
                    payload,
                    scopes,
                    allow_generic_loader=allow_generic_loader,
                )
    except AuthenticationError:
        raise
    except Exception as error_msg:
        raise AuthenticationError(
            f"Credentials authentication failed: {error_msg}"
        ) from error_msg

    return GoogleCredentialsLoadResult(
        credentials=loaded_credentials,
        source_type=source_type,
        source_name=source_name,
        project_id=project_id,
    )
