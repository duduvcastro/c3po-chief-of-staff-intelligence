"""The official target price — one for everything (Valuation Engine V3.2 rev 7, §7-bis, Passo 0).

Two structures, both append-only (rev 7, TP-B):

* **prediction records** (`valuation_predictions`): what a producer said for ``(market, symbol)`` at
  ``prediction_instant``, keyed by the producing cycle (the ``analysis_snapshots`` row the producer published).
  Sources coexist (``official_blend_v1`` today; ``official_internal_v1`` after Passo 1; ``v3_2_shadow`` later);
  a re-run is a new cycle, hence a new record — nothing is rewritten.
* **the official selection** (`valuation_official_selection`): one row per *generation* — the set of complete,
  validated cycles, one per market, whose predictions ARE the official TP right now. Switching the source
  (Passo 1/2) or rolling back is the insertion of a new generation; the previous one stays readable.

Passo 0 changes no number: the producer is the current official engine — the canonical universe rows the
screeners already publish (`valuation_universe.outputs.rows`, ``our_tp``), i.e. exactly what the site shows.
What changes is who may compute: **no operational consumer computes, adjusts, calibrates or blends a TP of its
own**; each resolves ``(market, symbol)`` once per request through the current generation and stamps
``generation_id`` / ``tp_source``. Studies and grading read prediction records by source (rev 7, TP-C).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

SOURCE_OFFICIAL = "official_blend_v1"
PREDICTION_SCHEMA = "VALUATION_PREDICTION_V1"
SELECTION_SCHEMA = "VALUATION_OFFICIAL_SELECTION_V1"
MARKETS: tuple[str, ...] = ("B3", "NASDAQ", "NYSE")
UNIVERSE_ANALYSIS = "valuation_universe"
TARGETED_ANALYSIS = "security_valuation"
ACTIVATED_BY = "valuation_official.activate_generation"
_CYCLE_CACHE_LIMIT = 8


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value)).astimezone(timezone.utc)


def market_of_entity(analysis_type: str, entity_key: str) -> str | None:
    """`valuation_universe` entities are ``<MARKET>_UNIVERSE``; targeted B3 valuations are keyed by the ticker."""
    if analysis_type == UNIVERSE_ANALYSIS:
        market = entity_key.removesuffix("_UNIVERSE")
        return market if market in MARKETS else None
    if analysis_type == TARGETED_ANALYSIS:
        return "B3"
    return None


def currency_of(market: str) -> str:
    return "BRL" if market == "B3" else "USD"


def prediction_from_row(row: Mapping[str, Any], *, market: str, scope: str, cycle_id: str, source_version: str,
                        prediction_instant: datetime) -> dict[str, Any] | None:
    """The immutable record of one canonical row. ``None`` when the row carries no usable official TP
    (no symbol, TP or buy-in): such rows are not predictions and never become official."""
    symbol = str(row.get("symbol") or "").strip().upper()
    tp, buy_in = _positive(row.get("our_tp")), _positive(row.get("buy_in"))
    if not symbol or tp is None or buy_in is None:
        return None
    instant = _utc(prediction_instant)
    methods = row.get("methods")
    decomposition = {
        "methods": {str(k): _number(v) for k, v in methods.items()} if isinstance(methods, Mapping) else {},
        "calibration_factor": _number(row.get("calibration_factor")),
        "valuation_profile": row.get("valuation_profile"),
        "risk_score": _number(row.get("risk_score")),
        "valuation_confidence": _number(row.get("valuation_confidence")),
        "method_dispersion_percent": _number(row.get("method_dispersion_percent")),
        "signal_quality": row.get("signal_quality"),
        "tp_validation_status": row.get("tp_validation_status"),
    }
    core = {
        "schema": PREDICTION_SCHEMA,
        "source": SOURCE_OFFICIAL,
        "source_version": str(source_version),
        "market": market,
        "symbol": symbol,
        "scope": scope,
        "session_date": instant.date().isoformat(),
        "cycle_id": str(cycle_id),
        "prediction_instant": instant.isoformat(),
        "tp": tp,
        "buy_in": buy_in,
        "internal_tp": _positive(row.get("internal_tp")),
        "consensus_tp": _positive(row.get("public_consensus_tp")),
        "consensus_source": row.get("consensus_origin_source") or None,
        "analyst_count": int(row["analyst_count"]) if _number(row.get("analyst_count")) is not None else None,
        "consensus_weight_percent": _number(row.get("consensus_weight_percent")),
        "price": _positive(row.get("price")),
        "currency": currency_of(market),
        "decomposition": decomposition,
    }
    return {**core, "id": str(uuid4()), "row_sha256": canonical_sha256(core)}


def cycle_rows(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    outputs = snapshot.get("outputs")
    if not isinstance(outputs, Mapping):
        return []
    if snapshot.get("analysis_type") == UNIVERSE_ANALYSIS:
        rows = outputs.get("rows")
        return [dict(item) for item in rows if isinstance(item, Mapping)] if isinstance(rows, list) else []
    row = outputs.get("row")
    return [dict(row)] if isinstance(row, Mapping) else []


def cycle_validation(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Whether a universe cycle is COMPLETE and VALID enough to be selectable: it finished (it was published),
    it has rows, and every row is a usable prediction (symbol, price, TP, buy-in, internal TP). Coverage against
    the producer's universe size is recorded, never presumed."""
    rows = cycle_rows(snapshot)
    outputs = snapshot.get("outputs") if isinstance(snapshot.get("outputs"), Mapping) else {}
    universe_size = _number(outputs.get("universe_size")) if isinstance(outputs, Mapping) else None
    invalid = [str(row.get("symbol") or "?") for row in rows
               if not (str(row.get("symbol") or "").strip() and _positive(row.get("price")) and _positive(row.get("our_tp"))
                       and _positive(row.get("buy_in")) and _positive(row.get("internal_tp")))]
    return {
        "cycle_id": str(snapshot.get("id")),
        "rows": len(rows),
        "universe_size": universe_size,
        "coverage": (len(rows) / universe_size) if universe_size else None,
        "invalid_rows": invalid[:20],
        "invalid_count": len(invalid),
        "valid": bool(rows) and not invalid,
        "published_at": _utc(snapshot["published_at"]).isoformat() if snapshot.get("published_at") else None,
    }


def record_snapshot(database: Any, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Called by the persistence layer right after a producer publishes a cycle: turns the cycle's rows into
    prediction records and, for universe cycles, activates a new generation when the set of selectable cycles
    changed. Idempotent per cycle (a cycle id is written once)."""
    analysis_type = str(snapshot.get("analysis_type") or "")
    market = market_of_entity(analysis_type, str(snapshot.get("entity_key") or ""))
    if market is None:
        return {"recorded": 0, "generation": None}
    scope = "universe" if analysis_type == UNIVERSE_ANALYSIS else "targeted"
    source_version = _source_version(snapshot)
    instant = _utc(snapshot["published_at"])
    records = [record for record in (prediction_from_row(row, market=market, scope=scope, cycle_id=str(snapshot["id"]),
                                                          source_version=source_version, prediction_instant=instant)
                                     for row in cycle_rows(snapshot)) if record is not None]
    recorded = database.insert_valuation_predictions(records) if records else 0
    generation = activate_generation_if_changed(database, now=instant) if scope == "universe" else None
    return {"recorded": recorded, "generation": generation}


def _source_version(snapshot: Mapping[str, Any]) -> str:
    inputs = snapshot.get("inputs")
    if isinstance(inputs, Mapping) and inputs.get("methodology_version") is not None:
        return str(inputs["methodology_version"])
    return str(snapshot.get("methodology_version_id") or "unknown")


def selectable_cycles(database: Any) -> dict[str, dict[str, Any]]:
    """The latest COMPLETE and VALID universe cycle per market (the candidates for the next generation)."""
    cycles: dict[str, dict[str, Any]] = {}
    for market in MARKETS:
        snapshot = database.latest_analysis_snapshot(UNIVERSE_ANALYSIS, f"{market}_UNIVERSE")
        if not snapshot:
            continue
        validation = cycle_validation(snapshot)
        validation["source_version"] = _source_version(snapshot)
        cycles[market] = validation
    return cycles


def activate_generation_if_changed(database: Any, *, now: datetime, activated_by: str = ACTIVATED_BY) -> dict[str, Any] | None:
    """Insert a new generation when the three markets have selectable cycles and the set differs from the current
    generation's. A market without a valid cycle blocks activation (an incomplete generation is never selectable);
    the current generation stays in force. One INSERT — readers see the previous generation or the new one, never
    a mixture."""
    candidates = selectable_cycles(database)
    valid = {market: item for market, item in candidates.items() if item["valid"]}
    if any(market not in valid for market in MARKETS):
        return None
    cycles = {market: valid[market]["cycle_id"] for market in MARKETS}
    current = database.latest_valuation_official_selection()
    if current and current.get("cycles") == cycles and current.get("source") == SOURCE_OFFICIAL:
        return None
    versions = sorted({valid[market]["source_version"] for market in MARKETS})
    generation = {
        "schema": SELECTION_SCHEMA,
        "generation_id": str(uuid4()),
        "source": SOURCE_OFFICIAL,
        "source_version": "+".join(versions),
        "cycles": cycles,
        "session_dates": {market: (valid[market]["published_at"] or "")[:10] for market in MARKETS},
        "validated_complete": True,
        "activated_at": _utc(now).isoformat(),
        "activated_by": activated_by,
        "previous_generation_id": current.get("generation_id") if current else None,
        "receipt": {"validation": {market: {k: v for k, v in valid[market].items() if k != "invalid_rows"} for market in MARKETS},
                    "changed_markets": [market for market in MARKETS if not current or (current.get("cycles") or {}).get(market) != cycles[market]]},
    }
    database.insert_valuation_official_selection(generation)
    database.drop_official_cycle_cache()
    return generation


def select_generation(database: Any, *, cycles: Mapping[str, str], now: datetime, activated_by: str, reason: str,
                      source: str = SOURCE_OFFICIAL, source_version: str = "rollback") -> dict[str, Any]:
    """Explicit selection (rollback or a mesa-ordered switch): a new generation pointing at complete cycles that
    already exist. Used by Passo 1/2 and by rollback; never by the nightly path."""
    snapshots: dict[str, dict[str, Any]] = {}
    for market in MARKETS:
        snapshot = database.analysis_snapshot_by_id(str(cycles[market]))
        if not snapshot or market_of_entity(str(snapshot.get("analysis_type") or ""), str(snapshot.get("entity_key") or "")) != market:
            raise ValueError(f"cycle for {market} is not a universe cycle: {cycles.get(market)}")
        if not cycle_validation(snapshot)["valid"]:
            raise ValueError(f"cycle for {market} is not complete/valid: {cycles[market]}")
        snapshots[market] = snapshot
    current = database.latest_valuation_official_selection()
    generation = {
        "schema": SELECTION_SCHEMA,
        "generation_id": str(uuid4()),
        "source": source,
        "source_version": source_version,
        "cycles": {market: str(cycles[market]) for market in MARKETS},
        "session_dates": {market: _utc(snapshots[market]["published_at"]).isoformat()[:10] for market in MARKETS},
        "validated_complete": True,
        "activated_at": _utc(now).isoformat(),
        "activated_by": activated_by,
        "previous_generation_id": current.get("generation_id") if current else None,
        "receipt": {"reason": reason},
    }
    database.insert_valuation_official_selection(generation)
    database.drop_official_cycle_cache()
    return generation


def current_generation(database: Any) -> dict[str, Any] | None:
    return database.latest_valuation_official_selection()


def _markets_for(market: str | None) -> tuple[str, ...]:
    if market is None:
        return MARKETS
    clean = market.strip().upper()
    if clean == "US":
        return ("NASDAQ", "NYSE")
    return (clean,) if clean in MARKETS else ()


def _stamp(row: Mapping[str, Any], *, generation: Mapping[str, Any] | None, cycle_id: str, scope: str,
           prediction_instant: Any, market: str) -> dict[str, Any]:
    stamped = dict(row)
    stamped.update({
        "tp_source": SOURCE_OFFICIAL,
        "generation_id": generation.get("generation_id") if generation else None,
        "official_cycle_id": cycle_id,
        "official_scope": scope,
        "official_market": market,
        "prediction_instant": _utc(prediction_instant).isoformat() if prediction_instant else None,
    })
    return stamped


def official_rows(database: Any, market: str, *, generation: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Every official row of one market for a generation (default: the current one), stamped. Empty when there is
    no generation: an operational consumer then has NO TP — it never falls back to computing one."""
    generation = generation or current_generation(database)
    if not generation:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for selected in _markets_for(market):
        cycle_id = (generation.get("cycles") or {}).get(selected)
        if not cycle_id:
            continue
        snapshot = database.official_cycle_snapshot(str(cycle_id))
        if not snapshot:
            continue
        for row in cycle_rows(snapshot):
            symbol = str(row.get("symbol") or "").strip().upper()
            if symbol and _positive(row.get("our_tp")) and _positive(row.get("buy_in")):
                result.setdefault(symbol, _stamp(row, generation=generation, cycle_id=str(cycle_id), scope="universe",
                                                 prediction_instant=snapshot.get("published_at"), market=selected))
    return result


def official_row(database: Any, market: str, symbol: str, *, generation: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """The official row for one symbol: from the generation's universe cycle first; otherwise the latest targeted
    prediction of the official producer (B3 on-demand valuations), whose cycle is read the same way. ``None``
    means "no official TP" — consumers say so instead of computing."""
    clean = symbol.strip().upper().removesuffix(".SA").removesuffix(".US")
    generation = generation or current_generation(database)
    if generation:
        for selected in _markets_for(market):
            cycle_id = (generation.get("cycles") or {}).get(selected)
            snapshot = database.official_cycle_snapshot(str(cycle_id)) if cycle_id else None
            if not snapshot:
                continue
            for row in cycle_rows(snapshot):
                if str(row.get("symbol") or "").strip().upper() == clean and _positive(row.get("our_tp")) and _positive(row.get("buy_in")):
                    return _stamp(row, generation=generation, cycle_id=str(cycle_id), scope="universe",
                                  prediction_instant=snapshot.get("published_at"), market=selected)
    for selected in _markets_for(market):
        prediction = database.latest_valuation_prediction(selected, clean, source=SOURCE_OFFICIAL, scope="targeted")
        if not prediction:
            continue
        snapshot = database.official_cycle_snapshot(str(prediction["cycle_id"]))
        for row in cycle_rows(snapshot or {}):
            if str(row.get("symbol") or "").strip().upper() == clean:
                return _stamp(row, generation=generation, cycle_id=str(prediction["cycle_id"]), scope="targeted",
                              prediction_instant=prediction.get("prediction_instant"), market=selected)
    return None


def official_stamp(database: Any, market: str) -> dict[str, Any]:
    """The stamp every served TP carries (I-TP3): producer, generation and this market's cycle inside it."""
    generation = current_generation(database)
    return {
        "tp_source": SOURCE_OFFICIAL,
        "official_generation_id": generation.get("generation_id") if generation else None,
        "official_cycle_id": (generation.get("cycles") or {}).get(market) if generation else None,
    }
