"""JSON storage manager for ValutaTrade Hub."""

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


class DatabaseManager:
    """Singleton manager for local JSON data storage."""

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, data_dir: str | Path = "data"):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, data_dir: str | Path = "data") -> None:
        if self._initialized:
            return

        self._data_dir = Path(data_dir).expanduser().resolve()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._users_file = self._data_dir / "users.json"
        self._portfolios_file = self._data_dir / "portfolios.json"
        self._rates_file = self._data_dir / "rates.json"

        self._write_lock = threading.RLock()
        self._initialized = True

    @property
    def data_dir(self) -> Path:
        """Return the data directory."""
        return self._data_dir

    def _read_json(self, path: Path, default: Any) -> Any:
        """Read JSON without silently hiding corrupted data."""
        if not path.exists():
            return default

        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write_json(self, path: Path, data: Any) -> None:
        """Atomically replace a JSON file with new data."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(
                    data,
                    temporary_file,
                    ensure_ascii=False,
                    indent=4,
                    allow_nan=False,
                )
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, path)

        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load_users(self) -> list:
        """Load registered users."""
        return self._read_json(self._users_file, [])

    def save_users(self, users: list) -> None:
        """Persist registered users."""
        if not isinstance(users, list):
            raise TypeError("Данные пользователей должны быть списком")

        with self._write_lock:
            self._write_json(self._users_file, users)

    def load_portfolios(self) -> list:
        """Load user portfolios."""
        return self._read_json(self._portfolios_file, [])

    def save_portfolios(self, portfolios: list) -> None:
        """Persist user portfolios."""
        if not isinstance(portfolios, list):
            raise TypeError("Данные портфелей должны быть списком")

        with self._write_lock:
            self._write_json(self._portfolios_file, portfolios)

    def load_rates(self) -> dict:
        """Load the latest exchange rates."""
        return self._read_json(
            self._rates_file,
            {"pairs": {}, "last_refresh": None},
        )

    def save_rates(self, rates: dict) -> None:
        """Persist the latest exchange rates."""
        if not isinstance(rates, dict):
            raise TypeError("Данные курсов должны быть словарём")

        with self._write_lock:
            self._write_json(self._rates_file, rates)
