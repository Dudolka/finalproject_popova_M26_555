"""Domain models for ValutaTrade Hub."""

import hashlib
import hmac
import math
import secrets
from datetime import datetime

from valutatrade_hub.core.exceptions import (
    CurrencyNotFoundError,
    InsufficientFundsError,
)


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
        """Return the unique user identifier."""
        return self._user_id

    @property
    def username(self) -> str:
        """Return the username."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        """Update the username after validation."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")

        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Return the stored password hash."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Return the user-specific password salt."""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Return the registration date."""
        return self._registration_date

    def change_password(self, new_password: str) -> None:
        """Replace the password hash using a fresh random salt."""
        if not isinstance(new_password, str) or len(new_password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")

        self._salt = secrets.token_hex(16)
        self._hashed_password = hashlib.sha256(
            (new_password + self._salt).encode("utf-8")
        ).hexdigest()

    def verify_password(self, password: str) -> bool:
        """Verify a password using constant-time hash comparison."""
        if not isinstance(password, str):
            return False

        candidate = hashlib.sha256((password + self._salt).encode("utf-8")).hexdigest()

        return hmac.compare_digest(
            candidate,
            self._hashed_password,
        )

    def get_user_info(self) -> dict:
        """Return public user information without password data."""
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
        """Restore a user from serialized data."""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(data["registration_date"]),
        )


class Wallet:
    """Represent a currency wallet with a validated non-negative balance."""

    def __init__(
        self,
        currency_code: str,
        balance: float = 0.0,
    ) -> None:
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")

        self._currency_code = currency_code.strip().upper()
        self._balance = 0.0

        self.balance = balance

    @property
    def currency_code(self) -> str:
        """Return the currency code."""
        return self._currency_code

    @property
    def balance(self) -> float:
        """Return the current balance."""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        """Set the balance after validating its type and value."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")

        if not math.isfinite(value):
            raise ValueError("Баланс должен быть конечным числом")

        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")

        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """Add a positive amount to the wallet."""
        self._validate_amount(amount)

        new_balance = self._balance + amount

        if not math.isfinite(new_balance):
            raise ValueError("Баланс после пополнения превышает допустимое значение")

        self.balance = new_balance

    def withdraw(self, amount: float) -> None:
        """Withdraw funds or raise InsufficientFundsError."""
        self._validate_amount(amount)

        if amount > self._balance:
            raise InsufficientFundsError(
                f"Недостаточно средств: доступно "
                f"{self._balance:.4f} {self._currency_code}, "
                f"требуется {amount:.4f} {self._currency_code}"
            )

        self.balance = self._balance - amount

    def get_balance_info(self) -> str:
        """Return a readable description of the wallet balance."""
        return f"Баланс {self._currency_code}: {self._balance:.4f}"

    @staticmethod
    def _validate_amount(amount: float) -> None:
        """Validate a positive finite amount."""
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError("Сумма операции должна быть числом")

        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Сумма должна быть положительным конечным числом")

    def to_dict(self) -> dict:
        """Serialize the wallet."""
        return {
            "currency_code": self._currency_code,
            "balance": self._balance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        """Restore a wallet from serialized data."""
        return cls(
            currency_code=data["currency_code"],
            balance=data["balance"],
        )


class Portfolio:
    """Manage a user's currency wallets and portfolio valuation."""

    def __init__(self, user: User) -> None:
        if not isinstance(user, User):
            raise TypeError("Владелец портфеля должен быть объектом User")

        self._user = user
        self._wallets: dict[str, Wallet] = {}

    @property
    def user(self) -> User:
        """Return the portfolio owner."""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Return a shallow copy of the wallets mapping."""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> Wallet:
        """Create a wallet if it does not already exist."""
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")

        code = currency_code.strip().upper()

        if code not in self._wallets:
            self._wallets[code] = Wallet(code)

        return self._wallets[code]

    def get_wallet(self, currency_code: str) -> Wallet:
        """Return a wallet or raise CurrencyNotFoundError."""
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")

        code = currency_code.strip().upper()

        if code not in self._wallets:
            raise CurrencyNotFoundError(f"Кошелёк {code} не найден")

        return self._wallets[code]

    def get_total_value(
        self,
        rates: dict[str, float],
        base_currency: str = "USD",
    ) -> float:
        """Calculate portfolio value using USD-based exchange rates.

        Rates map currency codes to USD per one currency unit.
        For a non-USD base, convert the total USD value
        using the supplied rate of the target base currency.

        The original get_total_value(rates) call remains supported.
        """
        if not isinstance(rates, dict):
            raise TypeError("Курсы валют должны быть словарём")

        if not isinstance(base_currency, str) or not base_currency.strip():
            raise ValueError("Базовая валюта не может быть пустой")

        base = base_currency.strip().upper()

        # Calculate the portfolio value in USD first.
        total_usd = 0.0

        for code, wallet in self._wallets.items():
            if wallet.balance == 0:
                continue

            if code == "USD":
                rate = 1.0
            else:
                if code not in rates:
                    raise CurrencyNotFoundError(f"Курс валюты {code} не найден")

                rate = rates[code]
                Wallet._validate_amount(rate)

            total_usd += wallet.balance * rate

            if not math.isfinite(total_usd):
                raise ValueError("Стоимость портфеля превышает допустимое значение")

        if base == "USD":
            return total_usd

        if base not in rates:
            raise CurrencyNotFoundError(f"Неизвестная базовая валюта '{base}'")

        base_rate = rates[base]
        Wallet._validate_amount(base_rate)

        total_in_base = total_usd / base_rate

        if not math.isfinite(total_in_base):
            raise ValueError("Стоимость портфеля превышает допустимое значение")

        return total_in_base

    def to_dict(self) -> dict:
        """Serialize the portfolio."""
        return {
            "user_id": self._user.user_id,
            "wallets": {
                code: wallet.to_dict() for code, wallet in self._wallets.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict, user: User) -> "Portfolio":
        """Restore a portfolio from serialized data."""
        if data["user_id"] != user.user_id:
            raise ValueError("Портфель принадлежит другому пользователю")

        portfolio = cls(user)

        for code, wallet_data in data["wallets"].items():
            wallet = Wallet.from_dict(wallet_data)

            if code != wallet.currency_code:
                raise ValueError("Код валюты не совпадает с данными кошелька")

            portfolio._wallets[code] = wallet

        return portfolio
