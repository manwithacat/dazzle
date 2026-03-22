"""
Production mode helpers for dazzle serve --production.

Validates environment, configures structured logging, and provides
the production-specific settings that differ from dev/local modes.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime


def validate_production_env() -> tuple[str, str | None]:
    """Validate required environment variables for production mode.

    Returns:
        (database_url, redis_url) — redis_url is None if REDIS_URL not set.

    Raises:
        SystemExit: If DATABASE_URL is missing.
    """
    database_url = os.environ.get("DATABASE_URL", "")

    if not database_url:
        print(
            "--production requires DATABASE_URL environment variable. "
            "Set it to your PostgreSQL connection string.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Normalize postgres:// → postgresql:// (Heroku convention)
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        os.environ["DATABASE_URL"] = database_url

    redis_url = os.environ.get("REDIS_URL") or None

    return database_url, redis_url


class _JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for production."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def configure_production_logging() -> None:
    """Configure structured JSON logging for production.

    Replaces default handlers on the root logger with a single
    StreamHandler that emits JSON lines to stderr.
    """
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
