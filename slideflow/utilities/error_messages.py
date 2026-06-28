"""Helpers for concise, safe exception message rendering."""

from typing import Optional

from slideflow.utilities.redaction import redact_text


def safe_error_line(
    error: BaseException, fallback: Optional[str] = None, *, redact: bool = False
) -> str:
    """Return a non-empty single-line error message.

    - Collapses multi-line exception strings to the first line.
    - Falls back to exception class name when the message is empty.
    - Uses explicit fallback text when provided.
    """
    message = str(error).strip()
    if message:
        first_line = message.splitlines()[0].strip()
        if first_line:
            return redact_text(first_line) if redact else first_line

    if fallback:
        return redact_text(fallback) if redact else fallback

    return error.__class__.__name__


def redacted_error_line(error: BaseException, fallback: Optional[str] = None) -> str:
    """Return a non-empty single-line error message with secrets redacted."""
    return safe_error_line(error, fallback=fallback, redact=True)
