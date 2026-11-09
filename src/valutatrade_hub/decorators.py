"""Safe logging decorators for ValutaTrade Hub."""

import inspect
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, overload

logger = logging.getLogger("valutatrade_hub.decorators")

SAFE_FIELDS = (
    "username",
    "user_id",
    "currency",
    "currency_code",
    "code",
    "amount",
    "rate",
    "base_currency",
)

MAX_FIELD_LENGTH = 100


def _safe_value(value: Any) -> str | None:
    """Return a bounded, log-safe representation of a scalar value."""
    if isinstance(value, bool):
        return None

    if not isinstance(value, (str, int, float)):
        return None

    result = str(value)
    result = result.replace("\r", " ").replace("\n", " ")

    return result[:MAX_FIELD_LENGTH]


def _extract_context(
    function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, str]:
    """Extract only explicitly approved transaction parameters."""
    try:
        signature = inspect.signature(function)
        bound = signature.bind_partial(*args, **kwargs)
    except (TypeError, ValueError):
        return {}

    context = {}

    for field in SAFE_FIELDS:
        if field not in bound.arguments:
            continue

        value = _safe_value(bound.arguments[field])

        if value is not None:
            context[field] = value

    return context


def _format_context(context: dict[str, str]) -> str:
    """Format approved transaction metadata for logging."""
    if not context:
        return ""

    return " | " + " | ".join(f"{key}={value}" for key, value in context.items())


def _decorate_action[**P, R](
    function: Callable[P, R],
    *,
    verbose: bool,
) -> Callable[P, R]:
    """Create a transaction audit decorator."""

    @wraps(function)
    def wrapper(
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        operation_name = function.__name__
        context = _extract_context(
            function,
            args,
            kwargs,
        )
        context_text = _format_context(context)

        started = time.monotonic()

        logger.info(
            "TRADE | action=%s%s | status=STARTED",
            operation_name,
            context_text,
        )

        if verbose:
            logger.debug(
                "TRADE DEBUG | action=%s%s",
                operation_name,
                context_text,
            )

        try:
            result = function(*args, **kwargs)

        except Exception as exc:
            elapsed = time.monotonic() - started

            logger.error(
                "TRADE | action=%s%s | status=FAILED | error_type=%s | duration=%.4fs",
                operation_name,
                context_text,
                type(exc).__name__,
                elapsed,
            )
            raise

        elapsed = time.monotonic() - started

        logger.info(
            "TRADE | action=%s%s | status=SUCCESS | duration=%.4fs",
            operation_name,
            context_text,
            elapsed,
        )

        return result

    return wrapper


@overload
def log_action[**P, R](
    function: Callable[P, R],
    *,
    verbose: bool = False,
) -> Callable[P, R]: ...


@overload
def log_action(
    function: None = None,
    *,
    verbose: bool = False,
) -> Callable[..., Any]: ...


def log_action(
    function: Callable[..., Any] | None = None,
    *,
    verbose: bool = False,
) -> Callable[..., Any]:
    """Log a trading action without exposing credentials.

    Can be used as:

        @log_action
        def buy(...): ...

        @log_action(verbose=True)
        def sell(...): ...

    Records:
        - action name;
        - explicitly named transaction parameters;
        - success or failure;
        - exception type on failure;
        - execution duration.

    The timestamp is supplied by logging_config.LOG_FORMAT.

    Passwords, API keys, arbitrary arguments, and return values
    are deliberately excluded from audit messages.
    """
    if not isinstance(verbose, bool):
        raise TypeError("verbose должен иметь тип bool")

    if function is None:

        def decorator(
            wrapped: Callable[..., Any],
        ) -> Callable[..., Any]:
            return _decorate_action(
                wrapped,
                verbose=verbose,
            )

        return decorator

    return _decorate_action(
        function,
        verbose=verbose,
    )


def log_operation[**P, R](
    function: Callable[P, R],
) -> Callable[P, R]:
    """Log execution metadata without exposing sensitive arguments.

    Records the operation name, duration, and exception type.
    Does not record arguments, return values, or exception messages.
    """

    @wraps(function)
    def wrapper(
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        operation_name = function.__qualname__

        logger.info(
            "Начало операции: %s",
            operation_name,
        )

        started = time.monotonic()

        try:
            result = function(*args, **kwargs)

        except Exception as exc:
            elapsed = time.monotonic() - started

            logger.error(
                "Ошибка операции %s | тип=%s | %.4f сек.",
                operation_name,
                type(exc).__name__,
                elapsed,
            )
            raise

        elapsed = time.monotonic() - started

        logger.info(
            "Операция завершена: %s | %.4f сек.",
            operation_name,
            elapsed,
        )

        return result

    return wrapper
