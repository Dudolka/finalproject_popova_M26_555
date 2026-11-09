"""Centralized configuration for the Parser Service."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ParserConfig:
    """Configuration for currency API clients and local storage.

    API credentials are read from environment variables.
    They must never be hardcoded or committed to Git.
    """

    coingecko_url: str = "https://api.coingecko.com/api/v3/simple/price"
    exchangerate_api_url: str = "https://v6.exchangerate-api.com/v6"

    base_currency: str = "USD"

    fiat_currencies: tuple[str, ...] = (
        "EUR",
        "GBP",
        "RUB",
    )

    crypto_currencies: tuple[str, ...] = (
        "BTC",
        "ETH",
        "SOL",
    )

    crypto_id_map: dict[str, str] = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )

    request_timeout: float = 10.0

    rates_file_path: Path = Path("data/rates.json")
    history_file_path: Path = Path("data/exchange_rates.json")

    exchangerate_api_key: str | None = field(
        default_factory=lambda: (
            os.getenv("EXCHANGE_RATE_API_KEY") or os.getenv("EXCHANGERATE_API_KEY")
        ),
        repr=False,
    )

    coingecko_api_key: str | None = field(
        default_factory=lambda: os.getenv("COINGECKO_API_KEY"),
        repr=False,
    )

    def __post_init__(self) -> None:
        """Validate configuration consistency."""
        if not isinstance(self.base_currency, str):
            raise TypeError("Базовая валюта должна быть строкой")

        if self.base_currency != "USD":
            raise ValueError(
                "Текущая реализация поддерживает USD как базовую валюту API"
            )

        if (
            isinstance(self.request_timeout, bool)
            or not isinstance(
                self.request_timeout,
                (int, float),
            )
            or not 0 < self.request_timeout < float("inf")
        ):
            raise ValueError("Тайм-аут должен быть положительным конечным числом")

        if not self.coingecko_url.startswith("https://"):
            raise ValueError("CoinGecko URL должен использовать HTTPS")

        if not self.exchangerate_api_url.startswith("https://"):
            raise ValueError("ExchangeRate-API URL должен использовать HTTPS")

        for code in (
            *self.fiat_currencies,
            *self.crypto_currencies,
        ):
            if (
                not isinstance(code, str)
                or not 2 <= len(code) <= 5
                or not code.isascii()
                or not code.isalnum()
                or code != code.upper()
            ):
                raise ValueError(f"Некорректный код валюты: {code!r}")

        if len(set(self.fiat_currencies)) != len(self.fiat_currencies):
            raise ValueError("Список фиатных валют содержит дубликаты")

        if len(set(self.crypto_currencies)) != len(self.crypto_currencies):
            raise ValueError("Список криптовалют содержит дубликаты")

        if set(self.fiat_currencies) & set(self.crypto_currencies):
            raise ValueError("Фиатные и криптовалютные коды не должны пересекаться")

        if set(self.crypto_id_map) != set(self.crypto_currencies):
            raise ValueError("Для каждой криптовалюты должен быть задан CoinGecko ID")

        if any(
            not isinstance(coin_id, str) or not coin_id.strip()
            for coin_id in self.crypto_id_map.values()
        ):
            raise ValueError("CoinGecko ID должен быть непустой строкой")

        object.__setattr__(
            self,
            "rates_file_path",
            Path(self.rates_file_path),
        )
        object.__setattr__(
            self,
            "history_file_path",
            Path(self.history_file_path),
        )

    @property
    def tracked_currencies(self) -> tuple[str, ...]:
        """Return all configured currency codes."""
        return (
            *self.fiat_currencies,
            *self.crypto_currencies,
        )

    @property
    def required_pairs(self) -> frozenset[str]:
        """Return configured pairs against USD."""
        return frozenset(
            f"{code}_{self.base_currency}" for code in self.tracked_currencies
        )
