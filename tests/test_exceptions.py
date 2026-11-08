"""Tests for custom application exceptions."""

import unittest

from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    ValutaTradeError,
)


class TestExceptions(unittest.TestCase):
    """Test custom exception hierarchy."""

    def test_base_exception(self):
        error = ValutaTradeError("Ошибка приложения")
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "Ошибка приложения")

    def test_insufficient_funds(self):
        with self.assertRaises(InsufficientFundsError):
            raise InsufficientFundsError("Недостаточно средств")

    def test_currency_not_found(self):
        with self.assertRaises(CurrencyNotFoundError):
            raise CurrencyNotFoundError("Валюта не найдена")

    def test_api_request_error(self):
        with self.assertRaises(ApiRequestError):
            raise ApiRequestError("Ошибка API")

    def test_inheritance(self):
        for error_class in (
            InsufficientFundsError,
            CurrencyNotFoundError,
            ApiRequestError,
        ):
            self.assertTrue(issubclass(error_class, ValutaTradeError))

    def test_value_error_compatibility(self):
        self.assertTrue(issubclass(InsufficientFundsError, ValueError))
        self.assertTrue(issubclass(CurrencyNotFoundError, ValueError))


if __name__ == "__main__":
    unittest.main()
