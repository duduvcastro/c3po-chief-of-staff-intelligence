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
from .r2d2_v2_contract import CandidateInputs, DailyBar, SplitRecord, RISK_C75, evaluate_candidate, input_complete
from .r2d2_v2_earnings_package import (
    CONSENT_SCHEMA, EARNINGS_AMENDMENT_SHA, EARNINGS_CLOSED_MANIFEST_SHA,
    EXPORT_SCHEMA, RELEASE_SCHEMA, STATE_SCHEMA,
    implementation_contract_sha as current_contract_sha,
    implementation_package_sha as current_package_sha,
)
from .r2d2_v2_portfolio import PortfolioBatch, apply_events, export_session_statistics, new_portfolio, register_candidate
from .r2d2_v2_portfolio import earnings_public_sessions
from .r2d2_v2_sources import MANIFEST_SHA
from .r2d2_v2_store import ShadowIntegrityError, canonical, digest, utc, validate_epoch

SCHEMA = STATE_SCHEMA
AMENDMENT_SHA = "3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4"
SIGNED_MANIFEST_SHA = "eabbe18057b7e5823535dd61e93c5190b33f8c7ac80b9118229b7908f974f4d0"


def _hash(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _release_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate release key")
        result[key] = value
    return result


def _release_nonfinite(_token):
    raise ValueError("nonfinite release number")


@dataclass(frozen=True)
class Release:
    epoch: str
    mode: str
    first_session: date
    approved_at: datetime
    code_revision: str
    receipt_sha: str
    readiness_sha: str | None = None
    earnings_amendment_sha: str | None = None
    earnings_closed_manifest_sha: str | None = None
    implementation_contract_sha: str | None = None
    implementation_package_sha: str | None = None

    @classmethod
    def verify(cls, data: bytes, expected_sha: str, *, now: datetime, build_sha: str,
               calendar: ShadowCalendar) -> Release:
        if not _hash(expected_sha) or sha256(data).hexdigest() != expected_sha:
            raise ShadowIntegrityError("RELEASE_HASH_MISMATCH")
        try:
            body = json.loads(data, object_pairs_hook=_release_object, parse_constant=_release_nonfinite)
        except (ValueError, TypeError) as exc:
            raise ShadowIntegrityError("RELEASE_INVALID") from exc
        if (not isinstance(body, dict) or body.get("schema") != RELEASE_SCHEMA
                or body.get("manifest_sha") != SIGNED_MANIFEST_SHA
                or body.get("signed_manifest_sha") != SIGNED_MANIFEST_SHA
                or body.get("amendment_sha") != AMENDMENT_SHA
                or body.get("earnings_amendment_sha") != EARNINGS_AMENDMENT_SHA
                or body.get("earnings_closed_manifest_sha") != EARNINGS_CLOSED_MANIFEST_SHA):
            raise ShadowIntegrityError("RELEASE_POLICY_MISMATCH")
        contract_sha, package_sha = current_contract_sha(), current_package_sha()
        if (body.get("implementation_contract_sha") != contract_sha
                or body.get("implementation_package_sha") != package_sha):
            raise ShadowIntegrityError("RELEASE_IMPLEMENTATION_PACKAGE_MISMATCH")
        epoch, mode = body.get("epoch"), body.get("mode")
        if not isinstance(epoch, str):
            raise ShadowIntegrityError("EPOCH_INVALID")
        validate_epoch(epoch)
        if not isinstance(mode, str) or mode not in {"DIAGNOSTIC", "CERTIFIED"}:
            raise ShadowIntegrityError("RELEASE_MODE_INVALID")
        prefix = "R2D2-V2-DIAG-" if mode == "DIAGNOSTIC" else "R2D2-V2-SHADOW-"
        if not epoch.startswith(prefix):
            raise ShadowIntegrityError("RELEASE_NAMESPACE_MISMATCH")
        try:
            approved = utc(body["approved_at"])
            first = date.fromisoformat(body["first_session"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ShadowIntegrityError("RELEASE_CLOCK_INVALID") from exc
        if not approved <= utc(now) or not approved < calendar.details(first)["open"]:
            raise ShadowIntegrityError("RELEASE_MUST_PRECEDE_FIRST_SESSION")
        revision = body.get("code_revision")
        if (not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision)
                or revision != build_sha or not _hash(body.get("code_audit_sha"))
                or not isinstance(body.get("authorization_ref"), str) or not body["authorization_ref"].strip()):
            raise ShadowIntegrityError("RELEASE_CODE_OR_AUTHORIZATION_UNVERIFIED")
        # These are operator-pinned receipt records, not cryptographic proofs
        # of who signed. Missing/placeholder records never count as approval.
        bindings = {key: body.get(key) for key in (
            "earnings_amendment_sha", "earnings_closed_manifest_sha", "implementation_contract_sha",
            "implementation_package_sha", "code_revision", "code_audit_sha", "source_audit_sha", "readiness_sha")}
        consents = body.get("package_consents")
        if (any(not _hash(bindings[key]) for key in ("code_audit_sha", "source_audit_sha", "readiness_sha"))
                or not isinstance(consents, list) or len(consents) != 3
                or any(not isinstance(item, dict) for item in consents)
                or any(not isinstance(item.get("party"), str) for item in consents)
                or {item.get("party") for item in consents} != {"CODEX", "FABLE", "DUDU"}):
            raise ShadowIntegrityError("PACKAGE_CONSENTS_REQUIRED")
        consent_times = []
        for consent in consents:
            if (consent.get("schema") != CONSENT_SCHEMA or consent.get("approved") is not True
                    or any(consent.get(key) != value for key, value in bindings.items())
                    or not _hash(consent.get("receipt_sha"))
                    or not isinstance(consent.get("receipt_ref"), str) or not consent["receipt_ref"].strip()):
                raise ShadowIntegrityError("PACKAGE_CONSENT_BINDING_MISMATCH")
            try:
                consent_at = utc(consent["approved_at"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ShadowIntegrityError("PACKAGE_CONSENT_CLOCK_INVALID") from exc
            if consent_at > approved:
                raise ShadowIntegrityError("PACKAGE_CONSENT_AFTER_RELEASE")
            consent_times.append(consent_at)
        if mode == "CERTIFIED":
            approvals = ("calibration_sha", "calibration_acceptance_sha", "source_audit_sha",
                         "source_codex_signature_sha", "source_fable_signature_sha", "readiness_sha")
            if (body.get("calibration_status") != "ACCEPTED"
                    or body.get("calibration_protocol") != "C3PO-V2-CAL-3"
                    or any(not _hash(body.get(key)) for key in approvals)):
                raise ShadowIntegrityError("CALIBRATION_AND_SOURCES_REQUIRED")
            try:
                ready, published, deployed = (utc(body[key]) for key in
                    ("readiness_at", "readiness_publication_at", "deploy_completed_at"))
            except (KeyError, TypeError, ValueError) as exc:
                raise ShadowIntegrityError("READINESS_CLOCK_INVALID") from exc
            opening = calendar.details(first)["open"]
            if (not deployed <= ready <= published <= utc(now) or approved < ready
                    or published >= opening or first != calendar.first_open_after(ready)
                    or any(consented < ready for consented in consent_times)):
                raise ShadowIntegrityError("READINESS_FIRST_SESSION_MISMATCH")
        return cls(epoch, mode, first, approved, revision, expected_sha, body.get("readiness_sha"),
                   EARNINGS_AMENDMENT_SHA, EARNINGS_CLOSED_MANIFEST_SHA, contract_sha, package_sha)


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
    # The source validates this hash once over the envelope. Hashing all 550
    # instruments again for each individual name was quadratic in input bytes.
    envelope_sha = batch.get("envelope_sha256")
    if not isinstance(envelope_sha, str) or not _hash(envelope_sha):
        raise ShadowIntegrityError("SNAPSHOT_ENVELOPE_HASH_REQUIRED")
    hashes = {name: digest(item) for name, item in component.items() if name != "universe"}
    hashes["universe"] = envelope_sha
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
    issues = [item["code"] for item in row.get("diagnostics", [])
              if isinstance(item, dict) and isinstance(item.get("code"), str)]
    received = _dt(quote.get("received_at"))
    q_available = _dt(quote.get("available_at"))
    clocks = [_dt(quote.get(key)) for key in ("bid_source_at", "ask_source_at")]
    if (received is None or q_available is None
            or not received <= q_available <= now
            or any(at is None or not at <= received or now - at > timedelta(seconds=10) for at in clocks)
            or now - received > timedelta(seconds=10) or now - q_available > timedelta(seconds=10)):
        issues.append("QUOTE_RECEIPT_NOT_CAUSAL_OR_STALE")
    if daily.get("coverage_verified") is not True:
        issues.append("DAILY_COVERAGE_UNVERIFIED")
    return CandidateInputs(symbol=row.get("symbol", ""), market=row.get("market"),
        security_type=row.get("security_type") if row.get("classification_verified") is True else None,
        session_date=day, decision_at=now, bid=quote.get("bid"), ask=quote.get("ask"),
        bid_at=_dt(quote.get("bid_source_at")), ask_at=_dt(quote.get("ask_source_at")), risk_score=risk.get("value"),
        daily_bars=tuple(bars), previous_sessions=detail["previous_sessions"], horizon_sessions=detail["horizon_sessions"],
        horizon_close_at=detail["horizon_close"], splits=tuple(splits),
        split_coverage_verified=daily.get("split_coverage_verified") is True,
        daily_price_basis=daily.get("adjustment"), earnings_component=earnings,
        source_at=source_at, available_at=available,
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


class _LazyPortfolio:
    """Do not copy or hash the ledger on an observation with no ledger change."""
    def __init__(self, state):
        self.host = state
        self.batch = None

    def _get(self):
        if self.batch is None:
            self.batch = PortfolioBatch(self.host["ledger"])
            self.host["ledger"] = self.batch.state
        return self.batch

    def event(self, event):
        return self._get().event(event)

    def register(self, **kwargs):
        return self._get().register(**kwargs)

    def finish(self):
        return self.batch.finish() if self.batch is not None else self.host["ledger"]


def _compact_evaluation(evaluation: dict) -> dict:
    """The immutable journal retains the full evaluation and private inputs."""
    risk = evaluation.get("risk_score")
    stratum = (("ELIGIBLE" if risk <= RISK_C75 else "CONTROL")
        if isinstance(risk, (int, float)) and not isinstance(risk, bool) and 0 <= risk <= 100 else "UNASSIGNED")
    return {"status": evaluation.get("status"), "arm": evaluation.get("arm"),
            "risk_stratum": stratum,
            "reasons": evaluation.get("reasons", []), "evaluation_sha256": digest(evaluation)}


def _pending_material(name: str, row: dict, evaluation: dict, batch: dict, now: datetime) -> tuple[str, dict]:
    """Separate candidate evidence from polling/global-envelope changes.

    The full row and all economic results/reasons remain material. Only the
    collector's observation clocks and universe envelope hash/clocks are
    excluded; producer identity/version and calendar identity remain pinned.
    The omitted values are retained in the last-observation context. The last
    full pending input lives only in the current capture window's state and is
    archived on completion/close; intermediate changes never repeat 61 bars.
    """
    material = dict(evaluation)
    clocks = {key: material.pop(key) for key in ("decision_at", "opened_at") if key in material}
    provenance = material.get("provenance")
    observed_provenance = {}
    if isinstance(provenance, dict):
        material["provenance"] = dict(provenance)
        for component, omitted in (("universe", ("sha256", "source_at", "available_at")),
                                   ("calendar", ("source_at", "available_at"))):
            value = provenance.get(component)
            if isinstance(value, dict):
                observed_provenance[component] = dict(value)
                material["provenance"][component] = {key: item for key, item in value.items() if key not in omitted}
    source_sha = digest(row)
    fingerprint = digest({"schema": "V2_PENDING_MATERIAL_V1", "instrument": name,
                          "source_row_sha256": source_sha, "evaluation": material})
    context = {"observed_at": now.isoformat(), "batch_receipt": batch.get("envelope_sha256"),
               "source_row_sha256": source_sha, "evaluation_sha256": digest(evaluation),
               "evaluation_clocks": clocks, "evaluation_provenance": observed_provenance}
    return fingerprint, context


def _pending_tail(previous: dict) -> dict:
    """Archive the last private input once, before clearing transient state."""
    return {"first_pending_receipt": previous.get("first_receipt", previous.get("receipt")),
            "pending_receipt": previous.get("receipt"), "pending_material_sha256": previous.get("material_sha256"),
            "last_pending_observation": previous.get("latest_observation"),
            "last_pending_full_observation": previous.get("latest_full_observation")}


class ShadowCollector:
    def __init__(self, store, source, release: Release, *, calendar: ShadowCalendar | None = None, clock=None):
        self.store, self.source, self.release = store, source, release
        self.implementation_package_sha = current_package_sha()
        self.implementation_contract_sha = current_contract_sha()
        if (release.earnings_amendment_sha != EARNINGS_AMENDMENT_SHA
                or release.earnings_closed_manifest_sha != EARNINGS_CLOSED_MANIFEST_SHA
                or release.implementation_contract_sha != self.implementation_contract_sha
                or release.implementation_package_sha != self.implementation_package_sha):
            raise ShadowIntegrityError("COLLECTOR_IMPLEMENTATION_PACKAGE_MISMATCH")
        self.calendar = calendar or ShadowCalendar()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.schedule = self.calendar.sessions(release.first_session, 69)
        self.schedule_index = {day: index for index, day in enumerate(self.schedule)}
        self._causal_cache: dict[date, dict] = {}

    def _initial(self) -> dict:
        return {"schema": SCHEMA, "epoch": self.release.epoch, "manifest_sha": SIGNED_MANIFEST_SHA,
                "signed_manifest_sha": SIGNED_MANIFEST_SHA, "amendment_sha": AMENDMENT_SHA,
                "earnings_amendment_sha": EARNINGS_AMENDMENT_SHA,
                "earnings_closed_manifest_sha": EARNINGS_CLOSED_MANIFEST_SHA,
                "implementation_contract_sha": self.implementation_contract_sha,
                "implementation_package_sha": self.implementation_package_sha,
                "readiness_sha": self.release.readiness_sha,
                "mode": self.release.mode, "release_sha": self.release.receipt_sha,
                "code_revision": self.release.code_revision, "first_session": self.release.first_session.isoformat(),
                "calendar_version": self.calendar.version, "schedule": [d.isoformat() for d in self.schedule],
                "sessions": {}, "ledger": new_portfolio() if self.release.mode == "CERTIFIED" else None,
                "last_cycle_at": None, "last_session": None, "event_receipts": {}, "event_sequences": {},
                "data_issues": [], "active_data_issues": {}, "watch_episodes": {}, "instrument_episodes": {},
                "terminal_veto_history": [],
                "clock_receipts": [], "last_price_at": {}, "coverage_until": {}, "gap_episode_receipts": {}, "cycle_count": 0}

    def _capture_window(self, now):
        day = now.astimezone(NEW_YORK).date()
        if not self.calendar.is_session(day) or now < self.release.approved_at:
            return False
        if self.release.mode == "CERTIFIED" and not 0 <= self.schedule_index.get(day, -1) < 60:
            return False
        detail = self.calendar.details(day)
        return detail["capture_open"] <= now < detail["capture_close"]

    def cycle(self, now: datetime | None = None) -> dict:
        """Observe inputs only in their window; recheck the actual clock after I/O."""
        live = now is None
        now = utc(self.clock() if live else now)
        in_window = self._capture_window(now)
        day = now.astimezone(NEW_YORK).date()
        # Lists are checked before a snapshot. A late list schedules zero entries
        # and cannot cause even an incidental snapshot read for that session.
        causal = self._causal_cache.get(day) if in_window else None
        if in_window and causal is None:
            causal = self.source.causal_list(self.release.epoch, day, now, self.calendar)
        batch = self.source.snapshot(now) if in_window and causal is not None and causal.get("status") == "AVAILABLE" else None
        events = self.source.events(now) if self.release.mode == "CERTIFIED" else []
        event_diagnostics = getattr(self.source, "last_event_diagnostics", []) if self.release.mode == "CERTIFIED" else []
        result = self.store.atomic(self.release.epoch, self._initial(),
            lambda state: self._cycle(state, batch, events, event_diagnostics,
                                      utc(self.clock()) if live else now, causal=causal), now)
        if causal is not None and causal.get("status") == "AVAILABLE":
            # Only after atomic journal persistence discard the raw registry and
            # daily bytes. Restart re-verifies the file + external receipts;
            # subsequent polls consume this immutable commitment, never mtime.
            keep = {"status", "symbols", "list_sha256", "commitment_sha256", "registry_sha256",
                    "daily_contract_sha256", "built_at", "publication_at", "cutoff_at", "decision_at",
                    "n_cut", "counts", "coverage", "diagnostics", "envelope_sha256"}
            self._causal_cache = {day: {key: value for key, value in causal.items() if key in keep}}
        return result

    def _cycle(self, state, batch, events, event_diagnostics, now, *, causal=None):
        if (state.get("schema") != SCHEMA or state.get("manifest_sha") != SIGNED_MANIFEST_SHA
                or state.get("signed_manifest_sha") != SIGNED_MANIFEST_SHA
                or state.get("amendment_sha") != AMENDMENT_SHA
                or state.get("earnings_amendment_sha") != EARNINGS_AMENDMENT_SHA
                or state.get("earnings_closed_manifest_sha") != EARNINGS_CLOSED_MANIFEST_SHA
                or state.get("implementation_contract_sha") != self.implementation_contract_sha
                or state.get("implementation_package_sha") != self.implementation_package_sha
                or state.get("mode") != self.release.mode
                or state.get("release_sha") != self.release.receipt_sha
                or state.get("code_revision") != self.release.code_revision):
            raise ShadowIntegrityError("STATE_IMPLEMENTATION_PACKAGE_MISMATCH")
        if state["calendar_version"] != self.calendar.version:
            raise ShadowIntegrityError("CALENDAR_VERSION_CHANGED")
        if state["last_cycle_at"] and now < utc(state["last_cycle_at"]):
            raise ShadowIntegrityError("COLLECTOR_CLOCK_REVERSED")
        journals = []
        portfolio = _LazyPortfolio(state) if state["ledger"] is not None else None
        active_day = now.astimezone(NEW_YORK).date()
        if self.release.mode == "DIAGNOSTIC":
            # No retrospective zero sessions, maturity clocks, or shadow ledger
            # are created in DIAG. Its only sessions are actual input attempts.
            days = (active_day,) if self._capture_window(now) else ()
            if state["last_session"]:
                last = state["sessions"][state["last_session"]]
                last_day = date.fromisoformat(last["date"])
                if not last["capture_closed"] and last_day not in days:
                    days = (last_day,) + days
        else:
            # Revisit only the last processed day (possibly still open), then
            # elapsed new official days. Normal polling never walks the epoch.
            first = date.fromisoformat(state["last_session"]) if state["last_session"] else self.release.first_session
            days = self.calendar.between(first, active_day)
        events_processed = False
        touched = False
        for day in days:
            detail = self.calendar.details(day)
            if detail["open"] > now:
                break
            key = day.isoformat()
            index = self.schedule_index.get(day, 69)
            if key not in state["sessions"]:
                state["sessions"][key] = {"date": key, "entry_session": index < 60,
                    "calendar_sha": detail["sha256"], "capture_closed": False, "universe": None,
                    "universe_sha": None, "causal_list": None, "programmed_zero_reason": None,
                    "candidates": {}, "pending": {}, "diagnostics": [], "attempts": 0}
                touched = True
            session = state["sessions"][key]
            if state["ledger"] is not None:
                self._clock(state, journals, "SESSION_OPEN", key, detail["open"], now, portfolio=portfolio)
            if day == active_day:
                self._events(state, journals, events, event_diagnostics, now, key, portfolio=portfolio)
                events_processed = True
            if day == active_day and self._capture_window(now) and not session["capture_closed"]:
                self._capture(state, journals, session, batch or {}, now, portfolio=portfolio, causal=causal)
                touched = True
            if now >= detail["capture_close"] and not session["capture_closed"]:
                if index < 60 or self.release.mode == "DIAGNOSTIC":
                    self._close_capture(state, journals, session, now)
                else:
                    session["capture_closed"] = True
                    touched = True
            if state["ledger"] is not None and now >= detail["close"]:
                if day < active_day and "SESSION_CLOSE:" + key not in state["clock_receipts"]:
                    self._gap(state, journals, now, key, "COLLECTOR_MISSED_SESSION_CLOSE", portfolio=portfolio)
                self._clock(state, journals, "SESSION_CLOSE", key, detail["close"], now, portfolio=portfolio)
            state["last_session"] = key
        if not events_processed and state["ledger"] is not None and state["ledger"]["session"]:
            self._events(state, journals, events, event_diagnostics, now, state["ledger"]["session"], portfolio=portfolio)
        if portfolio is not None:
            state["ledger"] = portfolio.finish()
        if journals or touched:
            state["last_cycle_at"] = now.isoformat()
            state["cycle_count"] += 1
        response = public_summary(state)
        response["observed_at"] = now.isoformat()
        return state, journals, response

    @staticmethod
    def _apply(state, events, portfolio):
        before = set(state["ledger"]["terminal_reasons"])
        if portfolio is not None:
            result = [portfolio.event(event) for event in events]
        else:
            state["ledger"], result = apply_events(state["ledger"], events)
        if events:
            ShadowCollector._record_terminal(state, before, events[-1]["available_at"], events[-1]["session"])
        return result

    @staticmethod
    def _record_terminal(state, before, observed_at, session):
        for reason in sorted(set(state["ledger"]["terminal_reasons"]) - before):
            state["terminal_veto_history"].append({"reason": reason, "observed_at": observed_at, "session": session})

    def _clock(self, state, journals, kind, session, at, now, *, portfolio=None):
        key = kind + ":" + session
        if key in state["clock_receipts"]:
            return
        event = {"event_id": "clock:" + key, "type": kind, "session": session,
                 "at": at.isoformat(), "available_at": now.isoformat()}
        self._apply(state, [event], portfolio)
        state["clock_receipts"].append(key)
        journals.append({"journal_key": "clock:" + key, "type": "CLOCK", "event": event})

    def _gap(self, state, journals, now, session, reason, *, gap_at=None, instrument=None, portfolio=None):
        scope = instrument or "*"
        base_key = session + ":" + scope + ":" + reason
        active = state["active_data_issues"].get(base_key)
        # A second outage after demonstrated restoration is a new factual
        # occurrence; an old recovery receipt cannot exempt future failures.
        repeated = active is not None and bool(active["restored_instruments"])
        key = (base_key + ":" + now.isoformat()) if repeated else active["key"] if active else base_key
        known = key in state["gap_episode_receipts"]
        known_gap = utc(gap_at) if gap_at else now
        if not known:
            issue = {"key": key, "session": session, "instrument": scope, "reason": reason,
                     "at": known_gap.isoformat()}
            state["data_issues"].append(issue)
            state["active_data_issues"][base_key] = {**issue, "restored_instruments": []}
        affected = [r for r in state["ledger"]["research"].values()
                    if (instrument is None or r["instrument_key"] == instrument)
                    and (r["status"] == "OPEN" or utc(r["opened_at"]) <= known_gap <
                         utc(r["exit_at"] or (r["exit_interval"] or [None, now.isoformat()])[1]))]
        prior = state["gap_episode_receipts"].setdefault(key, [])
        new_episodes = sorted(r["episode_key"] for r in affected if r["episode_key"] not in prior)
        if known and not new_episodes:
            return
        prior.extend(new_episodes)
        batch_key = digest([key, new_episodes])
        gap_events = [{"event_id": "gap:" + digest([batch_key, name]), "type": "DATA_GAP", "session": session,
                   "instrument_key": name, "reason": reason, "at": known_gap.isoformat(), "available_at": now.isoformat()}
                  for name in sorted({r["instrument_key"] for r in affected if r["episode_key"] in new_episodes})]
        self._apply(state, gap_events, portfolio)
        journals.append({"journal_key": "gap:" + batch_key, "type": "DATA_GAP", "session": session,
                         "instrument": scope, "reason": reason, "events": gap_events})

    def _restore(self, state, journals, event, now, session):
        # A fresh complete regular bar proves a new observable interval. It
        # restores admission for this name; it never repairs an old episode.
        if (event["type"] != "BAR" or event.get("regular") is not True
                or event.get("coverage_complete") is not True
                or utc(event["at"]).astimezone(NEW_YORK).date().isoformat() != session
                or not timedelta(0) <= now - utc(event["end_at"]) <= timedelta(seconds=90)):
            return
        name = event["instrument_key"]
        for key, issue in state["active_data_issues"].items():
            if (issue["session"] == session and issue["instrument"] in ("*", name)
                    and name not in issue["restored_instruments"] and utc(event["at"]) >= utc(issue["at"])):
                issue["restored_instruments"].append(name)
                journals.append({"journal_key": "recovery:" + digest([key, name, event["event_id"]]),
                    "type": "ADMISSION_OBSERVABILITY_RESTORED", "session": session,
                    "instrument": name, "gap_key": key, "bar_event_id": event["event_id"],
                    "available_at": now.isoformat()})

    @staticmethod
    def _admission_block(state, session, name):
        # A past-session outage remains attached to its affected episodes. A
        # newly verified D−1 list + complete fresh snapshot starts a new session
        # observation; no epoch-global flag can veto all subsequent entries.
        return "COLLECTION_DATA_GATE_BLOCKED" if any(
            issue["session"] == session and issue["instrument"] in ("*", name)
            and name not in issue["restored_instruments"] for issue in state["active_data_issues"].values()) else None

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
                    "BAR": 3, "TRADE": 3, "MARK": 4, "EARNINGS": 2, "QUOTE": 4, "DATA_GAP": 1,
                    "EARNINGS_OBSERVATION_FAILED": 1}
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
                    "manifest_sha", "amendment_sha", "self_sha256", "envelope_sha256", "envelope_available_at"}}
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
            elif event["type"] in {"EARNINGS", "EARNINGS_OBSERVATION_FAILED"}:
                round_day = _date(event.get("round_session"))
                received = _dt(event.get("round_received_at"))
                if (round_day is None or received is None or not self.calendar.is_session(round_day)
                        or received <= self.calendar.details(round_day)["close"]):
                    raise ShadowIntegrityError("EARNINGS_ROUND_SESSION_INVALID")
            if event is not None:
                name = event["instrument_key"]
                episodes = [state["ledger"]["research"][key] for key in state["instrument_episodes"].get(name, [])]
                episodes = [record for record in episodes if record["status"] == "OPEN"
                    or (record["exit_at"] or (record["exit_interval"] or [None, None])[1]) is not None
                    and utc(record["exit_at"] or record["exit_interval"][1]) >= utc(event["at"])]
                if event["type"] == "DATA_GAP":
                    self._gap(state, journals, now, session, "PRODUCER_DATA_GAP", gap_at=utc(event["at"]),
                              instrument=name, portfolio=portfolio)
                if episodes and event["type"] in {"TRADE", "BAR"} and event.get("regular") is True:
                    at = utc(event["at"])
                    opening = self.calendar.details(at.astimezone(NEW_YORK).date())["open"]
                    first_entry = min(utc(r["opened_at"]) for r in episodes)
                    coverage = max(utc(state["coverage_until"].get(name, first_entry)), opening, first_entry)
                    # A first print after a missing interval cannot close the
                    # position and thereby erase the preceding data failure.
                    if at - coverage > timedelta(seconds=90):
                        self._gap(state, journals, now, session, "LIVE_EVIDENCE_STALE", gap_at=coverage,
                                  instrument=name, portfolio=portfolio)
                    if event["type"] == "BAR" and event.get("coverage_complete") is True:
                        if at > coverage:
                            self._gap(state, journals, now, session, "BAR_COVERAGE_GAP", gap_at=coverage,
                                      instrument=name, portfolio=portfolio)
                        elif utc(event["end_at"]) > coverage:
                            state["coverage_until"][name] = event["end_at"]
                result = self._apply(state, [event], portfolio)
                if event["type"] == "BAR" and event.get("regular") is True and event.get("coverage_complete") is True:
                    old = state["coverage_until"].get(name)
                    if old is None or utc(event["end_at"]) > utc(old):
                        state["coverage_until"][name] = event["end_at"]
                self._restore(state, journals, event, now, session)
                if event["type"] in {"BAR", "TRADE", "QUOTE", "MARK"}:
                    state["last_price_at"][event["instrument_key"]] = event.get("end_at", event["at"])
            else:
                result = [{"status": "DATA_UNOBSERVABLE"}]
            state["event_receipts"][item["event_id"]] = item["envelope_sha256"]
            journals.append({"journal_key": "event:" + item["event_id"], "type": "SOURCE_EVENT",
                             "source": item, "applied_event": event, "result": result})
        # Missing cycles or stale evidence are data failures, not zero returns.
        for episode in tuple(state["watch_episodes"]):
            record = state["ledger"]["research"][episode]
            last = max(utc(state["coverage_until"].get(record["instrument_key"], record["opened_at"])),
                       utc(record["opened_at"]))
            terminal = record["exit_at"] or (record["exit_interval"] or [None, None])[1]
            if (terminal and last >= utc(terminal)) or record["category"] == "unobservable":
                state["watch_episodes"].pop(episode)
                continue
            day = now.astimezone(NEW_YORK).date()
            if self.calendar.is_session(day):
                detail = self.calendar.details(day)
                if min(now, detail["close"]) - max(last, detail["open"]) > timedelta(seconds=90):
                    self._gap(state, journals, now, session, "LIVE_EVIDENCE_STALE", gap_at=max(last, detail["open"]),
                              instrument=record["instrument_key"], portfolio=portfolio)

    def _capture(self, state, journals, session, batch, now, *, portfolio=None, causal=None):
        session["attempts"] += 1
        causal = causal or {}
        codes = [_object(item).get("code") for item in causal.get("diagnostics", [])]
        if "CAUSAL_LIST_LATE" in codes:
            session.update(universe=[], universe_sha=digest([]), capture_closed=True,
                           programmed_zero_reason="CAUSAL_LIST_LATE")
            _diagnostic(state, journals, session, "CAUSAL_LIST_LATE", now)
            journals.append({"journal_key": "capture-close:" + session["date"], "type": "PROGRAMMED_ZERO",
                "session": session["date"], "reason": "CAUSAL_LIST_LATE", "source": causal})
            return
        if causal.get("status") != "AVAILABLE":
            _diagnostic(state, journals, session, "CAUSAL_LIST_UNVERIFIED", now)
            return
        symbols = causal.get("symbols")
        if (not isinstance(symbols, list) or any(not isinstance(name, str) for name in symbols)
                or len(symbols) != len(set(symbols)) or len(symbols) > 550 or causal.get("n_cut") != 550
                or not _hash(causal.get("list_sha256")) or not _hash(causal.get("commitment_sha256"))):
            raise ShadowIntegrityError("CAUSAL_LIST_INVALID")
        names = ["US:" + name for name in symbols]
        if session["universe"] is None:
            session["universe"], session["universe_sha"] = names, causal["list_sha256"]
            session["causal_list"] = {key: causal.get(key) for key in ("list_sha256", "commitment_sha256",
                "registry_sha256", "daily_contract_sha256", "built_at", "publication_at", "cutoff_at", "n_cut", "counts", "coverage")}
            journals.append({"journal_key": "universe:" + session["date"], "type": "CAUSAL_UNIVERSE",
                             "session": session["date"], "causal_list": causal})
        elif (names != session["universe"] or causal["list_sha256"] != session["universe_sha"]
                or causal["commitment_sha256"] != session["causal_list"]["commitment_sha256"]):
            _diagnostic(state, journals, session, "CAUSAL_LIST_CHANGED_WITHIN_SESSION", now)
            return
        universe = _object(batch.get("universe"))
        if batch.get("status") != "AVAILABLE" or universe.get("coverage_verified") is not True:
            _diagnostic(state, journals, session, "UNIVERSE_COVERAGE_UNVERIFIED", now)
            return
        all_rows = universe.get("instruments", [])
        if not isinstance(all_rows, list):
            raise ShadowIntegrityError("UNIVERSE_INVALID")
        observed_names = [_instrument(row) for row in all_rows]
        if len(observed_names) != len(set(observed_names)):
            raise ShadowIntegrityError("UNIVERSE_DUPLICATE")
        selected = set(names)
        rows = [row for row in all_rows if _instrument(row) in selected]
        extra_count = len(all_rows) - len(rows)
        if extra_count and "SNAPSHOT_OUTSIDE_CAUSAL_LIST" not in session["diagnostics"]:
            _diagnostic(state, journals, session, "SNAPSHOT_OUTSIDE_CAUSAL_LIST", now)
            journals.append({"journal_key": "outside-list:" + session["date"], "type": "CAUSAL_EXCLUSION_COUNT",
                             "session": session["date"], "count": extra_count})
        prepared = []
        for row in rows:
            name = _instrument(row)
            if name in session["candidates"]:
                continue
            inputs = candidate_inputs(row, batch, now, self.calendar)
            evaluation = evaluate_candidate(inputs).to_dict()
            observation = {"evaluation": evaluation, "source": row, "batch_receipt": batch.get("envelope_sha256")}
            if input_complete(inputs):
                available = max(t for key, t in inputs.available_at.items() if t is not None and key != "calendar")
                tie_hash = sha256(f"{self.release.epoch}|{session['date']}|{row['symbol']}".encode()).hexdigest()
                prepared.append((available, tie_hash, name, observation))
            else:
                compact = _compact_evaluation(evaluation)
                material_sha, latest = _pending_material(name, row, evaluation, batch, now)
                previous = session["pending"].get(name, {})
                revision = previous.get("revision", 0)
                receipt = previous.get("receipt")
                if previous.get("material_sha256") != material_sha:
                    revision += 1
                    # A return to an earlier material state is another observed
                    # transition, not a conflicting reuse of its journal key.
                    receipt = digest([name, material_sha, revision])
                    record = {"journal_key": "pending:" + session["date"] + ":" + receipt,
                        "type": "CANDIDATE_PENDING_CHANGE" if previous else "CANDIDATE_PENDING",
                        "instrument_key": name, "material_sha256": material_sha,
                        "revision": revision, "observed_at": now.isoformat()}
                    if previous:
                        # Quote changes can arrive each second while earnings
                        # remain pending. Preserve their evidence commitments
                        # without reserializing daily history into the journal.
                        record.update(first_pending_receipt=previous.get("first_receipt"),
                                      previous_pending_receipt=previous.get("receipt"),
                                      evaluation=compact, observation_context=latest)
                    else:
                        record["observation"] = observation
                    journals.append(record)
                session["pending"][name] = {**compact, "receipt": receipt, "material_sha256": material_sha,
                    "revision": revision, "first_receipt": previous.get("first_receipt", receipt),
                    "latest_observation": latest, "latest_full_observation": observation}
        for _, episode, name, observation in sorted(prepared, key=lambda item: item[:3]):
            previous = session["pending"].pop(name, {})
            evaluation = observation["evaluation"]
            session["candidates"][name] = _compact_evaluation(evaluation)
            record = {"journal_key": "candidate:" + session["date"] + ":" + digest(name), "type": "CANDIDATE",
                      "episode_key": episode, "instrument_key": name, "observation": observation}
            if previous:
                record.update(_pending_tail(previous))
            if state["ledger"] is not None and evaluation["arm"] is not None:
                before_terminal = set(state["ledger"]["terminal_reasons"])
                kwargs: dict[str, Any] = dict(episode_key=episode,
                    instrument_key=name, session=session["date"], opened_at=now.isoformat(),
                    maturity_at=evaluation["maturity_at"], geometry=evaluation["geometry"], arm=evaluation["arm"],
                    admission_block_reason=self._admission_block(state, session["date"], name))
                if portfolio is not None:
                    research, admission = portfolio.register(**kwargs)
                else:
                    state["ledger"], research, admission = register_candidate(state["ledger"], **kwargs)
                record.update(research=research, admission=admission)
                self._record_terminal(state, before_terminal, now.isoformat(), session["date"])
                state["coverage_until"].setdefault(name, now.isoformat())
                state["watch_episodes"][episode] = name
                state["instrument_episodes"].setdefault(name, []).append(episode)
            journals.append(record)

    def _close_capture(self, state, journals, session, now):
        if session["universe"] is None:
            _diagnostic(state, journals, session, "CAPTURE_WINDOW_WITHOUT_VERIFIED_UNIVERSE", now)
        for name in session["universe"] or []:
            if name in session["candidates"]:
                continue
            previous = session["pending"].get(name, {})
            evaluation = {"status": "DATA_INELIGIBLE", "arm": None,
                "reasons": list(dict.fromkeys(previous.get("reasons", []) + ["CAPTURE_WINDOW_INCOMPLETE"]))}
            session["candidates"][name] = _compact_evaluation(evaluation)
            journals.append({"journal_key": "candidate:" + session["date"] + ":" + digest(name),
                "type": "CANDIDATE_INCOMPLETE", "instrument_key": name,
                **_pending_tail(previous), "evaluation": evaluation})
        session["pending"] = {}
        session["capture_closed"] = True
        journals.append({"journal_key": "capture-close:" + session["date"], "type": "CAPTURE_CLOSED",
                         "session": session["date"], "closed_observed_at": now.isoformat(),
                         "candidate_count": len(session["candidates"]), "diagnostics": session["diagnostics"]})


def public_summary(state: dict) -> dict:
    """No symbols, private identifiers, input values, or statistical verdicts."""
    sessions = []
    observed = earnings_public_sessions(state["ledger"]) if state["ledger"] is not None else {}
    earnings_codes = ("EARNINGS_WITHIN_HORIZON", "EARNINGS_EXPECTED_WITHIN_HORIZON",
        "EARNINGS_NOT_TRACKED", "EARNINGS_LAST_REPORT_UNKNOWN", "EARNINGS_EVIDENCE_INVALID",
        "EARNINGS_SOURCE_UNAVAILABLE", "EARNINGS_DETECTED_AFTER_ENTRY", "EARNINGS_OBSERVATION_FAILED")
    current = state.get("last_session") or max(state["sessions"], default=None)
    current_names = (state["sessions"].get(current, {}).get("universe") or [])
    active_issues = [issue for issue in state["active_data_issues"].values()
        if issue["session"] == current and (
            issue["instrument"] not in issue["restored_instruments"] if issue["instrument"] != "*"
            else not current_names or not set(current_names).issubset(issue["restored_instruments"]))]
    for session in state["sessions"].values():
        reasons = Counter(reason for c in session["candidates"].values() for reason in c.get("reasons", []))
        earnings_counts = {arm: dict.fromkeys(earnings_codes, 0) for arm in ("ELIGIBLE", "CONTROL", "UNASSIGNED")}
        for candidate in session["candidates"].values():
            arm = candidate.get("risk_stratum", "UNASSIGNED")
            for reason in set(candidate.get("reasons", [])) & set(earnings_codes):
                earnings_counts[arm][reason] += 1
        detection = observed.get(session["date"], {})
        for arm, counts in detection.get("counts", {}).items():
            earnings_counts[arm].update(counts)
        sessions.append({"session_date": session["date"], "entry_session": session["entry_session"],
            "capture_closed": session["capture_closed"], "universe_count": len(session["universe"]) if session["universe"] is not None else None,
            "snapshot_attempts": session["attempts"], "frozen_count": len(session["candidates"]),
            "reason_counts": dict(reasons), "diagnostics": session["diagnostics"],
            "earnings_counts_by_arm": earnings_counts,
            "earnings_count_basis": "VALID_RISK_R1_STRATUM_BEFORE_DATA_EXCLUSION_OR_ADMITTED_EPISODE_ARM",
            "earnings_exit_diagnostics_by_arm": detection.get("exits"),
            "programmed_zero_reason": session.get("programmed_zero_reason")})
    return {"schema": "R2D2_V2_COLLECTOR_STATUS_V2", "epoch": state["epoch"], "manifest_sha": state["manifest_sha"],
            "amendment_sha": state["amendment_sha"],
            "earnings_amendment_sha": state["earnings_amendment_sha"],
            "earnings_closed_manifest_sha": state["earnings_closed_manifest_sha"],
            "implementation_contract_sha": state["implementation_contract_sha"],
            "implementation_package_sha": state["implementation_package_sha"],
            "mode": state["mode"], "last_cycle_at": state["last_cycle_at"], "sessions": sessions,
            "earnings_observation_dates": [{"date": day, **summary}
                for day, summary in sorted(observed.items())],
            "cohort_clock_started": state["mode"] == "CERTIFIED" and bool(state["sessions"]),
            "data_gate_unknown": bool(active_issues), "data_gate_scope": "CURRENT_SESSION_OBSERVATION",
            "data_issue_count": len(state["data_issues"]),
            "active_data_issue_count": len(active_issues),
            "certification_computed": False, "production_orders": False}


def export_cohort(state: dict, size: int, *, now: datetime, calendar: ShadowCalendar) -> dict:
    """Sufficient statistics for the signed estimator, only after maturity.

This does not compute a bootstrap or authorize a GO. Every programmed session,
including zero days, remains in order. Diagnostic epochs cannot be promoted.
"""
    if (state.get("schema") != SCHEMA or state.get("mode") != "CERTIFIED"
            or not str(state.get("epoch", "")).startswith("R2D2-V2-SHADOW-")
            or size not in (40, 60) or state.get("manifest_sha") != SIGNED_MANIFEST_SHA
            or state.get("signed_manifest_sha") != SIGNED_MANIFEST_SHA
            or state.get("amendment_sha") != AMENDMENT_SHA
            or state.get("earnings_amendment_sha") != EARNINGS_AMENDMENT_SHA
            or state.get("earnings_closed_manifest_sha") != EARNINGS_CLOSED_MANIFEST_SHA
            or state.get("implementation_contract_sha") != current_contract_sha()
            or not _hash(state.get("implementation_package_sha"))):
        raise ShadowIntegrityError("COHORT_NOT_AUTHORIZED")
    schedule = state["schedule"]
    maturity_day = date.fromisoformat(schedule[size + 8])
    if utc(now) < calendar.details(maturity_day)["close"]:
        raise ShadowIntegrityError("COHORT_NOT_MATURE")
    rows = []
    coverage_unknown = False
    def veto_through(cutoff):
        history = state.get("terminal_veto_history", [])
        known = {item["reason"] for item in history if _dt(item.get("observed_at")) is not None}
        # An untimed old reason is unknown and blocking; never infer it happened
        # after a reading. New V2 transitions record their actual first receipt.
        return (bool(set(state["ledger"]["terminal_reasons"]) - known)
                or any(_dt(item.get("observed_at")) is None or utc(item["observed_at"]) <= cutoff for item in history))
    for index, day in enumerate(schedule[:size], 1):
        capture = state["sessions"].get(day)
        unknown = (not capture or not capture["capture_closed"] or capture["universe"] is None
                   or "CAUSAL_LIST_CHANGED_WITHIN_SESSION" in capture["diagnostics"])
        coverage_unknown |= unknown
        stats = export_session_statistics(state["ledger"], day)
        # Session rows have their own fixed N10 observation horizon, so later
        # epoch-global vetoes cannot mutate the frozen forty-session prefix.
        stats["terminal_veto"] = veto_through(calendar.details(date.fromisoformat(day))["horizon_close"])
        rows.append({**stats, "capture_coverage_unknown": unknown, "programmed_session_index": index})
    completed = sum(calendar.details(date.fromisoformat(day))["close"] <= utc(now) for day in schedule)
    result = {"schema": EXPORT_SCHEMA, "epoch": state["epoch"], "manifest_sha": state["manifest_sha"],
        "amendment_sha": state["amendment_sha"], "signed_manifest_sha": state["signed_manifest_sha"],
        "earnings_amendment_sha": state["earnings_amendment_sha"],
        "earnings_closed_manifest_sha": state["earnings_closed_manifest_sha"],
        "implementation_contract_sha": state["implementation_contract_sha"],
        "implementation_package_sha": state["implementation_package_sha"],
        "readiness_sha": state["readiness_sha"], "programmed_sessions": schedule, "sessions_completed": completed,
        "maturity_session_index": size + 9, "certification_target": "V2_FILTER_CERTIFIED_R1",
        "certificate_scope": "R1_DISCRIMINATION_ONLY",
        "release_sha": state["release_sha"], "code_revision": state["code_revision"], "cohort_size": size,
        "calendar_version": state["calendar_version"], "maturity_session": maturity_day.isoformat(), "sessions": rows,
        "data_gate_unknown": coverage_unknown or any(r["data_gate_unknown"] for r in rows),
        "terminal_veto": veto_through(calendar.details(maturity_day)["close"]),
        "observation_cutoff_at": calendar.details(maturity_day)["close"].isoformat(),
        "statistical_verdict": "NOT_COMPUTED"}
    return {**result, "sha256": digest(result)}
