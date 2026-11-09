"""Validated conversion helpers shared by the CLI and the domain layer."""

import math


def cross_rate(from_usd: float, to_usd: float) -> float:
    """Calculate units of target currency per one source currency.

    Both arguments are USD prices of one unit of the respective currency.
    """
    for value in (from_usd, to_usd):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError("Для пересчёта нужны положительные конечные курсы")
    result = from_usd / to_usd
    if not math.isfinite(result) or result <= 0:
        raise ValueError("Некорректный результат пересчёта курса")
    return result
