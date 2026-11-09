"""Tests for the ValutaTrade Hub command-line interface."""

import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from valutatrade_hub.cli.interface import ValutaTradeCLI


class TestValutaTradeCLI(unittest.TestCase):
    """Test CLI commands without external APIs or real storage."""

    def setUp(self):
        """Create a CLI with isolated mock services."""
        self.cli = ValutaTradeCLI.__new__(ValutaTradeCLI)

        self.cli._settings = Mock()
        self.cli._settings.rates_ttl_seconds = 3600
        self.cli._database = Mock()
        self.cli._users = Mock()
        self.cli._trading = Mock()
        self.cli._updater = Mock()
        self.cli._current_user = None

        self.user = SimpleNamespace(
            user_id=1,
            username="testuser",
        )

        self.cli._users.register.return_value = self.user
        self.cli._users.login.return_value = self.user

        self.output = StringIO()

    def _execute(self, command):
        """Execute a command and capture printed output."""
        self.output = StringIO()

        with redirect_stdout(self.output):
            result = self.cli.execute(command)

        return result, self.output.getvalue()

    def _login(self):
        """Set an authenticated user for command tests."""
        self.cli._current_user = self.user

    def test_help(self):
        """Display the list of supported commands."""
        result, output = self._execute("help")

        self.assertTrue(result)
        self.assertIn("register", output)
        self.assertIn("login", output)
        self.assertIn("deposit", output)
        self.assertIn("show-portfolio", output)
        self.assertIn("buy", output)
        self.assertIn("sell", output)
        self.assertIn("update-rates", output)

    def test_unknown_command(self):
        """Show an error for unsupported commands."""
        result, output = self._execute("unknown")

        self.assertTrue(result)
        self.assertIn("Неизвестная команда", output)

    def test_empty_command(self):
        """Ignore empty command lines."""
        result, output = self._execute("   ")

        self.assertTrue(result)
        self.assertEqual(output, "")

    def test_exit(self):
        """Stop execution when the exit command is entered."""
        result, _ = self._execute("exit")

        self.assertFalse(result)

    def test_quit(self):
        """Support quit as an alternative exit command."""
        result, _ = self._execute("quit")

        self.assertFalse(result)

    def test_register_success(self):
        """Register a user with matching passwords."""
        with patch(
            "valutatrade_hub.cli.interface.getpass",
            side_effect=["test-password", "test-password"],
        ):
            result, output = self._execute("register testuser")

        self.assertTrue(result)
        self.assertIn("зарегистрирован", output)

        self.cli._users.register.assert_called_once_with(
            "testuser",
            "test-password",
        )

    def test_register_password_mismatch(self):
        """Reject registration when passwords differ."""
        with patch(
            "valutatrade_hub.cli.interface.getpass",
            side_effect=["first-password", "second-password"],
        ):
            _, output = self._execute("register testuser")

        self.assertIn("Пароли не совпадают", output)
        self.cli._users.register.assert_not_called()

    def test_login_success(self):
        """Authenticate the user and start a session."""
        with patch(
            "valutatrade_hub.cli.interface.getpass",
            return_value="test-password",
        ):
            _, output = self._execute("login testuser")

        self.assertIn("Вход выполнен", output)
        self.assertEqual(
            self.cli._current_user.user_id,
            1,
        )

        self.cli._users.login.assert_called_once_with(
            "testuser",
            "test-password",
        )

    def test_login_failure(self):
        """Do not authenticate a user with invalid credentials."""
        self.cli._users.login.side_effect = ValueError(
            "Неверное имя пользователя или пароль"
        )

        with patch(
            "valutatrade_hub.cli.interface.getpass",
            return_value="wrong-password",
        ):
            _, output = self._execute("login testuser")

        self.assertIn("Ошибка", output)
        self.assertIsNone(self.cli._current_user)

    def test_logout(self):
        """Clear the authenticated session."""
        self._login()

        _, output = self._execute("logout")

        self.assertIsNone(self.cli._current_user)
        self.assertIn("вышли", output)

    def test_deposit_requires_login(self):
        """Reject deposits from unauthenticated users."""
        _, output = self._execute("deposit 10000")

        self.assertIn("войдите в систему", output)
        self.cli._trading.deposit_usd.assert_not_called()

    def test_deposit_success(self):
        """Deposit virtual USD into the user's wallet."""
        self._login()

        _, output = self._execute("deposit 10000")

        self.assertIn("10000.00 USD", output)

        self.cli._trading.deposit_usd.assert_called_once_with(
            1,
            10000.0,
        )

    def test_deposit_invalid_amount(self):
        """Reject negative deposit amounts."""
        self._login()

        _, output = self._execute("deposit -100")

        self.assertIn("Ошибка", output)
        self.cli._trading.deposit_usd.assert_not_called()

    def test_deposit_non_numeric_amount(self):
        """Reject deposit amounts that are not numbers."""
        self._login()

        _, output = self._execute("deposit abc")

        self.assertIn("Ошибка", output)
        self.cli._trading.deposit_usd.assert_not_called()

    def test_buy_success(self):
        """Pass a cryptocurrency purchase to TradingService."""
        self._login()

        _, output = self._execute("buy BTC 0.01")

        self.assertIn("Покупка выполнена", output)

        self.cli._trading.buy.assert_called_once_with(
            1,
            "BTC",
            0.01,
        )

    def test_buy_requires_login(self):
        """Reject purchases without authentication."""
        _, output = self._execute("buy BTC 0.01")

        self.assertIn("войдите в систему", output)
        self.cli._trading.buy.assert_not_called()

    def test_buy_insufficient_funds(self):
        """Display a trading error without terminating the CLI."""
        self._login()

        self.cli._trading.buy.side_effect = ValueError("Недостаточно средств")

        result, output = self._execute("buy BTC 100")

        self.assertTrue(result)
        self.assertIn("Недостаточно средств", output)

    def test_sell_success(self):
        """Pass a cryptocurrency sale to TradingService."""
        self._login()

        _, output = self._execute("sell BTC 0.005")

        self.assertIn("Продажа выполнена", output)

        self.cli._trading.sell.assert_called_once_with(
            1,
            "BTC",
            0.005,
        )

    def test_sell_requires_login(self):
        """Reject sales without authentication."""
        _, output = self._execute("sell BTC 0.005")

        self.assertIn("войдите в систему", output)
        self.cli._trading.sell.assert_not_called()

    def test_show_empty_portfolio(self):
        """Display a message for an empty portfolio."""
        self._login()

        portfolio = SimpleNamespace(
            user=self.user,
            wallets={},
        )

        self.cli._trading.get_portfolio.return_value = portfolio

        _, output = self._execute("show-portfolio")

        self.assertIn("Портфель пока пуст", output)

        self.cli._trading.get_portfolio.assert_called_once_with(1)

    def test_show_portfolio_with_usd(self):
        """Display the user's USD balance and total value."""
        self._login()

        wallet = SimpleNamespace(
            balance=10000.0,
        )

        portfolio = SimpleNamespace(
            user=self.user,
            wallets={"USD": wallet},
        )

        self.cli._trading.get_portfolio.return_value = portfolio
        self.cli._trading.get_portfolio_value.return_value = 10000.0

        _, output = self._execute("show-portfolio")

        self.assertIn("testuser", output)
        self.assertIn("10000.00000000", output)
        self.assertIn("10000.00 USD", output)

    def test_show_rates_empty(self):
        """Show a message when no exchange rates are saved."""
        self.cli._database.load_rates.return_value = {
            "pairs": {},
            "last_refresh": None,
        }

        _, output = self._execute("show-rates")

        self.assertIn("Сохранённые курсы отсутствуют", output)

    def test_show_rates_success(self):
        """Display saved exchange rates."""
        self.cli._database.load_rates.return_value = {
            "pairs": {
                "BTC_USD": 50000.0,
                "ETH_USD": 2500.0,
                "EUR_USD": 1.25,
                "RUB_USD": 0.01,
            },
            "last_refresh": "2026-11-09T10:00:00+00:00",
        }

        _, output = self._execute("show-rates")

        self.assertIn("BTC_USD", output)
        self.assertIn("ETH_USD", output)
        self.assertIn("EUR_USD", output)
        self.assertIn("RUB_USD", output)
        self.assertIn("устарел", output)

    def test_get_rate_success(self):
        """Display a saved BTC exchange rate."""
        self.cli._database.load_rates.return_value = {
            "pairs": {"BTC_USD": 50000.0},
            "last_refresh": None,
        }

        self.cli._updater.is_fresh.return_value = False

        _, output = self._execute("get-rate BTC")

        self.assertIn("50000.00000000 USD", output)
        self.assertIn("устарел", output)

    def test_get_rate_missing(self):
        """Handle a missing exchange rate."""
        self.cli._database.load_rates.return_value = {
            "pairs": {},
            "last_refresh": None,
        }

        _, output = self._execute("get-rate BTC")

        self.assertIn("Курс BTC_USD отсутствует", output)

    def test_get_rate_usd(self):
        """Return a fixed USD-to-USD rate."""
        _, output = self._execute("get-rate USD")

        self.assertIn("1 USD = 1 USD", output)

    def test_update_rates_success(self):
        """Call RatesUpdater when update-rates is entered."""
        self.cli._updater.run_update.return_value = {
            "pairs": {
                "BTC_USD": 50000.0,
                "ETH_USD": 2500.0,
                "EUR_USD": 1.25,
                "RUB_USD": 0.01,
            },
            "last_refresh": "2026-11-09T10:00:00+00:00",
        }

        _, output = self._execute("update-rates")

        self.assertIn("Обновление курсов завершено", output)
        self.assertIn("BTC_USD", output)

        self.cli._updater.run_update.assert_called_once_with(source=None)

    def test_update_rates_failure(self):
        """Handle API failures without terminating the CLI."""
        from valutatrade_hub.core.exceptions import ApiRequestError

        self.cli._updater.run_update.side_effect = ApiRequestError("API недоступен")

        result, output = self._execute("update-rates")

        self.assertTrue(result)
        self.assertIn("API недоступен", output)

    def test_invalid_argument_count(self):
        """Reject commands with an incorrect argument count."""
        self._login()

        _, output = self._execute("buy BTC")

        self.assertIn("Неверное количество аргументов", output)
        self.cli._trading.buy.assert_not_called()

    def test_unclosed_quote(self):
        """Handle malformed quoted command arguments."""
        result, output = self._execute('login "unfinished')

        self.assertTrue(result)
        self.assertIn("Ошибка ввода", output)

    @staticmethod
    def _modern_snapshot(age_seconds=20):
        """Return a six-pair cache in the current MEPhI JSON format."""
        timestamp = (datetime.now(UTC) - timedelta(seconds=age_seconds)).isoformat()
        rates = {
            "BTC_USD": (50000.0, "CoinGecko"),
            "ETH_USD": (2500.0, "CoinGecko"),
            "SOL_USD": (150.0, "CoinGecko"),
            "EUR_USD": (1.25, "ExchangeRate-API"),
            "GBP_USD": (1.40, "ExchangeRate-API"),
            "RUB_USD": (0.01, "ExchangeRate-API"),
        }
        return {
            "pairs": {
                pair: {
                    "rate": rate,
                    "updated_at": timestamp,
                    "source": source,
                }
                for pair, (rate, source) in rates.items()
            },
            "last_refresh": timestamp,
        }

    def test_register_named_username(self):
        """Accept registration through the required --username flag."""
        with patch(
            "valutatrade_hub.cli.interface.getpass",
            side_effect=["test-password", "test-password"],
        ):
            _, output = self._execute("register --username testuser")
        self.assertIn("зарегистрирован", output)
        self.cli._users.register.assert_called_once_with("testuser", "test-password")

    def test_register_named_password(self):
        """Allow explicit credentials without prompting for them."""
        with patch("valutatrade_hub.cli.interface.getpass") as prompt:
            _, output = self._execute(
                "register --username testuser --password test-password"
            )
        self.assertIn("зарегистрирован", output)
        self.cli._users.register.assert_called_once_with("testuser", "test-password")
        prompt.assert_not_called()

    def test_login_named_username(self):
        """Authenticate with the --username option."""
        with patch(
            "valutatrade_hub.cli.interface.getpass",
            return_value="test-password",
        ):
            _, output = self._execute("login --username testuser")
        self.assertIn("Вход выполнен", output)
        self.cli._users.login.assert_called_once_with("testuser", "test-password")

    def test_buy_named_arguments(self):
        """Buy with --currency and --amount in either order."""
        self._login()
        _, output = self._execute("buy --amount 0.01 --currency BTC")
        self.assertIn("Покупка выполнена", output)
        self.cli._trading.buy.assert_called_once_with(1, "BTC", 0.01)

    def test_sell_named_arguments(self):
        """Sell with the required named options."""
        self._login()
        _, output = self._execute("sell --currency ETH --amount 0.2")
        self.assertIn("Продажа выполнена", output)
        self.cli._trading.sell.assert_called_once_with(1, "ETH", 0.2)

    def test_get_rate_named_pair(self):
        """Read a named BTC/USD rate from nested cache entries."""
        self.cli._database.load_rates.return_value = self._modern_snapshot()
        _, output = self._execute("get-rate --from BTC --to USD")
        self.assertIn("1 BTC = 50000.00000000 USD", output)
        self.assertIn("CoinGecko", output)
        self.assertNotIn("устарел", output)

    def test_get_rate_cross_currency(self):
        """Compute EUR/GBP using the cached USD base rates."""
        self.cli._database.load_rates.return_value = self._modern_snapshot()
        _, output = self._execute("get-rate --from EUR --to GBP")
        self.assertIn("1 EUR = 0.89285714 GBP", output)
        self.assertIn("ExchangeRate-API", output)

    def test_get_rate_reverse_usd(self):
        """Invert the USD value when USD is the source currency."""
        self.cli._database.load_rates.return_value = self._modern_snapshot()
        _, output = self._execute("get-rate --from USD --to EUR")
        self.assertIn("1 USD = 0.80000000 EUR", output)

    def test_get_rate_individual_ttl(self):
        """Warn when a pair is stale despite fresh last_refresh."""
        snapshot = self._modern_snapshot()
        snapshot["pairs"]["BTC_USD"]["updated_at"] = (
            datetime.now(UTC) - timedelta(hours=2)
        ).isoformat()
        self.cli._database.load_rates.return_value = snapshot
        _, output = self._execute("get-rate --from BTC --to USD")
        self.assertIn("BTC_USD устарел", output)

    def test_show_rates_named_filters(self):
        """Filter by currency and limit the number of displayed rows."""
        self.cli._database.load_rates.return_value = self._modern_snapshot()
        _, output = self._execute("show-rates --currency BTC --top 1 --base USD")
        self.assertIn("BTC_USD", output)
        self.assertNotIn("ETH_USD", output)
        self.assertIn("CoinGecko", output)

    def test_show_rates_cross_base(self):
        """Convert the displayed price into a requested base currency."""
        self.cli._database.load_rates.return_value = self._modern_snapshot()
        _, output = self._execute("show-rates --currency BTC --base EUR")
        self.assertIn("BTC_EUR", output)
        self.assertIn("40000.00000000", output)

    def test_show_rates_top_limit(self):
        """Limit displayed rows to the highest rates."""
        self.cli._database.load_rates.return_value = self._modern_snapshot()
        _, output = self._execute("show-rates --top 2")
        self.assertIn("BTC_USD", output)
        self.assertIn("ETH_USD", output)
        self.assertNotIn("SOL_USD", output)

    def test_show_rates_invalid_top(self):
        """Reject invalid --top values instead of crashing."""
        self.cli._database.load_rates.return_value = self._modern_snapshot()
        for value in ("0", "-1", "abc"):
            with self.subTest(value=value):
                _, output = self._execute(f"show-rates --top {value}")
                self.assertIn("Ошибка", output)

    def test_show_portfolio_with_base_eur(self):
        """Convert total portfolio value into EUR."""
        self._login()
        self.cli._trading.get_portfolio.return_value = SimpleNamespace(
            user=self.user,
            wallets={"USD": SimpleNamespace(balance=100.0)},
        )
        self.cli._trading.get_portfolio_value.return_value = 100.0
        self.cli._database.load_rates.return_value = self._modern_snapshot()
        _, output = self._execute("show-portfolio --base EUR")
        self.assertIn("Общая стоимость: 80.00 EUR", output)

    def test_update_rates_source(self):
        """Pass the chosen API source to the main updater method."""
        self.cli._updater.run_update.return_value = self._modern_snapshot()
        _, output = self._execute("update-rates --source coingecko")
        self.assertIn("Обновление курсов завершено", output)
        self.cli._updater.run_update.assert_called_once_with(source="coingecko")
        self.cli._updater.update_rates.assert_not_called()

    def test_update_rates_reject_unknown_source(self):
        """Reject unknown providers before calling the updater."""
        _, output = self._execute("update-rates --source unknown")
        self.assertIn("Ошибка", output)
        self.cli._updater.run_update.assert_not_called()

    def test_duplicate_flag_rejected(self):
        """Reject duplicated options to avoid ambiguous trades."""
        self._login()
        _, output = self._execute("buy --currency BTC --amount 1 --amount 2")
        self.assertIn("повторно", output)
        self.cli._trading.buy.assert_not_called()

    def test_missing_flag_value_rejected(self):
        """Reject omitted option values without executing a trade."""
        self._login()
        _, output = self._execute("buy --currency BTC --amount")
        self.assertIn("Не указано значение", output)
        self.cli._trading.buy.assert_not_called()

    def test_missing_required_flag_rejected(self):
        """Reject an incomplete named trade command."""
        self._login()
        _, output = self._execute("buy --currency BTC")
        self.assertIn("Отсутствуют обязательные параметры", output)
        self.cli._trading.buy.assert_not_called()

    def test_get_rate_attempts_refresh_for_stale_pair(self):
        """A stale pair triggers an API update and a fresh cache read."""
        stale = self._modern_snapshot(age_seconds=8000)
        fresh = self._modern_snapshot()
        self.cli._database.load_rates.side_effect = [stale, fresh]
        _, output = self._execute("get-rate --from BTC --to USD")
        self.cli._updater.run_update.assert_called_once_with(source=None)
        self.assertIn("Пробуем обновить", output)
        self.assertIn("50000.00000000 USD", output)
        self.assertNotIn("BTC_USD устарел", output)

    def test_get_rate_attempts_refresh_for_missing_pair(self):
        """A missing pair can be populated by a successful API refresh."""
        empty = {"pairs": {}, "last_refresh": None}
        self.cli._database.load_rates.side_effect = [empty, self._modern_snapshot()]
        _, output = self._execute("get-rate --from SOL --to USD")
        self.cli._updater.run_update.assert_called_once_with(source=None)
        self.assertIn("1 SOL = 150.00000000 USD", output)

    def test_get_rate_api_failure_warns_and_shows_stale(self):
        """An API outage cannot make a stale quote appear current."""
        from valutatrade_hub.core.exceptions import ApiRequestError

        self.cli._database.load_rates.return_value = self._modern_snapshot(8000)
        self.cli._updater.run_update.side_effect = ApiRequestError("Сеть недоступна")
        _, output = self._execute("get-rate --from BTC --to USD")
        self.assertIn("Обновление не удалось", output)
        self.assertIn("BTC_USD устарел", output)

    def test_top_only_crypto_even_if_fiat_has_higher_rate(self):
        """Top N must filter fiat rates before sorting cryptocurrencies."""
        snapshot = self._modern_snapshot()
        snapshot["pairs"]["GBP_USD"]["rate"] = 100000.0
        self.cli._database.load_rates.return_value = snapshot
        _, output = self._execute("show-rates --top 2")
        self.assertIn("BTC_USD", output)
        self.assertIn("ETH_USD", output)
        self.assertNotIn("GBP_USD", output)

    def test_portfolio_displays_value_per_wallet(self):
        """The portfolio table contains estimates for individual wallets."""
        self._login()
        self.cli._trading.get_portfolio.return_value = SimpleNamespace(
            user=self.user,
            wallets={
                "USD": SimpleNamespace(balance=100.0),
                "BTC": SimpleNamespace(balance=0.01),
            },
        )
        self.cli._trading.get_portfolio_value.return_value = 600.0
        self.cli._database.load_rates.return_value = self._modern_snapshot()
        _, output = self._execute("show-portfolio")
        self.assertIn("Стоимость (USD)", output)
        self.assertIn("500.00", output)
        self.assertIn("600.00 USD", output)

    def test_successful_buy_displays_execution_details(self):
        """A committed trade displays rate, cost and remaining balances."""
        self._login()
        self.cli._database.load_rates.return_value = self._modern_snapshot()
        self.cli._trading.buy.return_value = SimpleNamespace(
            wallets={
                "BTC": SimpleNamespace(balance=0.01),
                "USD": SimpleNamespace(balance=500.0),
            }
        )
        _, output = self._execute("buy --currency BTC --amount 0.01")
        self.assertIn("Курс исполнения", output)
        self.assertIn("500.00 USD", output)
        self.assertIn("Остаток USD", output)

    def test_unknown_flag_rejected(self):
        """Show an error for unsupported option names."""
        self._login()
        _, output = self._execute("buy --currency BTC --amount 1 --unknown value")
        self.assertIn("Неизвестный параметр", output)
        self.cli._trading.buy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
