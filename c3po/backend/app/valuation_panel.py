"""The weekly measurement panel of the Valuation Engine V3.2 (rev 7 §7.3 item 3; PROMO-1, PROMO-2, PROMO-2-ZERO), v1.

MEASUREMENT, NEVER A GATE: nothing served changes, nothing is blocked, nothing is written to the store. The panel reads
the immutable prediction records (``valuation_predictions``, by source and version — `valuation_official` readers, rev 7
TP-C) and the persisted price series (``valuation_price_history``, through ``PriceHistoryService`` with the cut as
``available_before``) and publishes, per market, source and horizon in SESSIONS of the market's exchange calendar
(21/42/63/126; 252 only for the consensus at its declared 12-month horizon):

* the realized log-error of §2.6 — ``e = ln(tp · a(T)) − ln(adjusted_close(T+h))`` with ``a(T) = adjusted_close(T) /
  close(T)`` from the SAME vintage (§2.2, total-return convention; the bar's currency must be the record's) — as
  ``MSE`` in log² and the median absolute error, for the source AND for the consensus the record itself persisted
  (the consensus that EXISTED at the prediction instant: ``decomposition.consensus`` with its own currency, instant
  and hash, its ``published_at ≤ prediction_instant`` — never a later one, never an unattested one) on the SAME mask
  ``(i, T)`` where source, consensus and label are all present;
* the attrition per cause (§2.2): denominator = observations whose target session ``T + h`` closed before the cut;
  ``not_yet_mature`` and ``beyond_calendar`` are OUTSIDE it and counted apart; a bar unavailable at the cut
  (``no_vintage``, ``missing_bar``, ``symbol_not_in_vintage``, …) is a missing label, never a price from elsewhere;
* the pre-registered decision at ``h = 126`` (PROMO-2 e): ``MSE_source ≤ k × MSE_consensus`` with ``k = 1.00`` (and
  ``1.05`` reported), the ratio reported (``N/D`` when ``MSE_consensus = 0``), the zero branches (both zero → ``TIE``,
  counts as passed with the marker; consensus zero and source > 0 → ``FAIL``), the minimums AFTER the intersection
  (``N_EVAL = 30``, ≥ 10 names, ≥ 10 sessions) → ``INSUFFICIENT``, attrition > 10 % → ``UNMEASURED`` before any count;
* level and dispersion against the consensus at prediction time (median of ``tp / consensus − 1``; quantiles of the
  centred deviations) per market and profile, with the sanity gates p50 ≤ 15 % / p90 ≤ 30 % of ``|tp / consensus − 1|``
  reported as ``SANITY_*`` — never blocking (§7.3 item 3, rev 5);
* the band coverage (PROMO-1): the fraction of realized prices (in the basis of ``T``) inside ``[bear_tp, bull_tp]``
  per market and horizon, mask and sample declared, null bands excluded and counted — a diagnostic, not a gate.

The receipt is a deterministic function of ``(cut, store)`` whenever the cut lies within the calendar's horizon
(``exchange_calendars`` builds a calendar to today + 1 year by default — a wall-clock bound; a target session past it
is ``not_yet_mature`` when the calendar's last session closes at or after the cut, exactly what a longer calendar
would answer; a cut PAST the calendar leaves ``beyond_calendar`` and the receipt says ``cut_within_calendar_horizon``
false): observations are ordered by (symbol, session) before any sum, ``-0.0`` is normalised, the protocol constants
travel inside the hashed payload, and the payload carries NO symbol (the per-symbol detail is a separate private file
written only on request, ``O_EXCL | O_NOFOLLOW``, mode 0600). The cut is always explicit and time-zone aware (never
``now()``), and the service never reaches the network: its price reader is built on an HTTP client that raises on any
call.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import math
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence, cast

import exchange_calendars as xcals

from . import valuation_price_history as price_history_module
from .config import Settings, get_settings
from .database import Database
from .market_data.http import JsonHttpClient
from .valuation_official import CalendarUnavailable, canonical_sha256, session_date_of
from .valuation_price_history import LABEL_ADJUSTMENT_UNKNOWN, PriceHistoryService

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "VALUATION-PANEL-7-3-v1"
MARKETS: tuple[str, ...] = price_history_module.MARKETS
CALENDARS: dict[str, str] = dict(price_history_module.CALENDARS)
DEFAULT_SOURCES: tuple[str, ...] = ("official_blend_v1",)
# --- protocol constants, pre-registered (rev 7 §7.3 PROMO-2, §2.6, §2.2); every one of them travels inside the hashed payload
HORIZONS: tuple[int, ...] = (21, 42, 63, 126)  # sessions; 21/42/63 diagnostics only
DECISORY_HORIZON = 126
CONSENSUS_DECLARED_HORIZON = 252  # the consensus at its declared 12-month horizon: reported, never decisory
K_PRIMARY = 1.00
K_SECONDARY = 1.05
N_EVAL = 30
MIN_NAMES = 10
MIN_SESSIONS = 10
ATTRITION_CAP = 0.10
SANITY_P50 = 0.15
SANITY_P90 = 0.30
TOL_BASIS = 0.02
QUANTILES: tuple[float, ...] = (0.10, 0.25, 0.75, 0.90)
LABEL_CONVENTION = "total_return:adjusted_close"
BASIS_MISMATCH = "label_unavailable:basis_mismatch"
BASIS_UNVERIFIABLE = "label_unavailable:basis_unverifiable"  # the record carries no price: |P − close(T)| cannot be checked
BASIS_CURRENCY_MISMATCH = "label_unavailable:currency_mismatch"  # the bar at T is not in the record's currency (§2.2): no basis, no label
INELIGIBLE: tuple[str, ...] = ("not_yet_mature", "beyond_calendar")  # outside the attrition denominator (§2.2); a session not in the calendar is refused earlier
# --- the persisted consensus and the common mask (PROMO-2 c): every status but ``present`` is excluded and counted by cause
CONSENSUS_PRESENT = "present"
CONSENSUS_ABSENT = "absent"  # no tp
CONSENSUS_UNATTESTED = "consensus_unattested"  # no block, or a block without currency / published_at / payload_sha256, or an unparseable instant
CONSENSUS_AFTER_PREDICTION = "consensus_after_prediction"  # the block's published_at is LATER than prediction_instant: not the consensus that existed then
CONSENSUS_CURRENCY_MISMATCH = "consensus_currency_mismatch"  # the block's currency is not the record's


def protocol() -> dict[str, Any]:
    """The pre-registered constants, as the receipt carries them (inside the hashed payload)."""
    return {
        "schema": SCHEMA_VERSION,
        "horizons_sessions": list(HORIZONS),
        "decisory_horizon": DECISORY_HORIZON,
        "consensus_declared_horizon": CONSENSUS_DECLARED_HORIZON,
        "k_primary": K_PRIMARY,
        "k_secondary": K_SECONDARY,
        "n_eval": N_EVAL,
        "min_names": MIN_NAMES,
        "min_sessions": MIN_SESSIONS,
        "attrition_cap": ATTRITION_CAP,
        "sanity_p50": SANITY_P50,
        "sanity_p90": SANITY_P90,
        "tol_basis": TOL_BASIS,
        "quantiles": list(QUANTILES),
        "label_convention": LABEL_CONVENTION,
        "log_error": "ln(tp * adjusted_close(T) / close(T)) - ln(adjusted_close(T + h))",
        "calendar": {"markets": dict(CALENDARS), "exchange_calendars": getattr(xcals, "__version__", "unknown")},
        "rule": "MSE_source <= k * MSE_consensus at the decisory horizon; k = 1.00 in at least two markets and 1.05 in the third",
        "gate": False,
    }


# ------------------------------------------------------------------ small helpers (no store, no clock)
def _finite(value: float) -> float:
    """A float as the receipt hashes it: ``-0.0`` → ``0.0`` (JSON has no signed zero; the hash must survive a round trip)."""
    return float(value) + 0.0


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return _finite(number)


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _utc(value: Any) -> datetime:
    """A clock as a UTC instant: a naive value is taken as UTC (the convention of the run API of the price series)."""
    instant = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant.astimezone(timezone.utc)


def _aware(value: datetime, name: str) -> datetime:
    """The panel's clocks (the cut, the window) are explicit AND time-zone aware: a naive one is refused (the clock rule)."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a time-zone aware datetime, got {value!r}: the panel never guesses a zone and never reads now()")
    return value.astimezone(timezone.utc)


def _parse_instant(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return _utc(value)
    except (TypeError, ValueError):
        return None


def _parse_session(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _counts(counter: Mapping[str, int]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def quantile(values: Iterable[float], fraction: float) -> float | None:
    """Linear interpolation between order statistics — the convention of ``valuation_v3_shadow._percentile`` (copied
    verbatim: that module is frozen and its helper private; pinned equal by test). ``None`` on an empty sample."""
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return _finite(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def log_error(tp: float, adjustment: float, realized: float) -> float:
    """§2.2 / §2.6 exactly: ``ln(tp · a(T)) − ln(adjusted_close(T + h))`` with ``a(T) = adjusted_close(T) / close(T)`` of
    the same vintage (total return: a dividend between ``T`` and ``T + h`` is credited to the realized price)."""
    return _finite(math.log(tp * adjustment) - math.log(realized))


# ------------------------------------------------------------------ the market's calendar (the one label_bar reads)
def _calendar(market: str) -> Any:
    """The calendar ``label_bar`` and ``sessions_after`` read (``valuation_price_history._calendar``: the SAME object,
    hence the same bounds) — the panel never builds a calendar of its own."""
    return price_history_module._calendar(market)


def session_in_calendar(market: str, session: date) -> bool:
    """Whether ``session`` is a session of the market's calendar. ``False`` for an unknown market and for a date the
    calendar cannot answer for (out of its bounds: ``DateOutOfBounds``, a ``ValueError``) — such a record is refused,
    never carried as an observation whose label would be ``not_a_session`` (§2.2: the denominator is decided before)."""
    if market not in CALENDARS:
        return False
    try:
        return bool(_calendar(market).is_session(session.isoformat()))
    except Exception:  # DateOutOfBounds, or a calendar that cannot be built: the calendar does not know the session
        return False


def calendar_horizon(market: str) -> datetime | None:
    """The close of the LAST session the market's calendar answers for (``exchange_calendars`` builds it to today + 1
    year by default: a wall-clock bound). ``None`` when the calendar cannot answer."""
    try:
        return price_history_module.session_close(market, _calendar(market).last_session.date())
    except Exception:
        return None


def resolve_label(label: Mapping[str, Any], *, cut: datetime, calendar_close: datetime | None) -> dict[str, Any]:
    """``label_bar``'s answer as the panel classifies it. ``beyond_calendar`` means the target session ``T + h`` lies past
    the END of the calendar — a bound set by the day the calendar was built, not by the store. When the calendar's last
    session closes at or after the cut, the target (later still) cannot have closed before ``C``: it is
    ``not_yet_mature`` — exactly what a longer calendar would answer, so the receipt does not depend on the day it is
    built. When the cut itself is past the calendar (``calendar_close < C``, or no calendar) the target may or may not
    have matured: ``beyond_calendar`` stays (ineligible, counted apart) and the receipt is then not a function of
    ``(C, store)`` alone — ``cut_within_calendar_horizon`` says so in the cell."""
    resolved = dict(label)
    if resolved.get("status") == "beyond_calendar" and calendar_close is not None and calendar_close >= _utc(cut):
        resolved["status"] = "not_yet_mature"
    return resolved


# ------------------------------------------------------------------ admissibility (§2.2, PROMO-2 b/c)
def admissible_records(records: Iterable[Mapping[str, Any]], *, cut: datetime, since: datetime | None = None,
                       until: datetime | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The records a cut ``C`` may use, and the refusals counted by cause: ``prediction_instant`` in ``[since, until)``
    (``outside_window``), ``published_at`` = ``available_at`` of the record ``< C`` (``published_at_not_before_cut``;
    a record without it — a legacy V1 row — is ``no_published_at``: data without an availability clock is ineligible),
    ``tp > 0`` (``tp_not_positive``), a parseable session (``session_unparseable``) that IS a session of the record's
    market calendar (``session_not_in_calendar``: a weekend, a holiday, a date the calendar cannot answer for — refused
    here, never an observation outside the denominator), and ONE record per ``(source, symbol, session)`` whatever the
    source version: the record with the SMALLEST ``published_at`` enters (the first that existed), the others — another
    version of the source, a re-run, a second cycle of the same session — are ``duplicate_session``: counted, never
    summed (§2.2). Re-runs (``provenance.rerun_of``) are admissible when their ``published_at < C`` and no earlier record
    of the same ``(source, symbol, session)`` exists; the caller counts them. Deterministic: candidates ordered by
    ``(published_at, prediction_instant, symbol, cycle_id)``, output ordered by (symbol, session, prediction_instant)."""
    cut_utc = _utc(cut)
    lower = _utc(since) if since is not None else None
    upper = _utc(until) if until is not None else None
    refusals: Counter[str] = Counter()
    candidates: list[tuple[datetime, datetime, str, str, dict[str, Any]]] = []
    for record in records:
        instant = _parse_instant(record.get("prediction_instant"))
        if instant is None:
            refusals["prediction_instant_unparseable"] += 1
            continue
        available = _parse_instant(record.get("published_at"))
        if available is None:
            refusals["no_published_at"] += 1
            continue
        symbol = str(record.get("symbol") or "").strip().upper()
        session = _parse_session(record.get("session_date"))
        if not symbol or session is None:
            refusals["session_unparseable"] += 1
            continue
        if not session_in_calendar(str(record.get("market") or ""), session):
            refusals["session_not_in_calendar"] += 1
            continue
        if (lower is not None and instant < lower) or (upper is not None and instant >= upper):
            refusals["outside_window"] += 1
            continue
        if available >= cut_utc:
            refusals["published_at_not_before_cut"] += 1
            continue
        if _positive(record.get("tp")) is None:
            refusals["tp_not_positive"] += 1
            continue
        candidates.append((instant, available, symbol, str(record.get("cycle_id") or ""), dict(record)))
    candidates.sort(key=lambda item: (item[1], item[0], item[2], item[3]))  # (published_at, prediction_instant, symbol, cycle): the first that existed
    kept: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for _instant, _available, symbol, _cycle, record in candidates:
        key = (str(record.get("source")), symbol, str(record.get("session_date"))[:10])
        if key in seen:
            refusals["duplicate_session"] += 1
            continue
        seen.add(key)
        kept.append(record)
    kept.sort(key=lambda record: (str(record["symbol"]), str(record["session_date"]), _utc(record["prediction_instant"]).isoformat()))
    return kept, _counts(refusals)


# ------------------------------------------------------------------ one observation (i, T)
def _consensus_of(record: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """The consensus block the record PERSISTED (``decomposition.consensus``: tp, source, horizon, currency, instant,
    hash) and its status for the common mask. ``present`` only when the block is attested — currency, ``published_at``
    and ``payload_sha256`` all there, the instant parseable — its ``published_at ≤ prediction_instant`` (the consensus
    that EXISTED at the prediction instant, PROMO-2 c: a re-run whose block was published later is
    ``consensus_after_prediction``) and its currency the record's (else ``consensus_currency_mismatch``). ``absent``
    without a tp; ``consensus_unattested`` for a block without those fields — the flat ``consensus_tp`` column of a
    record without the block is reported as the tp but never attests anything (no source, horizon, currency, instant
    or hash: it cannot be the consensus of PROMO-2 c)."""
    block = _mapping(_mapping(record.get("decomposition")).get("consensus"))
    tp = _positive(block.get("tp"))
    if tp is None:
        tp = _positive(record.get("consensus_tp"))  # a record without the block (not the official emitter's shape): the column, reported only
    currency = block.get("currency")
    consensus = {"tp": tp, "source": block.get("source"), "horizon": block.get("horizon"), "currency": currency,
                 "published_at": block.get("published_at"), "payload_sha256": block.get("payload_sha256")}
    if tp is None:
        return consensus, CONSENSUS_ABSENT
    if currency in (None, "") or consensus["published_at"] in (None, "") or consensus["payload_sha256"] in (None, ""):
        return consensus, CONSENSUS_UNATTESTED
    consensus_instant, prediction_instant = _parse_instant(consensus["published_at"]), _parse_instant(record.get("prediction_instant"))
    if consensus_instant is None or prediction_instant is None:
        return consensus, CONSENSUS_UNATTESTED
    if consensus_instant > prediction_instant:
        return consensus, CONSENSUS_AFTER_PREDICTION
    if record.get("currency") is not None and str(currency) != str(record.get("currency")):
        return consensus, CONSENSUS_CURRENCY_MISMATCH
    return consensus, CONSENSUS_PRESENT


def _bands_of(record: Mapping[str, Any]) -> tuple[float | None, float | None]:
    bands = _mapping(_mapping(record.get("decomposition")).get("bands"))
    bear = _positive(record.get("bear_tp")) or _positive(bands.get("bear_tp"))
    bull = _positive(record.get("bull_tp")) or _positive(bands.get("bull_tp"))
    return bear, bull


def observation(record: Mapping[str, Any], bar_at_session: Mapping[str, Any] | None, labels_by_horizon: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    """One row of the panel for ``(i, T)``: the record's identity and numbers, its persisted consensus and bands, the
    adjustment ``a(T)`` with the basis check of §2.2 (the bar's currency must be the record's, else
    ``label_unavailable:currency_mismatch``; ``|price − close(T)| / close(T) ≤ TOL_BASIS``, else
    ``label_unavailable:basis_mismatch``; no bar at ``T`` in the vintage → ``label_unavailable:adjustment_unknown``), and
    per horizon the label as the service resolved it (``resolve_label``), read into: ``eligible`` (the target session
    closed before the cut — ``not_yet_mature``/``beyond_calendar`` are not), the realized adjusted close, the log-errors
    of the source and of the consensus (only when the consensus is ``present``), and whether the realized price IN THE
    BASIS OF ``T`` (``adjusted_close(T+h) / a(T)``) lies inside ``[bear_tp, bull_tp]`` (``None`` without bands). A
    labelled bar under a failed basis check is the basis cause, never a label."""
    tp = float(record["tp"])
    price = _positive(record.get("price"))
    consensus, consensus_status = _consensus_of(record)
    bear, bull = _bands_of(record)
    adjustment: float | None = None
    close_at_session: float | None = None
    basis_status = LABEL_ADJUSTMENT_UNKNOWN
    if bar_at_session is not None:
        close_at_session, adjusted_at_session = _positive(bar_at_session.get("close")), _positive(bar_at_session.get("adjusted_close"))
        if close_at_session is not None and adjusted_at_session is not None:
            adjustment = _finite(adjusted_at_session / close_at_session)
            bar_currency, record_currency = bar_at_session.get("currency"), record.get("currency")
            if bar_currency not in (None, "") and record_currency not in (None, "") and str(bar_currency) != str(record_currency):
                basis_status = BASIS_CURRENCY_MISMATCH  # §2.2: a price in another currency is no basis for the TP, whatever the tolerance says
            elif price is None:
                basis_status = BASIS_UNVERIFIABLE
            elif abs(price - close_at_session) / close_at_session > TOL_BASIS:
                basis_status = BASIS_MISMATCH
            else:
                basis_status = "ok"
    horizons: dict[str, dict[str, Any]] = {}
    for horizon in sorted(labels_by_horizon):
        label = labels_by_horizon[horizon]
        status = str(label.get("status"))
        entry: dict[str, Any] = {"status": status, "eligible": status not in INELIGIBLE, "session": label.get("session"), "realized": None, "close": None,
                                 "bar_sha256": None, "e_source": None, "e_consensus": None, "within_bands": None}
        if entry["eligible"] and status == "labelled":
            realized = _positive(label.get("adjusted_close"))
            if basis_status != "ok" or adjustment is None:
                entry["status"] = basis_status
            elif realized is None:
                entry["status"] = LABEL_ADJUSTMENT_UNKNOWN
            else:
                entry.update({"realized": realized, "close": _positive(label.get("close")), "bar_sha256": label.get("bar_sha256"),
                              "e_source": log_error(tp, adjustment, realized)})
                if consensus_status == CONSENSUS_PRESENT and consensus["tp"] is not None:
                    entry["e_consensus"] = log_error(float(consensus["tp"]), adjustment, realized)
                if bear is not None and bull is not None:
                    in_basis_of_session = realized / adjustment
                    entry["within_bands"] = bool(bear <= in_basis_of_session <= bull)
        horizons[str(horizon)] = entry
    provenance = _mapping(_mapping(record.get("decomposition")).get("provenance"))
    return {
        "symbol": str(record["symbol"]), "session": str(record["session_date"])[:10], "market": record.get("market"), "source": record.get("source"),
        "source_version": str(record.get("source_version")), "cycle_id": record.get("cycle_id"), "row_sha256": record.get("row_sha256"),
        "prediction_instant": _utc(record["prediction_instant"]).isoformat(), "published_at": _utc(record["published_at"]).isoformat(),
        "rerun_of": provenance.get("rerun_of"), "tp": tp, "price": price, "currency": record.get("currency"),  # the record's TP, read — never computed here (I-TP1)
        "consensus": consensus, "consensus_status": consensus_status, "bands": {"bear_tp": bear, "bull_tp": bull},
        "close_at_session": close_at_session, "adjustment": adjustment, "basis_status": basis_status, "horizons": horizons,
    }


# ------------------------------------------------------------------ metrics per horizon (§2.6 log-error, §2.2 attrition, PROMO-1 bands)
def _error_metrics(errors: list[float]) -> dict[str, Any]:
    """``MSE`` in log² (the metric of §2.6, not a rate in p.p.), the median absolute error, the mean (signed) error."""
    if not errors:
        return {"n": 0, "mse": None, "median_abs_log_error": None, "mean_log_error": None}
    total_square = 0.0
    total = 0.0
    for error in errors:  # in the callers' (symbol, session) order: the same sum every time
        total_square += error * error
        total += error
    return {"n": len(errors), "mse": _finite(total_square / len(errors)), "median_abs_log_error": quantile([abs(e) for e in errors], 0.5),
            "mean_log_error": _finite(total / len(errors))}


def _mask_stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Dependence, as §2.6 asks it published: distinct names, distinct sessions, the largest share of one name."""
    by_name: Counter[str] = Counter(str(row["symbol"]) for row in rows)
    sessions = {str(row["session"]) for row in rows}
    return {"n": len(rows), "names": len(by_name), "sessions": len(sessions),
            "max_share_single_name": _finite(max(by_name.values()) / len(rows)) if rows else None}


def horizon_metrics(observations: Sequence[Mapping[str, Any]], horizon: int) -> dict[str, Any]:
    """Per horizon: the eligible observations (target session closed before the cut), the ineligible ones counted
    apart, the attrition by cause over the ELIGIBLE (§2.2), the source's realized error over every labelled
    observation, the consensus' error on the COMMON mask (label AND consensus present, PROMO-2 d) with the source's
    error restricted to that same mask (what the decision compares), the mask's dependence statistics, and the band
    coverage over the labelled observations (null bands excluded and counted, PROMO-1)."""
    key = str(horizon)
    eligible = [row for row in observations if row["horizons"][key]["eligible"]]
    ineligible: Counter[str] = Counter(str(row["horizons"][key]["status"]) for row in observations if not row["horizons"][key]["eligible"])
    labelled = [row for row in eligible if row["horizons"][key]["e_source"] is not None]
    unavailable: Counter[str] = Counter(str(row["horizons"][key]["status"]) for row in eligible if row["horizons"][key]["e_source"] is None)
    common = [row for row in labelled if row["horizons"][key]["e_consensus"] is not None]
    excluded: Counter[str] = Counter(str(row["consensus_status"]) for row in labelled if row["horizons"][key]["e_consensus"] is None)
    with_bands = [row for row in labelled if row["horizons"][key]["within_bands"] is not None]
    within = sum(1 for row in with_bands if row["horizons"][key]["within_bands"])
    return {
        "horizon_sessions": horizon,
        "diagnostic_only": horizon != DECISORY_HORIZON,
        "eligible": len(eligible),
        "ineligible": _counts(ineligible),
        "labelled": len(labelled),
        "attrition": {"rate": _finite(sum(unavailable.values()) / len(eligible)) if eligible else None, "unavailable": sum(unavailable.values()),
                      "by_cause": _counts(unavailable)},
        "source": _error_metrics([float(row["horizons"][key]["e_source"]) for row in labelled]),
        "source_on_common_mask": _error_metrics([float(row["horizons"][key]["e_source"]) for row in common]),
        "consensus": _error_metrics([float(row["horizons"][key]["e_consensus"]) for row in common]),
        "common_mask": {**_mask_stats(common), "excluded": _counts(excluded)},
        "band_coverage": {"mask": "labelled observations of the source with both bands", "n_with_bands": len(with_bands),
                          "n_null_bands": len(labelled) - len(with_bands), "within": within,
                          "fraction": _finite(within / len(with_bands)) if with_bands else None},
    }


# ------------------------------------------------------------------ the pre-registered decision (PROMO-2 e, PROMO-2-ZERO)
def decision(source_mse: float | None, consensus_mse: float | None, n: int, names: int, sessions: int, attrition: float | None) -> dict[str, Any]:
    """``MSE_source ≤ k × MSE_consensus`` at the decisory horizon, in the pre-registered order: attrition above the cap
    (or no eligible observation at all) → ``UNMEASURED`` before any count; the minimums after the intersection
    (``N_EVAL``, names, sessions) → ``INSUFFICIENT``; both MSE zero → ``TIE`` (satisfies the inequality, counts as
    passed, marker ``tie``); consensus zero and source > 0 → ``FAIL`` with ratio ``N/D``; otherwise the ratio is
    reported and the status is ``PASS`` at ``k = 1.00`` (``passes_k_1_05`` reported alongside). No epsilon, no policy
    chosen after the result."""
    result: dict[str, Any] = {"status": "UNMEASURED", "ratio": "N/D", "passes_k_1_00": False, "passes_k_1_05": False, "tie": False, "reasons": [],
                              "n": n, "names": names, "sessions": sessions, "attrition": attrition, "mse_source": source_mse, "mse_consensus": consensus_mse,
                              "k_primary": K_PRIMARY, "k_secondary": K_SECONDARY}
    if attrition is None:
        result["reasons"].append("no_eligible_observations")
        return result
    if attrition > ATTRITION_CAP:
        result["reasons"].append(f"attrition_above_cap:{attrition:.4f}>{ATTRITION_CAP}")
        return result
    reasons = []
    if n < N_EVAL:
        reasons.append(f"n_below_n_eval:{n}<{N_EVAL}")
    if names < MIN_NAMES:
        reasons.append(f"names_below_min:{names}<{MIN_NAMES}")
    if sessions < MIN_SESSIONS:
        reasons.append(f"sessions_below_min:{sessions}<{MIN_SESSIONS}")
    if source_mse is None or consensus_mse is None:
        reasons.append("mse_unavailable")
    if reasons:
        result.update({"status": "INSUFFICIENT", "reasons": reasons})
        return result
    assert source_mse is not None and consensus_mse is not None
    if consensus_mse == 0.0:
        if source_mse == 0.0:
            result.update({"status": "TIE", "passes_k_1_00": True, "passes_k_1_05": True, "tie": True, "reasons": ["both_mse_zero"]})
        else:
            result.update({"status": "FAIL", "reasons": ["consensus_mse_zero_source_positive"]})
        return result
    ratio = _finite(source_mse / consensus_mse)
    passes_primary = source_mse <= K_PRIMARY * consensus_mse
    passes_secondary = source_mse <= K_SECONDARY * consensus_mse
    result.update({"status": "PASS" if passes_primary else "FAIL", "ratio": ratio, "passes_k_1_00": passes_primary, "passes_k_1_05": passes_secondary,
                   "reasons": [] if passes_primary else [f"ratio_above_k_primary:{ratio:.6f}"]})
    return result


def protocol_combination(decisions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The three-market rule of PROMO-2 e / §10.9 over the per-market decisions of one source: ``k = 1.00`` in at least
    two markets and ``k = 1.05`` in the third (a ``TIE`` counts as passed at both). ``NOT_EVALUABLE`` while any of the
    three markets is missing, ``UNMEASURED`` or ``INSUFFICIENT`` — never a verdict on fewer markets."""
    missing = [market for market in MARKETS if market not in decisions]
    unmeasured = sorted(market for market, item in decisions.items() if item["status"] not in ("PASS", "FAIL", "TIE"))
    passed_primary = sorted(market for market, item in decisions.items() if item["passes_k_1_00"])
    passed_secondary = sorted(market for market, item in decisions.items() if item["passes_k_1_05"])
    if missing or unmeasured:
        status = "NOT_EVALUABLE"
    else:
        status = "PASS" if len(passed_primary) >= 2 and len(passed_secondary) == len(MARKETS) else "FAIL"
    return {"status": status, "markets_missing": missing, "markets_unmeasured": unmeasured, "passed_k_1_00": passed_primary, "passed_k_1_05": passed_secondary,
            "ties": sorted(market for market, item in decisions.items() if item.get("tie")), "gate": False}


# ------------------------------------------------------------------ level and dispersion vs the consensus at prediction time (§7.3 item 3, §2.4 as reading)
def level_dispersion(observations: Sequence[Mapping[str, Any]], profile_of: Callable[[Mapping[str, Any]], str]) -> dict[str, dict[str, Any]]:
    """Per profile: the median of ``tp / consensus − 1`` (level), the quantiles p10/p25/p75/p90 of the CENTRED deviations
    (dispersion), and the sanity gates on ``|tp / consensus − 1|`` (p50 ≤ 15 %, p90 ≤ 30 %) as ``SANITY_OK`` /
    ``SANITY_OUT`` / ``SANITY_UNMEASURED`` — reported, never blocking. Over every admissible observation with a
    ``present`` consensus (no label needed); the others are counted by their consensus status."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in observations:
        groups.setdefault(str(profile_of(row)), []).append(row)
    result: dict[str, dict[str, Any]] = {}
    for profile in sorted(groups):
        rows = groups[profile]
        deviations = [_finite(float(row["tp"]) / float(row["consensus"]["tp"]) - 1.0) for row in rows if row["consensus_status"] == CONSENSUS_PRESENT]
        excluded: Counter[str] = Counter(str(row["consensus_status"]) for row in rows if row["consensus_status"] != CONSENSUS_PRESENT)
        median = quantile(deviations, 0.5)
        centred = [_finite(deviation - median) for deviation in deviations] if median is not None else []
        magnitudes = [abs(deviation) for deviation in deviations]
        p50_abs, p90_abs = quantile(magnitudes, 0.5), quantile(magnitudes, 0.9)
        if p50_abs is None or p90_abs is None:
            status = "SANITY_UNMEASURED"
        else:
            status = "SANITY_OK" if p50_abs <= SANITY_P50 and p90_abs <= SANITY_P90 else "SANITY_OUT"
        result[profile] = {
            "n": len(deviations), "consensus_excluded": _counts(excluded), "median_level": median,
            "centred_quantiles": {f"p{int(round(fraction * 100))}": quantile(centred, fraction) for fraction in QUANTILES},
            "sanity": {"p50_abs": p50_abs, "p90_abs": p90_abs, "threshold_p50": SANITY_P50, "threshold_p90": SANITY_P90, "status": status, "blocking": False},
        }
    return result


# ------------------------------------------------------------------ the receipt and the private detail
def receipt(*, cut: datetime, window: Mapping[str, Any], markets: Iterable[str], sources: Iterable[str], results: Mapping[str, Any]) -> dict[str, Any]:
    """The aggregate receipt: a wrapper around a canonical payload (sorted keys, compact separators) and its sha256.
    The payload carries the protocol, the cut, the window, the markets, the sources, the results and the three-market
    combination per source — and NO symbol, NO wall clock (``built_at`` is not part of it: the receipt is a function of
    ``(cut, store)`` alone)."""
    market_list, source_list = list(markets), list(sources)
    combination = {source: protocol_combination({market: results[market][source]["decision"] for market in market_list
                                                 if source in results.get(market, {})}) for source in source_list}
    payload = {"schema": SCHEMA_VERSION, "protocol": protocol(), "cut": _utc(cut).isoformat(), "window": dict(window), "markets": market_list,
               "sources": source_list, "results": copy.deepcopy(dict(results)), "combination": combination}
    return {"schema": SCHEMA_VERSION, "payload": payload, "payload_sha256": canonical_sha256(payload)}


def write_private_detail(path: Path | str, detail: Any) -> None:
    """The per-symbol detail, written ONLY here: ``O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW``, mode 0600 (the pattern of
    ``r2d2_v2_shadow_worker._private_export``) — an existing path or a symlink (dangling included) is ``FileExistsError``
    with nothing written; canonical JSON, fsync'd."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(json.dumps(detail, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8") + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


# ------------------------------------------------------------------ the service (store only; the clock is a parameter)
class _NoNetworkHttp(JsonHttpClient):
    """The HTTP client the panel's price reader is built on: every call raises. The readers of ``PriceHistoryService``
    never touch it (only ``fetch_bars`` does, the producer's path); ``calls`` counts the attempts, pinned at 0 by test."""

    def __init__(self) -> None:
        super().__init__(timeout=0.0, max_retries=0)
        self.calls = 0

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        self.calls += 1
        raise RuntimeError(f"valuation_panel never reaches the network (attempted {url}): the panel reads the persisted store only")

    def get_text(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> str:
        self.calls += 1
        raise RuntimeError(f"valuation_panel never reaches the network (attempted {url}): the panel reads the persisted store only")


class _CutReads:
    """A thin proxy over ``Database`` that memoises, for ONE run, the two reads ``PriceHistoryService.vintage`` makes on
    every ``label_bar`` (``latest_analysis_snapshot_before`` by cut and ``analysis_snapshot_by_id``). Exact for the
    panel: the cut is constant during the run and the store is append-only, so the vintage a cut sees cannot change —
    and even a publication arriving mid-run (a cut set in the future) is then seen by the whole run or by none of it.
    Deep copies out, as the store's own readers. Everything else is delegated untouched."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._before: dict[tuple[str, str, str, str | None], dict[str, Any] | None] = {}
        self._by_id: dict[str, dict[str, Any] | None] = {}
        self.reads = 0  # store reads actually made (pinned by test: one per memo key)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._database, name)

    def latest_analysis_snapshot_before(self, analysis_type: str, entity_key: str, before: datetime, *, schema_version: str | None = None) -> dict[str, Any] | None:
        key = (analysis_type, entity_key, _utc(before).isoformat(), schema_version)
        if key not in self._before:
            self.reads += 1
            self._before[key] = self._database.latest_analysis_snapshot_before(analysis_type, entity_key, before, schema_version=schema_version)
        return copy.deepcopy(self._before[key])

    def analysis_snapshot_by_id(self, snapshot_id: str) -> dict[str, Any] | None:
        if snapshot_id not in self._by_id:
            self.reads += 1
            self._by_id[snapshot_id] = self._database.analysis_snapshot_by_id(snapshot_id)
        return copy.deepcopy(self._by_id[snapshot_id])


def last_closed_session(market: str, cut: datetime) -> str | None:
    """The last session of the market whose close is STRICTLY before the cut — the maturity rule of ``label_bar``
    (``session_close(T + h) < C``), read through ``valuation_official.session_date_of`` (close ≤ instant) one microsecond
    before the cut. ``None`` when the calendar cannot answer."""
    try:
        return session_date_of(market, _utc(cut) - timedelta(microseconds=1))
    except CalendarUnavailable:
        return None


class PanelService:
    """Reads the store as of a cut and produces the receipt and the private detail. Never writes, never fetches."""

    def __init__(self, database: Database, *, settings: Settings | None = None, price_history: PriceHistoryService | None = None) -> None:
        self.database = database
        self.reads = _CutReads(database)
        self.http: _NoNetworkHttp | None = None
        if price_history is None:
            self.http = _NoNetworkHttp()
            price_history = PriceHistoryService(settings if settings is not None else get_settings(), cast(Database, self.reads), self.http)
        self.price_history = price_history

    def _labels(self, market: str, symbol: str, session: date, cut: datetime, calendar_close: datetime | None) -> dict[int, dict[str, Any]]:
        return {horizon: resolve_label(self.price_history.label_bar(market, symbol, session, horizon, available_before=cut), cut=cut, calendar_close=calendar_close)
                for horizon in (*HORIZONS, CONSENSUS_DECLARED_HORIZON)}

    def _vintage_header(self, market: str, cut: datetime) -> dict[str, Any]:
        vintage = self.price_history.vintage(market, available_before=cut)
        if vintage is None:
            return {"status": None, "publication_id": None, "price_snapshot_id": None, "available_at": None, "fetched_at": None, "window": None}
        return {"status": vintage["status"], "publication_id": vintage["publication_id"], "price_snapshot_id": vintage["price_snapshot_id"],
                "available_at": vintage["available_at"], "fetched_at": vintage["fetched_at"],
                "window": [vintage["from"], vintage["to"]] if vintage["status"] == "ok" else None}

    def measure(self, market: str, source: str, *, cut: datetime, since: datetime | None, until: datetime | None,
                profile_label: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """One (market, source) cell: the records in the window, their admissibility, one observation per (i, T) with
        the bar at ``T`` and the labels at every horizon (all as of the cut; ``beyond_calendar`` resolved against the
        calendar's horizon, ``resolve_label``), then the pure functions. Returns the aggregate (no symbol) and the
        observations (the detail)."""
        records = self.database.list_valuation_predictions_in_window(market, source=source, since=since, until=until)
        kept, refusals = admissible_records(records, cut=cut, since=since, until=until)
        calendar_close = calendar_horizon(market)
        bars_by_symbol: dict[str, dict[str, dict[str, Any]]] = {}
        observations: list[dict[str, Any]] = []
        for record in kept:
            symbol = str(record["symbol"])
            if symbol not in bars_by_symbol:
                bars_by_symbol[symbol] = self.price_history.bars(market, symbol, available_before=cut)
            session = date.fromisoformat(str(record["session_date"])[:10])
            observations.append(observation(record, bars_by_symbol[symbol].get(session.isoformat()), self._labels(market, symbol, session, cut, calendar_close)))
        observations.sort(key=lambda row: (row["symbol"], row["session"], row["prediction_instant"]))  # the order every sum runs in
        horizons = {str(horizon): horizon_metrics(observations, horizon) for horizon in HORIZONS}
        decisory = horizons[str(DECISORY_HORIZON)]
        decided = decision(decisory["source_on_common_mask"]["mse"], decisory["consensus"]["mse"], decisory["common_mask"]["n"],
                           decisory["common_mask"]["names"], decisory["common_mask"]["sessions"], decisory["attrition"]["rate"])
        declared = horizon_metrics(observations, CONSENSUS_DECLARED_HORIZON)
        for key in ("source", "source_on_common_mask", "band_coverage", "diagnostic_only"):  # 252 sessions: the consensus at its declared horizon only
            declared.pop(key)
        declared["consensus_only"] = True
        aggregate = {
            "records": {"read": len(records), "admissible": len(kept), "refused": refusals, "reruns": sum(1 for row in observations if row["rerun_of"])},
            "observations": {**_mask_stats(observations), "basis": _counts(Counter(str(row["basis_status"]) for row in observations))},
            "vintage": self._vintage_header(market, cut),
            "last_closed_session": last_closed_session(market, cut),
            "cut_within_calendar_horizon": calendar_close is not None and calendar_close >= cut,  # false: beyond_calendar may hide matured targets; the receipt is then not (C, store) alone
            "horizons": horizons,
            "decision": decided,
            "consensus_declared_horizon": declared,
            "level_dispersion": level_dispersion(observations, lambda row: profile_label or str(row["source_version"])),
        }
        return aggregate, observations

    def run(self, *, cut: datetime, markets: Iterable[str] = MARKETS, sources: Iterable[str] = DEFAULT_SOURCES, since: datetime | None = None,
            until: datetime | None = None, profile_label: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """The panel as of ``cut`` (aware, explicit): ``(receipt, detail_rows)``. The receipt has no symbol; the detail
        rows are the observations with their symbols, for ``write_private_detail`` only."""
        cut_utc = _aware(cut, "cut")
        lower = _aware(since, "since") if since is not None else None
        upper = _aware(until, "until") if until is not None else None
        if lower is not None and upper is not None and lower >= upper:
            raise ValueError(f"since {lower.isoformat()} must precede until {upper.isoformat()}")
        market_list = [market.strip().upper() for market in markets]
        unknown = [market for market in market_list if market not in MARKETS]
        if unknown:
            raise ValueError(f"unknown markets {unknown}: the panel measures {list(MARKETS)}")
        source_list = [source.strip() for source in sources if source.strip()]
        if not source_list:
            raise ValueError("no sources: name at least one prediction source (e.g. official_blend_v1)")
        results: dict[str, dict[str, Any]] = {}
        detail: list[dict[str, Any]] = []
        for market in market_list:
            results[market] = {}
            for source in source_list:
                aggregate, observations = self.measure(market, source, cut=cut_utc, since=lower, until=upper, profile_label=profile_label)
                results[market][source] = aggregate
                detail.extend(observations)
        window = {"since": lower.isoformat() if lower else None, "until": upper.isoformat() if upper else None, "profile_label": profile_label}
        return receipt(cut=cut_utc, window=window, markets=market_list, sources=source_list, results=results), detail


# ------------------------------------------------------------------ CLI
def _cli_instant(parser: argparse.ArgumentParser, option: str, value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parser.error(f"{option} must be an ISO-8601 instant with a zone, e.g. 2026-09-14T00:00:00-03:00, got {value!r}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parser.error(f"{option} must carry a time zone (the clock rule: no naive instant, no now()), got {value!r}")
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valuation V3.2 §7.3 weekly panel: realized log-error vs the persisted consensus, attrition, level/dispersion, "
                                                 "band coverage — measurement only (no gate, nothing served changes, no network). Prints the receipt (no symbols).")
    parser.add_argument("--as-of", required=True, help="the cut C (ISO-8601 WITH zone; naive refused): records with published_at < C, bars available before C")
    parser.add_argument("--markets", default=",".join(MARKETS), help="comma-separated subset of B3,NASDAQ,NYSE (default: all three)")
    parser.add_argument("--sources", default=",".join(DEFAULT_SOURCES), help="comma-separated prediction sources, e.g. official_blend_v1,v3_2_shadow")
    parser.add_argument("--since", default=None, help="lower bound (inclusive) of prediction_instant, ISO-8601 with zone")
    parser.add_argument("--until", default=None, help="upper bound (exclusive) of prediction_instant, ISO-8601 with zone")
    parser.add_argument("--profile-label", default=None, help="label the level/dispersion profile with this instead of the record's source_version")
    parser.add_argument("--detail", type=Path, default=None, help="write the PRIVATE per-symbol detail to this NEW path (O_EXCL|O_NOFOLLOW, 0600)")
    args = parser.parse_args(argv)
    cut = _cli_instant(parser, "--as-of", args.as_of)
    since, until = _cli_instant(parser, "--since", args.since), _cli_instant(parser, "--until", args.until)
    assert cut is not None
    markets = [market.strip().upper() for market in args.markets.split(",") if market.strip()]
    if not markets or any(market not in MARKETS for market in markets):
        parser.error(f"--markets must be a non-empty subset of {','.join(MARKETS)}, got {args.markets!r}")
    sources = [source.strip() for source in args.sources.split(",") if source.strip()]
    if not sources:
        parser.error("--sources must name at least one prediction source")
    if args.detail is not None and (args.detail.is_symlink() or args.detail.exists()):
        parser.error(f"--detail {args.detail} exists (or is a symlink): the private detail is written to a NEW path only, nothing written")
    if since is not None and until is not None and since >= until:
        parser.error("--since must precede --until")
    database = Database(get_settings())
    service = PanelService(database, settings=get_settings())
    result, detail = service.run(cut=cut, markets=markets, sources=sources, since=since, until=until, profile_label=args.profile_label)
    if args.detail is not None:
        write_private_detail(args.detail, {"schema": f"{SCHEMA_VERSION}:detail", "cut": result["payload"]["cut"], "payload_sha256": result["payload_sha256"],
                                           "rows": detail})
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
