"""Causal V2 collector. This module cannot place orders or operate the V1 engine.

DIAGNOSTIC records inputs/reasons only, in a distinct immutable epoch. CERTIFIED
requires a pinned release attestation for the signed policy, code, sources and
accepted calibration. The attestation is an operator-controlled release record,
not a substitute for the audits it references. No release ships with this code.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from typing import Any

from .r2d2_v2_calendar import NEW_YORK, ShadowCalendar
from .r2d2_v2_contract import CandidateInputs, DailyBar, SplitRecord, evaluate_candidate, input_complete
from .r2d2_v2_portfolio import PortfolioBatch, apply_events, export_session_statistics, new_portfolio, register_candidate
from .r2d2_v2_sources import MANIFEST_SHA
from .r2d2_v2_store import ShadowIntegrityError, canonical, digest, utc, validate_epoch

SCHEMA = "R2D2_V2_SHADOW_STATE_V1"


def _hash(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True)
class Release:
    epoch: str
    mode: str
    first_session: date
    approved_at: datetime
    code_revision: str
    receipt_sha: str

    @classmethod
    def verify(cls, data: bytes, expected_sha: str, *, now: datetime, build_sha: str,
               calendar: ShadowCalendar) -> Release:
        if not _hash(expected_sha) or sha256(data).hexdigest() != expected_sha:
            raise ShadowIntegrityError("RELEASE_HASH_MISMATCH")
        body = json.loads(data)
        if body.get("schema") != "R2D2_V2_RELEASE_V1" or body.get("manifest_sha") != MANIFEST_SHA:
            raise ShadowIntegrityError("RELEASE_POLICY_MISMATCH")
        epoch, mode = body.get("epoch"), body.get("mode")
        validate_epoch(epoch)
        if mode not in {"DIAGNOSTIC", "CERTIFIED"}:
            raise ShadowIntegrityError("RELEASE_MODE_INVALID")
        approved = utc(body["approved_at"])
        first = date.fromisoformat(body["first_session"])
        if not approved <= utc(now) or not approved < calendar.details(first)["open"]:
            raise ShadowIntegrityError("RELEASE_MUST_PRECEDE_FIRST_SESSION")
        revision = body.get("code_revision")
        if (not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision)
                or revision != build_sha or not _hash(body.get("code_audit_sha"))
                or not isinstance(body.get("authorization_ref"), str) or not body["authorization_ref"].strip()):
            raise ShadowIntegrityError("RELEASE_CODE_OR_AUTHORIZATION_UNVERIFIED")
        if mode == "CERTIFIED" and (body.get("calibration_status") != "ACCEPTED"
                or not _hash(body.get("calibration_sha")) or not _hash(body.get("source_audit_sha"))):
            raise ShadowIntegrityError("CALIBRATION_AND_SOURCES_REQUIRED")
        return cls(epoch, mode, first, approved, revision, expected_sha)


def _dt(value):
    try:
        return utc(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _object(value) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def candidate_inputs(row: dict, batch: dict, now: datetime, calendar: ShadowCalendar) -> CandidateInputs:
    """Map evidence without synthesizing missing fields or normalizing scores."""
    now = utc(now)
    day = now.astimezone(NEW_YORK).date()
    detail = calendar.details(day)
    quote, daily, risk, earnings = (_object(row.get(k)) for k in ("quote", "daily", "risk", "earnings"))
    provenance = _object(batch.get("provenance"))
    producer, version = provenance.get("producer"), provenance.get("version")
    component = {"quote": quote, "daily": daily, "risk": risk, "earnings": earnings,
                 "splits": daily, "universe": batch,
                 "calendar": {"source_at": now.isoformat(), "available_at": now.isoformat()}}
    source_at = {name: _dt(item.get("source_at")) for name, item in component.items()}
    # Quotes carry separate event clocks and a shared receipt.
    if quote.get("bid_source_at") is not None and quote.get("ask_source_at") is not None:
        clocks = [_dt(quote.get(k)) for k in ("bid_source_at", "ask_source_at")]
        valid_clocks = [at for at in clocks if at is not None]
        source_at["quote"] = max(valid_clocks) if len(valid_clocks) == 2 else None
    available = {name: _dt(item.get("available_at")) for name, item in component.items()}
    sources = {name: f"{producer}.{name}" for name in component if isinstance(producer, str) and producer}
    versions = {name: version for name in component if isinstance(version, str)}
    hashes = {name: digest(item) for name, item in component.items()}
    sources["calendar"], versions["calendar"], hashes["calendar"] = (
        "exchange_calendars.XNYS", calendar.version, detail["sha256"])
    bars = []
    for item in daily.get("bars", []) if isinstance(daily.get("bars"), list) else []:
        item = _object(item)
        bars.append(DailyBar(session_date=_date(item.get("session_date")), open=item.get("open"),
            high=item.get("high"), low=item.get("low"), close=item.get("close"), volume=item.get("volume"),
            source_at=_dt(item.get("source_at")), available_at=_dt(item.get("available_at")),
            complete=item.get("complete") is True, regular_session=item.get("regular_session") is True))
    splits = []
    for item in daily.get("splits", []) if isinstance(daily.get("splits"), list) else []:
        item = _object(item)
        splits.append(SplitRecord(_dt(item.get("effective_at")), item.get("factor"),
                                  _dt(item.get("source_at")), _dt(item.get("available_at"))))
    earnings_events = earnings.get("events", [])
    earnings_clocks = [_dt(_object(item).get("event_at")) for item in earnings_events] if isinstance(earnings_events, list) else [None]
    earnings_at = tuple(at for at in earnings_clocks if at is not None)
    issues = [item["code"] for item in row.get("diagnostics", [])
              if isinstance(item, dict) and isinstance(item.get("code"), str)]
    if daily.get("coverage_verified") is not True:
        issues.append("DAILY_COVERAGE_UNVERIFIED")
    if any(at is None for at in earnings_clocks):
        issues.append("EARNINGS_EVENT_INVALID")
    if isinstance(earnings_events, list):
        for item in earnings_events:
            known_at = _dt(_object(item).get("available_at"))
            if known_at is None or known_at > now:
                issues.append("EARNINGS_EVENT_NOT_CAUSAL")
    start, end = _dt(earnings.get("window_start")), _dt(earnings.get("window_end"))
    # The port uses precise coverage instants. Never widen a partial date window.
    coverage = (earnings.get("coverage_verified") is True and start is not None and end is not None
                and start <= now and end >= detail["horizon_close"] - timedelta(minutes=5))
    return CandidateInputs(symbol=row.get("symbol", ""), market=row.get("market"),
        security_type=row.get("security_type") if row.get("classification_verified") is True else None,
        session_date=day, decision_at=now, bid=quote.get("bid"), ask=quote.get("ask"),
        bid_at=_dt(quote.get("bid_source_at")), ask_at=_dt(quote.get("ask_source_at")), risk_score=risk.get("value"),
        daily_bars=tuple(bars), previous_sessions=detail["previous_sessions"], horizon_sessions=detail["horizon_sessions"],
        horizon_close_at=detail["horizon_close"], splits=tuple(splits),
        split_coverage_verified=daily.get("split_coverage_verified") is True,
        daily_price_basis=daily.get("adjustment"), earnings_at=earnings_at,
        earnings_coverage_start=start.astimezone(NEW_YORK).date() if start else None,
        earnings_coverage_end=end.astimezone(NEW_YORK).date() if end else None,
        earnings_coverage_verified=coverage, source_at=source_at, available_at=available,
        sources=sources, source_versions=versions, source_hashes=hashes, source_issues=tuple(dict.fromkeys(issues)))


def _instrument(row: dict) -> str:
    # One name across the US universe; a listing transfer cannot open a second
    # position or change the identity of a pending snapshot within the window.
    return "US:" + str(row.get("symbol"))


def _diagnostic(state: dict, journals: list, session: dict, code: str, now: datetime):
    if code not in session["diagnostics"]:
        session["diagnostics"].append(code)
        journals.append({"journal_key": "diagnostic:" + session["date"] + ":" + code,
                         "type": "DIAGNOSTIC", "session": session["date"], "code": code})


class ShadowCollector:
    def __init__(self, store, source, release: Release, *, calendar: ShadowCalendar | None = None, clock=None):
        self.store, self.source, self.release = store, source, release
        self.calendar = calendar or ShadowCalendar()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.schedule = self.calendar.sessions(release.first_session, 39)

    def _initial(self) -> dict:
        return {"schema": SCHEMA, "epoch": self.release.epoch, "manifest_sha": MANIFEST_SHA,
                "mode": self.release.mode, "release_sha": self.release.receipt_sha,
                "code_revision": self.release.code_revision, "first_session": self.release.first_session.isoformat(),
                "calendar_version": self.calendar.version, "schedule": [d.isoformat() for d in self.schedule],
                "sessions": {}, "ledger": new_portfolio() if self.release.mode == "CERTIFIED" else None,
                "last_cycle_at": None, "event_receipts": {}, "event_sequences": {}, "data_issues": [],
                "clock_receipts": [], "last_price_at": {}, "coverage_until": {}, "gap_episode_receipts": {}, "cycle_count": 0}

    def cycle(self, now: datetime | None = None) -> dict:
        """One observation; explicit clocks are for deterministic offline tests.

The worker uses the real clock again *inside* the transaction, after file reads
and lock acquisition. Waiting cannot manufacture a decision in a past window.
"""
        live = now is None
        now = utc(self.clock() if live else now)
        batch = self.source.snapshot(now)
        events = self.source.events(now) if self.release.mode == "CERTIFIED" else []
        event_diagnostics = getattr(self.source, "last_event_diagnostics", []) if self.release.mode == "CERTIFIED" else []
        return self.store.atomic(self.release.epoch, self._initial(),
            lambda state: self._cycle(state, batch, events, event_diagnostics,
                                      utc(self.clock()) if live else now), now)

    def _cycle(self, state, batch, events, event_diagnostics, now):
        if state["calendar_version"] != self.calendar.version:
            raise ShadowIntegrityError("CALENDAR_VERSION_CHANGED")
        if state["last_cycle_at"] and now < utc(state["last_cycle_at"]):
            raise ShadowIntegrityError("COLLECTOR_CLOCK_REVERSED")
        journals = []
        portfolio = PortfolioBatch(state["ledger"]) if state["ledger"] is not None else None
        if portfolio is not None:
            state["ledger"] = portfolio.state
        active_day = now.astimezone(NEW_YORK).date()
        # Persist all elapsed official days. Monitoring can continue beyond the
        # planned 39 sessions when an exit/receivable is still unresolved.
        elapsed = self.calendar.calendar.sessions_in_range(self.release.first_session.isoformat(), active_day.isoformat()) \
            if active_day >= self.release.first_session else []
        events_processed = False
        for index, stamp in enumerate(elapsed):
            day = stamp.date()
            detail = self.calendar.details(day)
            if detail["open"] > now:
                break
            key = day.isoformat()
            session = state["sessions"].setdefault(key, {"date": key, "entry_session": index < 30,
                "calendar_sha": detail["sha256"], "capture_closed": False, "universe": None,
                "universe_sha": None, "candidates": {}, "pending": {}, "diagnostics": [], "attempts": 0})
            if state["ledger"] is not None:
                self._clock(state, journals, "SESSION_OPEN", key, detail["open"], now, portfolio=portfolio)
            if day == active_day:
                self._events(state, journals, events, event_diagnostics, now, key, portfolio=portfolio)
                events_processed = True
            if day == active_day and index < 30 and detail["capture_open"] <= now < detail["capture_close"]:
                self._capture(state, journals, session, batch, now, portfolio=portfolio)
            if now >= detail["capture_close"] and not session["capture_closed"]:
                if index < 30:
                    self._close_capture(state, journals, session, now)
                else:
                    session["capture_closed"] = True
            if state["ledger"] is not None and now >= detail["close"]:
                if day < active_day and "SESSION_CLOSE:" + key not in state["clock_receipts"]:
                    self._gap(state, journals, now, key, "COLLECTOR_MISSED_SESSION_CLOSE", portfolio=portfolio)
                self._clock(state, journals, "SESSION_CLOSE", key, detail["close"], now, portfolio=portfolio)
        if not events_processed and state["ledger"] is not None and state["ledger"]["session"]:
            self._events(state, journals, events, event_diagnostics, now, state["ledger"]["session"], portfolio=portfolio)
        if portfolio is not None:
            state["ledger"] = portfolio.finish()
        state["last_cycle_at"] = now.isoformat()
        state["cycle_count"] += 1
        response = public_summary(state)
        return state, journals, response

    @staticmethod
    def _apply(state, events, portfolio):
        if portfolio is not None:
            return [portfolio.event(event) for event in events]
        state["ledger"], result = apply_events(state["ledger"], events)
        return result

    def _clock(self, state, journals, kind, session, at, now, *, portfolio=None):
        key = kind + ":" + session
        if key in state["clock_receipts"]:
            return
        event = {"event_id": "clock:" + key, "type": kind, "session": session,
                 "at": at.isoformat(), "available_at": now.isoformat()}
        self._apply(state, [event], portfolio)
        state["clock_receipts"].append(key)
        journals.append({"journal_key": "clock:" + key, "type": "CLOCK", "event": event})

    def _gap(self, state, journals, now, session, reason, *, gap_at=None, portfolio=None):
        key = session + ":" + reason
        known = key in state["data_issues"]
        if not known:
            state["data_issues"].append(key)
        known_gap = utc(gap_at) if gap_at else now
        affected = [r for r in state["ledger"]["research"].values()
                    if r["status"] == "OPEN" or utc(r["opened_at"]) <= known_gap <
                    utc(r["exit_at"] or (r["exit_interval"] or [None, now.isoformat()])[1])]
        prior = state["gap_episode_receipts"].setdefault(key, [])
        new_episodes = sorted(r["episode_key"] for r in affected if r["episode_key"] not in prior)
        if known and not new_episodes:
            return
        prior.extend(new_episodes)
        batch_key = digest([key, new_episodes])
        events = [{"event_id": "gap:" + digest([batch_key, name]), "type": "DATA_GAP", "session": session,
                   "instrument_key": name, "reason": reason, "at": known_gap.isoformat(), "available_at": now.isoformat()}
                  for name in sorted({r["instrument_key"] for r in affected if r["episode_key"] in new_episodes})]
        self._apply(state, events, portfolio)
        journals.append({"journal_key": "gap:" + batch_key, "type": "DATA_GAP", "reason": reason, "events": events})

    def _events(self, state, journals, events, diagnostics, now, session, *, portfolio=None):
        if state["ledger"] is None:
            return
        if diagnostics:
            self._gap(state, journals, now, session, "EVENT_SOURCE_UNVERIFIED", portfolio=portfolio)
            return
        pending = []
        for item in events:
            identity, receipt = item["event_id"], item["envelope_sha256"]
            old = state["event_receipts"].get(identity)
            if old is not None:
                if old != receipt:
                    raise ShadowIntegrityError("EVENT_ID_MUTATED")
                continue
            pending.append(item)
        priority = {"SPLIT": 1, "DIVIDEND_ENTITLEMENT": 1, "DIVIDEND_PAYMENT": 1,
                    "BAR": 3, "TRADE": 3, "MARK": 4, "EARNINGS": 2, "QUOTE": 4, "DATA_GAP": 1}
        # Source sequence is a separate proof from timestamps: missing packets
        # cannot silently disappear after restart or journal-file rotation.
        for item in sorted(pending, key=lambda e: (e["source_id"], e["sequence"])):
            source = item["source_id"]
            expected = state["event_sequences"].get(source, -1) + 1
            if item["sequence"] != expected:
                self._gap(state, journals, now, session, "EVENT_SEQUENCE_GAP", portfolio=portfolio)
            state["event_sequences"][source] = max(item["sequence"], expected - 1)
        pending.sort(key=lambda e: (utc(e["available_at"]), utc(e["at"]), priority.get(e["type"], 10), e["sequence"], e["event_id"]))
        for item in pending:
            raw = {k: v for k, v in item.items() if k not in {"source_id", "source_at", "sequence", "provenance",
                    "manifest_sha", "self_sha256", "envelope_sha256", "envelope_available_at"}}
            if utc(raw["available_at"]) > now or utc(raw["at"]) > utc(raw["available_at"]):
                raise ShadowIntegrityError("EVENT_NOT_CAUSAL")
            # Producer receipt and collector receipt are both archived. A file
            # read later never grants the collector knowledge at an earlier time.
            event = {**raw, "source_available_at": raw["available_at"], "available_at": now.isoformat(), "session": session}
            identity_parts = str(event.get("instrument_key", "")).split(":")
            if len(identity_parts) == 2 and identity_parts[0] in {"NYSE", "NASDAQ", "US"}:
                event["instrument_key"] = "US:" + identity_parts[1]
            elif event["type"] in priority:
                raise ShadowIntegrityError("EVENT_US_INSTRUMENT_REQUIRED")
            if event["type"] not in priority:
                self._gap(state, journals, now, session, "SOURCE_CLOCK_EVENT_NOT_AUTHORIZED", portfolio=portfolio)
                event = None
            elif event.get("regular") is True and not self.calendar.regular(utc(event["at"]),
                    end=utc(event["end_at"]) if event.get("end_at") else None):
                self._gap(state, journals, now, session, "EVENT_REGULAR_SESSION_INVALID", portfolio=portfolio)
                event = None
            if event is not None:
                name = event["instrument_key"]
                episodes = [r for r in state["ledger"]["research"].values() if r["instrument_key"] == name]
                if episodes and event["type"] in {"TRADE", "BAR"} and event.get("regular") is True:
                    at = utc(event["at"])
                    opening = self.calendar.details(at.astimezone(NEW_YORK).date())["open"]
                    coverage = max(utc(state["coverage_until"].get(name, min(r["opened_at"] for r in episodes))), opening)
                    # A first print after a missing interval cannot close the
                    # position and thereby erase the preceding data failure.
                    if at - coverage > timedelta(seconds=90):
                        self._gap(state, journals, now, session, "LIVE_EVIDENCE_STALE", gap_at=coverage, portfolio=portfolio)
                    if event["type"] == "BAR" and event.get("coverage_complete") is True:
                        if at > coverage:
                            self._gap(state, journals, now, session, "BAR_COVERAGE_GAP", gap_at=coverage, portfolio=portfolio)
                        elif utc(event["end_at"]) > coverage:
                            state["coverage_until"][name] = event["end_at"]
                result = self._apply(state, [event], portfolio)
                if event["type"] in {"BAR", "TRADE", "QUOTE", "MARK"}:
                    state["last_price_at"][event["instrument_key"]] = event.get("end_at", event["at"])
            else:
                result = [{"status": "DATA_UNOBSERVABLE"}]
            state["event_receipts"][item["event_id"]] = item["envelope_sha256"]
            journals.append({"journal_key": "event:" + item["event_id"], "type": "SOURCE_EVENT",
                             "source": item, "applied_event": event, "result": result})
        # Missing cycles or stale evidence are data failures, not zero returns.
        for record in state["ledger"]["research"].values():
            last = utc(state["coverage_until"].get(record["instrument_key"], record["opened_at"]))
            terminal = record["exit_at"] or (record["exit_interval"] or [None, None])[1]
            if terminal and last >= utc(terminal):
                continue
            day = now.astimezone(NEW_YORK).date()
            if self.calendar.is_session(day):
                detail = self.calendar.details(day)
                if min(now, detail["close"]) - max(last, detail["open"]) > timedelta(seconds=90):
                    self._gap(state, journals, now, session, "LIVE_EVIDENCE_STALE", gap_at=max(last, detail["open"]), portfolio=portfolio)
                    break

    def _capture(self, state, journals, session, batch, now, *, portfolio=None):
        session["attempts"] += 1
        universe = _object(batch.get("universe"))
        if batch.get("status") != "AVAILABLE" or universe.get("coverage_verified") is not True:
            _diagnostic(state, journals, session, "UNIVERSE_COVERAGE_UNVERIFIED", now)
            return
        rows = universe.get("instruments", [])
        names = sorted(_instrument(row) for row in rows)
        if len(names) != len(set(names)):
            raise ShadowIntegrityError("UNIVERSE_DUPLICATE")
        if session["universe"] is None:
            session["universe"], session["universe_sha"] = names, digest(names)
            journals.append({"journal_key": "universe:" + session["date"], "type": "UNIVERSE",
                             "session": session["date"], "names": names, "source_receipt": batch.get("envelope_sha256")})
        elif names != session["universe"]:
            _diagnostic(state, journals, session, "UNIVERSE_CHANGED_WITHIN_WINDOW", now)
            return
        prepared = []
        for row in rows:
            name = _instrument(row)
            if name in session["candidates"]:
                continue
            inputs = candidate_inputs(row, batch, now, self.calendar)
            evaluation = evaluate_candidate(inputs).to_dict()
            session["pending"][name] = {"evaluation": evaluation, "source": row,
                                         "batch_receipt": batch.get("envelope_sha256")}
            if input_complete(inputs):
                available = max(t for key, t in inputs.available_at.items() if t is not None and key != "calendar")
                tie_hash = sha256(f"{self.release.epoch}|{session['date']}|{row['symbol']}".encode()).hexdigest()
                prepared.append((available, tie_hash, name))
        # Hash resolves only simultaneous availability; eligibility never ranks.
        for _, episode, name in sorted(prepared):
            observation = session["pending"].pop(name)
            evaluation = observation["evaluation"]
            session["candidates"][name] = evaluation
            record = {"journal_key": "candidate:" + session["date"] + ":" + digest(name), "type": "CANDIDATE",
                      "episode_key": episode, "instrument_key": name, "observation": observation}
            if state["ledger"] is not None and evaluation["arm"] is not None:
                blocked = "COLLECTION_DATA_GATE_BLOCKED" if state["data_issues"] else None
                kwargs: dict[str, Any] = dict(episode_key=episode,
                    instrument_key=name, session=session["date"], opened_at=now.isoformat(),
                    maturity_at=evaluation["maturity_at"], geometry=evaluation["geometry"], arm=evaluation["arm"],
                    admission_block_reason=blocked)
                if portfolio is not None:
                    research, admission = portfolio.register(**kwargs)
                else:
                    state["ledger"], research, admission = register_candidate(state["ledger"], **kwargs)
                record.update(research=research, admission=admission)
                state["coverage_until"].setdefault(name, now.isoformat())
            journals.append(record)

    def _close_capture(self, state, journals, session, now):
        if session["universe"] is None:
            _diagnostic(state, journals, session, "CAPTURE_WINDOW_WITHOUT_VERIFIED_UNIVERSE", now)
        for name in session["universe"] or []:
            if name in session["candidates"]:
                continue
            observation = session["pending"].get(name, {})
            evaluation = observation.get("evaluation", {})
            evaluation.update(status="DATA_INELIGIBLE", arm=None, research_eligible=False, portfolio_eligible=False)
            evaluation["reasons"] = list(dict.fromkeys(evaluation.get("reasons", []) + ["CAPTURE_WINDOW_INCOMPLETE"]))
            session["candidates"][name] = evaluation
            journals.append({"journal_key": "candidate:" + session["date"] + ":" + digest(name),
                             "type": "CANDIDATE_INCOMPLETE", "instrument_key": name, "observation": observation,
                             "evaluation": evaluation})
        session["pending"] = {}
        session["capture_closed"] = True
        journals.append({"journal_key": "capture-close:" + session["date"], "type": "CAPTURE_CLOSED",
                         "session": session["date"], "closed_observed_at": now.isoformat(),
                         "candidate_count": len(session["candidates"]), "diagnostics": session["diagnostics"]})


def public_summary(state: dict) -> dict:
    """No symbols, private identifiers, input values, or statistical verdicts."""
    sessions = []
    for session in state["sessions"].values():
        reasons = Counter(reason for c in session["candidates"].values() for reason in c.get("reasons", []))
        sessions.append({"session_date": session["date"], "entry_session": session["entry_session"],
            "capture_closed": session["capture_closed"], "universe_count": len(session["universe"]) if session["universe"] is not None else None,
            "snapshot_attempts": session["attempts"], "frozen_count": len(session["candidates"]),
            "reason_counts": dict(reasons), "diagnostics": session["diagnostics"]})
    return {"schema": "R2D2_V2_COLLECTOR_STATUS_V1", "epoch": state["epoch"], "manifest_sha": state["manifest_sha"],
            "mode": state["mode"], "last_cycle_at": state["last_cycle_at"], "sessions": sessions,
            "cohort_clock_started": state["mode"] == "CERTIFIED" and bool(state["sessions"]),
            "data_gate_unknown": bool(state["data_issues"]),
            "data_issue_count": len(state["data_issues"]),
            "certification_computed": False, "production_orders": False}


def export_cohort(state: dict, size: int, *, now: datetime, calendar: ShadowCalendar) -> dict:
    """Sufficient statistics for the signed estimator, only after maturity.

This does not compute a bootstrap or authorize a GO. Every programmed session,
including zero days, remains in order. Diagnostic epochs cannot be promoted.
"""
    if state["mode"] != "CERTIFIED" or size not in (20, 30):
        raise ShadowIntegrityError("COHORT_NOT_AUTHORIZED")
    schedule = state["schedule"]
    maturity_day = date.fromisoformat(schedule[size + 8])
    if utc(now) < calendar.details(maturity_day)["close"]:
        raise ShadowIntegrityError("COHORT_NOT_MATURE")
    rows = []
    coverage_unknown = False
    for day in schedule[:size]:
        capture = state["sessions"].get(day)
        unknown = (not capture or not capture["capture_closed"] or capture["universe"] is None
                   or "UNIVERSE_CHANGED_WITHIN_WINDOW" in capture["diagnostics"])
        coverage_unknown |= unknown
        stats = export_session_statistics(state["ledger"], day)
        rows.append({**stats, "capture_coverage_unknown": unknown})
    result = {"schema": "R2D2_V2_COHORT_EXPORT_V1", "epoch": state["epoch"], "manifest_sha": state["manifest_sha"],
        "release_sha": state["release_sha"], "code_revision": state["code_revision"], "cohort_size": size,
        "calendar_version": state["calendar_version"], "maturity_session": maturity_day.isoformat(), "sessions": rows,
        "data_gate_unknown": coverage_unknown or bool(state["data_issues"]) or any(r["data_gate_unknown"] for r in rows),
        "terminal_veto": bool(state["ledger"]["terminal_reasons"]), "statistical_verdict": "NOT_COMPUTED"}
    return {**result, "sha256": digest(result)}
