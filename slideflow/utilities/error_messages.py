"""Helpers for concise, safe exception message rendering."""

from typing import Optional


def safe_error_line(error: BaseException, fallback: Optional[str] = None) -> str:
    """Return a non-empty single-line error message.

    - Collapses multi-line exception strings to the first line.
    - Falls back to exception class name when the message is empty.
    - Uses explicit fallback text when provided.
    """
    message = str(error).strip()
    if message:
        first_line = message.splitlines()[0].strip()
        if first_line:
            return first_line

    if fallback:
        return fallback

    return error.__class__.__name__
