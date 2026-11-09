"""Record an offline, reproducible asciinema v2 demo with fixture API rates.

Run: uv run python scripts/record_demo.py
Output: demo/ValutaTrade_Hub.cast (safe to commit: no real users or API keys).
The HTTP responses are deliberately simulated; use the real CLI separately to
verify live API connectivity before claiming real-network integration.
"""

import json
import os
import tempfile
import time
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from valutatrade_hub.cli.interface import ValutaTradeCLI
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)

CRYPTO_RATES = {"BTC_USD": 50000.0, "ETH_USD": 2500.0, "SOL_USD": 150.0}
FIAT_RATES = {"EUR_USD": 1.25, "GBP_USD": 1.40, "RUB_USD": 0.01}


def main() -> None:
    """Exercise the real CLI against temporary storage and simulated APIs."""
    events: list[list[object]] = []
    clock = 0.0

    def record(message: str) -> None:
        nonlocal clock
        events.append(
            [round(clock, 2), "o", message.replace("\r\n", "\n").replace("\n", "\r\n")]
        )
        clock += 0.45

    with (
        tempfile.TemporaryDirectory(prefix="valutatrade_demo_") as temp_dir,
        patch.dict(os.environ, {"VALUTATRADE_DATA_DIR": temp_dir}),
        patch.object(CoinGeckoClient, "fetch_rates", return_value=CRYPTO_RATES),
        patch.object(ExchangeRateApiClient, "fetch_rates", return_value=FIAT_RATES),
        patch("valutatrade_hub.cli.interface.getpass", return_value="demo-password"),
    ):
        # The singleton must not retain the user's real runtime data directory.
        DatabaseManager._instance = None
        SettingsLoader._instance = None
        try:
            cli = ValutaTradeCLI()
            record("ValutaTrade Hub — учебная демонстрация (курсы API смоделированы)\n")
            commands = [
                "help",
                "register --username demo_student",
                "login --username demo_student",
                "deposit 1000",
                "update-rates",
                "show-rates --top 3",
                "get-rate --from BTC --to EUR",
                "buy --currency BTC --amount 0.01",
                "show-portfolio --base USD",
                "sell --currency BTC --amount 0.005",
                "show-portfolio --base EUR",
                "buy --currency BTC --amount 100",  # insufficient funds
                "buy --currency XYZ --amount 1",  # unknown currency
                "exit",
            ]
            for command in commands:
                record(f"\r\nvalutatrade> {command}\n")
                output = StringIO()
                with redirect_stdout(output):
                    keep_running = cli.execute(command)
                if output.getvalue():
                    record(output.getvalue())
                if not keep_running:
                    record("Работа ValutaTrade Hub завершена.\n")
                    break
        finally:
            DatabaseManager._instance = None
            SettingsLoader._instance = None

    output_path = Path("demo/ValutaTrade_Hub.cast")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "version": 2,
        "width": 120,
        "height": 35,
        "timestamp": int(time.time()),
        "title": "ValutaTrade Hub — offline functional demo (simulated API rates)",
        "env": {"TERM": "xterm-256color", "SHELL": "/bin/sh"},
    }
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(header, ensure_ascii=False) + "\n")
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(f"Создана демонстрация: {output_path}")
    print("Данные API в демонстрации смоделированы; реальный HTTP не проверяется.")


if __name__ == "__main__":
    main()
