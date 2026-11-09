"""Safely migrate legacy exchange-rate snapshots to observation records."""

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.storage import RatesHistoryStorage

HISTORY_PATH = Path("data/exchange_rates.json")
BACKUP_DIR = Path("backups")


def load_history(path: Path) -> list[dict]:
    """Load existing history without modifying it."""
    if not path.is_file():
        raise FileNotFoundError(f"Файл истории не найден: {path}")

    with path.open(encoding="utf-8") as file:
        history = json.load(file)

    if not isinstance(history, list):
        raise TypeError("История должна быть списком")

    return history


def migrate_records(
    history: list[dict],
) -> tuple[list[dict], int]:
    """Convert legacy snapshots to individual rate observations."""
    records = []
    known = {}
    migrated_snapshots = 0

    for item in history:
        if not isinstance(item, dict):
            raise TypeError("Элемент истории должен быть словарём")

        if "id" in item:
            candidates = [RatesHistoryStorage._validate_record(item)]

        elif "pairs" in item and "last_refresh" in item:
            pairs = item["pairs"]

            if not isinstance(pairs, dict):
                raise TypeError("Поле pairs должно быть словарём")

            candidates = []

            for pair, entry in pairs.items():
                if not isinstance(pair, str) or pair.count("_") != 1:
                    raise ValueError(f"Некорректная валютная пара: {pair!r}")

                from_currency, to_currency = pair.split("_", 1)

                if isinstance(entry, dict):
                    rate = entry.get("rate")
                    timestamp = entry.get(
                        "updated_at",
                        item["last_refresh"],
                    )
                    source = entry.get("source")
                else:
                    rate = entry
                    timestamp = item["last_refresh"]
                    source = item.get("source")

                if not isinstance(source, str) or not source.strip():
                    source = "LegacyCache"

                record = RatesHistoryStorage.create_record(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate=rate,
                    timestamp=timestamp,
                    source=source,
                    meta={"migrated_from": "legacy_snapshot"},
                )
                candidates.append(record)

            migrated_snapshots += 1

        else:
            raise ValueError("Обнаружен неизвестный формат записи истории")

        for record in candidates:
            existing = known.get(record["id"])

            if existing is not None:
                if existing != record:
                    raise ValueError(
                        f"Конфликт записей с одинаковым ID: {record['id']}"
                    )
                continue

            known[record["id"]] = record
            records.append(record)

    return records, migrated_snapshots


def main() -> None:
    """Preview or apply a validated migration."""
    parser = argparse.ArgumentParser(
        description="Миграция истории курсов к формату МИФИ"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Записать результат после создания резервной копии",
    )
    args = parser.parse_args()

    original = load_history(HISTORY_PATH)
    migrated, legacy_count = migrate_records(original)

    print(f"Исходных элементов истории: {len(original)}")
    print(f"Старых снимков: {legacy_count}")
    print(f"Записей после преобразования: {len(migrated)}")

    if legacy_count == 0:
        print("Миграция не требуется.")
        return

    if not args.apply:
        print("Предварительная проверка завершена.")
        print("Данные не изменены.")
        print("Для применения используйте параметр --apply.")
        return

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")

    backup_path = BACKUP_DIR / (f"exchange_rates_before_migration_{timestamp}.json")

    shutil.copy2(
        HISTORY_PATH,
        backup_path,
    )

    print(f"Резервная копия: {backup_path}")

    storage = RatesHistoryStorage(HISTORY_PATH)
    storage.save_history(migrated)

    saved = storage.read_history()

    if len(saved) != len(migrated):
        raise ApiRequestError("Проверка количества записей после миграции не пройдена")

    if saved != migrated:
        raise ApiRequestError("Сохранённые записи отличаются от подготовленных")

    print("Миграция успешно завершена.")
    print(f"Проверено записей: {len(saved)}")


if __name__ == "__main__":
    main()
