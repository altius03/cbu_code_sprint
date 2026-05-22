from __future__ import annotations

import argparse
from pathlib import Path

from .paths import default_home


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CBU Code Sprint")
    parser.add_argument(
        "--home",
        type=Path,
        default=default_home(),
        help="Portable app home directory containing data/config/assets/exports/backups",
    )
    parser.add_argument("--fullscreen", action="store_true", help="Start the GUI in fullscreen mode")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from .app import run_app
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print("PySide6 is not installed. Install project dependencies before running the GUI.")
            return 2
        raise
    return run_app(home=args.home, fullscreen=args.fullscreen)


if __name__ == "__main__":
    raise SystemExit(main())
