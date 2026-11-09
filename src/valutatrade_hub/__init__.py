"""ValutaTrade Hub application package."""


def main() -> None:
    """Start the ValutaTrade Hub command-line interface."""
    from valutatrade_hub.cli.interface import main as cli_main

    cli_main()
