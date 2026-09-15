"""P5 export from the collector's verified immutable archive, without new data.

The current event schema carries an earnings forecast window, not a certificate
of uninterrupted detector operation. Never treat that forecast, or an empty
event list, as observed detector-clock coverage after an official EOD exit.
Those altered trajectories are N/D until the archived evidence determines them.
Episodes on which EOD caused no exit retain the identical official trajectory.
This limitation is published rather than hidden by dropping the denominator.
"""
from __future__ import annotations

from typing import Any

from .r2d2_v2_counterfactual import evaluate, paired_summary
from .r2d2_v2_portfolio import _pnl
from .r2d2_v2_store import ShadowIntegrityError, digest, utc, verify_journal


def summarize(saved: dict, journal: list[dict] | None, *, sessions: list[str], cutoff: str) -> dict[str, Any]:
    if digest(saved["state"]) != saved["state_sha"]:
        raise ShadowIntegrityError("STATE_HASH_MISMATCH")
    state = saved["state"]
    if journal is not None:
        verify_journal(saved, journal)
    raw_receipts = {}
    cursor = {}
    for record in journal or []:
        payload = record["payload"]
        if payload.get("type") != "SOURCE_CURSOR":
            continue
        if (payload.get("previous_sha256") != digest(cursor)
                or payload.get("cursor_sha256") != digest(payload.get("cursor"))):
            raise ShadowIntegrityError("P5_RAW_CURSOR_CHAIN_MISMATCH")
        cursor = payload["cursor"]
        for identity, receipt in payload.get("raw_receipts", {}).items():
            if identity in raw_receipts:
                raise ShadowIntegrityError("P5_RAW_RECEIPT_DUPLICATED")
            raw_receipts[identity] = (receipt, record["recorded_at"])
    if journal is not None and cursor != state.get("raw_source_cursor", {}):
        raise ShadowIntegrityError("P5_RAW_CURSOR_HEAD_MISMATCH")
    through = utc(cutoff)
    events: dict[str, list[dict]] = {}
    used_records = []
    for record in journal or []:
        if utc(record["recorded_at"]) > through:
            continue
        payload = record["payload"]
        if payload.get("type") != "SOURCE_EVENT" or payload.get("applied_event") is None:
            continue
        source, applied = payload["source"], payload["applied_event"]
        retained = state["event_receipts"].get(source["event_id"]) == source["envelope_sha256"]
        raw_retained = raw_receipts.get(source["event_id"]) == (source["envelope_sha256"], record["recorded_at"])
        if (not (retained or raw_retained)
                or applied["event_id"] != source["event_id"]
                or utc(applied["available_at"]) > utc(record["recorded_at"])):
            raise ShadowIntegrityError("P5_SOURCE_RECEIPT_MISMATCH")
        events.setdefault(applied["instrument_key"], []).append(applied)
        used_records.append(record["record_sha"])
    rows = []
    for record in state["ledger"]["research"].values():
        if record["session"] not in sessions or not record.get("eod_windows"):
            continue
        windows = []
        for day, window in record["eod_windows"].items():
            observations = window.get("observations", [])
            first_known = (observations[0]["observed_at"] if observations
                           else window.get("observed_at") or window.get("session_close"))
            if first_known is not None and utc(first_known) <= through:
                windows.append(day)
        if not windows:
            continue
        # Do not use an official result learned after the fixed cohort cutoff.
        terminal_known = record.get("exit_available_at") and utc(record["exit_available_at"]) <= through
        pnl = _pnl(record, require_terminal=True) if terminal_known else None
        if record.get("exit_cause") == "EOD_POSITIVE" and terminal_known:
            frozen = record.get("p5_no_eod")
            if frozen is None:
                raise ShadowIntegrityError("P5_FROZEN_SEED_MISSING")
            # No existing journal record certifies a continuous detector range.
            # Supplying None is intentional N/D, not a guessed last-round time.
            cf = evaluate(frozen["seed"], events.get(record["instrument_key"], []),
                eod_at=frozen["eod_at"], as_of=cutoff,
                event_clock_from=None, event_clock_through=None)
        elif pnl is not None:
            cf = {"defined": True, "reason": None, "pnl_usd": pnl,
                  "pnl_r": pnl / record["initial_r_usd"], "basis": "IDENTICAL_NO_EOD_EXIT"}
        else:
            reason = "CF_AMBIGUOUS" if record.get("category") == "ambiguous" else "CF_EVENT_CLOCK_UNAVAILABLE"
            cf = {"defined": False, "reason": reason, "pnl_usd": None, "pnl_r": None}
        rows.append({"arm": record["arm"], "official_pnl_usd": pnl,
                     "official_pnl_r": pnl / record["initial_r_usd"] if pnl is not None else None,
                     "counterfactual": cf})
    result = paired_summary(rows)
    return {**result, "archive_status": "VERIFIED" if journal is not None else "UNAVAILABLE",
            "archive_record_count": len(used_records), "archive_evidence_sha256": digest(used_records),
            "detector_clock_coverage": "NOT_ESTABLISHED_BY_CURRENT_EVENT_SCHEMA",
            "observation_cutoff_at": cutoff}
