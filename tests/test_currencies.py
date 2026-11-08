"""Tests for currency models and factory."""

import unittest

from valutatrade_hub.core.currencies import (
    CryptoCurrency,
    Currency,
    FiatCurrency,
    create_currency,
)


class TestCurrencies(unittest.TestCase):
    """Test currency inheritance, validation, and factory."""

    def test_abstract_currency(self):
        with self.assertRaises(TypeError):
            Currency("USD", "US Dollar")

    def test_fiat_currency(self):
        currency = FiatCurrency("USD", "US Dollar")
        self.assertEqual(currency.code, "USD")
        self.assertEqual(currency.name, "US Dollar")
        self.assertEqual(currency.currency_type, "fiat")

    def test_crypto_currency(self):
        currency = CryptoCurrency("BTC", "Bitcoin")
        self.assertEqual(currency.code, "BTC")
        self.assertEqual(currency.currency_type, "crypto")

    def test_inheritance(self):
        currency = create_currency("BTC")
        self.assertIsInstance(currency, Currency)
        self.assertIsInstance(currency, CryptoCurrency)

    def test_factory_fiat(self):
        currency = create_currency("EUR")
        self.assertIsInstance(currency, FiatCurrency)
        self.assertEqual(currency.name, "Euro")

    def test_factory_crypto(self):
        currency = create_currency("ETH")
        self.assertIsInstance(currency, CryptoCurrency)
        self.assertEqual(currency.name, "Ethereum")

    def test_factory_normalization(self):
        currency = create_currency(" btc ")
        self.assertEqual(currency.code, "BTC")

    def test_unsupported_currency(self):
        with self.assertRaises(ValueError):
            create_currency("XYZ")

    def test_empty_currency_code(self):
        with self.assertRaises(ValueError):
            create_currency("")

    def test_empty_currency_name(self):
        with self.assertRaises(ValueError):
            FiatCurrency("USD", "")

    def test_display_info(self):
        currency = create_currency("RUB")
        self.assertIn("RUB", currency.get_display_info())
        self.assertIn("фиатная валюта", currency.get_display_info())

    def test_serialization(self):
        currency = create_currency("BTC")
        self.assertEqual(
            currency.to_dict(),
            {
                "code": "BTC",
                "name": "Bitcoin",
                "type": "crypto",
            },
        )


if __name__ == "__main__":
    unittest.main()
