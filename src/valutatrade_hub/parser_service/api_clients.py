"""HTTP clients for external currency exchange-rate APIs."""

import math
import os
from abc import ABC, abstractmethod
from typing import ClassVar

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.config import ParserConfig


def validate_rate(value: object, currency_code: str) -> float:
    """Validate a positive and finite exchange rate."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ApiRequestError(f"Некорректный курс валюты {currency_code}: {value!r}")

    return float(value)


class BaseApiClient(ABC):
    """Abstract interface for external exchange-rate providers."""

    def __init__(
        self,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Тайм-аут должен быть положительным числом")

        self._timeout = float(timeout)
        self._session = session if session is not None else requests.Session()

    @staticmethod
    def _http_error_message(
        status_code: int | None,
    ) -> str:
        """Translate HTTP status codes into safe application messages."""
        if status_code == 401:
            return "Ошибка API: неверный ключ доступа (HTTP 401)"

        if status_code == 403:
            return "Ошибка API: доступ запрещён (HTTP 403)"

        if status_code == 429:
            return "Ошибка API: превышен лимит запросов (HTTP 429)"

        if isinstance(status_code, int):
            return f"Ошибка HTTP при получении курсов: {status_code}"

        return "Ошибка HTTP при получении курсов"

    def _request_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        """Perform a GET request and validate the JSON response."""
        response = None

        try:
            response = self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()

        except requests.Timeout as exc:
            raise ApiRequestError("Превышено время ожидания ответа API") from exc

        except requests.HTTPError as exc:
            error_response = getattr(exc, "response", None)

            if error_response is None:
                error_response = response

            status_code = getattr(
                error_response,
                "status_code",
                None,
            )

            if not isinstance(status_code, int):
                status_code = None

            raise ApiRequestError(self._http_error_message(status_code)) from exc

        except requests.RequestException as exc:
            raise ApiRequestError(
                "Сетевая ошибка при получении валютных курсов"
            ) from exc

        except ValueError as exc:
            raise ApiRequestError("API вернул некорректный JSON") from exc

        if not isinstance(data, dict):
            raise ApiRequestError("Ответ API должен быть JSON-объектом")

        return data

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Fetch exchange rates in the standard PAIR: rate format."""

    def get_rates(self) -> dict[str, float]:
        """Keep compatibility with existing application code."""
        return self.fetch_rates()


class CoinGeckoClient(BaseApiClient):
    """Fetch cryptocurrency prices from CoinGecko."""

    COIN_IDS: ClassVar[dict[str, str]] = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
    }

    def __init__(
        self,
        timeout: float | None = None,
        session: requests.Session | None = None,
        config: ParserConfig | None = None,
    ) -> None:
        self._config = config
        self._settings = SettingsLoader()

        effective_timeout = (
            timeout
            if timeout is not None
            else (config.request_timeout if config is not None else 10.0)
        )

        super().__init__(
            timeout=effective_timeout,
            session=session,
        )

    def fetch_rates(self) -> dict[str, float]:
        """Fetch configured cryptocurrency prices against USD."""
        if self._config is None:
            coin_ids = self.COIN_IDS
            base_currency = "USD"
            url = f"{self._settings.coingecko_base_url}/simple/price"
            api_key = os.getenv("COINGECKO_API_KEY")
        else:
            coin_ids = {
                code: self._config.crypto_id_map[code]
                for code in self._config.crypto_currencies
            }
            base_currency = self._config.base_currency
            url = self._config.coingecko_url
            api_key = self._config.coingecko_api_key

        headers = {}

        if api_key:
            headers["x-cg-demo-api-key"] = api_key

        data = self._request_json(
            url,
            params={
                "ids": ",".join(coin_ids.values()),
                "vs_currencies": base_currency.lower(),
            },
            headers=headers or None,
        )

        rates = {}

        for code, coin_id in coin_ids.items():
            coin_data = data.get(coin_id)

            if not isinstance(coin_data, dict):
                raise ApiRequestError(f"В ответе CoinGecko отсутствует {coin_id}")

            rate = validate_rate(
                coin_data.get(base_currency.lower()),
                code,
            )

            rates[f"{code}_{base_currency}"] = rate

        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Fetch fiat exchange rates from ExchangeRate-API."""

    FIAT_CODES: ClassVar[tuple[str, ...]] = (
        "EUR",
        "RUB",
    )

    def __init__(
        self,
        timeout: float | None = None,
        session: requests.Session | None = None,
        config: ParserConfig | None = None,
    ) -> None:
        self._config = config
        self._settings = SettingsLoader()

        effective_timeout = (
            timeout
            if timeout is not None
            else (config.request_timeout if config is not None else 10.0)
        )

        super().__init__(
            timeout=effective_timeout,
            session=session,
        )

    def fetch_rates(self) -> dict[str, float]:
        """Fetch fiat rates expressed in USD per currency unit."""
        if self._config is None:
            fiat_codes = self.FIAT_CODES
            base_currency = "USD"
            base_url = self._settings.exchange_rate_base_url
            api_key = self._settings.exchange_rate_api_key
        else:
            fiat_codes = self._config.fiat_currencies
            base_currency = self._config.base_currency
            base_url = self._config.exchangerate_api_url.rstrip("/")
            api_key = self._config.exchangerate_api_key

        if not api_key:
            raise ApiRequestError("Не задан EXCHANGE_RATE_API_KEY")

        url = f"{base_url}/{api_key}/latest/{base_currency}"

        data = self._request_json(url)

        if data.get("result") != "success":
            raise ApiRequestError("ExchangeRate-API не подтвердил успешный запрос")

        if data.get("base_code") != base_currency:
            raise ApiRequestError("Некорректная базовая валюта ExchangeRate-API")

        conversion_rates = data.get("conversion_rates")

        if not isinstance(conversion_rates, dict):
            raise ApiRequestError("В ответе отсутствует словарь conversion_rates")

        rates = {}

        for code in fiat_codes:
            units_per_usd = validate_rate(
                conversion_rates.get(code),
                code,
            )

            # ExchangeRate-API returns currency units per USD.
            # TradingService requires USD per currency unit.
            usd_per_unit = 1.0 / units_per_usd

            rates[f"{code}_{base_currency}"] = validate_rate(usd_per_unit, code)

        return rates
