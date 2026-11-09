"""Tests for the Parser Service history storage."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.storage import (
    RatesHistoryStorage,
)


class TestRatesHistoryStorage(unittest.TestCase):
    """Verify historical records and atomic persistence."""

    def setUp(self):
        """Create an isolated temporary history file."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.path = Path(self.temp_dir.name) / "exchange_rates.json"
        self.storage = RatesHistoryStorage(self.path)

        self.record = self.storage.create_record(
            from_currency="BTC",
            to_currency="USD",
            rate=50000.0,
            timestamp="2026-11-09T17:00:00Z",
            source="CoinGecko",
        )

    def test_create_record(self):
        """Check the structure of a historical observation."""
        self.assertEqual(
            self.record["id"],
            "BTC_USD_2026-11-09T17:00:00Z",
        )
        self.assertEqual(
            self.record["from_currency"],
            "BTC",
        )
        self.assertEqual(
            self.record["to_currency"],
            "USD",
        )
        self.assertEqual(
            self.record["rate"],
            50000.0,
        )
        self.assertEqual(
            self.record["source"],
            "CoinGecko",
        )
        self.assertEqual(self.record["meta"], {})

    def test_timezone_normalization(self):
        """Equivalent timestamps produce identical IDs."""
        record = self.storage.create_record(
            "BTC",
            "USD",
            50000.0,
            "2026-11-09T20:00:00+03:00",
            "CoinGecko",
        )

        self.assertEqual(
            record["id"],
            self.record["id"],
        )

    def test_save_and_read(self):
        """Saved observations can be read again."""
        self.storage.save_history([self.record])

        self.assertTrue(self.path.exists())
        self.assertEqual(
            self.storage.read_history(),
            [self.record],
        )

    def test_append_new_record(self):
        """A new observation is appended."""
        added = self.storage.append_records([self.record])

        self.assertEqual(added, 1)
        self.assertEqual(
            self.storage.read_history(),
            [self.record],
        )

    def test_duplicate_id_is_not_appended(self):
        """Duplicate records are skipped."""
        self.storage.append_records([self.record])

        added = self.storage.append_records([self.record])

        self.assertEqual(added, 0)
        self.assertEqual(
            len(self.storage.read_history()),
            1,
        )

    def test_different_times_create_separate_records(self):
        """Different measurements remain in history."""
        second = self.storage.create_record(
            "BTC",
            "USD",
            51000.0,
            "2026-11-09T18:00:00Z",
            "CoinGecko",
        )

        self.storage.append_records([self.record])
        self.storage.append_records([second])

        self.assertEqual(
            len(self.storage.read_history()),
            2,
        )

    def test_invalid_rates(self):
        """Reject invalid exchange-rate values."""
        invalid_rates = (
            -1,
            0,
            float("nan"),
            float("inf"),
            True,
        )

        for value in invalid_rates:
            with self.subTest(value=value), self.assertRaises(ApiRequestError):
                self.storage.create_record(
                    "BTC",
                    "USD",
                    value,
                    "2026-11-09T17:00:00Z",
                    "CoinGecko",
                )

    def test_invalid_currency_code(self):
        """Reject lowercase currency identifiers."""
        with self.assertRaises(ApiRequestError):
            self.storage.create_record(
                "btc",
                "USD",
                50000.0,
                "2026-11-09T17:00:00Z",
                "CoinGecko",
            )

    def test_missing_timezone(self):
        """Reject timestamps without timezone information."""
        with self.assertRaises(ApiRequestError):
            self.storage.create_record(
                "BTC",
                "USD",
                50000.0,
                "2026-11-09T17:00:00",
                "CoinGecko",
            )

    def test_corrupted_json_is_rejected(self):
        """Do not overwrite corrupted history silently."""
        self.path.write_text(
            "{invalid json",
            encoding="utf-8",
        )

        with self.assertRaises(ApiRequestError):
            self.storage.read_history()

        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            "{invalid json",
        )

    def test_invalid_record_id(self):
        """Reject inconsistent record identifiers."""
        invalid_record = dict(self.record)
        invalid_record["id"] = "WRONG_ID"

        with self.assertRaises(ApiRequestError):
            self.storage.save_history([invalid_record])

    def test_atomic_save_failure_preserves_old_file(self):
        """Failed replacement must preserve existing history."""
        self.storage.save_history([self.record])

        before = self.path.read_bytes()

        second = self.storage.create_record(
            "ETH",
            "USD",
            2500.0,
            "2026-11-09T18:00:00Z",
            "CoinGecko",
        )

        with (
            patch(
                "valutatrade_hub.parser_service.storage.os.replace",
                side_effect=OSError("Simulated disk error"),
            ),
            self.assertRaises(ApiRequestError),
        ):
            self.storage.save_history([self.record, second])

        self.assertEqual(self.path.read_bytes(), before)

    def test_saved_json_is_valid(self):
        """History is stored as valid JSON."""
        self.storage.save_history([self.record])

        with self.path.open(encoding="utf-8") as file:
            data = json.load(file)

        self.assertIsInstance(data, list)
        self.assertEqual(
            data[0]["id"],
            self.record["id"],
        )


if __name__ == "__main__":
    unittest.main()
