"""Error visibility and redaction tests."""

from __future__ import annotations

import logging
from pathlib import Path

from archivestudio.core.errors import classify_exception, redact_secrets
from archivestudio.core.logging import configure_logging


def test_redact_secrets_removes_common_api_key_shapes() -> None:
    text = (
        "openai=sk-abcdefghijklmnopqrstuvwxyz "
        "anthropic=sk-ant-abcdefghijklmnopqrstuvwxyz "
        "google=AIzaabcdefghijklmnopqrstuvwxyz12345 "
        "Authorization: Bearer secret-token-value"
    )

    redacted = redact_secrets(text)

    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "secret-token-value" not in redacted
    assert redacted.count("[redacted]") >= 4


def test_classify_authentication_error() -> None:
    report = classify_exception(RuntimeError("401 invalid API key sk-testsecret123456"))

    assert report.category == "API key / authentication"
    assert "rejected the API key" in report.summary
    assert "sk-testsecret" not in report.technical_detail


def test_classify_rate_limit_error() -> None:
    report = classify_exception(RuntimeError("429 too many requests, rate limit exceeded"))

    assert report.category == "Rate limit"
    assert "rate limiting" in report.summary


def test_classify_translation_without_source_text() -> None:
    report = classify_exception(ValueError("No pages matched the translation request"))

    assert report.category == "No translatable text"
    assert "text to translate" in report.summary
    assert "Original, or Corrected text" in report.suggestion
    assert "will not overwrite" in report.suggestion


def test_logging_formatter_redacts_secrets(tmp_path: Path) -> None:
    log_file = tmp_path / "archivestudio.log"
    configure_logging(log_file=log_file)

    logging.getLogger("archivestudio.test").error("bad key sk-supersecret123456789")

    text = log_file.read_text(encoding="utf-8")
    assert "sk-supersecret" not in text
    assert "[redacted]" in text
