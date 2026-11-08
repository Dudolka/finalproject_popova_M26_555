"""Application use cases for ValutaTrade Hub."""

from datetime import UTC, datetime

from valutatrade_hub.core.models import User
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader


class UserService:
    """Handle user registration and authentication."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
    ) -> None:
        if database is None:
            settings = SettingsLoader()
            database = DatabaseManager(settings.data_dir)

        self._database = database

    def register(self, username: str, password: str) -> User:
        """Register a new user and save their credentials."""
        if not isinstance(username, str):
            raise TypeError("Имя пользователя должно быть строкой")

        if not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")

        if not isinstance(password, str):
            raise TypeError("Пароль должен быть строкой")

        if len(password) < 4:
            raise ValueError("Пароль должен содержать минимум 4 символа")

        username = username.strip()
        users_data = self._database.load_users()

        for user_data in users_data:
            existing_username = user_data["username"]

            if existing_username.casefold() == username.casefold():
                raise ValueError(f"Пользователь {username} уже существует")

        next_user_id = (
            max(
                (user_data["user_id"] for user_data in users_data),
                default=0,
            )
            + 1
        )

        user = User(
            user_id=next_user_id,
            username=username,
            hashed_password="",
            salt="initial",
            registration_date=datetime.now(UTC),
        )

        user.change_password(password)

        users_data.append(user.to_dict())
        self._database.save_users(users_data)

        return user

    def login(self, username: str, password: str) -> User:
        """Authenticate a registered user."""
        if not isinstance(username, str):
            raise TypeError("Имя пользователя должно быть строкой")

        if not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")

        if not isinstance(password, str):
            raise TypeError("Пароль должен быть строкой")

        username = username.strip()

        for user_data in self._database.load_users():
            if user_data["username"].casefold() == username.casefold():
                user = User.from_dict(user_data)

                if user.verify_password(password):
                    return user

                break

        raise ValueError("Неверное имя пользователя или пароль")

    def get_user(self, user_id: int) -> User:
        """Find a registered user by ID."""
        if type(user_id) is not int:
            raise TypeError("ID пользователя должен быть целым числом")

        if user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным")

        for user_data in self._database.load_users():
            if user_data["user_id"] == user_id:
                return User.from_dict(user_data)

        raise ValueError(f"Пользователь с ID {user_id} не найден")
