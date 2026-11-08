"""Tests for the JSON DatabaseManager."""

import json
import tempfile
import unittest
from pathlib import Path

from valutatrade_hub.infra.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):
    """Test singleton behavior and JSON storage."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db = DatabaseManager(cls.temp_dir.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        for filename in (
            "users.json",
            "portfolios.json",
            "rates.json",
        ):
            path = self.db.data_dir / filename
            path.unlink(missing_ok=True)

    def test_singleton(self):
        another_db = DatabaseManager()
        self.assertIs(self.db, another_db)

    def test_missing_users(self):
        self.assertEqual(self.db.load_users(), [])

    def test_save_and_load_users(self):
        users = [
            {
                "user_id": 1,
                "username": "olga",
            }
        ]

        self.db.save_users(users)

        self.assertEqual(self.db.load_users(), users)

    def test_missing_portfolios(self):
        self.assertEqual(self.db.load_portfolios(), [])

    def test_save_and_load_portfolios(self):
        portfolios = [
            {
                "user_id": 1,
                "wallets": {},
            }
        ]

        self.db.save_portfolios(portfolios)

        self.assertEqual(
            self.db.load_portfolios(),
            portfolios,
        )

    def test_missing_rates(self):
        self.assertEqual(
            self.db.load_rates(),
            {
                "pairs": {},
                "last_refresh": None,
            },
        )

    def test_save_and_load_rates(self):
        rates = {
            "pairs": {
                "BTC_USD": 65000.0,
            },
            "last_refresh": "2026-11-08T12:00:00",
        }

        self.db.save_rates(rates)

        self.assertEqual(self.db.load_rates(), rates)

    def test_invalid_users_type(self):
        with self.assertRaises(TypeError):
            self.db.save_users({})

    def test_invalid_portfolios_type(self):
        with self.assertRaises(TypeError):
            self.db.save_portfolios({})

    def test_invalid_rates_type(self):
        with self.assertRaises(TypeError):
            self.db.save_rates([])

    def test_corrupted_json(self):
        path = self.db.data_dir / "users.json"
        path.write_text("{invalid json", encoding="utf-8")

        with self.assertRaises(json.JSONDecodeError):
            self.db.load_users()

    def test_valid_json_file(self):
        self.db.save_users([{"user_id": 2}])

        path = self.db.data_dir / "users.json"

        with path.open("r", encoding="utf-8") as file:
            saved_data = json.load(file)

        self.assertEqual(saved_data, [{"user_id": 2}])

    def test_data_directory(self):
        self.assertIsInstance(self.db.data_dir, Path)
        self.assertTrue(self.db.data_dir.exists())

    def test_failed_serialization_preserves_file(self):
        original_data = [{"user_id": 1}]
        self.db.save_users(original_data)

        with self.assertRaises(TypeError):
            self.db.save_users([{"invalid": object()}])

        self.assertEqual(self.db.load_users(), original_data)


if __name__ == "__main__":
    unittest.main()
