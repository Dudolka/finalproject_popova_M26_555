"""Centralized logging configuration for ValutaTrade Hub."""

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "valutatrade_hub"

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

SENSITIVE_PATTERNS = (
    re.compile(
        r"(?i)\b(password|passwd|api[_-]?key|token|secret)"
        r"\s*[:=]\s*([^\s,;]+)"
    ),
    re.compile(r"(?i)\bbearer\s+\S+"),
)


class SensitiveDataFilter(logging.Filter):
    """Redact common credential patterns from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitize a log record before it is written."""
        message = record.getMessage()

        for pattern in SENSITIVE_PATTERNS:
            if pattern.pattern.endswith(r"\S+"):
                message = pattern.sub(
                    "Bearer [REDACTED]",
                    message,
                )
            else:
                message = pattern.sub(
                    lambda match: f"{match.group(1)}=[REDACTED]",
                    message,
                )

        record.msg = message
        record.args = ()

        return True


def setup_logging(
    log_dir: str | Path = "logs",
    level: int = logging.INFO,
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
) -> logging.Logger:
    """Configure console and rotating file logging.

    Args:
        log_dir: Directory for log files.
        level: Minimum logging level.
        max_bytes: Maximum size of the active log file.
        backup_count: Number of rotated backup files.

    Returns:
        Configured application logger.
    """
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool):
        raise TypeError("max_bytes должен быть целым числом")

    if max_bytes <= 0:
        raise ValueError("max_bytes должен быть положительным")

    if not isinstance(backup_count, int) or isinstance(backup_count, bool):
        raise TypeError("backup_count должен быть целым числом")

    if backup_count < 0:
        raise ValueError("backup_count не может быть отрицательным")

    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    # Remove only handlers created by this configuration function.
    for handler in list(logger.handlers):
        if getattr(handler, "_valutatrade_managed", False):
            logger.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SensitiveDataFilter())
    console_handler._valutatrade_managed = True

    file_handler = RotatingFileHandler(
        filename=directory / "valutatrade.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SensitiveDataFilter())
    file_handler._valutatrade_managed = True

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
