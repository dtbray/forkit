"""Exercise real stdlib and structlog records through the configured formatter."""

import json
import logging

import pytest
import structlog

from forkit.logging import configure_logging


@pytest.fixture
def logging_configuration():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    config = structlog.get_config().copy()
    try:
        yield
    finally:
        for handler in root.handlers:
            if handler not in handlers:
                handler.close()
        root.handlers = handlers
        root.setLevel(level)
        structlog.configure(**config)


def test_stdlib_and_structlog_emit_redacted_json(logging_configuration, capsys):
    configure_logging()
    secret = "sk-ant-0123456789SECRET"
    foreign = logging.getLogger("apscheduler.scheduler")
    foreign.info("Scheduled job with %s", secret)
    structured = structlog.get_logger("forkit.test")
    headers = {"Authorization": "Bearer private-token"}
    structured.info("import", headers=headers, nested=[{"x-api-key": secret}], value=secret)
    try:
        raise ValueError(f"failed with {secret}")
    except ValueError:
        foreign.exception("Job failed")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Logging error" not in captured.err
    assert secret not in captured.err
    assert "private-token" not in captured.err
    records = [json.loads(line) for line in captured.err.splitlines()]
    assert len(records) == 3
    assert records[0]["logger"] == "apscheduler.scheduler"
    assert records[0]["event"] == "Scheduled job with [REDACTED]"
    assert records[0]["level"] == "info"
    assert records[1]["logger"] == "forkit.test"
    assert records[1]["headers"]["Authorization"] == "[REDACTED]"
    assert records[1]["nested"] == [{"x-api-key": "[REDACTED]"}]
    assert headers == {"Authorization": "Bearer private-token"}
    assert "ValueError: failed with [REDACTED]" in records[2]["exception"]
    assert records[2]["level"] == "error"
    assert all(record["timestamp"] for record in records)
    assert all("_record" not in record and "_from_structlog" not in record for record in records)
