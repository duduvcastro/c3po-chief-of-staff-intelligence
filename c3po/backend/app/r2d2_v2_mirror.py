"""R2D2 V2 — paper mirror adapter (EMENDA 2 rev 2, closed six-hands; OFF by default).

Replicates decisions ALREADY RECORDED in the V2 virtual ledger (the shadow
generator's portfolio records) as paper orders in a dedicated R2D2 experiment
(`R2D2-V2-MIRROR-001`). The adapter decides nothing on its own. EMENDA 2 rev 2
and the Codex audit of #387 (I1–I5, C1–C5) fix these behaviours:

- one COMMAND per ledger decision with a durable identity (mirror epoch, shadow
  epoch, episode key, decision) and the hash of its payload, registered in the
  mirror's own memory BEFORE the paper effect; the effect is CLAIMED atomically
  (BUY_PENDING → BUY_EXECUTING, one claimant), the paper trade carries the
  command id, an uncertain outcome is resolved by READING the paper trades,
  repetition returns the receipt, a payload that differs from the registered or
  executed one BLOCKS (also after OPEN and on recovery); cycles of one mirror
  epoch are serialized by a lock, so two processes never run the same command;
- a portfolio admission (kind PORTFOLIO, status OPEN, opened at or after the
  published initial cursor) becomes ONE paper BUY of the ledger quantity `q`
  (eight-decimal nominal precision; more decimals are rejected, never rounded);
  research episodes and controls are never mirrored; a BUY still pending when
  the virtual position already closed becomes SKIPPED; a BUY not yet executed
  obeys every veto in force at execution time;
- a recorded exit becomes ONE paper SELL of the quantity actually mirrored for
  that episode; until executed the position is EXIT_PENDING (latency recorded,
  new BUYs blocked); a missing quote never erases the position nor invents a
  fill; the exit obligation survives any conflict or disposition (a BLOCKED or
  AWAITING_DISPOSITION row with a position keeps blocking BUYs and still sells
  when the ledger records the exit);
- inherited vetoes: ledger terminal reasons, the V2 collection data gate of the
  current session (active, unrestored data issues), exits-only orders, the
  mirror experiment's own `entries_paused`, any pending exit, and any cap
  breached by marking (per US name across exchanges, 48% gross US aggregated,
  95% exposure, 5% cash) block new BUYs; nothing is liquidated;
- fills use a REGULAR bid/ask quote with causal clocks (source ≤ available ≤
  now, at most 10 s old, never in the future), midpoint reference and the
  simulator's US friction; the receipt records the quote clocks, the decision
  instant and the FACTUAL fill instant returned by the paper engine;
- memory is scoped by (mirror epoch, shadow epoch, experiment);
- the release receipt binds the initial cursor to a session open and requires
  publication before that cursor;
- everything published carries MIRROR_NOT_CERTIFIED.

Production wiring: the ledger is read through the shadow store of the
generator (PR #383, `r2d2_v2_store.PostgresShadowStore.read`); the paper
engine is the existing `R2D2Repository` (paper-only, no broker); nothing of
the V1 selection/sizing/stop/watcher/learning runs on the mirror experiment.
The worker refuses to run without `C3PO_R2D2_V2_MIRROR_ENABLED=true`, a pinned
release receipt (`R2D2_V2_MIRROR_RELEASE_V1`) and a CERTIFIED shadow epoch.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time as clock
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from .database import Database
from .r2d2 import R2D2Repository, _paper_buy_execution, _paper_exit_execution

logger = logging.getLogger(__name__)

MIRROR_ID = "R2D2-V2-MIRROR"
MIRROR_VERSION = "v3"
LABEL = "MIRROR_NOT_CERTIFIED"
STATEMENT = "réplica descritiva da carteira virtual; não é evidência"
RELEASE_SCHEMA = "R2D2_V2_MIRROR_RELEASE_V1"
DEFAULT_EXPERIMENT_CODE = "R2D2-V2-MIRROR-001"
STARTING_CAPITAL_USD = 1_000_000.0
SHADOW_EPOCH_PREFIX = "R2D2-V2-SHADOW-"
MARKETS = ("NASDAQ", "NYSE")
NEW_YORK = ZoneInfo("America/New_York")
OFFICIAL_OPEN = time(9, 30)
CAPS = {"per_name_percent": 6.0, "gross_us_percent": 48.0, "exposure_percent": 95.0, "cash_percent": 5.0}
QUOTE_MAX_AGE_SECONDS = 10.0
QUANTITY_DECIMALS = 8
METHODOLOGY_VERSION = "r2d2-v2-mirror-v3"
EXIT_CAUSES = ("STOP", "TARGET", "EVENT", "TIME")
STATUSES = ("SKIPPED", "BUY_PENDING", "BUY_EXECUTING", "OPEN", "EXIT_PENDING", "SELL_EXECUTING", "CLOSED", "AWAITING_DISPOSITION", "BLOCKED")
EXIT_OBLIGATION_STATUSES = ("EXIT_PENDING", "SELL_EXECUTING", "AWAITING_DISPOSITION")


class MirrorInputError(ValueError):
    """Controlled message only."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False, default=str).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


# ---------------------------------------------------------------- ledger view (read-only, confirmed facts only)

def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise MirrorInputError("LEDGER_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise MirrorInputError("LEDGER_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None:
        raise MirrorInputError("LEDGER_TIMESTAMP_NAIVE")
    return parsed.astimezone(timezone.utc)


def _number(value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
        raise MirrorInputError("LEDGER_NUMBER_INVALID")
    return float(value)


def quantity_precision_ok(quantity: float) -> bool:
    """The simulator's nominal precision is eight decimals; more is never rounded away silently."""
    exponent = Decimal(repr(quantity)).normalize().as_tuple().exponent
    return isinstance(exponent, int) and exponent >= -QUANTITY_DECIMALS


@dataclass(frozen=True)
class LedgerRecord:
    episode_key: str
    instrument_key: str
    symbol: str
    kind: str
    status: str
    quantity: float
    entry_price: float
    stop: float
    target: float
    opened_at: datetime
    maturity_at: datetime | None
    exit_cause: str | None
    exit_price: float | None
    exit_at: datetime | None
    exit_available_at: datetime | None
    exit_interval: tuple[str, str] | None

    def buy_payload(self) -> dict[str, Any]:
        return {"decision": "BUY", "episode_key": self.episode_key, "instrument_key": self.instrument_key, "quantity": self.quantity,
                "entry_price": self.entry_price, "stop": self.stop, "target": self.target, "opened_at": self.opened_at.isoformat()}

    def sell_payload(self) -> dict[str, Any]:
        return {"decision": "SELL", "episode_key": self.episode_key, "instrument_key": self.instrument_key, "exit_cause": self.exit_cause,
                "exit_price": self.exit_price, "exit_at": self.exit_at.isoformat() if self.exit_at else None,
                "exit_available_at": self.exit_available_at.isoformat() if self.exit_available_at else None,
                "exit_interval": list(self.exit_interval) if self.exit_interval else None}


@dataclass(frozen=True)
class LedgerView:
    epoch: str
    version: int
    state_sha: str
    session: str | None
    terminal_reasons: tuple[str, ...]
    data_gate_blocked: bool
    records: tuple[LedgerRecord, ...]

    @property
    def vetoed(self) -> bool:
        return bool(self.terminal_reasons) or self.data_gate_blocked

    def by_key(self) -> dict[str, LedgerRecord]:
        return {record.episode_key: record for record in self.records}


def _record(key: str, raw: Mapping[str, Any]) -> LedgerRecord:
    instrument = raw.get("instrument_key")
    if not isinstance(instrument, str) or not instrument.startswith("US:") or len(instrument) < 4:
        raise MirrorInputError("LEDGER_INSTRUMENT_INVALID")
    status = raw.get("status")
    if status not in ("OPEN", "CLOSED"):
        raise MirrorInputError("LEDGER_STATUS_INVALID")
    geometry = raw.get("geometry")
    if not isinstance(geometry, dict):
        raise MirrorInputError("LEDGER_GEOMETRY_INVALID")
    closed = status == "CLOSED"
    exit_cause = raw.get("exit_cause")
    if closed and exit_cause not in EXIT_CAUSES:
        raise MirrorInputError("LEDGER_EXIT_CAUSE_INVALID")
    interval = raw.get("exit_interval")
    parsed_interval: tuple[str, str] | None = None
    if closed and isinstance(interval, list) and len(interval) == 2 and all(isinstance(item, str) for item in interval):
        parsed_interval = (interval[0], interval[1])
    return LedgerRecord(
        episode_key=key, instrument_key=instrument, symbol=instrument[3:], kind=str(raw.get("kind")), status=status,
        quantity=_number(raw.get("quantity"), positive=True), entry_price=_number(geometry.get("P"), positive=True),
        stop=_number(geometry.get("S"), positive=True), target=_number(geometry.get("T"), positive=True),
        opened_at=_time(raw.get("opened_at")),
        maturity_at=_time(raw.get("maturity_at")) if raw.get("maturity_at") is not None else None,
        exit_cause=str(exit_cause) if closed else None,
        exit_price=_number(raw.get("exit_price"), positive=True) if closed else None,
        exit_at=_time(raw.get("exit_at")) if closed and raw.get("exit_at") is not None else None,
        exit_available_at=_time(raw.get("exit_available_at")) if closed and raw.get("exit_available_at") is not None else None,
        exit_interval=parsed_interval,
    )


def data_gate_blocked(state: Mapping[str, Any], session: str | None) -> bool:
    """The collector's gate (#383 `_admission_block`): an active, unrestored data issue of the current session, any instrument."""
    issues = state.get("active_data_issues")
    if issues is None:
        return False
    if not isinstance(issues, dict):
        raise MirrorInputError("SHADOW_DATA_ISSUES_INVALID")
    for issue in issues.values():
        if not isinstance(issue, dict):
            raise MirrorInputError("SHADOW_DATA_ISSUES_INVALID")
        if issue.get("session") == session and (issue.get("instrument") == "*" or issue.get("instrument") not in (issue.get("restored_instruments") or [])):
            return True
    return False


def read_ledger(row: Mapping[str, Any]) -> LedgerView:
    """The stored shadow epoch row (`state`, `state_sha`, `version`) -> a read-only view of its portfolio records and vetoes."""
    state = row.get("state")
    if not isinstance(state, dict):
        raise MirrorInputError("SHADOW_STATE_MISSING")
    epoch = state.get("epoch")
    if not isinstance(epoch, str) or not epoch.startswith(SHADOW_EPOCH_PREFIX):
        raise MirrorInputError("SHADOW_EPOCH_NOT_CERTIFIED")
    if state.get("mode") != "CERTIFIED":
        raise MirrorInputError("SHADOW_MODE_NOT_CERTIFIED")
    ledger = state.get("ledger")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("portfolio"), dict):
        raise MirrorInputError("SHADOW_LEDGER_MISSING")
    version = row.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise MirrorInputError("SHADOW_VERSION_INVALID")
    state_sha = row.get("state_sha")
    if not isinstance(state_sha, str) or len(state_sha) != 64:
        raise MirrorInputError("SHADOW_STATE_SHA_INVALID")
    reasons = ledger.get("terminal_reasons")
    if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
        raise MirrorInputError("SHADOW_TERMINAL_REASONS_INVALID")
    session = ledger.get("session")
    session_key = session if isinstance(session, str) else None
    records = tuple(_record(str(key), value) for key, value in sorted(ledger["portfolio"].items()) if isinstance(value, dict))
    return LedgerView(epoch=epoch, version=version, state_sha=state_sha, session=session_key, terminal_reasons=tuple(reasons),
                      data_gate_blocked=data_gate_blocked(state, session_key), records=records)


# ---------------------------------------------------------------- command identity

def command_id(mirror_epoch: str, shadow_epoch: str, episode_key: str, decision: str) -> str:
    return hashlib.sha256(f"{mirror_epoch}|{shadow_epoch}|{episode_key}|{decision}".encode()).hexdigest()


# ---------------------------------------------------------------- mirror memory (own table; the paper ledger stays the engine's)

MIRROR_FIELDS = ("mirror_epoch", "epoch", "episode_key", "symbol", "market", "experiment_id", "status", "reason",
                 "buy_command_id", "buy_command_sha", "sell_command_id", "sell_command_sha", "command_registered_at",
                 "claim_token", "claimed_at",
                 "buy_trade_id", "buy_at", "buy_quantity", "buy_fill_price", "ledger_entry_price", "ledger_quantity", "ledger_opened_at",
                 "sell_trade_id", "sell_at", "sell_fill_price", "ledger_exit_price", "ledger_exit_at", "ledger_exit_cause",
                 "divergence", "created_at", "updated_at")


def has_position(row: Mapping[str, Any]) -> bool:
    return bool(row.get("buy_trade_id")) and not row.get("sell_trade_id")


class MirrorRepository:
    """Per-episode command memory scoped by (mirror epoch, shadow epoch, experiment). Claims are atomic; cycles are serialized."""

    def __init__(self, database: Database) -> None:
        self.database = database
        if not hasattr(database, "_r2d2_v2_mirror_memory"):
            database._r2d2_v2_mirror_memory = {}  # type: ignore[attr-defined]
        if not hasattr(database, "_r2d2_v2_mirror_lock"):
            database._r2d2_v2_mirror_lock = threading.Lock()  # type: ignore[attr-defined]

    @property
    def memory(self) -> dict[tuple[str, str, str], dict[str, Any]]:
        return self.database._r2d2_v2_mirror_memory  # type: ignore[attr-defined]

    @contextmanager
    def cycle_lock(self, mirror_epoch: str) -> Iterator[bool]:
        """One cycle at a time per mirror epoch: a session-level advisory lock in PostgreSQL, a process lock in memory mode."""
        if not self.database.database_url:
            lock: threading.Lock = self.database._r2d2_v2_mirror_lock  # type: ignore[attr-defined]
            acquired = lock.acquire(blocking=False)
            try:
                yield acquired
            finally:
                if acquired:
                    lock.release()
            return
        with self.database.connection() as connection:
            acquired = bool(connection.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (f"{MIRROR_ID}:cycle:{mirror_epoch}",)).fetchone()[0])
            try:
                yield acquired
            finally:
                if acquired:
                    connection.execute("SELECT pg_advisory_unlock(hashtext(%s))", (f"{MIRROR_ID}:cycle:{mirror_epoch}",))
                connection.commit()

    def load(self, mirror_epoch: str, epoch: str, experiment_id: str) -> dict[str, dict[str, Any]]:
        if not self.database.database_url:
            return {key[2]: dict(value) for key, value in self.memory.items()
                    if key[0] == mirror_epoch and key[1] == epoch and value.get("experiment_id") == experiment_id}
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT {', '.join(MIRROR_FIELDS)} FROM r2d2_v2_mirror_episodes WHERE mirror_epoch=%s AND epoch=%s AND experiment_id=%s",
                (mirror_epoch, epoch, experiment_id)).fetchall()
        return {row[2]: dict(zip(MIRROR_FIELDS, row)) for row in rows}

    def upsert(self, row: Mapping[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        record = {field: row.get(field) for field in MIRROR_FIELDS}
        if record["status"] not in STATUSES:
            raise MirrorInputError("MIRROR_STATUS_INVALID")
        for key in ("mirror_epoch", "epoch", "episode_key", "experiment_id"):
            if not record.get(key):
                raise MirrorInputError("MIRROR_ROW_SCOPE_MISSING")
        record["updated_at"] = now
        if not self.database.database_url:
            key = (str(record["mirror_epoch"]), str(record["epoch"]), str(record["episode_key"]))
            previous = self.memory.get(key)
            record["created_at"] = previous["created_at"] if previous else now
            self.memory[key] = record
            return dict(record)
        record["created_at"] = record.get("created_at") or now
        columns = ", ".join(MIRROR_FIELDS)
        placeholders = ", ".join("%s::jsonb" if field == "divergence" else "%s" for field in MIRROR_FIELDS)
        updates = ", ".join(f"{field}=EXCLUDED.{field}" for field in MIRROR_FIELDS if field not in ("mirror_epoch", "epoch", "episode_key", "created_at"))
        values = [json.dumps(record[field], default=str) if field == "divergence" else record[field] for field in MIRROR_FIELDS]
        with self.database.connection() as connection:
            connection.execute(
                f"INSERT INTO r2d2_v2_mirror_episodes ({columns}) VALUES ({placeholders}) "
                f"ON CONFLICT (mirror_epoch, epoch, episode_key) DO UPDATE SET {updates}", values)
            connection.commit()
        return dict(record)

    def claim(self, row: Mapping[str, Any], *, from_status: str, to_status: str, now: datetime) -> dict[str, Any] | None:
        """Atomically move a command from `from_status` to `to_status`; only one claimant ever gets the row."""
        token = str(uuid4())
        key = (str(row["mirror_epoch"]), str(row["epoch"]), str(row["episode_key"]))
        if not self.database.database_url:
            lock: threading.Lock = self.database._r2d2_v2_mirror_lock  # type: ignore[attr-defined]
            with lock if not lock.locked() else _noop():
                current = self.memory.get(key)
                if current is None or current.get("status") != from_status:
                    return None
                current.update(status=to_status, claim_token=token, claimed_at=now, updated_at=now)
                return dict(current)
        with self.database.connection() as connection:
            claimed = connection.execute(
                """UPDATE r2d2_v2_mirror_episodes SET status=%s, claim_token=%s, claimed_at=%s, updated_at=%s
                   WHERE mirror_epoch=%s AND epoch=%s AND episode_key=%s AND status=%s RETURNING """ + ", ".join(MIRROR_FIELDS),
                (to_status, token, now, now, *key, from_status)).fetchone()
            connection.commit()
        return dict(zip(MIRROR_FIELDS, claimed)) if claimed else None

    def trade_for_command(self, repo: R2D2Repository, experiment_id: str, command: str) -> dict[str, Any] | None:
        """The paper effect of a command, if it happened: resolution by READING, never by a new effect."""
        if not self.database.database_url:
            for trade in repo.memory["trades"]:
                snapshot = trade.get("decision_snapshot") or {}
                if trade.get("experiment_id") == experiment_id and snapshot.get("command_id") == command:
                    return {**trade, "command_sha": snapshot.get("command_sha")}
            return None
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT id::text, side, quantity, fill_price_local, executed_at, quote_as_of, decision_snapshot->>'command_sha' FROM r2d2_trades
                   WHERE experiment_id=%s AND decision_snapshot->>'command_id'=%s ORDER BY executed_at LIMIT 1""",
                (experiment_id, command)).fetchone()
        if row is None:
            return None
        return {"id": row[0], "side": row[1], "quantity": float(row[2]), "fill_price_local": float(row[3]), "executed_at": row[4],
                "quote_as_of": row[5], "command_sha": row[6]}


@contextmanager
def _noop() -> Iterator[None]:
    yield None


# ---------------------------------------------------------------- experiment (dedicated paper account, NAV 1M)

def mirror_mandate(epoch: str, mirror_epoch: str) -> dict[str, Any]:
    return {
        "mode": "paper_only", "real_broker_execution": False, "mirror": MIRROR_ID, "mirror_version": MIRROR_VERSION, "mirror_epoch": mirror_epoch,
        "label": LABEL, "statement": STATEMENT, "mirrored_epoch": epoch, "markets": list(MARKETS),
        "own_decisions": False, "source": "V2 virtual ledger (shadow generator) — admissions and exits already recorded",
        "caps": dict(CAPS), "quote_policy": {"regular_bid_ask": True, "max_age_seconds": QUOTE_MAX_AGE_SECONDS, "reference": "midpoint",
                                             "causal_clocks": "source_at <= available_at <= decision", "friction_us": {"slippage_rate": 0.0010, "fee_rate": 0.0004}},
        "quantity_policy": f"ledger q preserved, {QUANTITY_DECIMALS} decimals, no resizing; caps/cash including friction reject permanently",
        "no_minimum_position": True, "research_episodes_mirrored": False, "controls_mirrored": False,
        "is_evidence": False, "certification_input": False,
    }


def ensure_mirror_experiment(repo: R2D2Repository, *, code: str, epoch: str, mirror_epoch: str,
                             starting_capital: float = STARTING_CAPITAL_USD, now: datetime | None = None) -> dict[str, Any]:
    """Create-or-read the mirror's own paper experiment. Never the V1 initialization routine; never re-runs a closed one."""
    if not code.startswith(MIRROR_ID):
        raise MirrorInputError("MIRROR_EXPERIMENT_CODE_INVALID")
    clock_now = now or datetime.now(timezone.utc)
    mandate = mirror_mandate(epoch, mirror_epoch)
    payload = {"id": str(uuid4()), "code": code, "status": "running", "base_currency": "USD",
               "starting_capital": starting_capital, "cash_balance": starting_capital, "start_date": clock_now.date(),
               "checkpoint_date": clock_now.date(), "methodology_version": METHODOLOGY_VERSION, "mandate": mandate,
               "entries_paused": False, "entries_paused_at": None, "entries_pause_operator": None, "entries_pause_reason": None,
               "policy_epoch": None, "policy_epoch_started_at": None, "entry_score_adapter_version": None,
               "entry_score_adapter_enabled_at": None, "created_at": clock_now, "updated_at": clock_now}
    if not repo.database.database_url:
        current = repo.memory["experiment"]
        if current is not None and current.get("code") != code:
            raise MirrorInputError("MEMORY_MODE_HOLDS_ANOTHER_EXPERIMENT")
        if current is None:
            repo.memory["experiment"] = payload
        return dict(repo.memory["experiment"])
    with repo.database.connection() as connection:
        row = connection.execute(
            """INSERT INTO r2d2_experiments
                   (id, code, status, starting_capital, cash_balance, start_date, end_date, checkpoint_date,
                    is_continuous, methodology_version, mandate)
               VALUES (%s, %s, 'running', %s, %s, %s, %s, %s, TRUE, %s, %s::jsonb)
               ON CONFLICT (code) DO UPDATE SET mandate = EXCLUDED.mandate, updated_at = now()
               RETURNING id::text, code, status, base_currency, starting_capital, cash_balance,
                         start_date, checkpoint_date, methodology_version, mandate,
                         entries_paused, entries_paused_at, entries_pause_operator,
                         entries_pause_reason, policy_epoch, policy_epoch_started_at,
                         entry_score_adapter_version, entry_score_adapter_enabled_at,
                         created_at, updated_at""",
            (payload["id"], code, starting_capital, starting_capital, clock_now.date(), clock_now.date(), clock_now.date(),
             METHODOLOGY_VERSION, json.dumps(mandate))).fetchone()
        connection.commit()
    experiment = R2D2Repository._experiment(row)
    if experiment["status"] == "completed":
        raise MirrorInputError("MIRROR_EXPERIMENT_CLOSED")
    return experiment


# ---------------------------------------------------------------- book and caps

def _position_value(row: Mapping[str, Any]) -> float:
    return float(row["quantity"]) * float(row["last_price_local"]) * float(row["fx_to_usd"] or 1.0)


def _book(repo: R2D2Repository, experiment: Mapping[str, Any]) -> tuple[list[dict[str, Any]], float, float]:
    positions = repo.positions(str(experiment["id"]))
    exposure = sum(_position_value(row) for row in positions)
    cash = float(experiment["cash_balance"])
    return positions, cash, cash + exposure


def _name_values(positions: list[dict[str, Any]]) -> dict[str, float]:
    """Value per US name, aggregated across exchanges (the economic identity is US:symbol)."""
    values: dict[str, float] = {}
    for row in positions:
        if row["market"] in MARKETS:
            values[row["symbol"]] = values.get(row["symbol"], 0.0) + _position_value(row)
    return values


def marked_excess(positions: list[dict[str, Any]], cash: float, nav: float) -> str | None:
    """A cap already breached by marking blocks every new BUY (EMENDA 2 rev 2 §3.4); nothing is liquidated."""
    if nav <= 0:
        return "CAP_NAV_NOT_POSITIVE"
    names = _name_values(positions)
    if any(value > nav * CAPS["per_name_percent"] / 100 for value in names.values()):
        return "MARKED_EXCESS_PER_NAME_6PCT"
    if sum(names.values()) > nav * CAPS["gross_us_percent"] / 100:
        return "MARKED_EXCESS_GROSS_US_48PCT"
    if sum(_position_value(row) for row in positions) > nav * CAPS["exposure_percent"] / 100:
        return "MARKED_EXCESS_EXPOSURE_95PCT"
    if cash < nav * CAPS["cash_percent"] / 100:
        return "MARKED_EXCESS_CASH_5PCT"
    return None


def _cap_breach(positions: list[dict[str, Any]], cash: float, nav: float, *, symbol: str, cost_usd: float) -> str | None:
    if nav <= 0:
        return "CAP_NAV_NOT_POSITIVE"
    names = _name_values(positions)
    if names.get(symbol, 0.0) + cost_usd > nav * CAPS["per_name_percent"] / 100:
        return "CAP_PER_NAME_6PCT"
    if sum(names.values()) + cost_usd > nav * CAPS["gross_us_percent"] / 100:
        return "CAP_GROSS_US_48PCT"
    if sum(_position_value(row) for row in positions) + cost_usd > nav * CAPS["exposure_percent"] / 100:
        return "CAP_EXPOSURE_95PCT"
    if cash - cost_usd < nav * CAPS["cash_percent"] / 100:
        return "CAP_CASH_5PCT"
    return None


# ---------------------------------------------------------------- planning (pure)

@dataclass(frozen=True)
class Action:
    kind: str  # BUY | SELL | SKIP | DEFER | DISPOSITION | BLOCK
    record: LedgerRecord | None
    reason: str
    episode_key: str


def plan(ledger: LedgerView, mirrored: Mapping[str, Mapping[str, Any]], *, activated_at: datetime, exits_only: bool = False,
         entries_paused: bool = False, marked: str | None = None) -> list[Action]:
    """Which commands are due now. SKIP/BLOCK are persisted (never revisited); DEFER is retried next cycle."""
    records = ledger.by_key()
    blockers: list[str] = []
    if exits_only:
        blockers.append("EXITS_ONLY_BY_DESK_ORDER")
    if entries_paused:
        blockers.append("MIRROR_ENTRIES_PAUSED")
    if ledger.terminal_reasons:
        blockers.append("LEDGER_VETO:" + ",".join(ledger.terminal_reasons))
    if ledger.data_gate_blocked:
        blockers.append("COLLECTION_DATA_GATE_BLOCKED")
    if marked:
        blockers.append(marked)
    obligations = [key for key, row in mirrored.items()
                   if row.get("status") in EXIT_OBLIGATION_STATUSES
                   or (row.get("status") in ("OPEN", "BLOCKED") and key in records and records[key].status == "CLOSED")
                   or (row.get("status") == "BLOCKED" and has_position(row))
                   or (row.get("status") in ("OPEN", "BUY_PENDING", "BUY_EXECUTING", "BLOCKED") and key not in records and (has_position(row) or row.get("status") != "OPEN"))]
    if obligations:
        blockers.append("EXIT_OBLIGATION_BLOCKS_BUYS")
    veto = ";".join(blockers) or None
    actions: list[Action] = []
    for key, row in mirrored.items():  # mirrored positions or pending commands whose episode vanished from the ledger: the desk decides
        if row.get("status") in ("OPEN", "EXIT_PENDING", "BUY_PENDING", "BUY_EXECUTING", "SELL_EXECUTING", "BLOCKED") and key not in records:
            actions.append(Action("DISPOSITION", None, "EPISODE_ABSENT_FROM_LEDGER", key))
    for record in ledger.records:
        if record.kind != "PORTFOLIO":
            continue
        row = mirrored.get(record.episode_key)
        status = row.get("status") if row else None
        buy_sha = digest(record.buy_payload())
        if row is None:
            if record.status == "CLOSED":
                actions.append(Action("SKIP", record, "CLOSED_BEFORE_MIRROR", record.episode_key))
            elif record.opened_at < activated_at:
                actions.append(Action("SKIP", record, "OPENED_BEFORE_INITIAL_CURSOR", record.episode_key))
            elif not quantity_precision_ok(record.quantity):
                actions.append(Action("SKIP", record, "QUANTITY_PRECISION_INVALID", record.episode_key))
            elif veto is not None:
                actions.append(Action("DEFER", record, veto, record.episode_key))
            else:
                actions.append(Action("BUY", record, "LEDGER_ADMISSION_RECORDED", record.episode_key))
        elif status in ("BUY_PENDING", "BUY_EXECUTING"):
            if row.get("buy_command_sha") not in (None, buy_sha):
                actions.append(Action("BLOCK", record, "COMMAND_PAYLOAD_CONFLICT", record.episode_key))
            elif record.status == "CLOSED":
                actions.append(Action("SKIP", record, "CLOSED_BEFORE_MIRROR_EXECUTION", record.episode_key))
            elif veto is not None:
                actions.append(Action("DEFER", record, veto, record.episode_key))  # every veto in force applies before an unexecuted BUY
            else:
                actions.append(Action("BUY", record, "COMMAND_REGISTERED_EFFECT_PENDING", record.episode_key))
        elif status == "OPEN":
            if row.get("buy_command_sha") not in (None, buy_sha):
                actions.append(Action("BLOCK", record, "COMMAND_PAYLOAD_CONFLICT", record.episode_key))
            elif record.status == "CLOSED":
                actions.append(Action("SELL", record, f"LEDGER_EXIT_RECORDED:{record.exit_cause}", record.episode_key))
        elif status == "BLOCKED":
            if record.status == "CLOSED" and has_position(row):
                actions.append(Action("SELL", record, "EXIT_OBLIGATION_AFTER_BLOCK", record.episode_key))
        elif status in ("EXIT_PENDING", "SELL_EXECUTING"):
            if row.get("sell_command_sha") not in (None, digest(record.sell_payload())):
                actions.append(Action("DISPOSITION", record, "EXIT_COMMAND_PAYLOAD_CONFLICT", record.episode_key))
            else:
                actions.append(Action("SELL", record, "EXIT_PENDING_RETRY", record.episode_key))
    order = {"DISPOSITION": 0, "BLOCK": 1, "SKIP": 2, "SELL": 3, "BUY": 4, "DEFER": 5}
    return sorted(actions, key=lambda action: (order[action.kind], action.episode_key))  # exits before entries, deterministic


# ---------------------------------------------------------------- quotes

@dataclass(frozen=True)
class MirrorQuote:
    bid: float
    ask: float
    source_at: datetime
    available_at: datetime
    status: str

    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2


class QuoteSource(Protocol):
    def quote(self, market: str, symbol: str, now: datetime) -> MirrorQuote | None: ...


MarketResolver = Callable[[str], str | None]


def quote_valid(quote: MirrorQuote | None, now: datetime, max_age_seconds: float = QUOTE_MAX_AGE_SECONDS) -> bool:
    """A regular, live bid/ask with causal clocks: source_at <= available_at <= now, at most `max_age_seconds` old, never future."""
    if quote is None or quote.status != "live":
        return False
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (quote.bid, quote.ask)) or not 0 < quote.bid <= quote.ask:
        return False
    if not isinstance(quote.source_at, datetime) or not isinstance(quote.available_at, datetime):
        return False
    if quote.source_at.tzinfo is None or quote.available_at.tzinfo is None:
        return False
    source, available = quote.source_at.astimezone(timezone.utc), quote.available_at.astimezone(timezone.utc)
    if not source <= available <= now:
        return False
    return (now - source).total_seconds() <= max_age_seconds


# ---------------------------------------------------------------- execution (paper simulator)

def _divergence(record: LedgerRecord, *, side: str, quote: MirrorQuote | None, fill_price: float, quantity: float, decided_at: datetime,
                executed_at: datetime) -> dict[str, Any]:
    reference_price = record.entry_price if side == "BUY" else float(record.exit_price or 0.0)
    reference_at = record.opened_at if side == "BUY" else (record.exit_available_at or record.exit_at or record.opened_at)
    return {"side": side, "ledger_price": reference_price, "mirror_fill_price": fill_price,
            "price_diff_bps": round((fill_price / reference_price - 1) * 10_000, 3) if reference_price > 0 else None,
            "ledger_quantity": record.quantity, "mirror_quantity": quantity,
            "ledger_at": reference_at.isoformat(), "ledger_exit_interval": list(record.exit_interval) if record.exit_interval else None,
            "quote_source_at": quote.source_at.isoformat() if quote else None,
            "quote_available_at": quote.available_at.isoformat() if quote else None,
            "decided_at": decided_at.isoformat(), "mirror_at": executed_at.isoformat(),
            "latency_seconds": round((executed_at - reference_at).total_seconds(), 3), "reconciled": False}


def _executed_at(trade: Mapping[str, Any], fallback: datetime) -> datetime:
    value = trade.get("executed_at")
    return value.astimezone(timezone.utc) if isinstance(value, datetime) and value.tzinfo else fallback


def reconcile(*, ledger: LedgerView, mirror_epoch: str, repo: R2D2Repository, mirror: MirrorRepository, experiment: Mapping[str, Any],
              now: datetime) -> dict[str, int]:
    """Resolve claimed/pending commands by READING the paper trades (crash between effect and receipt); never a new effect.

    The effect is adopted only if its payload hash equals the registered one AND the decision the ledger presents now."""
    counts = {"buy_adopted": 0, "sell_adopted": 0, "conflicts": 0, "released": 0}
    records = ledger.by_key()
    for key, row in mirror.load(mirror_epoch, ledger.epoch, str(experiment["id"])).items():
        status = row.get("status")
        if status not in ("BUY_PENDING", "BUY_EXECUTING", "EXIT_PENDING", "SELL_EXECUTING"):
            continue
        side = "BUY" if status in ("BUY_PENDING", "BUY_EXECUTING") else "SELL"
        command = row.get("buy_command_id") if side == "BUY" else row.get("sell_command_id")
        registered_sha = row.get("buy_command_sha") if side == "BUY" else row.get("sell_command_sha")
        record = records.get(key)
        current_sha = (digest(record.buy_payload()) if side == "BUY" else digest(record.sell_payload())) if record else None
        trade = mirror.trade_for_command(repo, str(experiment["id"]), str(command)) if command else None
        if trade is None:
            if status in ("BUY_EXECUTING", "SELL_EXECUTING"):  # a claim without effect: the claimant died before the paper engine committed
                mirror.upsert({**row, "status": "BUY_PENDING" if side == "BUY" else "EXIT_PENDING", "claim_token": None, "claimed_at": None,
                               "reason": "CLAIM_RELEASED_NO_EFFECT"})
                counts["released"] += 1
            continue
        if trade.get("command_sha") != registered_sha or (record is not None and current_sha != registered_sha):
            mirror.upsert({**row, "status": "BLOCKED", "reason": "COMMAND_PAYLOAD_CONFLICT", "claim_token": None,
                           **({"buy_trade_id": trade["id"], "buy_at": _executed_at(trade, now), "buy_quantity": float(trade["quantity"]),
                               "buy_fill_price": float(trade["fill_price_local"])} if side == "BUY" and not row.get("buy_trade_id") else {})})
            counts["conflicts"] += 1
            continue
        executed = _executed_at(trade, now)
        divergence = dict(row.get("divergence") or {})
        if side == "BUY" and trade.get("side") == "BUY":
            if record is not None:
                divergence["buy"] = _divergence(record, side="BUY", quote=None, fill_price=float(trade["fill_price_local"]), quantity=float(trade["quantity"]),
                                                decided_at=executed, executed_at=executed)
            mirror.upsert({**row, "status": "OPEN", "reason": "EFFECT_RECOVERED_BY_READING", "claim_token": None, "buy_trade_id": trade["id"],
                           "buy_at": executed, "buy_quantity": float(trade["quantity"]), "buy_fill_price": float(trade["fill_price_local"]), "divergence": divergence})
            counts["buy_adopted"] += 1
        elif side == "SELL" and trade.get("side") == "SELL":
            if record is not None:
                divergence["sell"] = _divergence(record, side="SELL", quote=None, fill_price=float(trade["fill_price_local"]), quantity=float(trade["quantity"]),
                                                 decided_at=executed, executed_at=executed)
            mirror.upsert({**row, "status": "CLOSED", "reason": "EFFECT_RECOVERED_BY_READING", "claim_token": None, "sell_trade_id": trade["id"],
                           "sell_at": executed, "sell_fill_price": float(trade["fill_price_local"]), "divergence": divergence})
            counts["sell_adopted"] += 1
    return counts


def execute(actions: Iterable[Action], *, ledger: LedgerView, mirror_epoch: str, repo: R2D2Repository, mirror: MirrorRepository,
            experiment: Mapping[str, Any], cycle_id: str, quotes: QuoteSource, resolve_market: MarketResolver, now: datetime,
            fx: float = 1.0) -> dict[str, Any]:
    """Emit the paper orders for the planned commands: register → claim → effect → receipt. Divergences recorded, never reconciled."""
    summary: dict[str, Any] = {"buys": 0, "sells": 0, "skipped": 0, "deferred": 0, "dispositions": 0, "blocked": 0, "reasons": {}}

    def count(reason: str) -> None:
        summary["reasons"][reason] = summary["reasons"].get(reason, 0) + 1

    experiment_id = str(experiment["id"])
    mirrored = mirror.load(mirror_epoch, ledger.epoch, experiment_id)

    def base_row(record: LedgerRecord, market: str | None) -> dict[str, Any]:
        return {"mirror_epoch": mirror_epoch, "epoch": ledger.epoch, "episode_key": record.episode_key, "symbol": record.symbol, "market": market,
                "experiment_id": experiment_id, "ledger_entry_price": record.entry_price, "ledger_quantity": record.quantity, "ledger_opened_at": record.opened_at}

    live_experiment = repo.experiment(str(experiment["code"])) or dict(experiment)
    for action in actions:
        previous = mirrored.get(action.episode_key, {})
        if action.kind == "DISPOSITION":
            if previous.get("status") != "AWAITING_DISPOSITION":
                base = base_row(action.record, previous.get("market")) if action.record else {}
                mirror.upsert({**previous, **base, "status": "AWAITING_DISPOSITION", "reason": action.reason, "claim_token": None})
            summary["dispositions"] += 1
            count(action.reason)
            continue
        record = action.record
        assert record is not None
        if action.kind == "DEFER":
            summary["deferred"] += 1
            count(action.reason)
            continue
        if action.kind == "BLOCK":
            mirror.upsert({**previous, **base_row(record, previous.get("market")), "status": "BLOCKED", "reason": action.reason, "claim_token": None})
            summary["blocked"] += 1
            count(action.reason)
            continue
        if action.kind == "SKIP":
            mirror.upsert({**previous, **base_row(record, previous.get("market")), "status": "SKIPPED", "reason": action.reason, "claim_token": None})
            summary["skipped"] += 1
            count(action.reason)
            continue
        market = previous.get("market") or resolve_market(record.symbol)
        if market not in MARKETS:
            mirror.upsert({**previous, **base_row(record, None), "status": "SKIPPED", "reason": "MARKET_UNRESOLVED"})
            summary["skipped"] += 1
            count("MARKET_UNRESOLVED")
            continue
        assert market is not None
        positions, cash, nav = _book(repo, live_experiment)
        existing = next((row for row in positions if row["market"] == market and row["symbol"] == record.symbol), None)
        if action.kind == "BUY":
            command = command_id(mirror_epoch, ledger.epoch, record.episode_key, "BUY")
            payload_sha = digest(record.buy_payload())
            if existing is not None and previous.get("status") not in ("BUY_PENDING", "BUY_EXECUTING"):
                mirror.upsert({**previous, **base_row(record, market), "status": "AWAITING_DISPOSITION", "reason": "POSITION_WITHOUT_MIRROR_COMMAND",
                               "buy_command_id": command, "buy_command_sha": payload_sha})
                summary["dispositions"] += 1
                count("POSITION_WITHOUT_MIRROR_COMMAND")
                continue
            quote = quotes.quote(market, record.symbol, now)
            if not quote_valid(quote, now):
                summary["deferred"] += 1
                count("QUOTE_NOT_VALID")
                continue
            assert quote is not None
            fill = _paper_buy_execution(market=market, price=quote.midpoint, quantity=record.quantity, fx=fx)
            cost = fill["gross_value_usd"] + fill["fees_usd"]
            breach = _cap_breach(positions, cash, nav, symbol=record.symbol, cost_usd=cost)
            if breach is not None:
                mirror.upsert({**previous, **base_row(record, market), "status": "SKIPPED", "reason": breach, "buy_command_id": command, "buy_command_sha": payload_sha})
                summary["skipped"] += 1
                count(breach)
                continue
            # 1. register the command; 2. claim it (one claimant); 3. paper effect carrying the command id; 4. receipt.
            registered = mirror.upsert({**previous, **base_row(record, market), "status": "BUY_PENDING", "reason": action.reason,
                                        "buy_command_id": command, "buy_command_sha": payload_sha,
                                        "command_registered_at": previous.get("command_registered_at") or now})
            claimed = mirror.claim(registered, from_status="BUY_PENDING", to_status="BUY_EXECUTING", now=now)
            if claimed is None:
                summary["deferred"] += 1
                count("COMMAND_CLAIMED_ELSEWHERE")
                continue
            candidate = {"market": market, "symbol": record.symbol, "name": record.symbol, "currency": "USD",
                         "stop_price": record.stop, "price": quote.midpoint, "quote_as_of": quote.source_at, "risk_score": None}
            decision = {"mirror": MIRROR_ID, "mirror_version": MIRROR_VERSION, "mirror_epoch": mirror_epoch, "label": LABEL, "statement": STATEMENT,
                        "command_id": command, "command_sha": payload_sha, "claim_token": claimed["claim_token"], "epoch": ledger.epoch,
                        "ledger_version": ledger.version, "ledger_state_sha": ledger.state_sha, "episode_key": record.episode_key,
                        "ledger": record.buy_payload(), "ledger_maturity_at": record.maturity_at.isoformat() if record.maturity_at else None,
                        "quote": {"bid": quote.bid, "ask": quote.ask, "source_at": quote.source_at.isoformat(), "available_at": quote.available_at.isoformat(),
                                  "reference": "midpoint"},
                        "decided_at": now.isoformat(), "paper_only": True, "own_decision": False}
            try:
                trade = repo.execute_trade(dict(live_experiment), cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=record.quantity,
                                           signal_price=quote.midpoint, fill_price=fill["fill_price"], fx=fx, fees=fill["fees_usd"],
                                           slippage=fill["slippage_usd"], reason=f"{LABEL}: mirror of V2 ledger admission (command {command[:12]})",
                                           decision=decision, quote_as_of=quote.source_at)
            except ValueError as exc:
                mirror.upsert({**claimed, "status": "SKIPPED", "reason": f"PAPER_ORDER_REJECTED:{exc}", "claim_token": None})
                summary["skipped"] += 1
                count("PAPER_ORDER_REJECTED")
                continue
            executed = _executed_at(trade, now)
            repo.save_decision(experiment_id, cycle_id, candidate, "BUY", [MIRROR_ID, LABEL, command], trade["id"])
            live_experiment = repo.experiment(str(experiment["code"])) or live_experiment
            mirror.upsert({**claimed, "status": "OPEN", "reason": action.reason, "claim_token": None, "buy_trade_id": trade["id"], "buy_at": executed,
                           "buy_quantity": record.quantity, "buy_fill_price": fill["fill_price"],
                           "divergence": {"buy": _divergence(record, side="BUY", quote=quote, fill_price=fill["fill_price"], quantity=record.quantity,
                                                             decided_at=now, executed_at=executed)}})
            summary["buys"] += 1
            count("BUY")
        elif action.kind == "SELL":
            command = command_id(mirror_epoch, ledger.epoch, record.episode_key, "SELL")
            payload_sha = digest(record.sell_payload())
            pending = {**previous, **base_row(record, market), "status": "EXIT_PENDING", "reason": action.reason, "sell_command_id": command,
                       "sell_command_sha": payload_sha, "claim_token": None,
                       "command_registered_at": previous.get("command_registered_at") if previous.get("status") in ("EXIT_PENDING", "SELL_EXECUTING") else now,
                       "ledger_exit_price": record.exit_price, "ledger_exit_at": record.exit_at, "ledger_exit_cause": record.exit_cause}
            if previous.get("status") != "EXIT_PENDING":
                pending = mirror.upsert(pending)  # the exit obligation is durable before any quote is looked at
            if existing is None:
                mirror.upsert({**pending, "status": "CLOSED", "reason": "POSITION_ABSENT_AT_EXIT"})
                count("POSITION_ABSENT_AT_EXIT")
                continue
            mirrored_quantity = float(previous.get("buy_quantity") or 0.0)
            quantity = min(float(existing["quantity"]), mirrored_quantity) if mirrored_quantity > 0 else float(existing["quantity"])
            quote = quotes.quote(market, record.symbol, now)
            if not quote_valid(quote, now):
                summary["deferred"] += 1
                count("QUOTE_NOT_VALID_EXIT_PENDING")
                continue
            assert quote is not None
            claimed = mirror.claim(pending, from_status="EXIT_PENDING", to_status="SELL_EXECUTING", now=now)
            if claimed is None:
                summary["deferred"] += 1
                count("COMMAND_CLAIMED_ELSEWHERE")
                continue
            fill = _paper_exit_execution(market=market, price=quote.midpoint, quantity=quantity, fx=fx)
            candidate = {"market": market, "symbol": record.symbol, "name": existing.get("name") or record.symbol, "currency": "USD",
                         "stop_price": record.stop, "price": quote.midpoint, "quote_as_of": quote.source_at, "risk_score": None}
            decision = {"mirror": MIRROR_ID, "mirror_epoch": mirror_epoch, "label": LABEL, "command_id": command, "command_sha": payload_sha,
                        "claim_token": claimed["claim_token"], "epoch": ledger.epoch, "episode_key": record.episode_key, "ledger": record.sell_payload(),
                        "quote": {"bid": quote.bid, "ask": quote.ask, "source_at": quote.source_at.isoformat(), "available_at": quote.available_at.isoformat(),
                                  "reference": "midpoint"},
                        "decided_at": now.isoformat(), "paper_only": True, "own_decision": False}
            try:
                trade = repo.execute_trade(dict(live_experiment), cycle_id=cycle_id, candidate=candidate, side="SELL", quantity=quantity,
                                           signal_price=quote.midpoint, fill_price=fill["fill_price"], fx=fx, fees=fill["fees_usd"],
                                           slippage=fill["slippage_usd"], reason=f"{LABEL}: mirror of V2 ledger exit {record.exit_cause} (command {command[:12]})",
                                           decision=decision, quote_as_of=quote.source_at)
            except ValueError as exc:
                mirror.upsert({**claimed, "status": "EXIT_PENDING", "claim_token": None, "reason": f"PAPER_SELL_REJECTED:{exc}"})
                count("PAPER_SELL_REJECTED")
                continue
            executed = _executed_at(trade, now)
            repo.save_decision(experiment_id, cycle_id, candidate, "SELL", [MIRROR_ID, LABEL, str(record.exit_cause), command], trade["id"])
            live_experiment = repo.experiment(str(experiment["code"])) or live_experiment
            divergence = dict(pending.get("divergence") or {})
            divergence["sell"] = _divergence(record, side="SELL", quote=quote, fill_price=fill["fill_price"], quantity=quantity, decided_at=now, executed_at=executed)
            mirror.upsert({**claimed, "status": "CLOSED", "reason": action.reason, "claim_token": None, "sell_trade_id": trade["id"], "sell_at": executed,
                           "sell_fill_price": fill["fill_price"], "divergence": divergence})
            summary["sells"] += 1
            count("SELL")
    return summary


def run_once(*, ledger_row: Mapping[str, Any], mirror_epoch: str, repo: R2D2Repository, mirror: MirrorRepository, experiment: Mapping[str, Any],
             quotes: QuoteSource, resolve_market: MarketResolver, now: datetime, activated_at: datetime, exits_only: bool = False,
             fx: float = 1.0) -> dict[str, Any]:
    """One mirror cycle under the mirror-epoch lock: read confirmed facts, recover by reading, plan, execute, log the cycle."""
    if activated_at.tzinfo is None:
        raise MirrorInputError("ACTIVATION_NOT_AWARE")
    with mirror.cycle_lock(mirror_epoch) as acquired:
        if not acquired:
            return {"cycle_id": None, "mirror_epoch": mirror_epoch, "status": "CYCLE_LOCKED_ELSEWHERE", "actions": 0, "buys": 0, "sells": 0,
                    "skipped": 0, "deferred": 0, "dispositions": 0, "blocked": 0, "reasons": {"CYCLE_LOCKED_ELSEWHERE": 1}, "label": LABEL}
        ledger = read_ledger(ledger_row)
        live_experiment = repo.experiment(str(experiment["code"])) or dict(experiment)
        if live_experiment.get("status") == "completed":
            raise MirrorInputError("MIRROR_EXPERIMENT_CLOSED")
        recovered = reconcile(ledger=ledger, mirror_epoch=mirror_epoch, repo=repo, mirror=mirror, experiment=experiment, now=now)
        positions, cash, nav = _book(repo, live_experiment)
        marked = marked_excess(positions, cash, nav)
        actions = plan(ledger, mirror.load(mirror_epoch, ledger.epoch, str(experiment["id"])), activated_at=activated_at, exits_only=exits_only,
                       entries_paused=bool(live_experiment.get("entries_paused")), marked=marked)
        cycle_id = repo.start_cycle(str(experiment["id"]), list(MARKETS))
        try:
            summary = execute(actions, ledger=ledger, mirror_epoch=mirror_epoch, repo=repo, mirror=mirror, experiment=experiment, cycle_id=cycle_id,
                              quotes=quotes, resolve_market=resolve_market, now=now, fx=fx)
        except Exception as exc:
            repo.finish_cycle(cycle_id, "failed", len(ledger.records), len(actions), 0, error=type(exc).__name__, metadata={"mirror": MIRROR_ID, "label": LABEL})
            raise
        repo.finish_cycle(cycle_id, "completed", len(ledger.records), len(actions), summary["buys"] + summary["sells"],
                          metadata={"mirror": MIRROR_ID, "label": LABEL, "mirror_epoch": mirror_epoch, "epoch": ledger.epoch,
                                    "ledger_version": ledger.version, "ledger_state_sha": ledger.state_sha, "vetoed": ledger.vetoed,
                                    "data_gate_blocked": ledger.data_gate_blocked, "marked_excess": marked, "exits_only": exits_only, **recovered, **summary})
        return {"cycle_id": cycle_id, "epoch": ledger.epoch, "mirror_epoch": mirror_epoch, "ledger_version": ledger.version,
                "ledger_state_sha": ledger.state_sha, "vetoed": ledger.vetoed, "data_gate_blocked": ledger.data_gate_blocked,
                "terminal_reasons": list(ledger.terminal_reasons), "marked_excess": marked, "actions": len(actions), **recovered, **summary,
                "status": "COMPLETED", "label": LABEL}


# ---------------------------------------------------------------- publication (aggregates only; never evidence)

def public_summary(*, repo: R2D2Repository, mirror: MirrorRepository, experiment: Mapping[str, Any], mirror_epoch: str, epoch: str,
                   terminal_reasons: Iterable[str] = (), now: datetime | None = None) -> dict[str, Any]:
    """Daily public aggregates of the mirror. No symbols, no episode keys, no statistical verdict."""
    clock_now = now or datetime.now(timezone.utc)
    live_experiment = repo.experiment(str(experiment["code"])) or dict(experiment)
    positions, cash, nav = _book(repo, live_experiment)
    rows = list(mirror.load(mirror_epoch, epoch, str(experiment["id"])).values())
    today = clock_now.astimezone(timezone.utc).date()

    def _day(value: Any) -> bool:
        return isinstance(value, datetime) and value.astimezone(timezone.utc).date() == today

    buys = [row["divergence"]["buy"] for row in rows if isinstance(row.get("divergence"), dict) and "buy" in row["divergence"]]
    sells = [row["divergence"]["sell"] for row in rows if isinstance(row.get("divergence"), dict) and "sell" in row["divergence"]]

    def _mean(values: list[Any], key: str) -> float | None:
        numbers = [float(item[key]) for item in values if isinstance(item, dict) and isinstance(item.get(key), (int, float))]
        return round(sum(numbers) / len(numbers), 3) if numbers else None

    return {"schema": "R2D2_V2_MIRROR_PUBLIC_SUMMARY_V3", "label": LABEL, "statement": STATEMENT, "is_evidence": False,
            "mirror": MIRROR_ID, "mirror_version": MIRROR_VERSION, "mirror_epoch": mirror_epoch, "experiment_code": live_experiment["code"],
            "mirrored_epoch": epoch, "as_of": clock_now.isoformat(), "nav_paper_usd": round(nav, 2), "cash_usd": round(cash, 2),
            "open_positions": len(positions), "marked_excess": marked_excess(positions, cash, nav),
            "status_counts": {status: sum(1 for r in rows if r.get("status") == status) for status in STATUSES},
            "orders_today": sum(1 for r in rows if _day(r.get("buy_at"))) + sum(1 for r in rows if _day(r.get("sell_at"))),
            "divergence_buy": {"mean_price_bps": _mean(buys, "price_diff_bps"), "mean_latency_seconds": _mean(buys, "latency_seconds"), "count": len(buys)},
            "divergence_sell": {"mean_price_bps": _mean(sells, "price_diff_bps"), "mean_latency_seconds": _mean(sells, "latency_seconds"), "count": len(sells)},
            "active_vetoes": sorted(set(terminal_reasons)), "entries_paused": bool(live_experiment.get("entries_paused")),
            "skip_reasons": _counts(rows)}


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("status") in ("SKIPPED", "BLOCKED", "AWAITING_DISPOSITION") and isinstance(row.get("reason"), str):
            counts[row["reason"]] = counts.get(row["reason"], 0) + 1
    return counts


# ---------------------------------------------------------------- release receipt (R2D2_V2_MIRROR_RELEASE_V1)

@dataclass(frozen=True)
class MirrorRelease:
    mirror_epoch: str
    epoch: str
    experiment_code: str
    code_revision: str
    review_sha: str
    owner_order_ref: str
    published_at: datetime
    initial_cursor_at: datetime
    receipt_sha: str

    @classmethod
    def verify(cls, data: bytes, expected_sha: str, *, build_sha: str, now: datetime) -> "MirrorRelease":
        receipt_sha = hashlib.sha256(data).hexdigest()
        if not expected_sha or receipt_sha != expected_sha:
            raise MirrorInputError("MIRROR_RELEASE_SHA_MISMATCH")
        try:
            body = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise MirrorInputError("MIRROR_RELEASE_MALFORMED") from None
        if not isinstance(body, dict) or body.get("schema") != RELEASE_SCHEMA:
            raise MirrorInputError("MIRROR_RELEASE_SCHEMA_INVALID")
        mirror_epoch, epoch, code = body.get("mirror_epoch"), body.get("epoch"), body.get("experiment_code")
        if not isinstance(mirror_epoch, str) or not mirror_epoch.startswith(MIRROR_ID + "-"):
            raise MirrorInputError("MIRROR_RELEASE_MIRROR_EPOCH_INVALID")
        if not isinstance(epoch, str) or not epoch.startswith(SHADOW_EPOCH_PREFIX):
            raise MirrorInputError("MIRROR_RELEASE_EPOCH_INVALID")
        if not isinstance(code, str) or not code.startswith(MIRROR_ID):
            raise MirrorInputError("MIRROR_RELEASE_EXPERIMENT_INVALID")
        if body.get("code_revision") != build_sha:
            raise MirrorInputError("MIRROR_RELEASE_CODE_REVISION_MISMATCH")
        review, order = body.get("review_sha"), body.get("owner_order_ref")
        if not isinstance(review, str) or len(review) != 64 or not isinstance(order, str) or not order:
            raise MirrorInputError("MIRROR_RELEASE_RECEIPTS_MISSING")
        signatures = body.get("signatures")
        if not isinstance(signatures, list) or {s.get("party") for s in signatures if isinstance(s, dict)} != {"CODEX", "FABLE", "DUDU"}:
            raise MirrorInputError("MIRROR_RELEASE_SIGNATURES_INCOMPLETE")
        published, cursor = _time(body.get("published_at")), _time(body.get("initial_cursor_at"))
        if published > cursor:
            raise MirrorInputError("MIRROR_RELEASE_PUBLISHED_AFTER_CURSOR")
        cursor_ny = cursor.astimezone(NEW_YORK)
        if cursor_ny.time() > OFFICIAL_OPEN:
            raise MirrorInputError("MIRROR_RELEASE_CURSOR_AFTER_OPEN")  # the cursor is the open of its first mirrored session, published before it
        if cursor > now:
            raise MirrorInputError("MIRROR_RELEASE_NOT_YET_ACTIVE")
        return cls(mirror_epoch, epoch, code, str(body["code_revision"]), review, order, published, cursor, receipt_sha)


# ---------------------------------------------------------------- production adapters

class RealtimeQuoteSource:
    """Regular bid/ask quotes with their own source and receipt clocks; rows without both clocks are not valid quotes for the mirror."""

    def __init__(self, realtime: Any) -> None:
        self.realtime = realtime

    def quote(self, market: str, symbol: str, now: datetime) -> MirrorQuote | None:
        try:
            rows = self.realtime._us_portfolio_rows(market, now, [symbol])
            rows = [self.realtime._apply_stream_row(row) for row in rows]
        except Exception:
            logger.exception("mirror quote lookup failed for %s", symbol)
            return None
        for row in rows:
            if getattr(row, "symbol", None) != symbol:
                continue
            bid, ask = getattr(row, "bid", None), getattr(row, "ask", None)
            source_at, available_at = getattr(row, "as_of", None), getattr(row, "received_at", None) or getattr(row, "available_at", None)
            status = str(getattr(row, "status", "unavailable"))
            if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and isinstance(source_at, datetime) and isinstance(available_at, datetime):
                return MirrorQuote(float(bid), float(ask), source_at if source_at.tzinfo else source_at.replace(tzinfo=timezone.utc),
                                   available_at if available_at.tzinfo else available_at.replace(tzinfo=timezone.utc), status)
        return None


class RegistryMarketResolver:
    """Symbol -> NYSE/NASDAQ from the newest causal registry document of the file port (pinned evidence, never guessed)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._cache: dict[str, str] = {}

    def __call__(self, symbol: str) -> str | None:
        if symbol in self._cache:
            return self._cache[symbol]
        base = self.root / "components"
        try:
            days = sorted((p for p in base.iterdir() if p.is_dir()), reverse=True)
        except OSError:
            return None
        for day in days[:5]:
            try:
                document = json.loads((day / "registry.json").read_bytes())
            except (OSError, ValueError):
                continue
            for row in document.get("instruments", []) if isinstance(document, dict) else []:
                if isinstance(row, dict) and row.get("symbol") == symbol and row.get("market") in MARKETS:
                    self._cache[symbol] = str(row["market"])
                    return self._cache[symbol]
        return None


def main(argv: list[str] | None = None) -> int:
    """Worker loop. OFF unless enabled; every cycle rechecks the pinned release and the CERTIFIED epoch."""
    if os.environ.get("C3PO_R2D2_V2_MIRROR_ENABLED", "").lower() != "true":
        print('{"status":"OFF","reason":"C3PO_R2D2_V2_MIRROR_ENABLED is not true"}')
        return 0
    import importlib

    from .config import get_settings
    from .market_data.realtime import RealtimeMarketsService
    from .market_data.service import MarketDataService

    try:  # the shadow store ships with the V2 generator (PR #383); without it there is no ledger to mirror
        PostgresShadowStore = importlib.import_module("app.r2d2_v2_store").PostgresShadowStore
    except ImportError as exc:
        raise MirrorInputError("SHADOW_STORE_MODULE_MISSING") from exc

    settings = get_settings()
    database = Database(settings)
    database.initialize()
    release_path = Path(getattr(settings, "r2d2_v2_mirror_release_file", ""))
    expected_sha = str(getattr(settings, "r2d2_v2_mirror_release_sha", ""))
    epoch = str(getattr(settings, "r2d2_v2_mirror_epoch", ""))
    code = str(getattr(settings, "r2d2_v2_mirror_experiment_code", DEFAULT_EXPERIMENT_CODE))
    cycle_seconds = float(getattr(settings, "r2d2_v2_mirror_cycle_seconds", 20))
    exits_only = bool(getattr(settings, "r2d2_v2_mirror_exits_only", False))
    registry_root = Path(getattr(settings, "r2d2_v2_mirror_registry_root", ""))
    release = MirrorRelease.verify(release_path.read_bytes(), expected_sha, build_sha=settings.build_sha, now=datetime.now(timezone.utc))
    if release.epoch != epoch or release.experiment_code != code:
        raise MirrorInputError("MIRROR_RELEASE_DOES_NOT_MATCH_SETTINGS")
    repo = R2D2Repository(database)
    mirror = MirrorRepository(database)
    experiment = ensure_mirror_experiment(repo, code=code, epoch=epoch, mirror_epoch=release.mirror_epoch)
    store = PostgresShadowStore(database.connection)
    market_data = MarketDataService(settings, database)
    quotes = RealtimeQuoteSource(RealtimeMarketsService(settings, database, market_data.http))
    resolve = RegistryMarketResolver(registry_root)
    logger.info("%s worker started: mirror epoch %s, shadow epoch %s, experiment %s (%s)", MIRROR_ID, release.mirror_epoch, epoch, code, LABEL)
    while True:
        started = clock.monotonic()
        try:
            now = datetime.now(timezone.utc)
            MirrorRelease.verify(release_path.read_bytes(), expected_sha, build_sha=settings.build_sha, now=now)
            row = store.read(epoch)
            if row is None:
                logger.warning("shadow epoch %s not found; mirror idle", epoch)
            else:
                result = run_once(ledger_row=row, mirror_epoch=release.mirror_epoch, repo=repo, mirror=mirror, experiment=experiment, quotes=quotes,
                                  resolve_market=resolve, now=now, activated_at=release.initial_cursor_at, exits_only=exits_only)
                logger.info("mirror cycle %s", json.dumps(result, default=str, sort_keys=True))
        except MirrorInputError as exc:
            logger.error("mirror halted this cycle: %s", exc)
        except Exception:
            logger.exception("unhandled mirror error")
        clock.sleep(max(0.0, cycle_seconds - (clock.monotonic() - started)))


if __name__ == "__main__":
    raise SystemExit(main())
