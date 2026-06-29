"""Shared presentation-layer rate limiter helpers.

This module hosts provider-agnostic rate limiter singletons used across
presentation runtime components to avoid cross-layer imports.
"""

import threading
from typing import Dict

from slideflow.utilities.rate_limiter import RateLimiter

_google_api_rate_limiters: Dict[float, RateLimiter] = {}
_google_api_rate_limiter_lock = threading.Lock()


def get_google_api_rate_limiter(rps: float, force_update: bool = False) -> RateLimiter:
    """Get or create a Google API rate limiter keyed by configured rate."""
    rps_key = float(rps)
    with _google_api_rate_limiter_lock:
        if force_update or rps_key not in _google_api_rate_limiters:
            _google_api_rate_limiters[rps_key] = RateLimiter(rps_key)
        return _google_api_rate_limiters[rps_key]


def reset_google_api_rate_limiter() -> None:
    """Reset cached Google API limiters for deterministic tests."""
    with _google_api_rate_limiter_lock:
        _google_api_rate_limiters.clear()
