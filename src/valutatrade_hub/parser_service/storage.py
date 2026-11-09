"""Atomic storage for historical exchange-rate observations."""

import json
import math
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from valutatrade_hub.core.exceptions import ApiRequestError


class RatesHistoryStorage:
    """Persist unique currency-pair observations in JSON."""

    def __init__(
        self,
        path: str | Path = "data/exchange_rates.json",
    ) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        """Return the history file location."""
        return self._path

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        """Parse an ISO timestamp and convert it to UTC."""
        if not isinstance(value, str):
            raise ApiRequestError("Время курса должно быть строкой ISO")

        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ApiRequestError("Некорректное время валютного курса") from exc

        if timestamp.tzinfo is None:
            raise ApiRequestError("Время курса должно содержать часовой пояс")

        return timestamp.astimezone(UTC)

    @staticmethod
    def _validate_code(value: object) -> str:
        """Validate a currency code."""
        if (
            not isinstance(value, str)
            or not 2 <= len(value) <= 5
            or not value.isascii()
            or not value.isalnum()
            or value != value.upper()
        ):
            raise ApiRequestError(f"Некорректный код валюты: {value!r}")

        return value

    @classmethod
    def create_record(
        cls,
        from_currency: str,
        to_currency: str,
        rate: float,
        timestamp: str,
        source: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create and validate a historical rate record."""
        from_code = cls._validate_code(from_currency)
        to_code = cls._validate_code(to_currency)

        if from_code == to_code:
            raise ApiRequestError("Валютная пара должна содержать разные валюты")

        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        ):
            raise ApiRequestError("Курс должен быть положительным конечным числом")

        if not isinstance(source, str) or not source.strip():
            raise ApiRequestError("Источник курса не указан")

        if meta is not None and not isinstance(meta, dict):
            raise ApiRequestError("Метаданные курса должны быть словарём")

        parsed_time = cls._parse_timestamp(timestamp)

        normalized_time = parsed_time.isoformat().replace("+00:00", "Z")

        pair = f"{from_code}_{to_code}"
        record_id = f"{pair}_{normalized_time}"

        return {
            "id": record_id,
            "from_currency": from_code,
            "to_currency": to_code,
            "rate": float(rate),
            "timestamp": normalized_time,
            "source": source.strip(),
            "meta": dict(meta) if meta is not None else {},
        }

    @classmethod
    def _validate_record(
        cls,
        record: object,
    ) -> dict[str, Any]:
        """Validate an existing historical record."""
        if not isinstance(record, dict):
            raise ApiRequestError("Запись истории должна быть словарём")

        required = (
            "id",
            "from_currency",
            "to_currency",
            "rate",
            "timestamp",
            "source",
        )

        if any(key not in record for key in required):
            raise ApiRequestError("В записи истории отсутствуют обязательные поля")

        normalized = cls.create_record(
            from_currency=record["from_currency"],
            to_currency=record["to_currency"],
            rate=record["rate"],
            timestamp=record["timestamp"],
            source=record["source"],
            meta=record.get("meta"),
        )

        if record["id"] != normalized["id"]:
            raise ApiRequestError(
                "Идентификатор записи истории не соответствует валютной паре и времени"
            )

        return normalized

    def read_history(self) -> list[dict[str, Any]]:
        """Read history and reject corrupted records."""
        with self._lock:
            if not self._path.exists():
                return []

            try:
                with self._path.open(
                    "r",
                    encoding="utf-8",
                ) as file:
                    data = json.load(file)
            except (OSError, ValueError) as exc:
                raise ApiRequestError("Не удалось прочитать историю курсов") from exc

            if not isinstance(data, list):
                raise ApiRequestError("История курсов должна быть списком")

            records = [self._validate_record(record) for record in data]

            identifiers = [record["id"] for record in records]

            if len(identifiers) != len(set(identifiers)):
                raise ApiRequestError("История содержит повторяющиеся ID")

            return records

    def save_history(
        self,
        records: list[dict[str, Any]],
    ) -> None:
        """Atomically replace the history JSON file."""
        if not isinstance(records, list):
            raise ApiRequestError("История должна быть списком записей")

        validated = [self._validate_record(record) for record in records]

        identifiers = [record["id"] for record in validated]

        if len(identifiers) != len(set(identifiers)):
            raise ApiRequestError("Нельзя сохранить историю с повторяющимися ID")

        with self._lock:
            temporary_path = None

            try:
                self._path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self._path.parent,
                    prefix=".exchange-rates-",
                    suffix=".tmp",
                    delete=False,
                ) as temporary_file:
                    temporary_path = Path(temporary_file.name)

                    json.dump(
                        validated,
                        temporary_file,
                        ensure_ascii=False,
                        indent=2,
                        allow_nan=False,
                    )
                    temporary_file.write("\n")
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())

                os.replace(
                    temporary_path,
                    self._path,
                )

            except (OSError, TypeError, ValueError) as exc:
                raise ApiRequestError("Не удалось сохранить историю курсов") from exc

            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        pass

    def append_records(
        self,
        records: list[dict[str, Any]],
    ) -> int:
        """Add new observations, skipping duplicate IDs.

        Returns:
            Number of newly appended records.
        """
        if not isinstance(records, list):
            raise ApiRequestError("Новые записи должны быть списком")

        validated = [self._validate_record(record) for record in records]

        with self._lock:
            existing = self.read_history()

            known_ids = {record["id"] for record in existing}

            added = []

            for record in validated:
                if record["id"] in known_ids:
                    continue

                known_ids.add(record["id"])
                added.append(record)

            if not added:
                return 0

            self.save_history([*existing, *added])

            return len(added)


if __name__ == "__main__":
    pass
