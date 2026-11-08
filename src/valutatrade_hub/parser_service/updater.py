"""Update and cache exchange rates from external APIs."""

import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)


class RatesUpdater:
    """Fetch, validate, cache, and store exchange rates."""

    REQUIRED_PAIRS = frozenset({"BTC_USD", "ETH_USD", "EUR_USD", "RUB_USD"})

    def __init__(
        self,
        database: DatabaseManager | None = None,
        settings: SettingsLoader | None = None,
        crypto_client: BaseApiClient | None = None,
        fiat_client: BaseApiClient | None = None,
        history_path: Path | None = None,
    ) -> None:
        self._settings = settings if settings is not None else SettingsLoader()
        self._database = database if database is not None else DatabaseManager()
        self._crypto_client = (
            crypto_client if crypto_client is not None else CoinGeckoClient()
        )
        self._fiat_client = (
            fiat_client if fiat_client is not None else ExchangeRateApiClient()
        )
        self._history_path = (
            Path(history_path)
            if history_path is not None
            else Path(self._settings.data_dir) / "exchange_rates.json"
        )

    @staticmethod
    def _validate_pairs(pairs: object) -> dict[str, float]:
        """Validate all required currency pairs."""
        if not isinstance(pairs, dict):
            raise ApiRequestError("Курсы валют должны быть представлены словарём")

        if set(pairs) != RatesUpdater.REQUIRED_PAIRS:
            raise ApiRequestError("Получен неполный или неожиданный набор валютных пар")

        validated = {}

        for pair, value in pairs.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ApiRequestError(f"Некорректный курс {pair}: {value!r}")

            validated[pair] = float(value)

        return validated

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        """Parse an ISO timestamp into UTC."""
        if not isinstance(value, str):
            return None

        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            return None

        return parsed.astimezone(UTC)

    def is_fresh(self, snapshot: dict | None = None) -> bool:
        """Check whether cached rates are valid and within TTL."""
        if snapshot is None:
            snapshot = self._database.load_rates()

        if not isinstance(snapshot, dict):
            return False

        timestamp = self._parse_timestamp(snapshot.get("last_refresh"))
        if timestamp is None:
            return False

        try:
            self._validate_pairs(snapshot.get("pairs"))
        except ApiRequestError:
            return False

        age_seconds = (datetime.now(UTC) - timestamp).total_seconds()

        return 0 <= age_seconds < self._settings.rates_ttl_seconds

    def get_rates(self) -> dict[str, Any]:
        """Return valid cached rates or request new ones."""
        snapshot = self._database.load_rates()

        if self.is_fresh(snapshot):
            return snapshot

        return self.update_rates(force=True)

    def update_rates(
        self,
        force: bool = False,
    ) -> dict[str, Any]:
        """Refresh rates with validation and recovery on failure."""
        previous_snapshot = self._database.load_rates()

        if not force and self.is_fresh(previous_snapshot):
            return previous_snapshot

        crypto_rates = self._crypto_client.get_rates()
        fiat_rates = self._fiat_client.get_rates()

        if not isinstance(crypto_rates, dict):
            raise ApiRequestError("CoinGecko вернул некорректный набор курсов")

        if not isinstance(fiat_rates, dict):
            raise ApiRequestError("ExchangeRate-API вернул некорректный набор курсов")

        if set(crypto_rates) & set(fiat_rates):
            raise ApiRequestError("Источники вернули пересекающиеся валютные пары")

        validated = self._validate_pairs({**crypto_rates, **fiat_rates})

        snapshot = {
            "pairs": validated,
            "last_refresh": datetime.now(UTC).isoformat(),
        }

        # Read and validate history BEFORE changing rates.json.
        history = self._load_history()

        # DatabaseManager replaces rates.json atomically.
        self._database.save_rates(snapshot)

        try:
            self._append_history(snapshot, history)
        except ApiRequestError as history_error:
            # Try to restore the previously stored snapshot.
            try:
                self._database.save_rates(previous_snapshot)
            except Exception as rollback_error:
                raise ApiRequestError(
                    "Не удалось сохранить историю и восстановить "
                    "предыдущие курсы. Требуется проверка файлов."
                ) from rollback_error

            raise ApiRequestError(
                "Не удалось сохранить историю. Предыдущий снимок курсов восстановлен."
            ) from history_error

        return snapshot

    def _load_history(self) -> list:
        """Load and validate the exchange-rate history."""
        if not self._history_path.exists():
            return []

        try:
            with self._history_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                history = json.load(file)

        except (OSError, ValueError) as exc:
            raise ApiRequestError(
                "Не удалось прочитать историю валютных курсов"
            ) from exc

        if not isinstance(history, list):
            raise ApiRequestError("История валютных курсов должна быть списком")

        return history

    def _append_history(
        self,
        snapshot: dict,
        history: list | None = None,
    ) -> None:
        """Append a snapshot using atomic file replacement."""
        if history is None:
            history = self._load_history()

        updated_history = [*history, snapshot]
        temporary_path = None

        try:
            self._history_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._history_path.parent,
                prefix=".rates-history-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)

                json.dump(
                    updated_history,
                    temporary_file,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )

                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(
                temporary_path,
                self._history_path,
            )

        except (OSError, TypeError, ValueError) as exc:
            raise ApiRequestError(
                "Не удалось сохранить историю валютных курсов"
            ) from exc

        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
