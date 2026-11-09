"""Tests for the ValutaTrade Hub trading service."""

import copy
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.usecases import TradingService, UserService


class FakeDatabase:
    """Isolated in-memory storage for trading tests."""

    def __init__(self):
        self.users = []
        self.portfolios = []
        self.rates = {
            "pairs": {
                "BTC_USD": 50000.0,
                "ETH_USD": 2500.0,
                "EUR_USD": 1.1,
            },
            "last_refresh": datetime.now(UTC).isoformat(),
        }

    def load_users(self):
        return copy.deepcopy(self.users)

    def save_users(self, users):
        self.users = copy.deepcopy(users)

    def load_portfolios(self):
        return copy.deepcopy(self.portfolios)

    def save_portfolios(self, portfolios):
        self.portfolios = copy.deepcopy(portfolios)

    def load_rates(self):
        return copy.deepcopy(self.rates)


class TestTradingService(unittest.TestCase):
    """Test currency trading, persistence, and TTL."""

    def setUp(self):
        self.database = FakeDatabase()
        self.settings = SimpleNamespace(rates_ttl_seconds=3600)
        self.user_service = UserService(database=self.database)
        self.trading = TradingService(
            database=self.database,
            settings=self.settings,
        )

        self.user = self.user_service.register(
            "olga",
            "password123",
        )
        self.user_id = self.user.user_id

    def _set_rate_age(self, seconds):
        """Set the last refresh to a specified age."""
        timestamp = datetime.now(UTC) - timedelta(seconds=seconds)
        self.database.rates["last_refresh"] = timestamp.isoformat()

    def test_empty_portfolio(self):
        portfolio = self.trading.get_portfolio(self.user_id)
        self.assertEqual(portfolio.wallets, {})

    def test_deposit_usd(self):
        portfolio = self.trading.deposit_usd(self.user_id, 1000.0)
        self.assertEqual(
            portfolio.get_wallet("USD").balance,
            1000.0,
        )

    def test_multiple_deposits(self):
        self.trading.deposit_usd(self.user_id, 1000.0)
        portfolio = self.trading.deposit_usd(self.user_id, 500.0)
        self.assertEqual(
            portfolio.get_wallet("USD").balance,
            1500.0,
        )

    def test_deposit_persists(self):
        self.trading.deposit_usd(self.user_id, 1000.0)

        reloaded = self.trading.get_portfolio(self.user_id)
        self.assertEqual(
            reloaded.get_wallet("USD").balance,
            1000.0,
        )

    def test_buy_bitcoin(self):
        self.trading.deposit_usd(self.user_id, 1000.0)
        portfolio = self.trading.buy(self.user_id, "BTC", 0.01)
        self.assertAlmostEqual(
            portfolio.get_wallet("USD").balance,
            500.0,
        )
        self.assertAlmostEqual(
            portfolio.get_wallet("BTC").balance,
            0.01,
        )

    def test_buy_ethereum(self):
        self.trading.deposit_usd(self.user_id, 1000.0)
        portfolio = self.trading.buy(self.user_id, "ETH", 0.2)
        self.assertAlmostEqual(
            portfolio.get_wallet("USD").balance,
            500.0,
        )
        self.assertAlmostEqual(
            portfolio.get_wallet("ETH").balance,
            0.2,
        )

    def test_sell_bitcoin(self):
        self.trading.deposit_usd(self.user_id, 1000.0)
        self.trading.buy(self.user_id, "BTC", 0.01)

        portfolio = self.trading.sell(self.user_id, "BTC", 0.005)
        self.assertAlmostEqual(
            portfolio.get_wallet("USD").balance,
            750.0,
        )
        self.assertAlmostEqual(
            portfolio.get_wallet("BTC").balance,
            0.005,
        )

    def test_buy_insufficient_funds(self):
        self.trading.deposit_usd(self.user_id, 100.0)

        with self.assertRaises(InsufficientFundsError):
            self.trading.buy(self.user_id, "BTC", 0.01)

        portfolio = self.trading.get_portfolio(self.user_id)
        self.assertEqual(
            portfolio.get_wallet("USD").balance,
            100.0,
        )
        self.assertNotIn("BTC", portfolio.wallets)

    def test_sell_insufficient_currency(self):
        self.trading.deposit_usd(self.user_id, 1000.0)
        self.trading.buy(self.user_id, "BTC", 0.01)

        with self.assertRaises(InsufficientFundsError):
            self.trading.sell(self.user_id, "BTC", 0.02)

        portfolio = self.trading.get_portfolio(self.user_id)
        self.assertAlmostEqual(
            portfolio.get_wallet("BTC").balance,
            0.01,
        )
        self.assertAlmostEqual(
            portfolio.get_wallet("USD").balance,
            500.0,
        )

    def test_missing_rate(self):
        self.database.rates["pairs"].pop("BTC_USD")
        self.trading.deposit_usd(self.user_id, 1000.0)

        with self.assertRaises(CurrencyNotFoundError):
            self.trading.buy(self.user_id, "BTC", 0.01)

    def test_unsupported_currency(self):
        self.trading.deposit_usd(self.user_id, 1000.0)

        with self.assertRaises(CurrencyNotFoundError):
            self.trading.buy(self.user_id, "XYZ", 1.0)

    def test_invalid_amount(self):
        self.trading.deposit_usd(self.user_id, 1000.0)

        with self.assertRaises(ValueError):
            self.trading.buy(self.user_id, "BTC", -1.0)

        with self.assertRaises(ValueError):
            self.trading.sell(self.user_id, "BTC", 0.0)

    def test_usd_to_usd_not_allowed(self):
        self.trading.deposit_usd(self.user_id, 1000.0)

        with self.assertRaises(ValueError):
            self.trading.buy(self.user_id, "USD", 100.0)

        with self.assertRaises(ValueError):
            self.trading.sell(self.user_id, "USD", 100.0)

    def test_portfolio_total_value(self):
        self.trading.deposit_usd(self.user_id, 1000.0)
        self.trading.buy(self.user_id, "BTC", 0.01)

        value = self.trading.get_portfolio_value(self.user_id)
        self.assertAlmostEqual(value, 1000.0)

    def test_portfolio_persistence(self):
        self.trading.deposit_usd(self.user_id, 1000.0)
        self.trading.buy(self.user_id, "BTC", 0.01)

        another_service = TradingService(
            database=self.database,
            settings=self.settings,
        )
        portfolio = another_service.get_portfolio(self.user_id)

        self.assertAlmostEqual(
            portfolio.get_wallet("USD").balance,
            500.0,
        )
        self.assertAlmostEqual(
            portfolio.get_wallet("BTC").balance,
            0.01,
        )

    def test_buy_expired_rate(self):
        """Block purchases when TTL has expired."""
        self.trading.deposit_usd(self.user_id, 1000.0)
        self._set_rate_age(7200)

        before = copy.deepcopy(self.database.portfolios)

        with self.assertRaises(ApiRequestError):
            self.trading.buy(self.user_id, "BTC", 0.01)

        self.assertEqual(
            self.database.portfolios,
            before,
        )

    def test_sell_expired_rate(self):
        """Block sales when TTL has expired."""
        self.trading.deposit_usd(self.user_id, 1000.0)
        self.trading.buy(self.user_id, "BTC", 0.01)

        self._set_rate_age(7200)
        before = copy.deepcopy(self.database.portfolios)

        with self.assertRaises(ApiRequestError):
            self.trading.sell(self.user_id, "BTC", 0.005)

        self.assertEqual(
            self.database.portfolios,
            before,
        )

    def test_missing_timestamp(self):
        """Reject trading when refresh time is missing."""
        self.database.rates["last_refresh"] = None
        self.trading.deposit_usd(self.user_id, 1000.0)

        with self.assertRaises(ApiRequestError):
            self.trading.buy(self.user_id, "BTC", 0.01)

    def test_invalid_timestamp(self):
        """Reject invalid ISO timestamps."""
        self.database.rates["last_refresh"] = "invalid"
        self.trading.deposit_usd(self.user_id, 1000.0)

        with self.assertRaises(ApiRequestError):
            self.trading.buy(self.user_id, "BTC", 0.01)

    def test_naive_timestamp(self):
        """Reject timestamps without timezone information."""
        self.database.rates["last_refresh"] = "2026-11-09T10:00:00"
        self.trading.deposit_usd(self.user_id, 1000.0)

        with self.assertRaises(ApiRequestError):
            self.trading.buy(self.user_id, "BTC", 0.01)

    def test_future_timestamp(self):
        """Reject timestamps in the future."""
        self._set_rate_age(-7200)
        self.trading.deposit_usd(self.user_id, 1000.0)

        with self.assertRaises(ApiRequestError):
            self.trading.buy(self.user_id, "BTC", 0.01)

    def test_deposit_with_expired_rates(self):
        """Allow USD deposits without fresh exchange rates."""
        self._set_rate_age(7200)

        portfolio = self.trading.deposit_usd(self.user_id, 1000.0)
        self.assertEqual(
            portfolio.get_wallet("USD").balance,
            1000.0,
        )

    def test_portfolio_value_with_expired_rates(self):
        """Allow historical valuation using saved rates."""
        self.trading.deposit_usd(self.user_id, 1000.0)
        self.trading.buy(self.user_id, "BTC", 0.01)
        self._set_rate_age(7200)

        portfolio = self.trading.get_portfolio(self.user_id)
        value = self.trading.get_portfolio_value(self.user_id)

        self.assertAlmostEqual(value, 1000.0)
        self.assertAlmostEqual(
            portfolio.get_wallet("BTC").balance,
            0.01,
        )


if __name__ == "__main__":
    unittest.main()
