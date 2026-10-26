"""Uncapped, restrictive consumer of the original nightly Decisor.

Only a real official generation is decided. A producer's unselected stage is not
a generation and receives no permission. The original Decisor and its frozen
rules run unchanged through a read-only adapter: migration 052 inserts are
captured in memory, never persisted. Separate ``full_universe_decisions``
snapshots contain those intact records and an additional PIT population guard.
No execution, selection, schedule or real-money path is enabled here.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from . import valuation_decision as decisor
from . import valuation_official as official
from .listed_universe import MARKETS, POPULATION_ANALYSIS, buy_scope_allows, digest, utc

ANALYSIS_TYPE = "full_universe_decisions"
DECISION_SCHEMA = "FULL-UNIVERSE-DECISION-v1"
RUN_SCHEMA = "FULL-UNIVERSE-DECISOR-RUN-v1"
PIT_SCOPE_UNVERIFIED = "PIT_BUY_POPULATION_UNVERIFIED"
PIT_SCOPE_NO_LONGER_VALID = "PIT_BUY_POPULATION_NO_LONGER_VALID"
SOURCE_CHANGED = "FULL_UNIVERSE_TP_SOURCE_CHANGED"
ARTIFACTS_UNATTESTED = "PIT_BUY_ARTIFACTS_UNATTESTED"
ArtifactVerifier = Callable[[Mapping[str, Any], Mapping[str, Any], datetime], Mapping[str, Any] | None]


class _SelectConnection:
    """The original readers need only SELECT, including table-existence reads."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def execute(self, query: str, parameters: Any = None) -> Any:
        if not isinstance(query, str) or not query.lstrip().upper().startswith("SELECT "):
            raise ValueError("the Decisor capture connection permits SELECT only")
        if ";" in query:
            raise ValueError("multiple SQL statements are not allowed in a capture")
        return self._connection.execute(query, parameters)


class _CaptureDatabase:
    """Expose the original run's specific read APIs and intercept its one insert.

    No write API of the real Database is delegated. Memory-only reader caches are
    copied, so a reader cannot mutate the real store through an exposed list.
    """

    _READS = frozenset({
        "analysis_snapshot_at_or_before", "analysis_snapshots_published_between",
        "official_cycle_snapshot", "valuation_predictions_for_cycle",
        "valuation_prediction_record", "valuation_official_selection_at",
        "ingestion_run_completed_at_or_before", "v2_forward_eps_at_or_before",
        "news_sentiment_at",
    })
    _MEMORY = frozenset({"_valuation_tp_staleness", "_statement_filings", "_statement_vintages"})

    def __init__(self, database: Any) -> None:
        self._database = database
        self.captured: list[dict[str, Any]] = []
        for name in self._MEMORY:
            if hasattr(database, name):
                setattr(self, name, copy.deepcopy(getattr(database, name)))

    @property
    def database_url(self) -> Any:
        return self._database.database_url

    def __getattr__(self, name: str) -> Any:
        if name in self._READS:
            return getattr(self._database, name)
        raise AttributeError(f"the Decisor capture does not expose {name}")

    @contextmanager
    def connection(self) -> Iterator[_SelectConnection]:
        with self._database.connection() as connection:
            yield _SelectConnection(connection)

    def insert_valuation_decisions(self, records: list[dict[str, Any]]) -> int:
        self.captured.extend(copy.deepcopy(records))
        return 0  # zero original records persisted; the caller reports capture separately


def _hash(value: Any) -> str:
    return digest(decisor._json_ready(value))


def _causal_snapshot(database: Any, analysis: str, market: str, at: datetime) -> dict[str, Any] | None:
    snapshot = database.analysis_snapshot_at_or_before(analysis, market, at)
    if not isinstance(snapshot, Mapping):
        return None
    try:
        if (not snapshot.get("id") or utc(snapshot["published_at"]) > at
                or not isinstance(snapshot.get("outputs"), Mapping)):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return copy.deepcopy(dict(snapshot))


def _scope_reference(snapshot: Mapping[str, Any] | None, *, with_outputs: bool = False) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    reference = {"snapshot_id": str(snapshot["id"]), "published_at": utc(snapshot["published_at"]).isoformat(),
                 "outputs_sha256": _hash(snapshot["outputs"])}
    if with_outputs:
        reference["outputs"] = copy.deepcopy(snapshot["outputs"])
    return reference


def _source_version(record: Mapping[str, Any]) -> str | None:
    inputs = record.get("inputs")
    tp = inputs.get("tp_record") if isinstance(inputs, Mapping) else None
    value = tp.get("source_version") if isinstance(tp, Mapping) else None
    return value if isinstance(value, str) and value else None


def _attestation_valid(value: Any, scope: Mapping[str, Any] | None, outputs: Mapping[str, Any] | None,
                       original: Mapping[str, Any], at: datetime) -> bool:
    """Validate a trusted verifier's binding, not the scientific artifacts itself.

    A stored mapping with these fields is NOT authority. Every permission read
    must invoke a server-injected verifier again; none is installed by this code.
    """
    if not isinstance(value, Mapping) or scope is None or outputs is None:
        return False
    try:
        bindings = {
            "schema": "PIT-BUY-ARTIFACT-ATTESTATION-v1", "scope_snapshot_id": str(scope["snapshot_id"]),
            "scope_outputs_sha256": scope["outputs_sha256"], "report_sha256": outputs["receipt_sha256"],
            "prereg_sha256": outputs["prereg_sha256"], "population_sha256": outputs["population_sha256"],
            "tp_source_version": _source_version(original), "market": original["market"], "symbol": original["symbol"],
            "tp_row_sha256": original["tp_row_sha256"], "generation_id": original["generation_id"], "as_of": at.isoformat(),
        }
        return bool(all(value.get(key) == expected for key, expected in bindings.items())
                    and re.fullmatch(r"[a-f0-9]{64}", value.get("artifact_manifest_sha256", "")))
    except (KeyError, TypeError, ValueError):
        return False


def _attest(verifier: ArtifactVerifier | None, snapshot: Mapping[str, Any] | None,
            original: Mapping[str, Any], at: datetime) -> dict[str, Any] | None:
    if verifier is None or snapshot is None:
        return None
    if not buy_scope_allows(snapshot["outputs"], market=str(original["market"]), symbol=str(original["symbol"]),
                            tp_source_version=_source_version(original), now=at):
        return None
    # Callback failure can never become permission. Copies protect the immutable
    # original record and the population store from a buggy injected verifier.
    try:
        value = verifier(copy.deepcopy(snapshot), copy.deepcopy(original), at)
        return copy.deepcopy(dict(value)) if _attestation_valid(value, _scope_reference(snapshot), snapshot["outputs"], original, at) else None
    except Exception:
        return None


def _guard(record: Mapping[str, Any], scope: Mapping[str, Any] | None, at: datetime, *,
           artifacts_attested: bool) -> tuple[str, list[str], bool]:
    member = buy_scope_allows(scope, market=str(record["market"]), symbol=str(record["symbol"]),
                              tp_source_version=_source_version(record), now=at)
    allowed = member and artifacts_attested
    verdict = str(record["verdict"])
    reasons = list(record["reason_codes"])
    if verdict == decisor.COMPRA_PERMITIDA and not allowed:
        verdict, reasons = decisor.OBSERVAR, [ARTIFACTS_UNATTESTED if member else PIT_SCOPE_UNVERIFIED]
    return verdict, reasons, allowed


def _guarded_record(original: Mapping[str, Any], snapshot: Mapping[str, Any] | None,
                    verifier: ArtifactVerifier | None) -> dict[str, Any]:
    record = decisor.stored_decision(original)
    if record is None:
        raise ValueError("the original Decisor emitted an unverifiable decision")
    at = utc(record["prediction_instant"])
    scope = _scope_reference(snapshot)
    attestation = _attest(verifier, snapshot, record, at)
    verdict, reasons, allowed = _guard(record, snapshot["outputs"] if snapshot else None, at, artifacts_attested=attestation is not None)
    body = {"schema": DECISION_SCHEMA, "market": record["market"], "symbol": record["symbol"],
            "run_id": record["run_id"], "prediction_instant": record["prediction_instant"],
            "published_at": record["published_at"], "verdict": verdict, "reason_codes": reasons,
            "pit_buy_scope_verified": allowed, "tp_source_version": _source_version(record),
            "population": scope, "artifact_attestation": attestation,
            "original_decision": record, "original_record_persisted": False}
    return {**body, "guarded_row_sha256": _hash(body)}


def stored_guarded_decision(value: Any, *, population: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """Verify both envelopes and the guard's meaning; malformed data is denied."""
    if not isinstance(value, Mapping):
        return None
    try:
        if value.get("schema") != DECISION_SCHEMA or value.get("original_record_persisted") is not False:
            return None
        body = {key: item for key, item in value.items() if key != "guarded_row_sha256"}
        if _hash(body) != value.get("guarded_row_sha256"):
            return None
        original = value["original_decision"]
        if not isinstance(original, Mapping) or decisor.stored_decision(original) is None:
            return None
        if original.get("verdict") not in decisor.VERDICTS or original.get("mode") != decisor.MODE_SHADOW:
            return None
        if any(value[key] != original[key] for key in ("market", "symbol", "run_id", "prediction_instant", "published_at")):
            return None
        if value["market"] not in MARKETS or value["tp_source_version"] != _source_version(original):
            return None
        at = utc(value["prediction_instant"])
        if utc(value["published_at"]) < at:
            return None
        reference = value["population"]
        outputs = None
        if reference is not None:
            # Population bytes are shared once per market run, never copied into
            # every row: storage grows linearly with the complete universe.
            if (not isinstance(reference, Mapping) or not isinstance(population, Mapping)
                    or not isinstance(population.get("outputs"), Mapping)):
                return None
            outputs = population["outputs"]
            metadata = {key: item for key, item in population.items() if key != "outputs"}
            if (dict(reference) != metadata or utc(reference["published_at"]) > at
                    or reference["outputs_sha256"] != _hash(outputs)):
                return None
        elif population is not None:
            return None
        attestation = value["artifact_attestation"]
        if attestation is not None and not _attestation_valid(attestation, reference, outputs, original, at):
            return None
        expected = _guard(original, outputs, at, artifacts_attested=attestation is not None)
        if (value["verdict"], value["reason_codes"], value["pit_buy_scope_verified"]) != expected:
            return None
        return copy.deepcopy(dict(value))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def run_full_universe_decisions(database: Any, *, now: datetime | None = None, record: bool = False,
                                artifact_verifier: ArtifactVerifier | None = None) -> dict[str, Any]:
    """Run the actual original Decisor over every selected name, then restrict.

    ``record`` writes only the new namespace. The original run's internal
    ``write=True`` is required to expose its records to the capture adapter; it
    never reaches Database.insert_valuation_decisions. No producer or generation
    is created. The receipt distinguishes captured records from persisted ones.
    A declared PASS and correctly shaped hashes alone NEVER grant permission.
    No real artifact verifier is supplied here or exposed by the CLI: without a
    trusted server injection all otherwise-permitted members become OBSERVAR.
    """
    at = utc(now or datetime.now(timezone.utc))
    scopes = {market: _causal_snapshot(database, POPULATION_ANALYSIS, market, at) for market in sorted(MARKETS)}
    capture = _CaptureDatabase(database)
    original_receipt = decisor.run_shadow(capture, now=at, write=True, enabled=True)
    # The unchanged core sets written=True after calling its insert, even though
    # our adapter returned zero. Expose a truthful capture receipt with its own
    # hash, retaining only the unmodified core receipt's hash as provenance.
    capture_receipt = {**copy.deepcopy(original_receipt), "status": "captured" if capture.captured else original_receipt["status"],
                       "written": False, "recorded": 0, "captured": len(capture.captured),
                       "upstream_receipt_sha256": original_receipt.get("receipt_sha256")}
    capture_receipt.pop("receipt_sha256", None)
    capture_receipt["receipt_sha256"] = _hash(capture_receipt)
    records = [_guarded_record(item, scopes[str(item["market"])], artifact_verifier) for item in capture.captured]
    published = max([at, datetime.now(timezone.utc), *(utc(item["published_at"]) for item in records)])
    snapshots: dict[str, str] = {}
    if record and records:
        method = database.ensure_methodology_version(
            ANALYSIS_TYPE, 1, {"original_thresholds_sha256": decisor.thresholds_sha256(), "pit_membership_guard": True},
            "Unchanged shadow Decisor with a restrictive PIT population gate; no 052 write or generation activation",
        )
        for market in sorted(MARKETS):
            group = [item for item in records if item["market"] == market]
            if group:
                payload = {"schema": RUN_SCHEMA, "market": market, "run_id": original_receipt["run_id"],
                           "prediction_instant": at.isoformat(), "published_at": published.isoformat(),
                           "population": _scope_reference(scopes[market], with_outputs=True),
                           "record_count": len(group), "records": group}
                payload["payload_sha256"] = _hash(payload)
                snapshots[market] = database.save_analysis_snapshot(
                    ANALYSIS_TYPE, market, method, {"original_run_id": original_receipt["run_id"],
                                                  "original_receipt_sha256": original_receipt.get("receipt_sha256")},
                    payload, published,
                )
    receipt = {"schema": RUN_SCHEMA, "status": "recorded" if snapshots else "dry_run" if records else original_receipt["status"],
               "run_id": original_receipt["run_id"], "generation_id": original_receipt["generation_id"],
               "prediction_instant": at.isoformat(), "published_at": published.isoformat(),
               "captured": len(records), "recorded": sum(1 for item in records if item["market"] in snapshots),
               "written": bool(snapshots), "original_recorded": 0, "original_written": False,
               "artifact_verifier_configured": artifact_verifier is not None,
               "artifact_attestations": sum(item["artifact_attestation"] is not None for item in records),
               "original_capture_receipt_sha256": capture_receipt["receipt_sha256"],
               "original_capture_receipt": capture_receipt, "snapshot_ids": snapshots,
               "markets": {market: {"decided": sum(item["market"] == market for item in records),
                                    "verdicts": {verdict: sum(item["market"] == market and item["verdict"] == verdict for item in records)
                                                 for verdict in decisor.VERDICTS}} for market in sorted(MARKETS)}}
    receipt["receipt_sha256"] = _hash(receipt)
    return receipt


def _stored_run(snapshot: Mapping[str, Any], market: str, at: datetime) -> list[dict[str, Any]]:
    payload = snapshot["outputs"]
    try:
        body = {key: item for key, item in payload.items() if key != "payload_sha256"}
        if (payload.get("schema") != RUN_SCHEMA or payload.get("market") != market
                or _hash(body) != payload.get("payload_sha256")
                or utc(payload["published_at"]) != utc(snapshot["published_at"])
                or utc(payload["published_at"]) > at or utc(payload["prediction_instant"]) > utc(payload["published_at"])):
            return []
        records = payload["records"]
        if not isinstance(records, list) or len(records) != payload["record_count"]:
            return []
        verified = [stored_guarded_decision(item, population=payload["population"]) for item in records]
        if any(item is None for item in verified):
            return []
        clean = [item for item in verified if item is not None]
        if (len({item["symbol"] for item in clean}) != len(clean)
                or any(item["market"] != market or item["run_id"] != payload["run_id"]
                       or utc(item["prediction_instant"]) != utc(payload["prediction_instant"])
                       or utc(item["published_at"]) > utc(payload["published_at"]) for item in clean)):
            return []
        return clean
    except (KeyError, TypeError, ValueError, OverflowError):
        return []


def latest_permissions(database: Any, market: str, symbols: Iterable[str], *, now: datetime | None = None,
                       artifact_verifier: ArtifactVerifier | None = None) -> dict[str, dict[str, Any]]:
    """Read guarded decisions causally and recheck session, TP and PIT scope now.

    This helper can only retain/downgrade a recorded verdict. A later PASS cannot
    upgrade an earlier missing/FAIL population decision. It does not read the
    unguarded migration 052 permission and never computes a replacement TP. An
    injected verifier must attest the current artifacts anew: stored attestations
    and JSON flags are never enough. With the default None no buy is permitted.
    """
    if market not in MARKETS:
        raise ValueError("unknown market")
    at = utc(now or datetime.now(timezone.utc))
    wanted = {item.strip().upper() for item in symbols if isinstance(item, str) and item.strip()}
    if not wanted:
        return {}
    snapshot = _causal_snapshot(database, ANALYSIS_TYPE, market, at)
    if snapshot is None:
        return {}
    records = _stored_run(snapshot, market, at)
    generation = official.generation_at(database, at)
    rows = official.official_rows(database, market, generation=generation) if generation else {}
    scope = _causal_snapshot(database, POPULATION_ANALYSIS, market, at)
    population = scope["outputs"] if scope else None
    generations: dict[str, Any] = {}
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        symbol = record["symbol"]
        if symbol not in wanted:
            continue
        original = record["original_decision"]
        predicted = record["prediction_instant"]
        if predicted not in generations:
            generations[predicted] = official.generation_at(database, utc(predicted))
        prior_generation = generations[predicted]
        if (not prior_generation or str(prior_generation.get("generation_id")) != str(original.get("generation_id"))
                or prior_generation.get("source") != original.get("tp_source")):
            continue
        row = rows.get(symbol)
        if row is None and market == "B3" and generation and symbol in (generation.get("targeted") or {}):
            row = official.official_row(database, market, symbol, generation=generation)
        source_current = bool(row and row.get("tp_source_version") == record["tp_source_version"]
                              and row.get("tp_source") == original["tp_source"])
        view = decisor._view(original, now=at, served_row_sha256=row.get("official_row_sha256") if row else None)
        member = buy_scope_allows(population, market=market, symbol=symbol,
                                  tp_source_version=row.get("tp_source_version") if row else None, now=at)
        attestation = _attest(artifact_verifier, scope, original, at) if source_current else None
        valid_scope = member and attestation is not None
        verdict, reasons = record["verdict"], list(record["reason_codes"])
        if view["effective_verdict"] == decisor.VETO:
            verdict, reasons = decisor.VETO, list(view["effective_reason_codes"])
        elif not source_current:
            verdict, reasons = decisor.VETO, [SOURCE_CHANGED]
        elif verdict == decisor.COMPRA_PERMITIDA and not valid_scope:
            verdict, reasons = decisor.OBSERVAR, [ARTIFACTS_UNATTESTED if member else PIT_SCOPE_NO_LONGER_VALID]
        result[symbol] = {**view, "original_verdict": original["verdict"], "verdict": record["verdict"],
                          "reason_codes": list(record["reason_codes"]), "effective_verdict": verdict,
                          "effective_reason_codes": reasons, "decisor_verdict": verdict,
                          "current": bool(view["current"] and source_current), "tp_source_current": source_current,
                          "pit_buy_scope_verified": valid_scope, "pit_population_member": member,
                          "pit_artifacts_attested": attestation is not None, "buy_permission": verdict == decisor.COMPRA_PERMITIDA,
                          "guarded_row_sha256": record["guarded_row_sha256"], "tp_source_version": record["tp_source_version"],
                          "population_snapshot_id": scope["id"] if scope else None,
                          "guarded_snapshot_id": snapshot["id"], "original_record_persisted": False}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="Record only full_universe_decisions; default is dry capture")
    parser.add_argument("--now", help="Explicit aware run clock; does not backdate the publication clock")
    args = parser.parse_args(argv)
    from .config import get_settings
    from .database import Database
    receipt = run_full_universe_decisions(Database(get_settings()), now=utc(args.now) if args.now else None, record=args.record)
    print(json.dumps(receipt, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
