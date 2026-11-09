"""Safe logging decorators for ValutaTrade Hub."""

import logging
import time
from collections.abc import Callable
from functools import wraps

logger = logging.getLogger("valutatrade_hub.decorators")


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
