"""Integration tests for the trading audit log."""

import copy
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.usecases import TradingService, UserService


class FakeDatabase:
    """In-memory database with configurable save failures."""

    def __init__(self):
        self.users = []
        self.portfolios = []
        self.rates = {
            "pairs": {
                "BTC_USD": 50000.0,
            },
            "last_refresh": datetime.now(UTC).isoformat(),
        }
        self.fail_on_save = False

    def load_users(self):
        return copy.deepcopy(self.users)

    def save_users(self, users):
        self.users = copy.deepcopy(users)

    def load_portfolios(self):
        return copy.deepcopy(self.portfolios)

    def save_portfolios(self, portfolios):
        if self.fail_on_save:
            raise OSError("Ошибка сохранения портфеля")

        self.portfolios = copy.deepcopy(portfolios)

    def load_rates(self):
        return copy.deepcopy(self.rates)


class TestTradingAudit(unittest.TestCase):
    """Verify that audit records match actual trade outcomes."""

    def setUp(self):
        """Prepare a user, trading service, and isolated database."""
        self.database = FakeDatabase()
        self.settings = SimpleNamespace(
            rates_ttl_seconds=3600,
        )

        self.user_service = UserService(
            database=self.database,
        )
        self.trading = TradingService(
            database=self.database,
            settings=self.settings,
        )

        self.password = "PRIVATE_PASSWORD_FOR_TEST_123"

        self.user = self.user_service.register(
            "audit_user",
            self.password,
        )
        self.user_id = self.user.user_id

        self.logger_name = "valutatrade_hub"

    def _messages(self, captured):
        """Return audit messages without logging prefixes."""
        return [record.getMessage() for record in captured.records]

    def _trade_messages(self, captured, action):
        """Return audit entries for one trade action."""
        return [
            message
            for message in self._messages(captured)
            if f"action={action}" in message
        ]

    def _assert_success_sequence(
        self,
        captured,
        action,
    ):
        """Require STARTED, COMMITTED, SUCCESS in exact order."""
        messages = self._trade_messages(captured, action)

        self.assertEqual(len(messages), 3)

        self.assertIn("status=STARTED", messages[0])
        self.assertIn("status=COMMITTED", messages[1])
        self.assertIn("status=SUCCESS", messages[2])

        self.assertIn(f"action={action}", messages[0])
        self.assertIn(f"action={action}", messages[1])
        self.assertIn(f"action={action}", messages[2])

        self.assertFalse(any("status=FAILED" in text for text in messages))

    def _assert_failure_sequence(
        self,
        captured,
        action,
        error_type,
    ):
        """Require STARTED and FAILED, without COMMITTED."""
        messages = self._trade_messages(captured, action)

        self.assertEqual(len(messages), 2)
        self.assertIn("status=STARTED", messages[0])
        self.assertIn("status=FAILED", messages[1])

        self.assertIn(
            f"error_type={error_type}",
            messages[1],
        )

        self.assertFalse(any("status=COMMITTED" in text for text in messages))
        self.assertFalse(any("status=SUCCESS" in text for text in messages))

    def test_successful_buy_audit(self):
        """A saved purchase must have complete audit metadata."""
        self.trading.deposit_usd(self.user_id, 1000.0)

        with self.assertLogs(
            self.logger_name,
            level="INFO",
        ) as captured:
            portfolio = self.trading.buy(
                self.user_id,
                "BTC",
                0.01,
            )

        self._assert_success_sequence(captured, "buy")

        messages = self._trade_messages(captured, "buy")
        details = messages[1]

        self.assertIn(f"user_id={self.user_id}", details)
        self.assertIn("username=audit_user", details)
        self.assertIn("currency=BTC", details)
        self.assertIn("amount=0.01000000", details)
        self.assertIn("rate_usd=50000.00000000", details)
        self.assertIn("total_usd=500.00000000", details)

        self.assertNotIn(
            self.password,
            "\n".join(messages),
        )

        self.assertAlmostEqual(
            portfolio.get_wallet("USD").balance,
            500.0,
        )
        self.assertAlmostEqual(
            portfolio.get_wallet("BTC").balance,
            0.01,
        )

    def test_successful_sell_audit(self):
        """A saved sale must have a COMMITTED audit entry."""
        self.trading.deposit_usd(self.user_id, 1000.0)
        self.trading.buy(self.user_id, "BTC", 0.01)

        with self.assertLogs(
            self.logger_name,
            level="INFO",
        ) as captured:
            portfolio = self.trading.sell(
                self.user_id,
                "BTC",
                0.005,
            )

        self._assert_success_sequence(captured, "sell")

        messages = self._trade_messages(captured, "sell")
        details = messages[1]

        self.assertIn("currency=BTC", details)
        self.assertIn("amount=0.00500000", details)
        self.assertIn("rate_usd=50000.00000000", details)
        self.assertIn("total_usd=250.00000000", details)

        self.assertAlmostEqual(
            portfolio.get_wallet("USD").balance,
            750.0,
        )
        self.assertAlmostEqual(
            portfolio.get_wallet("BTC").balance,
            0.005,
        )

    def test_buy_insufficient_funds_audit(self):
        """Rejected purchases must not be marked COMMITTED."""
        self.trading.deposit_usd(self.user_id, 100.0)
        before = copy.deepcopy(self.database.portfolios)

        with (
            self.assertLogs(
                self.logger_name,
                level="INFO",
            ) as captured,
            self.assertRaises(InsufficientFundsError),
        ):
            self.trading.buy(
                self.user_id,
                "BTC",
                0.01,
            )

        self._assert_failure_sequence(
            captured,
            "buy",
            "InsufficientFundsError",
        )
        self.assertEqual(
            self.database.portfolios,
            before,
        )

    def test_sell_insufficient_currency_audit(self):
        """Rejected sales must not be marked COMMITTED."""
        self.trading.deposit_usd(self.user_id, 1000.0)
        self.trading.buy(self.user_id, "BTC", 0.01)

        before = copy.deepcopy(self.database.portfolios)

        with (
            self.assertLogs(
                self.logger_name,
                level="INFO",
            ) as captured,
            self.assertRaises(InsufficientFundsError),
        ):
            self.trading.sell(
                self.user_id,
                "BTC",
                0.02,
            )

        self._assert_failure_sequence(
            captured,
            "sell",
            "InsufficientFundsError",
        )
        self.assertEqual(
            self.database.portfolios,
            before,
        )

    def test_failed_buy_save_audit(self):
        """A failed purchase save must not produce COMMITTED."""
        self.trading.deposit_usd(self.user_id, 1000.0)

        before = copy.deepcopy(self.database.portfolios)
        self.database.fail_on_save = True

        with (
            self.assertLogs(
                self.logger_name,
                level="INFO",
            ) as captured,
            self.assertRaises(OSError),
        ):
            self.trading.buy(
                self.user_id,
                "BTC",
                0.01,
            )

        self._assert_failure_sequence(
            captured,
            "buy",
            "OSError",
        )
        self.assertEqual(
            self.database.portfolios,
            before,
        )

    def test_failed_sell_save_audit(self):
        """A failed sale save must not produce COMMITTED."""
        self.trading.deposit_usd(self.user_id, 1000.0)
        self.trading.buy(self.user_id, "BTC", 0.01)

        before = copy.deepcopy(self.database.portfolios)
        self.database.fail_on_save = True

        with (
            self.assertLogs(
                self.logger_name,
                level="INFO",
            ) as captured,
            self.assertRaises(OSError),
        ):
            self.trading.sell(
                self.user_id,
                "BTC",
                0.005,
            )

        self._assert_failure_sequence(
            captured,
            "sell",
            "OSError",
        )
        self.assertEqual(
            self.database.portfolios,
            before,
        )


if __name__ == "__main__":
    unittest.main()
