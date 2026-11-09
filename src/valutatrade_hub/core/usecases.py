"""Application use cases for ValutaTrade Hub."""

import logging
import math
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import create_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
)
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

logger = logging.getLogger("valutatrade_hub.trading")


def _get_database(
    database: DatabaseManager | None,
) -> DatabaseManager:
    """Return an injected database or the configured database."""
    if database is not None:
        return database

    settings = SettingsLoader()
    return DatabaseManager(settings.data_dir)


def _safe_username(username: str) -> str:
    """Remove log-control characters from a username."""
    return "".join(
        " " if character in "\r\n\t" else character for character in username
    )[:100]


def _log_trade_details(
    *,
    action: str,
    portfolio: Portfolio,
    currency_code: str,
    amount: float,
    rate: float,
    total_usd: float,
) -> None:
    """Log details of a successfully persisted transaction."""
    logger.info(
        "TRADE DETAILS | action=%s | status=COMMITTED "
        "| user_id=%s | username=%s | currency=%s "
        "| amount=%.8f | rate_usd=%.8f | total_usd=%.8f",
        action,
        portfolio.user.user_id,
        _safe_username(portfolio.user.username),
        currency_code,
        amount,
        rate,
        total_usd,
    )


class UserService:
    """Handle user registration and authentication."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
    ) -> None:
        """Initialize the user service."""
        self._database = _get_database(database)

    def register(
        self,
        username: str,
        password: str,
    ) -> User:
        """Register and persist a new user."""
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

    def login(
        self,
        username: str,
        password: str,
    ) -> User:
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


class TradingService:
    """Manage simulated currency trading and portfolios."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
        settings: SettingsLoader | None = None,
    ) -> None:
        """Initialize trading dependencies."""
        self._database = _get_database(database)
        self._settings = settings if settings is not None else SettingsLoader()
        self._users = UserService(self._database)

    def get_portfolio(
        self,
        user_id: int,
    ) -> Portfolio:
        """Load a user's portfolio or create one in memory."""
        user = self._users.get_user(user_id)

        for portfolio_data in self._database.load_portfolios():
            if portfolio_data["user_id"] == user_id:
                return Portfolio.from_dict(
                    portfolio_data,
                    user,
                )

        return Portfolio(user)

    def _save_portfolio(
        self,
        portfolio: Portfolio,
    ) -> None:
        """Save a portfolio without changing other users' data."""
        portfolios = self._database.load_portfolios()
        serialized = portfolio.to_dict()

        for index, existing in enumerate(portfolios):
            if existing["user_id"] == portfolio.user.user_id:
                portfolios[index] = serialized
                break
        else:
            portfolios.append(serialized)

        self._database.save_portfolios(portfolios)

    def _check_rate_freshness(
        self,
        rates_data: dict,
        rate_entry: dict | None = None,
    ) -> None:
        """Reject an expired or invalid individual exchange rate.

        The current format uses the pair's updated_at timestamp.
        The previous numeric format uses snapshot last_refresh.
        """
        if rate_entry is None:
            timestamp_value = rates_data.get("last_refresh")
        else:
            timestamp_value = rate_entry.get("updated_at")

        if not isinstance(timestamp_value, str):
            raise ApiRequestError(
                "Время обновления курса отсутствует. Выполните update-rates."
            )

        try:
            timestamp = datetime.fromisoformat(timestamp_value)
        except ValueError as exc:
            raise ApiRequestError(
                "Некорректное время обновления курса. Выполните update-rates."
            ) from exc

        if timestamp.tzinfo is None:
            raise ApiRequestError(
                "Время обновления курса не содержит "
                "часовой пояс. Выполните update-rates."
            )

        age_seconds = (datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds()

        if (
            not math.isfinite(age_seconds)
            or age_seconds < 0
            or age_seconds >= self._settings.rates_ttl_seconds
        ):
            raise ApiRequestError(
                "Курс валюты устарел или имеет некорректное "
                "время обновления. Выполните update-rates."
            )

    def _get_rate(
        self,
        currency_code: str,
        *,
        require_fresh: bool = True,
    ) -> float:
        """Return the USD value of one currency unit."""
        code = currency_code.strip().upper()

        if code == "USD":
            return 1.0

        rates_data = self._database.load_rates()

        if not isinstance(rates_data, dict):
            raise ApiRequestError("Некорректный формат кэша валютных курсов")

        pairs = rates_data.get("pairs", {})

        if not isinstance(pairs, dict):
            raise ApiRequestError("Поле pairs в кэше курсов должно быть словарём")

        pair = f"{code}_USD"

        if pair not in pairs:
            raise CurrencyNotFoundError(
                f"Курс {pair} отсутствует. Обновите курсы валют."
            )

        entry = pairs[pair]

        if isinstance(entry, dict):
            # Required format from the MEPhI assignment.
            rate = entry.get("rate")
            updated_at = entry.get("updated_at")
            source = entry.get("source")

            if not isinstance(updated_at, str):
                raise ApiRequestError(
                    f"Для {pair} отсутствует updated_at. Выполните update-rates."
                )

            if not isinstance(source, str) or not source.strip():
                raise ApiRequestError(f"Для {pair} отсутствует источник курса")

            rate_entry = entry
        else:
            # Transitional compatibility with numeric cache entries.
            rate = entry
            rate_entry = None

        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        ):
            raise ApiRequestError(f"Некорректное значение курса {pair}")

        if require_fresh:
            self._check_rate_freshness(
                rates_data,
                rate_entry,
            )

        return float(rate)

    def deposit_usd(
        self,
        user_id: int,
        amount: float,
    ) -> Portfolio:
        """Add virtual USD funds to a user's portfolio."""
        Wallet._validate_amount(amount)

        portfolio = self.get_portfolio(user_id)
        portfolio.add_currency("USD").deposit(amount)

        self._save_portfolio(portfolio)
        return portfolio

    @log_action
    def buy(
        self,
        user_id: int,
        currency_code: str,
        amount: float,
    ) -> Portfolio:
        """Buy currency using a fresh exchange rate."""
        Wallet._validate_amount(amount)

        currency = create_currency(currency_code)
        code = currency.code

        if code == "USD":
            raise ValueError("Покупка USD за USD не поддерживается")

        rate = self._get_rate(
            code,
            require_fresh=True,
        )

        cost_usd = amount * rate
        Wallet._validate_amount(cost_usd)

        portfolio = self.get_portfolio(user_id)
        usd_wallet = portfolio.add_currency("USD")

        # Validate and modify balances in memory.
        usd_wallet.withdraw(cost_usd)
        portfolio.add_currency(code).deposit(amount)

        # Persist the trade before recording COMMITTED.
        self._save_portfolio(portfolio)

        _log_trade_details(
            action="buy",
            portfolio=portfolio,
            currency_code=code,
            amount=amount,
            rate=rate,
            total_usd=cost_usd,
        )

        return portfolio

    @log_action
    def sell(
        self,
        user_id: int,
        currency_code: str,
        amount: float,
    ) -> Portfolio:
        """Sell currency using a fresh exchange rate."""
        Wallet._validate_amount(amount)

        currency = create_currency(currency_code)
        code = currency.code

        if code == "USD":
            raise ValueError("Продажа USD за USD не поддерживается")

        rate = self._get_rate(
            code,
            require_fresh=True,
        )

        proceeds_usd = amount * rate
        Wallet._validate_amount(proceeds_usd)

        portfolio = self.get_portfolio(user_id)
        currency_wallet = portfolio.get_wallet(code)
        usd_wallet = portfolio.add_currency("USD")

        if not math.isfinite(usd_wallet.balance + proceeds_usd):
            raise ValueError("Баланс USD превышает допустимое значение")

        # Validate and modify balances in memory.
        currency_wallet.withdraw(amount)
        usd_wallet.deposit(proceeds_usd)

        # Persist the trade before recording COMMITTED.
        self._save_portfolio(portfolio)

        _log_trade_details(
            action="sell",
            portfolio=portfolio,
            currency_code=code,
            amount=amount,
            rate=rate,
            total_usd=proceeds_usd,
        )

        return portfolio

    def get_portfolio_value(
        self,
        user_id: int,
    ) -> float:
        """Calculate portfolio value using cached exchange rates.

        Valuation may use stale rates, while trading always
        requires fresh observations.
        """
        portfolio = self.get_portfolio(user_id)
        rates = {}

        for code, wallet in portfolio.wallets.items():
            if code != "USD" and wallet.balance > 0:
                rates[code] = self._get_rate(
                    code,
                    require_fresh=False,
                )

        return portfolio.get_total_value(rates)
