"""Tests for the Wallet model."""

import unittest

from valutatrade_hub.core.models import Wallet


class TestWallet(unittest.TestCase):
    """Test wallet operations and validation."""

    def setUp(self):
        """Create a wallet before each test."""
        self.wallet = Wallet("USD", 100.0)

    def test_wallet_creation(self):
        self.assertEqual(self.wallet.currency_code, "USD")
        self.assertEqual(self.wallet.balance, 100.0)

    def test_currency_code_normalization(self):
        wallet = Wallet(" eur ")
        self.assertEqual(wallet.currency_code, "EUR")

    def test_deposit(self):
        self.wallet.deposit(50.0)
        self.assertEqual(self.wallet.balance, 150.0)

    def test_withdraw(self):
        self.wallet.withdraw(30.0)
        self.assertEqual(self.wallet.balance, 70.0)

    def test_insufficient_funds(self):
        with self.assertRaises(ValueError):
            self.wallet.withdraw(200.0)
        self.assertEqual(self.wallet.balance, 100.0)

    def test_negative_deposit(self):
        with self.assertRaises(ValueError):
            self.wallet.deposit(-10.0)

    def test_zero_withdraw(self):
        with self.assertRaises(ValueError):
            self.wallet.withdraw(0)

    def test_negative_initial_balance(self):
        with self.assertRaises(ValueError):
            Wallet("USD", -100.0)

    def test_invalid_currency(self):
        with self.assertRaises(ValueError):
            Wallet("")

    def test_serialization(self):
        data = self.wallet.to_dict()
        restored = Wallet.from_dict(data)
        self.assertEqual(restored.currency_code, "USD")
        self.assertEqual(restored.balance, 100.0)

    def test_infinite_deposit(self):
        with self.assertRaises(ValueError):
            self.wallet.deposit(float("inf"))

    def test_balance_overflow(self):
        wallet = Wallet("USD", 1e308)
        with self.assertRaises(ValueError):
            wallet.deposit(1e308)
        self.assertEqual(wallet.balance, 1e308)


if __name__ == "__main__":
    unittest.main()
