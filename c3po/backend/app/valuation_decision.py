"""Decisor V1 — the Valuation decides buy / no-buy, in SHADOW (owner's direction of 2026-10-17; migration 052).

Per name per night, one verdict with its reason codes, over the generation of the official selection in force:

* ``COMPRA_PERMITIDA`` — every gate passed: the name may be bought;
* ``OBSERVAR`` — the TP is trustworthy but there is no permission: no margin today (``PRICE_ABOVE_BUY_IN``,
  ``TP_MARGIN_INSUFFICIENT``), an input of the margin is not measured yet (``E_PROFILE_WARMING_UP``,
  ``E_PROFILE_UNAVAILABLE``, ``MARKET_RATE_UNAVAILABLE``) — no permission while the producers' calibration warms up —,
  (US) the TP awaits the revaluation a filing accepted after it triggered (``TP_STALE_AFTER_FILING``) or that question
  cannot be answered (``STALENESS_SOURCE_UNAVAILABLE``: no 053 table; ``STALENESS_SOURCE_STALE``: no live as-filed poll),
  or (US) an earnings announcement reaches the next N sessions (``EARNINGS_WITHIN_N``) or a calendar row of the name is
  unreadable and nothing else answers (``EARNINGS_CALENDAR_ROW_INVALID``);
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
  declared premium — B3: BCB SGS 432 (dated observations), else the Selic the official B3 cycle used (its
  ``outputs.macro.selic``: UNDATED — the producer records no observation date and may have used its governor constant —
  so admitted only when the block lists it in ``undated_rate_sources_admitted``); US: the 13-week T-bill (the R2D2 cash
  yield package), else the interpolated 5Y (the validated package, aged by its yields' observation date) — the first
  FRESH source of the declared order wins and is named in the record.
* freshness (VETO): ``tp_stale`` set on the row; the TP's session more than ``max_tp_age_sessions`` behind the last
  completed session; fundamentals older than a quarter + 45 days (or undated); the price moved more than
  ``max_price_move_percent`` since the cut (the TP record's price), or no price; the price not observed since the last
  completed session closed (``PRICE_SESSION_STALE``: the cut's own price is of the TP's session, so a TP one session
  behind is never decided on the session nobody observed — a cycle published after that close, or a fresh quote, is).
* quality (VETO): not validated (``tp_validation_status`` when the producer emits it — B3 —, else ``signal_quality`` —
  US); method dispersion above the limit (or unknown); confidence below the limit (or unknown); any data-defect mark.
* staleness after a filing (OBSERVAR; US only — migration 053 marks the US TPs against SEC filings, B3 is
  ``not_applicable``): a ``stale`` mark of the name KNOWN AT the run's clock (``valuation_asfiled.us_staleness_at``:
  only marks recorded — and inserted — by then, the latest state per filing; a ``cleared`` written later never reaches
  an earlier night) → ``TP_STALE_AFTER_FILING``, the filings (053 mark id, accession, form, acceptance) named in the
  record; the table absent (053 not applied) → ``STALENESS_SOURCE_UNAVAILABLE`` for every US name: fail closed, as
  every unmeasured input of a permission is (``E_PROFILE_UNAVAILABLE``, ``MARKET_RATE_UNAVAILABLE``). OBSERVAR, not
  VETO: the TP is not defective — it waits for the cut that revalues it (``TP_STALE_FLAG``, the producer's own mark on
  its row, stays a VETO: the producer declares that row untrustworthy, with no revaluation scheduled). An empty 053 is
  evidence only while the as-filed poll is alive, judged FIRST: a SUCCESSFUL ``sec_asfiled`` run with progress (a
  throttled pass is recorded ``partial``) that STARTED at or after D − ``staleness_poll_max_age_hours`` and completed by
  D − ε; without one every US name is ``STALENESS_SOURCE_STALE`` whether or not the table exists (fail closed).
* events (the block's ``event_gates`` says which withhold a permission; every other event code is a MARK — recorded in
  ``checks.events.marks``, never a verdict): ``EARNINGS_WITHIN_N`` — an announcement known at D whose report OR reaction
  session (AfterMarket and untimed releases react on the next session: an AMC on T counts) falls in [T+1, T+N]. The
  calendars read are every one received in [D − 36 h, D − ε] and the latest one received before that window: ANY of
  them with an in-window event of the name gates; otherwise "no event" is answered ONLY by the NEWEST USABLE calendar of
  the window (≥ ``earnings_calendar_min_us_events`` US events, unattributed invalid rows ≤
  ``earnings_calendar_max_invalid_share``, covering the window), and only when it lists the name and no calendar read
  has an invalid row of the name; in every other case the 051 cadence estimate answers (``EARNINGS_DATE_ESTIMATED``,
  within → gate); without one, an invalid row of the name fails closed (``EARNINGS_CALENDAR_ROW_INVALID``, a gate; a mark
  next to an estimate) and otherwise ``EARNINGS_CALENDAR_UNAVAILABLE``, no gate — gates on the US exchanges (market
  ``US`` included), marks on B3. ``CONSENSUS_EPS_CUT_30D`` and ``NEWS_SENTIMENT_NEGATIVE`` are marks (the latter never a gate:
  ``NEVER_GATES``). Every record keeps ``checks.counterfactual.verdict_without_events``: the verdict with the event gates
  off.
* ε (``insert_margin_seconds``): every read the event and 053 rules make on an insert clock — the poll's completion, 053
  ``created_at``, the calendar and consensus snapshots' publication, 051 ``first_seen_at``, the sentiment row's
  publication, the served record's publication — stops at D − ε; a served record published after D − ε is not decided
  (``tp_published_after_run_instant``). The decisor's other reads (the generation, the cycles, the calibration, the rate
  packages) stop at D, as they did before these rules.

Records (``valuation_decisions``) carry the discipline of ``valuation_predictions``: two clocks (``prediction_instant`` = the
run's clock; ``published_at`` read immediately before the insert, never before it), the session of the verdict (the last
completed session of the market's calendar — never a civil date; an unavailable calendar records nothing for that
market), the identity of the TP read (generation, source, cycle, row hash, prediction instant), ``inputs`` with the
provenance of every input and its ``inputs_sha256``, ``checks`` with every gate's numbers, the thresholds' hash and the
canonical ``row_sha256`` — recomputed and verified by every reader (``stored_decision``). Append-only; idempotent per
``(run_id, market, symbol)``; ``mode`` is ``shadow`` (the migration admits nothing else). Causal: the TP is read from the
generation IN FORCE AT the run's clock (``generation_at``, never a later one — a replay decides what that night saw), and
a served row predicted after the clock, or published after D − ε, is not decided. ``replay_sha256`` hashes what a
verdict decided without the run's identity: a re-run of the night reproduces it, the Finnhub sentiment excepted (its
source overwrites the week: the value read stays in the record, outside that hash).

The nightly phase (``valuation_worker``, flag ``C3PO_VALUATION_DECISOR_SHADOW``, default OFF) runs LAST, after the official
cut and every existing phase, and never writes the selection or any served number. ``run_shadow`` writes only when asked
(``write=True``) AND the flag is on; a run on a caller's quotes is a dry run, never a record: the nightly verdicts are
decided on the cut and the cycles published after it, and nothing intraday replaces them. A night is done when the latest
run decided over the generation in force (``last_run_at``): a generation activated later inside the window (a canonical
retry) is decided again. The R2D2 lab reads verdicts by symbol (``latest_verdict``/``latest_verdicts``): it names the
symbols it asks about — nothing here enumerates the names a verdict permits, and receipts are aggregate counts only. A
verdict is ``current`` only for its own session AND while the generation in force still serves the TP it read (the same
row hash: a targeted admission of another name keeps it, a source switch or a rollback does not).
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from . import valuation_env
from . import valuation_official as official
from .config import get_settings
from .sec_xbrl import EARNINGS_RELEASE_ITEM
from .valuation_asfiled import next_quarter_end, us_staleness_at
from .valuation_earnings_calendar import ANALYSIS_TYPE as CALENDAR_ANALYSIS, ENTITY_KEY as CALENDAR_ENTITY, calendars_at, filings_known_at
from .valuation_official import (MARKETS, CalendarUnavailable, canonical_sha256, current_generation, cycle_rows, generation_at, official_row, official_rows,
                                 session_date_of)
from .valuation_v3_macro import ValuationV3MacroDataError, package_hash_is_valid, validate_us_curve_package

logger = logging.getLogger(__name__)
NEW_YORK = ZoneInfo("America/New_York")

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
VERDICT_TP_NOT_SERVED = "VERDICT_TP_NOT_SERVED"  # the lab helper's downgrade of a verdict whose TP the generation in force no longer serves
VETO_CODES: tuple[str, ...] = (
    "TP_STALE_FLAG", "TP_SESSION_STALE", "FUNDAMENTALS_STALE", "FUNDAMENTALS_DATE_UNKNOWN", "PRICE_UNAVAILABLE", "PRICE_SESSION_STALE",
    "PRICE_MOVED_SINCE_CUT", "NOT_VALIDATED", "METHOD_DISPERSION_HIGH", "METHOD_DISPERSION_UNKNOWN", "CONFIDENCE_LOW", "CONFIDENCE_UNKNOWN",
    "DATA_DEFECT",
)
OBSERVAR_CODES: tuple[str, ...] = (
    "E_PROFILE_WARMING_UP", "E_PROFILE_UNAVAILABLE", "MARKET_RATE_UNAVAILABLE", "PRICE_ABOVE_BUY_IN", "TP_MARGIN_INSUFFICIENT",
    "TP_STALE_AFTER_FILING", "STALENESS_SOURCE_UNAVAILABLE", "STALENESS_SOURCE_STALE", "EARNINGS_WITHIN_N", "EARNINGS_CALENDAR_ROW_INVALID",
)
TP_STALE_AFTER_FILING = "TP_STALE_AFTER_FILING"  # a pending 053 'stale' mark known at the run's clock (US)
STALENESS_SOURCE_UNAVAILABLE = "STALENESS_SOURCE_UNAVAILABLE"  # the 053 table absent: no US name is permitted (fail closed)
STALENESS_SOURCE_STALE = "STALENESS_SOURCE_STALE"  # no live as-filed poll observed in [D − 6 h, D − ε]: an empty 053 is no evidence (fail closed)
# events (the block's ``event_gates`` says which withhold a permission; the others are MARKS: recorded, never a verdict)
EARNINGS_WITHIN_N = "EARNINGS_WITHIN_N"  # an announcement known at D on sessions [T+1, T+N] (a gate in earnings_gate_markets)
EARNINGS_DATE_ESTIMATED = "EARNINGS_DATE_ESTIMATED"  # the 051 cadence estimate answered (no usable calendar, no calendar row for the name, or an invalid row of it)
EARNINGS_CALENDAR_UNAVAILABLE = "EARNINGS_CALENDAR_UNAVAILABLE"  # no calendar answer for the name and no estimate: no gate (an abstention rule)
# a calendar read has an invalid row of the name: with no 051 estimate a GATE wherever EARNINGS_WITHIN_N gates (fail closed:
# an unreadable provider row about the name is a warning, not evidence of no event); with an estimate, a mark
EARNINGS_CALENDAR_ROW_INVALID = "EARNINGS_CALENDAR_ROW_INVALID"
CONSENSUS_EPS_CUT_30D = "CONSENSUS_EPS_CUT_30D"  # FY1 consensus EPS cut over the last 30 days beyond the block's limit
NEWS_SENTIMENT_NEGATIVE = "NEWS_SENTIMENT_NEGATIVE"  # the weekly Finnhub sentiment read at D is bearish beyond the block's limit (never a gate)
EVENT_CODES: tuple[str, ...] = (EARNINGS_WITHIN_N, EARNINGS_CALENDAR_ROW_INVALID, EARNINGS_DATE_ESTIMATED, EARNINGS_CALENDAR_UNAVAILABLE,
                                CONSENSUS_EPS_CUT_30D, NEWS_SENTIMENT_NEGATIVE)
MARK_CODES: tuple[str, ...] = (EARNINGS_DATE_ESTIMATED, EARNINGS_CALENDAR_UNAVAILABLE, CONSENSUS_EPS_CUT_30D, NEWS_SENTIMENT_NEGATIVE)
NEVER_GATES: tuple[str, ...] = (NEWS_SENTIMENT_NEGATIVE,)  # its source overwrites the week: a verdict on it could not be replayed

STALENESS_SOURCE = "valuation_tp_staleness"  # migration 053, read causally by valuation_asfiled.us_staleness_at
STALENESS_CLEAR, STALENESS_STALE, STALENESS_UNAVAILABLE, STALENESS_NOT_APPLICABLE = "clear", "stale", "unavailable", "not_applicable"
US_STALENESS_MARKETS = ("NASDAQ", "NYSE", "US")  # 053 marks only the US TPs (SEC filings); a US row is never 'not_applicable'

RATE_B3_CYCLE_SELIC = "b3_cycle_selic"  # outputs.macro.selic of the generation's B3 universe cycle (the producer's effective Selic; UNDATED)
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
    max_quote_age_minutes: int = 15  # a caller's quote older than this at the run's clock is refused (a dry run's quotes only)
    validated_status: str = "validated"
    max_method_dispersion_percent: float = 45.0  # the producers' own MAX_METHOD_DISPERSION / MAX_DISPERSION
    min_valuation_confidence: float = 70.0  # the producers' own MIN_VALUATION_CONFIDENCE / MIN_CONFIDENCE
    data_defect_fields: tuple[str, ...] = ("data_defect", "data_defects")  # a producer mark under any of these (truthy) vetoes
    min_profile_samples: int = 15  # the producers' CALIBRATION_MIN_PROFILE_SAMPLES
    calibration_min_horizon_days: int = 60
    calibration_max_horizon_days: int = 150  # the producers' active window for the observed horizon
    calibration_max_age_days: int = 7  # a calibration snapshot older than this is not a measurement of tonight's producer
    allow_global_error_fallback: bool = False  # a profile below its minimum samples borrows the global error only if True
    b3_rate_sources: tuple[str, ...] = (RATE_BCB_SGS_432, RATE_B3_CYCLE_SELIC)
    us_rate_sources: tuple[str, ...] = (RATE_US_TBILL_13W, RATE_US_5Y)
    undated_rate_sources_admitted: tuple[str, ...] = ()  # an UNDATED source (the B3 cycle's Selic) counts only if listed here — aged by its cycle's publication
    market_rate_max_age_days: int = 10
    tp_horizon_years: float = 1.0  # a 12-month TP: h_market = (1 + rate) ** years - 1 + premium
    market_premium: float = 0.0
    # every read on an INSERT clock (the poll's completion, 053 created_at, a snapshot's publication, 051 first_seen_at, the
    # sentiment row's publication, the TP record's publication) stops at D − ε: a commit racing the run's read is out of the
    # original AND of every replay
    insert_margin_seconds: int = 60
    # US filings (053): the marks are evidence only while the as-filed poll is alive at D
    staleness_poll_source: str = "sec_asfiled"  # the ingestion_runs source of the as-filed poll (InvestorRelationsService.sync_sec_asfiled)
    staleness_poll_max_age_hours: int = 6  # a SUCCESSFUL poll with progress, STARTED at or after D − 6 h and completed by D − ε
    # events
    earnings_window_sessions: int = 2  # N: an announcement reaching sessions [T+1, T+N] of the market (T = the last completed session)
    earnings_gate_markets: tuple[str, ...] = ("NASDAQ", "NYSE")  # EARNINGS_WITHIN_N withholds the permission here; elsewhere (B3) it is a mark
    earnings_calendar_max_age_hours: int = 36  # only a calendar received in [D − 36 h, D − ε] may say "no event"; any calendar's events gate
    earnings_calendar_min_us_events: int = 100  # a calendar with fewer US events in its request window is partial: it says nothing
    earnings_calendar_max_invalid_share: float = 0.05  # ...nor one whose unattributed invalid rows exceed this share of its rows
    earnings_filings_lookback_days: int = 400  # the 051 filings the estimate reads (a year of quarters, plus the seasonal base)
    earnings_estimate_seasonal_days: int = 364  # the estimate: the same fiscal quarter's release one year earlier + 364 days...
    earnings_estimate_period_match_days: int = 10  # ...that quarter found by its period end within this many days of a year before
    earnings_estimate_offset_days: int = 91  # else the most recent original 8-K 2.02 / 10-Q acceptance + 91 days (a 10-K: period end + 91 + lag)
    earnings_estimate_default_10q_lag_days: int = 45  # a 10-K base adds the issuer's latest 10-Q filing lag, else this
    earnings_estimate_tolerance_days: int = 7  # an estimate counts when it reaches the window widened by this many days on each side
    consensus_eps_cut_log: float = 0.05  # CONSENSUS_EPS_CUT_30D: ln(FY1 at D / FY1 at D − 30 d) < −0.05 (or turned non-positive)
    consensus_lookback_days: int = 30
    news_sentiment_bearish_min_percent: float = 60.0  # NEWS_SENTIMENT_NEGATIVE: bearish ≥ 60 %...
    news_sentiment_min_articles: int = 5  # ...over at least 5 articles in the provider's last week...
    news_sentiment_max_age_days: int = 8  # ...in a weekly row read at D, first published at most 8 days before it
    event_gates: tuple[str, ...] = (EARNINGS_WITHIN_N,)  # the event codes that withhold a permission (OBSERVAR); every other one is a mark
    # (NEWS_SENTIMENT_NEGATIVE is a mark whatever this lists: NEVER_GATES)


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
    raw_outputs = snapshot.get("outputs")
    outputs: Mapping[str, Any] = raw_outputs if isinstance(raw_outputs, Mapping) else {}
    raw_metrics = outputs.get("metrics")
    metrics: Mapping[str, Any] = raw_metrics if isinstance(raw_metrics, Mapping) else {}
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
        if _text(outputs.get("available_at")) and _utc(outputs["available_at"]) > at:
            return {**candidate, "detail": "the observation was not available at the run's clock"}
        rate, observed = _positive(outputs.get("annual_rate")), _text(outputs.get("observation_date"))
    else:
        # the 5Y is aged by its YIELDS' observation date, never by the package's as_of (the date the operator asked for:
        # the producer takes the latest yield within 30 days of it) — the package validated as V3 validates it
        try:
            rate = _positive(validate_us_curve_package(dict(outputs), as_of=date.fromisoformat(str(outputs.get("as_of") or ""))))
        except (ValuationV3MacroDataError, ValueError) as error:
            return {**candidate, "detail": f"package does not validate: {error}"}
        points = [point for point in outputs.get("points") or [] if isinstance(point, Mapping)]
        if any(_utc(point["available_at"]) > at for point in points):
            return {**candidate, "detail": "a yield was not available at the run's clock"}
        observed = _text(points[0].get("observation_date")) if points else None  # validated: both tenors share one observation date
    return {**candidate, "annual_rate": rate, "observed_at": observed, "detail": None if rate is not None else "no usable observation"}


def market_rate(database: Any, market: str, *, at: datetime, generation: Mapping[str, Any] | None,
                thresholds: DecisorThresholds = THRESHOLDS) -> dict[str, Any]:
    """``h_market``: the market rate over the TP horizon plus the declared premium, from the FIRST source of the declared
    order (B3: ``b3_rate_sources``; US: ``us_rate_sources``) whose observation is positive and no older than
    ``market_rate_max_age_days`` at ``at``. ``status`` ``ok`` names the source, its reference (snapshot / cycle id,
    package hash), the observation and the annual rate; ``unavailable`` lists what was tried. An UNDATED source (the B3
    cycle's Selic: the cycle records no observation date, and its producer falls back to a hard-coded governor constant
    when both of its feeds fail — indistinguishable in the cycle) is tried and refused unless the block lists it in
    ``undated_rate_sources_admitted``; admitted, it is aged by its cycle's publication and recorded ``undated``."""
    sources = thresholds.b3_rate_sources if market == "B3" else thresholds.us_rate_sources
    tried: list[dict[str, Any]] = []
    for source in sources:
        if source == RATE_B3_CYCLE_SELIC:
            cycle_id = ((generation or {}).get("cycles") or {}).get("B3")
            snapshot = database.official_cycle_snapshot(str(cycle_id)) if cycle_id else None
            if snapshot and (not snapshot.get("published_at") or _utc(snapshot["published_at"]) > at):
                snapshot = None  # causal: a cycle published after the run's clock was not there to be read
            macro = (snapshot.get("outputs") or {}).get("macro") if snapshot and isinstance(snapshot.get("outputs"), Mapping) else None
            candidate = {"source": source, "reference": f"valuation_universe/B3_UNIVERSE#{cycle_id}" if cycle_id else None,
                         "snapshot_id": str(cycle_id) if cycle_id else None, "payload_sha256": None, "undated": True,
                         "annual_rate": _positive((macro or {}).get("selic")) if isinstance(macro, Mapping) else None,
                         "observed_at": _utc(snapshot["published_at"]).isoformat() if snapshot else None}
            if candidate["annual_rate"] is None:
                candidate["detail"] = "the B3 cycle carries no macro.selic"
            elif source not in thresholds.undated_rate_sources_admitted:
                candidate["detail"] = "undated: the cycle records macro.selic without its observation date (the producer's governor constant cannot be " \
                                      "told from a BCB observation) — not admitted by the block"
                tried.append({key: candidate.get(key) for key in ("source", "reference", "detail")})
                continue
            else:
                candidate["detail"] = None
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
                rate = float(cast(float, candidate["annual_rate"]))  # checked not None above
                hurdle = (1 + rate) ** thresholds.tp_horizon_years - 1 + thresholds.market_premium
                return {"status": "ok", **candidate, "undated": bool(candidate.get("undated")), "h_market": hurdle,
                        "tp_horizon_years": thresholds.tp_horizon_years, "market_premium": thresholds.market_premium, "tried": tried}
        tried.append({key: candidate.get(key) for key in ("source", "reference", "detail")})
    return {"status": "unavailable", "source": None, "annual_rate": None, "h_market": None, "tried": tried}


def _session_or_none(market: str, instant: datetime) -> str | None:
    try:
        return session_date_of(market, instant)
    except CalendarUnavailable:
        return None


def _price_observation(row: Mapping[str, Any], *, market: str, symbol: str, at: datetime, quotes: Mapping[tuple[str, str], Mapping[str, Any]] | None,
                       latest_universe: Mapping[str, Any] | None, thresholds: DecisorThresholds = THRESHOLDS) -> dict[str, Any]:
    """The price the verdict is taken at, with the market ``session`` it belongs to (``decide`` vetoes a price of a session
    before the last completed one, ``PRICE_SESSION_STALE``):

    * a quote the caller hands over (``quotes[(market, symbol)]``: ``price``, optional ``ask``, ``as_of``, ``source``; a dry
      run only) — its session is the last completed one at its ``as_of``. Refused, and named in ``quote_refused``, without a
      positive price, without a readable ``as_of``, with an ``as_of`` after the run's clock or older than
      ``max_quote_age_minutes``: the next source answers;
    * else the newest universe cycle of the market published AFTER the TP's cut that quotes the symbol (the generation may
      carry an older cycle) — its session the last completed one at its publication;
    * else the cut's own price (the TP record's), of the TP's own session.

    ``price`` is ``None`` when no source has one."""
    refused: str | None = None
    quote = (quotes or {}).get((market, symbol))
    if quote is not None:
        price = _positive(quote.get("price"))
        try:
            quoted_at = _utc(quote["as_of"]) if _text(quote.get("as_of")) else None
        except (TypeError, ValueError):
            quoted_at = None
        if price is None:
            refused = "no positive price"
        elif quoted_at is None:
            refused = "no readable as_of"
        elif quoted_at > at:
            refused = "as_of after the run's clock"
        elif at - quoted_at > timedelta(minutes=thresholds.max_quote_age_minutes):
            refused = f"older than {thresholds.max_quote_age_minutes} minutes at the run's clock"
        else:
            return {"price": price, "ask": _positive(quote.get("ask")), "as_of": quoted_at.isoformat(), "session": _session_or_none(market, quoted_at),
                    "source": _text(quote.get("source")) or "quote", "reference": _text(quote.get("reference")), "quote_refused": None}
    if latest_universe and latest_universe.get("published_at") and str(latest_universe.get("id")) != str(row.get("official_cycle_id")) \
            and _utc(latest_universe["published_at"]) > _utc(row["prediction_instant"]):
        for candidate in cycle_rows({**latest_universe, "analysis_type": official.UNIVERSE_ANALYSIS}):
            if str(candidate.get("symbol") or "").strip().upper() == symbol and _positive(candidate.get("price")) is not None:
                return {"price": _positive(candidate.get("price")), "ask": None, "as_of": _text(candidate.get("as_of")),
                        "session": _session_or_none(market, _utc(latest_universe["published_at"])), "source": "latest_universe_cycle",
                        "reference": str(latest_universe.get("id")), "quote_refused": refused}
    price = _positive(row.get("price"))
    if price is None:
        return {"price": None, "ask": None, "as_of": None, "session": None, "source": None, "reference": None, "quote_refused": refused}
    return {"price": price, "ask": None, "as_of": _text(row.get("as_of")), "session": _text(row.get("official_session_date")), "source": "official_cut",
            "reference": _text(row.get("official_cycle_id")), "quote_refused": refused}


def _filing_reference(mark: Mapping[str, Any]) -> dict[str, Any]:
    """What a record keeps of one 053 mark: its own id, the filing (accession, form, items, acceptance), when the trigger
    recorded it, why, and what the TP has to reach — enough to find the mark again, nothing the table does not hold."""
    return {"mark_id": _text(mark.get("id")), "doc_id": _text(mark.get("doc_id")), "form": _text(mark.get("form")), "items": _text(mark.get("items")),
            "accepted_at": _utc(mark["accepted_at"]).isoformat() if mark.get("accepted_at") else None,
            "recorded_at": _utc(mark["recorded_at"]).isoformat() if mark.get("recorded_at") else None, "reason": _text(mark.get("reason")),
            "expected_period_end": _text(mark.get("expected_period_end")), "official_cycle_id": _text(mark.get("official_cycle_id"))}


def poll_reference(run: Mapping[str, Any] | None, source_code: str) -> dict[str, Any] | None:
    """What a record keeps of the as-filed poll it relied on: the source, the run id, what it read and when it ran."""
    if not run or not run.get("completed_at"):
        return None
    metadata = run.get("metadata") if isinstance(run.get("metadata"), Mapping) else {}
    failed = (metadata or {}).get("failed_issuers")
    return {"source_code": source_code, "run_id": _text(run.get("id")), "records_read": int(run.get("records_read") or 0),
            "started_at": _utc(run["started_at"]).isoformat() if run.get("started_at") else None, "completed_at": _utc(run["completed_at"]).isoformat(),
            "issuers_not_observed": len(failed) if isinstance(failed, list) else None}


def failed_issuers(run: Mapping[str, Any] | None) -> list[str]:
    """The issuers (CIKs) the as-filed poll did not observe (its run metadata, ``failed_issuers``)."""
    metadata = (run or {}).get("metadata") if isinstance((run or {}).get("metadata"), Mapping) else {}
    failed = (metadata or {}).get("failed_issuers")
    return sorted({str(item) for item in failed}) if isinstance(failed, list) else []


def _poll_fresh(poll: Mapping[str, Any] | None, known_at: Any, thresholds: DecisorThresholds) -> bool:
    """The as-filed poll is alive at the read's clock D: a SUCCESSFUL run with progress (the reader already asked for
    both) that STARTED at or after D − ``staleness_poll_max_age_hours`` — its observations are that recent — and completed
    by D − ε (the reader's cutoff)."""
    if not poll or not poll.get("started_at") or not poll.get("completed_at") or not known_at:
        return False
    clock = _utc(known_at)
    started, completed = _utc(poll["started_at"]), _utc(poll["completed_at"])
    return (clock - timedelta(hours=thresholds.staleness_poll_max_age_hours) <= started <= completed
            <= clock - timedelta(seconds=thresholds.insert_margin_seconds))


def name_staleness(source: Mapping[str, Any] | None, market: str, symbol: str, *, thresholds: DecisorThresholds = THRESHOLDS,
                   issuer_key: str | None = None) -> dict[str, Any]:
    """What ``decide`` reads about ONE name from the causal read of migration 053 (``valuation_asfiled.us_staleness_at``
    at the run's clock, ``source``, with the as-filed poll it relied on in ``trigger_poll``): B3 → ``not_applicable``
    (053 marks US TPs against SEC filings only). A US name: the poll is judged FIRST — no live poll (``_poll_fresh``)
    → ``source_status`` ``stale`` whether or not the table exists (an absent table then reads as an empty one: a night
    from before 053 replays identically once it lands), the marks known still listed; a live poll and no table →
    ``unavailable``; else ``ok``. A live poll covers a name only if it observed the name's issuer (``issuer_key``, from
    the 051 filings known at D): an issuer in the poll's ``failed_issuers`` — or, when the poll missed any issuer, a name
    whose issuer is unknown — is ``source_status`` ``stale`` too. ``status``: ``stale`` with the pending filings,
    ``clear``, or ``unavailable``."""
    if market not in US_STALENESS_MARKETS:
        return {"status": STALENESS_NOT_APPLICABLE, "source_status": None, "source": None, "detail": "migration 053 marks US TPs only (SEC filings)",
                "filings": []}
    read = dict(source or {})
    poll = read.get("trigger_poll") if isinstance(read.get("trigger_poll"), Mapping) else None
    fresh = _poll_fresh(poll, read.get("known_at"), thresholds)
    missed = {str(item) for item in read.get("failed_issuers") or []}
    uncovered = fresh and bool(missed) and (issuer_key is None or str(issuer_key) in missed)
    fresh = fresh and not uncovered
    table = read.get("status") == "ok"
    if not fresh and not table:  # nobody looked, and nothing was there to look at: the same record as an empty table
        read.update({"marks_known": 0, "latest_recorded_at": None, "pending": {}})
    base = {"source": STALENESS_SOURCE, "known_at": read.get("known_at"), "marks_known": read.get("marks_known"),
            "latest_recorded_at": read.get("latest_recorded_at"), "trigger_poll": dict(poll) if poll else None,
            "poll_max_age_hours": thresholds.staleness_poll_max_age_hours}
    base["issuer_observed"] = None if not poll else not uncovered
    if fresh and not table:
        return {**base, "status": STALENESS_UNAVAILABLE, "source_status": STALENESS_UNAVAILABLE,
                "detail": _text(read.get("detail")) or "the staleness source was not read", "filings": []}
    pending = read.get("pending") if isinstance(read.get("pending"), Mapping) else {}
    marks = [mark for mark in (pending or {}).get(symbol) or [] if isinstance(mark, Mapping)]
    return {**base, "status": STALENESS_STALE if marks else STALENESS_CLEAR, "source_status": "ok" if fresh else STALENESS_STALE,
            "detail": None if fresh else (
                ("the live poll did not observe the name's issuer" if issuer_key is not None else
                 "the live poll missed issuers and the name's issuer is unknown") + ": the marks known are kept, their absence is no evidence"
                if uncovered else
                f"no live {thresholds.staleness_poll_source} poll (successful, with progress, started in the "
                f"{thresholds.staleness_poll_max_age_hours} h before the run's clock): the marks known are kept, their absence is no evidence"),
            "filings": [_filing_reference(mark) for mark in marks]}


# ------------------------------------------------------------------ inputs: events (earnings, consensus, sentiment)


def _exchange_calendar(market: str) -> Any:
    """The exchange calendar of a market; the aggregate ``US`` (NASDAQ ∪ NYSE) reads XNYS like both of its exchanges."""
    return official._calendar("NYSE" if market == "US" else market)


def _calendar_sessions(market: str, expected_session: str, count: int) -> list[str] | None:
    """Sessions T+1 … T+count of the market's exchange calendar (T = ``expected_session``); ``None`` when it cannot say."""
    if count <= 0:
        return []
    try:
        window = _exchange_calendar(market).sessions_window(expected_session, count + 1)
        sessions = [stamp.date().isoformat() for stamp in window]
    except Exception:
        return None
    if len(sessions) != count + 1 or sessions[0] != expected_session:
        return None
    return sessions[1:]


def _session_on_or_after(market: str, day: str) -> str | None:
    """The session an announcement dated ``day`` reaches: ``day`` itself when it is a session, else the next one."""
    try:
        return _exchange_calendar(market).date_to_session(day, direction="next").date().isoformat()
    except Exception:
        return None


def reaction_sessions(market: str, report_date: str, timing: str | None) -> tuple[str | None, str | None]:
    """(report session, reaction session) of an announcement: the report session is the date's session (the next one
    for a date that is no session); the session whose PRICE reacts is that same session for a BeforeMarket release, the
    NEXT session after the date for an AfterMarket release or an unknown timing (the provider's day-only rows) — the gap
    risk: the price the night decides on has not seen the news yet."""
    report = _session_on_or_after(market, report_date)
    if report is None:
        return None, None
    if timing == "BeforeMarket":
        return report, report
    if report != report_date:  # a date that is no session: the next session is both
        return report, report
    try:
        return report, _exchange_calendar(market).next_session(report_date).date().isoformat()
    except Exception:
        return report, None


def _provider_codes(market: str, symbol: str) -> list[str]:
    """The calendar's codes of a symbol: ``<S>.SA`` on B3; ``<S>.US`` on the US exchanges (also with ``.`` → ``-``, the
    provider's spelling of share classes: BRK.B → BRK-B.US)."""
    if market == "B3":
        return [f"{symbol}.SA"]
    return list(dict.fromkeys([f"{symbol}.US", f"{symbol.replace('.', '-')}.US"]))


def _calendar_usable(calendar: Mapping[str, Any], window: list[str], thresholds: DecisorThresholds) -> str | None:
    """Why a calendar cannot say "no event" (``None`` when it can): partial (fewer US events in its request window than
    ``earnings_calendar_min_us_events``), garbled (unattributed invalid rows above ``earnings_calendar_max_invalid_share``)
    or not covering [T+1, T+N]."""
    if int(calendar.get("us_events") or 0) < max(thresholds.earnings_calendar_min_us_events, 1):
        return f"partial: {int(calendar.get('us_events') or 0)} US events in its window (< {thresholds.earnings_calendar_min_us_events})"
    if float(calendar.get("invalid_share") or 0.0) > thresholds.earnings_calendar_max_invalid_share:
        return f"garbled: unattributed invalid rows above {thresholds.earnings_calendar_max_invalid_share:.0%} of its rows"
    if window and not (str(calendar.get("request_from") or "9999") <= window[0] and window[-1] <= str(calendar.get("request_to") or "")):
        return "its request window does not cover sessions T+1..T+N"
    return None


def _add_days(day: date, days: int) -> str:
    return (day + timedelta(days=days)).isoformat()


def cadence_estimate(filings: list[Mapping[str, Any]], thresholds: DecisorThresholds = THRESHOLDS) -> dict[str, Any] | None:
    """The next earnings date the name's ORIGINAL filings (8-K 2.02, 10-Q, 10-K; amendments never) suggest, ``None``
    without any:

    * ``seasonal`` — the quarter after the latest statement period, one year earlier: its release (the first 8-K 2.02
      accepted after that period ended and before the next quarter ended; else its own 10-Q/10-K) + 364 days, the
      weekday kept; the period found within ``earnings_estimate_period_match_days`` of a year before;
    * ``recent`` — else the MORE RECENT of the last 8-K 2.02 / 10-Q / 10-K: an 8-K or 10-Q acceptance + 91 days; a 10-K
      period end + 91 days + the issuer's latest 10-Q filing lag (acceptance − period end; else the default lag).

    Acceptance days are New York's; the base is the ACCEPTANCE, never the registration (a backfill moves nothing)."""
    def accepted_day(item: Mapping[str, Any]) -> date:
        return _utc(item["accepted_at"]).astimezone(NEW_YORK).date()

    def period(item: Mapping[str, Any]) -> date | None:
        try:
            return date.fromisoformat(str(item.get("period_of_report"))[:10]) if item.get("period_of_report") else None
        except ValueError:
            return None

    originals = [item for item in filings if str(item.get("form") or "") in ("8-K", "10-Q", "10-K")]
    releases = sorted((item for item in originals if item["form"] == "8-K" and EARNINGS_RELEASE_ITEM in str(item.get("items") or "").split(",")),
                      key=lambda item: _utc(item["accepted_at"]))
    statements = sorted((item for item in originals if item["form"] in ("10-Q", "10-K") and period(item) is not None),
                        key=lambda item: _utc(item["accepted_at"]))
    if statements:
        latest_period = max(cast(date, period(item)) for item in statements)
        upcoming = next_quarter_end(latest_period)
        target = upcoming - timedelta(days=thresholds.earnings_estimate_seasonal_days)
        prior = [item for item in statements if abs((cast(date, period(item)) - target).days) <= thresholds.earnings_estimate_period_match_days]
        if prior:
            statement = min(prior, key=lambda item: abs((cast(date, period(item)) - target).days))
            prior_end = cast(date, period(statement))
            following = next_quarter_end(prior_end)
            release = next((item for item in releases if prior_end < accepted_day(item) <= following), None)
            base = release or statement
            return {"rule": "seasonal", "basis": dict(base), "prior_period_end": prior_end.isoformat(), "upcoming_period_end": upcoming.isoformat(),
                    "days": thresholds.earnings_estimate_seasonal_days, "estimated_date": _add_days(accepted_day(base), thresholds.earnings_estimate_seasonal_days)}
    candidates = [item for item in (releases[-1] if releases else None,
                                    next((item for item in reversed(statements) if item["form"] == "10-Q"), None),
                                    next((item for item in reversed(statements) if item["form"] == "10-K"), None)) if item is not None]
    if not candidates:
        return None
    base = max(candidates, key=lambda item: _utc(item["accepted_at"]))
    if base["form"] == "10-K" and period(base) is not None:
        quarterly = next((item for item in reversed(statements) if item["form"] == "10-Q"), None)
        lag = (accepted_day(quarterly) - cast(date, period(quarterly))).days if quarterly else thresholds.earnings_estimate_default_10q_lag_days
        return {"rule": "recent", "basis": dict(base), "lag_days": lag, "lag_basis": quarterly["doc_id"] if quarterly else "default",
                "days": thresholds.earnings_estimate_offset_days,
                "estimated_date": _add_days(cast(date, period(base)), thresholds.earnings_estimate_offset_days + lag)}
    return {"rule": "recent", "basis": dict(base), "days": thresholds.earnings_estimate_offset_days,
            "estimated_date": _add_days(accepted_day(base), thresholds.earnings_estimate_offset_days)}


def _estimate_within(market: str, estimate: Mapping[str, Any], window: list[str], thresholds: DecisorThresholds) -> dict[str, Any]:
    report, reaction = reaction_sessions(market, str(estimate["estimated_date"]), None)  # an estimate has no timing: unknown
    low = _add_days(date.fromisoformat(window[0]), -thresholds.earnings_estimate_tolerance_days)
    high = _add_days(date.fromisoformat(window[-1]), thresholds.earnings_estimate_tolerance_days)
    within = any(session is not None and low <= session <= high for session in (report, reaction))
    return {**dict(estimate), "report_session": report, "reaction_session": reaction, "tolerance_days": thresholds.earnings_estimate_tolerance_days,
            "range": [low, high], "within": within}


def name_earnings(calendars: Mapping[str, Any] | None, filings: Mapping[str, Any] | None, market: str, symbol: str, *, at: datetime,
                  expected_session: str, thresholds: DecisorThresholds = THRESHOLDS) -> dict[str, Any]:
    """The earnings facts of ONE name at the run's clock ``at`` — ``within`` when an announcement reaches sessions
    [T+1, T+N] (N = ``earnings_window_sessions``) by its report session or its reaction session (``reaction_sessions``:
    an AfterMarket or untimed release on T reacts on T+1 and counts). The calendars read
    (``valuation_earnings_calendar.calendars_at``) are every one received in [D − ``earnings_calendar_max_age_hours``,
    D − ε] and the latest one received before that window:

    1. GATE (``calendar``, within) when ANY calendar read — usable or not, recent or not — has an event of the name whose
       report or reaction session is in the window;
    2. otherwise "no event" (``calendar``, not within) is answered ONLY by the NEWEST USABLE calendar of the window
       (``_calendar_usable``), and only when it has a valid row of the name (out of the window) and NO calendar read has
       an invalid row of the name;
    3. in every other case (no usable calendar; the newest usable one without a row of the name; an invalid row of the
       name anywhere) the 051 cadence estimate (``cadence_estimate``, US) answers: ``estimated`` — within → gate, else no
       gate; without an estimate ``row_invalid`` when a calendar read has an invalid row of the name (fail closed:
       ``EARNINGS_CALENDAR_ROW_INVALID``), else ``unavailable``, no gate (an abstention rule fails open, and says why).
       ``row_invalid`` (the flag) records an invalid row of the name whatever answered."""
    window = _calendar_sessions(market, expected_session, thresholds.earnings_window_sessions)
    base: dict[str, Any] = {"window": window, "window_sessions": thresholds.earnings_window_sessions, "calendars": [], "estimate": None,
                            "events": [], "within": False, "row_invalid": False}
    if window is None:
        return {**base, "status": "unavailable", "detail": "the exchange calendar cannot name sessions T+1..T+N"}
    read = calendars or {}
    recent = sorted((item for item in read.get("recent") or [] if isinstance(item, Mapping)), key=lambda item: str(item.get("received_at")))
    older = read.get("older") if isinstance(read.get("older"), Mapping) else None
    pool = [*([older] if older else []), *recent]  # oldest first
    recent_ids = {str(item["snapshot_id"]) for item in recent}
    codes = _provider_codes(market, symbol)
    events: list[dict[str, Any]] = []
    for calendar in pool:
        for code in codes:
            for event in (calendar.get("by_code") or {}).get(code) or []:
                report_date, timing = str(event.get("report_date") or ""), event.get("timing")
                report, reaction = reaction_sessions(market, report_date, timing)
                events.append({"code": code, "report_date": report_date, "fiscal_period_end": event.get("fiscal_period_end"), "timing": timing,
                               "report_session": report, "reaction_session": reaction, "snapshot_id": str(calendar["snapshot_id"]),
                               "in_window": any(session is not None and session in window for session in (report, reaction))})
    blocked = [str(calendar["snapshot_id"]) for calendar in pool if any((calendar.get("blocking_codes") or {}).get(code) for code in codes)]
    judged = []
    for calendar in pool:
        snapshot_id = str(calendar["snapshot_id"])
        refused = _calendar_usable(calendar, window, thresholds)
        if refused is None and snapshot_id not in recent_ids:
            refused = f"received more than {thresholds.earnings_calendar_max_age_hours} h before the run's clock"
        judged.append({**{key: calendar.get(key) for key in ("snapshot_id", "received_at", "payload_sha256", "request_from", "request_to",
                                                            "us_events", "invalid_share")},
                       "refused": refused, "lists_name": any((calendar.get("by_code") or {}).get(code) for code in codes),
                       "invalid_row_of_name": snapshot_id in blocked})
    usable = [item for item in judged if item["refused"] is None]
    newest = usable[-1] if usable else None  # judged follows the pool: oldest first
    base.update({"calendars": judged, "events": events, "answering": newest["snapshot_id"] if newest else None, "row_invalid": bool(blocked)})
    estimate_raw = None
    if market in US_STALENESS_MARKETS and (filings or {}).get("status") == "ok":
        estimate_raw = cadence_estimate(list(((filings or {}).get("by_symbol") or {}).get(symbol) or []), thresholds)
    estimate = _estimate_within(market, estimate_raw, window, thresholds) if estimate_raw and window else None
    base["estimate"] = estimate
    if any(item["in_window"] for item in events):  # 1. any calendar's in-window event gates
        return {**base, "status": "calendar", "within": True, "detail": None}
    if newest is not None and newest["lists_name"] and not blocked:  # 2. the newest usable calendar lists the name, nobody contradicts it
        return {**base, "status": "calendar", "within": False, "detail": None}
    if blocked:  # 3. the estimate answers — and why
        why = f"an invalid row of the name in {', '.join(blocked)}"
    elif newest is not None:
        why = f"the newest usable calendar ({newest['snapshot_id']}) has no row of the name"
    else:
        why = "no usable calendar: " + ("; ".join(f"{item['snapshot_id']}: {item['refused']}" for item in judged) or "none received by the run's clock")
    if estimate is not None:
        return {**base, "status": "estimated", "within": bool(estimate["within"]), "detail": why}
    tail = "no 051 earnings filing known for the name" if market in US_STALENESS_MARKETS else "no estimate outside the US"
    if blocked:  # an unreadable provider row about the name and nothing else to say: fail closed (EARNINGS_CALENDAR_ROW_INVALID)
        return {**base, "status": "row_invalid", "within": False, "detail": f"{why}; {tail}"}
    return {**base, "status": "unavailable", "within": False, "detail": f"{why}; {tail}"}


def _eps(row: Any) -> float | None:
    return _number(row.get("eps_avg")) if isinstance(row, Mapping) else None


def name_consensus(current: Mapping[str, Any] | None, past: Mapping[str, Any] | None, symbol: str, *,
                   thresholds: DecisorThresholds = THRESHOLDS) -> dict[str, Any]:
    """The FY1 consensus EPS of ONE name now and ``consensus_lookback_days`` ago (``Database.v2_forward_eps_at_or_before``:
    ``current`` the latest ``valuation_v2_data`` snapshot published by D − ε, ``past`` the latest by D − 30 d − ε) — a
    30-day revision, never the ~24 h one the nightly re-cut of the TP would give. The SAME fiscal year is compared (the
    past FY1, looked up in the current term structure). ``status`` ``ok`` (with ``log_change`` = ln(now / then), or
    ``turned_non_positive``), ``not_comparable`` or ``unavailable``."""
    base: dict[str, Any] = {"source": "valuation_v2_data", "lookback_days": thresholds.consensus_lookback_days,
                            "past_snapshot_id": _text((past or {}).get("snapshot_id")), "current_snapshot_id": _text((current or {}).get("snapshot_id")),
                            "fiscal_year_end": None, "past_eps": None, "current_eps": None, "log_change": None, "turned_non_positive": False}
    if not current or not past:
        return {**base, "status": "unavailable", "detail": f"no V2 consensus snapshot by the run's clock or {thresholds.consensus_lookback_days} days before it"}
    past_packet = (past.get("packets") or {}).get(symbol) or {}
    past_fy1 = past_packet.get("fy1_estimate") if isinstance(past_packet, Mapping) else None
    past_eps = _eps(past_fy1)
    if past_eps is None:
        return {**base, "status": "unavailable", "detail": f"no FY1 consensus EPS {thresholds.consensus_lookback_days} days before"}
    fiscal = _text((past_fy1 or {}).get("fiscal_year_end"))
    packet = (current.get("packets") or {}).get(symbol) or {}
    rows = [packet.get("fy1_estimate"), *(packet.get("forward_estimates") or [])] if isinstance(packet, Mapping) else []
    same = next((row for row in rows if isinstance(row, Mapping) and _text(row.get("fiscal_year_end")) == fiscal and _eps(row) is not None), None)
    base.update({"fiscal_year_end": fiscal, "past_eps": past_eps})
    if same is None:
        return {**base, "status": "not_comparable", "detail": "the past FY1 is not in the current consensus term structure"}
    current_eps = _eps(same)
    base["current_eps"] = current_eps
    if past_eps <= 0:
        return {**base, "status": "not_comparable", "detail": "the past FY1 consensus EPS is not positive"}
    if current_eps is None or current_eps <= 0:
        return {**base, "status": "ok", "turned_non_positive": True, "detail": None}
    return {**base, "status": "ok", "log_change": math.log(current_eps / past_eps), "detail": None}


def name_sentiment(read: Mapping[str, Any] | None, market: str, symbol: str, *, at: datetime) -> dict[str, Any]:
    """The weekly Finnhub news sentiment of ONE US name as read at ``at`` (``Database.news_sentiment_at``) — the values
    recorded here are the only copy of what was read (the source overwrites the week's row on every poll: a replay
    reads other numbers, so ``replay_sha256`` leaves them out and the code is never a gate). B3: ``not_applicable``."""
    if market not in US_STALENESS_MARKETS:
        return {"status": "not_applicable", "detail": "the Finnhub sentiment is a US source"}
    if not read:
        return {"status": "unavailable", "detail": "no sentiment row published by the run's clock"}
    metadata = read.get("raw_metadata") if isinstance(read.get("raw_metadata"), Mapping) else {}
    published = _utc(read["published_at"]) if read.get("published_at") else None
    return {"status": "ok", "source": "ir_events/finnhub", "external_id": _text(read.get("external_id")),
            "published_at": published.isoformat() if published else None,
            "age_days": (_utc(at) - published).total_seconds() / 86400 if published else None,
            "bullish_percent": _number((metadata or {}).get("bullish_percent")), "bearish_percent": _number((metadata or {}).get("bearish_percent")),
            "articles_last_week": _number((metadata or {}).get("articles_last_week")), "company_news_score": _number((metadata or {}).get("company_news_score")),
            "detail": None}


# ------------------------------------------------------------------ the verdict (pure)


def decide(row: Mapping[str, Any], *, expected_session: str, tp_sessions_behind: int, price: Mapping[str, Any] | None,
           error: Mapping[str, Any], rate: Mapping[str, Any], staleness: Mapping[str, Any], events: Mapping[str, Any],
           thresholds: DecisorThresholds = THRESHOLDS) -> dict[str, Any]:
    """The verdict of ONE served official row — pure: everything it reads is an argument. Returns ``verdict``,
    ``reason_codes`` (every failing gate, in evaluation order; ``[ALL_GATES_PASSED]`` for a permission), ``checks`` (each
    gate's numbers and outcome), ``marks`` (event codes recorded that never change the verdict), ``verdict_without_events``
    (the verdict with the event gates off — the counterfactual a read-only report compares) and the numbers the record
    keeps (``price``, ``e_profile``, ``h_market``).

    ``staleness`` is the name's 053 state (``name_staleness``): ``not_applicable`` passes (B3); ``clear`` passes only with
    ``source_status`` ``ok``; ``stale`` is ``TP_STALE_AFTER_FILING``; a stale poll adds ``STALENESS_SOURCE_STALE``; anything
    else is ``STALENESS_SOURCE_UNAVAILABLE`` — and a row served for a US market is never ``not_applicable`` (it fails
    closed). ``events`` carries ``market`` (else the row's ``official_market``; unknown → the gate applies: fail closed)
    and the facts of ``name_earnings``/``name_consensus``/``name_sentiment``: the codes they raise are gates when listed in
    ``event_gates`` (``EARNINGS_WITHIN_N`` only inside ``earnings_gate_markets``; ``NEVER_GATES`` never), marks otherwise."""
    codes: list[str] = []
    checks: dict[str, Any] = {}
    tp_value, buy_in = _positive(row.get("our_tp")), _positive(row.get("buy_in"))

    stale_flag = row.get("tp_stale")
    checks["tp_stale_flag"] = {"pass": not _marked(stale_flag), "value": stale_flag}
    if _marked(stale_flag):
        codes.append("TP_STALE_FLAG")
    staleness_status = str(staleness.get("status") or "")
    if staleness_status == STALENESS_NOT_APPLICABLE and str(row.get("official_market") or "").strip().upper() in US_STALENESS_MARKETS:
        staleness_status = STALENESS_UNAVAILABLE  # a US TP is never exempt from the filings question
    source_status = _text(staleness.get("source_status"))
    filings = [dict(item) for item in staleness.get("filings") or [] if isinstance(item, Mapping)]
    checks["tp_staleness"] = {"pass": None if staleness_status == STALENESS_NOT_APPLICABLE else staleness_status == STALENESS_CLEAR and source_status == "ok",
                              "status": staleness_status, "source_status": source_status, "filings": filings,
                              "trigger_poll": staleness.get("trigger_poll"), "detail": staleness.get("detail")}
    if staleness_status in (STALENESS_STALE, STALENESS_CLEAR):
        if staleness_status == STALENESS_STALE:
            codes.append(TP_STALE_AFTER_FILING)
        if source_status == STALENESS_STALE:
            codes.append(STALENESS_SOURCE_STALE)
        elif source_status != "ok":
            codes.append(STALENESS_SOURCE_UNAVAILABLE)
    elif staleness_status != STALENESS_NOT_APPLICABLE:
        codes.append(STALENESS_SOURCE_UNAVAILABLE)
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
    # the price must be observed since the last completed session closed: the cut's own price is of the TP's session, so a
    # TP one session behind (tolerated by the age gate) is never decided on a session nobody observed — its move would be 0
    price_session = _text((price or {}).get("session"))
    session_observed = price_session is not None and price_session >= expected_session
    checks["price_session"] = {"pass": session_observed if observed is not None else None, "price_session": price_session,
                               "expected_session": expected_session, "price_source": (price or {}).get("source")}
    if move is None:
        codes.append("PRICE_UNAVAILABLE")
    else:
        if not session_observed:
            codes.append("PRICE_SESSION_STALE")
        if move > thresholds.max_price_move_percent:
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

    raised, event_checks = _event_codes(events, thresholds)
    market = _text(events.get("market")) or _text(row.get("official_market"))
    market = market.strip().upper() if market else None
    # a row whose market nobody named fails closed; "US" (both US exchanges) gates when either of them does
    gated_market = market is None or market in thresholds.earnings_gate_markets or (
        market == "US" and any(exchange in thresholds.earnings_gate_markets for exchange in ("NASDAQ", "NYSE")))
    earnings_status = (events.get("earnings") or {}).get("status") if isinstance(events.get("earnings"), Mapping) else None

    def gates_here(code: str) -> bool:
        if code in NEVER_GATES:
            return False
        if code == EARNINGS_CALENDAR_ROW_INVALID:  # the earnings gate's fail-closed branch: it gates where that gate does, and only
            # when nothing else answered (no estimate); next to an estimate it is a mark
            return earnings_status == "row_invalid" and (EARNINGS_WITHIN_N in thresholds.event_gates or code in thresholds.event_gates) and gated_market
        return code in thresholds.event_gates and (code != EARNINGS_WITHIN_N or gated_market)

    gates = [code for code in raised if gates_here(code)]
    marks = [code for code in raised if code not in gates]
    checks["events"] = {**event_checks, "market": market, "raised": raised, "gates": gates, "marks": marks}
    verdict_without, codes_without = _verdict_of(codes)
    verdict, reason_codes = _verdict_of([*codes, *gates])
    checks["counterfactual"] = {"verdict_without_events": verdict_without, "reason_codes_without_events": codes_without}
    return {"verdict": verdict, "reason_codes": reason_codes, "checks": _json_ready(checks), "marks": marks, "verdict_without_events": verdict_without,
            "price": entry_price, "e_profile": e_profile, "h_market": h_market}


def _verdict_of(codes: list[str]) -> tuple[str, list[str]]:
    """A VETO when any code vetoes, OBSERVAR when any other code holds, else the permission (``ALL_GATES_PASSED``)."""
    if any(code in VETO_CODES for code in codes):
        return VETO, list(codes)
    if codes:
        return OBSERVAR, list(codes)
    return COMPRA_PERMITIDA, [ALL_GATES_PASSED]


def _event_codes(events: Mapping[str, Any], thresholds: DecisorThresholds) -> tuple[list[str], dict[str, Any]]:
    """The event codes the facts raise, in a fixed order, and each rule's numbers: ``EARNINGS_WITHIN_N`` (the facts'
    ``within``), ``EARNINGS_CALENDAR_ROW_INVALID`` (an invalid row of the name), ``EARNINGS_DATE_ESTIMATED`` /
    ``EARNINGS_CALENDAR_UNAVAILABLE`` (which source answered),
    ``CONSENSUS_EPS_CUT_30D`` (ln change below −``consensus_eps_cut_log``, or FY1 turned non-positive) and
    ``NEWS_SENTIMENT_NEGATIVE`` (bearish ≥ the limit over at least the minimum articles, in a row no older than the limit)."""
    raised: list[str] = []
    earnings = events.get("earnings") if isinstance(events.get("earnings"), Mapping) else {}
    if (earnings or {}).get("within") is True:
        raised.append(EARNINGS_WITHIN_N)
    if (earnings or {}).get("status") == "row_invalid" or (earnings or {}).get("row_invalid") is True:
        raised.append(EARNINGS_CALENDAR_ROW_INVALID)
    if (earnings or {}).get("status") == "estimated":
        raised.append(EARNINGS_DATE_ESTIMATED)
    elif (earnings or {}).get("status") not in ("calendar", "row_invalid"):
        raised.append(EARNINGS_CALENDAR_UNAVAILABLE)
    consensus = dict(events.get("consensus") or {}) if isinstance(events.get("consensus"), Mapping) else {}
    change = _number(consensus.get("log_change"))
    cut = consensus.get("status") == "ok" and (consensus.get("turned_non_positive") is True
                                               or (change is not None and change < -thresholds.consensus_eps_cut_log))
    if cut:
        raised.append(CONSENSUS_EPS_CUT_30D)
    sentiment = dict(events.get("sentiment") or {}) if isinstance(events.get("sentiment"), Mapping) else {}
    bearish, articles, age = (_number(sentiment.get(key)) for key in ("bearish_percent", "articles_last_week", "age_days"))
    negative = (sentiment.get("status") == "ok" and bearish is not None and articles is not None and age is not None
                and bearish >= thresholds.news_sentiment_bearish_min_percent and articles >= thresholds.news_sentiment_min_articles
                and age <= thresholds.news_sentiment_max_age_days)
    if negative:
        raised.append(NEWS_SENTIMENT_NEGATIVE)
    return raised, {
        "earnings": dict(earnings or {}),
        "consensus": {**consensus, "cut": cut, "limit_log": -thresholds.consensus_eps_cut_log},
        "sentiment": {**sentiment, "negative": negative, "bearish_min_percent": thresholds.news_sentiment_bearish_min_percent,
                      "min_articles": thresholds.news_sentiment_min_articles, "max_age_days": thresholds.news_sentiment_max_age_days},
    }


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


REPLAY_EXCLUDED_KEYS = ("id", "row_sha256", "run_id", "published_at", "inputs_sha256")  # the run's identity, its wall clock, the hashes over them


def replay_sha256(record: Mapping[str, Any]) -> str:
    """The hash of what a verdict DECIDED — every key of the record but the run's identity (``id``, ``run_id``), the wall
    clock of its insert (``published_at``) and the hashes that cover those (``row_sha256``, ``inputs_sha256``): a re-run
    of a night at the same clock has the same one, whatever was published or marked after that clock (every read is
    causal: the generation, the cycles, the calibration and the rate packages at ≤ D; the served records, the 053 marks
    and the poll, the calendars, the 051 filings and the consensus snapshots at D − ε on their insert clocks) — with ONE
    declared exception left out of it: the Finnhub sentiment (``inputs.events.sentiment``, ``checks.events.sentiment`` and
    the ``NEWS_SENTIMENT_NEGATIVE`` mark). Its source overwrites the week's row on every poll, so a replay cannot see the
    value read at D; that value stays in the record, and the code is never a gate (``NEVER_GATES``)."""
    content = copy.deepcopy({key: value for key, value in record.items() if key not in REPLAY_EXCLUDED_KEYS})
    for part in ("inputs", "checks"):
        events = (content.get(part) or {}).get("events") if isinstance(content.get(part), Mapping) else None
        if isinstance(events, dict):
            events.pop("sentiment", None)
            for listing in ("raised", "marks"):
                if isinstance(events.get(listing), list):
                    events[listing] = [code for code in events[listing] if code != NEWS_SENTIMENT_NEGATIVE]
    return canonical_sha256(content)


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
               thresholds: DecisorThresholds = THRESHOLDS, write: bool = False, enabled: bool | None = None) -> dict[str, Any]:
    """One decision run over the generation IN FORCE AT the run's clock (``generation_at``: a replay with a past ``now``
    reads what that night saw, never a later selection): a verdict per served name. A dry run by default (the receipt
    only); ``write=True`` records every verdict in ONE append (idempotent per ``(run_id, market, symbol)``) — refused
    (``ValueError``, nothing read) while ``C3PO_VALUATION_DECISOR_SHADOW`` is off (``enabled``, else the process's environment,
    ``valuation_env.decisor_shadow_enabled``) and
    for a run on ``quotes``: a caller's quotes (``(market, symbol) → {price, ask, as_of, source}``, fresh ones only — see
    ``_price_observation``) are for a dry run, so nothing intraday replaces the nightly verdicts in the lab's reads. ``now``
    is the run's clock (the wall clock by default); ``published_at`` is the later of it and the wall clock read
    immediately before the insert. A served row predicted after the run's clock is not decided (counted in
    ``tp_after_run_instant``). The US names read migration 053 ONCE, at the run's clock (``us_staleness_at``). The receipt
    is aggregate (per market: decided, verdicts, reasons, unrecordable, refused quotes, the 053 source's status) — it
    names no symbol and no filing. Nothing is decided without a generation, under a generation whose source is unknown, or
    under a thresholds block other than the one the PREREG froze (``ValueError``)."""
    if write and quotes:
        raise ValueError("a run on a caller's quotes is a dry run (write=False): the nightly verdicts are decided on the official cut and the cycles "
                         "published after it, and nothing intraday replaces them")
    if write and not (enabled if enabled is not None else valuation_env.decisor_shadow_enabled()):
        raise ValueError("C3PO_VALUATION_DECISOR_SHADOW is off: the decisor records nothing (a dry run decides without writing)")
    frozen = _prereg_frozen(thresholds)
    digest = thresholds_sha256(thresholds)
    instant = _utc(now) if now is not None else datetime.now(timezone.utc)
    generation = generation_at(database, instant)
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
    us_staleness: dict[str, Any] | None = None  # migration 053 read ONCE per run, at the run's clock, for both US markets
    us_filings: dict[str, Any] | None = None  # the 051 fallback of the earnings rule, read once (US)
    us_issuers: dict[str, str] = {}  # symbol → issuer (CIK) from the 051 filings known at D: the poll's coverage of a name
    margin = timedelta(seconds=thresholds.insert_margin_seconds)  # ε: every read on an insert clock stops at D − ε
    calendars = calendars_at(database, instant, recent_hours=thresholds.earnings_calendar_max_age_hours,
                             margin_seconds=thresholds.insert_margin_seconds)  # the calendars this run may read, once
    for market in MARKETS:
        stats: dict[str, Any] = {"decided": 0, "verdicts": {verdict: 0 for verdict in VERDICTS}, "reasons": {}, "unrecordable": 0,
                                 "tp_after_run_instant": 0, "tp_published_after_run_instant": 0, "quotes_refused": 0, "expected_session": None,
                                 "calendar_unavailable": False, "tp_staleness_source": STALENESS_NOT_APPLICABLE,
                                 "earnings_calendars": {"recent": len(calendars["recent"]), "older": calendars["older"] is not None},
                                 "marks": {}, "verdicts_without_events": {verdict: 0 for verdict in VERDICTS}}
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
        if group == "US":
            if us_staleness is None:  # the poll first (a SUCCESSFUL run with progress, completed by D − ε), then the table
                poll = database.ingestion_run_completed_at_or_before(thresholds.staleness_poll_source, instant - margin, min_records_read=1)
                us_staleness = {**us_staleness_at(database, instant, margin_seconds=thresholds.insert_margin_seconds),
                                "trigger_poll": poll_reference(poll, thresholds.staleness_poll_source), "failed_issuers": failed_issuers(poll)}
                us_filings = filings_known_at(database, instant, lookback_days=thresholds.earnings_filings_lookback_days,
                                              margin_seconds=thresholds.insert_margin_seconds)
                us_issuers = {symbol: str(refs[-1]["issuer_key"]) for symbol, refs in ((us_filings or {}).get("by_symbol") or {}).items()
                              if refs and refs[-1].get("issuer_key")}  # the name's issuer, from the 051 filings known at D (the latest)
            stats["tp_staleness_source"] = str(us_staleness.get("status"))
        latest_universe = database.analysis_snapshot_at_or_before(official.UNIVERSE_ANALYSIS, f"{market}_UNIVERSE", instant)
        served = _served_rows(database, market, generation)
        symbols = sorted(served)
        consensus_now = database.v2_forward_eps_at_or_before(market, symbols, instant - margin)
        consensus_past = database.v2_forward_eps_at_or_before(market, symbols, instant - timedelta(days=thresholds.consensus_lookback_days) - margin)
        sentiment = database.news_sentiment_at(symbols, instant - margin) if group == "US" else {}
        for symbol, row in sorted(served.items()):
            if _utc(row["prediction_instant"]) > instant:  # causal: a TP predicted after the run's clock is not one this run could read
                logger.warning("valuation_decision: %s/%s not decided — its TP was predicted at %s, after the run's clock %s", market, symbol,
                               _utc(row["prediction_instant"]).isoformat(), instant.isoformat())
                stats["tp_after_run_instant"] += 1
                continue
            if row.get("official_published_at") and _utc(row["official_published_at"]) > instant - margin:
                # a record published after the run's clock (a bootstrap of old cycles) was not there to be read: a replay of an
                # earlier night never decides on it (counted, aggregate)
                stats["tp_published_after_run_instant"] += 1
                continue
            try:
                behind = _sessions_behind(market, str(row.get("official_session_date") or ""), expected)
            except CalendarUnavailable as error:
                logger.warning("valuation_decision: %s/%s not decided — %s", market, symbol, error)
                stats["unrecordable"] += 1
                continue
            profile = str(row.get("valuation_profile") or "general")
            if (market, profile) not in errors:
                errors[(market, profile)] = profile_error(database, market, profile, at=instant, thresholds=thresholds)
            price = _price_observation(row, market=market, symbol=symbol, at=instant, quotes=quotes, latest_universe=latest_universe,
                                       thresholds=thresholds)
            if price["quote_refused"]:
                stats["quotes_refused"] += 1
            staleness = name_staleness(us_staleness if group == "US" else None, market, symbol, thresholds=thresholds,
                                       issuer_key=us_issuers.get(symbol) if group == "US" else None)
            events = {"market": market,
                      "earnings": name_earnings(calendars, us_filings if group == "US" else None, market, symbol, at=instant,
                                                expected_session=expected, thresholds=thresholds),
                      "consensus": name_consensus(consensus_now, consensus_past, symbol, thresholds=thresholds),
                      "sentiment": name_sentiment(sentiment.get(symbol), market, symbol, at=instant)}
            outcome = decide(row, expected_session=expected, tp_sessions_behind=behind, price=price, error=errors[(market, profile)],
                             rate=rates[group], staleness=staleness, events=events, thresholds=thresholds)
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
                "tp_staleness": staleness,
                "events": events,
                "expected_session": expected,
                "thresholds_sha256": digest,
                "prereg_frozen": frozen,
            }
            drafts.append((market, symbol, expected, row, outcome, inputs))
            stats["decided"] += 1
            stats["verdicts"][outcome["verdict"]] += 1
            for code in outcome["reason_codes"]:
                stats["reasons"][code] = stats["reasons"].get(code, 0) + 1
            for code in outcome["marks"]:
                stats["marks"][code] = stats["marks"].get(code, 0) + 1
            stats["verdicts_without_events"][outcome["verdict_without_events"]] += 1
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


def not_before(database: Any, *, thresholds: DecisorThresholds = THRESHOLDS) -> datetime | None:
    """The first instant the nightly phase may decide: the newest earnings calendar's receipt + ε. A calendar received
    inside the last ε is out of the run's read (``calendars_at``), so a run right after the calendar phase would decide
    without the calendar it just collected; the phase waits ("not yet": nothing recorded) and the worker wakes then.
    ``None`` without any calendar."""
    latest = database.latest_analysis_snapshot_published_at(CALENDAR_ANALYSIS, CALENDAR_ENTITY)
    return _utc(latest) + timedelta(seconds=thresholds.insert_margin_seconds) if latest is not None else None


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


def _view(record: Mapping[str, Any], *, now: datetime, served_row_sha256: str | None) -> dict[str, Any]:
    try:
        session_current = record["session_date"] == session_date_of(str(record["market"]), now)
    except CalendarUnavailable:
        session_current = False
    tp_served = served_row_sha256 is not None and served_row_sha256 == record["tp_row_sha256"]
    downgrades = [code for code, failed in ((VERDICT_NOT_CURRENT, not session_current), (VERDICT_TP_NOT_SERVED, not tp_served)) if failed]
    view = {key: copy.deepcopy(record.get(key)) for key in ("symbol", "market", "verdict", "reason_codes", "session_date", "prediction_instant",
                                                             "published_at", "run_id", "generation_id", "tp_source", "tp_cycle_id", "tp_row_sha256", "tp",
                                                             "buy_in", "price", "e_profile", "h_market", "thresholds_sha256", "row_sha256", "mode")}
    events = ((record.get("checks") or {}).get("events") or {}) if isinstance(record.get("checks"), Mapping) else {}
    view.update({"current": not downgrades, "session_current": session_current, "tp_served": tp_served,
                 "effective_verdict": VETO if downgrades else record["verdict"],
                 "effective_reason_codes": downgrades if downgrades else list(record["reason_codes"]),
                 "marks": list(events.get("marks") or []) if isinstance(events, Mapping) else []})  # recorded, never a verdict
    return view


def latest_verdicts(database: Any, market: str, symbols: Iterable[str], *, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """The latest verdict of each REQUESTED symbol (``market``: ``B3``, ``NASDAQ``, ``NYSE`` or ``US`` for both US
    markets) — the R2D2 lab names what it asks about; nothing here enumerates the names a verdict permits. Each view
    carries the verdict, its codes, the TP read and its identity, and whether it is ``current`` at ``now``: decided for
    the last completed session (``session_current``) AND over the TP the generation in force at ``now`` still serves
    for the symbol (``tp_served``: the same row hash — a generation is immutable, so the verdict's own generation always
    serves it; a later one serves it while it carries the same record, e.g. after a targeted admission of another name,
    and not after a source switch or a rollback). A verdict that is not current is served with ``effective_verdict =
    VETO`` and ``effective_reason_codes`` naming why (``VERDICT_NOT_CURRENT``, ``VERDICT_TP_NOT_SERVED``) — no permission
    outlives its night or its TP. A symbol without a verified verdict is absent."""
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
    generation = generation_at(database, at)
    views: dict[str, dict[str, Any]] = {}
    for symbol, record in found.items():
        if generation is not None and str(record["generation_id"]) == str(generation.get("generation_id")):
            served: str | None = str(record["tp_row_sha256"])  # the verdict's own generation: immutable, it serves the row the verdict read
        else:
            row = official_row(database, str(record["market"]), symbol, generation=generation)  # None generation → nothing served
            served = _text((row or {}).get("official_row_sha256"))
        views[symbol] = _view(record, now=at, served_row_sha256=served)
    return views


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
    from .database import Database
    settings = get_settings()
    if args.run and not valuation_env.decisor_shadow_enabled():
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
