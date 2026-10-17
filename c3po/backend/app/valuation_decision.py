"""Decisor V1 — the Valuation decides buy / no-buy, in SHADOW (owner's direction of 2026-10-17; migration 052).

Per name per night, one verdict with its reason codes, over the generation of the official selection in force:

* ``COMPRA_PERMITIDA`` — every gate passed: the name may be bought;
* ``OBSERVAR`` — the TP is trustworthy but there is no permission: no margin today (``PRICE_ABOVE_BUY_IN``,
  ``TP_MARGIN_INSUFFICIENT``) or an input of the margin is not measured yet (``E_PROFILE_WARMING_UP``,
  ``E_PROFILE_UNAVAILABLE``, ``MARKET_RATE_UNAVAILABLE``) — no permission while the producers' calibration warms up;
* ``VETO`` — the TP or its data cannot be trusted now (freshness, quality, data defects). A VETO lists every failing
  code, the OBSERVAR codes included: the record is the full picture, the verdict its strictest class.

The rules (every number in ``DecisorThresholds``, the ONE settings block the PREREG freezes):

* TP = the SERVED official row (``valuation_official.official_rows``/``official_row`` through ONE generation): the
  record's ``our_tp``/``buy_in`` — the internal ones when the generation selects ``official_internal_v1``. The decisor
  never computes, adjusts or blends a TP; it reads one and tests it.
* margin: ``ask_or_price <= buy_in`` AND ``tp * (1 - e_profile) >= ask_or_price * (1 + h_market)``. The execution price is
  the ask when the observation carries one (the conservative side), else the price. ``e_profile`` is the MEDIAN ABSOLUTE
  error the producer measured for the name's ``valuation_profile`` (``valuation_calibration/<M>_POWER_MODEL``,
  ``metrics[profile].median_absolute_error_percent``) — only when the calibration is ``active``, its horizon in range, the
  profile has its minimum samples and the snapshot is fresh; ``h_market`` is the market rate over the TP horizon plus the
  declared premium — B3: the Selic the official B3 cycle used (its ``outputs.macro.selic``), else BCB SGS 432; US: the
  13-week T-bill (the R2D2 cash yield package), else the interpolated 5Y — the first FRESH source of the declared order wins
  and is named in the record.
* freshness (VETO): ``tp_stale`` set on the row; the TP's session more than ``max_tp_age_sessions`` behind the last
  completed session; fundamentals older than a quarter + 45 days (or undated); the price moved more than
  ``max_price_move_percent`` since the cut (the TP record's price), or no price.
* quality (VETO): not validated (``tp_validation_status`` when the producer emits it — B3 —, else ``signal_quality`` —
  US); method dispersion above the limit (or unknown); confidence below the limit (or unknown); any data-defect mark.

Records (``valuation_decisions``) carry the discipline of ``valuation_predictions``: two clocks (``prediction_instant`` = the
run's clock; ``published_at`` read immediately before the insert, never before it), the session of the verdict (the last
completed session of the market's calendar — never a civil date; an unavailable calendar records nothing for that
market), the identity of the TP read (generation, source, cycle, row hash, prediction instant), ``inputs`` with the
provenance of every input and its ``inputs_sha256``, ``checks`` with every gate's numbers, the thresholds' hash and the
canonical ``row_sha256`` — recomputed and verified by every reader (``stored_decision``). Append-only; idempotent per
``(run_id, market, symbol)``; ``mode`` is ``shadow`` (the migration admits nothing else).

The nightly phase (``valuation_worker``, flag ``C3PO_VALUATION_DECISOR_SHADOW``, default OFF) runs LAST, after the official
cut and every existing phase, and never writes the selection or any served number. A night is done when the latest run
decided over the generation in force (``last_run_at``): a generation activated later inside the window (a canonical
retry) is decided again. The R2D2 lab reads verdicts by symbol (``latest_verdict``/``latest_verdicts``): it names the
symbols it asks about — nothing here enumerates the names a verdict permits, and receipts are aggregate counts only.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping
from uuid import uuid4

from . import valuation_official as official
from .valuation_official import MARKETS, CalendarUnavailable, canonical_sha256, current_generation, cycle_rows, official_row, official_rows, session_date_of
from .valuation_v3_macro import package_hash_is_valid

logger = logging.getLogger(__name__)

DECISION_SCHEMA = "VALUATION_DECISION_V1"
RUN_SCHEMA = "VALUATION_DECISION_RUN_V1"
DECISOR_VERSION = "valuation_decisor_v1"
MODE_SHADOW = "shadow"  # migration 052: CHECK (mode IN ('shadow')) — a verdict that acts needs a new migration

COMPRA_PERMITIDA = "COMPRA_PERMITIDA"
OBSERVAR = "OBSERVAR"
VETO = "VETO"
VERDICTS: tuple[str, ...] = (COMPRA_PERMITIDA, OBSERVAR, VETO)

ALL_GATES_PASSED = "ALL_GATES_PASSED"
VERDICT_NOT_CURRENT = "VERDICT_NOT_CURRENT"  # the lab helper's downgrade of a verdict decided for another session
VETO_CODES: tuple[str, ...] = (
    "TP_STALE_FLAG", "TP_SESSION_STALE", "FUNDAMENTALS_STALE", "FUNDAMENTALS_DATE_UNKNOWN", "PRICE_UNAVAILABLE", "PRICE_MOVED_SINCE_CUT",
    "NOT_VALIDATED", "METHOD_DISPERSION_HIGH", "METHOD_DISPERSION_UNKNOWN", "CONFIDENCE_LOW", "CONFIDENCE_UNKNOWN", "DATA_DEFECT",
)
OBSERVAR_CODES: tuple[str, ...] = (
    "E_PROFILE_WARMING_UP", "E_PROFILE_UNAVAILABLE", "MARKET_RATE_UNAVAILABLE", "PRICE_ABOVE_BUY_IN", "TP_MARGIN_INSUFFICIENT",
)

RATE_B3_CYCLE_SELIC = "b3_cycle_selic"  # outputs.macro.selic of the generation's B3 universe cycle (the producer's effective Selic)
RATE_BCB_SGS_432 = "bcb_sgs_432"  # valuation_macro_history/B3_SELIC_REGIME (hashed package, dated observations)
RATE_US_TBILL_13W = "us_tbill_13w"  # r2d2_cash_yield_rate/US_TBILL_13_WEEK_COUPON_EQUIVALENT (hashed package)
RATE_US_5Y = "us_5y_interpolated"  # valuation_macro_rates/US_5Y_INTERPOLATED (hashed package)
_RATE_PACKAGES = {
    RATE_BCB_SGS_432: ("valuation_macro_history", "B3_SELIC_REGIME"),
    RATE_US_TBILL_13W: ("r2d2_cash_yield_rate", "US_TBILL_13_WEEK_COUPON_EQUIVALENT"),
    RATE_US_5Y: ("valuation_macro_rates", "US_5Y_INTERPOLATED"),
}


@dataclass(frozen=True)
class DecisorThresholds:
    """The ONE settings block of the decisor — every number a verdict depends on, hashed into every record
    (``thresholds_sha256``). The PREREG freezes it: ``PREREG_THRESHOLDS_SHA256`` is set to its hash by the commit that
    cites the PREREG, and a run under any other block is refused from then on."""
    max_tp_age_sessions: int = 1  # the TP may be at most this many sessions behind the last completed one ("older than 1 session" vetoes)
    fundamentals_quarter_days: int = 92
    fundamentals_grace_days: int = 45  # fundamentals older than a quarter + 45 days veto
    max_price_move_percent: float = 5.0  # |price / cut price - 1| above this since the cut vetoes
    validated_status: str = "validated"
    max_method_dispersion_percent: float = 45.0  # the producers' own MAX_METHOD_DISPERSION / MAX_DISPERSION
    min_valuation_confidence: float = 70.0  # the producers' own MIN_VALUATION_CONFIDENCE / MIN_CONFIDENCE
    data_defect_fields: tuple[str, ...] = ("data_defect", "data_defects")  # a producer mark under any of these (truthy) vetoes
    min_profile_samples: int = 15  # the producers' CALIBRATION_MIN_PROFILE_SAMPLES
    calibration_min_horizon_days: int = 60
    calibration_max_horizon_days: int = 150  # the producers' active window for the observed horizon
    calibration_max_age_days: int = 7  # a calibration snapshot older than this is not a measurement of tonight's producer
    allow_global_error_fallback: bool = False  # a profile below its minimum samples borrows the global error only if True
    b3_rate_sources: tuple[str, ...] = (RATE_B3_CYCLE_SELIC, RATE_BCB_SGS_432)
    us_rate_sources: tuple[str, ...] = (RATE_US_TBILL_13W, RATE_US_5Y)
    market_rate_max_age_days: int = 10
    tp_horizon_years: float = 1.0  # a 12-month TP: h_market = (1 + rate) ** years - 1 + premium
    market_premium: float = 0.0


THRESHOLDS = DecisorThresholds()
PREREG_THRESHOLDS_SHA256: str | None = None  # None until the PREREG freezes the block; then the hash every run must match
_integrity_logged: set[str] = set()  # stored decisions this PROCESS already warned could not be verified: the repeats are INFO


def thresholds_sha256(thresholds: DecisorThresholds = THRESHOLDS) -> str:
    return canonical_sha256(asdict(thresholds))


def _prereg_frozen(thresholds: DecisorThresholds) -> bool:
    """Whether the block is the one the PREREG froze. Before the freeze: ``False`` (recorded in every record). After it,
    a run under another block is refused (``ValueError``) — a frozen study never mixes two rules."""
    if PREREG_THRESHOLDS_SHA256 is None:
        return False
    digest = thresholds_sha256(thresholds)
    if digest != PREREG_THRESHOLDS_SHA256:
        raise ValueError(f"the decisor thresholds ({digest[:12]}…) are not the block the PREREG froze ({PREREG_THRESHOLDS_SHA256[:12]}…): nothing is decided")
    return True


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number + 0.0  # -0.0 → 0.0: JSONB has no signed zero, and the hash must survive the round trip


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _json_ready(value: Any) -> Any:
    """What JSONB stores and gives back, so the hash survives the round trip: ISO instants and dates, finite numbers
    (NaN/inf → null, -0.0 → 0.0), string keys, lists for tuples."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return _number(value) if isinstance(value, float) else value
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return str(value)


def _marked(value: Any) -> bool:
    """A producer mark is set when it is truthy as data: ``True``, a non-empty list/dict, a non-empty text."""
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().lower() not in ("false", "0", "none", "no")
    return bool(value)


def _sessions_behind(market: str, tp_session: str, expected_session: str) -> int:
    """How many sessions the TP's session is behind the last completed session (0 when it IS that session) — the
    exchange calendar of the market (``CalendarUnavailable`` when it cannot answer: the name is not decided)."""
    if tp_session >= expected_session:
        return 0
    try:
        return int(official._calendar(market).sessions_distance(tp_session, expected_session)) - 1
    except Exception as error:
        raise CalendarUnavailable(f"{market} calendar cannot count {tp_session}..{expected_session}: {type(error).__name__}") from error


def fundamentals_age_days(value: Any, reference: date) -> int | None:
    """Days between the fundamentals' date (the first 10 characters, ISO) and ``reference``; ``None`` when undated."""
    text = _text(value)
    if not text:
        return None
    try:
        return max((reference - date.fromisoformat(text[:10])).days, 0)
    except ValueError:
        return None


# ------------------------------------------------------------------ inputs: measured error, market rate, price


def profile_error(database: Any, market: str, profile: str, *, at: datetime, thresholds: DecisorThresholds = THRESHOLDS) -> dict[str, Any]:
    """``e_profile``: the median absolute error the producer measured for ``profile`` in ``market`` — the calibration
    snapshot published at or before ``at`` (causal). ``status`` is ``ok`` (``value`` set), ``warming_up`` (the
    calibration is not active, its horizon is out of range or the profile lacks its minimum samples) or ``unavailable``
    (no snapshot, a stale one, or a producer that does not publish the metric yet). Every field read is named."""
    snapshot = database.analysis_snapshot_at_or_before("valuation_calibration", f"{market}_POWER_MODEL", at)
    base: dict[str, Any] = {"status": "unavailable", "value": None, "profile": profile, "metric": "median_absolute_error_percent",
                            "snapshot_id": None, "published_at": None, "calibration_status": None, "observed_horizon_days": None,
                            "samples": None, "basis": None}
    if not snapshot:
        return {**base, "detail": "no calibration snapshot"}
    published = _utc(snapshot["published_at"])
    outputs = snapshot.get("outputs") if isinstance(snapshot.get("outputs"), Mapping) else {}
    metrics = outputs.get("metrics") if isinstance(outputs.get("metrics"), Mapping) else {}
    horizon = _number(outputs.get("observed_horizon_days"))
    base.update({"snapshot_id": str(snapshot.get("id")), "published_at": published.isoformat(), "calibration_status": outputs.get("status"),
                 "observed_horizon_days": horizon})
    if at - published > timedelta(days=thresholds.calibration_max_age_days):
        return {**base, "detail": f"calibration older than {thresholds.calibration_max_age_days} days"}
    if outputs.get("status") != "active" or horizon is None \
            or not thresholds.calibration_min_horizon_days <= horizon <= thresholds.calibration_max_horizon_days:
        return {**base, "status": "warming_up", "detail": "calibration not active or horizon out of range"}
    basis = profile
    entry = metrics.get(profile) if isinstance(metrics.get(profile), Mapping) else None
    samples = _number((entry or {}).get("samples"))
    if (samples is None or samples < thresholds.min_profile_samples) and thresholds.allow_global_error_fallback:
        basis, entry = "global", metrics.get("global") if isinstance(metrics.get("global"), Mapping) else None
        samples = _number((entry or {}).get("samples"))
    base.update({"samples": int(samples) if samples is not None else None, "basis": basis})
    if samples is None or samples < thresholds.min_profile_samples:
        return {**base, "status": "warming_up", "detail": f"profile below {thresholds.min_profile_samples} samples"}
    measured = _number((entry or {}).get("median_absolute_error_percent"))
    if measured is None or measured < 0:
        return {**base, "detail": "the producer publishes no median_absolute_error_percent for this profile"}
    return {**base, "status": "ok", "value": measured / 100, "detail": None}


def _package_rate(database: Any, source: str, *, at: datetime) -> dict[str, Any]:
    analysis_type, entity_key = _RATE_PACKAGES[source]
    snapshot = database.analysis_snapshot_at_or_before(analysis_type, entity_key, at)
    candidate: dict[str, Any] = {"source": source, "reference": f"{analysis_type}/{entity_key}", "snapshot_id": None, "payload_sha256": None,
                                 "annual_rate": None, "observed_at": None}
    outputs = snapshot.get("outputs") if snapshot and isinstance(snapshot.get("outputs"), Mapping) else None
    if not outputs:
        return {**candidate, "detail": "no package"}
    candidate.update({"snapshot_id": str(snapshot.get("id")), "payload_sha256": outputs.get("payload_sha256")})  # type: ignore[union-attr]
    if not package_hash_is_valid(dict(outputs)):
        return {**candidate, "detail": "package hash does not verify"}
    if source == RATE_BCB_SGS_432:
        observations = [item for item in outputs.get("observations") or [] if isinstance(item, Mapping)
                        and _text(item.get("available_at")) and _utc(item["available_at"]) <= at]
        latest = max(observations, key=lambda item: str(item.get("observation_date"))) if observations else None
        rate, observed = (_positive((latest or {}).get("annual_rate")), _text((latest or {}).get("observation_date")))
    elif source == RATE_US_TBILL_13W:
        rate, observed = _positive(outputs.get("annual_rate")), _text(outputs.get("observation_date"))
    else:
        rate, observed = _positive(outputs.get("interpolated_5y_rate")), _text(outputs.get("as_of"))
    return {**candidate, "annual_rate": rate, "observed_at": observed, "detail": None if rate is not None else "no usable observation"}


def market_rate(database: Any, market: str, *, at: datetime, generation: Mapping[str, Any] | None,
                thresholds: DecisorThresholds = THRESHOLDS) -> dict[str, Any]:
    """``h_market``: the market rate over the TP horizon plus the declared premium, from the FIRST source of the declared
    order (B3: ``b3_rate_sources``; US: ``us_rate_sources``) whose observation is positive and no older than
    ``market_rate_max_age_days`` at ``at``. ``status`` ``ok`` names the source, its reference (snapshot / cycle id,
    package hash), the observation and the annual rate; ``unavailable`` lists what was tried."""
    sources = thresholds.b3_rate_sources if market == "B3" else thresholds.us_rate_sources
    tried: list[dict[str, Any]] = []
    for source in sources:
        if source == RATE_B3_CYCLE_SELIC:
            cycle_id = ((generation or {}).get("cycles") or {}).get("B3")
            snapshot = database.official_cycle_snapshot(str(cycle_id)) if cycle_id else None
            macro = (snapshot.get("outputs") or {}).get("macro") if snapshot and isinstance(snapshot.get("outputs"), Mapping) else None
            candidate = {"source": source, "reference": f"valuation_universe/B3_UNIVERSE#{cycle_id}" if cycle_id else None,
                         "snapshot_id": str(cycle_id) if cycle_id else None, "payload_sha256": None,
                         "annual_rate": _positive((macro or {}).get("selic")) if isinstance(macro, Mapping) else None,
                         "observed_at": _utc(snapshot["published_at"]).isoformat() if snapshot and snapshot.get("published_at") else None}
            candidate["detail"] = None if candidate["annual_rate"] is not None else "the B3 cycle carries no macro.selic"
        elif source in _RATE_PACKAGES:
            candidate = _package_rate(database, source, at=at)
        else:
            candidate = {"source": source, "annual_rate": None, "detail": "unknown rate source"}
        if candidate.get("annual_rate") is not None and candidate.get("observed_at"):
            observed = _utc(candidate["observed_at"]) if "T" in str(candidate["observed_at"]) else \
                datetime.combine(date.fromisoformat(str(candidate["observed_at"])[:10]), datetime.min.time(), tzinfo=timezone.utc)
            if at - observed > timedelta(days=thresholds.market_rate_max_age_days):
                candidate["detail"] = f"observation older than {thresholds.market_rate_max_age_days} days"
            else:
                rate = float(candidate["annual_rate"])
                hurdle = (1 + rate) ** thresholds.tp_horizon_years - 1 + thresholds.market_premium
                return {"status": "ok", **candidate, "h_market": hurdle, "tp_horizon_years": thresholds.tp_horizon_years,
                        "market_premium": thresholds.market_premium, "tried": tried}
        tried.append({key: candidate.get(key) for key in ("source", "reference", "detail")})
    return {"status": "unavailable", "source": None, "annual_rate": None, "h_market": None, "tried": tried}


def _price_observation(row: Mapping[str, Any], *, market: str, symbol: str, quotes: Mapping[tuple[str, str], Mapping[str, Any]] | None,
                       latest_universe: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The price the verdict is taken at: a quote the caller hands over (``quotes[(market, symbol)]``: ``price``, optional
    ``ask``, ``as_of``, ``source``); else the newest universe cycle of the market published AFTER the TP's cut that quotes
    the symbol (the generation may carry an older cycle); else the cut's own price (the TP record's). ``None``: no price."""
    quote = (quotes or {}).get((market, symbol))
    if quote is not None and _positive(quote.get("price")) is not None:
        return {"price": _positive(quote.get("price")), "ask": _positive(quote.get("ask")), "as_of": _text(quote.get("as_of")),
                "source": _text(quote.get("source")) or "quote", "reference": _text(quote.get("reference"))}
    if latest_universe and latest_universe.get("published_at") and str(latest_universe.get("id")) != str(row.get("official_cycle_id")) \
            and _utc(latest_universe["published_at"]) > _utc(row["prediction_instant"]):
        for candidate in cycle_rows({**latest_universe, "analysis_type": official.UNIVERSE_ANALYSIS}):
            if str(candidate.get("symbol") or "").strip().upper() == symbol and _positive(candidate.get("price")) is not None:
                return {"price": _positive(candidate.get("price")), "ask": None, "as_of": _text(candidate.get("as_of")),
                        "source": "latest_universe_cycle", "reference": str(latest_universe.get("id"))}
    price = _positive(row.get("price"))
    if price is None:
        return None
    return {"price": price, "ask": None, "as_of": _text(row.get("as_of")), "source": "official_cut", "reference": _text(row.get("official_cycle_id"))}


# ------------------------------------------------------------------ the verdict (pure)


def decide(row: Mapping[str, Any], *, expected_session: str, tp_sessions_behind: int, price: Mapping[str, Any] | None,
           error: Mapping[str, Any], rate: Mapping[str, Any], thresholds: DecisorThresholds = THRESHOLDS) -> dict[str, Any]:
    """The verdict of ONE served official row — pure: everything it reads is an argument. Returns ``verdict``,
    ``reason_codes`` (every failing gate, in evaluation order; ``[ALL_GATES_PASSED]`` for a permission), ``checks`` (each
    gate's numbers and outcome) and the numbers the record keeps (``price``, ``e_profile``, ``h_market``)."""
    codes: list[str] = []
    checks: dict[str, Any] = {}
    tp_value, buy_in = _positive(row.get("our_tp")), _positive(row.get("buy_in"))

    stale_flag = row.get("tp_stale")
    checks["tp_stale_flag"] = {"pass": not _marked(stale_flag), "value": stale_flag}
    if _marked(stale_flag):
        codes.append("TP_STALE_FLAG")
    checks["tp_session_age"] = {"pass": tp_sessions_behind <= thresholds.max_tp_age_sessions, "sessions_behind": tp_sessions_behind,
                                "limit": thresholds.max_tp_age_sessions, "tp_session": row.get("official_session_date"), "expected_session": expected_session}
    if tp_sessions_behind > thresholds.max_tp_age_sessions:
        codes.append("TP_SESSION_STALE")
    limit_days = thresholds.fundamentals_quarter_days + thresholds.fundamentals_grace_days
    age = fundamentals_age_days(row.get("fundamentals_as_of"), date.fromisoformat(expected_session))
    checks["fundamentals_age"] = {"pass": age is not None and age <= limit_days, "fundamentals_as_of": _text(row.get("fundamentals_as_of")),
                                  "age_days": age, "limit_days": limit_days}
    if age is None:
        codes.append("FUNDAMENTALS_DATE_UNKNOWN")
    elif age > limit_days:
        codes.append("FUNDAMENTALS_STALE")
    cut_price = _positive(row.get("price"))
    observed = _positive((price or {}).get("price"))
    move = abs(observed / cut_price - 1) * 100 if observed is not None and cut_price is not None else None
    checks["price_move"] = {"pass": move is not None and move <= thresholds.max_price_move_percent, "cut_price": cut_price, "price": observed,
                            "move_percent": move, "limit_percent": thresholds.max_price_move_percent, "price_source": (price or {}).get("source")}
    if move is None:
        codes.append("PRICE_UNAVAILABLE")
    elif move > thresholds.max_price_move_percent:
        codes.append("PRICE_MOVED_SINCE_CUT")

    status_field = "tp_validation_status" if row.get("tp_validation_status") is not None else "signal_quality"
    validated = row.get(status_field) == thresholds.validated_status
    checks["validated"] = {"pass": validated, "field": status_field, "value": row.get(status_field)}
    if not validated:
        codes.append("NOT_VALIDATED")
    dispersion = _number(row.get("method_dispersion_percent"))
    checks["method_dispersion"] = {"pass": dispersion is not None and dispersion <= thresholds.max_method_dispersion_percent,
                                   "value": dispersion, "limit": thresholds.max_method_dispersion_percent}
    if dispersion is None:
        codes.append("METHOD_DISPERSION_UNKNOWN")
    elif dispersion > thresholds.max_method_dispersion_percent:
        codes.append("METHOD_DISPERSION_HIGH")
    confidence = _number(row.get("valuation_confidence"))
    checks["confidence"] = {"pass": confidence is not None and confidence >= thresholds.min_valuation_confidence,
                            "value": confidence, "limit": thresholds.min_valuation_confidence}
    if confidence is None:
        codes.append("CONFIDENCE_UNKNOWN")
    elif confidence < thresholds.min_valuation_confidence:
        codes.append("CONFIDENCE_LOW")
    marks = {field: row.get(field) for field in thresholds.data_defect_fields if _marked(row.get(field))}
    checks["data_defects"] = {"pass": not marks, "marks": marks, "fields": list(thresholds.data_defect_fields)}
    if marks:
        codes.append("DATA_DEFECT")

    e_profile = _number(error.get("value")) if error.get("status") == "ok" else None
    if error.get("status") == "warming_up":
        codes.append("E_PROFILE_WARMING_UP")
    elif e_profile is None:
        codes.append("E_PROFILE_UNAVAILABLE")
    h_market = _number(rate.get("h_market")) if rate.get("status") == "ok" else None
    if h_market is None:
        codes.append("MARKET_RATE_UNAVAILABLE")
    ask = _positive((price or {}).get("ask"))
    entry_price = ask if ask is not None else observed
    entry_ok = entry_price is not None and buy_in is not None and entry_price <= buy_in
    checks["entry"] = {"pass": entry_ok if entry_price is not None else None, "entry_price": entry_price, "basis": "ask" if ask is not None else "price",
                       "buy_in": buy_in}
    if entry_price is not None and not entry_ok:
        codes.append("PRICE_ABOVE_BUY_IN")
    margin: dict[str, Any] = {"pass": None, "tp_value": tp_value, "e_profile": e_profile, "h_market": h_market, "tp_after_error": None, "required": None}
    if entry_price is not None and tp_value is not None and e_profile is not None and h_market is not None:
        margin.update({"tp_after_error": tp_value * (1 - e_profile), "required": entry_price * (1 + h_market)})
        margin["pass"] = margin["tp_after_error"] >= margin["required"]
        if not margin["pass"]:
            codes.append("TP_MARGIN_INSUFFICIENT")
    checks["tp_margin"] = margin

    if any(code in VETO_CODES for code in codes):
        verdict = VETO
    elif codes:
        verdict = OBSERVAR
    else:
        verdict, codes = COMPRA_PERMITIDA, [ALL_GATES_PASSED]
    return {"verdict": verdict, "reason_codes": codes, "checks": _json_ready(checks), "price": entry_price, "e_profile": e_profile, "h_market": h_market}


# ------------------------------------------------------------------ the immutable record


def decision_record(*, run_id: str, market: str, symbol: str, session_date: str, prediction_instant: datetime, published_at: datetime,
                    row: Mapping[str, Any], outcome: Mapping[str, Any], inputs: Mapping[str, Any], thresholds_hash: str) -> dict[str, Any]:
    """The immutable record of one verdict: every key the migration names, the canonical ``row_sha256`` of all the others
    (``id`` and ``row_sha256`` excepted) and ``inputs_sha256`` over the provenance. ``published_at`` before
    ``prediction_instant`` is a ``ValueError`` — the PostgreSQL CHECK, applied before any record exists.
    ``Database._decision_record`` rebuilds EXACTLY this shape from a PostgreSQL row: change both together."""
    instant, available = _utc(prediction_instant), _utc(published_at)
    if available < instant:
        raise ValueError(f"published_at {available.isoformat()} precedes prediction_instant {instant.isoformat()} for {market}/{symbol}")
    if outcome["verdict"] not in VERDICTS:
        raise ValueError(f"unknown verdict {outcome['verdict']!r}")
    provenance = _json_ready(inputs)
    core = {
        "schema": DECISION_SCHEMA,
        "decisor_version": DECISOR_VERSION,
        "mode": MODE_SHADOW,
        "run_id": str(run_id),
        "market": market,
        "symbol": symbol,
        "session_date": str(session_date),
        "prediction_instant": instant.isoformat(),
        "published_at": available.isoformat(),
        "verdict": outcome["verdict"],
        "reason_codes": [str(code) for code in outcome["reason_codes"]],
        "generation_id": str(row["generation_id"]),
        "tp_source": str(row["tp_source"]),
        "tp_cycle_id": str(row["official_cycle_id"]),
        "tp_row_sha256": str(row["official_row_sha256"]),
        "tp_prediction_instant": _utc(row["prediction_instant"]).isoformat(),
        "tp": _positive(row.get("our_tp")),
        "buy_in": _positive(row.get("buy_in")),
        "price": _positive(outcome.get("price")),
        "e_profile": _number(outcome.get("e_profile")),
        "h_market": _number(outcome.get("h_market")),
        "thresholds_sha256": thresholds_hash,
        "inputs": provenance,
        "inputs_sha256": canonical_sha256(provenance),
        "checks": _json_ready(outcome["checks"]),
    }
    return {**core, "id": str(uuid4()), "row_sha256": canonical_sha256(core)}


def stored_decision(record: Mapping[str, Any]) -> dict[str, Any] | None:
    """The record a reader SERVES for a stored row: its schema is ``DECISION_SCHEMA`` and both hashes recompute
    (``row_sha256`` over every key but ``id``/``row_sha256``; ``inputs_sha256`` over ``inputs``) — else ``None``, not
    served, with a WARNING the first time this process meets the row (INFO after). Every reader passes through here —
    the PostgreSQL reader ``Database._decision_record`` and the memory double alike."""
    key = str(record.get("id") or f"{record.get('market')}/{record.get('symbol')}/{record.get('run_id')}")
    reason: str | None = None
    if record.get("schema") != DECISION_SCHEMA:
        reason = f"it claims schema {record.get('schema')!r}"
    elif canonical_sha256(record.get("inputs")) != record.get("inputs_sha256"):
        reason = "its inputs_sha256 does not verify"
    else:
        core = {name: value for name, value in record.items() if name not in ("id", "row_sha256")}
        if canonical_sha256(core) != record.get("row_sha256"):
            reason = "its row_sha256 does not verify"
    if reason is not None:
        level = logging.INFO if key in _integrity_logged else logging.WARNING
        _integrity_logged.add(key)
        logger.log(level, "valuation_decision: stored decision %s (%s/%s of run %s) is not served — %s", record.get("id"), record.get("market"),
                   record.get("symbol"), record.get("run_id"), reason)
        return None
    return copy.deepcopy(dict(record))


# ------------------------------------------------------------------ the nightly shadow run


def _served_rows(database: Any, market: str, generation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Every row the generation SERVES for ``market``: the universe cycle's, plus (B3) the targeted admissions the
    universe does not serve — exactly what ``official_row`` answers for each symbol."""
    rows = official_rows(database, market, generation=generation)
    if market == "B3":
        for symbol in sorted((generation.get("targeted") or {})):
            clean = str(symbol).strip().upper()
            if clean in rows:
                continue
            row = official_row(database, "B3", clean, generation=generation)
            if row is not None:
                rows[clean] = row
    return rows


ROW_INPUT_KEYS = ("valuation_profile", "fundamentals_as_of", "as_of", "tp_validation_status", "signal_quality", "valuation_confidence",
                  "method_dispersion_percent", "tp_stale", "price")


def run_shadow(database: Any, *, now: datetime | None = None, quotes: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
               thresholds: DecisorThresholds = THRESHOLDS, write: bool = True) -> dict[str, Any]:
    """One decision run over the generation in force: a verdict per served name, every record written in ONE append
    (idempotent per ``(run_id, market, symbol)``) unless ``write`` is ``False`` (a dry run: the receipt only). ``now`` is
    the run's clock (the wall clock by default); ``published_at`` is the later of it and the wall clock read immediately
    before the insert. ``quotes`` (``(market, symbol) → {price, ask, as_of, source}``) is for a caller holding live quotes;
    the nightly phase passes none. The receipt is aggregate (per market: decided, verdicts, reasons, unrecordable) — it
    names no symbol. Nothing is decided without a generation, under a generation whose source is unknown, or under a
    thresholds block other than the one the PREREG froze (``ValueError``)."""
    frozen = _prereg_frozen(thresholds)
    digest = thresholds_sha256(thresholds)
    instant = _utc(now) if now is not None else datetime.now(timezone.utc)
    generation = current_generation(database)
    receipt: dict[str, Any] = {"schema": RUN_SCHEMA, "decisor_version": DECISOR_VERSION, "mode": MODE_SHADOW, "run_id": None, "status": "no_generation",
                               "generation_id": generation.get("generation_id") if generation else None, "tp_source": generation.get("source") if generation else None,
                               "prediction_instant": instant.isoformat(), "published_at": None, "thresholds_sha256": digest, "prereg_frozen": frozen,
                               "markets": {}, "recorded": 0, "written": False}
    if not generation:
        logger.info("valuation_decision: no official generation in force — nothing decided")
        return receipt
    if official._selected_source(generation) is None:  # Q3 of the selection: nothing is served under an unknown source, nothing is decided
        receipt["status"] = "unknown_source"
        return receipt
    run_id = str(uuid4())
    drafts: list[tuple[str, str, str, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    rates: dict[str, dict[str, Any]] = {}
    errors: dict[tuple[str, str], dict[str, Any]] = {}
    for market in MARKETS:
        stats: dict[str, Any] = {"decided": 0, "verdicts": {verdict: 0 for verdict in VERDICTS}, "reasons": {}, "unrecordable": 0,
                                 "expected_session": None, "calendar_unavailable": False}
        receipt["markets"][market] = stats
        try:
            expected = session_date_of(market, instant)
        except CalendarUnavailable:
            stats["calendar_unavailable"] = True
            continue
        stats["expected_session"] = expected
        group = "B3" if market == "B3" else "US"
        if group not in rates:
            rates[group] = market_rate(database, market, at=instant, generation=generation, thresholds=thresholds)
        latest_universe = database.analysis_snapshot_at_or_before(official.UNIVERSE_ANALYSIS, f"{market}_UNIVERSE", instant)
        for symbol, row in sorted(_served_rows(database, market, generation).items()):
            try:
                behind = _sessions_behind(market, str(row.get("official_session_date") or ""), expected)
            except CalendarUnavailable as error:
                logger.warning("valuation_decision: %s/%s not decided — %s", market, symbol, error)
                stats["unrecordable"] += 1
                continue
            profile = str(row.get("valuation_profile") or "general")
            if (market, profile) not in errors:
                errors[(market, profile)] = profile_error(database, market, profile, at=instant, thresholds=thresholds)
            price = _price_observation(row, market=market, symbol=symbol, quotes=quotes, latest_universe=latest_universe)
            outcome = decide(row, expected_session=expected, tp_sessions_behind=behind, price=price, error=errors[(market, profile)],
                             rate=rates[group], thresholds=thresholds)
            inputs = {
                "generation": {"generation_id": generation["generation_id"], "source": generation.get("source"), "activated_at": generation.get("activated_at")},
                "tp_record": {"source": row.get("tp_source"), "source_version": row.get("tp_source_version"), "cycle_id": row.get("official_cycle_id"),
                              "scope": row.get("official_scope"), "session_date": row.get("official_session_date"),
                              "prediction_instant": row.get("prediction_instant"), "published_at": row.get("official_published_at"),
                              "row_sha256": row.get("official_row_sha256")},
                "row": {key: row.get(key) for key in (*ROW_INPUT_KEYS, *thresholds.data_defect_fields)},
                "price": price,
                "e_profile": errors[(market, profile)],
                "market_rate": rates[group],
                "expected_session": expected,
                "thresholds_sha256": digest,
                "prereg_frozen": frozen,
            }
            drafts.append((market, symbol, expected, row, outcome, inputs))
            stats["decided"] += 1
            stats["verdicts"][outcome["verdict"]] += 1
            for code in outcome["reason_codes"]:
                stats["reasons"][code] = stats["reasons"].get(code, 0) + 1
    published = max(instant, datetime.now(timezone.utc))  # read immediately before the insert, never before the run's clock
    records = [decision_record(run_id=run_id, market=market, symbol=symbol, session_date=expected, prediction_instant=instant, published_at=published,
                               row=row, outcome=outcome, inputs=inputs, thresholds_hash=digest)
               for market, symbol, expected, row, outcome, inputs in drafts]
    receipt.update({"run_id": run_id, "status": "recorded" if write else "dry_run", "published_at": published.isoformat()})
    if write and records:
        receipt["recorded"] = int(database.insert_valuation_decisions(records))
        receipt["written"] = True
    receipt["receipt_sha256"] = canonical_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    logger.info("valuation_decision: run %s over generation %s (%s) — %s", run_id, generation["generation_id"], receipt["status"],
                {market: stats["verdicts"] for market, stats in receipt["markets"].items()})
    return receipt


def last_run_at(database: Any) -> datetime | None:
    """When the night's verdicts were published — the phase's ``last_completed_at``. A run counts only when it decided
    over the generation IN FORCE: a generation activated after it (a canonical retry that succeeded later in the window)
    makes the phase due again, so the night ends decided over the official cut it closed on."""
    run = database.latest_valuation_decision_run()
    generation = current_generation(database)
    if not run or not generation or str(run.get("generation_id")) != str(generation.get("generation_id")):
        return None
    return _utc(run["published_at"])


# ------------------------------------------------------------------ the R2D2 lab's read helper


def _view(record: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    try:
        current = record["session_date"] == session_date_of(str(record["market"]), now)
    except CalendarUnavailable:
        current = False
    view = {key: copy.deepcopy(record.get(key)) for key in ("symbol", "market", "verdict", "reason_codes", "session_date", "prediction_instant",
                                                             "published_at", "run_id", "generation_id", "tp_source", "tp_cycle_id", "tp", "buy_in",
                                                             "price", "e_profile", "h_market", "thresholds_sha256", "row_sha256", "mode")}
    view.update({"current": current, "effective_verdict": record["verdict"] if current else VETO,
                 "effective_reason_codes": list(record["reason_codes"]) if current else [VERDICT_NOT_CURRENT]})
    return view


def latest_verdicts(database: Any, market: str, symbols: Iterable[str], *, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """The latest verdict of each REQUESTED symbol (``market``: ``B3``, ``NASDAQ``, ``NYSE`` or ``US`` for both US
    markets) — the R2D2 lab names what it asks about; nothing here enumerates the names a verdict permits. Each view
    carries the verdict, its codes, the TP read and its identity, and whether it was decided for the session in force at
    ``now`` (``current``: its session is the last completed one); a verdict of another session is served with
    ``effective_verdict = VETO`` and ``effective_reason_codes = [VERDICT_NOT_CURRENT]`` — no permission outlives its night.
    A symbol without a verified verdict is absent."""
    at = _utc(now) if now is not None else datetime.now(timezone.utc)
    wanted = sorted({str(symbol).strip().upper().removesuffix(".SA").removesuffix(".US") for symbol in symbols if str(symbol).strip()})
    found: dict[str, dict[str, Any]] = {}
    if not wanted:
        return found
    for selected in official._markets_for(market):
        for symbol, record in database.latest_valuation_decisions(selected, wanted).items():
            held = found.get(symbol)
            if held is None or (_utc(record["prediction_instant"]), _utc(record["published_at"])) > (_utc(held["prediction_instant"]), _utc(held["published_at"])):
                found[symbol] = record
    return {symbol: _view(record, now=at) for symbol, record in found.items()}


def latest_verdict(database: Any, market: str, symbol: str, *, now: datetime | None = None) -> dict[str, Any] | None:
    """One symbol's latest verdict view (``latest_verdicts``), or ``None`` when it has none."""
    views = latest_verdicts(database, market, [symbol], now=now)
    return next(iter(views.values()), None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valuation decisor V1 (shadow): a dry run (aggregate receipt, nothing written), a recorded run "
                                                 "(refused while C3PO_VALUATION_DECISOR_SHADOW is off) or one symbol's latest verdict.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="decide over the generation in force and print the aggregate receipt; writes nothing")
    group.add_argument("--run", action="store_true", help="decide and record (only with C3PO_VALUATION_DECISOR_SHADOW on)")
    group.add_argument("--verdict", metavar="MARKET:SYMBOL", help="the latest verdict of one symbol")
    args = parser.parse_args(argv)
    from .config import get_settings
    from .database import Database
    settings = get_settings()
    if args.run and not settings.valuation_decisor_shadow:
        parser.error("C3PO_VALUATION_DECISOR_SHADOW is off: the decisor records nothing (use --dry-run)")
    database = Database(settings)
    if args.verdict:
        market, sep, symbol = args.verdict.partition(":")
        if not sep or not market.strip() or not symbol.strip():
            parser.error("--verdict expects MARKET:SYMBOL")
        result: Any = latest_verdict(database, market.strip().upper(), symbol)
    else:
        result = run_shadow(database, write=args.run)
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
