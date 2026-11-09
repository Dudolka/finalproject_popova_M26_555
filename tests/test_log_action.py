"""Tests for the log_action trading audit decorator."""

import unittest
from unittest.mock import patch

from valutatrade_hub.decorators import log_action


class TestLogAction(unittest.TestCase):
    """Verify audit metadata, errors, and sensitive-data protection."""

    def setUp(self):
        """Set the application audit logger name."""
        self.logger_name = "valutatrade_hub.decorators"

    def test_successful_operation(self):
        """Successful operations return their original result."""

        @log_action
        def buy(user_id, currency_code, amount):
            return amount * 2

        with self.assertLogs(self.logger_name, level="INFO") as captured:
            result = buy(1, "BTC", 0.01)

        self.assertEqual(result, 0.02)

        messages = "\n".join(captured.output)

        self.assertIn("action=buy", messages)
        self.assertIn("user_id=1", messages)
        self.assertIn("currency_code=BTC", messages)
        self.assertIn("amount=0.01", messages)
        self.assertIn("status=STARTED", messages)
        self.assertIn("status=SUCCESS", messages)

    def test_failed_operation(self):
        """Failures are logged and original exceptions propagate."""

        @log_action
        def sell(user_id, currency_code, amount):
            raise ValueError("Некорректная сумма")

        with (
            self.assertLogs(
                self.logger_name,
                level="ERROR",
            ) as captured,
            self.assertRaises(ValueError),
        ):
            sell(1, "ETH", -5)

        messages = "\n".join(captured.output)

        self.assertIn("action=sell", messages)
        self.assertIn("status=FAILED", messages)
        self.assertIn("error_type=ValueError", messages)

    def test_password_is_not_logged(self):
        """Password arguments must not appear in audit messages."""

        @log_action
        def operation(user_id, password):
            return user_id

        secret = "SUPER_SECRET_PASSWORD_123"

        with self.assertLogs(self.logger_name, level="INFO") as captured:
            operation(1, secret)

        messages = "\n".join(captured.output)

        self.assertNotIn(secret, messages)
        self.assertNotIn("password=", messages)

    def test_api_key_is_not_logged(self):
        """API keys must not appear in audit messages."""

        @log_action
        def operation(user_id, api_key):
            return user_id

        secret = "PRIVATE_API_KEY_123"

        with self.assertLogs(self.logger_name, level="INFO") as captured:
            operation(1, secret)

        messages = "\n".join(captured.output)

        self.assertNotIn(secret, messages)
        self.assertNotIn("api_key=", messages)

    def test_return_value_is_not_logged(self):
        """Sensitive return values must not appear in audit messages."""

        @log_action
        def operation(user_id):
            return "PRIVATE_RETURN_VALUE_123"

        with self.assertLogs(self.logger_name, level="INFO") as captured:
            result = operation(1)

        self.assertEqual(result, "PRIVATE_RETURN_VALUE_123")
        self.assertNotIn(
            result,
            "\n".join(captured.output),
        )

    def test_verbose_mode(self):
        """Verbose mode emits DEBUG metadata."""

        @log_action(verbose=True)
        def buy(user_id, currency_code, amount):
            return amount

        with self.assertLogs(self.logger_name, level="DEBUG") as captured:
            buy(1, "BTC", 0.01)

        messages = "\n".join(captured.output)

        self.assertIn("TRADE DEBUG", messages)
        self.assertIn("action=buy", messages)

    def test_invalid_verbose_value(self):
        """Verbose argument must be boolean."""
        with self.assertRaises(TypeError):
            log_action(verbose="yes")

    def test_function_metadata(self):
        """Decorator preserves the wrapped function's identity."""

        @log_action
        def example_operation(user_id):
            """Example operation."""
            return user_id

        self.assertEqual(
            example_operation.__name__,
            "example_operation",
        )
        self.assertEqual(
            example_operation.__doc__,
            "Example operation.",
        )

    def test_exception_type_is_preserved(self):
        """Decorator must preserve domain exception types."""

        class TestTradingError(Exception):
            pass

        @log_action
        def failed_operation(user_id):
            raise TestTradingError("Expected failure")

        with (
            self.assertLogs(
                self.logger_name,
                level="ERROR",
            ),
            self.assertRaises(TestTradingError),
        ):
            failed_operation(1)

    def test_arbitrary_objects_are_not_logged(self):
        """Unexpected objects must not be serialized into logs."""

        class SensitiveObject:
            def __str__(self):
                return "PRIVATE_OBJECT_CONTENT"

        @log_action
        def operation(user_id, payload):
            return True

        with self.assertLogs(self.logger_name, level="INFO") as captured:
            operation(1, SensitiveObject())

        self.assertNotIn(
            "PRIVATE_OBJECT_CONTENT",
            "\n".join(captured.output),
        )

    def test_duration_is_logged(self):
        """Audit records include the elapsed execution time."""

        @log_action
        def buy(user_id, amount):
            return amount

        with self.assertLogs(self.logger_name, level="INFO") as captured:
            buy(1, 10)

        self.assertTrue(any("duration=" in message for message in captured.output))

    def test_decorator_calls_function_once(self):
        """Audit logging must not duplicate business operations."""
        calls = []

        @log_action
        def buy(user_id, currency_code, amount):
            calls.append((user_id, currency_code, amount))
            return "done"

        with self.assertLogs(self.logger_name, level="INFO"):
            result = buy(1, "BTC", 0.01)

        self.assertEqual(result, "done")
        self.assertEqual(calls, [(1, "BTC", 0.01)])

    def test_logging_failure_does_not_hide_exception(self):
        """Business exceptions must propagate unchanged."""

        @log_action
        def sell(user_id, amount):
            raise RuntimeError("Transaction failed")

        with (
            patch(
                "valutatrade_hub.decorators.time.monotonic",
                side_effect=[1.0, 1.5],
            ),
            self.assertLogs(
                self.logger_name,
                level="ERROR",
            ),
            self.assertRaisesRegex(
                RuntimeError,
                "Transaction failed",
            ),
        ):
            sell(1, 100)


if __name__ == "__main__":
    unittest.main()
