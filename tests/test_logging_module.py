from __future__ import annotations

import logging

import slideflow.utilities.logging as logging_module


def test_setup_logging_uses_expected_defaults_and_force(monkeypatch):
    calls = []
    slideflow_logger = logging.getLogger("slideflow")
    original_level = slideflow_logger.level

    monkeypatch.setattr(
        logging_module.logging,
        "basicConfig",
        lambda *args, **kwargs: calls.append(kwargs),
    )

    try:
        logging_module.setup_logging(level="warning", enable_debug=True)

        assert calls
        kwargs = calls[0]
        assert kwargs["force"] is True
        assert kwargs["level"] == logging.WARNING
        assert "%(name)s" in kwargs["format"]
        assert slideflow_logger.level == logging.DEBUG
    finally:
        slideflow_logger.setLevel(original_level)


def test_setup_logging_without_module_names_uses_simple_format(monkeypatch):
    calls = []
    monkeypatch.setattr(
        logging_module.logging,
        "basicConfig",
        lambda *args, **kwargs: calls.append(kwargs),
    )

    logging_module.setup_logging(level="INFO", show_module_names=False)

    assert calls
    assert calls[0]["format"] == "%(asctime)s - %(levelname)s - %(message)s"


def test_log_performance_formats_duration_and_context(monkeypatch):
    messages = []
    fake_logger = type(
        "FakeLogger", (), {"info": lambda self, msg: messages.append(msg)}
    )()
    monkeypatch.setattr(logging_module, "get_logger", lambda _name: fake_logger)

    logging_module.log_performance("build", 1.2345, rows=10, source="csv")

    assert messages == ["build completed in 1.23s (rows=10, source=csv)"]


def test_log_data_operation_formats_records_and_context(monkeypatch):
    messages = []
    fake_logger = type(
        "FakeLogger", (), {"info": lambda self, msg: messages.append(msg)}
    )()
    monkeypatch.setattr(logging_module, "get_logger", lambda _name: fake_logger)

    logging_module.log_data_operation(
        "fetch", "csv", record_count=2, file_path="/tmp/a.csv"
    )

    assert messages == ["fetch from csv (2 records) [file_path=/tmp/a.csv]"]


def test_log_api_operation_uses_status_symbol_and_level(monkeypatch):
    calls = []

    class FakeLogger:
        def log(self, level, message):
            calls.append((level, message))

    monkeypatch.setattr(logging_module, "get_logger", lambda _name: FakeLogger())

    logging_module.log_api_operation(
        "google_slides", "batch_update", success=True, duration=0.5
    )
    logging_module.log_api_operation(
        "google_slides", "batch_update", success=False, error="timeout"
    )

    assert calls[0] == (logging.INFO, "✓ google_slides.batch_update (0.50s)")
    assert calls[1] == (
        logging.ERROR,
        "✗ google_slides.batch_update [error=timeout]",
    )
