"""HTTP clients for external currency exchange-rate APIs."""

import math
import os
from abc import ABC, abstractmethod
from typing import ClassVar

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.settings import SettingsLoader


def validate_rate(value: object, currency_code: str) -> float:
    """Validate a positive, finite exchange rate."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ApiRequestError(f"Некорректный курс валюты {currency_code}: {value!r}")

    return float(value)


class BaseApiClient(ABC):
    """Abstract base class for currency API clients."""

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

    def _request_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        """Perform an HTTP request and validate its JSON response."""
        try:
            response = self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()

        except requests.RequestException as exc:
            raise ApiRequestError(
                f"Ошибка получения курсов: {type(exc).__name__}"
            ) from exc

        except ValueError as exc:
            raise ApiRequestError("API вернул некорректный JSON") from exc

        if not isinstance(data, dict):
            raise ApiRequestError("Ответ API должен быть JSON-объектом")

        return data

    @abstractmethod
    def get_rates(self) -> dict[str, float]:
        """Return currency prices in USD."""


class CoinGeckoClient(BaseApiClient):
    """Fetch BTC and ETH prices from CoinGecko."""

    COIN_IDS: ClassVar[dict[str, str]] = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
    }

    def __init__(
        self,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        super().__init__(
            timeout=timeout,
            session=session,
        )
        self._settings = SettingsLoader()

    def get_rates(self) -> dict[str, float]:
        """Return BTC_USD and ETH_USD exchange rates."""
        url = f"{self._settings.coingecko_base_url}/simple/price"

        headers = {}
        api_key = os.getenv("COINGECKO_API_KEY")

        if api_key:
            headers["x-cg-demo-api-key"] = api_key

        data = self._request_json(
            url,
            params={
                "ids": ",".join(self.COIN_IDS.values()),
                "vs_currencies": "usd",
            },
            headers=headers or None,
        )

        rates = {}

        for code, coin_id in self.COIN_IDS.items():
            coin_data = data.get(coin_id)

            if not isinstance(coin_data, dict):
                raise ApiRequestError(f"В ответе CoinGecko отсутствует {coin_id}")

            rates[f"{code}_USD"] = validate_rate(
                coin_data.get("usd"),
                code,
            )

        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Fetch fiat exchange rates from ExchangeRate-API."""

    FIAT_CODES: ClassVar[tuple[str, ...]] = (
        "EUR",
        "RUB",
    )

    def __init__(
        self,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        super().__init__(
            timeout=timeout,
            session=session,
        )
        self._settings = SettingsLoader()

    def get_rates(self) -> dict[str, float]:
        """Return USD prices for one unit of EUR and RUB."""
        api_key = self._settings.exchange_rate_api_key

        if not api_key:
            raise ApiRequestError("Не задан EXCHANGE_RATE_API_KEY")

        url = f"{self._settings.exchange_rate_base_url}/{api_key}/latest/USD"

        data = self._request_json(url)

        if data.get("result") != "success":
            raise ApiRequestError("ExchangeRate-API не подтвердил успешный запрос")

        if data.get("base_code") != "USD":
            raise ApiRequestError("Некорректная базовая валюта ExchangeRate-API")

        conversion_rates = data.get("conversion_rates")

        if not isinstance(conversion_rates, dict):
            raise ApiRequestError("В ответе отсутствует словарь conversion_rates")

        rates = {}

        for code in self.FIAT_CODES:
            units_per_usd = validate_rate(
                conversion_rates.get(code),
                code,
            )

            # The API returns currency units per one USD.
            # TradingService needs USD per one currency unit.
            usd_per_unit = 1.0 / units_per_usd

            rates[f"{code}_USD"] = validate_rate(
                usd_per_unit,
                code,
            )

        return rates
