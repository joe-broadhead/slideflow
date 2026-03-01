"""Shared presentation-layer rate limiter helpers.

This module hosts provider-agnostic rate limiter singletons used across
presentation runtime components to avoid cross-layer imports.
"""

import threading
from typing import Optional

from slideflow.utilities.rate_limiter import RateLimiter

_google_api_rate_limiter: Optional[RateLimiter] = None
_google_api_rate_limiter_lock = threading.Lock()


def get_google_api_rate_limiter(rps: float, force_update: bool = False) -> RateLimiter:
    """Get or create the shared Google API rate limiter."""
    global _google_api_rate_limiter
    with _google_api_rate_limiter_lock:
        if _google_api_rate_limiter is None:
            _google_api_rate_limiter = RateLimiter(rps)
        elif force_update:
            _google_api_rate_limiter.set_rate(rps)
        return _google_api_rate_limiter


def reset_google_api_rate_limiter() -> None:
    """Reset shared Google API limiter for deterministic tests."""
    global _google_api_rate_limiter
    with _google_api_rate_limiter_lock:
        _google_api_rate_limiter = None
