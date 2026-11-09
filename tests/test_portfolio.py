"""Tests for the Portfolio domain model."""

import unittest
from datetime import datetime

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.models import Portfolio, User


class TestPortfolio(unittest.TestCase):
    """Test portfolio wallets, serialization, and valuation."""

    def setUp(self):
        """Create a user and portfolio before each test."""
        self.user = User(
            user_id=1,
            username="alice",
            hashed_password="",
            salt="initial_salt",
            registration_date=datetime(2026, 11, 8),
        )
        self.portfolio = Portfolio(self.user)

    def test_portfolio_creation(self):
        self.assertEqual(self.portfolio.user.user_id, 1)
        self.assertEqual(self.portfolio.wallets, {})

    def test_add_currency(self):
        wallet = self.portfolio.add_currency("USD")
        self.assertEqual(wallet.currency_code, "USD")
        self.assertEqual(wallet.balance, 0.0)

    def test_duplicate_currency(self):
        first = self.portfolio.add_currency("USD")
        second = self.portfolio.add_currency("usd")

        self.assertIs(first, second)
        self.assertEqual(len(self.portfolio.wallets), 1)

    def test_get_wallet(self):
        self.portfolio.add_currency("EUR")
        wallet = self.portfolio.get_wallet("eur")
        self.assertEqual(wallet.currency_code, "EUR")

    def test_missing_wallet(self):
        with self.assertRaises(CurrencyNotFoundError):
            self.portfolio.get_wallet("BTC")

    def test_invalid_currency(self):
        with self.assertRaises(ValueError):
            self.portfolio.add_currency("")

    def test_wallets_mapping_is_copy(self):
        self.portfolio.add_currency("USD")
        wallets = self.portfolio.wallets
        wallets.clear()

        self.assertEqual(len(self.portfolio.wallets), 1)

    def test_total_value_usd(self):
        self.portfolio.add_currency("USD").deposit(100)

        self.assertEqual(
            self.portfolio.get_total_value({}),
            100.0,
        )

    def test_total_value_usd_explicit(self):
        self.portfolio.add_currency("USD").deposit(100)

        self.assertEqual(
            self.portfolio.get_total_value(
                {},
                base_currency="USD",
            ),
            100.0,
        )

    def test_total_value_multiple_currencies(self):
        self.portfolio.add_currency("USD").deposit(100)
        self.portfolio.add_currency("EUR").deposit(50)
        self.portfolio.add_currency("BTC").deposit(0.01)

        rates = {
            "EUR": 1.2,
            "BTC": 60000.0,
        }

        self.assertAlmostEqual(
            self.portfolio.get_total_value(rates),
            760.0,
        )

    def test_total_value_in_eur(self):
        self.portfolio.add_currency("USD").deposit(100)
        self.portfolio.add_currency("EUR").deposit(50)

        rates = {"EUR": 1.25}

        self.assertAlmostEqual(
            self.portfolio.get_total_value(
                rates,
                base_currency="EUR",
            ),
            130.0,
        )

    def test_total_value_in_rub(self):
        self.portfolio.add_currency("USD").deposit(100)

        rates = {"RUB": 0.01}

        self.assertAlmostEqual(
            self.portfolio.get_total_value(
                rates,
                base_currency="RUB",
            ),
            10000.0,
        )

    def test_base_currency_normalization(self):
        self.portfolio.add_currency("USD").deposit(100)

        rates = {"EUR": 1.25}

        self.assertAlmostEqual(
            self.portfolio.get_total_value(
                rates,
                base_currency=" eur ",
            ),
            80.0,
        )

    def test_missing_rate(self):
        self.portfolio.add_currency("EUR").deposit(10)

        with self.assertRaises(CurrencyNotFoundError):
            self.portfolio.get_total_value({})

    def test_missing_base_currency_rate(self):
        self.portfolio.add_currency("USD").deposit(100)

        with self.assertRaises(CurrencyNotFoundError):
            self.portfolio.get_total_value(
                {},
                base_currency="EUR",
            )

    def test_zero_balance_without_rate(self):
        self.portfolio.add_currency("BTC")

        self.assertEqual(
            self.portfolio.get_total_value({}),
            0.0,
        )

    def test_empty_portfolio_value(self):
        self.assertEqual(
            self.portfolio.get_total_value(
                {},
                base_currency="USD",
            ),
            0.0,
        )

    def test_invalid_rate(self):
        self.portfolio.add_currency("EUR").deposit(10)

        with self.assertRaises(ValueError):
            self.portfolio.get_total_value({"EUR": -1.0})

    def test_invalid_base_rate(self):
        self.portfolio.add_currency("USD").deposit(100)

        with self.assertRaises(ValueError):
            self.portfolio.get_total_value(
                {"EUR": 0.0},
                base_currency="EUR",
            )

    def test_non_finite_asset_rate(self):
        self.portfolio.add_currency("BTC").deposit(1)

        for invalid_rate in (
            float("nan"),
            float("inf"),
        ):
            with (
                self.subTest(rate=invalid_rate),
                self.assertRaises(ValueError),
            ):
                self.portfolio.get_total_value({"BTC": invalid_rate})

    def test_non_finite_base_rate(self):
        self.portfolio.add_currency("USD").deposit(100)

        with self.assertRaises(ValueError):
            self.portfolio.get_total_value(
                {"EUR": float("inf")},
                base_currency="EUR",
            )

    def test_invalid_base_currency(self):
        with self.assertRaises(ValueError):
            self.portfolio.get_total_value(
                {},
                base_currency="",
            )

    def test_portfolio_value_overflow(self):
        self.portfolio.add_currency("EUR").deposit(1e308)

        with self.assertRaises(ValueError):
            self.portfolio.get_total_value({"EUR": 2.0})

    def test_invalid_portfolio_owner(self):
        with self.assertRaises(TypeError):
            Portfolio("alice")

    def test_serialization(self):
        self.portfolio.add_currency("USD").deposit(100)
        self.portfolio.add_currency("EUR").deposit(50)

        data = self.portfolio.to_dict()
        restored = Portfolio.from_dict(
            data,
            self.user,
        )

        self.assertEqual(restored.user.user_id, 1)
        self.assertEqual(
            restored.get_wallet("USD").balance,
            100.0,
        )
        self.assertEqual(
            restored.get_wallet("EUR").balance,
            50.0,
        )

    def test_wrong_owner(self):
        data = self.portfolio.to_dict()

        other_user = User(
            user_id=2,
            username="bob",
            hashed_password="",
            salt="initial_salt",
            registration_date=datetime(2026, 11, 8),
        )

        with self.assertRaises(ValueError):
            Portfolio.from_dict(
                data,
                other_user,
            )


if __name__ == "__main__":
    unittest.main()
