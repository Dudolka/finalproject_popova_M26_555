"""Tests for currency models, validation, inheritance, and factory."""

import unittest

from valutatrade_hub.core.currencies import (
    CryptoCurrency,
    Currency,
    FiatCurrency,
    create_currency,
    get_currency,
)
from valutatrade_hub.core.exceptions import CurrencyNotFoundError


class TestCurrencies(unittest.TestCase):
    """Test currency models against the MEPHI requirements."""

    # Abstract base class and inheritance

    def test_abstract_currency(self):
        """Currency cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            Currency("USD", "US Dollar")

    def test_fiat_currency(self):
        """FiatCurrency stores common currency attributes."""
        currency = FiatCurrency("USD", "US Dollar")

        self.assertEqual(currency.code, "USD")
        self.assertEqual(currency.name, "US Dollar")
        self.assertEqual(currency.currency_type, "fiat")

    def test_crypto_currency(self):
        """CryptoCurrency stores common currency attributes."""
        currency = CryptoCurrency("BTC", "Bitcoin")

        self.assertEqual(currency.code, "BTC")
        self.assertEqual(currency.name, "Bitcoin")
        self.assertEqual(currency.currency_type, "crypto")

    def test_inheritance(self):
        """Factory returns instances of the correct hierarchy."""
        currency = create_currency("BTC")

        self.assertIsInstance(currency, Currency)
        self.assertIsInstance(currency, CryptoCurrency)

    # FiatCurrency requirements

    def test_fiat_issuing_country(self):
        """FiatCurrency stores the issuing country."""
        currency = FiatCurrency(
            "USD",
            "US Dollar",
            issuing_country="United States",
        )

        self.assertEqual(
            currency.issuing_country,
            "United States",
        )

    def test_fiat_issuing_country_validation(self):
        """Issuing country cannot be empty or invalid."""
        with self.assertRaises(ValueError):
            FiatCurrency("USD", "US Dollar", issuing_country="")

        with self.assertRaises(TypeError):
            FiatCurrency("USD", "US Dollar", issuing_country=123)

    def test_fiat_display_info(self):
        """Fiat display information follows the required format."""
        currency = FiatCurrency(
            "USD",
            "US Dollar",
            issuing_country="United States",
        )

        self.assertEqual(
            currency.get_display_info(),
            "[FIAT] USD — US Dollar (Issuing: United States)",
        )

    # CryptoCurrency requirements

    def test_crypto_algorithm(self):
        """CryptoCurrency stores the algorithm."""
        currency = CryptoCurrency(
            "BTC",
            "Bitcoin",
            algorithm="SHA-256",
            market_cap=1.12e12,
        )

        self.assertEqual(currency.algorithm, "SHA-256")

    def test_crypto_market_cap(self):
        """CryptoCurrency stores a numeric market capitalization."""
        currency = CryptoCurrency(
            "BTC",
            "Bitcoin",
            algorithm="SHA-256",
            market_cap=1.12e12,
        )

        self.assertEqual(currency.market_cap, 1.12e12)

    def test_crypto_negative_market_cap(self):
        """Negative market capitalization is rejected."""
        with self.assertRaises(ValueError):
            CryptoCurrency(
                "BTC",
                "Bitcoin",
                algorithm="SHA-256",
                market_cap=-100,
            )

    def test_crypto_invalid_market_cap_type(self):
        """Market capitalization must be numeric."""
        for invalid_value in ("1000", None, True):
            with (
                self.subTest(value=invalid_value),
                self.assertRaises(TypeError),
            ):
                CryptoCurrency(
                    "BTC",
                    "Bitcoin",
                    algorithm="SHA-256",
                    market_cap=invalid_value,
                )

    def test_crypto_non_finite_market_cap(self):
        """NaN and infinity are rejected."""
        for invalid_value in (
            float("nan"),
            float("inf"),
            float("-inf"),
        ):
            with (
                self.subTest(value=invalid_value),
                self.assertRaises(ValueError),
            ):
                CryptoCurrency(
                    "BTC",
                    "Bitcoin",
                    algorithm="SHA-256",
                    market_cap=invalid_value,
                )

    def test_crypto_invalid_algorithm(self):
        """Algorithm must be a non-empty string."""
        with self.assertRaises(ValueError):
            CryptoCurrency(
                "BTC",
                "Bitcoin",
                algorithm="",
            )

        with self.assertRaises(TypeError):
            CryptoCurrency(
                "BTC",
                "Bitcoin",
                algorithm=123,
            )

    def test_crypto_display_info(self):
        """Crypto display information includes required metadata."""
        currency = CryptoCurrency(
            "BTC",
            "Bitcoin",
            algorithm="SHA-256",
            market_cap=1.12e12,
        )

        self.assertEqual(
            currency.get_display_info(),
            "[CRYPTO] BTC — Bitcoin (Algo: SHA-256, MCAP: 1.12e+12)",
        )

    # Factory requirements

    def test_factory_fiat(self):
        """Legacy factory creates a fiat currency."""
        currency = create_currency("EUR")

        self.assertIsInstance(currency, FiatCurrency)
        self.assertEqual(currency.name, "Euro")

    def test_factory_crypto(self):
        """Legacy factory creates a cryptocurrency."""
        currency = create_currency("ETH")

        self.assertIsInstance(currency, CryptoCurrency)
        self.assertEqual(currency.name, "Ethereum")

    def test_factory_normalization(self):
        """Factory normalizes lowercase codes and outer spaces."""
        currency = create_currency(" btc ")

        self.assertEqual(currency.code, "BTC")

    def test_get_currency_factory(self):
        """Required get_currency factory creates supported currencies."""
        currency = get_currency("USD")

        self.assertIsInstance(currency, FiatCurrency)
        self.assertEqual(currency.code, "USD")
        self.assertEqual(
            currency.issuing_country,
            "United States",
        )

    def test_get_currency_crypto_metadata(self):
        """Factory provides cryptocurrency algorithm metadata."""
        currency = get_currency("BTC")

        self.assertIsInstance(currency, CryptoCurrency)
        self.assertEqual(currency.algorithm, "SHA-256")

    def test_unsupported_currency(self):
        """Unknown codes raise CurrencyNotFoundError."""
        with self.assertRaises(CurrencyNotFoundError):
            create_currency("XYZ")

    def test_get_currency_unknown_code(self):
        """Required factory rejects unsupported codes."""
        with self.assertRaises(CurrencyNotFoundError):
            get_currency("ABC")

    # Currency validation

    def test_empty_currency_code(self):
        """Empty currency codes are rejected."""
        with self.assertRaises(ValueError):
            create_currency("")

    def test_empty_currency_name(self):
        """Empty currency names are rejected."""
        with self.assertRaises(ValueError):
            FiatCurrency("USD", "")

    def test_code_too_short(self):
        """Currency code must have at least two characters."""
        with self.assertRaises(ValueError):
            FiatCurrency("A", "Test Currency")

    def test_code_too_long(self):
        """Currency code cannot exceed five characters."""
        with self.assertRaises(ValueError):
            FiatCurrency("ABCDEF", "Test Currency")

    def test_code_with_internal_spaces(self):
        """Currency code cannot contain internal spaces."""
        with self.assertRaises(ValueError):
            FiatCurrency("US D", "Test Currency")

    def test_code_with_special_characters(self):
        """Currency code cannot contain special characters."""
        with self.assertRaises(ValueError):
            FiatCurrency("U$D", "Test Currency")

    def test_code_uppercase_normalization(self):
        """Currency code is normalized to uppercase."""
        currency = FiatCurrency("usd", "US Dollar")

        self.assertEqual(currency.code, "USD")

    def test_invalid_currency_name_type(self):
        """Currency name must be a string."""
        with self.assertRaises(ValueError):
            FiatCurrency("USD", 123)

    # Display and serialization

    def test_display_info(self):
        """Factory returns the required fiat display format."""
        currency = create_currency("RUB")

        self.assertEqual(
            currency.get_display_info(),
            "[FIAT] RUB — Russian Ruble (Issuing: Russia)",
        )

    def test_serialization(self):
        """Serialization remains backward compatible."""
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
