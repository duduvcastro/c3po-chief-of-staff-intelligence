"""The official target price — one for everything (Valuation Engine V3.2 rev 7, §7-bis, Passo 0).

Two structures, both append-only (rev 7, TP-B):

* **prediction records** (`valuation_predictions`): what a producer said for ``(market, symbol)`` at
  ``prediction_instant``, keyed by the producing cycle (the ``analysis_snapshots`` row the producer published).
  Sources coexist (``official_blend_v1`` today; ``official_internal_v1`` after Passo 1; ``v3_2_shadow`` later);
  a re-run is a new cycle, hence a new record — nothing is rewritten. **The record is what is served**: the
  official TP and buy-in a consumer sees come from the record, never from a snapshot that could be edited.
* **the official selection** (`valuation_official_selection`): one row per *generation* — the set of complete,
  validated cycles, one per market, plus the targeted (on-demand) cycles admitted for symbols outside the universe,
  whose records ARE the official TP right now. Any change of a served number is a NEW generation (new id); switching
  the source (Passo 1/2) or rolling back is the insertion of a new generation; the previous one stays readable.

Passo 0 changes no number: the producer is the current official engine — the canonical universe rows the
screeners already publish (`valuation_universe.outputs.rows`, ``our_tp``), i.e. exactly what the site shows.
What changes is who may compute: **no operational consumer computes, adjusts, calibrates or blends a TP of its
own**; each resolves ONE generation per request/batch and reads every market and symbol through it, stamping
``generation_id`` / ``tp_source`` / ``official_cycle_id``. Studies and grading read prediction records by
source/version/instant (rev 7, TP-C; §10.8).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

SOURCE_OFFICIAL = "official_blend_v1"
PREDICTION_SCHEMA = "VALUATION_PREDICTION_V1"
SELECTION_SCHEMA = "VALUATION_OFFICIAL_SELECTION_V1"
MARKETS: tuple[str, ...] = ("B3", "NASDAQ", "NYSE")
UNIVERSE_ANALYSIS = "valuation_universe"
TARGETED_ANALYSIS = "security_valuation"
ACTIVATED_BY = "valuation_official.activate_generation"
SESSION_ZONES = {"B3": ZoneInfo("America/Sao_Paulo"), "NASDAQ": ZoneInfo("America/New_York"), "NYSE": ZoneInfo("America/New_York")}


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


def session_date_of(market: str, instant: datetime) -> str:
    """The market session a prediction belongs to: the calendar date of the instant in the market's own time zone
    (B3: America/Sao_Paulo; NASDAQ/NYSE: America/New_York) — never the UTC/civil date of the server (rev 7, TP-B)."""
    return _utc(instant).astimezone(SESSION_ZONES[market]).date().isoformat()


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


def _normalized_snapshot(snapshot: Mapping[str, Any], *, analysis_type: str, entity_key: str) -> dict[str, Any]:
    """Storage readers may return a snapshot without ``analysis_type``/``entity_key`` (the PostgreSQL path of
    ``latest_analysis_snapshot`` does): the caller always knows both, so they are re-attached here (F393-1)."""
    return {**snapshot, "analysis_type": analysis_type, "entity_key": entity_key}


def prediction_from_row(row: Mapping[str, Any], *, market: str, scope: str, cycle_id: str, source_version: str,
                        prediction_instant: datetime, source_manifest_sha256: str | None = None) -> dict[str, Any] | None:
    """The immutable record of one canonical row. ``None`` when the row carries no usable official TP
    (no symbol, TP or buy-in): such rows are not predictions and never become official. Every field the contract
    names is present — absent values are explicit ``null``, never dropped (F393-6)."""
    symbol = str(row.get("symbol") or "").strip().upper()
    tp, buy_in = _positive(row.get("our_tp")), _positive(row.get("buy_in"))
    if not symbol or tp is None or buy_in is None:
        return None
    instant = _utc(prediction_instant)
    methods = row.get("methods")
    buy_in_models = row.get("buy_in_models")
    core = {
        "schema": PREDICTION_SCHEMA,
        "source": SOURCE_OFFICIAL,
        "source_version": str(source_version),
        "market": market,
        "symbol": symbol,
        "scope": scope,
        "session_date": session_date_of(market, instant),
        "cycle_id": str(cycle_id),
        "prediction_instant": instant.isoformat(),
        "tp": tp,
        "buy_in": buy_in,
        "internal_tp": _positive(row.get("internal_tp")),
        "bear_tp": _positive(row.get("bear_tp")),
        "bull_tp": _positive(row.get("bull_tp")),
        "consensus_tp": _positive(row.get("public_consensus_tp")),
        "consensus_source": row.get("consensus_origin_source") or None,
        "analyst_count": int(row["analyst_count"]) if _number(row.get("analyst_count")) is not None else None,
        "consensus_weight_percent": _number(row.get("consensus_weight_percent")),
        "price": _positive(row.get("price")),
        "currency": currency_of(market),
        "decomposition": {
            "methods": {str(k): _number(v) for k, v in methods.items()} if isinstance(methods, Mapping) else {},
            "buy_in_models": {str(k): _number(v) for k, v in buy_in_models.items()} if isinstance(buy_in_models, Mapping) else {},
            "weights": {
                "calibration_factor": _number(row.get("calibration_factor")),
                "convergence_weight": _number(row.get("convergence_weight")),
                "consensus_weight_percent": _number(row.get("consensus_weight_percent")),
            },
            "bands": {"bear_tp": _positive(row.get("bear_tp")), "bull_tp": _positive(row.get("bull_tp"))},
            "valuation_profile": row.get("valuation_profile"),
            "risk_score": _number(row.get("risk_score")),
            "valuation_confidence": _number(row.get("valuation_confidence")),
            "method_dispersion_percent": _number(row.get("method_dispersion_percent")),
            "signal_quality": row.get("signal_quality"),
            "status": row.get("status"),
            "tp_validation_status": row.get("tp_validation_status"),
            "provenance": {
                "source_name": row.get("source_name") or row.get("history_source") or None,
                "fundamentals_as_of": row.get("fundamentals_as_of") or None,
                "as_of": str(row.get("as_of")) if row.get("as_of") is not None else None,
                "source_manifest_sha256": source_manifest_sha256,
            },
        },
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


def _usable(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("symbol") or "").strip() and _positive(row.get("price")) and _positive(row.get("our_tp"))
                and _positive(row.get("buy_in")) and _positive(row.get("internal_tp")))


def cycle_validation(snapshot: Mapping[str, Any], *, recorded: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Whether a cycle is COMPLETE, VALID and RECORDED enough to be selectable: it finished (it was published), it has
    rows, every row is a usable prediction (symbol, price, TP, buy-in, internal TP) and — when ``recorded`` is given —
    every usable row already has its immutable prediction record (selection never precedes the records, F393-5).
    Coverage against the producer's universe size is recorded, never presumed."""
    rows = cycle_rows(snapshot)
    outputs = snapshot.get("outputs") if isinstance(snapshot.get("outputs"), Mapping) else {}
    universe_size = _number(outputs.get("universe_size")) if isinstance(outputs, Mapping) else None
    invalid = [str(row.get("symbol") or "?") for row in rows if not _usable(row)]
    unrecorded: list[str] = []
    if recorded is not None:
        unrecorded = [str(row["symbol"]).strip().upper() for row in rows if _usable(row) and str(row["symbol"]).strip().upper() not in recorded]
    return {
        "cycle_id": str(snapshot.get("id")),
        "rows": len(rows),
        "universe_size": universe_size,
        "coverage": (len(rows) / universe_size) if universe_size else None,
        "invalid_rows": invalid[:20],
        "invalid_count": len(invalid),
        "unrecorded_count": len(unrecorded),
        "valid": bool(rows) and not invalid and not unrecorded,
        "published_at": _utc(snapshot["published_at"]).isoformat() if snapshot.get("published_at") else None,
    }


def _source_version(snapshot: Mapping[str, Any]) -> str:
    inputs = snapshot.get("inputs")
    if isinstance(inputs, Mapping) and inputs.get("methodology_version") is not None:
        return str(inputs["methodology_version"])
    return str(snapshot.get("methodology_version_id") or "unknown")


def _manifest_sha(snapshot: Mapping[str, Any]) -> str | None:
    inputs = snapshot.get("inputs")
    if isinstance(inputs, Mapping):
        value = inputs.get("source_manifest_sha256")
        return str(value) if value else None
    return None


def record_snapshot(database: Any, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Called by the persistence layer right after a producer publishes a cycle: turns the cycle's rows into
    prediction records FIRST, then (universe cycles) activates a new generation when the set of selectable cycles
    changed, or (targeted cycles) admits the symbol into a new generation. Idempotent per cycle."""
    analysis_type = str(snapshot.get("analysis_type") or "")
    market = market_of_entity(analysis_type, str(snapshot.get("entity_key") or ""))
    if market is None:
        return {"recorded": 0, "generation": None}
    scope = "universe" if analysis_type == UNIVERSE_ANALYSIS else "targeted"
    instant = _utc(snapshot["published_at"])
    records = [record for record in (prediction_from_row(row, market=market, scope=scope, cycle_id=str(snapshot["id"]),
                                                          source_version=_source_version(snapshot), prediction_instant=instant,
                                                          source_manifest_sha256=_manifest_sha(snapshot))
                                     for row in cycle_rows(snapshot)) if record is not None]
    recorded = database.insert_valuation_predictions(records) if records else 0
    if scope == "universe":
        generation = activate_generation_if_changed(database, now=instant)
    else:
        symbol = str(snapshot.get("entity_key") or "").strip().upper()
        generation = admit_targeted_cycle(database, symbol=symbol, cycle_id=str(snapshot["id"]), now=instant) if records else None
    return {"recorded": recorded, "generation": generation}


def selectable_cycles(database: Any) -> dict[str, dict[str, Any]]:
    """The latest COMPLETE, VALID and RECORDED universe cycle per market (the candidates for the next generation)."""
    cycles: dict[str, dict[str, Any]] = {}
    for market in MARKETS:
        raw = database.latest_analysis_snapshot(UNIVERSE_ANALYSIS, f"{market}_UNIVERSE")
        if not raw:
            continue
        snapshot = _normalized_snapshot(raw, analysis_type=UNIVERSE_ANALYSIS, entity_key=f"{market}_UNIVERSE")
        validation = cycle_validation(snapshot, recorded=database.valuation_predictions_for_cycle(str(snapshot["id"])))
        validation["source_version"] = _source_version(snapshot)
        cycles[market] = validation
    return cycles


def _new_generation(database: Any, *, cycles: Mapping[str, str], targeted: Mapping[str, str], source: str, source_version: str,
                    session_dates: Mapping[str, str], now: datetime, activated_by: str, receipt: Mapping[str, Any]) -> dict[str, Any]:
    current = database.latest_valuation_official_selection()
    generation = {
        "schema": SELECTION_SCHEMA,
        "generation_id": str(uuid4()),
        "source": source,
        "source_version": source_version,
        "cycles": {market: str(cycles[market]) for market in MARKETS},
        "targeted": {str(symbol): str(cycle_id) for symbol, cycle_id in sorted(targeted.items())},
        "session_dates": dict(session_dates),
        "validated_complete": True,
        "activated_at": _utc(now).isoformat(),
        "activated_by": activated_by,
        "previous_generation_id": current.get("generation_id") if current else None,
        "receipt": dict(receipt),
    }
    database.insert_valuation_official_selection(generation)
    database.drop_official_cycle_cache()
    return generation


def activate_generation_if_changed(database: Any, *, now: datetime, activated_by: str = ACTIVATED_BY) -> dict[str, Any] | None:
    """Insert a new generation when the three markets have selectable cycles and the set differs from the current
    generation's. A market without a valid, recorded cycle blocks activation (an incomplete generation is never
    selectable); the current generation stays in force. One INSERT — readers see the previous generation or the new
    one, never a mixture. Targeted admissions of the current generation are carried over."""
    candidates = selectable_cycles(database)
    valid = {market: item for market, item in candidates.items() if item["valid"]}
    if any(market not in valid for market in MARKETS):
        return None
    cycles = {market: valid[market]["cycle_id"] for market in MARKETS}
    current = database.latest_valuation_official_selection()
    if current and current.get("cycles") == cycles and current.get("source") == SOURCE_OFFICIAL:
        return None
    versions = sorted({valid[market]["source_version"] for market in MARKETS})
    return _new_generation(
        database, cycles=cycles, targeted=(current or {}).get("targeted") or {}, source=SOURCE_OFFICIAL, source_version="+".join(versions),
        session_dates={market: session_date_of(market, _utc(valid[market]["published_at"])) for market in MARKETS}, now=now,
        activated_by=activated_by,
        receipt={"validation": {market: {k: v for k, v in valid[market].items() if k != "invalid_rows"} for market in MARKETS},
                 "changed_markets": [market for market in MARKETS if not current or (current.get("cycles") or {}).get(market) != cycles[market]]},
    )


def admit_targeted_cycle(database: Any, *, symbol: str, cycle_id: str, now: datetime, activated_by: str = ACTIVATED_BY) -> dict[str, Any] | None:
    """A targeted (on-demand) valuation published by the official producer for a symbol outside the universe becomes
    official only THROUGH the selection: a new generation with ``targeted[symbol] = cycle_id`` (new id — a new served
    number is a new generation, F393-4). Without a current generation there is nothing to admit into."""
    current = database.latest_valuation_official_selection()
    if not current:
        return None
    if (current.get("targeted") or {}).get(symbol) == cycle_id:
        return None
    return _new_generation(
        database, cycles=current["cycles"], targeted={**(current.get("targeted") or {}), symbol: cycle_id}, source=str(current["source"]),
        source_version=str(current["source_version"]), session_dates=dict(current.get("session_dates") or {}), now=now, activated_by=activated_by,
        receipt={"targeted_admission": {"symbol": symbol, "cycle_id": cycle_id}, "changed_markets": []},
    )


def select_generation(database: Any, *, cycles: Mapping[str, str], now: datetime, activated_by: str, reason: str,
                      targeted: Mapping[str, str] | None = None, source: str = SOURCE_OFFICIAL, source_version: str = "rollback") -> dict[str, Any]:
    """Explicit selection (rollback or a mesa-ordered switch): a new generation pointing at complete, recorded cycles
    that already exist — each market cycle must be a universe cycle OF THAT MARKET, each targeted cycle a targeted
    cycle OF THAT SYMBOL (F393-4). Never used by the nightly path."""
    snapshots: dict[str, dict[str, Any]] = {}
    for market in MARKETS:
        snapshot = database.analysis_snapshot_by_id(str(cycles[market]))
        if not snapshot or snapshot.get("analysis_type") != UNIVERSE_ANALYSIS or market_of_entity(UNIVERSE_ANALYSIS, str(snapshot.get("entity_key") or "")) != market:
            raise ValueError(f"cycle for {market} is not a universe cycle of {market}: {cycles.get(market)}")
        if not cycle_validation(snapshot, recorded=database.valuation_predictions_for_cycle(str(cycles[market])))["valid"]:
            raise ValueError(f"cycle for {market} is not complete/valid/recorded: {cycles[market]}")
        snapshots[market] = snapshot
    for symbol, cycle_id in (targeted or {}).items():
        snapshot = database.analysis_snapshot_by_id(str(cycle_id))
        if not snapshot or snapshot.get("analysis_type") != TARGETED_ANALYSIS or str(snapshot.get("entity_key") or "").upper() != symbol.upper():
            raise ValueError(f"targeted cycle for {symbol} is not a targeted cycle of {symbol}: {cycle_id}")
        if symbol.upper() not in database.valuation_predictions_for_cycle(str(cycle_id)):
            raise ValueError(f"targeted cycle for {symbol} has no prediction record: {cycle_id}")
    return _new_generation(
        database, cycles=cycles, targeted=targeted or {}, source=source, source_version=source_version,
        session_dates={market: session_date_of(market, _utc(snapshots[market]["published_at"])) for market in MARKETS}, now=now,
        activated_by=activated_by, receipt={"reason": reason},
    )


def current_generation(database: Any) -> dict[str, Any] | None:
    return database.latest_valuation_official_selection()


def _markets_for(market: str | None) -> tuple[str, ...]:
    if market is None:
        return MARKETS
    clean = market.strip().upper()
    if clean == "US":
        return ("NASDAQ", "NYSE")
    return (clean,) if clean in MARKETS else ()


def _served(row: Mapping[str, Any], record: Mapping[str, Any], *, generation: Mapping[str, Any], cycle_id: str, scope: str, market: str) -> dict[str, Any]:
    """What a consumer receives: the cycle row for display fields, with the SERVED numbers taken from the immutable
    record (``our_tp``, ``buy_in``) and the full stamp (F393-3, F393-5, F393-6)."""
    stamped = dict(row)
    stamped.update({
        "our_tp": float(record["tp"]),
        "buy_in": float(record["buy_in"]),
        "tp_source": record["source"],
        "tp_source_version": record["source_version"],
        "generation_id": generation["generation_id"],
        "official_cycle_id": cycle_id,
        "official_scope": scope,
        "official_market": market,
        "official_session_date": record["session_date"],
        "prediction_instant": record["prediction_instant"],
        "official_row_sha256": record["row_sha256"],
    })
    return stamped


def official_rows(database: Any, market: str, *, generation: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Every official row of one market for ONE generation (default: the current one — resolve it once per request or
    batch and pass it, so that every market and symbol of that request comes from the same generation). Numbers come
    from the prediction records of the generation's cycle; rows without a record are not served. Empty when there is
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
        records = database.valuation_predictions_for_cycle(str(cycle_id))
        if not snapshot:
            continue
        for row in cycle_rows(snapshot):
            symbol = str(row.get("symbol") or "").strip().upper()
            record = records.get(symbol)
            if symbol and record is not None:
                result.setdefault(symbol, _served(row, record, generation=generation, cycle_id=str(cycle_id), scope="universe", market=selected))
    return result


def official_row(database: Any, market: str, symbol: str, *, generation: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """The official row for one symbol, resolved through ONE generation: from the market's universe cycle, else from
    the targeted cycles the generation admitted for that symbol. Nothing outside the generation is ever served
    (F393-4). ``None`` means "no official TP" — consumers say so instead of computing."""
    clean = symbol.strip().upper().removesuffix(".SA").removesuffix(".US")
    generation = generation or current_generation(database)
    if not generation:
        return None
    for selected in _markets_for(market):
        cycle_id = (generation.get("cycles") or {}).get(selected)
        snapshot = database.official_cycle_snapshot(str(cycle_id)) if cycle_id else None
        if not snapshot:
            continue
        record = database.valuation_predictions_for_cycle(str(cycle_id)).get(clean)
        if record is None:
            continue
        for row in cycle_rows(snapshot):
            if str(row.get("symbol") or "").strip().upper() == clean:
                return _served(row, record, generation=generation, cycle_id=str(cycle_id), scope="universe", market=selected)
    targeted_cycle = (generation.get("targeted") or {}).get(clean)
    if targeted_cycle and "B3" in _markets_for(market):
        snapshot = database.official_cycle_snapshot(str(targeted_cycle))
        record = database.valuation_predictions_for_cycle(str(targeted_cycle)).get(clean)
        if snapshot and record is not None:
            for row in cycle_rows(snapshot):
                if str(row.get("symbol") or "").strip().upper() == clean:
                    return _served(row, record, generation=generation, cycle_id=str(targeted_cycle), scope="targeted", market="B3")
    return None


def official_stamp(database: Any, market: str, *, generation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The stamp every served response carries (I-TP3): producer, generation and this market's cycle inside it.
    Explicit ``None`` values when there is no generation in force."""
    generation = generation or current_generation(database)
    return {
        "tp_source": generation.get("source") if generation else None,
        "official_generation_id": generation.get("generation_id") if generation else None,
        "official_cycle_id": (generation.get("cycles") or {}).get(market) if generation else None,
    }


def prediction_records(database: Any, market: str, symbol: str, *, source: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    """History for studies and grading (rev 7, TP-C; §10.8): the immutable records of one symbol, newest first,
    by source when given — never re-read through the current selection."""
    clean = symbol.strip().upper()
    rows: list[dict[str, Any]] = []
    for selected in _markets_for(market):
        rows.extend(database.list_valuation_predictions(selected, clean, source=source, limit=limit))
    rows.sort(key=lambda record: str(record["prediction_instant"]), reverse=True)
    return rows[:limit]


def official_prediction_snapshot(database: Any, market: str, *, generation: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """The official records of one market for one generation, in the shape the studies adapter reads (``outputs.results``
    keyed by symbol), with ``published_at`` = the generation's activation — the provenance a study needs."""
    generation = generation or current_generation(database)
    if not generation:
        return None
    cycle_id = (generation.get("cycles") or {}).get(market)
    if not cycle_id:
        return None
    records = database.valuation_predictions_for_cycle(str(cycle_id))
    return {
        "id": str(cycle_id),
        "analysis_type": "valuation_official_prediction",
        "entity_key": f"{market}_OFFICIAL",
        "published_at": _utc(generation["activated_at"]),
        "outputs": {"generation_id": generation["generation_id"], "source": generation["source"], "results": {symbol: dict(record) for symbol, record in records.items()}},
    }
