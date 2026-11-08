"""Tests for the User model."""

import unittest
from datetime import datetime

from valutatrade_hub.core.models import User


class TestUser(unittest.TestCase):
    """Verify user creation, passwords, and serialization."""

    def setUp(self):
        """Create a user before each test."""
        self.user = User(
            user_id=1,
            username="alice",
            hashed_password="",
            salt="initial_salt",
            registration_date=datetime(2026, 11, 7),
        )
        self.user.change_password("1234")

    def test_user_creation(self):
        self.assertEqual(self.user.user_id, 1)
        self.assertEqual(self.user.username, "alice")

    def test_correct_password(self):
        self.assertTrue(self.user.verify_password("1234"))

    def test_incorrect_password(self):
        self.assertFalse(self.user.verify_password("wrong"))

    def test_password_change(self):
        self.user.change_password("new_password")
        self.assertTrue(self.user.verify_password("new_password"))
        self.assertFalse(self.user.verify_password("1234"))

    def test_short_password(self):
        with self.assertRaises(ValueError):
            self.user.change_password("123")

    def test_empty_username(self):
        with self.assertRaises(ValueError):
            self.user.username = ""

    def test_public_info_excludes_password(self):
        info = self.user.get_user_info()
        self.assertNotIn("hashed_password", info)
        self.assertNotIn("salt", info)

    def test_serialization(self):
        data = self.user.to_dict()
        restored = User.from_dict(data)

        self.assertEqual(restored.username, "alice")
        self.assertTrue(restored.verify_password("1234"))


if __name__ == "__main__":
    unittest.main()
