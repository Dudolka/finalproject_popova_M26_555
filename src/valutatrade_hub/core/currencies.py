"""Currency models and factory for ValutaTrade Hub."""

from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError


class Currency(ABC):
    """Abstract base class for currencies."""

    def __init__(self, code: str, name: str) -> None:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Код валюты не может быть пустым")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")

        self._code = code.strip().upper()
        self._name = name.strip()

    @property
    def code(self) -> str:
        return self._code

    @property
    def name(self) -> str:
        return self._name

    @property
    @abstractmethod
    def currency_type(self) -> str:
        """Return the currency category."""

    @abstractmethod
    def get_display_info(self) -> str:
        """Return a human-readable currency description."""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "type": self.currency_type,
        }


class FiatCurrency(Currency):
    """Represent a government-issued currency."""

    @property
    def currency_type(self) -> str:
        return "fiat"

    def get_display_info(self) -> str:
        return f"{self.code} — {self.name} (фиатная валюта)"


class CryptoCurrency(Currency):
    """Represent a cryptocurrency."""

    @property
    def currency_type(self) -> str:
        return "crypto"

    def get_display_info(self) -> str:
        return f"{self.code} — {self.name} (криптовалюта)"


SUPPORTED_CURRENCIES = {
    "USD": ("US Dollar", FiatCurrency),
    "EUR": ("Euro", FiatCurrency),
    "RUB": ("Russian Ruble", FiatCurrency),
    "BTC": ("Bitcoin", CryptoCurrency),
    "ETH": ("Ethereum", CryptoCurrency),
}


def create_currency(code: str) -> Currency:
    """Create a supported currency using the factory pattern."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Код валюты не может быть пустым")

    normalized_code = code.strip().upper()

    if normalized_code not in SUPPORTED_CURRENCIES:
        raise CurrencyNotFoundError(f"Неподдерживаемая валюта: {normalized_code}")

    name, currency_class = SUPPORTED_CURRENCIES[normalized_code]
    return currency_class(normalized_code, name)
