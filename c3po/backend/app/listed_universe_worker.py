"""Explicit CLI for resumable canonical full-inventory staging, never promotion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .listed_universe import catalogue_from_payload, utc
from .listed_universe_runtime import produce_catalogue, stage_predictions


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, required=True, help="Previously captured official manifest JSON")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True, help="Explicit quota window/limits/rate_card/deadline and optional provider_symbols")
    parser.add_argument("--run", action="store_true", help="Explicitly collect/value into a private checkpoint; default is a no-read plan")
    parser.add_argument("--stage-records", action="store_true", help="Append canonical records to an unselectable staging namespace after completion")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args(argv)
    if args.stage_records and not args.run:
        parser.error("--stage-records requires --run")
    catalogue = catalogue_from_payload(json.loads(args.catalogue.read_text()))
    policy = json.loads(args.policy.read_text())
    from .config import get_settings
    from .database import Database
    from .listed_universe_producer import LiveCanonicalAdapter
    database = Database(get_settings())
    adapter = LiveCanonicalAdapter(get_settings(), database, market=catalogue.market,
                                   deadline=utc(policy["deadline"]), provider_symbols=policy.get("provider_symbols"))
    receipt = produce_catalogue(
        catalogue, args.checkpoint, adapter, act=args.run, window=policy["window"],
        limits=policy["limits"], rate_card=policy["rate_card"], batch_size=args.batch_size,
        max_batches=args.max_batches,
    )
    if args.stage_records and receipt.get("complete"):
        receipt["stage"] = stage_predictions(database, args.checkpoint, act=True)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
