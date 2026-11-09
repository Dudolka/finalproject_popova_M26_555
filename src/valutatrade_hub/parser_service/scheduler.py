"""Periodic exchange-rate updater for ValutaTrade Hub."""

import logging
import math
import threading

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.updater import RatesUpdater

logger = logging.getLogger(__name__)


class RatesScheduler:
    """Periodically check and update exchange rates."""

    def __init__(
        self,
        updater: RatesUpdater | None = None,
        interval_seconds: float = 60.0,
        stop_event: threading.Event | None = None,
    ) -> None:
        """Initialize the scheduler and validate its interval."""
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not math.isfinite(interval_seconds)
            or interval_seconds <= 0
        ):
            raise ValueError(
                "Интервал обновления должен быть положительным конечным числом"
            )

        self._updater = updater if updater is not None else RatesUpdater()
        self._interval_seconds = float(interval_seconds)
        self._stop_event = stop_event if stop_event is not None else threading.Event()

    def run_once(self) -> dict:
        """Check rates once, updating only when needed."""
        return self._updater.update_rates(force=False)

    def run(self) -> None:
        """Run checks periodically until stopped."""
        logger.info(
            "Планировщик запущен. Интервал проверки: %.1f сек.",
            self._interval_seconds,
        )

        while not self._stop_event.is_set():
            try:
                snapshot = self.run_once()

                logger.info(
                    "Проверка курсов завершена. Последнее обновление: %s",
                    snapshot.get("last_refresh", "нет данных"),
                )

            except (ApiRequestError, OSError, ValueError) as exc:
                logger.warning(
                    "Не удалось проверить или обновить курсы: %s",
                    exc,
                )

            self._stop_event.wait(self._interval_seconds)

        logger.info("Планировщик остановлен.")

    def stop(self) -> None:
        """Request a graceful shutdown."""
        self._stop_event.set()


def main() -> None:
    """Run the scheduler as a standalone process."""
    setup_logging()

    scheduler = RatesScheduler()

    try:
        scheduler.run()
    except KeyboardInterrupt:
        scheduler.stop()
        logger.info("Остановка по запросу пользователя.")


if __name__ == "__main__":
    main()
