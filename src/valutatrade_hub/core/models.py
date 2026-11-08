"""Domain models for ValutaTrade Hub."""

import hashlib
import hmac
import secrets
from datetime import datetime


class User:
    """Represent a registered user with password verification."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ) -> None:
        if type(user_id) is not int or user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным целым числом")

        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")

        if not isinstance(hashed_password, str):
            raise TypeError("Хеш пароля должен быть строкой")

        if not isinstance(salt, str) or not salt:
            raise ValueError("Соль не может быть пустой")

        if not isinstance(registration_date, datetime):
            raise TypeError("Дата регистрации должна иметь тип datetime")

        self._user_id = user_id
        self._username = username.strip()
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @property
    def user_id(self) -> int:
        """Return the user identifier."""
        return self._user_id

    @property
    def username(self) -> str:
        """Return the username."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        """Validate and update the username."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Return the stored password hash for persistence."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Return the salt used for password hashing."""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Return the registration date."""
        return self._registration_date

    def change_password(self, new_password: str) -> None:
        """Validate and hash a new password with a fresh salt."""
        if not isinstance(new_password, str) or len(new_password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")

        self._salt = secrets.token_hex(16)
        self._hashed_password = hashlib.sha256(
            (new_password + self._salt).encode("utf-8")
        ).hexdigest()

    def verify_password(self, password: str) -> bool:
        """Check a password without exposing the stored hash."""
        if not isinstance(password, str):
            return False

        candidate = hashlib.sha256((password + self._salt).encode("utf-8")).hexdigest()

        return hmac.compare_digest(candidate, self._hashed_password)

    def get_user_info(self) -> dict:
        """Return public user information without password credentials."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    def to_dict(self) -> dict:
        """Serialize the user for JSON storage."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """Restore a user from JSON-compatible data."""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(data["registration_date"]),
        )


class Wallet:
    """Represent a currency wallet with a non-negative balance."""

    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")

        if not isinstance(balance, (int, float)) or isinstance(balance, bool):
            raise TypeError("Баланс должен быть числом")

        if not 0 <= balance < float("inf"):
            raise ValueError("Баланс должен быть конечным и неотрицательным")

        self._currency_code = currency_code.strip().upper()
        self._balance = float(balance)

    @property
    def currency_code(self) -> str:
        """Return the currency code."""
        return self._currency_code

    @property
    def balance(self) -> float:
        """Return the current balance."""
        return self._balance

    def deposit(self, amount: float) -> None:
        """Add a positive amount to the wallet."""
        self._validate_amount(amount)

        new_balance = self._balance + amount
        if not new_balance < float("inf"):
            raise ValueError("Баланс после пополнения превышает допустимое значение")

        self._balance = new_balance

    def withdraw(self, amount: float) -> None:
        """Withdraw an amount if sufficient funds are available."""
        self._validate_amount(amount)

        if amount > self._balance:
            raise ValueError("Недостаточно средств на кошельке")

        self._balance -= amount

    @staticmethod
    def _validate_amount(amount: float) -> None:
        """Validate a transaction amount."""
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise TypeError("Сумма операции должна быть числом")

        if not 0 < amount < float("inf"):
            raise ValueError("Сумма должна быть положительным конечным числом")

    def to_dict(self) -> dict:
        """Serialize the wallet for JSON storage."""
        return {
            "currency_code": self._currency_code,
            "balance": self._balance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        """Restore a wallet from JSON-compatible data."""
        return cls(
            currency_code=data["currency_code"],
            balance=data["balance"],
        )
