"""Path A normalization from injected private receipts; no acquisition or writes.

Receipt assertions are inputs to auditing, not independently verified coverage.
Historical arithmetic is retained; coverage guards are the owner's RC-4 policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import hashlib
import json
from typing import Any

from app.foreign_listings import normalize_foreign_fundamentals, policy_for
from app.market_data.eodhd import EodhdClient
from app.market_data.fmp import FmpClient
from app.official_fundamentals import apply_official_fundamentals
from app.r2d2_v2_risk_acquisition import SourceReceipt
from app.r2d2_v2_risk_direct_insider import SCHEMA as DIRECT_INSIDER_SCHEMA, assess_direct_insider
from app.r2d2_v2_risk_normalization import (
    canonical_growth_ratio, canonical_symbol, finite_number, grade_candidates,
    insider_event_candidates, institutional_candidate, strict_day,
)
from app.r2d2_v2_risk_source import (
    COMPONENTS, ORIGIN_REVISION, CanonicalRiskInputs, ComponentEvidence,
    adapt_canonical_risk,
)


@dataclass(frozen=True)
class PrivateSnapshot:
    """Exact snapshot bytes and factual read time from read-only DB transaction."""
    body: bytes
    received_at: datetime
    source_id: str

    def payload(self) -> Any:
        return json.loads(self.body)

    @property
    def payload_sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


def _day_clock(value: Any) -> datetime | None:
    day = strict_day(value)
    return datetime.combine(day, time.min, timezone.utc) if day else None


def _number(value: Any) -> float | None:
    try:
        return finite_number(value)
    except ValueError:
        return None


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _sum(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [v for row in rows[:4] if (v := _number(row.get(field))) is not None]
    return sum(values) if values else None


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def prepare_path_a(raw: dict[str, Any], *, symbol: str,
                   overlay: dict[str, Any] | None, fx_rate: float | None,
                   quote_price: float | None) -> dict[str, Any]:
    """Canonical normalize -> FX -> official overlay, on injected snapshots.

    The official helper's appliedAt wall-clock metadata is discarded: it is not
    an input, a source clock, nor part of the calculation receipt.
    """
    if canonical_symbol(raw.get("General", {}).get("Code")) != canonical_symbol(symbol):
        raise ValueError("FUNDAMENTALS_IDENTITY_MISMATCH")
    fundamentals = EodhdClient._normalize_fundamentals(raw)
    policy = policy_for(symbol)
    if policy is not None:
        if fx_rate is None or quote_price is None:
            raise ValueError("PATH_A_FX_MISSING")
        fundamentals = normalize_foreign_fundamentals(
            fundamentals, policy=policy, fx_rate=finite_number(fx_rate),
            quote_price=finite_number(quote_price))
    result = apply_official_fundamentals(fundamentals, overlay)
    if isinstance(result.get("officialFundamentals"), dict):
        result["officialFundamentals"].pop("appliedAt", None)
    return result


def fundamental_candidates(fundamentals: dict[str, Any]) -> tuple[dict[str, float | None], dict[str, Any]]:
    """Exact precedence of _analyze; missing defaults never prove coverage."""
    beta = _positive(fundamentals.get("beta"))
    growth = _number(fundamentals.get("earningsGrowthAnnual"))
    growth_receipt: dict[str, Any] = {"normalization": "ORIGIN_RATIO_ABS_GT_2_DIVIDE_100", "input_value": None}
    if growth is not None:
        growth, growth_receipt = canonical_growth_ratio(growth)
    income = _rows(fundamentals.get("quarterlyIncome"))
    cash = _rows(fundamentals.get("quarterlyCashFlow"))
    balance = _rows(fundamentals.get("quarterlyBalance"))
    debt = _positive(fundamentals.get("totalDebt")) or 0.0
    if balance:
        debt = (_number(balance[0].get("shortLongTermDebtTotal"))
                or _number(balance[0].get("netDebt")) or debt)
    ebitda = _sum(income, "ebitda") or _positive(fundamentals.get("ebitda"))
    cashflow = _sum(cash, "freeCashFlow")
    if cashflow is None:
        cashflow = _number(fundamentals.get("freeCashflow"))
    ratio = debt / ebitda if ebitda and debt >= 0 else None
    return {"beta": beta, "earnings_growth": growth,
            "debt_to_ebitda": ratio, "free_cashflow": cashflow}, growth_receipt


def _ttm_covered(rows: list[dict[str, Any]], field: str, decision_at: datetime) -> bool:
    selected = rows[:4]
    dates = [strict_day(row.get("date")) for row in selected]
    currencies = [row.get("currency_symbol") for row in selected]
    return (len(selected) == 4 and None not in dates and len(set(dates)) == 4
            and all(day is not None and day <= decision_at.date() for day in dates)
            and all(_number(row.get(field)) is not None for row in selected)
            and all(isinstance(code, str) and bool(code) for code in currencies)
            and len(set(currencies)) == 1)


def _receipt_payload(receipt: SourceReceipt, provider: str, path: str) -> Any:
    if (receipt.status != 200 or receipt.started_at.tzinfo is None or receipt.received_at.tzinfo is None
            or receipt.started_at > receipt.received_at
            or receipt.request.provider != provider or receipt.request.path != path
            or hashlib.sha256(receipt.body).hexdigest() != receipt.payload_sha256):
        raise ValueError("SOURCE_RECEIPT_BINDING_INVALID")
    return receipt.payload()


def build_risk_bundle(*, symbol: str, market: str, fundamentals: SourceReceipt | None = None,
                      grades: SourceReceipt | None = None, institutional: SourceReceipt | None = None,
                      insider_snapshot: PrivateSnapshot | None = None, official_snapshot: PrivateSnapshot | None = None,
                      computed_at: datetime, available_at: datetime, decision_at: datetime,
                      fx_rate: float | None = None, quote_price: float | None = None,
                      fx_receipt: PrivateSnapshot | None = None) -> dict[str, Any]:
    """Build one private assessment. The executor must validate DB provenance.

    insider snapshot: symbol, market, query_cutoff_at (factual DB query), events, sync {source='sync_sec',
    window_start, window_end, completed_at, complete, symbol}; clocks ISO UTC.
    official snapshot: symbol, market, outputs (null proves absence in snapshot).
    Empty FMP grades have unknown coverage; EODHD identity cannot prove FMP coverage.
    """
    symbol = canonical_symbol(symbol)
    if market not in {"US", "B3"}:
        raise ValueError("MARKET_INVALID")
    if market == "B3":
        policy_hash = hashlib.sha256(b"RC5:B3:COMPLETED_NULL").hexdigest()
        unsupported_evidence = {name: ComponentEvidence(True, False, "OWNER_RC5_UNSUPPORTED_MARKET", ORIGIN_REVISION,
            policy_hash, computed_at, computed_at, "Policy assessment only; no provider acquisition or input coverage") for name in COMPONENTS}
        unsupported = adapt_canonical_risk(CanonicalRiskInputs(None, None, None, None, None, None, None), unsupported_evidence,
            computed_at=computed_at, available_at=available_at, decision_at=decision_at)
        unsupported["diagnostics"].append("B3_COMPLETED_NULL_RC5")
        unsupported.pop("self_sha256", None)
        unsupported["self_sha256"] = hashlib.sha256(json.dumps(unsupported, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
        return unsupported
    if fundamentals is None or grades is None or institutional is None or insider_snapshot is None or official_snapshot is None:
        raise ValueError("US_SOURCE_RECEIPTS_REQUIRED")
    if any(clock.tzinfo is None or clock.utcoffset() is None for clock in
           (computed_at, available_at, decision_at, insider_snapshot.received_at, official_snapshot.received_at)):
        raise ValueError("BUNDLE_CLOCK_INVALID")
    path_symbol = symbol if "." in symbol else symbol + (".SA" if market == "B3" else ".US")
    raw = _receipt_payload(fundamentals, "eodhd", "/api/v1.1/fundamentals/" + path_symbol)
    official = official_snapshot.payload()
    if not isinstance(official, dict) or official.get("symbol") != symbol or official.get("market") != market or "outputs" not in official:
        raise ValueError("OFFICIAL_SNAPSHOT_IDENTITY_INVALID")
    if official["outputs"] is not None and not isinstance(official["outputs"], dict):
        raise ValueError("OFFICIAL_SNAPSHOT_INVALID")
    normalized = prepare_path_a(raw, symbol=symbol, overlay=official["outputs"],
                                fx_rate=fx_rate, quote_price=quote_price)
    overlay_applied = bool(normalized.get("officialFundamentals"))
    overlay_causal = not overlay_applied
    overlay_source = overlay_available = None
    if overlay_applied:
        try:
            overlay_source = datetime.fromisoformat(official["source_at"])
            overlay_available = datetime.fromisoformat(official["available_at"])
            overlay_period = _day_clock((official["outputs"] or {}).get("as_of"))
            overlay_causal = (overlay_source.tzinfo is not None and overlay_available.tzinfo is not None
                              and overlay_period is not None
                              and overlay_period <= overlay_source <= overlay_available <= official_snapshot.received_at <= computed_at)
        except (KeyError, TypeError, ValueError):
            overlay_causal = False
    values, growth_receipt = fundamental_candidates(normalized)
    income = _rows(normalized.get("quarterlyIncome"))
    cash = _rows(normalized.get("quarterlyCashFlow"))
    balance = _rows(normalized.get("quarterlyBalance"))
    general_clock = _day_clock(raw.get("General", {}).get("UpdatedAt"))
    income_clocks = [clock for row in income[:4] if (clock := _day_clock(row.get("date"))) is not None]
    cash_clocks = [clock for row in cash[:4] if (clock := _day_clock(row.get("date"))) is not None]
    income_clock = max(income_clocks, default=None) if len(income_clocks) == len(income[:4]) else None
    cash_clock = max(cash_clocks, default=None) if len(cash_clocks) == len(cash[:4]) else None
    observed = max(fundamentals.received_at, official_snapshot.received_at)
    hashes = {"eodhd": fundamentals.payload_sha256, "official_snapshot": official_snapshot.payload_sha256}
    if policy_for(symbol):
        if fx_receipt is None:
            raise ValueError("PATH_A_FX_RECEIPT_MISSING")
        fx = fx_receipt.payload()
        fx_source_at = datetime.fromisoformat(fx.get("source_at", ""))
        if (fx.get("symbol") != symbol or fx.get("fx_rate") != fx_rate or fx.get("quote_price") != quote_price
                or fx.get("fx_symbol") != policy_for(symbol).fx_symbol  # type: ignore[union-attr]
                or fx_source_at.tzinfo is None or not fx_source_at <= fx_receipt.received_at <= computed_at):
            raise ValueError("PATH_A_FX_RECEIPT_BINDING_INVALID")
        observed = max(observed, fx_receipt.received_at)
        hashes["fx"] = fx_receipt.payload_sha256
    combined_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    latest_balance = balance[0] if balance else {}
    balance_date = _day_clock(latest_balance.get("date"))
    # EODHD defaults missing debt legs to zero. That arithmetic is retained,
    # but a single known leg cannot prove the total debt population covered.
    debt_present = (any(_number(latest_balance.get(key)) is not None
                        for key in ("shortLongTermDebtTotal", "netDebt"))
                    or (any(_number(latest_balance.get(key)) is not None
                            for key in ("shortTermDebt", "shortLongTermDebt"))
                        and _number(latest_balance.get("longTermDebt")) is not None))
    financial_currency = cash[0].get("currency_symbol") if cash else None
    coverage = {
        "beta": values["beta"] is not None and _number(raw.get("Technicals", {}).get("Beta")) is not None,
        "earnings_growth": values["earnings_growth"] is not None and _number(raw.get("Highlights", {}).get("QuarterlyEarningsGrowthYOY")) is not None,
        "free_cashflow": _ttm_covered(cash, "freeCashFlow", decision_at) and overlay_causal,
        "debt_to_ebitda": (_ttm_covered(income, "ebitda", decision_at) and debt_present and overlay_causal and _sum(income, "ebitda") not in (None, 0)
                           and balance_date is not None and balance_date <= decision_at
                           and latest_balance.get("currency_symbol") == (income[0].get("currency_symbol") if income else None)),
    }
    growth_overlay_changed = (overlay_applied and normalized.get("earningsGrowthAnnual")
                              != EodhdClient._normalize_fundamentals(raw).get("earningsGrowthAnnual"))
    if growth_overlay_changed:
        coverage["earnings_growth"] = False  # source contract for overlay growth requires disposition
    clocks = {"beta": general_clock, "earnings_growth": general_clock,
              "free_cashflow": cash_clock,
              "debt_to_ebitda": max(income_clock, balance_date) if income_clock and balance_date else None}
    evidence = {name: ComponentEvidence(True, coverage[name] and market == "US", "PATH_A", ORIGIN_REVISION,
                combined_hash, clocks[name], observed,
                "RC4; no source TTL; observed age only; complete four-quarter rows for TTM; General.UpdatedAt for beta/growth")
                for name in COMPONENTS[:4]}
    snapshot = insider_snapshot.payload()
    if not isinstance(snapshot, dict) or snapshot.get("symbol") != symbol or snapshot.get("market") != market:
        raise ValueError("INSIDER_SNAPSHOT_IDENTITY_INVALID")
    direct_diagnostics: list[str] = []
    if snapshot.get("schema") == DIRECT_INSIDER_SCHEMA:
        insider_value, evidence["insider_activity"], direct_diagnostics = assess_direct_insider(
            snapshot, received_at=insider_snapshot.received_at, computed_at=computed_at)
        cutoff = datetime.fromisoformat(snapshot["query_cutoff_at"])
        sync_covered = evidence["insider_activity"].coverage_verified
    else:
        events = snapshot.get("events")
        if not isinstance(events, list):
            raise ValueError("INSIDER_EVENTS_INVALID")
        copied = [dict(row) for row in events]
        for row in copied:
            if isinstance(row.get("published_at"), str):
                row["published_at"] = datetime.fromisoformat(row["published_at"])
        cutoff = None
        try:
            candidate_cutoff = datetime.fromisoformat(snapshot["query_cutoff_at"])
            if candidate_cutoff.tzinfo is not None and candidate_cutoff.utcoffset() is not None:
                cutoff = candidate_cutoff
        except (ValueError, TypeError, KeyError):
            pass
        insider_value = insider_event_candidates(copied, symbol=symbol, decision_at=cutoff or decision_at) if market == "US" else None
        sync = snapshot.get("sync") or {}
        sync_covered = False
        sync_clock = None
        try:
            start, end, sync_clock = (datetime.fromisoformat(sync[key]) for key in ("window_start", "window_end", "completed_at"))
            sync_covered = (all(clock.tzinfo is not None and clock.utcoffset() is not None for clock in (start, end, sync_clock))
                            and sync.get("source") == "sync_sec" and sync.get("symbol") == symbol and sync.get("complete") is True
                            and cutoff is not None and start <= cutoff - timedelta(days=180) and end >= cutoff
                            and cutoff <= end <= sync_clock <= insider_snapshot.received_at <= computed_at)
        except (ValueError, TypeError, KeyError):
            sync_clock = None
        eligible_clocks = [row["published_at"] for row in copied
                           if row.get("symbol") == symbol and row.get("market") == "US" and row.get("source_code") == "sec"
                           and row.get("event_type") == "Insider Transaction"
                           and isinstance(row.get("published_at"), datetime)
                           and cutoff is not None and cutoff - timedelta(days=180) <= row["published_at"] <= cutoff]
        evidence["insider_activity"] = ComponentEvidence(True, sync_covered and market == "US", "ir_events/sync_sec", ORIGIN_REVISION,
            insider_snapshot.payload_sha256, max(eligible_clocks) if eligible_clocks else sync_clock,
            insider_snapshot.received_at, "180d on published_at; persisted Finnhub events; EODHD only ingestion fallback; no direct Form4 substitution")
    year, quarter = FmpClient.latest_reportable_13f_quarter(institutional.started_at.date())
    institutions = _receipt_payload(institutional, "fmp", "/stable/institutional-ownership/symbol-positions-summary")
    if dict(institutional.request.parameters) != {"symbol": symbol, "year": year, "quarter": quarter}:
        raise ValueError("INSTITUTIONAL_REQUEST_MISMATCH")
    institution_value = institutional_candidate(institutions, symbol=symbol, year=year, quarter=quarter) if institutions else None
    institutional_clock = _day_clock(institutions[0].get("date")) if institutions else None
    evidence["institutional_positions"] = ComponentEvidence(True, bool(institutions) and market == "US", "FMP_POSITIONS", ORIGIN_REVISION,
        institutional.payload_sha256, institutional_clock, institutional.received_at, "RC4 HTTP200 nonempty first row; canonical quarter end+50d; empty UNKNOWN")
    grade_rows = _receipt_payload(grades, "fmp", "/stable/grades")
    if dict(grades.request.parameters) != {"symbol": symbol}:
        raise ValueError("GRADES_REQUEST_MISMATCH")
    actions = grade_candidates(grade_rows, symbol=symbol, since=grades.started_at.date()-timedelta(days=90), through=grades.started_at.date())
    grade_clocks = [clock for row in grade_rows if (clock := _day_clock(row.get("date"))) is not None
                    and grades.started_at.date()-timedelta(days=90) <= clock.date() <= grades.started_at.date()]
    # RC4 did not define source_at for a verified empty grades population;
    # leave it unknown rather than manufacture a source timestamp from HTTP.
    evidence["recent_grade_actions"] = ComponentEvidence(True, bool(grade_rows) and market == "US", "FMP_GRADES", ORIGIN_REVISION,
        grades.payload_sha256, max(grade_clocks) if grade_clocks else None, grades.received_at,
        "HTTP200 and nonempty FMP rows with matching identity; 90d; dedup date/gradingCompany/action; empty coverage/source_at unknown")
    inputs = CanonicalRiskInputs(values["beta"], values["debt_to_ebitda"], values["earnings_growth"], values["free_cashflow"],
                                  insider_value, institution_value, actions)
    result = adapt_canonical_risk(inputs, evidence, computed_at=computed_at, available_at=available_at, decision_at=decision_at)
    result["path_a"] = {"origin_revision": ORIGIN_REVISION, "source_hashes": hashes,
                        "official_overlay_present": official["outputs"] is not None,
                        "official_overlay_applied": bool(normalized.get("officialFundamentals")),
                        "foreign_listing_policy": policy_for(symbol) is not None,
                        "growth_normalization": growth_receipt, "financial_currency": financial_currency,
                        "insider_query_cutoff_at": cutoff.isoformat() if cutoff else None,
                        "institutional_query_at": institutional.started_at.isoformat(),
                        "institutional_identity_normalization": ("STRICT_QUARTER_END_DATE" if institutions and "year" not in institutions[0] and "quarter" not in institutions[0] else "EXPLICIT_YEAR_QUARTER" if institutions else "UNAVAILABLE"),
                        "grades_query_at": grades.started_at.isoformat(),
                        "overlay_source_at": overlay_source.isoformat() if overlay_source else None,
                        "overlay_available_at": overlay_available.isoformat() if overlay_available else None,
                        "overlay_clocks_verified": overlay_causal,
                        "receipt_attestations_independently_verified": False}
    result["diagnostics"].extend(direct_diagnostics)
    if _sum(income, "ebitda") == 0:
        result["diagnostics"].append("EBITDA_ZERO_TTM_FALLBACK_UNCOVERED")
    if growth_overlay_changed:
        result["diagnostics"].append("GROWTH_OVERLAY_PROVENANCE_UNRESOLVED")
    raw_beta = _number(raw.get("Technicals", {}).get("Beta"))
    if raw_beta is not None and raw_beta <= 0:
        result["diagnostics"].append("BETA_NONPOSITIVE_COMPLETED_NULL_RC5")
    if not overlay_causal:
        result["diagnostics"].append("OFFICIAL_OVERLAY_PROVENANCE_NOT_CAUSAL")
    if not grade_rows:
        result["diagnostics"].append("GRADES_EMPTY_COVERAGE_UNKNOWN")
    elif not grade_clocks:
        result["diagnostics"].append("GRADES_WINDOW_SOURCE_AT_UNKNOWN")
    if not sync_covered:
        result["diagnostics"].append("DIRECT_INSIDER_COVERAGE_UNKNOWN" if snapshot.get("schema") == DIRECT_INSIDER_SCHEMA else "INSIDER_WINDOW_PARTIAL")
    if cutoff is None:
        result["diagnostics"].append("INSIDER_QUERY_CUTOFF_MISSING")
    result.pop("self_sha256", None)
    result["self_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    return result
