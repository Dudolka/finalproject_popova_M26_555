"""Tests for the ValutaTrade Hub command-line interface."""

import unittest
from contextlib import redirect_stdout
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

        self.cli._updater.is_fresh.return_value = True

        _, output = self._execute("show-rates")

        self.assertIn("BTC_USD", output)
        self.assertIn("ETH_USD", output)
        self.assertIn("EUR_USD", output)
        self.assertIn("RUB_USD", output)
        self.assertIn("актуальны", output)

    def test_get_rate_success(self):
        """Display a saved BTC exchange rate."""
        self.cli._database.load_rates.return_value = {
            "pairs": {"BTC_USD": 50000.0},
            "last_refresh": None,
        }

        self.cli._updater.is_fresh.return_value = False

        _, output = self._execute("get-rate BTC")

        self.assertIn("50000.00000000 USD", output)
        self.assertIn("устарели", output)

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
        self.cli._updater.update_rates.return_value = {
            "pairs": {
                "BTC_USD": 50000.0,
                "ETH_USD": 2500.0,
                "EUR_USD": 1.25,
                "RUB_USD": 0.01,
            },
            "last_refresh": "2026-11-09T10:00:00+00:00",
        }

        _, output = self._execute("update-rates")

        self.assertIn("Курсы успешно обновлены", output)
        self.assertIn("BTC_USD", output)

        self.cli._updater.update_rates.assert_called_once_with(force=True)

    def test_update_rates_failure(self):
        """Handle API failures without terminating the CLI."""
        from valutatrade_hub.core.exceptions import ApiRequestError

        self.cli._updater.update_rates.side_effect = ApiRequestError("API недоступен")

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


if __name__ == "__main__":
    unittest.main()
