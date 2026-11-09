"""Interactive command-line interface for ValutaTrade Hub."""

import math
import shlex
from datetime import UTC, datetime
from getpass import getpass
from typing import Any

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import CryptoCurrency, create_currency
from valutatrade_hub.core.exceptions import CurrencyNotFoundError, ValutaTradeError
from valutatrade_hub.core.usecases import TradingService, UserService
from valutatrade_hub.core.utils import cross_rate
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.updater import RatesUpdater


class ValutaTradeCLI:
    """Interactive interface for simulated currency trading."""

    def __init__(self) -> None:
        """Initialize services and an empty user session."""
        self._settings = SettingsLoader()
        self._database = DatabaseManager(self._settings.data_dir)
        self._users = UserService(self._database)
        self._trading = TradingService(self._database, self._settings)
        self._updater = RatesUpdater(database=self._database, settings=self._settings)
        self._current_user = None

    @staticmethod
    def _parse_amount(value: str) -> float:
        """Parse a strictly positive finite amount."""
        try:
            amount = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Сумма должна быть числом") from exc
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Сумма должна быть положительным конечным числом")
        return amount

    @staticmethod
    def _check_arguments(arguments: list[str], expected: int, usage: str) -> None:
        """Require a fixed number of positional arguments."""
        if len(arguments) != expected:
            raise ValueError(f"Неверное количество аргументов.\nИспользование: {usage}")

    @staticmethod
    def _options(
        arguments: list[str],
        *,
        allowed: frozenset[str],
        required: frozenset[str] = frozenset(),
    ) -> dict[str, str]:
        """Parse unique --name value options without exiting the CLI."""
        result = {}
        index = 0
        while index < len(arguments):
            name = arguments[index]
            if name not in allowed:
                raise ValueError(f"Неизвестный параметр: {name}")
            if name in result:
                raise ValueError(f"Параметр {name} указан повторно")
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
                raise ValueError(f"Не указано значение параметра {name}")
            result[name] = arguments[index + 1]
            index += 2
        missing = required.difference(result)
        if missing:
            raise ValueError(
                f"Отсутствуют обязательные параметры: {', '.join(sorted(missing))}"
            )
        return result

    @staticmethod
    def _code(value: str) -> str:
        """Validate an ASCII currency code for market-data queries."""
        if not isinstance(value, str):
            raise TypeError("Код валюты должен быть строкой")
        code = value.strip().upper()
        if not 2 <= len(code) <= 5 or not code.isascii() or not code.isalpha():
            raise ValueError(f"Некорректный код валюты: {value!r}")
        return create_currency(code).code

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        """Parse a timezone-aware ISO timestamp."""
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(UTC)

    def _rate_is_fresh(self, timestamp: object) -> bool:
        """Check TTL for a specific observation."""
        parsed = self._timestamp(timestamp)
        if parsed is None:
            return False
        age = (datetime.now(UTC) - parsed).total_seconds()
        return 0 <= age < self._settings.rates_ttl_seconds

    def _snapshot(self) -> dict[str, Any]:
        """Read and validate the outer cache structure."""
        snapshot = self._database.load_rates()
        if not isinstance(snapshot, dict) or not isinstance(
            snapshot.get("pairs"), dict
        ):
            raise TypeError("Некорректный файл курсов. Выполните update-rates.")
        return snapshot

    def _observation(
        self, snapshot: dict[str, Any], from_code: str
    ) -> tuple[float, str | None, str]:
        """Return USD price, timestamp and source for one currency."""
        if from_code == "USD":
            return 1.0, None, "USD"
        pair = f"{from_code}_USD"
        raw = snapshot["pairs"].get(pair)
        if raw is None:
            raise CurrencyNotFoundError(
                f"Курс {pair} отсутствует. Выполните update-rates."
            )
        if isinstance(raw, dict):
            rate = raw.get("rate")
            timestamp = raw.get("updated_at")
            source = raw.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError(f"Отсутствует источник курса {pair}")
        else:
            rate = raw
            timestamp = snapshot.get("last_refresh")
            source = "LegacyCache"
        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        ):
            raise ValueError(f"Некорректный курс {pair}. Выполните update-rates.")
        return float(rate), timestamp, source

    def _require_login(self) -> int:
        """Return the authenticated user's identifier."""
        if self._current_user is None:
            raise ValueError("Для выполнения команды войдите в систему")
        return self._current_user.user_id

    @staticmethod
    def show_help() -> None:
        """Display the supported commands and flags."""
        table = PrettyTable()
        table.field_names = ["Команда", "Назначение"]
        table.align = "l"
        commands = (
            ("register --username NAME [--password PASSWORD]", "Регистрация"),
            ("login --username NAME [--password PASSWORD]", "Авторизация"),
            ("logout", "Выход из учётной записи"),
            ("deposit AMOUNT", "Пополнение виртуального USD"),
            ("show-portfolio [--base USD]", "Просмотр портфеля"),
            ("buy --currency BTC --amount 0.01", "Покупка валюты"),
            ("sell --currency BTC --amount 0.01", "Продажа валюты"),
            ("get-rate --from BTC --to USD", "Курс валютной пары"),
            ("show-rates [--currency BTC] [--top 5] [--base USD]", "Кэш курсов"),
            ("update-rates [--source coingecko|exchangerate]", "Обновление API"),
            ("help / exit", "Справка / завершение"),
        )
        for command, description in commands:
            table.add_row([command, description])
        print(table)
        print("Допускаются и прежние позиционные команды, например: buy BTC 0.01")
        print("Для паролей рекомендуется интерактивный ввод, без --password.")
        print("Все сделки учебные. Реальные деньги не используются.")

    def register(self, arguments: list[str]) -> None:
        """Register a user using named options or legacy syntax."""
        if arguments and not arguments[0].startswith("--"):
            self._check_arguments(arguments, 1, "register USERNAME")
            username, password = arguments[0], None
        else:
            options = self._options(
                arguments,
                allowed=frozenset({"--username", "--password"}),
                required=frozenset({"--username"}),
            )
            username, password = options["--username"], options.get("--password")
        if password is None:
            password = getpass("Введите пароль: ")
            if password != getpass("Повторите пароль: "):
                raise ValueError("Пароли не совпадают")
        user = self._users.register(username, password)
        print(f"Пользователь {user.username} зарегистрирован. ID: {user.user_id}")
        print("Для входа выполните команду login.")

    def login(self, arguments: list[str]) -> None:
        """Authenticate a user without exposing the entered password."""
        if arguments and not arguments[0].startswith("--"):
            self._check_arguments(arguments, 1, "login USERNAME")
            username, password = arguments[0], None
        else:
            options = self._options(
                arguments,
                allowed=frozenset({"--username", "--password"}),
                required=frozenset({"--username"}),
            )
            username, password = options["--username"], options.get("--password")
        if password is None:
            password = getpass("Введите пароль: ")
        user = self._users.login(username, password)
        self._current_user = user
        print(f"Вход выполнен. Пользователь: {user.username}")

    def logout(self, arguments: list[str]) -> None:
        """Finish the current user session."""
        self._check_arguments(arguments, 0, "logout")
        self._current_user = None
        print("Вы вышли из учётной записи.")

    def deposit(self, arguments: list[str]) -> None:
        """Deposit virtual US dollars into the active portfolio."""
        user_id = self._require_login()
        self._check_arguments(arguments, 1, "deposit AMOUNT")
        amount = self._parse_amount(arguments[0])
        self._trading.deposit_usd(user_id, amount)
        print(f"Виртуальный баланс пополнен на {amount:.2f} USD.")

    def show_portfolio(self, arguments: list[str]) -> None:
        """Display each holding and its estimated value in the chosen base."""
        user_id = self._require_login()
        options = self._options(arguments, allowed=frozenset({"--base"}))
        base = self._code(options.get("--base", "USD"))
        portfolio = self._trading.get_portfolio(user_id)
        print(f"\nПортфель пользователя: {portfolio.user.username}")
        if not portfolio.wallets:
            print("Портфель пока пуст.")
            return

        snapshot = None
        base_rate = 1.0
        valuation_error = None
        needs_rates = base != "USD" or any(
            code != "USD" and wallet.balance > 0
            for code, wallet in portfolio.wallets.items()
        )
        if needs_rates:
            try:
                snapshot = self._snapshot()
                base_rate, _, _ = self._observation(snapshot, base)
            except (ValutaTradeError, ValueError, OSError, TypeError) as exc:
                valuation_error = str(exc)

        table = PrettyTable()
        table.field_names = ["Валюта", "Баланс", f"Стоимость ({base})"]
        table.align = "l"
        for code, wallet in sorted(portfolio.wallets.items()):
            valuation = "н/д"
            if valuation_error is None:
                try:
                    usd_rate = (
                        1.0
                        if code == "USD" or wallet.balance == 0
                        else self._observation(snapshot, code)[0]
                    )
                    value = wallet.balance * cross_rate(usd_rate, base_rate)
                    if not math.isfinite(value):
                        raise ValueError("Результат оценки не является конечным числом")
                    valuation = f"{value:.2f}"
                except (ValutaTradeError, ValueError, OSError, TypeError):
                    pass
            table.add_row([code, f"{wallet.balance:.8f}", valuation])
        print(table)
        try:
            if valuation_error is not None:
                raise ValueError(valuation_error)
            value_usd = self._trading.get_portfolio_value(user_id)
            total = value_usd / base_rate
            if not math.isfinite(total):
                raise ValueError("Результат пересчёта не является конечным числом")
        except (ValutaTradeError, ValueError, OSError, TypeError) as exc:
            print(f"Общая стоимость недоступна: {exc}")
        else:
            print(f"Общая стоимость: {total:.2f} {base}")

    def _print_trade_result(
        self, action: str, code: str, amount: float, portfolio: object
    ) -> None:
        """Explain the execution price, settlement and current balances."""
        print(f"{action} выполнена: {amount:.8f} {code}.")
        # A successful trade always uses a fresh USD rate in TradingService.
        # The portfolio is returned by that service after persistence.
        wallets = getattr(portfolio, "wallets", None)
        if not isinstance(wallets, dict):
            return
        try:
            rate, _, _ = self._observation(self._snapshot(), code)
            cost = amount * rate
            if not math.isfinite(cost):
                raise ValueError("Некорректная стоимость сделки")
            print(f"Курс исполнения (по кэшу): 1 {code} = {rate:.8f} USD")
            print(f"Расчётная сумма: {cost:.2f} USD")
        except (ValutaTradeError, ValueError, OSError, TypeError):
            print("Курс сделки недоступен для отображения.")
        for currency in (code, "USD"):
            if currency in wallets:
                print(f"Остаток {currency}: {wallets[currency].balance:.8f}")

    def _trade_arguments(self, arguments: list[str], command: str) -> tuple[str, float]:
        """Parse the currency and amount for a simulated trade."""
        if arguments and not arguments[0].startswith("--"):
            self._check_arguments(arguments, 2, f"{command} CODE AMOUNT")
            code, amount = arguments
        else:
            options = self._options(
                arguments,
                allowed=frozenset({"--currency", "--amount"}),
                required=frozenset({"--currency", "--amount"}),
            )
            code, amount = options["--currency"], options["--amount"]
        return create_currency(code).code, self._parse_amount(amount)

    def buy(self, arguments: list[str]) -> None:
        """Buy a currency using virtual US dollars."""
        user_id = self._require_login()
        code, amount = self._trade_arguments(arguments, "buy")
        portfolio = self._trading.buy(user_id, code, amount)
        self._print_trade_result("Покупка", code, amount, portfolio)

    def sell(self, arguments: list[str]) -> None:
        """Sell a currency for virtual US dollars."""
        user_id = self._require_login()
        code, amount = self._trade_arguments(arguments, "sell")
        portfolio = self._trading.sell(user_id, code, amount)
        self._print_trade_result("Продажа", code, amount, portfolio)

    def get_rate(self, arguments: list[str]) -> None:
        """Display a cross-rate, refreshing missing or expired observations."""
        if arguments and not arguments[0].startswith("--"):
            self._check_arguments(arguments, 1, "get-rate CODE")
            from_code, to_code = self._code(arguments[0]), "USD"
        else:
            options = self._options(
                arguments,
                allowed=frozenset({"--from", "--to"}),
                required=frozenset({"--from", "--to"}),
            )
            from_code = self._code(options["--from"])
            to_code = self._code(options["--to"])
        if from_code == to_code:
            print(f"1 {from_code} = 1 {to_code}")
            return

        snapshot = self._snapshot()
        needed = {from_code, to_code} - {"USD"}
        must_refresh = False
        for code in needed:
            try:
                _, timestamp, _ = self._observation(snapshot, code)
            except CurrencyNotFoundError:
                must_refresh = True
            else:
                if not self._rate_is_fresh(timestamp):
                    must_refresh = True

        if must_refresh:
            print("Кэш отсутствует или устарел. Пробуем обновить курсы через API...")
            try:
                self._updater.run_update(source=None)
                snapshot = self._snapshot()
            except (ValutaTradeError, ValueError, OSError, TypeError) as exc:
                print(f"Обновление не удалось: {exc}")
                print(
                    "При наличии сохранённых значений они будут помечены устаревшими."
                )

        from_rate, from_time, from_source = self._observation(snapshot, from_code)
        to_rate, to_time, to_source = self._observation(snapshot, to_code)
        result = cross_rate(from_rate, to_rate)
        print(f"1 {from_code} = {result:.8f} {to_code}")
        for code, timestamp, source in (
            (from_code, from_time, from_source),
            (to_code, to_time, to_source),
        ):
            if code != "USD":
                print(
                    f"Источник {code}_USD: {source}; обновлено: {timestamp or 'неизвестно'}"
                )
                if not self._rate_is_fresh(timestamp):
                    print(f"Внимание: курс {code}_USD устарел. Выполните update-rates.")

    def show_rates(self, arguments: list[str]) -> None:
        """Display saved rates, optionally filtered and converted."""
        options = self._options(
            arguments,
            allowed=frozenset({"--currency", "--top", "--base"}),
        )
        filter_code = (
            self._code(options["--currency"]) if "--currency" in options else None
        )
        base = self._code(options.get("--base", "USD"))
        top = None
        if "--top" in options:
            try:
                top = int(options["--top"])
            except ValueError as exc:
                raise ValueError(
                    "--top должен быть целым положительным числом"
                ) from exc
            if top <= 0:
                raise ValueError("--top должен быть целым положительным числом")
        snapshot = self._snapshot()
        pairs = snapshot["pairs"]
        if not pairs:
            print("Сохранённые курсы отсутствуют. Выполните update-rates.")
            return
        base_rate, _, _ = self._observation(snapshot, base)
        rows = []
        for pair in sorted(pairs):
            if not isinstance(pair, str) or pair.count("_") != 1:
                raise ValueError(f"Некорректная валютная пара: {pair!r}")
            from_code, quote_code = pair.split("_", 1)
            if quote_code != "USD":
                continue
            if filter_code is not None and from_code != filter_code:
                continue
            if top is not None and not isinstance(
                create_currency(from_code), CryptoCurrency
            ):
                continue
            rate, updated_at, source = self._observation(snapshot, from_code)
            converted = cross_rate(rate, base_rate)
            rows.append((f"{from_code}_{base}", converted, updated_at, source))
        if filter_code == base and not rows:
            rows.append((f"{base}_{base}", 1.0, None, "Расчётный"))
        rows.sort(key=lambda item: item[1], reverse=True)
        if top is not None:
            rows = rows[:top]
        if not rows:
            print("По заданным фильтрам курсы не найдены.")
            return
        table = PrettyTable()
        table.field_names = [
            "Валютная пара",
            "Курс",
            "Обновлено (UTC)",
            "Источник",
            "Статус",
        ]
        table.align = "l"
        for pair, value, updated_at, source in rows:
            status = (
                "актуален"
                if updated_at is None or self._rate_is_fresh(updated_at)
                else "устарел"
            )
            table.add_row([pair, f"{value:.8f}", updated_at or "—", source, status])
        print(table)
        print(
            f"Последнее обновление кэша (UTC): {snapshot.get('last_refresh') or 'нет данных'}"
        )
        if base != "USD":
            print(f"Пересчёт выполнен через сохранённый курс {base}_USD.")

    def update_rates(self, arguments: list[str]) -> None:
        """Refresh rates from all or one configured external source."""
        options = self._options(arguments, allowed=frozenset({"--source"}))
        source = options.get("--source")
        if source is not None and source.lower() not in RatesUpdater.SOURCES:
            raise ValueError("Источник должен быть coingecko или exchangerate")
        snapshot = self._updater.run_update(source=source.lower() if source else None)
        print("Обновление курсов завершено.")
        print(f"Всего сохранённых пар: {len(snapshot['pairs'])}")
        for pair, data in sorted(snapshot["pairs"].items()):
            rate = data["rate"] if isinstance(data, dict) else data
            print(f"{pair}: {rate:.8f}")
        print(f"Время обновления (UTC): {snapshot['last_refresh']}")

    def execute(self, command_line: str) -> bool:
        """Execute one interactive command; return False to quit."""
        try:
            parts = shlex.split(command_line)
        except ValueError as exc:
            print(f"Ошибка ввода: {exc}")
            return True
        if not parts:
            return True
        command, arguments = parts[0].lower(), parts[1:]
        try:
            match command:
                case "help":
                    self._check_arguments(arguments, 0, "help")
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
                    self._check_arguments(arguments, 0, "exit")
                    return False
                case _:
                    print(f"Неизвестная команда: {command}. Введите help.")
        except (ValutaTradeError, ValueError, TypeError, OSError) as exc:
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
                if not self.execute(command_line):
                    print("Работа ValutaTrade Hub завершена.")
                    break
            except (EOFError, KeyboardInterrupt):
                print("\nРабота ValutaTrade Hub завершена.")
                break


def main() -> None:
    """Start the CLI with configured logging."""
    setup_logging()
    ValutaTradeCLI().run()


if __name__ == "__main__":
    main()
