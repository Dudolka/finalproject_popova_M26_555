"""Edge-case tests for ValutaTrade Hub trading operations."""

import copy
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.usecases import TradingService, UserService


class FakeDatabase:
    """In-memory storage for isolated trading tests."""

    def __init__(self):
        self.users = []
        self.portfolios = []
        self.rates = {
            "pairs": {
                "BTC_USD": 50000.0,
                "ETH_USD": 2500.0,
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
            raise OSError("Ошибка записи данных")
        self.portfolios = copy.deepcopy(portfolios)

    def load_rates(self):
        return copy.deepcopy(self.rates)


class TestTradingEdgeCases(unittest.TestCase):
    """Verify portfolio consistency in exceptional situations."""

    def setUp(self):
        self.database = FakeDatabase()
        self.settings = SimpleNamespace(rates_ttl_seconds=3600)

        self.users = UserService(database=self.database)
        self.trading = TradingService(
            database=self.database,
            settings=self.settings,
        )

        self.first_user = self.users.register(
            "first",
            "password123",
        )
        self.second_user = self.users.register(
            "second",
            "password456",
        )

    def test_failed_save_preserves_portfolio(self):
        """A failed save must preserve previously stored data."""
        user_id = self.first_user.user_id

        self.trading.deposit_usd(user_id, 1000.0)
        before = copy.deepcopy(self.database.portfolios)

        self.database.fail_on_save = True

        with self.assertRaises(OSError):
            self.trading.buy(user_id, "BTC", 0.01)

        self.assertEqual(self.database.portfolios, before)

    def test_insufficient_funds_preserves_portfolio(self):
        """A rejected purchase must preserve stored balances."""
        user_id = self.first_user.user_id

        self.trading.deposit_usd(user_id, 100.0)
        before = copy.deepcopy(self.database.portfolios)

        with self.assertRaises(InsufficientFundsError):
            self.trading.buy(user_id, "BTC", 0.01)

        self.assertEqual(self.database.portfolios, before)

    def test_users_have_separate_portfolios(self):
        """One user's trade must not affect another user."""
        first_id = self.first_user.user_id
        second_id = self.second_user.user_id

        self.trading.deposit_usd(first_id, 1000.0)
        self.trading.deposit_usd(second_id, 2000.0)

        self.trading.buy(first_id, "BTC", 0.01)

        first = self.trading.get_portfolio(first_id)
        second = self.trading.get_portfolio(second_id)

        self.assertAlmostEqual(
            first.get_wallet("USD").balance,
            500.0,
        )
        self.assertAlmostEqual(
            first.get_wallet("BTC").balance,
            0.01,
        )
        self.assertAlmostEqual(
            second.get_wallet("USD").balance,
            2000.0,
        )
        self.assertNotIn("BTC", second.wallets)

    def test_sell_usd_overflow_preserves_portfolio(self):
        """Reject a sale if its proceeds overflow float."""
        user_id = self.first_user.user_id

        self.trading.deposit_usd(user_id, 1000.0)
        self.trading.buy(user_id, "BTC", 0.01)

        self.database.portfolios[0]["wallets"]["USD"]["balance"] = 1e308
        self.database.portfolios[0]["wallets"]["BTC"]["balance"] = 1e308

        before = copy.deepcopy(self.database.portfolios)

        with self.assertRaises(ValueError):
            self.trading.sell(user_id, "BTC", 1e308)

        self.assertEqual(self.database.portfolios, before)

    def test_usd_balance_overflow_preserves_portfolio(self):
        """Reject a sale when adding finite proceeds overflows."""
        user_id = self.first_user.user_id

        self.trading.deposit_usd(user_id, 1000.0)
        self.trading.buy(user_id, "BTC", 0.01)

        self.database.portfolios[0]["wallets"]["USD"]["balance"] = 1e308
        self.database.portfolios[0]["wallets"]["BTC"]["balance"] = 1e308

        self.database.rates["pairs"]["BTC_USD"] = 1.0

        before = copy.deepcopy(self.database.portfolios)

        with self.assertRaises(ValueError):
            self.trading.sell(user_id, "BTC", 1e308)

        self.assertEqual(self.database.portfolios, before)


if __name__ == "__main__":
    unittest.main()
