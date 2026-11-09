"""Extended tests for configured currency API clients."""

import unittest
from unittest.mock import Mock

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig


class TestConfiguredApiClients(unittest.TestCase):
    """Verify configurable providers and HTTP error handling."""

    def setUp(self):
        """Create a mock HTTP session and configuration."""
        self.session = Mock()
        self.response = Mock()

        self.response.raise_for_status.return_value = None
        self.session.get.return_value = self.response

        self.config = ParserConfig(
            exchangerate_api_key="test-api-key",
            coingecko_api_key="test-crypto-key",
            request_timeout=7.0,
        )

    def test_configured_crypto_currencies(self):
        """Fetch BTC, ETH, and SOL using CoinGecko IDs."""
        self.response.json.return_value = {
            "bitcoin": {"usd": 50000.0},
            "ethereum": {"usd": 2500.0},
            "solana": {"usd": 150.0},
        }

        client = CoinGeckoClient(
            session=self.session,
            config=self.config,
        )

        rates = client.fetch_rates()

        self.assertEqual(
            rates,
            {
                "BTC_USD": 50000.0,
                "ETH_USD": 2500.0,
                "SOL_USD": 150.0,
            },
        )

        request = self.session.get.call_args.kwargs

        self.assertEqual(
            request["params"]["ids"],
            "bitcoin,ethereum,solana",
        )
        self.assertEqual(
            request["params"]["vs_currencies"],
            "usd",
        )
        self.assertEqual(request["timeout"], 7.0)

    def test_configured_fiat_currencies(self):
        """Fetch EUR, GBP, and RUB with correct conversion."""
        self.response.json.return_value = {
            "result": "success",
            "base_code": "USD",
            "conversion_rates": {
                "EUR": 0.8,
                "GBP": 0.5,
                "RUB": 100.0,
            },
        }

        client = ExchangeRateApiClient(
            session=self.session,
            config=self.config,
        )

        rates = client.fetch_rates()

        self.assertAlmostEqual(rates["EUR_USD"], 1.25)
        self.assertAlmostEqual(rates["GBP_USD"], 2.0)
        self.assertAlmostEqual(rates["RUB_USD"], 0.01)
        self.assertEqual(len(rates), 3)

    def test_configured_crypto_api_key(self):
        """Send the configured CoinGecko key in headers."""
        self.response.json.return_value = {
            "bitcoin": {"usd": 50000.0},
            "ethereum": {"usd": 2500.0},
            "solana": {"usd": 150.0},
        }

        client = CoinGeckoClient(
            session=self.session,
            config=self.config,
        )

        client.fetch_rates()

        headers = self.session.get.call_args.kwargs["headers"]

        self.assertEqual(
            headers["x-cg-demo-api-key"],
            "test-crypto-key",
        )

    def test_http_401(self):
        """Translate an unauthorized response into ApiRequestError."""
        self.response.status_code = 401
        self.response.raise_for_status.side_effect = requests.HTTPError("Unauthorized")

        client = CoinGeckoClient(
            session=self.session,
            config=self.config,
        )

        with self.assertRaisesRegex(
            ApiRequestError,
            "401",
        ):
            client.fetch_rates()

    def test_http_429(self):
        """Translate a rate-limit response into ApiRequestError."""
        self.response.status_code = 429
        self.response.raise_for_status.side_effect = requests.HTTPError(
            "Too Many Requests"
        )

        client = CoinGeckoClient(
            session=self.session,
            config=self.config,
        )

        with self.assertRaisesRegex(
            ApiRequestError,
            "429",
        ):
            client.fetch_rates()

    def test_configured_timeout(self):
        """A configured timeout must reach the HTTP session."""
        self.session.get.side_effect = requests.Timeout("Request timeout")

        client = CoinGeckoClient(
            session=self.session,
            config=self.config,
        )

        with self.assertRaises(ApiRequestError):
            client.fetch_rates()

        self.assertEqual(
            self.session.get.call_args.kwargs["timeout"],
            7.0,
        )

    def test_missing_solana(self):
        """Reject a response missing a configured cryptocurrency."""
        self.response.json.return_value = {
            "bitcoin": {"usd": 50000.0},
            "ethereum": {"usd": 2500.0},
        }

        client = CoinGeckoClient(
            session=self.session,
            config=self.config,
        )

        with self.assertRaises(ApiRequestError):
            client.fetch_rates()

    def test_get_rates_compatibility(self):
        """Preserve the legacy get_rates interface."""
        self.response.json.return_value = {
            "bitcoin": {"usd": 50000.0},
            "ethereum": {"usd": 2500.0},
            "solana": {"usd": 150.0},
        }

        client = CoinGeckoClient(
            session=self.session,
            config=self.config,
        )

        self.assertEqual(
            client.get_rates(),
            {
                "BTC_USD": 50000.0,
                "ETH_USD": 2500.0,
                "SOL_USD": 150.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
