"""Command-line interface for libgen-bulk."""

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="libgen-bulk",
        description="libgen-bulk command-line interface",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"libgen-bulk {__version__}",
    )
    return parser


def main() -> int:
    parser = build_parser()
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
