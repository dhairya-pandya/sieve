"""Command-line entry point."""
from __future__ import annotations

import argparse
import asyncio
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sieve", description="Verifiable AI grant reviews for NEAR DAOs")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("verify", help="re-check every on-chain review without an API key")
    p.add_argument("--contract", help="Sieve contract (default: deployments/testnet.json)")
    p.add_argument("--round", type=int, help="only this round")
    p = sub.add_parser("setup", help="deploy the contract, demo DAO and rounds to testnet")
    p.add_argument("--operator", required=True, help="funded testnet account with a key in ~/.near-credentials/testnet")
    p.add_argument("--name", default="sieve", help="sub-account name for the contract")
    p.add_argument("--dao", default="sieve-demo", help="Sputnik DAO name")
    sub.add_parser("attest", help="check the TEE attestation of every review model")
    p = sub.add_parser("relay", help="review open proposals with NEAR AI Cloud and post signed results")
    p.add_argument("--operator", required=True, help="testnet account that pays gas, key in ~/.near-credentials/testnet")
    p.add_argument("--contract", help="Sieve contract (default: deployments/testnet.json)")
    p.add_argument("--once", action="store_true", help="one pass, then exit")
    p.add_argument("--interval", type=float, default=15.0, help="seconds between passes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "setup":
        from sieve.setup import setup
        asyncio.run(setup(args.operator, args.name, args.dao))
        return 0
    if args.command == "verify":
        from sieve.setup import deployment
        from sieve.verify import verify
        return verify(args.contract or deployment()["contract"], args.round)
    if args.command == "relay":
        from sieve.relayer import run
        from sieve.setup import deployment
        asyncio.run(run(args.operator, args.contract or deployment()["contract"], args.once, args.interval))
        return 0
    if args.command == "attest":
        from sieve.attest import model_signers
        from sieve.config import REVIEW_MODELS
        model_signers(REVIEW_MODELS)
        return 0
    print(f"{args.command}: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
