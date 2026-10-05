"""Descriptive P5_NO_EOD from already archived evidence, never provider I/O.

The caller must verify the original journal/hash chain and the official daily
source before passing events. event_clock_through is the END of demonstrated
coverage from the official detector, not the last event seen or wall clock.
Absence of detector evidence is explicitly N/D. This evaluator neither asks
for more data nor alters the official ledger, gates, sizing, or estimator.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from . import r2d2_v2_portfolio as ledger
from .r2d2_v2_calendar import ShadowCalendar
from .r2d2_v2_earnings_events import validate_observation, window_covers
from .r2d2_v2_earnings_policy import event_intersects

ND_REASONS = ("CF_QUOTE_UNAVAILABLE", "CF_EVENT_CLOCK_UNAVAILABLE",
              "CF_AMBIGUOUS", "CF_FIRST_BAR_UNRESOLVED")


def _result(reason: str | None, record: Mapping[str, Any], evidence: Sequence[str]) -> dict[str, Any]:
    pnl = ledger._pnl(record, require_terminal=True) if reason is None else None
    if reason is None and pnl is None:
        reason = "CF_EVENT_CLOCK_UNAVAILABLE"
    risk = record["initial_r_usd"]
    return {"schema": "P5_NO_EOD_RESULT_V1", "reason": reason, "defined": reason is None,
            "pnl_usd": pnl, "pnl_r": pnl / risk if pnl is not None else None,
            "exit_cause": record.get("exit_cause") if reason is None else None,
            "fill_evidence": record.get("fill_evidence") if reason is None else None,
            "evidence_sha256": list(evidence), "descriptive_only": True,
            "official_effect": False}


def evaluate(seed: Mapping[str, Any], events: Sequence[Mapping[str, Any]], *,
             eod_at: str, as_of: str, event_clock_through: str | None,
             event_clock_from: str | None = None) -> dict[str, Any]:
    """Replay a frozen pre-EOD research episode without the EOD exit rule.

    Only official daily BAR, previously captured regular QUOTE and original
    detector/corporate events are admissible. An unresolved first partial day
    cannot be silently discarded to obtain a favorable later result. Every
    causal event's bytes are hashed in the private result. Missing evidence is
    N/D, including at maturity; no closing-price stand-in is permitted.
    """
    if seed.get("kind") != "RESEARCH" or seed.get("q0") != 1 or seed.get("status") != "OPEN":
        raise ValueError("CF_FROZEN_OPEN_RESEARCH_SEED_REQUIRED")
    cutoff, through = ledger._time(eod_at), ledger._time(as_of)
    if cutoff < ledger._time(seed["opened_at"]) or through < cutoff:
        raise ValueError("CF_CLOCK_INVALID")
    record = deepcopy(dict(seed))
    record["eod_windows"] = {}
    record.pop("p5_no_eod", None)
    if record.get("intent") and record["intent"]["cause"] == "EOD_POSITIVE":
        record["intent"] = None
    proofs: list[str] = []
    if event_clock_through is None or event_clock_from is None or ledger._time(event_clock_from) > cutoff:
        return _result("CF_EVENT_CLOCK_UNAVAILABLE", record, proofs)
    clock_end = ledger._time(event_clock_through)
    calendar = ShadowCalendar()
    scratch = ledger.new_portfolio()
    evidence = []
    for supplied in events:
        item = dict(supplied)
        available, at = ledger._time(item["available_at"]), ledger._time(item["at"])
        if at > available:
            raise ValueError("CF_NONCAUSAL_EVENT")
        if available > through:
            continue  # never let evidence beyond the reading enter the result
        if item.get("instrument_key") != seed["instrument_key"]:
            continue
        if available < cutoff:
            continue
        evidence.append(item)
    priorities = {"SPLIT": 1, "DIVIDEND_ENTITLEMENT": 1, "DIVIDEND_PAYMENT": 1,
                  "EARNINGS": 2, "EARNINGS_OBSERVATION_FAILED": 2, "BAR": 3, "QUOTE": 4}
    evidence.sort(key=lambda e: (ledger._time(e["available_at"]), ledger._time(e["at"]),
                                 priorities.get(e["type"], 10), e["event_id"]))
    covered_until = cutoff
    seen: dict[str, str] = {}
    for item in evidence:
        digest = ledger._digest(item)
        key = item["event_id"]
        if key in seen:
            if seen[key] != digest:
                raise ValueError("CF_CONFLICTING_EVENT_REPLAY")
            continue
        seen[key] = digest
        kind = item["type"]
        if kind not in priorities:
            continue  # no new use of intraday trades, marks or invented prices
        at, available = ledger._time(item["at"]), ledger._time(item["available_at"])
        if at > clock_end:
            return _result("CF_EVENT_CLOCK_UNAVAILABLE", record, proofs)
        proofs.append(digest)
        maturity = ledger._time(record["maturity_at"])
        known_until = ledger._time(item["end_at"]) if kind == "BAR" else at
        if known_until >= maturity:
            ledger._intent(record, "TIME", record["maturity_at"])
        if kind == "BAR":
            day = at.date()
            if not calendar.is_session(day):
                raise ValueError("CF_OFFICIAL_DAILY_BAR_REQUIRED")
            bounds = calendar.details(day)
            end = ledger._time(item["end_at"])
            if (at != bounds["open"] or end != bounds["close"] or
                    item.get("regular") is not True or item.get("coverage_complete") is not True):
                raise ValueError("CF_OFFICIAL_DAILY_BAR_REQUIRED")
            if end <= cutoff:
                continue
            if at < cutoff:
                # Same-session daily extremes include the pre-EOD path. A5
                # needs complete trades to resolve the portion after the exit.
                if not item.get("trades"):
                    return _result("CF_FIRST_BAR_UNRESOLVED", record, proofs)
                original_open = record["opened_at"]
                record["opened_at"] = eod_at
                ledger._apply_bar(scratch, record, item)
                record["opened_at"] = original_open
            else:
                # Require the trailing first session and each intervening
                # official session; weekends are not missing observations.
                previous_day = covered_until.date()
                if previous_day < day:
                    if covered_until < calendar.details(previous_day)["close"]:
                        return _result("CF_FIRST_BAR_UNRESOLVED", record, proofs)
                    sessions = calendar.between(previous_day, day)
                    if len(sessions) != 2:
                        return _result("CF_FIRST_BAR_UNRESOLVED", record, proofs)
                ledger._apply_bar(scratch, record, item)
            covered_until = max(covered_until, end)
        elif kind == "QUOTE":
            # Original A7 only. This does not evaluate EOD or reset the horizon.
            if item.get("regular") is True and not calendar.regular(at):
                raise ValueError("CF_REGULAR_QUOTE_REQUIRED")
            ledger._apply_quote(scratch, record, item, evaluate_eod=False)
        elif kind.startswith("DIVIDEND_") or kind == "SPLIT":
            ledger._corporate(scratch, record, item)
        elif kind == "EARNINGS_OBSERVATION_FAILED":
            return _result("CF_EVENT_CLOCK_UNAVAILABLE", record, proofs)
        elif kind == "EARNINGS":
            validate_observation(item, detected_at=available)
            if not window_covers(item, opened_at=ledger._time(record["opened_at"]), maturity_at=maturity):
                return _result("CF_EVENT_CLOCK_UNAVAILABLE", record, proofs)
            if event_intersects(item, opened_at=ledger._time(record["opened_at"]), maturity_at=maturity):
                ledger._intent(record, "EVENT", item["available_at"])
        if record["category"] == "ambiguous":
            return _result("CF_AMBIGUOUS", record, proofs)
        if record["order_unknown"] or record["accounting_unknown"]:
            reason = ("CF_FIRST_BAR_UNRESOLVED" if "PARTIAL_ENTRY_BAR_WITHOUT_TRADES" in record["flags"]
                      else "CF_EVENT_CLOCK_UNAVAILABLE")
            return _result(reason, record, proofs)
        if record["status"] == "CLOSED":
            terminal = ledger._time(record["exit_at"] or record["exit_interval"][-1])
            if clock_end < terminal:
                return _result("CF_EVENT_CLOCK_UNAVAILABLE", record, proofs)
            if record["exit_cause"] in {"TIME", "EVENT"} and covered_until < terminal:
                return _result("CF_FIRST_BAR_UNRESOLVED", record, proofs)
            return _result(None, record, proofs)
    if clock_end < min(through, ledger._time(record["maturity_at"])):
        return _result("CF_EVENT_CLOCK_UNAVAILABLE", record, proofs)
    return _result("CF_QUOTE_UNAVAILABLE" if record["intent"] or through >= ledger._time(record["maturity_at"])
                   else "CF_FIRST_BAR_UNRESOLVED", record, proofs)


def paired_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """All subjected episodes remain in denominators; only defined pairs differ."""
    result: dict[str, Any] = {}
    for row in rows:
        cf = row["counterfactual"]
        if row["arm"] not in {"ELIGIBLE", "CONTROL"} or (
                cf["defined"] is not True and cf["reason"] not in ND_REASONS):
            raise ValueError("CF_COMPARISON_ROW_INVALID")
    for arm in ("ELIGIBLE", "CONTROL"):
        selected = [row for row in rows if row["arm"] == arm]
        defined = [row for row in selected if row["counterfactual"]["defined"]]
        paired = [row for row in defined if row["official_pnl_usd"] is not None]
        diffs = [ledger._number(row["official_pnl_usd"]) - ledger._number(row["counterfactual"]["pnl_usd"]) for row in paired]
        paired_r = [row for row in paired if row.get("official_pnl_r") is not None]
        diffs_r = [ledger._number(row["official_pnl_r"]) - ledger._number(row["counterfactual"]["pnl_r"]) for row in paired_r]
        result[arm] = {"subjected_episodes": len(selected), "counterfactual_defined": len(defined),
            "paired_episodes": len(paired), "paired_coverage": len(paired) / len(selected) if selected else None,
            "nd_counts": {reason: sum(row["counterfactual"]["reason"] == reason for row in selected) for reason in ND_REASONS},
            "ambiguous_episodes": sum(row["counterfactual"]["reason"] == "CF_AMBIGUOUS" for row in selected),
            "difference_pnl_usd_sum": sum(diffs) if paired else None,
            "difference_pnl_usd_mean": sum(diffs) / len(paired) if paired else None,
            "paired_episodes_r": len(paired_r),
            "difference_pnl_r_sum": sum(diffs_r) if paired_r else None,
            "difference_pnl_r_mean": sum(diffs_r) / len(paired_r) if paired_r else None}
    return {"schema": "P5_NO_EOD_PAIRED_V1", "arms": result, "descriptive_only": True,
            "coverage_limitation": "Conditional coverage does not establish benefit for the whole population.",
            "official_effect": False, "p_values": None}
