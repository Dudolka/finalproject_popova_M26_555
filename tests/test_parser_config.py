"""Tests for Parser Service configuration."""

import os
import unittest
from unittest.mock import patch

from valutatrade_hub.parser_service.config import ParserConfig


class TestParserConfig(unittest.TestCase):
    """Validate centralized parser configuration."""

    def test_default_configuration(self):
        """Check default currencies and network settings."""
        config = ParserConfig()

        self.assertEqual(config.base_currency, "USD")
        self.assertEqual(config.request_timeout, 10.0)

        self.assertEqual(
            config.fiat_currencies,
            ("EUR", "GBP", "RUB"),
        )
        self.assertEqual(
            config.crypto_currencies,
            ("BTC", "ETH", "SOL"),
        )

    def test_required_pairs(self):
        """Check generated currency pairs."""
        config = ParserConfig()

        self.assertEqual(
            config.required_pairs,
            frozenset(
                {
                    "BTC_USD",
                    "ETH_USD",
                    "SOL_USD",
                    "EUR_USD",
                    "GBP_USD",
                    "RUB_USD",
                }
            ),
        )

    def test_api_key_from_environment(self):
        """Read API credentials from environment variables."""
        with patch.dict(
            os.environ,
            {
                "EXCHANGE_RATE_API_KEY": "test-key-123",
                "COINGECKO_API_KEY": "crypto-key-456",
            },
        ):
            config = ParserConfig()

        self.assertEqual(
            config.exchangerate_api_key,
            "test-key-123",
        )
        self.assertEqual(
            config.coingecko_api_key,
            "crypto-key-456",
        )

    def test_api_keys_hidden_from_repr(self):
        """Protect API credentials from accidental logging."""
        config = ParserConfig(
            exchangerate_api_key="SECRET_API_KEY",
            coingecko_api_key="SECRET_CRYPTO_KEY",
        )

        self.assertNotIn("SECRET_API_KEY", repr(config))
        self.assertNotIn("SECRET_CRYPTO_KEY", repr(config))

    def test_invalid_timeout(self):
        """Reject invalid request timeouts."""
        values = (
            0,
            -1,
            float("nan"),
            float("inf"),
            True,
        )

        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ParserConfig(request_timeout=value)

    def test_invalid_base_currency(self):
        """Reject unsupported base currency."""
        with self.assertRaises(ValueError):
            ParserConfig(base_currency="EUR")

    def test_duplicate_currencies(self):
        """Reject duplicated currency codes."""
        with self.assertRaises(ValueError):
            ParserConfig(
                fiat_currencies=("EUR", "EUR"),
            )

    def test_crypto_id_map_consistency(self):
        """Every cryptocurrency needs a CoinGecko ID."""
        with self.assertRaises(ValueError):
            ParserConfig(
                crypto_id_map={"BTC": "bitcoin"},
            )

    def test_invalid_api_url(self):
        """Reject unencrypted API endpoints."""
        with self.assertRaises(ValueError):
            ParserConfig(
                coingecko_url="http://example.com",
            )


if __name__ == "__main__":
    unittest.main()
