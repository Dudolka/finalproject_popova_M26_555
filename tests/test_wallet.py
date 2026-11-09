"""Tests for the Wallet domain model."""

import unittest

from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.models import Wallet


class TestWallet(unittest.TestCase):
    """Test wallet creation, balance properties, and transactions."""

    def setUp(self):
        """Create a wallet before each test."""
        self.wallet = Wallet("USD", 100.0)

    def test_wallet_creation(self):
        """Wallet stores its currency and initial balance."""
        self.assertEqual(self.wallet.currency_code, "USD")
        self.assertEqual(self.wallet.balance, 100.0)

    def test_currency_code_normalization(self):
        """Currency codes are normalized to uppercase."""
        wallet = Wallet(" eur ")
        self.assertEqual(wallet.currency_code, "EUR")

    def test_default_balance(self):
        """New wallets have a zero balance by default."""
        wallet = Wallet("BTC")
        self.assertEqual(wallet.balance, 0.0)

    def test_balance_setter(self):
        """Balance can be updated through its property setter."""
        self.wallet.balance = 250.5
        self.assertEqual(self.wallet.balance, 250.5)

    def test_balance_setter_zero(self):
        """Balance setter accepts zero."""
        self.wallet.balance = 0
        self.assertEqual(self.wallet.balance, 0.0)

    def test_balance_setter_negative(self):
        """Balance setter rejects negative values."""
        with self.assertRaises(ValueError):
            self.wallet.balance = -10.0

        self.assertEqual(self.wallet.balance, 100.0)

    def test_balance_setter_invalid_type(self):
        """Balance setter rejects non-numeric values and booleans."""
        for invalid_value in ("100", None, True):
            with (
                self.subTest(value=invalid_value),
                self.assertRaises(TypeError),
            ):
                self.wallet.balance = invalid_value

        self.assertEqual(self.wallet.balance, 100.0)

    def test_balance_setter_non_finite(self):
        """Balance setter rejects NaN and infinity."""
        for invalid_value in (
            float("nan"),
            float("inf"),
            float("-inf"),
        ):
            with (
                self.subTest(value=invalid_value),
                self.assertRaises(ValueError),
            ):
                self.wallet.balance = invalid_value

        self.assertEqual(self.wallet.balance, 100.0)

    def test_get_balance_info(self):
        """Balance information includes currency and formatted amount."""
        self.assertEqual(
            self.wallet.get_balance_info(),
            "Баланс USD: 100.0000",
        )

    def test_get_balance_info_after_deposit(self):
        """Balance information reflects completed deposits."""
        self.wallet.deposit(25.5)

        self.assertEqual(
            self.wallet.get_balance_info(),
            "Баланс USD: 125.5000",
        )

    def test_deposit(self):
        """Deposit increases the balance."""
        self.wallet.deposit(50.0)
        self.assertEqual(self.wallet.balance, 150.0)

    def test_withdraw(self):
        """Withdrawal decreases the balance."""
        self.wallet.withdraw(30.0)
        self.assertEqual(self.wallet.balance, 70.0)

    def test_withdraw_entire_balance(self):
        """Withdrawal of all available funds is permitted."""
        self.wallet.withdraw(100.0)
        self.assertEqual(self.wallet.balance, 0.0)

    def test_insufficient_funds(self):
        """Withdrawal rejects amounts exceeding the balance."""
        with self.assertRaises(InsufficientFundsError):
            self.wallet.withdraw(200.0)

        self.assertEqual(self.wallet.balance, 100.0)

    def test_insufficient_funds_message(self):
        """InsufficientFundsError contains useful transaction details."""
        with self.assertRaises(InsufficientFundsError) as context:
            self.wallet.withdraw(200.0)

        message = str(context.exception)

        self.assertIn("Недостаточно средств", message)
        self.assertIn("100.0000", message)
        self.assertIn("200.0000", message)
        self.assertIn("USD", message)

    def test_negative_deposit(self):
        """Negative deposits are rejected."""
        with self.assertRaises(ValueError):
            self.wallet.deposit(-10.0)

    def test_zero_deposit(self):
        """Zero deposits are rejected."""
        with self.assertRaises(ValueError):
            self.wallet.deposit(0.0)

    def test_zero_withdraw(self):
        """Zero withdrawals are rejected."""
        with self.assertRaises(ValueError):
            self.wallet.withdraw(0)

    def test_invalid_operation_type(self):
        """Deposit and withdrawal reject invalid amount types."""
        for invalid_value in ("10", None, True):
            for operation in (
                self.wallet.deposit,
                self.wallet.withdraw,
            ):
                with (
                    self.subTest(
                        value=invalid_value,
                        operation=operation.__name__,
                    ),
                    self.assertRaises(TypeError),
                ):
                    operation(invalid_value)

        self.assertEqual(self.wallet.balance, 100.0)

    def test_negative_initial_balance(self):
        """A wallet cannot be created with a negative balance."""
        with self.assertRaises(ValueError):
            Wallet("USD", -100.0)

    def test_invalid_currency(self):
        """Empty currency codes are rejected."""
        with self.assertRaises(ValueError):
            Wallet("")

    def test_serialization(self):
        """Wallet serialization preserves the currency and balance."""
        data = self.wallet.to_dict()
        restored = Wallet.from_dict(data)

        self.assertEqual(restored.currency_code, "USD")
        self.assertEqual(restored.balance, 100.0)
        self.assertIsInstance(restored, Wallet)

    def test_infinite_deposit(self):
        """Infinite deposits are rejected."""
        with self.assertRaises(ValueError):
            self.wallet.deposit(float("inf"))

    def test_balance_overflow(self):
        """Overflowing deposits do not modify the existing balance."""
        wallet = Wallet("USD", 1e308)

        with self.assertRaises(ValueError):
            wallet.deposit(1e308)

        self.assertEqual(wallet.balance, 1e308)


if __name__ == "__main__":
    unittest.main()
