"""Valuation as-filed (owner's direction 2026-10-17): from statement vintages to valuation inputs, in shadow.

* ``as_of_fundamentals(database, issuer_key, as_of)`` — the TTM inputs a valuation at ``as_of`` could have known: only
  vintages ACCEPTED at or before ``as_of`` exist for it; for each fact the latest such acceptance wins (a restatement
  known at ``as_of`` supersedes the original); quarters come from ``sec_xbrl.discrete_quarters`` (Q4 = FY − 9M) and the
  TTM is the four contiguous quarters ending at the latest reported quarter of revenue (net income when there is none).
  Diluted EPS is not additive: a TTM that is exactly a fiscal year takes the year's reported EPS, and quarters from
  documents of different share bases (a split) are never summed (``None`` with a warning, see ``_ttm_eps``).
* ``reconcile_with_eodhd`` / ``record_us_reconciliation`` — the shadow comparison, field by field, against the EODHD
  fundamentals the US producer consumed in the same build (agreement within ``AGREEMENT_TOLERANCE``). It is persisted as
  its own analysis snapshot; it never feeds a served number.
* ``evaluate_us_filings`` — the US revaluation trigger: an accepted 10-Q/10-K (or amendment) or 8-K item 2.02 marks the
  official TP of each of the issuer's symbols ``stale`` when that TP predates the acceptance or its fundamentals predate
  the period the filing reports (a 10-Q/10-K's filed period; for an 8-K 2.02, the fiscal quarter it announces — see
  ``announced_quarter_end``) and queues it for the next nightly cut; the cut that revalues it appends ``cleared``
  (migration 053, append-only). ``us_staleness_at`` is what a decision reads (the Decisor V1, ``valuation_decision``):
  the marks known at the decision's clock, never a later one.

Everything here runs only behind ``C3PO_VALUATION_ASFILED_ENABLED`` (default off) and changes no served number — except
the read-only ``us_staleness_at``, which the decisor calls (its nightly phase and its writes are behind its own switch,
``C3PO_VALUATION_DECISOR_SHADOW``).
"""
from __future__ import annotations

import calendar
import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from .database import Database
from .sec_xbrl import (
    CONCEPT_LADDER,
    DURATION_FIELDS,
    FIELD_UNITS,
    FILING_SOURCE,
    MARKET,
    NEW_YORK,
    QUARTER_CONTIGUITY_DAYS,
    STATEMENT_FORMS,
    VINTAGE_SOURCE,
    discrete_quarters,
    duration_months,
    filing_items,
    is_trigger_filing,
)
from .statement_vintages import StatementVintageStore, as_date, utc_instant
from .valuation_official import current_generation, official_rows


logger = logging.getLogger(__name__)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
FUNDAMENTALS_SCHEMA = "VALUATION_ASFILED_FUNDAMENTALS_V1"
RECONCILIATION_ANALYSIS = "valuation_asfiled_reconciliation"
RECONCILIATION_SCHEMA = "VALUATION_ASFILED_RECONCILIATION_V1"
RECONCILIATION_METHODOLOGY_VERSION = 1
AGREEMENT_TOLERANCE = 0.02  # relative difference at or below 2 % is agreement
TRIGGER_LOOKBACK_DAYS = 10  # filings accepted earlier are not (re)evaluated by the trigger
PERIOD_TOLERANCE_DAYS = 7  # a provider labelling the quarter by calendar month end (06-30 for a 06-27 close) still covers it
QUARTER_HISTORY = 8
INSTANT_FIELDS = tuple(name for name in CONCEPT_LADDER if name not in DURATION_FIELDS)
SHARES_CONCEPT = CONCEPT_LADDER["shares_outstanding"][0]
SHARE_BASIS_RATIO = 1.4  # cover share counts this far apart across the documents of one TTM EPS: a split (or a new share base)
EPS_SHARE_BASIS_CHANGED = "eps_diluted_share_basis_changed"
STALE, CLEARED, UNTRACKED = "stale", "cleared", "untracked"
STALENESS_TABLE = "valuation_tp_staleness"
# the order of the states of one (filing, symbol) when two marks share a recorded_at — the trigger never writes that (one
# mark per pair per pass); should it happen, the stricter state is the one a decision reads
_STATE_ORDER = {UNTRACKED: 0, CLEARED: 1, STALE: 2}


# -- the universe ------------------------------------------------------------------------------------------------------

def us_valuation_universe(database: Database) -> dict[str, str]:
    """symbol → market (NASDAQ/NYSE) of the STOCKS of the latest US universe cycles — the names a US TP is produced for
    (ETFs file no 10-Q)."""
    universe: dict[str, str] = {}
    for market in ("NASDAQ", "NYSE"):
        snapshot = database.latest_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE")
        outputs = (snapshot or {}).get("outputs")
        rows = outputs.get("rows") if isinstance(outputs, Mapping) else None
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, Mapping) or str(row.get("security_type") or "Stock") == "ETF":
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if symbol:
                universe.setdefault(symbol, market)
    return universe


# -- the bridge --------------------------------------------------------------------------------------------------------

def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _point_in_time(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, date | None, date], Mapping[str, Any]]:
    """(concept, start, end) → the row of the latest document accepted (rows are read accepted ≤ as_of already)."""
    view: dict[tuple[str, date | None, date], Mapping[str, Any]] = {}
    for row in rows:
        key = (str(row["concept"]), as_date(row.get("period_start")), as_date(row["period_end"]) or date.min)
        current = view.get(key)
        if current is None or (utc_instant(row["accepted_at"]), str(row["doc_id"])) > (utc_instant(current["accepted_at"]), str(current["doc_id"])):
            view[key] = row
    return view


def _ladder_durations(view: Mapping[tuple[str, date | None, date], Mapping[str, Any]], field: str) -> dict[tuple[date, date], Mapping[str, Any]]:
    """(start, end) → the fact of the first ladder concept reported for that period."""
    unit = FIELD_UNITS.get(field, "USD")
    output: dict[tuple[date, date], Mapping[str, Any]] = {}
    for concept in CONCEPT_LADDER[field]:
        for (name, start, end), row in view.items():
            if name == concept and start is not None and str(row["unit"]) == unit and (start, end) not in output:
                output[(start, end)] = row
    return output


def _ladder_instants(view: Mapping[tuple[str, date | None, date], Mapping[str, Any]], field: str) -> dict[date, Mapping[str, Any]]:
    unit = FIELD_UNITS.get(field, "USD")
    output: dict[date, Mapping[str, Any]] = {}
    for concept in CONCEPT_LADDER[field]:
        for (name, start, end), row in view.items():
            if name == concept and start is None and str(row["unit"]) == unit and end not in output:
                output[end] = row
    return output


def _chain_ending(quarters: Mapping[tuple[date, date], Mapping[str, Any]], ending: date, count: int = 4) -> list[tuple[date, date]]:
    """``count`` contiguous quarters, newest first, the newest ending at ``ending`` (± the contiguity tolerance)."""
    newest = next((key for key in sorted(quarters, key=lambda key: key[1], reverse=True)
                   if abs((key[1] - ending).days) <= QUARTER_CONTIGUITY_DAYS), None)
    if newest is None:
        return []
    chain = [newest]
    while len(chain) < count:
        start = chain[-1][0]
        previous = next((key for key in quarters if key not in chain
                         and abs((start - timedelta(days=1) - key[1]).days) <= QUARTER_CONTIGUITY_DAYS), None)
        if previous is None:
            return []
        chain.append(previous)
    return chain


def _provenance(row: Mapping[str, Any]) -> dict[str, Any]:
    start = as_date(row.get("period_start"))
    return {
        "concept": str(row["concept"]),
        "doc_id": str(row["doc_id"]),
        "form": str(row.get("form") or ""),
        "accepted_at": utc_instant(row["accepted_at"]).isoformat(),
        "period_start": start.isoformat() if start else None,
        "period_end": (as_date(row["period_end"]) or date.min).isoformat(),
        "first_publication": bool(row.get("is_first_publication")),
    }


def _cover_shares(rows: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """doc_id → the cover-page share count the document reported (its latest cover date): the share basis of its EPS."""
    latest: dict[str, tuple[date, float]] = {}
    for row in rows:
        if str(row["concept"]) != SHARES_CONCEPT:
            continue
        value, end = _float(row["value"]), as_date(row["period_end"])
        if value is None or value <= 0 or end is None:
            continue
        doc_id = str(row["doc_id"])
        if doc_id not in latest or end > latest[doc_id][0]:
            latest[doc_id] = (end, value)
    return {doc_id: value for doc_id, (_, value) in latest.items()}


def _ttm_eps(
    quarters: Mapping[tuple[date, date], Mapping[str, Any]],
    chain: Sequence[tuple[date, date]],
    durations: Mapping[tuple[date, date], Mapping[str, Any]],
    cover_shares: Mapping[str, float],
) -> tuple[float | None, list[tuple[Mapping[str, Any], bool]], str | None]:
    """TTM diluted EPS on ONE share basis → (value, [(fact, derived quarter)], refusal reason).

    When the four quarters are exactly a fiscal year, the year's reported EPS (exact: EPS is not additive, so FY − 9M is
    only an approximation of Q4). Otherwise the sum of the quarters — refused (``None``) when the documents behind them
    report cover share counts ``SHARE_BASIS_RATIO`` or more apart: a split restates EPS only in the documents filed after
    it, so their quarters are never added to quarters of an older share basis."""
    span = (chain[-1][0], chain[0][1])
    annual = durations.get(span)
    if annual is not None and duration_months(*span) == 12:
        return float(annual["value"]), [(annual, False)], None
    facts = [(fact, bool(quarters[key]["derived"])) for key in chain for fact in quarters[key]["facts"]]
    counts = [cover_shares[doc_id] for doc_id in {str(fact["doc_id"]) for fact, _ in facts} if doc_id in cover_shares]
    if counts and max(counts) / min(counts) >= SHARE_BASIS_RATIO:
        return None, facts, EPS_SHARE_BASIS_CHANGED
    return sum(float(quarters[key]["value"]) for key in chain), facts, None


def total_debt(balance: Mapping[str, float | None]) -> float | None:
    """Long + short without double counting: ``DebtCurrent`` when tagged, else current maturities of long-term debt plus
    short-term borrowings (commercial paper only when no short-term total is tagged); when only ``LongTermDebt`` (which
    INCLUDES current maturities) exists, it plus short-term borrowings."""
    long_term = balance.get("long_term_debt")
    short_borrowings = balance.get("short_term_borrowings")
    if long_term is None and balance.get("long_term_debt_including_current") is not None:
        return float(balance["long_term_debt_including_current"] or 0.0) + (short_borrowings or 0.0)
    current = balance.get("debt_current")
    if current is None and (balance.get("long_term_debt_current") is not None or short_borrowings is not None):
        current = (balance.get("long_term_debt_current") or 0.0) + (short_borrowings or 0.0)
    if long_term is None and current is None:
        return None
    return (long_term or 0.0) + (current or 0.0)


def as_of_fundamentals(database: Database, issuer_key: str, as_of: datetime, *, market: str = MARKET) -> dict[str, Any]:
    """The as-filed valuation inputs of one issuer at ``as_of`` (see the module docstring). Never raises for missing
    data: absent fields are ``None`` and listed in ``missing``."""
    cut = utc_instant(as_of)
    rows = StatementVintageStore(database).vintages(market, issuer_key, accepted_at_or_before=cut, source=VINTAGE_SOURCE)
    view = _point_in_time(rows)
    quarters = {field: discrete_quarters(_ladder_durations(view, field)) for field in sorted(DURATION_FIELDS)}
    reference = quarters["revenue"] or quarters["net_income"]
    ending = max((key[1] for key in reference), default=None)
    ttm: dict[str, float | None] = {}
    provenance: dict[str, list[dict[str, Any]]] = {}
    used: list[Mapping[str, Any]] = []
    warnings: list[str] = []
    for field in sorted(DURATION_FIELDS):
        chain = _chain_ending(quarters[field], ending) if ending else []
        if not chain:
            ttm[field] = None
            continue
        if field == "eps_diluted":
            ttm[field], facts, refusal = _ttm_eps(quarters[field], chain, _ladder_durations(view, field), _cover_shares(rows))
            if refusal:
                warnings.append(refusal)
        else:
            ttm[field] = sum(float(quarters[field][key]["value"]) for key in chain)
            facts = [(fact, bool(quarters[field][key]["derived"])) for key in chain for fact in quarters[field][key]["facts"]]
        used.extend(fact for fact, _ in facts)
        provenance[field] = [{**_provenance(fact), "derived_quarter": derived} for fact, derived in facts]
    balance: dict[str, float | None] = {}
    balance_dates: dict[str, str | None] = {}
    for field in INSTANT_FIELDS:
        instants = _ladder_instants(view, field)
        chosen_end: date | None = None
        if field == "shares_outstanding" or ending is None:
            chosen_end = max(instants) if instants else None  # the cover-page share count is dated after the quarter
        else:  # a balance at the TTM's own quarter end, never an older one (a component repaid since is absent, not stale)
            chosen_end = next((end for end in sorted(instants, reverse=True) if abs((end - ending).days) <= QUARTER_CONTIGUITY_DAYS), None)
        if chosen_end is None:
            balance[field], balance_dates[field] = None, None
            continue
        row = instants[chosen_end]
        balance[field] = _float(row["value"])
        balance_dates[field] = chosen_end.isoformat()
        used.append(row)
        provenance[field] = [_provenance(row)]
    debt = total_debt(balance)
    operating_income, d_and_a = ttm.get("operating_income"), ttm.get("d_and_a")
    operating_cash, capex = ttm.get("operating_cash_flow"), ttm.get("capex")
    derived = {
        "ebitda": operating_income + d_and_a if operating_income is not None and d_and_a is not None else None,
        "free_cash_flow": operating_cash - abs(capex) if operating_cash is not None and capex is not None else None,
        "total_debt": debt,
    }
    quarter_history = {
        field: [
            {"period_start": key[0].isoformat(), "period_end": key[1].isoformat(), "value": float(entry["value"]), "derived": bool(entry["derived"])}
            for key, entry in sorted(quarters[field].items(), key=lambda item: item[0][1], reverse=True)[:QUARTER_HISTORY]
        ]
        for field in sorted(DURATION_FIELDS)
    }
    expected = [*sorted(DURATION_FIELDS), "cash", "stockholders_equity", "shares_outstanding", "total_debt"]
    values = {**ttm, **balance, **derived}
    latest = max((utc_instant(row["accepted_at"]) for row in used), default=None)
    return {
        "schema": FUNDAMENTALS_SCHEMA,
        "market": market,
        "issuer_key": issuer_key,
        "as_of": cut.isoformat(),
        "period_end": ending.isoformat() if ending else None,
        "latest_accepted_at": latest.isoformat() if latest else None,
        "documents": sorted({str(row["doc_id"]) for row in used}),
        "ttm": ttm,
        "balance": balance,
        "balance_dates": balance_dates,
        "derived": derived,
        "quarters": quarter_history,
        "provenance": provenance,
        "missing": [name for name in expected if values.get(name) is None],
        "warnings": warnings,
    }


# -- the shadow reconciliation -----------------------------------------------------------------------------------------

def _sum_latest(rows: Any, field: str, count: int = 4) -> float | None:
    """The sum of ``field`` over the ``count`` newest provider statement rows, only when every one of them has it."""
    if not isinstance(rows, list) or len(rows) < count:
        return None
    values = [_float(row.get(field)) if isinstance(row, Mapping) else None for row in rows[:count]]
    return sum(value for value in values if value is not None) if all(value is not None for value in values) else None


def _abs_or_none(value: float | None) -> float | None:
    return abs(value) if value is not None else None


def comparable_fields(asfiled: Mapping[str, Any], fundamentals: Mapping[str, Any]) -> dict[str, tuple[float | None, float | None]]:
    """field → (as-filed, EODHD) for every number the US producer reads from EODHD today, like for like: TTM flows
    against EODHD's TTM highlights or the sum of its four newest quarters, balances against its latest quarter."""
    ttm = asfiled.get("ttm") or {}
    balance = asfiled.get("balance") or {}
    derived = asfiled.get("derived") or {}
    income = fundamentals.get("quarterlyIncome")
    cash_flow = fundamentals.get("quarterlyCashFlow")
    return {
        "revenue_ttm": (ttm.get("revenue"), _float(fundamentals.get("totalRevenue"))),
        "net_income_ttm": (ttm.get("net_income"), _sum_latest(income, "netIncome")),
        "eps_diluted_ttm": (ttm.get("eps_diluted"), _float(fundamentals.get("trailingEps"))),
        "operating_income_ttm": (ttm.get("operating_income"), _sum_latest(income, "operatingIncome")),
        "d_and_a_ttm": (ttm.get("d_and_a"), _sum_latest(cash_flow, "depreciation")),
        "ebitda_ttm": (derived.get("ebitda"), _float(fundamentals.get("ebitda"))),
        "operating_cash_flow_ttm": (ttm.get("operating_cash_flow"), _sum_latest(cash_flow, "totalCashFromOperatingActivities")),
        "capex_ttm": (_abs_or_none(ttm.get("capex")), _abs_or_none(_sum_latest(cash_flow, "capitalExpenditures"))),
        "cash": (balance.get("cash"), _float(fundamentals.get("totalCash"))),
        "total_debt": (derived.get("total_debt"), _float(fundamentals.get("totalDebt"))),
        "stockholders_equity": (balance.get("stockholders_equity"), _float(fundamentals.get("totalEquity"))),
        "shares_outstanding": (balance.get("shares_outstanding"), _float(fundamentals.get("sharesOutstanding"))),
    }


def field_agreement(asfiled: float | None, provider: float | None, *, tolerance: float = AGREEMENT_TOLERANCE) -> dict[str, Any]:
    if asfiled is None:
        return {"asfiled": None, "eodhd": provider, "relative_difference": None, "status": "missing_asfiled"}
    if provider is None:
        return {"asfiled": asfiled, "eodhd": None, "relative_difference": None, "status": "missing_eodhd"}
    scale = max(abs(asfiled), abs(provider))
    difference = 0.0 if scale == 0 else abs(asfiled - provider) / scale
    return {"asfiled": asfiled, "eodhd": provider, "relative_difference": difference,
            "status": "agree" if difference <= tolerance else "disagree"}


def reconcile_with_eodhd(asfiled: Mapping[str, Any], fundamentals: Mapping[str, Any], *, tolerance: float = AGREEMENT_TOLERANCE) -> dict[str, Any]:
    """Per-field agreement between the as-filed inputs and one symbol's EODHD fundamentals."""
    fields = {name: field_agreement(left, right, tolerance=tolerance) for name, (left, right) in comparable_fields(asfiled, fundamentals).items()}
    period_end = as_date(asfiled.get("period_end"))
    provider_period = None
    try:
        provider_period = as_date(fundamentals.get("financialsAsOf"))
    except ValueError:
        provider_period = None
    return {
        "issuer_key": asfiled.get("issuer_key"),
        "asfiled_period_end": period_end.isoformat() if period_end else None,
        "eodhd_financials_as_of": provider_period.isoformat() if provider_period else None,
        "period_aligned": (abs((period_end - provider_period).days) <= PERIOD_TOLERANCE_DAYS) if period_end and provider_period else None,
        "fields": fields,
    }


def summarize_reconciliations(per_symbol: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """field → {compared, agree, disagree, missing_asfiled, missing_eodhd, agreement_percent}."""
    summary: dict[str, dict[str, Any]] = {}
    for report in per_symbol.values():
        for name, item in (report.get("fields") or {}).items():
            bucket = summary.setdefault(name, {"compared": 0, "agree": 0, "disagree": 0, "missing_asfiled": 0, "missing_eodhd": 0})
            bucket[item["status"]] += 1
            bucket["compared"] += int(item["status"] in {"agree", "disagree"})
    for bucket in summary.values():
        bucket["agreement_percent"] = round(bucket["agree"] / bucket["compared"] * 100, 2) if bucket["compared"] else None
    return summary


def record_us_reconciliation(
    database: Database,
    market: str,
    fundamentals_by_symbol: Mapping[str, Mapping[str, Any]],
    *,
    as_of: datetime,
) -> str | None:
    """The shadow reconciliation of one US build: for every symbol whose issuer has vintages, ``as_of_fundamentals`` at
    the instant EODHD answered (``as_of``) against the EODHD fundamentals that build consumed. Persisted as
    ``valuation_asfiled_reconciliation/<MARKET>_ASFILED_RECONCILIATION``; ``None`` when no symbol could be compared."""
    issuers = StatementVintageStore(database).symbol_issuers(MARKET, source=FILING_SOURCE)
    per_symbol: dict[str, dict[str, Any]] = {}
    unmapped: list[str] = []
    for symbol, fundamentals in sorted(fundamentals_by_symbol.items()):
        issuer_key = issuers.get(symbol.upper())
        if not issuer_key:
            unmapped.append(symbol.upper())
            continue
        asfiled = as_of_fundamentals(database, issuer_key, as_of)
        if not asfiled["documents"]:
            unmapped.append(symbol.upper())
            continue
        per_symbol[symbol.upper()] = reconcile_with_eodhd(asfiled, fundamentals)
    if not per_symbol:
        return None
    methodology_id = database.ensure_methodology_version(
        RECONCILIATION_ANALYSIS,
        RECONCILIATION_METHODOLOGY_VERSION,
        {"tolerance": AGREEMENT_TOLERANCE, "basis": "latest vintage accepted at or before the EODHD answer", "schema": RECONCILIATION_SCHEMA},
        "Shadow per-field agreement of SEC as-filed statements with the EODHD fundamentals of the US producer; never served.",
    )
    published_at = datetime.now(timezone.utc)
    return database.save_analysis_snapshot(
        RECONCILIATION_ANALYSIS,
        f"{market}_ASFILED_RECONCILIATION",
        methodology_id,
        {"schema": RECONCILIATION_SCHEMA, "market": market, "as_of": utc_instant(as_of).isoformat(), "tolerance": AGREEMENT_TOLERANCE},
        {"schema": RECONCILIATION_SCHEMA, "fields": summarize_reconciliations(per_symbol), "symbols": per_symbol,
         "unmapped": unmapped, "compared_symbols": len(per_symbol)},
        published_at,
    )


# -- the US revaluation trigger (migration 053) -------------------------------------------------------------------------

_STALENESS_KEYS = ("id", "market", "symbol", "issuer_key", "doc_id", "form", "items", "accepted_at", "period_of_report", "state", "reason",
                   "official_cycle_id", "prediction_instant", "fundamentals_as_of", "expected_period_end", "covers_period",
                   "queued_for_cut_at", "recorded_at")


class TpStalenessStore:
    """Append-only marks of ``valuation_tp_staleness``; one row per (doc_id, symbol, state)."""

    def __init__(self, database: Database) -> None:
        self.database = database
        if not hasattr(database, "_valuation_tp_staleness"):
            database._valuation_tp_staleness = []  # type: ignore[attr-defined]

    def append(self, rows: Sequence[Mapping[str, Any]]) -> int:
        if not rows:
            return 0
        prepared = [{key: row.get(key) for key in _STALENESS_KEYS} | {"id": str(row.get("id") or uuid4())} for row in rows]
        for row in prepared:
            if row["state"] not in {STALE, CLEARED, UNTRACKED} or not row["symbol"] or not row["doc_id"] or not row["reason"]:
                raise ValueError(f"malformed staleness mark {row!r}")
        if not self.database.database_url:
            store: list[dict[str, Any]] = self.database._valuation_tp_staleness  # type: ignore[attr-defined]
            existing = {(row["doc_id"], row["symbol"], row["state"]) for row in store}
            written = 0
            for row in prepared:
                key = (row["doc_id"], row["symbol"], row["state"])
                if key in existing:
                    continue
                existing.add(key)
                store.append(row)
                written += 1
            return written
        written = 0
        with self.database.connection() as connection:
            for row in prepared:
                cursor = connection.execute(
                    f"""
                    INSERT INTO valuation_tp_staleness ({', '.join(_STALENESS_KEYS)})
                    VALUES ({', '.join(['%s'] * len(_STALENESS_KEYS))})
                    ON CONFLICT ON CONSTRAINT valuation_tp_staleness_once DO NOTHING
                    """,
                    tuple(row[key] for key in _STALENESS_KEYS),
                )
                written += max(0, cursor.rowcount or 0)
            connection.commit()
        return written

    def rows(self, *, doc_ids: Iterable[str] | None = None, accepted_since: datetime | None = None) -> list[dict[str, Any]]:
        wanted = sorted({str(doc_id) for doc_id in doc_ids}) if doc_ids is not None else None
        if wanted is not None and not wanted:
            return []
        since = utc_instant(accepted_since) if accepted_since is not None else None
        if not self.database.database_url:
            return [
                dict(row) for row in self.database._valuation_tp_staleness  # type: ignore[attr-defined]
                if (wanted is None or row["doc_id"] in wanted) and (since is None or utc_instant(row["accepted_at"]) >= since)
            ]
        clauses: list[str] = []
        arguments: list[Any] = []
        if wanted is not None:
            clauses.append("doc_id = ANY(%s)")
            arguments.append(wanted)
        if since is not None:
            clauses.append("accepted_at >= %s")
            arguments.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT {', '.join(key if key != 'id' else 'id::text' for key in _STALENESS_KEYS)} FROM valuation_tp_staleness {where} "
                "ORDER BY recorded_at, doc_id, symbol",
                arguments,
            ).fetchall()
        return [dict(zip(_STALENESS_KEYS, row)) for row in rows]

    def rows_known_at(self, at: datetime) -> list[dict[str, Any]]:
        """The marks a reader at ``at`` could have read: written by a pass whose clock (``recorded_at``) is at or before
        ``at`` AND — PostgreSQL — inserted by then (``created_at``, the insert's transaction clock). A mark a later pass
        wrote, a pass replayed with a past clock, or a pass that straddles ``at`` and inserts after it never reaches a
        decision taken at ``at``: a replay of an old night reads what that night could read. The memory double keeps no
        ``created_at`` (a test row may carry one: then it is applied too)."""
        clock = utc_instant(at)
        if not self.database.database_url:
            return [
                dict(row) for row in self.database._valuation_tp_staleness  # type: ignore[attr-defined]
                if utc_instant(row["recorded_at"]) <= clock and (row.get("created_at") is None or utc_instant(row["created_at"]) <= clock)
            ]
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT {', '.join(key if key != 'id' else 'id::text' for key in _STALENESS_KEYS)} FROM valuation_tp_staleness "
                "WHERE recorded_at <= %s AND created_at <= %s ORDER BY recorded_at, doc_id, symbol, state",
                (clock, clock),
            ).fetchall()
        return [dict(zip(_STALENESS_KEYS, row)) for row in rows]


def staleness_table_present(database: Database) -> bool:
    """Whether migration 053 is applied where ``database`` reads: PostgreSQL ``to_regclass`` of the table the writer
    inserts into (the connection's search path); in memory, the store's list on the ``Database`` — present once a
    writer created it, as ``valuation_pit_rerun`` reads the as-filed tables. Never creates anything."""
    if not database.database_url:
        return isinstance(getattr(database, "_valuation_tp_staleness", None), list)
    with database.connection() as connection:
        found = connection.execute("SELECT to_regclass(%s)::text", (STALENESS_TABLE,)).fetchone()
    return bool(found and found[0])


def next_nightly_cut(now: datetime) -> datetime:
    """The nightly canonical cycle runs from 00:00 America/Sao_Paulo (valuation_worker); EDGAR closes at 22:00 ET, so
    the next local midnight is always the cut a filing of today waits for."""
    local = utc_instant(now).astimezone(SAO_PAULO)
    return datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=SAO_PAULO)


def next_quarter_end(end: date) -> date:
    """The fiscal quarter end after ``end``: three calendar months on for a month-end close (06-30 → 09-30, 11-30 →
    02-28), thirteen weeks on for a 52/53-week close (2025-09-27 → 2025-12-27)."""
    if (end + timedelta(days=1)).day != 1:
        return end + timedelta(weeks=13)
    month_index = end.year * 12 + end.month - 1 + 3
    year, month = divmod(month_index, 12)
    return date(year, month + 1, calendar.monthrange(year, month + 1)[1])


def announced_quarter_end(accepted_at: Any, statement_periods: Iterable[date]) -> date:
    """The fiscal quarter an earnings release (8-K item 2.02) reports: the latest quarter end before its acceptance day
    (New York), stepped forward from the issuer's latest filed statement period that ended before that day (the
    ``period_of_report`` of its registered 10-Q/10-K). Without any such period (the issuer is not backfilled yet), the
    latest calendar quarter end before that day — for an off-calendar fiscal year that is later than the true quarter
    end, so a pre-release TP is still flagged; a release more than a month after an off-calendar close may then stay
    stale until the backfill registers the issuer's statements."""
    accepted_day = utc_instant(accepted_at).astimezone(NEW_YORK).date()
    known = [period for period in statement_periods if period < accepted_day]
    if not known:
        return max(
            date(year, month, calendar.monthrange(year, month)[1])
            for year in (accepted_day.year - 1, accepted_day.year) for month in (3, 6, 9, 12)
            if date(year, month, calendar.monthrange(year, month)[1]) < accepted_day
        )
    end = max(known)
    while (following := next_quarter_end(end)) < accepted_day:
        end = following
    return end


def expected_period_end(filing: Mapping[str, Any], statement_periods: Iterable[date]) -> date:
    """The quarter end an official TP's fundamentals must reach to reflect the filing: a 10-Q/10-K's filed period
    (``period_of_report``); for an 8-K item 2.02 (or a statement without a period), the quarter it announces."""
    period = as_date(filing.get("period_of_report"))
    if filing["form"] in STATEMENT_FORMS and period is not None:
        return period
    return announced_quarter_end(filing["accepted_at"], statement_periods)


def _fundamentals_as_of(official: Mapping[str, Any] | None) -> date | None:
    try:
        return as_date((official or {}).get("fundamentals_as_of"))
    except ValueError:
        return None


def _covers_period(expected: date, official: Mapping[str, Any]) -> bool:
    """Whether the official row's fundamentals reach ``expected`` (within the provider's labelling tolerance)."""
    fundamentals = _fundamentals_as_of(official)
    return fundamentals is not None and fundamentals >= expected - timedelta(days=PERIOD_TOLERANCE_DAYS)


def _official_clock(official: Mapping[str, Any]) -> datetime | None:
    try:
        return utc_instant(official["prediction_instant"]) if official.get("prediction_instant") else None
    except ValueError:
        return None


def _mark(filing: Mapping[str, Any], symbol: str, *, state: str, reason: str, official: Mapping[str, Any] | None,
          now: datetime, expected: date | None = None, covers: bool | None = None) -> dict[str, Any]:
    return {
        "market": str((official or {}).get("official_market") or MARKET),
        "symbol": symbol,
        "issuer_key": filing["issuer_key"],
        "doc_id": filing["doc_id"],
        "form": filing["form"],
        "items": filing.get("items") or "",
        "accepted_at": utc_instant(filing["accepted_at"]),
        "period_of_report": as_date(filing.get("period_of_report")),
        "state": state,
        "reason": reason,
        "official_cycle_id": str(official["official_cycle_id"]) if official and official.get("official_cycle_id") else None,
        "prediction_instant": _official_clock(official) if official else None,
        "fundamentals_as_of": _fundamentals_as_of(official),
        "expected_period_end": expected,
        "covers_period": covers,
        "queued_for_cut_at": next_nightly_cut(now) if state == STALE else None,
        "recorded_at": utc_instant(now),
    }


def evaluate_us_filings(database: Database, *, now: datetime | None = None) -> dict[str, int]:
    """The US revaluation trigger, idempotent: every trigger filing registered in the last ``TRIGGER_LOOKBACK_DAYS`` is
    evaluated per symbol (``stale`` / ``cleared`` / ``untracked``); every pending ``stale`` mark — whatever its age — is
    re-checked against the official TP in force and ``cleared`` once a cycle predicted after the acceptance AND whose
    fundamentals reach the reported period (``expected_period_end``: the filed period of a 10-Q/10-K, the announced
    quarter of an 8-K 2.02) is official. ``untracked`` is not terminal: inside the lookback the pair is evaluated again
    on every pass, so a TP that enters the generation later is still marked. Reads ONE generation for the whole pass."""
    clock = utc_instant(now or datetime.now(timezone.utc))
    vintages = StatementVintageStore(database)
    staleness = TpStalenessStore(database)
    states: dict[tuple[str, str], set[str]] = {}
    for row in staleness.rows():
        states.setdefault((row["doc_id"], row["symbol"]), set()).add(row["state"])
    pending_documents = {doc_id for (doc_id, _), known in states.items() if STALE in known and CLEARED not in known}
    recent = vintages.filings(MARKET, source=FILING_SOURCE, accepted_since=clock - timedelta(days=TRIGGER_LOOKBACK_DAYS))
    recent_documents = {filing["doc_id"] for filing in recent}
    older = vintages.filings(MARKET, source=FILING_SOURCE, doc_ids=pending_documents - recent_documents)
    filings = [filing for filing in [*older, *recent] if is_trigger_filing(filing["form"], filing_items(filing.get("items")))]

    def is_open(filing: Mapping[str, Any], symbol: str) -> bool:
        known = states.get((filing["doc_id"], symbol), set())
        if CLEARED in known:
            return False
        return STALE in known or not known or filing["doc_id"] in recent_documents  # untracked: re-evaluated in the lookback

    open_pairs = [(filing, symbol) for filing in filings for symbol in filing.get("symbols") or () if is_open(filing, symbol)]
    counts = {"filings": len(filings), "evaluated": len(open_pairs), "stale": 0, "cleared": 0, "untracked": 0}
    if not open_pairs:
        return counts
    generation = current_generation(database)
    served = official_rows(database, MARKET, generation=generation) if generation else {}  # NASDAQ + NYSE, one generation
    periods_by_issuer: dict[str, list[date]] = {}

    def statement_periods(issuer_key: str) -> list[date]:
        if issuer_key not in periods_by_issuer:
            periods_by_issuer[issuer_key] = [
                period for row in vintages.filings(MARKET, source=FILING_SOURCE, issuer_key=issuer_key)
                if row["form"] in STATEMENT_FORMS and (period := as_date(row.get("period_of_report"))) is not None
            ]
        return periods_by_issuer[issuer_key]

    marks: list[dict[str, Any]] = []
    for filing, symbol in open_pairs:
        known = states.get((filing["doc_id"], symbol), set())
        official = served.get(symbol)
        if official is None:
            if not known:
                marks.append(_mark(filing, symbol, state=UNTRACKED, reason="no_official_tp", official=None, now=clock))
            continue
        predicted = _official_clock(official)
        expected = expected_period_end(filing, statement_periods(str(filing["issuer_key"])))
        covers = _covers_period(expected, official)
        after = predicted is not None and predicted > utc_instant(filing["accepted_at"])
        if after and covers:
            reason = "revalued_by_cut" if STALE in known else "tp_after_acceptance"
            marks.append(_mark(filing, symbol, state=CLEARED, reason=reason, official=official, now=clock, expected=expected, covers=covers))
        elif STALE not in known:
            reason = "tp_predates_acceptance" if not after else "fundamentals_predate_period"
            marks.append(_mark(filing, symbol, state=STALE, reason=reason, official=official, now=clock, expected=expected, covers=covers))
    staleness.append(marks)
    for mark in marks:
        counts[mark["state"]] += 1
    if counts["stale"] or counts["cleared"]:
        logger.info("valuation_asfiled: US revaluation trigger %s", counts)
    return counts


def stale_us_tps(database: Database, *, since: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
    """symbol → its pending stale marks (no ``cleared`` for the same filing yet), oldest acceptance first — EVERYTHING the
    table holds now (operations, tests). A decision reads ``us_staleness_at`` instead: the same question, causal."""
    rows = TpStalenessStore(database).rows(accepted_since=since)
    cleared = {(row["doc_id"], row["symbol"]) for row in rows if row["state"] == CLEARED}
    pending: dict[str, list[dict[str, Any]]] = {}
    for row in sorted(rows, key=lambda item: utc_instant(item["accepted_at"])):
        if row["state"] == STALE and (row["doc_id"], row["symbol"]) not in cleared:
            pending.setdefault(row["symbol"], []).append(row)
    return pending


def us_staleness_at(database: Database, at: datetime) -> dict[str, Any]:
    """The causal reader of migration 053 for a decision taken at ``at`` (the decisor's run clock): the state of every
    (filing, symbol) AS KNOWN AT ``at`` — only the marks ``TpStalenessStore.rows_known_at`` returns; per pair the latest
    of them by ``recorded_at`` (a tie, which the trigger never writes, resolves to the stricter state) — and the pairs
    whose latest state is ``stale``. A ``cleared`` written after ``at`` never reaches it: a re-run of an old night reads
    what that night read, and decides the same.

    ``{"status": "ok", "known_at", "marks_known", "latest_recorded_at", "pending": {symbol: [mark, …]}}`` — the full
    marks, oldest acceptance first — or ``{"status": "unavailable", "detail"}`` when the table is absent (migration 053
    not applied). A read that fails raises, as every other read of the decisor does."""
    clock = utc_instant(at)
    if not staleness_table_present(database):
        return {"status": "unavailable", "known_at": clock.isoformat(), "detail": f"{STALENESS_TABLE} absent (migration 053 not applied)"}
    known = TpStalenessStore(database).rows_known_at(clock)
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in known:
        key = (str(row["doc_id"]), str(row["symbol"]))
        order = (utc_instant(row["recorded_at"]), _STATE_ORDER.get(str(row["state"]), len(_STATE_ORDER)))
        held = latest.get(key)
        if held is None or order > (utc_instant(held["recorded_at"]), _STATE_ORDER.get(str(held["state"]), len(_STATE_ORDER))):
            latest[key] = row
    pending: dict[str, list[dict[str, Any]]] = {}
    for (_, symbol), row in sorted(latest.items(), key=lambda item: (utc_instant(item[1]["accepted_at"]), item[0])):
        if row["state"] == STALE:
            pending.setdefault(symbol, []).append(dict(row))
    newest = max((utc_instant(row["recorded_at"]) for row in known), default=None)
    return {"status": "ok", "known_at": clock.isoformat(), "marks_known": len(known),
            "latest_recorded_at": newest.isoformat() if newest is not None else None, "pending": pending}
