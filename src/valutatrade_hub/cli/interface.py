"""Interactive command-line interface for ValutaTrade Hub."""

import math
import shlex
from getpass import getpass

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import create_currency
from valutatrade_hub.core.exceptions import (
    CurrencyNotFoundError,
    ValutaTradeError,
)
from valutatrade_hub.core.usecases import TradingService, UserService
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.updater import RatesUpdater


class ValutaTradeCLI:
    """Interactive interface for simulated currency trading."""

    def __init__(self) -> None:
        """Initialize application services and user session."""
        self._settings = SettingsLoader()
        self._database = DatabaseManager(self._settings.data_dir)

        self._users = UserService(self._database)
        self._trading = TradingService(self._database)
        self._updater = RatesUpdater(
            database=self._database,
            settings=self._settings,
        )

        self._current_user = None

    @staticmethod
    def _parse_amount(value: str) -> float:
        """Convert input to a positive finite number."""
        try:
            amount = float(value)
        except ValueError as exc:
            raise ValueError("Сумма должна быть числом") from exc

        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Сумма должна быть положительным конечным числом")

        return amount

    @staticmethod
    def _check_arguments(
        arguments: list[str],
        expected: int,
        usage: str,
    ) -> None:
        """Validate the number of command arguments."""
        if len(arguments) != expected:
            raise ValueError(f"Неверное количество аргументов.\nИспользование: {usage}")

    def _require_login(self) -> int:
        """Return authenticated user ID."""
        if self._current_user is None:
            raise ValueError("Для выполнения команды войдите в систему")

        return self._current_user.user_id

    @staticmethod
    def show_help() -> None:
        """Display available CLI commands."""
        table = PrettyTable()
        table.field_names = ["Команда", "Назначение"]
        table.align = "l"

        commands = [
            ("register USERNAME", "Регистрация"),
            ("login USERNAME", "Авторизация"),
            ("logout", "Выход из учётной записи"),
            ("deposit AMOUNT", "Пополнение виртуального USD"),
            ("show-portfolio", "Просмотр портфеля"),
            ("buy CODE AMOUNT", "Покупка валюты"),
            ("sell CODE AMOUNT", "Продажа валюты"),
            ("get-rate CODE", "Просмотр курса валюты"),
            ("show-rates", "Просмотр всех сохранённых курсов"),
            ("update-rates", "Принудительное обновление курсов"),
            ("help", "Список команд"),
            ("exit", "Завершение программы"),
        ]

        for command, description in commands:
            table.add_row([command, description])

        print(table)
        print("\nПоддерживаемые валюты: USD, EUR, RUB, BTC, ETH.")
        print("Все сделки учебные. Реальные деньги не используются.")
        print("Для update-rates требуется доступ к API и соответствующие ключи.")

    def register(self, arguments: list[str]) -> None:
        """Register a new user."""
        self._check_arguments(
            arguments,
            1,
            "register USERNAME",
        )

        username = arguments[0]

        password = getpass("Введите пароль: ")
        confirmation = getpass("Повторите пароль: ")

        if password != confirmation:
            raise ValueError("Пароли не совпадают")

        user = self._users.register(username, password)

        print(f"Пользователь {user.username} зарегистрирован. ID: {user.user_id}")
        print("Для входа выполните команду login.")

    def login(self, arguments: list[str]) -> None:
        """Authenticate a user."""
        self._check_arguments(
            arguments,
            1,
            "login USERNAME",
        )

        username = arguments[0]
        password = getpass("Введите пароль: ")

        user = self._users.login(username, password)
        self._current_user = user

        print(f"Вход выполнен. Пользователь: {user.username}")

    def logout(self, arguments: list[str]) -> None:
        """End the current user session."""
        self._check_arguments(
            arguments,
            0,
            "logout",
        )

        self._current_user = None
        print("Вы вышли из учётной записи.")

    def deposit(self, arguments: list[str]) -> None:
        """Add virtual USD funds."""
        user_id = self._require_login()

        self._check_arguments(
            arguments,
            1,
            "deposit AMOUNT",
        )

        amount = self._parse_amount(arguments[0])

        self._trading.deposit_usd(user_id, amount)

        print(f"Виртуальный баланс пополнен на {amount:.2f} USD.")

    def show_portfolio(self, arguments: list[str]) -> None:
        """Display the authenticated user's portfolio."""
        user_id = self._require_login()

        self._check_arguments(
            arguments,
            0,
            "show-portfolio",
        )

        portfolio = self._trading.get_portfolio(user_id)
        wallets = portfolio.wallets

        print(f"\nПортфель пользователя: {portfolio.user.username}")

        if not wallets:
            print("Портфель пока пуст.")
            return

        table = PrettyTable()
        table.field_names = ["Валюта", "Баланс"]
        table.align = "l"

        for code, wallet in sorted(wallets.items()):
            table.add_row([code, f"{wallet.balance:.8f}"])

        print(table)

        try:
            value = self._trading.get_portfolio_value(user_id)
        except (ValueError, CurrencyNotFoundError):
            print("Общая стоимость недоступна: отсутствуют необходимые курсы.")
        else:
            print(f"Общая стоимость: {value:.2f} USD")

    def buy(self, arguments: list[str]) -> None:
        """Buy a currency with virtual USD."""
        user_id = self._require_login()

        self._check_arguments(
            arguments,
            2,
            "buy CODE AMOUNT",
        )

        code = create_currency(arguments[0]).code
        amount = self._parse_amount(arguments[1])

        self._trading.buy(user_id, code, amount)

        print(f"Покупка выполнена: {amount:.8f} {code}.")

    def sell(self, arguments: list[str]) -> None:
        """Sell a currency for virtual USD."""
        user_id = self._require_login()

        self._check_arguments(
            arguments,
            2,
            "sell CODE AMOUNT",
        )

        code = create_currency(arguments[0]).code
        amount = self._parse_amount(arguments[1])

        self._trading.sell(user_id, code, amount)

        print(f"Продажа выполнена: {amount:.8f} {code}.")

    def get_rate(self, arguments: list[str]) -> None:
        """Display a saved currency rate against USD."""
        self._check_arguments(
            arguments,
            1,
            "get-rate CODE",
        )

        code = create_currency(arguments[0]).code

        if code == "USD":
            print("1 USD = 1 USD")
            return

        snapshot = self._database.load_rates()
        pairs = snapshot.get("pairs", {})
        rate = pairs.get(f"{code}_USD")

        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        ):
            raise CurrencyNotFoundError(
                f"Курс {code}_USD отсутствует или некорректен. Выполните update-rates."
            )

        print(f"1 {code} = {rate:.8f} USD")

        if not self._updater.is_fresh(snapshot):
            print("Внимание: сохранённые курсы устарели. Выполните update-rates.")

    def show_rates(self, arguments: list[str]) -> None:
        """Display saved exchange rates."""
        self._check_arguments(
            arguments,
            0,
            "show-rates",
        )

        snapshot = self._database.load_rates()
        pairs = snapshot.get("pairs", {})

        if not pairs:
            print("Сохранённые курсы отсутствуют. Выполните update-rates.")
            return

        table = PrettyTable()
        table.field_names = ["Валютная пара", "Курс"]
        table.align = "l"

        for pair, rate in sorted(pairs.items()):
            table.add_row([pair, rate])

        print(table)

        refreshed = snapshot.get("last_refresh")

        print(f"Последнее обновление (UTC): {refreshed or 'нет данных'}")

        if self._updater.is_fresh(snapshot):
            print("Статус: курсы актуальны по TTL.")
        else:
            print("Статус: курсы устарели или неполные.")

    def update_rates(self, arguments: list[str]) -> None:
        """Force an exchange-rate refresh."""
        self._check_arguments(
            arguments,
            0,
            "update-rates",
        )

        snapshot = self._updater.update_rates(force=True)

        print("Курсы успешно обновлены.")

        for pair, rate in sorted(snapshot["pairs"].items()):
            print(f"{pair}: {rate:.8f}")

        print(f"Время обновления (UTC): {snapshot['last_refresh']}")

    def execute(self, command_line: str) -> bool:
        """Execute one command; return False to exit."""
        try:
            parts = shlex.split(command_line)
        except ValueError as exc:
            print(f"Ошибка ввода: {exc}")
            return True

        if not parts:
            return True

        command = parts[0].lower()
        arguments = parts[1:]

        try:
            match command:
                case "help":
                    self._check_arguments(
                        arguments,
                        0,
                        "help",
                    )
                    self.show_help()

                case "register":
                    self.register(arguments)

                case "login":
                    self.login(arguments)

                case "logout":
                    self.logout(arguments)

                case "deposit":
                    self.deposit(arguments)

                case "show-portfolio":
                    self.show_portfolio(arguments)

                case "buy":
                    self.buy(arguments)

                case "sell":
                    self.sell(arguments)

                case "get-rate":
                    self.get_rate(arguments)

                case "show-rates":
                    self.show_rates(arguments)

                case "update-rates":
                    self.update_rates(arguments)

                case "exit" | "quit":
                    self._check_arguments(
                        arguments,
                        0,
                        "exit",
                    )
                    return False

                case _:
                    print(f"Неизвестная команда: {command}. Введите help.")

        except (
            ValutaTradeError,
            ValueError,
            TypeError,
            OSError,
        ) as exc:
            print(f"Ошибка: {exc}")

        return True

    def run(self) -> None:
        """Start the interactive command loop."""
        print("\nValutaTrade Hub")
        print("Учебная платформа торговли валютами.")
        print("Введите help для просмотра команд.\n")

        while True:
            try:
                command_line = input("valutatrade> ")
                should_continue = self.execute(command_line)

                if not should_continue:
                    print("Работа ValutaTrade Hub завершена.")
                    break

            except (EOFError, KeyboardInterrupt):
                print("\nРабота ValutaTrade Hub завершена.")
                break


def main() -> None:
    """Start the command-line application with logging."""
    setup_logging()

    application = ValutaTradeCLI()
    application.run()


if __name__ == "__main__":
    main()
