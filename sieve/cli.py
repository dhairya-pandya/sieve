"""Command-line entry point. Subcommands are registered by their modules."""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sieve", description="Verifiable AI grant reviews for NEAR DAOs")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify", help="re-check every on-chain review without an API key")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"{args.command}: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
