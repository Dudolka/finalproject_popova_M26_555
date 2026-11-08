"""Custom exceptions for ValutaTrade Hub."""


class ValutaTradeError(Exception):
    """Base exception for application-specific errors."""


class InsufficientFundsError(ValutaTradeError, ValueError):
    """Raised when a wallet has insufficient funds."""


class CurrencyNotFoundError(ValutaTradeError, ValueError):
    """Raised when a requested currency or wallet is unavailable."""


class ApiRequestError(ValutaTradeError):
    """Raised when an external currency API request fails."""
