"""Regression guard for #1199 — framework-level log/error secret redaction.

Credentials that reach a log record (an API key in an exception string, a
bearer token in a traceback, a DB-URL password) must be masked before the
record is emitted.
"""

import logging

from dazzle.log_setup import SecretRedactionFilter, redact_secrets


def test_redacts_url_password() -> None:
    out = redact_secrets("connecting to postgresql://dazzle:s3cr3t@db.host:5432/app")
    assert "s3cr3t" not in out
    assert "postgresql://dazzle:" in out  # non-secret prefix preserved
    assert "@db.host:5432/app" in out


def test_redacts_bearer_token() -> None:
    out = redact_secrets("Authorization: Bearer abc123.def456-XYZ")
    assert "abc123.def456-XYZ" not in out
    assert "REDACTED" in out


def test_redacts_bare_bearer_token() -> None:
    # A bearer token outside an `Authorization:` key still gets masked.
    out = redact_secrets("retrying with bearer tok_9f8e7d6c5b")
    assert "tok_9f8e7d6c5b" not in out
    assert "bearer" in out.lower()


def test_redacts_key_value_secrets() -> None:
    for src, leak in (
        ("api_key=sk-livedeadbeef", "sk-livedeadbeef"),
        ('password: "hunter2"', "hunter2"),
        ("client_secret=zzz999", "zzz999"),
    ):
        out = redact_secrets(src)
        assert leak not in out, src
        assert "REDACTED" in out, src


def test_benign_message_unchanged() -> None:
    msg = "processed 42 records in 1.3s"
    assert redact_secrets(msg) == msg


def test_filter_redacts_record_message() -> None:
    record = logging.LogRecord(
        name="dazzle.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="auth failed for Bearer sk-shouldnotappear",
        args=(),
        exc_info=None,
    )
    assert SecretRedactionFilter().filter(record) is True
    assert "sk-shouldnotappear" not in record.getMessage()


def test_filter_redacts_args_interpolation() -> None:
    record = logging.LogRecord(
        name="dazzle.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="db url is %s",
        args=("postgres://u:leaked@h/d",),
        exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    assert "leaked" not in record.getMessage()
