"""Tests for SettingsLoader."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from valutatrade_hub.infra.settings import SettingsLoader


class TestSettingsLoader(unittest.TestCase):
    """Test singleton settings and environment variables."""

    def setUp(self):
        self.settings = SettingsLoader()

    def test_singleton(self):
        second_instance = SettingsLoader()
        self.assertIs(self.settings, second_instance)

    def test_project_root(self):
        self.assertIsInstance(self.settings.project_root, Path)
        self.assertTrue(self.settings.project_root.is_dir())

    def test_default_data_directory(self):
        with patch.dict(
            os.environ,
            {"VALUTATRADE_DATA_DIR": ""},
        ):
            self.assertEqual(
                self.settings.data_dir,
                self.settings.project_root / "data",
            )

    def test_custom_data_directory(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {"VALUTATRADE_DATA_DIR": directory},
            ),
        ):
            self.assertEqual(
                self.settings.data_dir,
                Path(directory).resolve(),
            )

    def test_default_ttl(self):
        with patch.dict(
            os.environ,
            {"VALUTATRADE_RATES_TTL": "3600"},
        ):
            self.assertEqual(
                self.settings.rates_ttl_seconds,
                3600,
            )

    def test_custom_ttl(self):
        with patch.dict(
            os.environ,
            {"VALUTATRADE_RATES_TTL": "600"},
        ):
            self.assertEqual(
                self.settings.rates_ttl_seconds,
                600,
            )

    def test_invalid_ttl_text(self):
        with (
            patch.dict(
                os.environ,
                {"VALUTATRADE_RATES_TTL": "invalid"},
            ),
            self.assertRaises(ValueError),
        ):
            _ = self.settings.rates_ttl_seconds

    def test_invalid_ttl_zero(self):
        with (
            patch.dict(
                os.environ,
                {"VALUTATRADE_RATES_TTL": "0"},
            ),
            self.assertRaises(ValueError),
        ):
            _ = self.settings.rates_ttl_seconds

    def test_invalid_ttl_negative(self):
        with (
            patch.dict(
                os.environ,
                {"VALUTATRADE_RATES_TTL": "-100"},
            ),
            self.assertRaises(ValueError),
        ):
            _ = self.settings.rates_ttl_seconds

    def test_api_key_from_environment(self):
        with patch.dict(
            os.environ,
            {"EXCHANGE_RATE_API_KEY": "test-key"},
        ):
            self.assertEqual(
                self.settings.exchange_rate_api_key,
                "test-key",
            )

    def test_api_urls(self):
        self.assertTrue(self.settings.coingecko_base_url.startswith("https://"))
        self.assertTrue(self.settings.exchange_rate_base_url.startswith("https://"))

    def test_named_settings_get(self):
        """Singleton exposes the configuration lookup specified in the task."""
        self.assertEqual(self.settings.get("base_currency"), "USD")
        self.assertEqual(
            self.settings.get("rates_ttl_seconds"), self.settings.rates_ttl_seconds
        )
        self.assertEqual(self.settings.get("unknown", 42), 42)
        with self.assertRaises(TypeError):
            self.settings.get(None)

    def test_log_file(self):
        self.assertEqual(
            self.settings.log_file,
            self.settings.project_root / "logs" / "valutatrade.log",
        )


if __name__ == "__main__":
    unittest.main()
