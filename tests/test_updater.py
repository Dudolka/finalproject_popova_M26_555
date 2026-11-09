"""Tests for the MEPhI-compliant exchange-rate updater."""

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesHistoryStorage
from valutatrade_hub.parser_service.updater import RatesUpdater


class TestRatesUpdater(unittest.TestCase):
    """Verify fetching, caching, failures, and historical records."""

    def setUp(self):
        """Create isolated storage and mocked providers."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.data_dir = Path(temporary.name)
        self.history_path = self.data_dir / "exchange_rates.json"

        self.settings = SimpleNamespace(
            data_dir=self.data_dir,
            rates_ttl_seconds=3600,
        )
        self.config = ParserConfig()

        self.database = Mock()
        self.database.load_rates.return_value = {
            "pairs": {},
            "last_refresh": None,
        }

        self.crypto_client = Mock()
        self.crypto_client.fetch_rates.return_value = {
            "BTC_USD": 50000.0,
            "ETH_USD": 2500.0,
            "SOL_USD": 150.0,
        }

        self.fiat_client = Mock()
        self.fiat_client.fetch_rates.return_value = {
            "EUR_USD": 1.25,
            "GBP_USD": 1.40,
            "RUB_USD": 0.01,
        }

        self.storage = RatesHistoryStorage(self.history_path)

        self.updater = RatesUpdater(
            database=self.database,
            settings=self.settings,
            crypto_client=self.crypto_client,
            fiat_client=self.fiat_client,
            config=self.config,
            storage=self.storage,
        )

    @staticmethod
    def _timestamp(age_seconds=0):
        """Return a UTC timestamp with a configurable age."""
        return (datetime.now(UTC) - timedelta(seconds=age_seconds)).isoformat()

    def _snapshot(self, age_seconds=60):
        """Build a complete cache using the required data structure."""
        timestamp = self._timestamp(age_seconds)

        pairs = {}

        for pair, rate in {
            **self.crypto_client.fetch_rates.return_value,
            **self.fiat_client.fetch_rates.return_value,
        }.items():
            source = (
                "CoinGecko"
                if pair.startswith(("BTC_", "ETH_", "SOL_"))
                else "ExchangeRate-API"
            )

            pairs[pair] = {
                "rate": rate,
                "updated_at": timestamp,
                "source": source,
            }

        return {
            "pairs": pairs,
            "last_refresh": timestamp,
        }

    def test_successful_update(self):
        """Save six configured exchange-rate pairs."""
        result = self.updater.run_update()

        self.assertEqual(len(result["pairs"]), 6)
        self.assertEqual(
            result["pairs"]["BTC_USD"]["rate"],
            50000.0,
        )
        self.assertEqual(
            result["pairs"]["GBP_USD"]["rate"],
            1.40,
        )
        self.assertIn("SOL_USD", result["pairs"])

        self.database.save_rates.assert_called_once_with(result)

        self.crypto_client.fetch_rates.assert_called_once()
        self.fiat_client.fetch_rates.assert_called_once()

    def test_cache_metadata(self):
        """Store rate, updated_at, and source for each currency pair."""
        result = self.updater.run_update()

        for pair, entry in result["pairs"].items():
            with self.subTest(pair=pair):
                self.assertEqual(
                    set(entry),
                    {"rate", "updated_at", "source"},
                )
                self.assertGreater(entry["rate"], 0)
                self.assertTrue(entry["updated_at"].endswith("Z"))
                self.assertIn(
                    entry["source"],
                    {"CoinGecko", "ExchangeRate-API"},
                )

        self.assertTrue(result["last_refresh"].endswith("Z"))

    def test_history_created(self):
        """Save one historical observation per currency pair."""
        self.updater.run_update()

        records = self.storage.read_history()

        self.assertEqual(len(records), 6)
        self.assertEqual(
            {
                f"{record['from_currency']}_{record['to_currency']}"
                for record in records
            },
            self.config.required_pairs,
        )

    def test_history_record_structure(self):
        """Follow the history format specified by MEPhI."""
        self.updater.run_update()

        records = self.storage.read_history()

        for record in records:
            with self.subTest(record=record["id"]):
                self.assertEqual(
                    set(record),
                    {
                        "id",
                        "from_currency",
                        "to_currency",
                        "rate",
                        "timestamp",
                        "source",
                        "meta",
                    },
                )
                self.assertTrue(record["timestamp"].endswith("Z"))
                self.assertTrue(record["id"].endswith(record["timestamp"]))

    def test_unique_history_ids(self):
        """Prevent duplicate observation identifiers."""
        self.updater.run_update()

        records = self.storage.read_history()
        identifiers = [record["id"] for record in records]

        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_fetch_rates_interface(self):
        """Use the required fetch_rates API-client method."""
        self.updater.run_update()

        self.crypto_client.fetch_rates.assert_called_once()
        self.fiat_client.fetch_rates.assert_called_once()
        self.crypto_client.get_rates.assert_not_called()
        self.fiat_client.get_rates.assert_not_called()

    def test_crypto_source_only(self):
        """Update only CoinGecko when explicitly selected."""
        result = self.updater.run_update(source="coingecko")

        self.assertEqual(
            set(result["pairs"]),
            {"BTC_USD", "ETH_USD", "SOL_USD"},
        )
        self.crypto_client.fetch_rates.assert_called_once()
        self.fiat_client.fetch_rates.assert_not_called()
        self.assertEqual(len(self.storage.read_history()), 3)

    def test_fiat_source_only(self):
        """Update only ExchangeRate-API when selected."""
        result = self.updater.run_update(source="exchangerate")

        self.assertEqual(
            set(result["pairs"]),
            {"EUR_USD", "GBP_USD", "RUB_USD"},
        )
        self.crypto_client.fetch_rates.assert_not_called()
        self.fiat_client.fetch_rates.assert_called_once()
        self.assertEqual(len(self.storage.read_history()), 3)

    def test_invalid_source(self):
        """Reject an unknown provider before changing data."""
        with self.assertRaises(ValueError):
            self.updater.run_update(source="unknown")

        self.database.save_rates.assert_not_called()
        self.crypto_client.fetch_rates.assert_not_called()
        self.fiat_client.fetch_rates.assert_not_called()

    def test_crypto_failure_allows_fiat_update(self):
        """A CoinGecko failure must not prevent fiat updates."""
        self.crypto_client.fetch_rates.side_effect = ApiRequestError(
            "CoinGecko unavailable"
        )

        result = self.updater.run_update()

        self.assertEqual(
            set(result["pairs"]),
            {"EUR_USD", "GBP_USD", "RUB_USD"},
        )
        self.database.save_rates.assert_called_once()
        self.assertEqual(len(self.storage.read_history()), 3)

    def test_fiat_failure_allows_crypto_update(self):
        """A fiat-provider failure must not prevent crypto updates."""
        self.fiat_client.fetch_rates.side_effect = ApiRequestError(
            "ExchangeRate-API unavailable"
        )

        result = self.updater.run_update()

        self.assertEqual(
            set(result["pairs"]),
            {"BTC_USD", "ETH_USD", "SOL_USD"},
        )
        self.database.save_rates.assert_called_once()
        self.assertEqual(len(self.storage.read_history()), 3)

    def test_both_sources_fail(self):
        """Keep existing data unchanged if both providers fail."""
        self.crypto_client.fetch_rates.side_effect = ApiRequestError(
            "Crypto unavailable"
        )
        self.fiat_client.fetch_rates.side_effect = ApiRequestError("Fiat unavailable")

        with self.assertRaises(ApiRequestError):
            self.updater.run_update()

        self.database.save_rates.assert_not_called()
        self.assertFalse(self.history_path.exists())

    def test_missing_currency(self):
        """Reject an incomplete provider response."""
        self.crypto_client.fetch_rates.return_value = {
            "BTC_USD": 50000.0,
            "ETH_USD": 2500.0,
        }
        self.fiat_client.fetch_rates.side_effect = ApiRequestError("Fiat unavailable")

        with self.assertRaises(ApiRequestError):
            self.updater.run_update()

        self.database.save_rates.assert_not_called()

    def test_invalid_rate(self):
        """Reject non-finite rates from a selected provider."""
        self.crypto_client.fetch_rates.return_value = {
            "BTC_USD": float("nan"),
            "ETH_USD": 2500.0,
            "SOL_USD": 150.0,
        }

        result = self.updater.run_update()

        self.assertEqual(
            set(result["pairs"]),
            {"EUR_USD", "GBP_USD", "RUB_USD"},
        )

    def test_fresh_cache(self):
        """Use fresh cached rates without requesting external data."""
        cached = self._snapshot(age_seconds=60)
        self.database.load_rates.return_value = cached

        result = self.updater.get_rates()

        self.assertEqual(result, cached)
        self.crypto_client.fetch_rates.assert_not_called()
        self.fiat_client.fetch_rates.assert_not_called()

    def test_expired_cache(self):
        """Refresh cached rates once their TTL expires."""
        cached = self._snapshot(age_seconds=7200)
        self.database.load_rates.return_value = cached

        result = self.updater.get_rates()

        self.assertEqual(len(result["pairs"]), 6)
        self.crypto_client.fetch_rates.assert_called_once()
        self.fiat_client.fetch_rates.assert_called_once()

    def test_force_update(self):
        """Refresh even when the existing cache is fresh."""
        cached = self._snapshot(age_seconds=60)
        self.database.load_rates.return_value = cached

        self.updater.update_rates(force=True)

        self.crypto_client.fetch_rates.assert_called_once()
        self.fiat_client.fetch_rates.assert_called_once()

    def test_update_without_force_uses_cache(self):
        """Preserve the legacy non-forced caching interface."""
        cached = self._snapshot(age_seconds=60)
        self.database.load_rates.return_value = cached

        result = self.updater.update_rates(force=False)

        self.assertEqual(result, cached)
        self.crypto_client.fetch_rates.assert_not_called()
        self.fiat_client.fetch_rates.assert_not_called()

    def test_one_expired_pair_invalidates_cache(self):
        """Check individual updated_at rather than last_refresh alone."""
        cached = self._snapshot(age_seconds=60)

        cached["pairs"]["BTC_USD"]["updated_at"] = self._timestamp(age_seconds=7200)
        self.assertFalse(self.updater.is_fresh(cached))

    def test_future_pair_timestamp(self):
        """Reject timestamps that lie in the future."""
        cached = self._snapshot(age_seconds=60)

        cached["pairs"]["BTC_USD"]["updated_at"] = self._timestamp(age_seconds=-7200)
        self.assertFalse(self.updater.is_fresh(cached))

    def test_missing_pair_invalidates_cache(self):
        """A complete cache must contain every configured pair."""
        cached = self._snapshot()
        del cached["pairs"]["SOL_USD"]

        self.assertFalse(self.updater.is_fresh(cached))

    def test_old_numeric_cache_can_be_read(self):
        """Support reading numeric cache entries during migration."""
        timestamp = self._timestamp(age_seconds=60)

        cached = {
            "pairs": {
                "BTC_USD": 50000.0,
                "ETH_USD": 2500.0,
                "SOL_USD": 150.0,
                "EUR_USD": 1.25,
                "GBP_USD": 1.40,
                "RUB_USD": 0.01,
            },
            "last_refresh": timestamp,
        }

        self.assertTrue(self.updater.is_fresh(cached))

    def test_corrupted_history(self):
        """Do not change the cache when history cannot be read."""
        self.history_path.write_text(
            "{invalid json",
            encoding="utf-8",
        )

        with self.assertRaises(ApiRequestError):
            self.updater.run_update()

        self.database.save_rates.assert_not_called()

    def test_history_write_failure_rolls_back(self):
        """Restore the previous cache when history persistence fails."""
        previous = self._snapshot(age_seconds=7200)
        self.database.load_rates.return_value = previous

        self.storage.append_records = Mock(
            side_effect=ApiRequestError("History write failed")
        )

        with self.assertRaisesRegex(
            ApiRequestError,
            "восстановлены",
        ):
            self.updater.run_update()

        self.assertEqual(self.database.save_rates.call_count, 2)
        self.assertEqual(
            self.database.save_rates.call_args_list[-1].args[0],
            previous,
        )

    def test_history_write_and_rollback_failure(self):
        """Report that manual file inspection is needed after rollback failure."""
        previous = self._snapshot(age_seconds=7200)
        self.database.load_rates.return_value = previous
        self.database.save_rates.side_effect = [
            None,
            OSError("Rollback failed"),
        ]

        self.storage.append_records = Mock(
            side_effect=ApiRequestError("History write failed")
        )

        with self.assertRaisesRegex(
            ApiRequestError,
            "Требуется проверка файлов",
        ):
            self.updater.run_update()

        self.assertEqual(self.database.save_rates.call_count, 2)

    def test_cache_write_failure(self):
        """Do not append history when saving the cache fails."""
        self.database.save_rates.side_effect = OSError("Cannot save rates")

        with self.assertRaises(OSError):
            self.updater.run_update()

        self.assertFalse(self.history_path.exists())


if __name__ == "__main__":
    unittest.main()
