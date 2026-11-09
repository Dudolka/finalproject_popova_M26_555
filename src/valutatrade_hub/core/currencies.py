"""Currency models and factory for ValutaTrade Hub."""

import math
import re
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError


class Currency(ABC):
    """Abstract base class for fiat and cryptocurrency models."""

    def __init__(self, code: str, name: str) -> None:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Код валюты не может быть пустым")

        normalized_code = code.strip().upper()

        if not re.fullmatch(r"[A-Z0-9]{2,5}", normalized_code):
            raise ValueError(
                "Код валюты должен содержать от 2 до 5 "
                "латинских букв или цифр без пробелов"
            )

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")

        self._code = normalized_code
        self._name = name.strip()

    @property
    def code(self) -> str:
        """Return the normalized currency code."""
        return self._code

    @property
    def name(self) -> str:
        """Return the currency name."""
        return self._name

    @property
    @abstractmethod
    def currency_type(self) -> str:
        """Return the currency category."""

    @abstractmethod
    def get_display_info(self) -> str:
        """Return a human-readable currency description."""

    def to_dict(self) -> dict:
        """Serialize common currency attributes."""
        return {
            "code": self.code,
            "name": self.name,
            "type": self.currency_type,
        }


class FiatCurrency(Currency):
    """Represent a fiat currency and its issuing country or region."""

    def __init__(
        self,
        code: str,
        name: str,
        issuing_country: str = "Unknown",
    ) -> None:
        super().__init__(code, name)

        if not isinstance(issuing_country, str):
            raise TypeError("Страна эмиссии должна быть строкой")

        if not issuing_country.strip():
            raise ValueError("Страна эмиссии не может быть пустой")

        self._issuing_country = issuing_country.strip()

    @property
    def issuing_country(self) -> str:
        """Return the issuing country or region."""
        return self._issuing_country

    @property
    def currency_type(self) -> str:
        """Return the fiat currency category."""
        return "fiat"

    def get_display_info(self) -> str:
        """Return the fiat currency description."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Represent a cryptocurrency with algorithm and market-cap metadata."""

    def __init__(
        self,
        code: str,
        name: str,
        algorithm: str = "Unknown",
        market_cap: float = 0.0,
    ) -> None:
        super().__init__(code, name)

        if not isinstance(algorithm, str):
            raise TypeError("Алгоритм должен быть строкой")

        if not algorithm.strip():
            raise ValueError("Алгоритм не может быть пустым")

        if isinstance(market_cap, bool) or not isinstance(market_cap, (int, float)):
            raise TypeError("Капитализация должна быть числом")

        normalized_market_cap = float(market_cap)

        if not math.isfinite(normalized_market_cap):
            raise ValueError("Капитализация должна быть конечным числом")

        if normalized_market_cap < 0:
            raise ValueError("Капитализация не может быть отрицательной")

        self._algorithm = algorithm.strip()
        self._market_cap = normalized_market_cap

    @property
    def algorithm(self) -> str:
        """Return the cryptocurrency algorithm description."""
        return self._algorithm

    @property
    def market_cap(self) -> float:
        """Return the latest known market capitalization."""
        return self._market_cap

    @property
    def currency_type(self) -> str:
        """Return the cryptocurrency category."""
        return "crypto"

    def get_display_info(self) -> str:
        """Return the cryptocurrency description."""
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {self.market_cap:.2e})"
        )


SUPPORTED_CURRENCIES = {
    "USD": ("US Dollar", FiatCurrency),
    "EUR": ("Euro", FiatCurrency),
    "RUB": ("Russian Ruble", FiatCurrency),
    "BTC": ("Bitcoin", CryptoCurrency),
    "ETH": ("Ethereum", CryptoCurrency),
}


FIAT_ISSUING_COUNTRIES = {
    "USD": "United States",
    "EUR": "Eurozone",
    "RUB": "Russia",
}


CRYPTO_ALGORITHMS = {
    "BTC": "SHA-256",
    "ETH": "Proof of Stake",
}


def get_currency(code: str) -> Currency:
    """Return a supported currency using the factory pattern."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Код валюты не может быть пустым")

    normalized_code = code.strip().upper()

    if not re.fullmatch(r"[A-Z0-9]{2,5}", normalized_code):
        raise ValueError(
            "Код валюты должен содержать от 2 до 5 латинских букв или цифр без пробелов"
        )

    if normalized_code not in SUPPORTED_CURRENCIES:
        raise CurrencyNotFoundError(f"Неизвестная валюта '{normalized_code}'")

    name, currency_class = SUPPORTED_CURRENCIES[normalized_code]

    if currency_class is FiatCurrency:
        return FiatCurrency(
            code=normalized_code,
            name=name,
            issuing_country=FIAT_ISSUING_COUNTRIES.get(normalized_code, "Unknown"),
        )

    if currency_class is CryptoCurrency:
        return CryptoCurrency(
            code=normalized_code,
            name=name,
            algorithm=CRYPTO_ALGORITHMS.get(normalized_code, "Unknown"),
            market_cap=0.0,
        )

    return currency_class(normalized_code, name)


def create_currency(code: str) -> Currency:
    """Backward-compatible currency factory."""
    return get_currency(code)
