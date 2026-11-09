"""Tests for logging configuration and decorators."""

import logging
import tempfile
import unittest
from pathlib import Path

from valutatrade_hub.decorators import log_operation
from valutatrade_hub.logging_config import (
    SensitiveDataFilter,
    setup_logging,
)


class TestLoggingConfig(unittest.TestCase):
    """Verify safe and repeatable logging configuration."""

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temporary_directory.name)

    def tearDown(self):
        logger = logging.getLogger("valutatrade_hub")

        for handler in list(logger.handlers):
            if getattr(handler, "_valutatrade_managed", False):
                logger.removeHandler(handler)
                handler.close()

        logger.propagate = True
        self.temporary_directory.cleanup()

    def test_log_file_creation(self):
        """Create an application log file."""
        setup_logging(self.log_dir)

        self.assertTrue((self.log_dir / "valutatrade.log").exists())

    def test_write_log_message(self):
        """Write log events to the file."""
        logger = setup_logging(self.log_dir)
        logger.info("Проверка журнала")

        content = (self.log_dir / "valutatrade.log").read_text(encoding="utf-8")

        self.assertIn("Проверка журнала", content)

    def test_password_redaction(self):
        """Do not expose a password in logs."""
        logger = setup_logging(self.log_dir)
        logger.info("password=topsecret123")

        content = (self.log_dir / "valutatrade.log").read_text(encoding="utf-8")

        self.assertNotIn("topsecret123", content)
        self.assertIn("[REDACTED]", content)

    def test_api_key_redaction(self):
        """Do not expose an API key in logs."""
        logger = setup_logging(self.log_dir)
        logger.info("api_key=secret-value")

        content = (self.log_dir / "valutatrade.log").read_text(encoding="utf-8")

        self.assertNotIn("secret-value", content)
        self.assertIn("[REDACTED]", content)

    def test_bearer_token_redaction(self):
        """Remove authorization bearer tokens."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Authorization: Bearer abc123",
            args=(),
            exc_info=None,
        )

        SensitiveDataFilter().filter(record)

        self.assertNotIn("abc123", record.getMessage())
        self.assertIn("[REDACTED]", record.getMessage())

    def test_repeated_setup(self):
        """Do not duplicate managed logging handlers."""
        setup_logging(self.log_dir)
        logger = setup_logging(self.log_dir)

        managed = [
            handler
            for handler in logger.handlers
            if getattr(
                handler,
                "_valutatrade_managed",
                False,
            )
        ]

        self.assertEqual(len(managed), 2)

    def test_invalid_max_bytes(self):
        """Reject invalid log file size."""
        with self.assertRaises(ValueError):
            setup_logging(self.log_dir, max_bytes=0)

    def test_invalid_backup_count(self):
        """Reject negative backup counts."""
        with self.assertRaises(ValueError):
            setup_logging(self.log_dir, backup_count=-1)

    def test_log_rotation(self):
        """Rotate files when the size limit is reached."""
        logger = setup_logging(
            self.log_dir,
            max_bytes=200,
            backup_count=2,
        )

        for number in range(20):
            logger.info(
                "Сообщение %s: %s",
                number,
                "x" * 80,
            )

        self.assertTrue((self.log_dir / "valutatrade.log.1").exists())


class TestLogOperation(unittest.TestCase):
    """Verify the safe operation logging decorator."""

    def test_successful_function(self):
        """Preserve function results."""

        @log_operation
        def add(first, second):
            return first + second

        self.assertEqual(add(2, 3), 5)

    def test_function_metadata(self):
        """Preserve function name and documentation."""

        @log_operation
        def example():
            """Example operation."""
            return True

        self.assertEqual(example.__name__, "example")
        self.assertEqual(
            example.__doc__,
            "Example operation.",
        )

    def test_exception_propagation(self):
        """Propagate errors to the calling code."""

        @log_operation
        def fail():
            raise ValueError("Ошибка операции")

        with self.assertRaises(ValueError):
            fail()

    def test_do_not_log_password(self):
        """Never record function arguments."""

        @log_operation
        def authenticate(password):
            return bool(password)

        with self.assertLogs(
            "valutatrade_hub.decorators",
            level="INFO",
        ) as captured:
            authenticate("super-secret-password")

        output = "\n".join(captured.output)

        self.assertNotIn(
            "super-secret-password",
            output,
        )

    def test_do_not_log_exception_message(self):
        """Log exception types without sensitive messages."""

        @log_operation
        def fail():
            raise RuntimeError("api_key=very-secret")

        with (
            self.assertLogs(
                "valutatrade_hub.decorators",
                level="ERROR",
            ) as captured,
            self.assertRaises(RuntimeError),
        ):
            fail()

        output = "\n".join(captured.output)

        self.assertIn("RuntimeError", output)
        self.assertNotIn("very-secret", output)


if __name__ == "__main__":
    unittest.main()
