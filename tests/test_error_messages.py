from slideflow.utilities.error_messages import redacted_error_line, safe_error_line


def test_safe_error_line_returns_first_line_for_multiline_errors():
    error = RuntimeError("first line\nsecond line")
    assert safe_error_line(error) == "first line"


def test_safe_error_line_handles_carriage_return_only_separator():
    error = RuntimeError("first line\rsecond line")
    assert safe_error_line(error) == "first line"


def test_safe_error_line_falls_back_to_exception_type_when_empty():
    error = RuntimeError("")
    assert safe_error_line(error) == "RuntimeError"


def test_safe_error_line_preserves_classifier_terms():
    error = RuntimeError("Authorization: Bearer raw-token")
    message = safe_error_line(error)

    assert "Bearer raw-token" in message


def test_redacted_error_line_redacts_secret_values():
    error = RuntimeError("Authorization: Bearer raw-token\nsecond line")
    message = redacted_error_line(error)

    assert "raw-token" not in message
    assert "Bearer ***REDACTED***" in message
