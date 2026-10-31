"""Capture an official listing manifest without refreshing a valuation producer.

Default: parse a supplied file and print a receipt, without a database write.
Downloads and recording each require their own explicit flag. This is not wired
into the nightly worker before the capacity and Fable review gates are complete.
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .listed_universe import (
    B3_LIST_URL, CATALOGUE_ANALYSIS, NASDAQ_LIST_URL, NYSE_LIST_URL,
    Catalogue, parse_b3_titulos, parse_nasdaq_directory,
)

MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_DIRECTORY_BYTES = 128 * 1024 * 1024


def decode_directory(raw: bytes, market: str) -> bytes:
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("official listing download is larger than the bounded input budget")
    if market != "B3" or not zipfile.is_zipfile(io.BytesIO(raw)):
        return raw
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if len(members) != 1 or members[0].file_size > MAX_DIRECTORY_BYTES:
            raise ValueError("B3 archive must contain one bounded directory file")
        return archive.read(members[0])


def record_catalogue(database, catalogue: Catalogue) -> str:
    payload = catalogue.payload()
    method = database.ensure_methodology_version(
        "official_listing_inventory", 1,
        {"source_format": catalogue.source_format, "screening_exclusions": False},
        "Official listed inventory; no valuation or buy-permission promotion",
    )
    return database.save_analysis_snapshot(
        CATALOGUE_ANALYSIS, catalogue.market, method,
        {"source_url": catalogue.source_url, "raw_sha256": catalogue.raw_sha256},
        payload, datetime.fromisoformat(catalogue.received_at),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", choices=("B3", "NASDAQ", "NYSE"), required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--download", action="store_true")
    parser.add_argument("--record", action="store_true", help="Record the inventory only, without publishing a TP generation")
    args = parser.parse_args(argv)
    if args.input:
        if args.input.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("official listing input exceeds the bounded input budget")
        raw = args.input.read_bytes()
    else:
        url = {"B3": B3_LIST_URL, "NASDAQ": NASDAQ_LIST_URL, "NYSE": NYSE_LIST_URL}[args.market]
        # No market provider credential is involved, and redirects to a different
        # host are refused: the manifest must come from the official origin.
        with httpx.Client(timeout=45, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise ValueError("official listing download exceeds the bounded input budget")
                    chunks.append(chunk)
                raw = b"".join(chunks)
    received_at = datetime.now(timezone.utc)
    directory = decode_directory(raw, args.market)
    catalogue = (parse_b3_titulos(directory, received_at=received_at) if args.market == "B3"
                 else parse_nasdaq_directory(directory, market=args.market, received_at=received_at))
    stored_id = None
    if args.record:
        from .config import get_settings
        from .database import Database
        stored_id = record_catalogue(Database(get_settings()), catalogue)
    payload = catalogue.payload()
    print(json.dumps({key: value for key, value in payload.items() if key != "listings"}
                     | {"listing_count": len(catalogue.listings), "recorded": bool(stored_id),
                        "snapshot_id": stored_id, "valuation_published": False, "buy_permission_promoted": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
