"""Coordinate currency-rate updates and persistent storage."""

import logging
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesHistoryStorage

logger = logging.getLogger(__name__)


class RatesUpdater:
    """Fetch rates, update the cache, and maintain observation history."""

    SOURCES: ClassVar[dict[str, str]] = {
        "coingecko": "CoinGecko",
        "exchangerate": "ExchangeRate-API",
    }

    def __init__(
        self,
        database: DatabaseManager | None = None,
        settings: SettingsLoader | None = None,
        crypto_client: BaseApiClient | None = None,
        fiat_client: BaseApiClient | None = None,
        history_path: Path | None = None,
        config: ParserConfig | None = None,
        storage: RatesHistoryStorage | None = None,
    ) -> None:
        """Initialize configuration, API clients, and storage."""
        self._settings = settings if settings is not None else SettingsLoader()
        self._database = database if database is not None else DatabaseManager()
        self._config = config if config is not None else ParserConfig()

        self._crypto_client = (
            crypto_client
            if crypto_client is not None
            else CoinGeckoClient(config=self._config)
        )

        self._fiat_client = (
            fiat_client
            if fiat_client is not None
            else ExchangeRateApiClient(config=self._config)
        )

        if storage is not None and history_path is not None:
            raise ValueError("Укажите либо storage, либо history_path")

        if storage is not None:
            self._storage = storage
        else:
            path = (
                Path(history_path)
                if history_path is not None
                else Path(self._settings.data_dir) / "exchange_rates.json"
            )
            self._storage = RatesHistoryStorage(path)

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        """Parse an ISO-8601 timestamp into UTC."""
        if not isinstance(value, str):
            return None

        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError:
            return None

        if timestamp.tzinfo is None:
            return None

        return timestamp.astimezone(UTC)

    @staticmethod
    def _iso_utc(timestamp: datetime) -> str:
        """Format an aware datetime as ISO-8601 UTC."""
        return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _validate_rate(pair: str, value: object) -> float:
        """Validate a positive finite exchange rate."""
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ApiRequestError(f"Некорректный курс {pair}: {value!r}")

        return float(value)

    def _read_cached_pairs(
        self,
        snapshot: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Normalize cached rates, including the previous numeric format."""
        if not isinstance(snapshot, dict):
            raise ApiRequestError("Некорректный формат кэша валютных курсов")

        raw_pairs = snapshot.get("pairs", {})

        if not isinstance(raw_pairs, dict):
            raise ApiRequestError("Поле pairs должно содержать словарь")

        normalized = {}

        for pair, entry in raw_pairs.items():
            if not isinstance(pair, str) or pair.count("_") != 1:
                raise ApiRequestError("Некорректное название валютной пары")

            from_code, to_code = pair.split("_")

            if (
                not 2 <= len(from_code) <= 5
                or not 2 <= len(to_code) <= 5
                or not from_code.isascii()
                or not to_code.isascii()
                or not from_code.isalpha()
                or not to_code.isalpha()
                or from_code != from_code.upper()
                or to_code != to_code.upper()
            ):
                raise ApiRequestError(f"Некорректная валютная пара: {pair}")

            if isinstance(entry, dict):
                value = entry.get("rate")
                updated_at = entry.get("updated_at")
                source = entry.get("source")
            else:
                # Transitional compatibility with older rates.json files.
                value = entry
                updated_at = snapshot.get("last_refresh")
                source = "LegacyCache"

            rate = self._validate_rate(pair, value)
            timestamp = self._parse_timestamp(updated_at)

            if timestamp is None:
                raise ApiRequestError(f"Некорректное время курса {pair}")

            if not isinstance(source, str) or not source.strip():
                raise ApiRequestError(f"Отсутствует источник курса {pair}")

            normalized[pair] = {
                "rate": rate,
                "updated_at": self._iso_utc(timestamp),
                "source": source.strip(),
            }

        return normalized

    def is_fresh(
        self,
        snapshot: dict | None = None,
    ) -> bool:
        """Check whether every configured pair is within its TTL."""
        if snapshot is None:
            snapshot = self._database.load_rates()

        if not isinstance(snapshot, dict):
            return False

        try:
            pairs = self._read_cached_pairs(snapshot)
        except ApiRequestError:
            return False

        if not self._config.required_pairs.issubset(pairs):
            return False

        now = datetime.now(UTC)
        ttl = self._settings.rates_ttl_seconds

        for pair in self._config.required_pairs:
            timestamp = self._parse_timestamp(pairs[pair]["updated_at"])

            if timestamp is None:
                return False

            age_seconds = (now - timestamp).total_seconds()

            if not 0 <= age_seconds < ttl:
                return False

        return True

    def get_rates(self) -> dict[str, Any]:
        """Return a fresh cache or run an external update."""
        snapshot = self._database.load_rates()

        if self.is_fresh(snapshot):
            return snapshot

        return self.run_update()

    def update_rates(
        self,
        force: bool = False,
    ) -> dict[str, Any]:
        """Keep the legacy updater interface available."""
        if not force:
            snapshot = self._database.load_rates()

            if self.is_fresh(snapshot):
                return snapshot

        return self.run_update()

    def run_update(
        self,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Update selected providers and persist validated observations.

        A failed provider does not interrupt successful providers.
        If no provider succeeds, the cache is left unchanged.
        """
        if source is not None:
            if not isinstance(source, str):
                raise ValueError("Источник должен быть строкой")

            source = source.strip().lower()

            if source not in self.SOURCES:
                raise ValueError("Источник должен быть coingecko или exchangerate")

        logger.info(
            "Начало обновления курсов. Источник: %s",
            source or "all",
        )

        providers = (
            (
                "coingecko",
                self._crypto_client,
                self._config.crypto_currencies,
            ),
            (
                "exchangerate",
                self._fiat_client,
                self._config.fiat_currencies,
            ),
        )

        # Validate history before making any changes.
        self._storage.read_history()

        previous_snapshot = self._database.load_rates()
        cached_pairs = self._read_cached_pairs(previous_snapshot)

        new_pairs: dict[str, dict[str, Any]] = {}
        records: list[dict[str, Any]] = []
        failed_sources: list[str] = []

        for provider_name, client, currencies in providers:
            if source is not None and provider_name != source:
                continue

            source_name = self.SOURCES[provider_name]

            expected_pairs = {
                f"{code}_{self._config.base_currency}" for code in currencies
            }

            logger.info(
                "Получение курсов: %s",
                source_name,
            )

            try:
                rates = client.fetch_rates()

                if not isinstance(rates, dict):
                    raise ApiRequestError("API должен вернуть словарь курсов")

                if set(rates) != expected_pairs:
                    raise ApiRequestError(
                        f"{source_name} вернул неполный "
                        "или неожиданный набор валютных пар"
                    )

                if set(rates) & set(new_pairs):
                    raise ApiRequestError(
                        "Источники вернули повторяющиеся валютные пары"
                    )

                validated = {
                    pair: self._validate_rate(pair, rate)
                    for pair, rate in rates.items()
                }

            except (ApiRequestError, OSError, ValueError) as exc:
                failed_sources.append(provider_name)

                logger.warning(
                    "Не удалось получить курсы от %s: %s",
                    source_name,
                    exc,
                )
                continue

            timestamp = self._iso_utc(datetime.now(UTC))

            for pair, rate in validated.items():
                from_currency, to_currency = pair.split("_", 1)

                record = self._storage.create_record(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate=rate,
                    timestamp=timestamp,
                    source=source_name,
                )

                records.append(record)

                candidate = {
                    "rate": rate,
                    "updated_at": timestamp,
                    "source": source_name,
                }

                previous = cached_pairs.get(pair)

                if previous is not None:
                    previous_time = self._parse_timestamp(previous["updated_at"])
                    candidate_time = self._parse_timestamp(timestamp)

                    if previous_time >= candidate_time:
                        continue

                new_pairs[pair] = candidate

            logger.info(
                "Курсы получены от %s: %d",
                source_name,
                len(validated),
            )

        if not records:
            logger.error("Обновление невозможно: нет успешных источников")
            raise ApiRequestError(
                "Не удалось получить курсы ни от одного выбранного источника"
            )

        updated_pairs = {
            **cached_pairs,
            **new_pairs,
        }

        last_refresh = self._iso_utc(datetime.now(UTC))

        snapshot = {
            "pairs": updated_pairs,
            "last_refresh": last_refresh,
        }

        logger.info(
            "Сохранение кэша: %d обновлённых валютных пар",
            len(new_pairs),
        )

        # DatabaseManager saves rates.json atomically.
        self._database.save_rates(snapshot)

        try:
            added = self._storage.append_records(records)

        except (ApiRequestError, OSError) as history_error:
            logger.exception("Не удалось сохранить историю курсов")

            try:
                self._database.save_rates(previous_snapshot)

            except (OSError, ApiRequestError) as rollback_error:
                raise ApiRequestError(
                    "Не удалось сохранить историю и восстановить "
                    "предыдущие курсы. Требуется проверка файлов."
                ) from rollback_error

            raise ApiRequestError(
                "Не удалось сохранить историю. Предыдущие курсы восстановлены."
            ) from history_error

        logger.info(
            "Обновление завершено. Получено курсов: %d. "
            "В историю добавлено записей: %d. "
            "Ошибок источников: %d",
            len(records),
            added,
            len(failed_sources),
        )

        return snapshot
