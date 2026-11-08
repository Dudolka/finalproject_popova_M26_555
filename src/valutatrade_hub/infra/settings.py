"""Application settings for ValutaTrade Hub."""

import os
import threading
from pathlib import Path


class SettingsLoader:
    """Singleton providing application configuration."""

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._project_root = Path(__file__).resolve().parents[3]
        self._initialized = True

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def data_dir(self) -> Path:
        value = os.getenv("VALUTATRADE_DATA_DIR")

        if value:
            return Path(value).expanduser().resolve()

        return self._project_root / "data"

    @property
    def rates_ttl_seconds(self) -> int:
        value = os.getenv("VALUTATRADE_RATES_TTL", "3600")

        try:
            ttl = int(value)
        except ValueError as exc:
            raise ValueError("VALUTATRADE_RATES_TTL должен быть целым числом") from exc

        if ttl <= 0:
            raise ValueError("VALUTATRADE_RATES_TTL должен быть положительным")

        return ttl

    @property
    def coingecko_base_url(self) -> str:
        return "https://api.coingecko.com/api/v3"

    @property
    def exchange_rate_base_url(self) -> str:
        return "https://v6.exchangerate-api.com/v6"

    @property
    def exchange_rate_api_key(self) -> str | None:
        return os.getenv("EXCHANGE_RATE_API_KEY")

    @property
    def log_file(self) -> Path:
        return self._project_root / "logs" / "valutatrade.log"
