"""Tests for external currency API clients."""

import os
import unittest
from unittest.mock import Mock, patch

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)


class TestApiClients(unittest.TestCase):
    """Test HTTP handling and currency rate conversion."""

    def setUp(self):
        """Create an isolated mock HTTP session."""
        self.session = Mock()
        self.response = Mock()

        self.response.raise_for_status.return_value = None
        self.session.get.return_value = self.response

    def test_abstract_base_client(self):
        """An abstract client cannot be instantiated."""
        with self.assertRaises(TypeError):
            BaseApiClient()

    def test_invalid_timeout(self):
        """Reject zero, negative, and infinite timeouts."""
        for timeout in (0, -1, float("inf")):
            with (
                self.subTest(timeout=timeout),
                self.assertRaises(ValueError),
            ):
                CoinGeckoClient(timeout=timeout)

    def test_coingecko_success(self):
        """Read valid cryptocurrency prices."""
        self.response.json.return_value = {
            "bitcoin": {"usd": 50000.0},
            "ethereum": {"usd": 2500.0},
        }

        with patch.dict(
            os.environ,
            {"COINGECKO_API_KEY": ""},
        ):
            client = CoinGeckoClient(session=self.session)
            rates = client.get_rates()

        self.assertEqual(
            rates,
            {
                "BTC_USD": 50000.0,
                "ETH_USD": 2500.0,
            },
        )

        self.assertEqual(
            self.session.get.call_args.kwargs["timeout"],
            10.0,
        )

    def test_coingecko_missing_currency(self):
        """Reject responses missing a requested cryptocurrency."""
        self.response.json.return_value = {
            "bitcoin": {"usd": 50000.0},
        }

        client = CoinGeckoClient(session=self.session)

        with self.assertRaises(ApiRequestError):
            client.get_rates()

    def test_coingecko_invalid_rate(self):
        """Reject negative cryptocurrency rates."""
        self.response.json.return_value = {
            "bitcoin": {"usd": -50000.0},
            "ethereum": {"usd": 2500.0},
        }

        client = CoinGeckoClient(session=self.session)

        with self.assertRaises(ApiRequestError):
            client.get_rates()

    def test_coingecko_timeout(self):
        """Convert HTTP timeouts to application errors."""
        self.session.get.side_effect = requests.Timeout("Connection timed out")

        client = CoinGeckoClient(session=self.session)

        with self.assertRaises(ApiRequestError):
            client.get_rates()

    def test_http_error(self):
        """Convert HTTP status errors to application errors."""
        self.response.raise_for_status.side_effect = requests.HTTPError(
            "429 Too Many Requests"
        )

        client = CoinGeckoClient(session=self.session)

        with self.assertRaises(ApiRequestError):
            client.get_rates()

    def test_invalid_json(self):
        """Reject malformed JSON responses."""
        self.response.json.side_effect = ValueError("Invalid JSON")

        client = CoinGeckoClient(session=self.session)

        with self.assertRaises(ApiRequestError):
            client.get_rates()

    def test_non_dictionary_response(self):
        """Reject JSON responses that are not objects."""
        self.response.json.return_value = [1, 2, 3]

        client = CoinGeckoClient(session=self.session)

        with self.assertRaises(ApiRequestError):
            client.get_rates()

    def test_coingecko_api_key_header(self):
        """Pass the optional CoinGecko demo API key."""
        self.response.json.return_value = {
            "bitcoin": {"usd": 50000.0},
            "ethereum": {"usd": 2500.0},
        }

        with patch.dict(
            os.environ,
            {"COINGECKO_API_KEY": "demo-test-key"},
        ):
            client = CoinGeckoClient(session=self.session)
            client.get_rates()

        headers = self.session.get.call_args.kwargs["headers"]

        self.assertEqual(
            headers["x-cg-demo-api-key"],
            "demo-test-key",
        )

    def test_fiat_missing_api_key(self):
        """Reject requests without the fiat API key."""
        with patch.dict(
            os.environ,
            {"EXCHANGE_RATE_API_KEY": ""},
        ):
            client = ExchangeRateApiClient(session=self.session)

            with self.assertRaises(ApiRequestError):
                client.get_rates()

    def test_fiat_success(self):
        """Convert USD-based rates to USD per currency unit."""
        self.response.json.return_value = {
            "result": "success",
            "base_code": "USD",
            "conversion_rates": {
                "EUR": 0.8,
                "RUB": 100.0,
            },
        }

        with patch.dict(
            os.environ,
            {"EXCHANGE_RATE_API_KEY": "test-key"},
        ):
            client = ExchangeRateApiClient(session=self.session)
            rates = client.get_rates()

        self.assertAlmostEqual(
            rates["EUR_USD"],
            1.25,
        )

        self.assertAlmostEqual(
            rates["RUB_USD"],
            0.01,
        )

    def test_fiat_api_failure(self):
        """Reject unsuccessful API responses."""
        self.response.json.return_value = {
            "result": "error",
        }

        with patch.dict(
            os.environ,
            {"EXCHANGE_RATE_API_KEY": "test-key"},
        ):
            client = ExchangeRateApiClient(session=self.session)

            with self.assertRaises(ApiRequestError):
                client.get_rates()

    def test_fiat_wrong_base_currency(self):
        """Reject responses using a base currency other than USD."""
        self.response.json.return_value = {
            "result": "success",
            "base_code": "EUR",
            "conversion_rates": {
                "EUR": 1.0,
                "RUB": 100.0,
            },
        }

        with patch.dict(
            os.environ,
            {"EXCHANGE_RATE_API_KEY": "test-key"},
        ):
            client = ExchangeRateApiClient(session=self.session)

            with self.assertRaises(ApiRequestError):
                client.get_rates()

    def test_fiat_missing_rate(self):
        """Reject incomplete fiat exchange-rate data."""
        self.response.json.return_value = {
            "result": "success",
            "base_code": "USD",
            "conversion_rates": {
                "EUR": 0.8,
            },
        }

        with patch.dict(
            os.environ,
            {"EXCHANGE_RATE_API_KEY": "test-key"},
        ):
            client = ExchangeRateApiClient(session=self.session)

            with self.assertRaises(ApiRequestError):
                client.get_rates()

    def test_fiat_zero_rate(self):
        """Reject zero fiat rates before division."""
        self.response.json.return_value = {
            "result": "success",
            "base_code": "USD",
            "conversion_rates": {
                "EUR": 0.0,
                "RUB": 100.0,
            },
        }

        with patch.dict(
            os.environ,
            {"EXCHANGE_RATE_API_KEY": "test-key"},
        ):
            client = ExchangeRateApiClient(session=self.session)

            with self.assertRaises(ApiRequestError):
                client.get_rates()


if __name__ == "__main__":
    unittest.main()
