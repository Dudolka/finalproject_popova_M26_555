"""Tests for the ValutaTrade Hub rates scheduler."""

import threading
import unittest
from unittest.mock import Mock, patch

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.scheduler import (
    RatesScheduler,
    main,
)


class TestRatesScheduler(unittest.TestCase):
    """Verify scheduling, error handling, and shutdown."""

    def setUp(self):
        self.updater = Mock()
        self.updater.update_rates.return_value = {
            "pairs": {"BTC_USD": 50000.0},
            "last_refresh": "2026-11-09T10:00:00+00:00",
        }

        self.stop_event = threading.Event()

        self.scheduler = RatesScheduler(
            updater=self.updater,
            interval_seconds=0.001,
            stop_event=self.stop_event,
        )

    def test_run_once(self):
        """Call the updater without forcing an API refresh."""
        result = self.scheduler.run_once()

        self.updater.update_rates.assert_called_once_with(force=False)
        self.assertIn("BTC_USD", result["pairs"])

    def test_invalid_interval_zero(self):
        """Reject a zero-length interval."""
        with self.assertRaises(ValueError):
            RatesScheduler(
                updater=self.updater,
                interval_seconds=0,
            )

    def test_invalid_interval_negative(self):
        """Reject a negative interval."""
        with self.assertRaises(ValueError):
            RatesScheduler(
                updater=self.updater,
                interval_seconds=-1,
            )

    def test_invalid_interval_nonfinite(self):
        """Reject infinite and NaN intervals."""
        for interval in [float("inf"), float("nan")]:
            with (
                self.subTest(interval=interval),
                self.assertRaises(ValueError),
            ):
                RatesScheduler(
                    updater=self.updater,
                    interval_seconds=interval,
                )

    def test_invalid_interval_bool(self):
        """Reject booleans as interval values."""
        with self.assertRaises(ValueError):
            RatesScheduler(
                updater=self.updater,
                interval_seconds=True,
            )

    def test_stop(self):
        """Set the stop event."""
        self.assertFalse(self.stop_event.is_set())

        self.scheduler.stop()

        self.assertTrue(self.stop_event.is_set())

    def test_stopped_before_run(self):
        """Do not call the updater when already stopped."""
        self.scheduler.stop()
        self.scheduler.run()

        self.updater.update_rates.assert_not_called()

    def test_run_until_stopped(self):
        """Run a check and then stop cleanly."""

        def update_and_stop(*, force):
            self.assertFalse(force)
            self.scheduler.stop()
            return {
                "pairs": {"BTC_USD": 50000.0},
                "last_refresh": "2026-11-09T10:00:00+00:00",
            }

        self.updater.update_rates.side_effect = update_and_stop

        self.scheduler.run()

        self.updater.update_rates.assert_called_once_with(force=False)
        self.assertTrue(self.stop_event.is_set())

    def test_retry_after_api_error(self):
        """Continue checking after a temporary API failure."""
        call_count = 0

        def update_with_retry(*, force):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                raise ApiRequestError("API временно недоступен")

            self.scheduler.stop()
            return {
                "pairs": {"BTC_USD": 50000.0},
                "last_refresh": "2026-11-09T10:00:00+00:00",
            }

        self.updater.update_rates.side_effect = update_with_retry

        with self.assertLogs(
            "valutatrade_hub.parser_service.scheduler",
            level="WARNING",
        ) as captured:
            self.scheduler.run()

        self.assertEqual(call_count, 2)
        self.assertTrue(
            any("API временно недоступен" in message for message in captured.output)
        )

    def test_retry_after_os_error(self):
        """Continue after a temporary storage failure."""
        self.updater.update_rates.side_effect = [
            OSError("Ошибка чтения файла"),
            {
                "pairs": {"BTC_USD": 50000.0},
                "last_refresh": "2026-11-09T10:00:00+00:00",
            },
        ]

        original_run_once = self.scheduler.run_once
        call_count = 0

        def checked_run_once():
            nonlocal call_count
            call_count += 1

            result = original_run_once()

            if call_count == 2:
                self.scheduler.stop()

            return result

        with patch.object(
            self.scheduler,
            "run_once",
            side_effect=checked_run_once,
        ):
            self.scheduler.run()

        self.assertEqual(call_count, 2)
        self.assertTrue(self.stop_event.is_set())

    def test_main_keyboard_interrupt(self):
        """Handle Ctrl+C without an unhandled traceback."""
        with patch(
            "valutatrade_hub.parser_service.scheduler.RatesScheduler"
        ) as scheduler_class:
            scheduler = scheduler_class.return_value
            scheduler.run.side_effect = KeyboardInterrupt

            main()

            scheduler.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
