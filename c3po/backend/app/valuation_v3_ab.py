from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable, Iterable, Mapping

from .config import get_settings
from .database import Database
from .valuation_v2_engine import (
    ENGINE_VERSION as V2_ENGINE_VERSION,
    US_RISK_FREE_FALLBACK,
    ValuationV2Engine,
)
from .valuation_v2_shadow import ValuationV2ShadowService
from .valuation_v3_engine import ENGINE_VERSION as V3_ENGINE_VERSION, ValuationV3Engine
from .valuation_v3_inputs import (
    attach_quality_to_multiples,
    build_quality_index,
    canonical_symbol,
)
from .valuation_v3_macro import package_hash_is_valid, validate_us_curve_package


MANIFEST_SCHEMA_VERSION = "VALUATION-V3-AB-MANIFEST-v2"
REPORT_SCHEMA_VERSION = "VALUATION-V3-AB-REPORT-v2"
AB_AS_OF = date(2026, 8, 24)
AB_EVALUATION_DATE = date(2026, 8, 25)
MARKETS = ("B3", "NASDAQ", "NYSE")
EXPECTED_COUNTS = {"B3": 100, "NASDAQ": 295, "NYSE": 299}
ENGINE_FILE_PATHS = {
    "v2": Path(__file__).with_name("valuation_v2_engine.py"),
    "v3": Path(__file__).with_name("valuation_v3_engine.py"),
}
HARNESS_FILE_PATH = Path(__file__)


class ValuationV3ABError(RuntimeError):
    pass


class ManifestValidationError(ValuationV3ABError):
    pass


class V2ReproductionError(ValuationV3ABError):
    pass


@dataclass(frozen=True)
class FrozenSnapshotReference:
    role: str
    market: str
    snapshot_id: str
    analysis_type: str
    entity_key: str
    published_at: datetime


def _utc(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc)


def _published(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


FROZEN_SNAPSHOT_REFERENCES = (
    FrozenSnapshotReference(
        "universe", "B3", "71437151-ab94-4e72-b289-a98f1237034a",
        "valuation_universe", "B3_UNIVERSE", _published("2026-08-24T14:21:19.551280"),
    ),
    FrozenSnapshotReference(
        "universe", "NASDAQ", "de4062a9-dcd7-4d79-b660-6a49c84ecfcf",
        "valuation_universe", "NASDAQ_UNIVERSE", _published("2026-08-25T02:29:58.195188"),
    ),
    FrozenSnapshotReference(
        "universe", "NYSE", "bd9f5d91-635c-4c35-98f3-6d5208c88ee7",
        "valuation_universe", "NYSE_UNIVERSE", _published("2026-08-25T02:32:31.046889"),
    ),
    FrozenSnapshotReference(
        "v2_data", "B3", "aa9ecf44-dd62-4bb6-a529-25baaaa3bddc",
        "valuation_v2_data", "B3_V2_DATA", _published("2026-08-25T02:35:56.529195"),
    ),
    FrozenSnapshotReference(
        "v2_data", "NASDAQ", "bdd5c12c-9fd0-4f76-b361-c06cd8058938",
        "valuation_v2_data", "NASDAQ_V2_DATA", _published("2026-08-25T02:36:57.518558"),
    ),
    FrozenSnapshotReference(
        "v2_data", "NYSE", "78117445-719f-44a5-a644-317f1e2b6d73",
        "valuation_v2_data", "NYSE_V2_DATA", _published("2026-08-25T02:37:58.921266"),
    ),
    FrozenSnapshotReference(
        "peer_quality", "B3", "9e651be9-847d-4d47-a384-f0caa0ce09d0",
        "valuation_v2_peer_quality", "B3_V2_PEER_QUALITY",
        _published("2026-08-25T02:39:50.607593"),
    ),
    FrozenSnapshotReference(
        "peer_quality", "US", "777825de-7b7e-4ace-8f24-84d9d9a157c5",
        "valuation_v2_peer_quality", "US_V2_PEER_QUALITY",
        _published("2026-08-25T02:41:38.465991"),
    ),
    FrozenSnapshotReference(
        "chewie", "B3", "71507f75-d32c-4b9f-9000-95f8177d5823",
        "chewie_fundamentals", "B3_FUNDAMENTALS", _published("2026-08-24T22:03:35.615463"),
    ),
    FrozenSnapshotReference(
        "chewie", "NASDAQ", "ce9295c0-c298-4cc6-bb0b-562223f42044",
        "chewie_fundamentals", "NASDAQ_FUNDAMENTALS", _published("2026-08-24T22:06:01.276426"),
    ),
    FrozenSnapshotReference(
        "chewie", "NYSE", "681caff1-b974-465e-b1de-5a6f8e9b87fa",
        "chewie_fundamentals", "NYSE_FUNDAMENTALS", _published("2026-08-24T22:07:34.054720"),
    ),
    FrozenSnapshotReference(
        "v2_shadow", "B3", "b759d4b3-101c-4fa8-9e97-d79dcf5d87a6",
        "valuation_v2_shadow", "B3_V2_SHADOW", _published("2026-08-25T02:38:51.814238"),
    ),
    FrozenSnapshotReference(
        "v2_shadow", "NASDAQ", "cfd47f1b-6946-426e-a85e-34dfb0daef9b",
        "valuation_v2_shadow", "NASDAQ_V2_SHADOW", _published("2026-08-25T02:38:52.413532"),
    ),
    FrozenSnapshotReference(
        "v2_shadow", "NYSE", "10ea1290-ed19-486f-af54-9c3bc104a3ce",
        "valuation_v2_shadow", "NYSE_V2_SHADOW", _published("2026-08-25T02:38:53.045874"),
    ),
)

WATCHLIST = (
    ("baseline", "NYSE", "HPQ"),
    ("baseline", "NASDAQ", "CPB"),
    ("baseline", "NYSE", "MPC"),
    ("baseline", "NYSE", "CF"),
    ("baseline", "NASDAQ", "CMCSA"),
    ("b3_top5", "B3", "RECV3"),
    ("b3_top5", "B3", "GOAU4"),
    ("b3_top5", "B3", "INTB3"),
    ("b3_top5", "B3", "SAPR4"),
    ("b3_top5", "B3", "LIGT3"),
    ("nasdaq_top5", "NASDAQ", "CHTR"),
    ("nasdaq_top5", "NASDAQ", "PDD"),
    ("nasdaq_top5", "NASDAQ", "CPB"),
    ("nasdaq_top5", "NASDAQ", "BIDU"),
    ("nasdaq_top5", "NASDAQ", "ADBE"),
    ("nyse_top5", "NYSE", "NVO"),
    ("nyse_top5", "NYSE", "HPQ"),
    ("nyse_top5", "NYSE", "ACN"),
    ("nyse_top5", "NYSE", "FIS"),
    ("nyse_top5", "NYSE", "GPN"),
)


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_ready(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _jsonb_numeric_ready(value: Any) -> Any:
    """Mirror JSONB's normalization of signed floating-point zero only."""
    if isinstance(value, Mapping):
        return {str(key): _jsonb_numeric_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonb_numeric_ready(item) for item in value]
    if isinstance(value, float) and value == 0.0:
        return 0.0
    return value


def v2_output_sha256(value: Any) -> str:
    return canonical_sha256(_jsonb_numeric_ready(value))


def _without_hash(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != field}


def manifest_hash(payload: Mapping[str, Any]) -> str:
    return canonical_sha256(_without_hash(payload, "manifest_sha256"))


def _snapshot_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(snapshot["id"]),
        "analysis_type": str(snapshot["analysis_type"]),
        "entity_key": str(snapshot["entity_key"]),
        "methodology_version_id": str(snapshot["methodology_version_id"]),
        "inputs": snapshot.get("inputs") or {},
        "outputs": snapshot.get("outputs") or {},
        "published_at": _utc(snapshot["published_at"]).isoformat(),
    }


class DatabaseSnapshotLoader:
    """Exact-ID, read-only snapshot loader used by the operator CLI."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def __call__(self, snapshot_id: str) -> dict[str, Any] | None:
        if not self.database.database_url:
            for item in self.database._analysis_snapshots:  # noqa: SLF001
                if str(item.get("id")) == snapshot_id:
                    return dict(item)
            return None
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT id::text, analysis_type, entity_key,
                       methodology_version_id::text, inputs, outputs, published_at
                FROM analysis_snapshots
                WHERE id = %s
                """,
                (snapshot_id,),
            ).fetchone()
        if not row:
            return None
        return dict(zip(
            (
                "id", "analysis_type", "entity_key", "methodology_version_id",
                "inputs", "outputs", "published_at",
            ),
            row,
        ))


SnapshotLoader = Callable[[str], dict[str, Any] | None]


def _require_snapshot(
    loader: SnapshotLoader,
    snapshot_id: str,
    *,
    analysis_type: str,
    entity_key: str,
    published_at: datetime | None = None,
) -> dict[str, Any]:
    snapshot = loader(snapshot_id)
    if snapshot is None:
        raise ManifestValidationError(f"Missing frozen snapshot {snapshot_id}")
    if str(snapshot.get("analysis_type")) != analysis_type:
        raise ManifestValidationError(f"Snapshot {snapshot_id} analysis_type mismatch")
    if str(snapshot.get("entity_key")) != entity_key:
        raise ManifestValidationError(f"Snapshot {snapshot_id} entity_key mismatch")
    actual_published = snapshot.get("published_at")
    if not isinstance(actual_published, datetime):
        raise ManifestValidationError(f"Snapshot {snapshot_id} has no published_at")
    if published_at is not None and _utc(actual_published) != _utc(published_at):
        raise ManifestValidationError(f"Snapshot {snapshot_id} published_at mismatch")
    return snapshot


def _engine_file_record(name: str) -> dict[str, Any]:
    path = ENGINE_FILE_PATHS[name]
    content = path.read_bytes()
    version = V2_ENGINE_VERSION if name == "v2" else V3_ENGINE_VERSION
    return {
        "engine_version": version,
        "path": f"app/{path.name}",
        "file_sha256": hashlib.sha256(content).hexdigest(),
    }


def _harness_file_record() -> dict[str, str]:
    return {
        "path": f"app/{HARNESS_FILE_PATH.name}",
        "file_sha256": hashlib.sha256(HARNESS_FILE_PATH.read_bytes()).hexdigest(),
    }


def build_manifest(
    loader: SnapshotLoader,
    *,
    selic_snapshot_id: str,
    us_curve_snapshot_id: str,
    engine_commit: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", engine_commit):
        raise ManifestValidationError("engine_commit must be a full lowercase Git SHA")

    records: list[dict[str, Any]] = []
    for reference in FROZEN_SNAPSHOT_REFERENCES:
        snapshot = _require_snapshot(
            loader,
            reference.snapshot_id,
            analysis_type=reference.analysis_type,
            entity_key=reference.entity_key,
            published_at=reference.published_at,
        )
        records.append({
            "role": reference.role,
            "market": reference.market,
            "snapshot_id": reference.snapshot_id,
            "analysis_type": reference.analysis_type,
            "entity_key": reference.entity_key,
            "published_at": _utc(reference.published_at).isoformat(),
            "snapshot_sha256": canonical_sha256(_snapshot_payload(snapshot)),
        })

    macro_specs = (
        (
            "selic_macro", "B3", selic_snapshot_id,
            "valuation_macro_history", "B3_SELIC_REGIME",
        ),
        (
            "treasury_macro", "US", us_curve_snapshot_id,
            "valuation_macro_rates", "US_5Y_INTERPOLATED",
        ),
    )
    macro_packages: dict[str, dict[str, Any]] = {}
    for role, market, snapshot_id, analysis_type, entity_key in macro_specs:
        snapshot = _require_snapshot(
            loader, snapshot_id, analysis_type=analysis_type, entity_key=entity_key,
        )
        package = snapshot.get("outputs")
        if not isinstance(package, dict) or not package_hash_is_valid(package):
            raise ManifestValidationError(f"Macro package hash mismatch: {entity_key}")
        if package.get("as_of") != AB_AS_OF.isoformat():
            raise ManifestValidationError(f"Macro package as_of mismatch: {entity_key}")
        if role == "treasury_macro":
            validate_us_curve_package(package, as_of=AB_AS_OF)
        records.append({
            "role": role,
            "market": market,
            "snapshot_id": snapshot_id,
            "analysis_type": analysis_type,
            "entity_key": entity_key,
            "published_at": _utc(snapshot["published_at"]).isoformat(),
            "snapshot_sha256": canonical_sha256(_snapshot_payload(snapshot)),
        })
        macro_packages[role] = {
            "snapshot_id": snapshot_id,
            "payload_sha256": str(package["payload_sha256"]),
            "as_of": str(package["as_of"]),
        }

    shadow_output_hashes: dict[str, str] = {}
    for record in records:
        if record["role"] != "v2_shadow":
            continue
        snapshot = loader(str(record["snapshot_id"]))
        if snapshot is None:
            raise ManifestValidationError("Frozen V2 shadow disappeared during manifest build")
        shadow_output_hashes[str(record["market"])] = v2_output_sha256(snapshot["outputs"])

    payload: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "as_of": AB_AS_OF.isoformat(),
        "evaluation_date": AB_EVALUATION_DATE.isoformat(),
        "created_at": _utc(created_at or datetime.now(timezone.utc)).isoformat(),
        "immutable": True,
        "provider_calls_authorized": False,
        "consumer_change_authorized": False,
        "engine_commit": engine_commit,
        "engines": {name: _engine_file_record(name) for name in ("v2", "v3")},
        "harness": _harness_file_record(),
        "expected_counts": dict(EXPECTED_COUNTS),
        "snapshots": records,
        "macro_packages": macro_packages,
        "accepted_v2_shadow_output_sha256": shadow_output_hashes,
        "comparison_ruler": "internal_tp_vs_consensus",
    }
    payload["manifest_sha256"] = manifest_hash(payload)
    return payload


def validate_manifest(
    manifest: Mapping[str, Any], loader: SnapshotLoader,
) -> dict[tuple[str, str], dict[str, Any]]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestValidationError("Unsupported A/B manifest schema")
    if manifest.get("as_of") != AB_AS_OF.isoformat():
        raise ManifestValidationError("A/B manifest as_of mismatch")
    if manifest.get("evaluation_date") != AB_EVALUATION_DATE.isoformat():
        raise ManifestValidationError("A/B manifest evaluation date mismatch")
    if manifest.get("immutable") is not True:
        raise ManifestValidationError("A/B manifest must be immutable")
    if manifest.get("manifest_sha256") != manifest_hash(manifest):
        raise ManifestValidationError("A/B manifest self-hash mismatch")
    if manifest.get("expected_counts") != EXPECTED_COUNTS:
        raise ManifestValidationError("A/B manifest expected counts changed")
    if manifest.get("provider_calls_authorized") is not False:
        raise ManifestValidationError("A/B manifest must prohibit provider calls")
    if manifest.get("consumer_change_authorized") is not False:
        raise ManifestValidationError("A/B manifest must prohibit consumer changes")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("engine_commit") or "")):
        raise ManifestValidationError("A/B manifest engine commit is invalid")

    engines = manifest.get("engines")
    if not isinstance(engines, dict):
        raise ManifestValidationError("A/B manifest has no engine records")
    for name in ("v2", "v3"):
        expected = engines.get(name)
        if not isinstance(expected, dict) or expected != _engine_file_record(name):
            raise ManifestValidationError(f"{name.upper()} engine file drift")
    if manifest.get("harness") != _harness_file_record():
        raise ManifestValidationError("A/B harness file drift")

    records = manifest.get("snapshots")
    if not isinstance(records, list):
        raise ManifestValidationError("A/B manifest has no snapshot records")
    expected_fixed = {
        (reference.role, reference.market): reference
        for reference in FROZEN_SNAPSHOT_REFERENCES
    }
    loaded: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ManifestValidationError("A/B manifest contains an invalid snapshot record")
        role, market = str(record.get("role")), str(record.get("market"))
        key = (role, market)
        if key in loaded:
            raise ManifestValidationError(f"Duplicate snapshot role {role}/{market}")
        snapshot_id = str(record.get("snapshot_id") or "")
        reference = expected_fixed.get(key)
        if reference is not None and (
            snapshot_id != reference.snapshot_id
            or record.get("analysis_type") != reference.analysis_type
            or record.get("entity_key") != reference.entity_key
            or record.get("published_at") != _utc(reference.published_at).isoformat()
        ):
            raise ManifestValidationError(f"Frozen snapshot reference changed: {role}/{market}")
        snapshot = _require_snapshot(
            loader,
            snapshot_id,
            analysis_type=str(record.get("analysis_type")),
            entity_key=str(record.get("entity_key")),
            published_at=datetime.fromisoformat(str(record.get("published_at"))),
        )
        if canonical_sha256(_snapshot_payload(snapshot)) != record.get("snapshot_sha256"):
            raise ManifestValidationError(f"Frozen snapshot hash mismatch: {role}/{market}")
        loaded[key] = snapshot
    required = set(expected_fixed) | {("selic_macro", "B3"), ("treasury_macro", "US")}
    if set(loaded) != required:
        raise ManifestValidationError("A/B manifest snapshot set changed")

    for role, market in (("selic_macro", "B3"), ("treasury_macro", "US")):
        package = loaded[(role, market)].get("outputs")
        expected = (manifest.get("macro_packages") or {}).get(role)
        if not isinstance(package, dict) or not isinstance(expected, dict):
            raise ManifestValidationError(f"Missing macro package: {role}")
        if not package_hash_is_valid(package):
            raise ManifestValidationError(f"Macro package hash mismatch: {role}")
        if package.get("payload_sha256") != expected.get("payload_sha256"):
            raise ManifestValidationError(f"Macro payload changed: {role}")
        if package.get("as_of") != AB_AS_OF.isoformat():
            raise ManifestValidationError(f"Macro package as_of changed: {role}")
    validate_us_curve_package(loaded[("treasury_macro", "US")]["outputs"], as_of=AB_AS_OF)
    return loaded


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _rows(snapshot: Mapping[str, Any], market: str) -> list[dict[str, Any]]:
    outputs = snapshot.get("outputs")
    rows = outputs.get("rows") if isinstance(outputs, dict) else None
    return [
        row for row in (rows or [])
        if isinstance(row, dict)
        and row.get("symbol")
        and (market == "B3" or row.get("security_type") == "Stock")
    ]


def _packets(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = snapshot.get("outputs")
    packets = outputs.get("packets") if isinstance(outputs, dict) else None
    return {
        str(symbol): packet
        for symbol, packet in (packets or {}).items()
        if isinstance(packet, dict)
    } if isinstance(packets, dict) else {}


def _chewie_items(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    outputs = snapshot.get("outputs")
    items = outputs.get("items") if isinstance(outputs, dict) else None
    return [item for item in (items or []) if isinstance(item, dict)]


def _multiples_index(
    market: str,
    rows_by_market: Mapping[str, list[dict[str, Any]]],
    chewie_by_market: Mapping[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    source_markets = ("B3",) if market == "B3" else ("NASDAQ", "NYSE")
    index: dict[str, dict[str, Any]] = {}
    for source_market in source_markets:
        for item in chewie_by_market[source_market]:
            symbol = str(item.get("symbol") or "")
            multiples = item.get("multiples") if isinstance(item.get("multiples"), dict) else {}
            profitability = (
                item.get("profitability")
                if isinstance(item.get("profitability"), dict) else {}
            )
            roe_percent = _number(profitability.get("roe_percent"))
            if symbol:
                index[symbol] = {
                    "pe": _number(multiples.get("pe")),
                    "forward_pe": _number(multiples.get("forward_pe")),
                    "ev_ebitda": _number(multiples.get("ev_ebitda")),
                    "price_to_book": _number(multiples.get("price_to_book")),
                    "roe": roe_percent / 100 if roe_percent is not None else None,
                }
    for source_market in source_markets:
        for row in rows_by_market[source_market]:
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            roe = _number(row.get("roe"))
            if roe is None:
                roe_percent = _number(row.get("roe_percent"))
                roe = roe_percent / 100 if roe_percent is not None else None
            index[symbol] = {
                "pe": _number(row.get("pe")),
                "forward_pe": _number(row.get("forward_pe")),
                "ev_ebitda": _number(row.get("ev_ebitda")),
                "price_to_book": _number(row.get("price_to_book")),
                "roe": roe,
            }
    return index


def _sector_medians(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    sectors = sorted({str(row.get("sector") or "") for row in rows if row.get("sector")})
    for sector in sectors:
        values_by_metric: dict[str, float] = {}
        for metric in ("pe", "forward_pe", "ev_ebitda", "price_to_book"):
            values = [
                value
                for row in rows
                if str(row.get("sector") or "") == sector
                and (value := _number(row.get(metric))) is not None
                and value > 0
            ]
            if len(values) >= 5:
                values_by_metric[metric] = median(values)
        output[sector] = values_by_metric
    return output


def _market_context(
    market: str,
    loaded: Mapping[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    rows_by_market = {
        item: _rows(loaded[("universe", item)], item) for item in MARKETS
    }
    packets_by_market = {
        item: _packets(loaded[("v2_data", item)]) for item in MARKETS
    }
    chewie_by_market = {
        item: _chewie_items(loaded[("chewie", item)]) for item in MARKETS
    }
    multiples = _multiples_index(market, rows_by_market, chewie_by_market)
    source_markets = ("B3",) if market == "B3" else ("NASDAQ", "NYSE")
    peer_quality_market = "B3" if market == "B3" else "US"
    quality_packets = _packets(loaded[("peer_quality", peer_quality_market)])
    quality_items: list[dict[str, Any]] = []
    for source_market in source_markets:
        # Target packets win defensively if a malformed closure snapshot ever
        # repeats a target symbol, even though V2.1b defines closure as P - T.
        quality_packets.update(packets_by_market[source_market])
        quality_items.extend(chewie_by_market[source_market])
    quality_index = build_quality_index(quality_packets, quality_items, as_of=AB_AS_OF)
    return {
        "rows": rows_by_market[market],
        "packets": packets_by_market[market],
        "multiples": multiples,
        "multiples_with_quality": attach_quality_to_multiples(multiples, quality_index),
        "quality_index": quality_index,
        "sector_medians": _sector_medians(rows_by_market[market]),
    }


def _peer_symbols(packet: Mapping[str, Any]) -> list[str]:
    return [
        str(peer.get("canonical_symbol") or peer.get("symbol"))
        for peer in packet.get("peers") or []
        if isinstance(peer, dict) and peer.get("symbol")
    ]


def _evaluate_market(
    engine: ValuationV2Engine,
    context: Mapping[str, Any],
    *,
    v3: bool,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    multiples_key = "multiples_with_quality" if v3 else "multiples"
    multiples_index = context[multiples_key]
    for row in context["rows"]:
        symbol = str(row.get("symbol"))
        packet = context["packets"].get(symbol)
        peer_multiples = {
            peer: multiples_index[peer]
            for peer in _peer_symbols(packet or {})
            if peer in multiples_index and peer != symbol
        }
        kwargs: dict[str, Any] = {
            "peer_multiples": peer_multiples,
            "sector_fair_multiples": context["sector_medians"].get(
                str(row.get("sector") or "")
            ),
        }
        if v3:
            kwargs["target_quality"] = context["quality_index"].get(
                canonical_symbol(symbol), {}
            )
        result = engine.evaluate(row, packet, **kwargs)
        if result is not None:
            result["peer_multiples_resolved"] = len(peer_multiples)
            results[symbol] = result
    return results


def _decorate_v2_results(
    results: dict[str, dict[str, Any]],
    rows: Iterable[Mapping[str, Any]],
) -> None:
    rows_by_symbol = {str(row.get("symbol")): row for row in rows}
    for symbol, result in results.items():
        row = rows_by_symbol[symbol]
        final_tp = _number(row.get("our_tp"))
        internal_tp = _number(row.get("internal_tp"))
        if final_tp is None:
            final_tp = internal_tp
        if internal_tp is None:
            internal_tp = final_tp
        consensus = result.get("consensus_tp")
        result["v1_final_tp"] = final_tp
        result["v1_internal_tp"] = internal_tp
        result["v1_final_divergence_vs_consensus"] = (
            round(abs(final_tp / consensus - 1), 4) if final_tp and consensus else None
        )
        result["v1_internal_divergence_vs_consensus"] = (
            round(abs(internal_tp / consensus - 1), 4) if internal_tp and consensus else None
        )


def _v2_outputs_for_rate(
    market: str,
    context: Mapping[str, Any],
    risk_free_rate: float | None,
    *,
    evaluation_date: date,
) -> dict[str, Any]:
    engine = ValuationV2Engine(
        market="B3" if market == "B3" else "US",
        risk_free_rate=risk_free_rate,
        today=evaluation_date,
    )
    results = _evaluate_market(engine, context, v3=False)
    _decorate_v2_results(results, context["rows"])
    return {
        "results": results,
        "summary": ValuationV2ShadowService._summary(list(results.values())),
    }


def _b3_rate_candidates(accepted: Mapping[str, Any]) -> list[float]:
    results = accepted.get("results") if isinstance(accepted.get("results"), dict) else {}
    rounded_rates = {
        _number(item.get("risk_free_rate"))
        for item in results.values()
        if isinstance(item, dict) and _number(item.get("risk_free_rate")) is not None
    }
    if len(rounded_rates) != 1:
        raise V2ReproductionError("Frozen B3 shadow has inconsistent risk-free rates")
    center = float(next(iter(rounded_rates)))
    offsets = [0]
    for step in range(1, 502):
        offsets.extend((step, -step))
    return [center + offset / 10_000_000 for offset in offsets]


def reproduce_v2(
    market: str,
    context: Mapping[str, Any],
    accepted_outputs: Mapping[str, Any],
    *,
    evaluation_date: date,
) -> tuple[dict[str, Any], float | None]:
    accepted_hash = v2_output_sha256(accepted_outputs)
    candidates = (
        _b3_rate_candidates(accepted_outputs)
        if market == "B3" else [None]
    )
    for rate in candidates:
        reproduced = _v2_outputs_for_rate(
            market, context, rate, evaluation_date=evaluation_date
        )
        if v2_output_sha256(reproduced) == accepted_hash:
            return reproduced, rate if market == "B3" else US_RISK_FREE_FALLBACK
    raise V2ReproductionError(
        f"Frozen V2 output did not reproduce byte-for-byte for {market}"
    )


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _rounded_percentile(values: list[float], fraction: float) -> float | None:
    value = _percentile(values, fraction)
    return round(value, 4) if value is not None else None


def _result_metrics(results: Mapping[str, Mapping[str, Any]], *, stage: str) -> dict[str, Any]:
    prefix = "v2" if stage == "v2" else "v3"
    internal_field = f"{prefix}_internal_tp"
    final_field = f"{prefix}_tp"
    internal_abs: list[float] = []
    internal_signed: list[float] = []
    final_abs: list[float] = []
    by_profile: dict[str, dict[str, list[float]]] = {}
    models = Counter()
    attribution = Counter()
    quality_statuses = Counter()
    quality_bases = Counter()
    regime_statuses = Counter()
    beta_zeroed = 0
    largest: list[dict[str, Any]] = []

    for result in results.values():
        consensus = _number(result.get("consensus_tp"))
        internal = _number(result.get(internal_field))
        final = _number(result.get(final_field))
        profile = str(result.get("profile") or "unknown")
        profile_values = by_profile.setdefault(profile, {"internal_abs": [], "internal_signed": []})
        if consensus and consensus > 0 and internal is not None:
            signed = internal / consensus - 1
            internal_signed.append(signed)
            internal_abs.append(abs(signed))
            profile_values["internal_signed"].append(signed)
            profile_values["internal_abs"].append(abs(signed))
            largest.append({
                "symbol": str(result.get("symbol")),
                "profile": profile,
                "internal_divergence": round(abs(signed), 4),
                "internal_signed_bias": round(signed, 4),
                "attribution_model": result.get("attribution_model"),
            })
        if consensus and consensus > 0 and final is not None:
            final_abs.append(abs(final / consensus - 1))
        for model_name, model in (result.get("models") or {}).items():
            models[str(model_name)] += 1
            if isinstance(model, dict):
                regime = model.get("regime_status")
                if regime:
                    regime_statuses[str(regime)] += 1
        attribution[str(result.get("attribution_model") or "none")] += 1
        for audit in (result.get("fair_multiple_audits") or {}).values():
            if not isinstance(audit, dict):
                continue
            status = str(audit.get("quality_adjustment_status") or "missing")
            quality_statuses[status] += 1
            quality_bases[str(audit.get("quality_basis") or "none")] += 1
            beta_zeroed += int(bool(audit.get("quality_beta_zeroed_negative")))
            regime = audit.get("regime_adjustment")
            if isinstance(regime, dict):
                regime_statuses[str(regime.get("regime_status") or "missing")] += 1

    return {
        "evaluated": len(results),
        "with_consensus": len(internal_abs),
        "internal_divergence_p50": _rounded_percentile(internal_abs, 0.50),
        "internal_divergence_p90": _rounded_percentile(internal_abs, 0.90),
        "internal_signed_bias_median": (
            round(median(internal_signed), 4) if internal_signed else None
        ),
        "final_divergence_p50": _rounded_percentile(final_abs, 0.50),
        "final_divergence_p90": _rounded_percentile(final_abs, 0.90),
        "low_conviction": sum(bool(item.get("low_conviction")) for item in results.values()),
        "low_conviction_rate": (
            round(sum(bool(item.get("low_conviction")) for item in results.values()) / len(results), 4)
            if results else None
        ),
        "by_profile": {
            profile: {
                "count": len(values["internal_abs"]),
                "internal_divergence_p50": _rounded_percentile(values["internal_abs"], 0.50),
                "internal_divergence_p90": _rounded_percentile(values["internal_abs"], 0.90),
                "internal_signed_bias_median": (
                    round(median(values["internal_signed"]), 4)
                    if values["internal_signed"] else None
                ),
            }
            for profile, values in sorted(by_profile.items())
        },
        "model_availability": dict(sorted(models.items())),
        "attribution_models": dict(sorted(attribution.items())),
        "largest_internal_divergences": sorted(
            largest,
            key=lambda item: (-float(item["internal_divergence"]), str(item["symbol"])),
        )[:15],
        "quality_adjustment_statuses": dict(sorted(quality_statuses.items())),
        "quality_bases": dict(sorted(quality_bases.items())),
        "quality_beta_zeroed_negative": beta_zeroed,
        "regime_statuses": dict(sorted(regime_statuses.items())),
    }


def _stage_deltas(
    stage_metrics: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, dict[str, dict[str, float | None]]]:
    comparisons = (
        ("v2_to_v3_1", "v2", "v3_1_quality"),
        ("v3_1_to_v3_1_plus_v3_2", "v3_1_quality", "v3_1_plus_v3_2"),
        ("v3_1_plus_v3_2_to_full", "v3_1_plus_v3_2", "v3_full"),
        ("v2_to_full", "v2", "v3_full"),
    )
    output: dict[str, dict[str, dict[str, float | None]]] = {}
    for label, before, after in comparisons:
        output[label] = {}
        for market in MARKETS:
            output[label][market] = {}
            for metric in (
                "internal_divergence_p50",
                "internal_divergence_p90",
                "internal_signed_bias_median",
                "final_divergence_p50",
                "final_divergence_p90",
                "low_conviction_rate",
            ):
                old = _number(stage_metrics[before][market].get(metric))
                new = _number(stage_metrics[after][market].get(metric))
                output[label][market][f"{metric}_delta"] = (
                    round(new - old, 4) if old is not None and new is not None else None
                )
    return output


def _watchlist_report(stages: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for role, market, symbol in WATCHLIST:
        item: dict[str, Any] = {"role": role, "market": market, "symbol": symbol, "stages": {}}
        for stage, by_market in stages.items():
            result = by_market.get(market, {}).get(symbol)
            if result is None:
                item["stages"][stage] = None
                continue
            prefix = "v2" if stage == "v2" else "v3"
            item["stages"][stage] = {
                "internal_tp": result.get(f"{prefix}_internal_tp"),
                "final_tp": result.get(f"{prefix}_tp"),
                "internal_divergence_vs_consensus": result.get(
                    "internal_divergence_vs_consensus"
                ),
                "final_divergence_vs_consensus": result.get(
                    "final_divergence_vs_consensus"
                ),
                "low_conviction": result.get("low_conviction"),
                "attribution_model": result.get("attribution_model"),
            }
        output.append(item)
    return output


def run_ab(
    manifest: Mapping[str, Any],
    loader: SnapshotLoader,
    *,
    harness_commit: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", harness_commit):
        raise ManifestValidationError("harness_commit must be a full lowercase Git SHA")
    loaded = validate_manifest(manifest, loader)
    evaluation_date = date.fromisoformat(str(manifest["evaluation_date"]))
    contexts = {market: _market_context(market, loaded) for market in MARKETS}

    # This entire gate completes before any V3 engine is constructed.
    v2_by_market: dict[str, dict[str, dict[str, Any]]] = {}
    reproduced_hashes: dict[str, str] = {}
    reproduction_rates: dict[str, float | None] = {}
    for market in MARKETS:
        accepted = loaded[("v2_shadow", market)].get("outputs")
        if not isinstance(accepted, dict):
            raise V2ReproductionError(f"Frozen V2 shadow output missing for {market}")
        if len(contexts[market]["rows"]) != EXPECTED_COUNTS[market]:
            raise V2ReproductionError(f"Frozen universe count changed for {market}")
        reproduced, rate = reproduce_v2(
            market,
            contexts[market],
            accepted,
            evaluation_date=evaluation_date,
        )
        reproduced_hash = v2_output_sha256(reproduced)
        expected_hash = (manifest.get("accepted_v2_shadow_output_sha256") or {}).get(market)
        if reproduced_hash != expected_hash:
            raise V2ReproductionError(f"Manifest V2 baseline hash mismatch for {market}")
        v2_by_market[market] = reproduced["results"]
        reproduced_hashes[market] = reproduced_hash
        reproduction_rates[market] = rate

    selic_package = loaded[("selic_macro", "B3")]["outputs"]
    us_curve_package = loaded[("treasury_macro", "US")]["outputs"]
    stage_results: dict[str, dict[str, dict[str, dict[str, Any]]]] = {
        "v2": v2_by_market,
        "v3_1_quality": {},
        "v3_1_plus_v3_2": {},
        "v3_full": {},
    }
    for market in MARKETS:
        engine_market = "B3" if market == "B3" else "US"
        v2_rate = reproduction_rates[market]
        quality = ValuationV3Engine(
            market=engine_market,
            risk_free_rate=v2_rate,
            today=evaluation_date,
            macro_as_of=AB_AS_OF,
            enable_quality=True,
            enable_selic=False,
            enable_treasury=False,
        )
        stage_results["v3_1_quality"][market] = _evaluate_market(
            quality, contexts[market], v3=True
        )

        quality_selic = ValuationV3Engine(
            market=engine_market,
            risk_free_rate=v2_rate,
            today=evaluation_date,
            macro_as_of=AB_AS_OF,
            selic_package=selic_package if market == "B3" else None,
            enable_quality=True,
            enable_selic=True,
            enable_treasury=False,
        )
        stage_results["v3_1_plus_v3_2"][market] = _evaluate_market(
            quality_selic, contexts[market], v3=True
        )

        full = ValuationV3Engine(
            market=engine_market,
            risk_free_rate=v2_rate,
            today=evaluation_date,
            macro_as_of=AB_AS_OF,
            us_curve_package=us_curve_package if market != "B3" else None,
            selic_package=selic_package if market == "B3" else None,
            enable_quality=True,
            enable_selic=True,
            enable_treasury=market != "B3",
        )
        stage_results["v3_full"][market] = _evaluate_market(
            full, contexts[market], v3=True
        )
        for stage in ("v3_1_quality", "v3_1_plus_v3_2", "v3_full"):
            if len(stage_results[stage][market]) != EXPECTED_COUNTS[market]:
                raise ValuationV3ABError(f"{stage} count changed for {market}")

    stage_metrics = {
        stage: {
            market: _result_metrics(results, stage=stage)
            for market, results in by_market.items()
        }
        for stage, by_market in stage_results.items()
    }
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "as_of": AB_AS_OF.isoformat(),
        "evaluation_date": evaluation_date.isoformat(),
        "generated_at": _utc(generated_at or datetime.now(timezone.utc)).isoformat(),
        "manifest_sha256": manifest["manifest_sha256"],
        "engine_commit": manifest["engine_commit"],
        "harness_commit": harness_commit,
        "harness_file_sha256": manifest["harness"]["file_sha256"],
        "consumer_change_authorized": False,
        "official_tp_replacement_authorized": False,
        "v2_reproduction": {
            "passed": True,
            "output_sha256": reproduced_hashes,
            "risk_free_rates": reproduction_rates,
        },
        "stages": stage_metrics,
        "stage_deltas": _stage_deltas(stage_metrics),
        "watchlist": _watchlist_report(stage_results),
    }
    report["report_sha256"] = canonical_sha256(_without_hash(report, "report_sha256"))
    return report


def write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        _json_ready(payload), sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False
    ).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == encoded:
            return
        raise FileExistsError(f"Immutable artifact already exists: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # A hard link publishes the complete temporary inode atomically and,
            # unlike os.replace(), can never overwrite an existing artifact.
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() == encoded:
                return
            raise FileExistsError(f"Immutable artifact already exists: {path}")
    finally:
        temporary.unlink(missing_ok=True)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ManifestValidationError(f"Expected a JSON object: {path}")
    return payload


def _artifact_sha256(payload: Mapping[str, Any]) -> str | None:
    # Reports also carry the parent manifest hash. Prefer the artifact's own
    # self-hash so operator output never labels the parent as the report hash.
    value = payload.get("report_sha256") or payload.get("manifest_sha256")
    return str(value) if value else None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Frozen Valuation V3 A/B harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    manifest = subparsers.add_parser("build-manifest")
    manifest.add_argument("--selic-snapshot-id", required=True)
    manifest.add_argument("--us-curve-snapshot-id", required=True)
    manifest.add_argument("--engine-commit", required=True)
    manifest.add_argument("--output", type=Path, required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--harness-commit", required=True)
    run.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database = Database(get_settings())
    loader = DatabaseSnapshotLoader(database)
    if args.command == "build-manifest":
        payload = build_manifest(
            loader,
            selic_snapshot_id=args.selic_snapshot_id,
            us_curve_snapshot_id=args.us_curve_snapshot_id,
            engine_commit=args.engine_commit,
        )
    else:
        payload = run_ab(
            _load_json(args.manifest),
            loader,
            harness_commit=args.harness_commit,
        )
    write_immutable_json(args.output, payload)
    print(json.dumps({
        "artifact": str(args.output),
        "sha256": _artifact_sha256(payload),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
