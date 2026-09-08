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
``generation_id`` / ``tp_source`` / ``official_cycle_id`` / session / instant / record hash. Studies and grading read
prediction records by source/version/instant (rev 7, TP-C; §10.8).

Rev 4 (Codex F393-3..7 residuals; pre-review D1–D3, B1–B2, A1, C1, E1, F1):
* a caller that RESOLVED a generation and found none passes ``None`` and is served nothing — only the sentinel
  ``UNRESOLVED`` (the default) makes a reader resolve the current generation itself; there is no raw fallback;
* the session of a prediction is the last COMPLETED session of the market's exchange calendar (a Sunday-night
  or an intraday prediction belongs to the previous session), never the civil date of any zone;
* a targeted cycle is admitted only if it passes the same validation as a universe cycle, and only for a symbol
  the universe cycle of the generation does not already serve;
* activation carries a market's current cycle over when that market has no new valid cycle (one market's bad
  night no longer strips the stamp from the other two); bootstrap still needs every market once;
* activation/admission take the wall clock; a generation chains on ``previous_generation_id`` (UNIQUE in the
  migration) so two concurrent writers cannot both extend the same predecessor; served objects are deep copies.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

logger = logging.getLogger(__name__)

SOURCE_OFFICIAL = "official_blend_v1"
PREDICTION_SCHEMA = "VALUATION_PREDICTION_V1"
SELECTION_SCHEMA = "VALUATION_OFFICIAL_SELECTION_V1"
MARKETS: tuple[str, ...] = ("B3", "NASDAQ", "NYSE")
UNIVERSE_ANALYSIS = "valuation_universe"
TARGETED_ANALYSIS = "security_valuation"
ACTIVATED_BY = "valuation_official.activate_generation"
SESSION_ZONES = {"B3": ZoneInfo("America/Sao_Paulo"), "NASDAQ": ZoneInfo("America/New_York"), "NYSE": ZoneInfo("America/New_York")}
CALENDARS = {"B3": "BVMF", "NASDAQ": "XNYS", "NYSE": "XNYS"}
UNRESOLVED: Any = object()  # "the caller did not resolve a generation": readers resolve the current one themselves
_calendars: dict[str, Any] = {}

ITEM_STAMP_KEYS = {  # served-row key → API item field (F393-6: the full stamp travels with every served number)
    "tp_source": "tp_source", "generation_id": "official_generation_id", "official_cycle_id": "official_cycle_id",
    "tp_source_version": "tp_source_version", "official_session_date": "official_session_date",
    "prediction_instant": "prediction_instant", "official_row_sha256": "official_row_sha256",
}


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
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _calendar(market: str) -> Any:
    name = CALENDARS[market]
    if name not in _calendars:
        _calendars[name] = xcals.get_calendar(name)
    return _calendars[name]


def session_date_of(market: str, instant: datetime) -> str:
    """The market session a prediction belongs to: the last COMPLETED session of the market's exchange calendar at
    ``instant`` (close ≤ instant) — B3 on BVMF, NASDAQ/NYSE on XNYS. A prediction published on a Sunday night, on a
    holiday or during the session belongs to the previous session (F393-6); never the civil date of any zone."""
    at = _utc(instant)
    local_day = at.astimezone(SESSION_ZONES[market]).date().isoformat()
    try:
        calendar = _calendar(market)
        session = calendar.date_to_session(local_day, direction="previous")
        if _utc(calendar.session_close(session).to_pydatetime()) > at:
            session = calendar.previous_session(session)
        return session.date().isoformat()
    except Exception as error:  # outside the calendar's range (decades away): declared, never silent
        logger.warning("session_date_of(%s, %s): calendar unavailable (%s); civil date of the market zone used", market, at.isoformat(), type(error).__name__)
        return local_day


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


def provenance_sha256(rows: list[Mapping[str, Any]]) -> str:
    """The manifest hash a producer records with its cycle (E1): the provenance of every row it published (symbol,
    source, fundamentals date, quote instant), canonical and sorted — what a re-execution must reproduce."""
    manifest = sorted(
        [str(row.get("symbol") or "").strip().upper(), str(row.get("source_name") or row.get("history_source") or ""),
         str(row.get("fundamentals_as_of") or ""), str(row.get("as_of") or "")]
        for row in rows if isinstance(row, Mapping) and row.get("symbol")
    )
    return canonical_sha256(manifest)


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
            "consensus": {
                "tp": _positive(row.get("public_consensus_tp")),
                "source": row.get("consensus_origin_source") or None,
                "analyst_count": int(row["analyst_count"]) if _number(row.get("analyst_count")) is not None else None,
                "as_of": str(row.get("consensus_as_of")) if row.get("consensus_as_of") is not None else None,
                "gap_percent": _number(row.get("consensus_gap_percent")),
            },
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
    Coverage against the producer's universe size is recorded, never presumed. The same rule admits targeted cycles."""
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


def record_snapshot(database: Any, snapshot: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Called by the persistence layer right after a producer publishes a cycle: turns the cycle's rows into
    prediction records FIRST, then (universe cycles) activates a new generation when the set of selectable cycles
    changed, or (targeted cycles) admits the symbol into a new generation. Idempotent per cycle. The activation
    instant is the wall clock (``now``), not the cycle's ``published_at``: generations are ordered by when they were
    activated, and a cycle whose basis instant is older than the current generation still activates (D3)."""
    analysis_type = str(snapshot.get("analysis_type") or "")
    market = market_of_entity(analysis_type, str(snapshot.get("entity_key") or ""))
    if market is None:
        return {"recorded": 0, "generation": None}
    scope = "universe" if analysis_type == UNIVERSE_ANALYSIS else "targeted"
    instant = _utc(snapshot["published_at"])
    activation_now = _utc(now) if now is not None else datetime.now(timezone.utc)
    records = [record for record in (prediction_from_row(row, market=market, scope=scope, cycle_id=str(snapshot["id"]),
                                                          source_version=_source_version(snapshot), prediction_instant=instant,
                                                          source_manifest_sha256=_manifest_sha(snapshot))
                                     for row in cycle_rows(snapshot)) if record is not None]
    recorded = database.insert_valuation_predictions(records) if records else 0
    if scope == "universe":
        generation = activate_generation_if_changed(database, now=activation_now)
    else:
        symbol = str(snapshot.get("entity_key") or "").strip().upper()
        generation = admit_targeted_cycle(database, symbol=symbol, cycle_id=str(snapshot["id"]), now=activation_now) if records else None
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
                    session_dates: Mapping[str, str], now: datetime, activated_by: str, receipt: Mapping[str, Any],
                    strict: bool = False) -> dict[str, Any] | None:
    """One INSERT chained on the current generation. A clock earlier than the current activation (D3) or a chain
    conflict (another writer extended the same predecessor first, B2) is refused: ``ValueError`` on the explicit path
    (``strict``), ``None`` on the automatic one — the next pass re-reads and retries; nothing is ever half-written."""
    from .database import SelectionConflict  # the storage layer raises it on the UNIQUE previous_generation_id
    current = database.latest_valuation_official_selection()
    activated_at = _utc(now)
    if current and activated_at < _utc(current["activated_at"]):
        message = f"activation clock {activated_at.isoformat()} is earlier than the current generation ({current['activated_at']})"
        if strict:
            raise ValueError(message)
        logger.warning("valuation_official: %s — generation not activated", message)
        return None
    generation = {
        "schema": SELECTION_SCHEMA,
        "generation_id": str(uuid4()),
        "source": source,
        "source_version": source_version,
        "cycles": {market: str(cycles[market]) for market in MARKETS},
        "targeted": {str(symbol): str(cycle_id) for symbol, cycle_id in sorted(targeted.items())},
        "session_dates": dict(session_dates),
        "validated_complete": True,
        "activated_at": activated_at.isoformat(),
        "activated_by": activated_by,
        "previous_generation_id": current.get("generation_id") if current else None,
        "receipt": dict(receipt),
    }
    try:
        database.insert_valuation_official_selection(generation)
    except SelectionConflict as error:
        if strict:
            raise ValueError(f"selection conflict: {error}") from error
        logger.warning("valuation_official: chain conflict on %s — generation not activated", generation["previous_generation_id"])
        return None
    database.drop_official_cycle_cache()
    return generation


def activate_generation_if_changed(database: Any, *, now: datetime, activated_by: str = ACTIVATED_BY) -> dict[str, Any] | None:
    """Insert a new generation when the set of official cycles changed. A market with a new COMPLETE, VALID, RECORDED
    cycle contributes it; a market without one keeps the cycle of the current generation (carried over, recorded in
    the receipt, B1) — so one market's bad night never strips the other two of their official stamp. Bootstrap (no
    generation yet) still requires every market to have a valid cycle: an incomplete generation is never selectable.
    One INSERT — readers see the previous generation or the new one, never a mixture. Targeted admissions of the
    current generation are carried over; a chain conflict is retried once."""
    for _attempt in range(2):
        candidates = selectable_cycles(database)
        current = database.latest_valuation_official_selection()
        cycles: dict[str, str] = {}
        versions: dict[str, str] = {}
        carried: list[str] = []
        session_dates: dict[str, str] = {}
        for market in MARKETS:
            item = candidates.get(market)
            if item and item["valid"]:
                cycles[market] = str(item["cycle_id"])
                versions[market] = str(item["source_version"])
                session_dates[market] = session_date_of(market, _utc(item["published_at"]))
            elif current and (current.get("cycles") or {}).get(market):
                cycles[market] = str(current["cycles"][market])
                carried_snapshot = database.official_cycle_snapshot(cycles[market])
                versions[market] = _source_version(carried_snapshot) if carried_snapshot else "unknown"
                session_dates[market] = str((current.get("session_dates") or {}).get(market) or "")
                carried.append(market)
            else:
                logger.warning("valuation_official: %s has no valid recorded cycle and no generation to carry — nothing activated", market)
                return None
        if current and current.get("cycles") == cycles and current.get("source") == SOURCE_OFFICIAL:
            return None
        generation = _new_generation(
            database, cycles=cycles, targeted=(current or {}).get("targeted") or {}, source=SOURCE_OFFICIAL,
            source_version="+".join(sorted(set(versions.values()))), session_dates=session_dates, now=now, activated_by=activated_by,
            receipt={"validation": {market: {k: v for k, v in candidates[market].items() if k != "invalid_rows"} for market in MARKETS if market in candidates},
                     "changed_markets": [market for market in MARKETS if not current or (current.get("cycles") or {}).get(market) != cycles[market]],
                     "carried_markets": carried, "versions": versions},
        )
        if generation is not None:
            return generation
    return None


def admit_targeted_cycle(database: Any, *, symbol: str, cycle_id: str, now: datetime, activated_by: str = ACTIVATED_BY) -> dict[str, Any] | None:
    """A targeted (on-demand) valuation published by the official producer for a symbol outside the universe becomes
    official only THROUGH the selection: a new generation with ``targeted[symbol] = cycle_id`` (new id — a new served
    number is a new generation, F393-4). The cycle must pass the SAME validation as a universe cycle (a row with
    ``price = 0`` or no ``internal_tp`` is never admitted); a symbol the universe cycle already serves is not admitted
    (the universe answers first, so the admission would never be read, A1). Without a current generation there is
    nothing to admit into. A chain conflict is retried once."""
    clean = symbol.strip().upper()
    snapshot = database.official_cycle_snapshot(str(cycle_id))
    if not snapshot or snapshot.get("analysis_type") != TARGETED_ANALYSIS:
        return None
    validation = cycle_validation(snapshot, recorded=database.valuation_predictions_for_cycle(str(cycle_id)))
    if not validation["valid"] or clean not in database.valuation_predictions_for_cycle(str(cycle_id)):
        logger.warning("valuation_official: targeted cycle %s for %s refused: %s", cycle_id, clean, {k: validation[k] for k in ("invalid_count", "unrecorded_count", "rows")})
        return None
    for _attempt in range(2):
        current = database.latest_valuation_official_selection()
        if not current:
            return None
        if (current.get("targeted") or {}).get(clean) == str(cycle_id):
            return None
        universe_cycle = (current.get("cycles") or {}).get("B3")
        if universe_cycle and clean in database.valuation_predictions_for_cycle(str(universe_cycle)):
            return None
        generation = _new_generation(
            database, cycles=current["cycles"], targeted={**(current.get("targeted") or {}), clean: str(cycle_id)}, source=str(current["source"]),
            source_version=str(current["source_version"]), session_dates=dict(current.get("session_dates") or {}), now=now, activated_by=activated_by,
            receipt={"targeted_admission": {"symbol": clean, "cycle_id": str(cycle_id), "validation": {k: v for k, v in validation.items() if k != "invalid_rows"}},
                     "changed_markets": []},
        )
        if generation is not None:
            return generation
    return None


def select_generation(database: Any, *, cycles: Mapping[str, str], now: datetime, activated_by: str, reason: str,
                      targeted: Mapping[str, str] | None = None, source: str = SOURCE_OFFICIAL, source_version: str = "rollback") -> dict[str, Any]:
    """Explicit selection (rollback or a mesa-ordered switch): a new generation pointing at complete, recorded cycles
    that already exist — each market cycle must be a universe cycle OF THAT MARKET, each targeted cycle a targeted
    cycle OF THAT SYMBOL (F393-4). Every market must be named (F1). Never used by the nightly path."""
    missing = [market for market in MARKETS if market not in cycles]
    if missing:
        raise ValueError(f"cycles must name every market; missing: {', '.join(missing)}")
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
    generation = _new_generation(
        database, cycles=cycles, targeted=targeted or {}, source=source, source_version=source_version,
        session_dates={market: session_date_of(market, _utc(snapshots[market]["published_at"])) for market in MARKETS}, now=now,
        activated_by=activated_by, receipt={"reason": reason}, strict=True,
    )
    assert generation is not None  # strict mode raises instead of returning None
    return generation


def current_generation(database: Any) -> dict[str, Any] | None:
    return database.latest_valuation_official_selection()


def generation_at(database: Any, instant: datetime) -> dict[str, Any] | None:
    """The generation that was in force at ``instant`` (the latest activated at or before it) — what a study or a
    replay of a past decision must read, never the current one (F393-7)."""
    return database.valuation_official_selection_at(_utc(instant))


def _resolve(database: Any, generation: Any) -> Mapping[str, Any] | None:
    """``UNRESOLVED`` → the current generation; ``None`` → the caller resolved and found none: serve NOTHING (F393-3)."""
    if generation is UNRESOLVED:
        return current_generation(database)
    return generation


def _markets_for(market: str | None) -> tuple[str, ...]:
    if market is None:
        return MARKETS
    clean = market.strip().upper()
    if clean == "US":
        return ("NASDAQ", "NYSE")
    return (clean,) if clean in MARKETS else ()


def _served(row: Mapping[str, Any], record: Mapping[str, Any], *, generation: Mapping[str, Any], cycle_id: str, scope: str, market: str) -> dict[str, Any]:
    """What a consumer receives: a DEEP COPY of the cycle row for display fields, with the SERVED numbers taken from
    the immutable record (``our_tp``, ``buy_in``) and the full stamp (F393-3, F393-5, F393-6). Mutating the result
    never reaches a cache or a record."""
    stamped = copy.deepcopy(dict(row))
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


def item_stamp(row: Mapping[str, Any] | None) -> dict[str, Any]:
    """The per-item stamp for API models (F393-6): every key explicit, ``None`` when the row is not official."""
    source = row or {}
    return {field: source.get(key) for key, field in ITEM_STAMP_KEYS.items()}


def official_rows(database: Any, market: str, *, generation: Any = UNRESOLVED) -> dict[str, dict[str, Any]]:
    """Every official row of one market for ONE generation (default: the current one — resolve it once per request or
    batch and pass it, so that every market and symbol of that request comes from the same generation; pass ``None``
    when you resolved and found none: nothing is served). Enumeration comes from the RECORDS of the generation's
    cycle (the identity), the display fields from the cycle row of the same symbol; a record whose row vanished from a
    mutated snapshot is not served and is logged. Empty when there is no generation: an operational consumer then
    has NO TP — it never falls back to computing or to a raw snapshot."""
    resolved = _resolve(database, generation)
    if not resolved:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for selected in _markets_for(market):
        cycle_id = (resolved.get("cycles") or {}).get(selected)
        if not cycle_id:
            continue
        snapshot = database.official_cycle_snapshot(str(cycle_id))
        if not snapshot:
            continue
        records = database.valuation_predictions_for_cycle(str(cycle_id))
        rows_by_symbol = {str(row.get("symbol") or "").strip().upper(): row for row in cycle_rows(snapshot)}
        for symbol, record in records.items():
            row = rows_by_symbol.get(symbol)
            if row is None:
                logger.warning("valuation_official: record %s/%s of cycle %s has no display row — not served", selected, symbol, cycle_id)
                continue
            result.setdefault(symbol, _served(row, record, generation=resolved, cycle_id=str(cycle_id), scope="universe", market=selected))
    return result


def official_row(database: Any, market: str, symbol: str, *, generation: Any = UNRESOLVED) -> dict[str, Any] | None:
    """The official row for one symbol, resolved through ONE generation: from the market's universe cycle, else from
    the targeted cycles the generation admitted for that symbol. Nothing outside the generation is ever served
    (F393-4). ``None`` means "no official TP" — consumers say so instead of computing."""
    clean = symbol.strip().upper().removesuffix(".SA").removesuffix(".US")
    resolved = _resolve(database, generation)
    if not resolved:
        return None
    for selected in _markets_for(market):
        cycle_id = (resolved.get("cycles") or {}).get(selected)
        snapshot = database.official_cycle_snapshot(str(cycle_id)) if cycle_id else None
        if not snapshot:
            continue
        record = database.valuation_predictions_for_cycle(str(cycle_id)).get(clean)
        if record is None:
            continue
        for row in cycle_rows(snapshot):
            if str(row.get("symbol") or "").strip().upper() == clean:
                return _served(row, record, generation=resolved, cycle_id=str(cycle_id), scope="universe", market=selected)
    targeted_cycle = (resolved.get("targeted") or {}).get(clean)
    if targeted_cycle and "B3" in _markets_for(market):
        snapshot = database.official_cycle_snapshot(str(targeted_cycle))
        record = database.valuation_predictions_for_cycle(str(targeted_cycle)).get(clean)
        if snapshot and record is not None:
            for row in cycle_rows(snapshot):
                if str(row.get("symbol") or "").strip().upper() == clean:
                    return _served(row, record, generation=resolved, cycle_id=str(targeted_cycle), scope="targeted", market="B3")
    return None


def official_stamp(database: Any, market: str, *, generation: Any = UNRESOLVED) -> dict[str, Any]:
    """The stamp every served response carries (I-TP3): producer, version, generation, this market's cycle inside it
    and its session. Explicit ``None`` values when there is no generation in force."""
    resolved = _resolve(database, generation)
    return {
        "tp_source": resolved.get("source") if resolved else None,
        "tp_source_version": resolved.get("source_version") if resolved else None,
        "official_generation_id": resolved.get("generation_id") if resolved else None,
        "official_cycle_id": (resolved.get("cycles") or {}).get(market) if resolved else None,
        "official_session_date": (resolved.get("session_dates") or {}).get(market) if resolved else None,
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


def official_prediction_snapshot(database: Any, market: str, *, generation: Any = UNRESOLVED) -> dict[str, Any] | None:
    """The official records of one market for one generation, in the shape the studies adapter reads (``outputs.results``
    keyed by symbol), with ``published_at`` = the generation's activation — the provenance a study needs. A study
    replaying a decision passes the generation in force at that decision (``generation_at``), never the current one."""
    resolved = _resolve(database, generation)
    if not resolved:
        return None
    cycle_id = (resolved.get("cycles") or {}).get(market)
    if not cycle_id:
        return None
    records = database.valuation_predictions_for_cycle(str(cycle_id))
    return {
        "id": str(cycle_id),
        "analysis_type": "valuation_official_prediction",
        "entity_key": f"{market}_OFFICIAL",
        "published_at": _utc(resolved["activated_at"]),
        "outputs": {"generation_id": resolved["generation_id"], "source": resolved["source"], "source_version": resolved["source_version"],
                    "session_date": (resolved.get("session_dates") or {}).get(market), "cycle_id": str(cycle_id),
                    "results": {symbol: dict(record) for symbol, record in records.items()}},
    }


def selection_health(database: Any, *, now: datetime) -> dict[str, Any]:
    """The state of the official selection for the health card and the receipts (B1): whether a generation is in
    force, how many sessions old each market's official cycle is, and which markets were carried over."""
    current = current_generation(database)
    if not current:
        return {"status": "none", "generation_id": None, "markets": {}, "detail": "no official generation in force — screeners serve nothing"}
    today = _utc(now)
    markets: dict[str, dict[str, Any]] = {}
    stale: list[str] = []
    for market in MARKETS:
        session = (current.get("session_dates") or {}).get(market)
        expected = session_date_of(market, today)
        age = 0
        if session and session < expected:
            calendar = _calendar(market)
            try:
                age = int(calendar.sessions_distance(session, expected)) - 1
            except Exception:
                age = 1
        markets[market] = {"cycle_id": (current.get("cycles") or {}).get(market), "session_date": session, "expected_session": expected, "sessions_behind": age,
                           "carried": market in ((current.get("receipt") or {}).get("carried_markets") or [])}
        if age >= 2:
            stale.append(market)
    return {"status": "stale" if stale else "ok", "generation_id": current["generation_id"], "activated_at": current["activated_at"], "markets": markets,
            "stale_markets": stale, "detail": f"stale official cycles: {', '.join(stale)}" if stale else "every market within one session"}


def bootstrap_official_selection(database: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """At process start (valuation worker) or by CLI: turn the latest universe cycle of every market into prediction
    records (idempotent — records are unique per cycle) and activate the first generation if all three are valid, so
    that a deploy of Passo 0 does not leave the screeners empty until every market publishes a new cycle."""
    recorded: dict[str, int] = {}
    for market in MARKETS:
        raw = database.latest_analysis_snapshot(UNIVERSE_ANALYSIS, f"{market}_UNIVERSE")
        if raw:
            recorded[market] = record_snapshot(database, _normalized_snapshot(raw, analysis_type=UNIVERSE_ANALYSIS, entity_key=f"{market}_UNIVERSE"), now=now)["recorded"]
    activated = activate_generation_if_changed(database, now=_utc(now) if now is not None else datetime.now(timezone.utc))
    generation = activated or current_generation(database)
    logger.info("valuation_official bootstrap: recorded %s; generation %s", recorded, generation["generation_id"] if generation else None)
    return {"recorded": recorded, "generation": generation}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Official TP selection (V3.2 rev 7 §7-bis): bootstrap records/generation, or show the health.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bootstrap", action="store_true")
    group.add_argument("--health", action="store_true")
    args = parser.parse_args(argv)
    from .config import get_settings
    from .database import Database
    database = Database(get_settings())
    now = datetime.now(timezone.utc)
    result = bootstrap_official_selection(database, now=now) if args.bootstrap else selection_health(database, now=now)
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
