"""Tests for the currency exchange-rate updater."""

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.updater import RatesUpdater


class TestRatesUpdater(unittest.TestCase):
    """Test updates, caching, history, and recovery."""

    def setUp(self):
        """Create isolated storage and fake API clients."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.data_dir = Path(self.temp_dir.name)
        self.history_path = self.data_dir / "exchange_rates.json"

        self.settings = SimpleNamespace(
            data_dir=self.data_dir,
            rates_ttl_seconds=3600,
        )

        self.database = Mock()
        self.database.load_rates.return_value = {
            "pairs": {},
            "last_refresh": None,
        }

        self.crypto_client = Mock()
        self.crypto_client.get_rates.return_value = {
            "BTC_USD": 50000.0,
            "ETH_USD": 2500.0,
        }

        self.fiat_client = Mock()
        self.fiat_client.get_rates.return_value = {
            "EUR_USD": 1.25,
            "RUB_USD": 0.01,
        }

        self.updater = RatesUpdater(
            database=self.database,
            settings=self.settings,
            crypto_client=self.crypto_client,
            fiat_client=self.fiat_client,
            history_path=self.history_path,
        )

    def _make_snapshot(self, age_seconds=0):
        """Make a complete snapshot with a chosen age."""
        timestamp = datetime.now(UTC) - timedelta(seconds=age_seconds)

        return {
            "pairs": {
                "BTC_USD": 50000.0,
                "ETH_USD": 2500.0,
                "EUR_USD": 1.25,
                "RUB_USD": 0.01,
            },
            "last_refresh": timestamp.isoformat(),
        }

    def test_successful_update(self):
        """Save a complete set of four exchange rates."""
        snapshot = self.updater.update_rates(force=True)

        self.assertEqual(len(snapshot["pairs"]), 4)
        self.assertEqual(
            snapshot["pairs"]["BTC_USD"],
            50000.0,
        )
        self.assertEqual(
            snapshot["pairs"]["RUB_USD"],
            0.01,
        )

        self.database.save_rates.assert_called_once_with(snapshot)

    def test_history_created(self):
        """Create history after a successful update."""
        snapshot = self.updater.update_rates(force=True)

        self.assertTrue(self.history_path.exists())

        with self.history_path.open(encoding="utf-8") as file:
            history = json.load(file)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0], snapshot)

    def test_history_appended(self):
        """Preserve previous history entries."""
        first = self.updater.update_rates(force=True)

        self.crypto_client.get_rates.return_value = {
            "BTC_USD": 60000.0,
            "ETH_USD": 3000.0,
        }

        second = self.updater.update_rates(force=True)

        with self.history_path.open(encoding="utf-8") as file:
            history = json.load(file)

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0], first)
        self.assertEqual(history[1], second)

    def test_fresh_cache(self):
        """Do not request rates when cache is fresh."""
        cached = self._make_snapshot(age_seconds=60)
        self.database.load_rates.return_value = cached

        result = self.updater.get_rates()

        self.assertEqual(result, cached)
        self.crypto_client.get_rates.assert_not_called()
        self.fiat_client.get_rates.assert_not_called()
        self.database.save_rates.assert_not_called()

    def test_expired_cache(self):
        """Refresh rates when TTL has expired."""
        expired = self._make_snapshot(age_seconds=7200)
        self.database.load_rates.return_value = expired

        result = self.updater.get_rates()

        self.assertEqual(
            result["pairs"]["BTC_USD"],
            50000.0,
        )
        self.crypto_client.get_rates.assert_called_once()
        self.fiat_client.get_rates.assert_called_once()
        self.database.save_rates.assert_called_once()

    def test_force_update(self):
        """Force a refresh even with a fresh cache."""
        cached = self._make_snapshot(age_seconds=60)
        self.database.load_rates.return_value = cached

        self.updater.update_rates(force=True)

        self.crypto_client.get_rates.assert_called_once()
        self.fiat_client.get_rates.assert_called_once()
        self.database.save_rates.assert_called_once()

    def test_update_without_force_uses_cache(self):
        """Skip a refresh when cached rates are valid."""
        cached = self._make_snapshot(age_seconds=60)
        self.database.load_rates.return_value = cached

        result = self.updater.update_rates()

        self.assertEqual(result, cached)
        self.crypto_client.get_rates.assert_not_called()
        self.fiat_client.get_rates.assert_not_called()
        self.database.save_rates.assert_not_called()

    def test_crypto_api_failure(self):
        """Do not save data when crypto API fails."""
        self.crypto_client.get_rates.side_effect = ApiRequestError(
            "CoinGecko unavailable"
        )

        with self.assertRaises(ApiRequestError):
            self.updater.update_rates(force=True)

        self.database.save_rates.assert_not_called()
        self.assertFalse(self.history_path.exists())

    def test_fiat_api_failure(self):
        """Do not save data when fiat API fails."""
        self.fiat_client.get_rates.side_effect = ApiRequestError("Fiat API unavailable")

        with self.assertRaises(ApiRequestError):
            self.updater.update_rates(force=True)

        self.database.save_rates.assert_not_called()
        self.assertFalse(self.history_path.exists())

    def test_missing_currency(self):
        """Reject incomplete currency-pair data."""
        self.crypto_client.get_rates.return_value = {
            "BTC_USD": 50000.0,
        }

        with self.assertRaises(ApiRequestError):
            self.updater.update_rates(force=True)

        self.database.save_rates.assert_not_called()

    def test_invalid_rate(self):
        """Reject non-finite exchange rates."""
        self.crypto_client.get_rates.return_value = {
            "BTC_USD": float("nan"),
            "ETH_USD": 2500.0,
        }

        with self.assertRaises(ApiRequestError):
            self.updater.update_rates(force=True)

        self.database.save_rates.assert_not_called()

    def test_overlapping_pairs(self):
        """Reject duplicate pairs across API sources."""
        self.fiat_client.get_rates.return_value = {
            "BTC_USD": 1.0,
            "EUR_USD": 1.25,
            "RUB_USD": 0.01,
        }

        with self.assertRaises(ApiRequestError):
            self.updater.update_rates(force=True)

        self.database.save_rates.assert_not_called()

    def test_invalid_cached_timestamp(self):
        """Reject a cache with an invalid timestamp."""
        snapshot = self._make_snapshot()
        snapshot["last_refresh"] = "invalid-date"

        self.assertFalse(self.updater.is_fresh(snapshot))

    def test_future_cached_timestamp(self):
        """Reject timestamps in the future."""
        snapshot = self._make_snapshot(age_seconds=-7200)

        self.assertFalse(self.updater.is_fresh(snapshot))

    def test_cached_snapshot_with_missing_pair(self):
        """Reject a cache missing a required pair."""
        snapshot = self._make_snapshot()
        del snapshot["pairs"]["RUB_USD"]

        self.assertFalse(self.updater.is_fresh(snapshot))

    def test_corrupted_history(self):
        """Do not overwrite rates if history is corrupted."""
        previous = self._make_snapshot(age_seconds=7200)
        self.database.load_rates.return_value = previous

        self.history_path.write_text(
            "{invalid json",
            encoding="utf-8",
        )

        with self.assertRaises(ApiRequestError):
            self.updater.update_rates(force=True)

        self.database.save_rates.assert_not_called()

        self.assertEqual(
            self.history_path.read_text(encoding="utf-8"),
            "{invalid json",
        )

    def test_invalid_history_structure(self):
        """Reject history that is not a JSON list."""
        self.history_path.write_text(
            '{"invalid": "history"}',
            encoding="utf-8",
        )

        with self.assertRaises(ApiRequestError):
            self.updater.update_rates(force=True)

        self.database.save_rates.assert_not_called()

    def test_history_write_failure_rolls_back(self):
        """Restore old rates if history cannot be written."""
        previous = self._make_snapshot(age_seconds=7200)
        self.database.load_rates.return_value = previous

        with (
            patch.object(
                self.updater,
                "_append_history",
                side_effect=ApiRequestError("History write failed"),
            ),
            self.assertRaisesRegex(
                ApiRequestError,
                "восстановлен",
            ),
        ):
            self.updater.update_rates(force=True)

        self.assertEqual(
            self.database.save_rates.call_count,
            2,
        )

        first_saved = self.database.save_rates.call_args_list[0].args[0]

        self.assertNotEqual(first_saved, previous)
        self.assertEqual(
            self.database.save_rates.call_args_list[1],
            call(previous),
        )

    def test_history_write_and_rollback_failure(self):
        """Report when both history and rollback fail."""
        previous = self._make_snapshot(age_seconds=7200)
        self.database.load_rates.return_value = previous

        self.database.save_rates.side_effect = [
            None,
            OSError("Rollback failed"),
        ]

        with (
            patch.object(
                self.updater,
                "_append_history",
                side_effect=ApiRequestError("History write failed"),
            ),
            self.assertRaisesRegex(
                ApiRequestError,
                "Требуется проверка файлов",
            ),
        ):
            self.updater.update_rates(force=True)

        self.assertEqual(
            self.database.save_rates.call_count,
            2,
        )

    def test_snapshot_save_failure(self):
        """Do not update history if snapshot saving fails."""
        self.database.save_rates.side_effect = OSError("Cannot save rates")

        with self.assertRaises(OSError):
            self.updater.update_rates(force=True)

        self.assertFalse(self.history_path.exists())
        self.database.save_rates.assert_called_once()


if __name__ == "__main__":
    unittest.main()
