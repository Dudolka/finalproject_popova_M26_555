"""Tests for application user use cases."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from valutatrade_hub.core.usecases import UserService


class TestUserService(unittest.TestCase):
    """Test registration, authentication, and user lookup."""

    def setUp(self):
        """Create an isolated temporary storage for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.users_file = Path(self.temp_dir.name) / "users.json"
        self.users_file.write_text(
            "[]",
            encoding="utf-8",
        )

        # Use an isolated storage object instead of the global singleton.
        self.database = TestDatabase(self.users_file)
        self.service = UserService(database=self.database)

    def test_register(self):
        """Test successful user registration."""
        user = self.service.register("olga", "password123")

        self.assertEqual(user.user_id, 1)
        self.assertEqual(user.username, "olga")
        self.assertTrue(user.verify_password("password123"))

    def test_register_saves_user(self):
        """Test that registration persists user data."""
        self.service.register("olga", "password123")

        saved_users = self.database.load_users()

        self.assertEqual(len(saved_users), 1)
        self.assertEqual(saved_users[0]["username"], "olga")
        self.assertNotIn("password123", str(saved_users))

    def test_register_multiple_users(self):
        """Test automatic generation of sequential user IDs."""
        first = self.service.register("olga", "password123")
        second = self.service.register("anna", "password456")

        self.assertEqual(first.user_id, 1)
        self.assertEqual(second.user_id, 2)

    def test_duplicate_username(self):
        """Test case-insensitive username uniqueness."""
        self.service.register("olga", "password123")

        with self.assertRaises(ValueError):
            self.service.register("OLGA", "anotherpassword")

    def test_empty_username(self):
        """Reject an empty username."""
        with self.assertRaises(ValueError):
            self.service.register("", "password123")

    def test_short_password(self):
        """Reject passwords shorter than four characters."""
        with self.assertRaises(ValueError):
            self.service.register("olga", "123")

    def test_login_success(self):
        """Test authentication with correct credentials."""
        self.service.register("olga", "password123")

        user = self.service.login("olga", "password123")

        self.assertEqual(user.username, "olga")

    def test_login_case_insensitive(self):
        """Test case-insensitive username lookup."""
        self.service.register("Olga", "password123")

        user = self.service.login("OLGA", "password123")

        self.assertEqual(user.username, "Olga")

    def test_login_wrong_password(self):
        """Reject an incorrect password."""
        self.service.register("olga", "password123")

        with self.assertRaises(ValueError):
            self.service.login("olga", "wrongpassword")

    def test_login_unknown_user(self):
        """Reject authentication of an unknown user."""
        with self.assertRaises(ValueError):
            self.service.login("unknown", "password123")

    def test_get_user(self):
        """Find an existing user by ID."""
        registered = self.service.register("olga", "password123")

        found = self.service.get_user(registered.user_id)

        self.assertEqual(found.user_id, registered.user_id)
        self.assertEqual(found.username, "olga")

    def test_get_unknown_user(self):
        """Reject an unknown user ID."""
        with self.assertRaises(ValueError):
            self.service.get_user(999)

    def test_invalid_user_id(self):
        """Reject a negative user ID."""
        with self.assertRaises(ValueError):
            self.service.get_user(-1)

    def test_invalid_password_type(self):
        """Reject a password with an invalid type."""
        with self.assertRaises(TypeError):
            self.service.register("olga", None)

    def test_database_injection(self):
        """Verify that UserService uses the injected storage."""
        with (
            patch.object(self.database, "load_users", return_value=[]),
            patch.object(self.database, "save_users") as mock_save,
        ):
            self.service.register("olga", "password123")
            mock_save.assert_called_once()


class TestDatabase:
    """Minimal isolated JSON storage for UserService tests."""

    def __init__(self, users_file: Path):
        self._users_file = users_file

    def load_users(self) -> list:
        """Load users from the temporary JSON file."""
        with self._users_file.open("r", encoding="utf-8") as file:
            return json.load(file)

    def save_users(self, users: list) -> None:
        """Save users to the temporary JSON file."""
        with self._users_file.open("w", encoding="utf-8") as file:
            json.dump(
                users,
                file,
                ensure_ascii=False,
                indent=4,
            )


if __name__ == "__main__":
    unittest.main()
