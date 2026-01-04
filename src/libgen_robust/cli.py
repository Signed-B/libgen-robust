"""Command-line interface for libgen-robust."""

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="libgen-robust",
        description="libgen-robust command-line interface",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"libgen-robust {__version__}",
    )
    return parser


def main() -> int:
    parser = build_parser()
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
