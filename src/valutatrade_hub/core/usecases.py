"""Application use cases for ValutaTrade Hub."""

from datetime import UTC, datetime

from valutatrade_hub.core.currencies import create_currency
from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader


def _get_database(database: DatabaseManager | None) -> DatabaseManager:
    """Return the injected database or the default database."""
    if database is not None:
        return database

    settings = SettingsLoader()
    return DatabaseManager(settings.data_dir)


class UserService:
    """Handle user registration and authentication."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
    ) -> None:
        self._database = _get_database(database)

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


class TradingService:
    """Manage simulated currency trading and portfolios."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
    ) -> None:
        self._database = _get_database(database)
        self._users = UserService(self._database)

    def get_portfolio(self, user_id: int) -> Portfolio:
        """Load a user's portfolio or create an empty one in memory."""
        user = self._users.get_user(user_id)

        for portfolio_data in self._database.load_portfolios():
            if portfolio_data["user_id"] == user_id:
                return Portfolio.from_dict(portfolio_data, user)

        return Portfolio(user)

    def _save_portfolio(self, portfolio: Portfolio) -> None:
        """Save one portfolio while preserving other users' data."""
        portfolios = self._database.load_portfolios()
        serialized = portfolio.to_dict()

        for index, existing in enumerate(portfolios):
            if existing["user_id"] == portfolio.user.user_id:
                portfolios[index] = serialized
                break
        else:
            portfolios.append(serialized)

        self._database.save_portfolios(portfolios)

    def _get_rate(self, currency_code: str) -> float:
        """Return the USD price of one currency unit."""
        code = currency_code.strip().upper()

        if code == "USD":
            return 1.0

        rates_data = self._database.load_rates()
        pairs = rates_data.get("pairs", {})
        pair = f"{code}_USD"

        if pair not in pairs:
            raise CurrencyNotFoundError(
                f"Курс {pair} отсутствует. Обновите курсы валют."
            )

        rate = pairs[pair]
        Wallet._validate_amount(rate)
        return float(rate)

    def deposit_usd(self, user_id: int, amount: float) -> Portfolio:
        """Add virtual USD funds to a user's portfolio."""
        Wallet._validate_amount(amount)

        portfolio = self.get_portfolio(user_id)
        portfolio.add_currency("USD").deposit(amount)

        self._save_portfolio(portfolio)
        return portfolio

    def buy(
        self,
        user_id: int,
        currency_code: str,
        amount: float,
    ) -> Portfolio:
        """Buy currency using the user's virtual USD balance."""
        Wallet._validate_amount(amount)

        currency = create_currency(currency_code)
        code = currency.code

        if code == "USD":
            raise ValueError("Покупка USD за USD не поддерживается")

        rate = self._get_rate(code)
        cost_usd = amount * rate

        Wallet._validate_amount(cost_usd)

        portfolio = self.get_portfolio(user_id)
        usd_wallet = portfolio.add_currency("USD")

        # Check available funds before changing the portfolio.
        if cost_usd > usd_wallet.balance:
            usd_wallet.withdraw(cost_usd)

        # Work with a separate in-memory portfolio copy.
        usd_wallet.withdraw(cost_usd)
        portfolio.add_currency(code).deposit(amount)

        self._save_portfolio(portfolio)
        return portfolio

    def sell(
        self,
        user_id: int,
        currency_code: str,
        amount: float,
    ) -> Portfolio:
        """Sell currency and receive its value in virtual USD."""
        Wallet._validate_amount(amount)

        currency = create_currency(currency_code)
        code = currency.code

        if code == "USD":
            raise ValueError("Продажа USD за USD не поддерживается")

        rate = self._get_rate(code)
        proceeds_usd = amount * rate

        Wallet._validate_amount(proceeds_usd)

        portfolio = self.get_portfolio(user_id)
        currency_wallet = portfolio.get_wallet(code)

        # Validate the amount before changing balances.
        if amount > currency_wallet.balance:
            currency_wallet.withdraw(amount)

        usd_wallet = portfolio.add_currency("USD")

        # Check that the USD balance can accept the proceeds.
        if not usd_wallet.balance + proceeds_usd < float("inf"):
            raise ValueError("Баланс USD превышает допустимое значение")

        currency_wallet.withdraw(amount)
        usd_wallet.deposit(proceeds_usd)

        self._save_portfolio(portfolio)
        return portfolio

    def get_portfolio_value(self, user_id: int) -> float:
        """Calculate the user's portfolio value in USD."""
        portfolio = self.get_portfolio(user_id)

        rates = {}
        for code, wallet in portfolio.wallets.items():
            if code != "USD" and wallet.balance > 0:
                rates[code] = self._get_rate(code)

        return portfolio.get_total_value(rates)
