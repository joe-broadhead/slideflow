from slideflow.utilities.error_messages import safe_error_line


def test_safe_error_line_returns_first_line_for_multiline_errors():
    error = RuntimeError("first line\nsecond line")
    assert safe_error_line(error) == "first line"


def test_safe_error_line_handles_carriage_return_only_separator():
    error = RuntimeError("first line\rsecond line")
    assert safe_error_line(error) == "first line"


def test_safe_error_line_falls_back_to_exception_type_when_empty():
    error = RuntimeError("")
    assert safe_error_line(error) == "RuntimeError"
