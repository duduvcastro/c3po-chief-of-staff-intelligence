"""R2D2 V2 — paper mirror adapter (EMENDA 2 rev 2, closed six-hands; OFF by default).

Replicates decisions ALREADY RECORDED in the V2 virtual ledger (the shadow
generator's portfolio records) as paper orders in a dedicated R2D2 experiment
(`R2D2-V2-MIRROR-001`). The adapter decides nothing on its own. EMENDA 2 rev 2
and the Codex audits of #387 (rounds 1 and 2: I1–I5, C1–C5) fix these behaviours:

- one COMMAND per ledger decision with a durable identity (mirror epoch, shadow
  epoch, episode key, decision) and the hash of its payload, registered in the
  mirror's own memory BEFORE the paper effect; the effect is CLAIMED atomically
  (BUY_PENDING → BUY_EXECUTING, one claimant) and the claim token is verified
  INSIDE the paper engine's transaction (row lock), where the receipt is also
  written: effect and receipt commit together or not at all, a claim released
  elsewhere aborts the effect, and a release is a compare-and-set of the token
  it observed (never a blind reopen). Cycles of one mirror epoch are serialized
  by a lock; repetition returns the receipt; a payload that differs from the
  registered or executed one BLOCKS — also after OPEN, on recovery and on the
  terminal receipts (CLOSED, registered SKIPPED);
- a portfolio admission (kind PORTFOLIO, status OPEN, opened at or after the
  published initial cursor) becomes ONE paper BUY of the ledger quantity `q`
  (eight-decimal nominal precision; more decimals are rejected, never rounded);
  research episodes and controls are never mirrored; a BUY still pending when
  the virtual position already closed becomes SKIPPED; a BUY not yet executed
  obeys every veto in force at execution time, re-read inside the effect's
  transaction (pause, desk exits-only order, quote age);
- a recorded exit becomes ONE paper SELL of the quantity actually mirrored for
  that episode; until executed the position is EXIT_PENDING (latency recorded,
  new BUYs blocked); a missing quote never erases the position nor invents a
  fill; the exit obligation survives any conflict (a BLOCKED row with a position
  keeps blocking BUYs and still sells when the ledger records the exit). A row
  AWAITING_DISPOSITION keeps its position and blocks BUYs until the desk orders
  its disposition; nothing here sells it automatically;
- inherited vetoes: ledger terminal reasons, the generator's own admission
  vetoes recomputed from its state (NAV unobservable, day NAV unobservable,
  daily loss ≥ 2 %), the V2 collection data gate of the current session applied
  PER NAME (an unrestored issue of the name or a wildcard the name was not
  restored from), exits-only orders, the mirror experiment's own
  `entries_paused`, any pending exit, any block or disposition recorded in the
  same cycle, and any cap breached by marking (per US name across exchanges,
  48 % gross US aggregated, 95 % exposure, 5 % cash) block new BUYs; entries are
  planned only after this cycle's transitions are durable; nothing is liquidated;
- fills use a REGULAR bid/ask quote proven by the official XNYS calendar at the
  tick instant, with causal clocks (source ≤ available ≤ now, at most 10 s old,
  never in the future) validated with a clock re-read after the lookup and again
  inside the effect's transaction; midpoint reference and the simulator's US
  friction; the receipt records the quote clocks, the decision instant and the
  FACTUAL fill instant returned by the paper engine;
- memory is scoped by (mirror epoch, shadow epoch, experiment); the experiment
  is bound to one (mirror epoch, shadow epoch) at creation and the binding is
  immutable (rows never change experiment);
- the release receipt binds the initial cursor to the official open of an
  official session, names that session, and requires publication strictly
  before that open;
- everything published carries MIRROR_NOT_CERTIFIED.

Production wiring: the ledger is read through the shadow store of the
generator (PR #383, `r2d2_v2_store.PostgresShadowStore.read`); the paper
engine is the existing `R2D2Repository` (paper-only, no broker; the only touch
on it is the optional pair of transaction hooks of `execute_trade`); quotes come
from the provider's raw `us-quote` feed (bid/ask with tick clocks) recorded by
the mirror's own tape; nothing of the V1 selection/sizing/stop/watcher/learning
runs on the mirror experiment. The worker refuses to run without
`C3PO_R2D2_V2_MIRROR_ENABLED=true`, a pinned release receipt
(`R2D2_V2_MIRROR_RELEASE_V1`, verified before any database initialization) and
a CERTIFIED shadow epoch.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import threading
import time as time_module
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol, TypeGuard
from uuid import uuid4
from zoneinfo import ZoneInfo

from .database import Database
from .r2d2 import R2D2Repository, _paper_buy_execution, _paper_exit_execution

logger = logging.getLogger(__name__)

MIRROR_ID = "R2D2-V2-MIRROR"
MIRROR_VERSION = "v4"
LABEL = "MIRROR_NOT_CERTIFIED"
STATEMENT = "réplica descritiva da carteira virtual; não é evidência"
RELEASE_SCHEMA = "R2D2_V2_MIRROR_RELEASE_V1"
DEFAULT_EXPERIMENT_CODE = "R2D2-V2-MIRROR-001"
STARTING_CAPITAL_USD = 1_000_000.0
SHADOW_EPOCH_PREFIX = "R2D2-V2-SHADOW-"
MARKETS = ("NASDAQ", "NYSE")
NEW_YORK = ZoneInfo("America/New_York")
CAPS = {"per_name_percent": 6.0, "gross_us_percent": 48.0, "exposure_percent": 95.0, "cash_percent": 5.0}
QUOTE_MAX_AGE_SECONDS = 10.0
QUANTITY_DECIMALS = 8
METHODOLOGY_VERSION = "r2d2-v2-mirror-v4"
EXIT_CAUSES = ("STOP", "TARGET", "EVENT", "TIME")
STATUSES = ("SKIPPED", "BUY_PENDING", "BUY_EXECUTING", "OPEN", "EXIT_PENDING", "SELL_EXECUTING", "CLOSED", "AWAITING_DISPOSITION", "BLOCKED")
EXIT_OBLIGATION_STATUSES = ("EXIT_PENDING", "SELL_EXECUTING", "AWAITING_DISPOSITION")
SOURCE_ADMISSION_VETOES = ("NAV_UNOBSERVABLE", "DAY_NAV_UNOBSERVABLE", "DAILY_LOSS_LIMIT")
Clock = Callable[[], datetime]


class MirrorInputError(ValueError):
    """Controlled message only."""


class MirrorClaimLost(MirrorInputError):
    """The claim was released or taken by another process before the effect committed: the effect is aborted."""


class MirrorVetoAtEffect(MirrorInputError):
    """A mutable veto (pause, desk order, quote age) observed inside the effect's transaction: the effect is aborted."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False, default=str).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- official calendar (XNYS)

def _xnys() -> Any:
    import exchange_calendars

    return exchange_calendars.get_calendar("XNYS")


@lru_cache(maxsize=2048)
def session_bounds(day: date) -> tuple[datetime, datetime] | None:
    """Official open and close (UTC) of `day`, or None when it is not an official session (weekend, holiday)."""
    calendar = _xnys()
    if not calendar.is_session(day.isoformat()):
        return None
    return (calendar.session_open(day.isoformat()).to_pydatetime().astimezone(timezone.utc),
            calendar.session_close(day.isoformat()).to_pydatetime().astimezone(timezone.utc))


def regular_session_at(instant: datetime) -> bool:
    """True only inside [official open, official close) of the official session of the instant's New York date."""
    if not isinstance(instant, datetime) or instant.tzinfo is None:
        return False
    bounds = session_bounds(instant.astimezone(NEW_YORK).date())
    return bounds is not None and bounds[0] <= instant.astimezone(timezone.utc) < bounds[1]


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


def _finite(value: Any) -> TypeGuard[float]:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _number(value: Any, *, positive: bool = False) -> float:
    if not _finite(value) or (positive and value <= 0):
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


def _issue_gates(issue: Mapping[str, Any], instrument_key: str | None) -> bool:
    """The collector's gate (#383 `_admission_block`): an active issue of the session gates a name unless the name was restored."""
    scope, restored = issue.get("instrument"), issue.get("restored_instruments") or []
    if instrument_key is None:
        return scope == "*" or scope not in restored
    return (scope == "*" or scope == instrument_key) and instrument_key not in restored


@dataclass(frozen=True)
class LedgerView:
    epoch: str
    version: int
    state_sha: str
    session: str | None
    terminal_reasons: tuple[str, ...]
    source_vetoes: tuple[str, ...]
    data_issues: tuple[Mapping[str, Any], ...]
    records: tuple[LedgerRecord, ...]

    @property
    def data_gate_blocked(self) -> bool:
        """At least one name is gated by an active, unrestored data issue of the current session (coarse, for reporting)."""
        return any(_issue_gates(issue, None) for issue in self.data_issues)

    def gated(self, instrument_key: str) -> bool:
        """The gate as the generator applies it to this name: the wildcard no longer gates a name it restored (I5b)."""
        return any(_issue_gates(issue, instrument_key) for issue in self.data_issues)

    @property
    def vetoed(self) -> bool:
        return bool(self.terminal_reasons) or bool(self.source_vetoes) or self.data_gate_blocked

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


def source_admission_vetoes(ledger: Mapping[str, Any]) -> tuple[str, ...]:
    """The generator's own admission vetoes (#383 `_admission`), recomputed from the state it publishes.

    NAV = cash + marks of OPEN positions + unpaid receivables, unknown when any position has unknown accounting/order or
    an OPEN position without a mark; NAV_UNOBSERVABLE (unknown or ≤ 0), DAY_NAV_UNOBSERVABLE (no session start NAV),
    DAILY_LOSS_LIMIT (NAV ≤ 98 % of the session start NAV), MARKED_CAP_EXCESS (the source's global marking veto, I5c:
    gross of OPEN positions > 48 % of NAV, or cash < 5 % of NAV, or any OPEN position marked above 6 % of NAV — in the
    same order and with the same thresholds as `_admission`, before any sizing). An unknown NAV is never treated as
    zero (I5a). Per-instrument vetoes of the source (POSITION_ALREADY_OPEN, NO_SAME_DAY_REENTRY) are not global and are
    not inherited: the ledger already records the admission of the episode being mirrored."""
    cash, positions = ledger.get("cash"), ledger.get("portfolio")
    if not _finite(cash) or not isinstance(positions, dict):
        return ("NAV_UNOBSERVABLE",)
    gross = rights = 0.0
    for record in positions.values():
        if not isinstance(record, dict) or record.get("accounting_unknown") or record.get("order_unknown"):
            return ("NAV_UNOBSERVABLE",)
        if record.get("status") == "OPEN":
            mark, quantity = record.get("mark"), record.get("quantity")
            if not _finite(mark) or not _finite(quantity):
                return ("NAV_UNOBSERVABLE",)
            gross += float(quantity) * float(mark)
        receivables = record.get("receivables")
        if receivables is not None:
            if not isinstance(receivables, dict):
                return ("NAV_UNOBSERVABLE",)
            for item in receivables.values():
                amount = item.get("amount") if isinstance(item, dict) else None
                if not _finite(amount):
                    return ("NAV_UNOBSERVABLE",)
                if not item.get("paid"):
                    rights += float(amount)
    nav = float(cash) + gross + rights
    if nav <= 0:
        return ("NAV_UNOBSERVABLE",)
    start = ledger.get("session_start_nav")
    if start is None:
        return ("DAY_NAV_UNOBSERVABLE",)
    if not _finite(start):
        return ("NAV_UNOBSERVABLE",)
    if nav <= 0.98 * float(start):
        return ("DAILY_LOSS_LIMIT",)
    live = [record for record in positions.values() if isinstance(record, dict) and record.get("status") == "OPEN"]
    if (gross > 0.48 * nav or float(cash) < 0.05 * nav
            or any(float(record["quantity"]) * float(record["mark"]) > 0.06 * nav for record in live)):
        return ("MARKED_CAP_EXCESS",)
    return ()


def _data_issues(state: Mapping[str, Any], session: str | None) -> tuple[Mapping[str, Any], ...]:
    issues = state.get("active_data_issues")
    if issues is None:
        return ()
    if not isinstance(issues, dict):
        raise MirrorInputError("SHADOW_DATA_ISSUES_INVALID")
    selected = []
    for issue in issues.values():
        if not isinstance(issue, dict):
            raise MirrorInputError("SHADOW_DATA_ISSUES_INVALID")
        if issue.get("session") == session:
            selected.append(issue)
    return tuple(selected)


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
                      source_vetoes=source_admission_vetoes(ledger), data_issues=_data_issues(state, session_key), records=records)


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
_SCOPE_FIELDS = ("mirror_epoch", "epoch", "episode_key")
_IMMUTABLE_FIELDS = _SCOPE_FIELDS + ("experiment_id", "created_at")


def _observed(previous: Mapping[str, Any]) -> tuple[str, ...]:
    """The status a row had when this cycle read it: the only state a conditional write may replace (I1)."""
    return (str(previous["status"]),) if previous.get("status") else ()


def has_position(row: Mapping[str, Any]) -> bool:
    return bool(row.get("buy_trade_id")) and not row.get("sell_trade_id")


def _key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(row["mirror_epoch"]), str(row["epoch"]), str(row["episode_key"]))


def _from_sql(values: Iterable[Any]) -> dict[str, Any]:
    """A stored row as the memory mode presents it: identifiers are strings (UUID columns come back as UUID objects)."""
    row: dict[str, Any] = dict(zip(MIRROR_FIELDS, values))
    for field in ("experiment_id", "buy_trade_id", "sell_trade_id"):
        if row.get(field) is not None:
            row[field] = str(row[field])
    return row


class MirrorRepository:
    """Per-episode command memory scoped by (mirror epoch, shadow epoch, experiment).

    Claims are atomic; the claim token is verified inside the paper effect's transaction (`guard`) and the receipt is
    written there too (`receipt`), so effect and receipt commit together; releases are compare-and-set (`release`);
    cycles are serialized per mirror epoch (`cycle_lock`)."""

    def __init__(self, database: Database) -> None:
        self.database = database
        if not hasattr(database, "_r2d2_v2_mirror_memory"):
            database._r2d2_v2_mirror_memory = {}  # type: ignore[attr-defined]
        if not hasattr(database, "_r2d2_v2_mirror_lock"):
            database._r2d2_v2_mirror_lock = threading.Lock()  # type: ignore[attr-defined]
        if not hasattr(database, "_r2d2_v2_mirror_rows_lock"):
            database._r2d2_v2_mirror_rows_lock = threading.RLock()  # type: ignore[attr-defined]

    @property
    def memory(self) -> dict[tuple[str, str, str], dict[str, Any]]:
        return self.database._r2d2_v2_mirror_memory  # type: ignore[attr-defined]

    @property
    def _rows_lock(self) -> threading.RLock:
        return self.database._r2d2_v2_mirror_rows_lock  # type: ignore[attr-defined]

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
            with self._rows_lock:
                return {key[2]: dict(value) for key, value in self.memory.items()
                        if key[0] == mirror_epoch and key[1] == epoch and value.get("experiment_id") == experiment_id}
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT {', '.join(MIRROR_FIELDS)} FROM r2d2_v2_mirror_episodes WHERE mirror_epoch=%s AND epoch=%s AND experiment_id=%s",
                (mirror_epoch, epoch, experiment_id)).fetchall()
        return {str(row[2]): _from_sql(row) for row in rows}

    @staticmethod
    def _validated(row: Mapping[str, Any], now: datetime) -> dict[str, Any]:
        record = {field: row.get(field) for field in MIRROR_FIELDS}
        if record["status"] not in STATUSES:
            raise MirrorInputError("MIRROR_STATUS_INVALID")
        for key in ("mirror_epoch", "epoch", "episode_key", "experiment_id"):
            if not record.get(key):
                raise MirrorInputError("MIRROR_ROW_SCOPE_MISSING")
        record["updated_at"] = now
        return record

    @staticmethod
    def _values(record: Mapping[str, Any], fields: Iterable[str]) -> list[Any]:
        return [json.dumps(record[field], default=str) if field == "divergence" else record[field] for field in fields]

    def write(self, row: Mapping[str, Any], *, expected: tuple[str, ...] | None, insert: bool = True) -> tuple[dict[str, Any] | None, bool]:
        """Conditional insert-or-update of a command row (Codex #387 round 3, I1).

        An absent row is inserted only when `insert` is true. A present row is updated only when its CURRENT status is in
        `expected` (None = only the status the new row carries, i.e. an idempotent re-registration) and it belongs to the
        same experiment (C3; another experiment raises). A row that advanced elsewhere between the caller's read and this
        write (claimed, OPEN, CLOSED, ...) is never overwritten: the caller gets the row as it is now and `applied=False`,
        so a stale worker can never reopen a command that another worker already executed."""
        now = _utc_now()
        record = self._validated(row, now)
        statuses = tuple(expected) if expected is not None else (record["status"],)
        key = _key(record)
        if not self.database.database_url:
            with self._rows_lock:
                current = self.memory.get(key)
                if current is None:
                    if not insert:
                        return None, False
                    record["created_at"] = now
                    self.memory[key] = record
                    return dict(record), True
                if current.get("experiment_id") != record["experiment_id"]:
                    raise MirrorInputError("MIRROR_ROW_EXPERIMENT_IMMUTABLE")
                if current.get("status") not in statuses:
                    return dict(current), False
                record["created_at"] = current["created_at"]
                self.memory[key] = record
                return dict(record), True
        record["created_at"] = record.get("created_at") or now
        fields = [field for field in MIRROR_FIELDS if field not in _IMMUTABLE_FIELDS]
        columns = ", ".join(MIRROR_FIELDS)
        selected = ", ".join(MIRROR_FIELDS)
        with self.database.connection() as connection:
            if insert:
                placeholders = ", ".join("%s::jsonb" if field == "divergence" else "%s" for field in MIRROR_FIELDS)
                updates = ", ".join(f"{field}=EXCLUDED.{field}" for field in fields)
                written = connection.execute(
                    f"INSERT INTO r2d2_v2_mirror_episodes ({columns}) VALUES ({placeholders}) "
                    f"ON CONFLICT (mirror_epoch, epoch, episode_key) DO UPDATE SET {updates} "
                    f"WHERE r2d2_v2_mirror_episodes.experiment_id = EXCLUDED.experiment_id "
                    f"AND r2d2_v2_mirror_episodes.status = ANY(%s) RETURNING {selected}",
                    [*self._values(record, MIRROR_FIELDS), list(statuses)]).fetchone()
            else:
                assignments = ", ".join(f"{field}=%s::jsonb" if field == "divergence" else f"{field}=%s" for field in fields)
                written = connection.execute(
                    f"UPDATE r2d2_v2_mirror_episodes SET {assignments} WHERE mirror_epoch=%s AND epoch=%s AND episode_key=%s "
                    f"AND experiment_id=%s AND status = ANY(%s) RETURNING {selected}",
                    [*self._values(record, fields), *key, record["experiment_id"], list(statuses)]).fetchone()
            if written is not None:
                connection.commit()
                return _from_sql(written), True
            connection.rollback()
            current = connection.execute(
                f"SELECT {selected} FROM r2d2_v2_mirror_episodes WHERE mirror_epoch=%s AND epoch=%s AND episode_key=%s", key).fetchone()
        if current is None:
            return None, False
        row_now = _from_sql(current)
        if row_now.get("experiment_id") != record["experiment_id"]:
            raise MirrorInputError("MIRROR_ROW_EXPERIMENT_IMMUTABLE")
        return row_now, False

    def upsert(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """Insert a command row, or rewrite it idempotently while it still has the status the row carries. A row that
        advanced elsewhere is never overwritten (raises MIRROR_ROW_ADVANCED_ELSEWHERE); the experiment binding is immutable (C3)."""
        record, applied = self.write(row, expected=None, insert=True)
        if not applied or record is None:
            raise MirrorInputError("MIRROR_ROW_ADVANCED_ELSEWHERE")
        return record

    def claim(self, row: Mapping[str, Any], *, from_status: str, to_status: str, now: datetime) -> dict[str, Any] | None:
        """Atomically move a command from `from_status` to `to_status`; only one claimant ever gets the row."""
        token = str(uuid4())
        key = _key(row)
        if not self.database.database_url:
            with self._rows_lock:
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
        return _from_sql(claimed) if claimed else None

    def guard(self, connection: Any, row: Mapping[str, Any], *, token: str, status: str) -> None:
        """Inside the effect's transaction (I1): the claim must still be ours, under the row lock; otherwise the effect aborts."""
        key = _key(row)
        if not self.database.database_url:
            with self._rows_lock:
                current = self.memory.get(key)
                if current is None or current.get("status") != status or current.get("claim_token") != token:
                    raise MirrorClaimLost("CLAIM_LOST_BEFORE_EFFECT")
            return
        found = connection.execute(
            "SELECT status, claim_token FROM r2d2_v2_mirror_episodes WHERE mirror_epoch=%s AND epoch=%s AND episode_key=%s FOR UPDATE",
            key).fetchone()
        if found is None or found[0] != status or found[1] != token:
            raise MirrorClaimLost("CLAIM_LOST_BEFORE_EFFECT")

    def receipt(self, connection: Any, row: Mapping[str, Any], *, token: str, status: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        """Inside the effect's transaction (I1): the command's receipt, committed atomically with the paper effect."""
        now = _utc_now()
        record = self._validated({**row, **updates, "claim_token": None, "claimed_at": None}, now)
        key = _key(record)
        if not self.database.database_url:
            with self._rows_lock:
                current = self.memory.get(key)
                if current is None or current.get("status") != status or current.get("claim_token") != token:
                    raise MirrorClaimLost("CLAIM_LOST_BEFORE_RECEIPT")
                record["created_at"] = current["created_at"]
                self.memory[key] = record
                return dict(record)
        fields = [field for field in MIRROR_FIELDS if field not in _IMMUTABLE_FIELDS]
        assignments = ", ".join(f"{field}=%s::jsonb" if field == "divergence" else f"{field}=%s" for field in fields)
        cursor = connection.execute(
            f"UPDATE r2d2_v2_mirror_episodes SET {assignments} WHERE mirror_epoch=%s AND epoch=%s AND episode_key=%s AND status=%s AND claim_token=%s",
            [*self._values(record, fields), *key, status, token])
        if cursor.rowcount != 1:
            raise MirrorClaimLost("CLAIM_LOST_BEFORE_RECEIPT")
        return dict(record)

    def release(self, row: Mapping[str, Any], *, token: str, from_status: str, to_status: str, reason: str, now: datetime) -> bool:
        """Compare-and-set release of the claim whose token was observed; a newer claim or a committed receipt is never clobbered."""
        key = _key(row)
        if not self.database.database_url:
            with self._rows_lock:
                current = self.memory.get(key)
                if current is None or current.get("status") != from_status or current.get("claim_token") != token:
                    return False
                current.update(status=to_status, claim_token=None, claimed_at=None, reason=reason, updated_at=now)
                return True
        with self.database.connection() as connection:
            cursor = connection.execute(
                """UPDATE r2d2_v2_mirror_episodes SET status=%s, claim_token=NULL, claimed_at=NULL, reason=%s, updated_at=%s
                   WHERE mirror_epoch=%s AND epoch=%s AND episode_key=%s AND status=%s AND claim_token=%s""",
                (to_status, reason, now, *key, from_status, token))
            released = cursor.rowcount == 1
            connection.commit()
        return released

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


# ---------------------------------------------------------------- experiment (dedicated paper account, NAV 1M)

def mirror_mandate(epoch: str, mirror_epoch: str) -> dict[str, Any]:
    return {
        "mode": "paper_only", "real_broker_execution": False, "mirror": MIRROR_ID, "mirror_version": MIRROR_VERSION, "mirror_epoch": mirror_epoch,
        "label": LABEL, "statement": STATEMENT, "mirrored_epoch": epoch, "markets": list(MARKETS),
        "own_decisions": False, "source": "V2 virtual ledger (shadow generator) — admissions and exits already recorded",
        "caps": dict(CAPS), "quote_policy": {"regular_bid_ask": True, "regularity": "official XNYS session at the tick instant",
                                             "max_age_seconds": QUOTE_MAX_AGE_SECONDS, "reference": "midpoint",
                                             "causal_clocks": "source_at <= available_at <= decision, re-read at the effect",
                                             "friction_us": {"slippage_rate": 0.0010, "fee_rate": 0.0004}},
        "quantity_policy": f"ledger q preserved, {QUANTITY_DECIMALS} decimals, no resizing; caps/cash including friction reject permanently",
        "no_minimum_position": True, "research_episodes_mirrored": False, "controls_mirrored": False,
        "binding": "immutable: one experiment per (mirror epoch, shadow epoch)",
        "decision_log": "r2d2_v2_mirror_episodes receipts + r2d2_trades.decision_snapshot, committed together; r2d2_decisions (V1 scored log) is not written",
        "cycle_status": "succeeded when every order was executed or deferred by rule; partial when the paper engine rejected an order or a row was blocked",
        "writes": "conditional on the status read in the same cycle; a row advanced elsewhere is never overwritten",
        "is_evidence": False, "certification_input": False,
    }


def verify_experiment_binding(experiment: Mapping[str, Any], *, epoch: str, mirror_epoch: str) -> None:
    """The experiment is bound to exactly one (mirror epoch, shadow epoch) by its mandate (C3); anything else is refused."""
    mandate = experiment.get("mandate")
    if (not isinstance(mandate, dict) or mandate.get("mirror") != MIRROR_ID or mandate.get("mirror_epoch") != mirror_epoch
            or mandate.get("mirrored_epoch") != epoch or mandate.get("real_broker_execution") is not False):
        raise MirrorInputError("MIRROR_EXPERIMENT_BOUND_TO_ANOTHER_MIRROR")


def ensure_mirror_experiment(repo: R2D2Repository, *, code: str, epoch: str, mirror_epoch: str,
                             starting_capital: float = STARTING_CAPITAL_USD, now: datetime | None = None) -> dict[str, Any]:
    """Create-or-read the mirror's own paper experiment. Never the V1 initialization routine; never re-runs a closed one;
    never rebinds an existing experiment to another mirror or shadow epoch (its mandate is written once)."""
    if not code.startswith(MIRROR_ID):
        raise MirrorInputError("MIRROR_EXPERIMENT_CODE_INVALID")
    clock_now = now or _utc_now()
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
        experiment = dict(repo.memory["experiment"])
    else:
        with repo.database.connection() as connection:
            row = connection.execute(
                """INSERT INTO r2d2_experiments
                       (id, code, status, starting_capital, cash_balance, start_date, end_date, checkpoint_date,
                        is_continuous, methodology_version, mandate)
                   VALUES (%s, %s, 'running', %s, %s, %s, %s, %s, TRUE, %s, %s::jsonb)
                   ON CONFLICT (code) DO NOTHING
                   RETURNING id::text, code, status, base_currency, starting_capital, cash_balance,
                             start_date, checkpoint_date, methodology_version, mandate,
                             entries_paused, entries_paused_at, entries_pause_operator,
                             entries_pause_reason, policy_epoch, policy_epoch_started_at,
                             entry_score_adapter_version, entry_score_adapter_enabled_at,
                             created_at, updated_at""",
                (payload["id"], code, starting_capital, starting_capital, clock_now.date(), clock_now.date(), clock_now.date(),
                 METHODOLOGY_VERSION, json.dumps(mandate))).fetchone()
            connection.commit()
        existing = repo.experiment(code) if row is None else R2D2Repository._experiment(row)
        if existing is None:
            raise MirrorInputError("MIRROR_EXPERIMENT_UNREADABLE")
        experiment = existing
    verify_experiment_binding(experiment, epoch=epoch, mirror_epoch=mirror_epoch)
    if experiment["status"] == "completed":
        raise MirrorInputError("MIRROR_EXPERIMENT_CLOSED")
    return experiment


def _entries_paused(repo: R2D2Repository, connection: Any, experiment_id: str) -> bool:
    """The pause flag as it is at the effect (I3): read inside the same transaction that holds the experiment row lock."""
    if not repo.database.database_url:
        current = repo.memory["experiment"]
        return bool(current and current.get("entries_paused"))
    row = connection.execute("SELECT entries_paused FROM r2d2_experiments WHERE id=%s", (experiment_id,)).fetchone()
    return bool(row and row[0])


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


ENTRY_KINDS = ("BUY", "DEFER")


def plan(ledger: LedgerView, mirrored: Mapping[str, Mapping[str, Any]], *, activated_at: datetime, exits_only: bool = False,
         entries_paused: bool = False, marked: str | None = None) -> list[Action]:
    """Which commands are due now. SKIP/BLOCK are persisted (never revisited); DEFER is retried next cycle.

    Blocks and dispositions discovered in this cycle join the obligations BEFORE entries are planned (I4); terminal
    receipts are compared with the ledger's current payload (I2); the generator's admission vetoes (I5a) and the per-name
    data gate (I5b) apply to every BUY not yet executed."""
    records = ledger.by_key()
    blockers: list[str] = []
    if exits_only:
        blockers.append("EXITS_ONLY_BY_DESK_ORDER")
    if entries_paused:
        blockers.append("MIRROR_ENTRIES_PAUSED")
    if ledger.terminal_reasons:
        blockers.append("LEDGER_VETO:" + ",".join(ledger.terminal_reasons))
    if ledger.source_vetoes:
        blockers.append("LEDGER_ADMISSION_VETO:" + ",".join(ledger.source_vetoes))
    if marked:
        blockers.append(marked)
    conflicts: dict[str, str] = {}  # rows that will be BLOCKED this cycle (payload conflicts), before any entry
    for key, row in mirrored.items():
        record = records.get(key)
        if record is None:
            continue
        buy_sha = digest(record.buy_payload())
        status = row.get("status")
        if status in ("BUY_PENDING", "BUY_EXECUTING", "OPEN") and row.get("buy_command_sha") not in (None, buy_sha):
            conflicts[key] = "COMMAND_PAYLOAD_CONFLICT"
        elif status == "CLOSED" and (row.get("buy_command_sha") not in (None, buy_sha)
                                     or row.get("sell_command_sha") not in (None, digest(record.sell_payload()))):
            conflicts[key] = "TERMINAL_RECEIPT_PAYLOAD_CONFLICT"
        elif status == "SKIPPED" and row.get("buy_command_sha") not in (None, buy_sha):
            conflicts[key] = "TERMINAL_RECEIPT_PAYLOAD_CONFLICT"
    obligations = [key for key, row in mirrored.items()
                   if row.get("status") in EXIT_OBLIGATION_STATUSES
                   or (row.get("status") in ("OPEN", "BLOCKED") and key in records and records[key].status == "CLOSED")
                   or (row.get("status") == "BLOCKED" and has_position(row))
                   or (key in conflicts and (has_position(row) or row.get("status") == "OPEN"))
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
        conflict = conflicts.get(record.episode_key)
        entry_veto = veto if veto is not None else ("COLLECTION_DATA_GATE_BLOCKED" if ledger.gated(record.instrument_key) else None)
        if row is None:
            if record.status == "CLOSED":
                actions.append(Action("SKIP", record, "CLOSED_BEFORE_MIRROR", record.episode_key))
            elif record.opened_at < activated_at:
                actions.append(Action("SKIP", record, "OPENED_BEFORE_INITIAL_CURSOR", record.episode_key))
            elif not quantity_precision_ok(record.quantity):
                actions.append(Action("SKIP", record, "QUANTITY_PRECISION_INVALID", record.episode_key))
            elif entry_veto is not None:
                actions.append(Action("DEFER", record, entry_veto, record.episode_key))
            else:
                actions.append(Action("BUY", record, "LEDGER_ADMISSION_RECORDED", record.episode_key))
        elif conflict is not None:
            actions.append(Action("BLOCK", record, conflict, record.episode_key))
        elif status in ("BUY_PENDING", "BUY_EXECUTING"):
            if record.status == "CLOSED":
                actions.append(Action("SKIP", record, "CLOSED_BEFORE_MIRROR_EXECUTION", record.episode_key))
            elif entry_veto is not None:
                actions.append(Action("DEFER", record, entry_veto, record.episode_key))  # every veto in force applies before an unexecuted BUY
            else:
                actions.append(Action("BUY", record, "COMMAND_REGISTERED_EFFECT_PENDING", record.episode_key))
        elif status == "OPEN":
            if record.status == "CLOSED":
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
    regular: bool = False  # proven by the official calendar at the tick instant; a source that cannot prove it is never valid

    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2


class QuoteSource(Protocol):
    def quote(self, market: str, symbol: str, now: datetime) -> MirrorQuote | None: ...


MarketResolver = Callable[[str], str | None]


def quote_valid(quote: MirrorQuote | None, now: datetime, max_age_seconds: float = QUOTE_MAX_AGE_SECONDS) -> bool:
    """A regular, live bid/ask with causal clocks: source_at <= available_at <= now, at most `max_age_seconds` old, never future."""
    if quote is None or quote.status != "live" or quote.regular is not True:
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


@dataclass(frozen=True)
class TapeQuote:
    bid: float
    ask: float
    tick_at: datetime
    received_at: datetime


class QuoteTape:
    """Latest causal bid/ask per symbol from the provider's raw `us-quote` payloads (`s`, `bp`, `ask` as `ap`, `t` in ms).

    The same fields the V2 snapshot producer records: finite positive prices, a tick clock not after the local receipt,
    never regressing; anything else is counted and ignored. Regularity is proven by the official calendar at the tick."""

    def __init__(self) -> None:
        self._quotes: dict[str, TapeQuote] = {}
        self._lock = threading.Lock()
        self.rejected: dict[str, int] = {}
        self.updates = 0

    def _reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

    def record(self, payload: str, received_at: datetime, allowed: set[str] | None = None) -> str | None:
        try:
            item = json.loads(payload)
        except ValueError:
            self._reject("NOT_JSON")
            return None
        if not isinstance(item, dict):
            self._reject("NOT_OBJECT")
            return None
        symbol = str(item.get("s") or "").strip().upper()
        if not symbol or (allowed is not None and symbol not in allowed):
            self._reject("SYMBOL_NOT_LISTED")
            return None
        stamp = item.get("t")
        if not _finite(stamp) or stamp <= 0:
            self._reject("TICK_CLOCK_INVALID")
            return None
        if received_at.tzinfo is None:
            self._reject("RECEIPT_CLOCK_NAIVE")
            return None
        tick_at = datetime.fromtimestamp(float(stamp) / 1000, tz=timezone.utc)
        if tick_at > received_at:
            self._reject("TICK_IN_FUTURE")
            return None
        bid, ask = item.get("bp"), item.get("ap")
        if not _finite(bid) or not _finite(ask) or not 0 < float(bid) <= float(ask):
            self._reject("BID_ASK_INVALID")
            return None
        with self._lock:
            current = self._quotes.get(symbol)
            if current is not None and tick_at < current.tick_at:
                self._reject("TICK_REGRESSES")
                return None
            self._quotes[symbol] = TapeQuote(float(bid), float(ask), tick_at, received_at.astimezone(timezone.utc))
            self.updates += 1
        return symbol

    def quote(self, market: str, symbol: str, now: datetime) -> MirrorQuote | None:
        with self._lock:
            item = self._quotes.get(symbol)
        if item is None:
            return None
        return MirrorQuote(item.bid, item.ask, item.tick_at, item.received_at, "live", regular=regular_session_at(item.tick_at))


async def stream_quotes(tape: QuoteTape, token: str, wanted: Callable[[], set[str]], stop: threading.Event, *,
                        url_base: str = "wss://ws.eodhistoricaldata.com/ws/us-quote", clock: Clock = _utc_now) -> None:
    """Consume the provider's `us-quote` feed into the tape until `stop`; reconnects. The token never reaches logs or receipts."""
    import websockets

    url = f"{url_base}?api_token={token}"
    while not stop.is_set():
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=2, max_size=1_000_000) as socket:
                subscribed: set[str] = set()
                while not stop.is_set():
                    missing = wanted() - subscribed
                    if missing:
                        await socket.send(json.dumps({"action": "subscribe", "symbols": ",".join(sorted(missing))}))
                        subscribed |= missing
                    try:
                        message = await asyncio.wait_for(socket.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    tape.record(message if isinstance(message, str) else bytes(message).decode("utf-8", "replace"), clock())
        except Exception as exc:  # the reason is logged by class only: the URL carries the token
            logger.warning("mirror quote stream disconnected: %s", type(exc).__name__)
            await asyncio.sleep(2.0)


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
    """Resolve claimed/pending commands by READING the paper trades; never a new effect.

    With the receipt committed inside the effect's transaction, a claim without a trade is a claimant that died before
    committing (or one still in flight: its release is a compare-and-set that waits for the row lock and then fails).
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
            if status in ("BUY_EXECUTING", "SELL_EXECUTING") and isinstance(row.get("claim_token"), str):
                if mirror.release(row, token=str(row["claim_token"]), from_status=status,
                                  to_status="BUY_PENDING" if side == "BUY" else "EXIT_PENDING", reason="CLAIM_RELEASED_NO_EFFECT", now=now):
                    counts["released"] += 1  # a CAS that fails means the effect committed meanwhile: its receipt is already durable
            continue
        # Every recovery write is conditional on the status this pass read (I1): if the claimant's own receipt committed
        # meanwhile, the row already carries the factual receipt and is left untouched.
        if trade.get("command_sha") != registered_sha or (record is not None and current_sha != registered_sha):
            _, applied = mirror.write({**row, "status": "BLOCKED", "reason": "COMMAND_PAYLOAD_CONFLICT", "claim_token": None,
                                       **({"buy_trade_id": trade["id"], "buy_at": _executed_at(trade, now), "buy_quantity": float(trade["quantity"]),
                                           "buy_fill_price": float(trade["fill_price_local"])} if side == "BUY" and not row.get("buy_trade_id") else {})},
                                      expected=(str(status),), insert=False)
            counts["conflicts"] += int(applied)
            continue
        executed = _executed_at(trade, now)
        divergence = dict(row.get("divergence") or {})
        if side == "BUY" and trade.get("side") == "BUY":
            if record is not None:
                divergence["buy"] = _divergence(record, side="BUY", quote=None, fill_price=float(trade["fill_price_local"]), quantity=float(trade["quantity"]),
                                                decided_at=executed, executed_at=executed)
            _, applied = mirror.write({**row, "status": "OPEN", "reason": "EFFECT_RECOVERED_BY_READING", "claim_token": None, "buy_trade_id": trade["id"],
                                       "buy_at": executed, "buy_quantity": float(trade["quantity"]), "buy_fill_price": float(trade["fill_price_local"]),
                                       "divergence": divergence}, expected=(str(status),), insert=False)
            counts["buy_adopted"] += int(applied)
        elif side == "SELL" and trade.get("side") == "SELL":
            if record is not None:
                divergence["sell"] = _divergence(record, side="SELL", quote=None, fill_price=float(trade["fill_price_local"]), quantity=float(trade["quantity"]),
                                                 decided_at=executed, executed_at=executed)
            _, applied = mirror.write({**row, "status": "CLOSED", "reason": "EFFECT_RECOVERED_BY_READING", "claim_token": None, "sell_trade_id": trade["id"],
                                       "sell_at": executed, "sell_fill_price": float(trade["fill_price_local"]), "divergence": divergence},
                                      expected=(str(status),), insert=False)
            counts["sell_adopted"] += int(applied)
    return counts


def execute(actions: Iterable[Action], *, ledger: LedgerView, mirror_epoch: str, repo: R2D2Repository, mirror: MirrorRepository,
            experiment: Mapping[str, Any], cycle_id: str, quotes: QuoteSource, resolve_market: MarketResolver, now: datetime,
            clock: Clock | None = None, exits_only: bool = False, fx: float = 1.0) -> dict[str, Any]:
    """Emit the paper orders for the planned commands: register → claim → effect (claim verified and receipt written inside the
    engine's transaction) → receipt. The quote is validated with a clock re-read after the lookup and again at the effect."""
    summary: dict[str, Any] = {"buys": 0, "sells": 0, "skipped": 0, "deferred": 0, "dispositions": 0, "blocked": 0, "reasons": {}}
    read_clock: Clock = clock or (lambda: now)

    def count(reason: str) -> None:
        summary["reasons"][reason] = summary["reasons"].get(reason, 0) + 1

    experiment_id = str(experiment["code"]) and str(experiment["id"])
    mirrored = mirror.load(mirror_epoch, ledger.epoch, experiment_id)

    def base_row(record: LedgerRecord, market: str | None) -> dict[str, Any]:
        return {"mirror_epoch": mirror_epoch, "epoch": ledger.epoch, "episode_key": record.episode_key, "symbol": record.symbol, "market": market,
                "experiment_id": experiment_id, "ledger_entry_price": record.entry_price, "ledger_quantity": record.quantity, "ledger_opened_at": record.opened_at}

    live_experiment = repo.experiment(str(experiment["code"])) or dict(experiment)

    def write_or_defer(row: Mapping[str, Any], *, expected: tuple[str, ...], insert: bool,
                       reason: str = "ROW_ADVANCED_ELSEWHERE") -> dict[str, Any] | None:
        """Every write of this cycle is conditional on the status the row had when the cycle read it (I1): a row that
        advanced elsewhere meanwhile is left exactly as it is and the action is deferred to the next cycle's reading."""
        written, applied = mirror.write(row, expected=expected, insert=insert)
        if applied and written is not None:
            return written
        summary["deferred"] += 1
        count(reason)
        return None

    for action in actions:
        previous = mirrored.get(action.episode_key, {})
        if action.kind == "DISPOSITION":
            if previous.get("status") != "AWAITING_DISPOSITION":
                base = base_row(action.record, previous.get("market")) if action.record else {}
                if write_or_defer({**previous, **base, "status": "AWAITING_DISPOSITION", "reason": action.reason, "claim_token": None},
                                  expected=_observed(previous), insert=not previous) is None:
                    continue
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
            if write_or_defer({**previous, **base_row(record, previous.get("market")), "status": "BLOCKED", "reason": action.reason, "claim_token": None},
                              expected=_observed(previous), insert=not previous) is None:
                continue
            summary["blocked"] += 1
            count(action.reason)
            continue
        if action.kind == "SKIP":
            if write_or_defer({**previous, **base_row(record, previous.get("market")), "status": "SKIPPED", "reason": action.reason, "claim_token": None},
                              expected=_observed(previous), insert=not previous) is None:
                continue
            summary["skipped"] += 1
            count(action.reason)
            continue
        market = previous.get("market") or resolve_market(record.symbol)
        if market not in MARKETS:
            if write_or_defer({**previous, **base_row(record, None), "status": "SKIPPED", "reason": "MARKET_UNRESOLVED"},
                              expected=_observed(previous), insert=not previous) is None:
                continue
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
                if write_or_defer({**previous, **base_row(record, market), "status": "AWAITING_DISPOSITION", "reason": "POSITION_WITHOUT_MIRROR_COMMAND",
                                   "buy_command_id": command, "buy_command_sha": payload_sha},
                                  expected=_observed(previous), insert=not previous) is None:
                    continue
                summary["dispositions"] += 1
                count("POSITION_WITHOUT_MIRROR_COMMAND")
                continue
            quote = quotes.quote(market, record.symbol, read_clock())
            decided_at = read_clock()  # the clock after the lookup: I/O time never rejuvenates a quote (C2)
            if not quote_valid(quote, decided_at):
                summary["deferred"] += 1
                count("QUOTE_NOT_VALID")
                continue
            assert quote is not None
            fill = _paper_buy_execution(market=market, price=quote.midpoint, quantity=record.quantity, fx=fx)
            cost = fill["gross_value_usd"] + fill["fees_usd"]
            breach = _cap_breach(positions, cash, nav, symbol=record.symbol, cost_usd=cost)
            if breach is not None:
                if write_or_defer({**previous, **base_row(record, market), "status": "SKIPPED", "reason": breach, "buy_command_id": command,
                                   "buy_command_sha": payload_sha}, expected=_observed(previous), insert=not previous) is None:
                    continue
                summary["skipped"] += 1
                count(breach)
                continue
            # 1. register the command — insert, or idempotent rewrite of a row still BUY_PENDING; a row that advanced elsewhere
            #    (claimed, OPEN, ...) is read, never overwritten, and this cycle defers (I1); 2. claim it (one claimant);
            # 3. paper effect carrying the command id, with the claim verified and the receipt written inside the engine's
            #    transaction; 4. the receipt is the row itself.
            registered = write_or_defer({**previous, **base_row(record, market), "status": "BUY_PENDING", "reason": action.reason,
                                         "buy_command_id": command, "buy_command_sha": payload_sha,
                                         "command_registered_at": previous.get("command_registered_at") or decided_at},
                                        expected=("BUY_PENDING",), insert=True, reason="COMMAND_ALREADY_ADVANCED")
            if registered is None:
                continue
            claimed = mirror.claim(registered, from_status="BUY_PENDING", to_status="BUY_EXECUTING", now=decided_at)
            if claimed is None:
                summary["deferred"] += 1
                count("COMMAND_CLAIMED_ELSEWHERE")
                continue
            token = str(claimed["claim_token"])
            # No V1 score exists for a mirrored admission: the audit record is the mirror row (receipt + divergence) and the
            # trade's decision_snapshot, committed together; r2d2_decisions (V1's scored log) is not written (PG-S1).
            candidate = {"market": market, "symbol": record.symbol, "name": record.symbol, "currency": "USD",
                         "stop_price": record.stop, "price": quote.midpoint, "quote_as_of": quote.source_at}
            decision = {"mirror": MIRROR_ID, "mirror_version": MIRROR_VERSION, "mirror_epoch": mirror_epoch, "label": LABEL, "statement": STATEMENT,
                        "command_id": command, "command_sha": payload_sha, "claim_token": token, "epoch": ledger.epoch,
                        "ledger_version": ledger.version, "ledger_state_sha": ledger.state_sha, "episode_key": record.episode_key,
                        "ledger": record.buy_payload(), "ledger_maturity_at": record.maturity_at.isoformat() if record.maturity_at else None,
                        "quote": {"bid": quote.bid, "ask": quote.ask, "source_at": quote.source_at.isoformat(), "available_at": quote.available_at.isoformat(),
                                  "reference": "midpoint", "regular": quote.regular},
                        "decided_at": decided_at.isoformat(), "paper_only": True, "own_decision": False}

            def before_buy(connection: Any, claimed: dict[str, Any] = claimed, token: str = token, quote: MirrorQuote = quote) -> None:
                mirror.guard(connection, claimed, token=token, status="BUY_EXECUTING")
                if exits_only:
                    raise MirrorVetoAtEffect("EXITS_ONLY_BY_DESK_ORDER")
                if _entries_paused(repo, connection, experiment_id):
                    raise MirrorVetoAtEffect("MIRROR_ENTRIES_PAUSED_AT_EFFECT")
                if not quote_valid(quote, read_clock()):
                    raise MirrorVetoAtEffect("QUOTE_STALE_AT_EFFECT")

            def after_buy(connection: Any, trade_id: str, executed_at: datetime, claimed: dict[str, Any] = claimed, token: str = token,
                          quote: MirrorQuote = quote, record: LedgerRecord = record, fill: dict[str, Any] = fill, decided_at: datetime = decided_at,
                          reason: str = action.reason) -> None:
                mirror.receipt(connection, claimed, token=token, status="BUY_EXECUTING", updates={
                    "status": "OPEN", "reason": reason, "buy_trade_id": trade_id, "buy_at": executed_at, "buy_quantity": record.quantity,
                    "buy_fill_price": fill["fill_price"],
                    "divergence": {"buy": _divergence(record, side="BUY", quote=quote, fill_price=fill["fill_price"], quantity=record.quantity,
                                                      decided_at=decided_at, executed_at=executed_at)}})

            try:
                trade = repo.execute_trade(dict(live_experiment), cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=record.quantity,
                                           signal_price=quote.midpoint, fill_price=fill["fill_price"], fx=fx, fees=fill["fees_usd"],
                                           slippage=fill["slippage_usd"], reason=f"{LABEL}: mirror of V2 ledger admission (command {command[:12]})",
                                           decision=decision, quote_as_of=quote.source_at, before_effect=before_buy, after_effect=after_buy)
            except MirrorClaimLost as exc:  # the claim is no longer ours: nothing to release, nothing executed
                summary["deferred"] += 1
                count(str(exc))
                continue
            except MirrorVetoAtEffect as exc:
                mirror.release(claimed, token=token, from_status="BUY_EXECUTING", to_status="BUY_PENDING", reason=str(exc), now=read_clock())
                summary["deferred"] += 1
                count(str(exc))
                continue
            except ValueError as exc:
                mirror.release(claimed, token=token, from_status="BUY_EXECUTING", to_status="SKIPPED", reason=f"PAPER_ORDER_REJECTED:{exc}", now=read_clock())
                summary["skipped"] += 1
                count("PAPER_ORDER_REJECTED")
                continue
            live_experiment = repo.experiment(str(experiment["code"])) or live_experiment
            summary["buys"] += 1
            count("BUY")
        elif action.kind == "SELL":
            command = command_id(mirror_epoch, ledger.epoch, record.episode_key, "SELL")
            payload_sha = digest(record.sell_payload())
            registered_at = read_clock()
            pending = {**previous, **base_row(record, market), "status": "EXIT_PENDING", "reason": action.reason, "sell_command_id": command,
                       "sell_command_sha": payload_sha, "claim_token": None,
                       "command_registered_at": previous.get("command_registered_at") if previous.get("status") in ("EXIT_PENDING", "SELL_EXECUTING") else registered_at,
                       "ledger_exit_price": record.exit_price, "ledger_exit_at": record.exit_at, "ledger_exit_cause": record.exit_cause}
            if previous.get("status") == "SELL_EXECUTING":  # claimed by another worker: its effect or release is resolved by reading
                summary["deferred"] += 1
                count("COMMAND_CLAIMED_ELSEWHERE")
                continue
            if previous.get("status") != "EXIT_PENDING":
                # the exit obligation is durable before any quote is looked at — written only over the OPEN/BLOCKED row this cycle read
                pending = write_or_defer(pending, expected=("OPEN", "BLOCKED"), insert=False, reason="COMMAND_ALREADY_ADVANCED")
                if pending is None:
                    continue
            if existing is None:
                if write_or_defer({**pending, "status": "CLOSED", "reason": "POSITION_ABSENT_AT_EXIT"}, expected=("EXIT_PENDING",), insert=False) is None:
                    continue
                count("POSITION_ABSENT_AT_EXIT")
                continue
            mirrored_quantity = float(previous.get("buy_quantity") or 0.0)
            quantity = min(float(existing["quantity"]), mirrored_quantity) if mirrored_quantity > 0 else float(existing["quantity"])
            quote = quotes.quote(market, record.symbol, read_clock())
            decided_at = read_clock()
            if not quote_valid(quote, decided_at):
                summary["deferred"] += 1
                count("QUOTE_NOT_VALID_EXIT_PENDING")
                continue
            assert quote is not None
            claimed = mirror.claim(pending, from_status="EXIT_PENDING", to_status="SELL_EXECUTING", now=decided_at)
            if claimed is None:
                summary["deferred"] += 1
                count("COMMAND_CLAIMED_ELSEWHERE")
                continue
            token = str(claimed["claim_token"])
            fill = _paper_exit_execution(market=market, price=quote.midpoint, quantity=quantity, fx=fx)
            candidate = {"market": market, "symbol": record.symbol, "name": existing.get("name") or record.symbol, "currency": "USD",
                         "stop_price": record.stop, "price": quote.midpoint, "quote_as_of": quote.source_at}
            decision = {"mirror": MIRROR_ID, "mirror_epoch": mirror_epoch, "label": LABEL, "command_id": command, "command_sha": payload_sha,
                        "claim_token": token, "epoch": ledger.epoch, "episode_key": record.episode_key, "ledger": record.sell_payload(),
                        "quote": {"bid": quote.bid, "ask": quote.ask, "source_at": quote.source_at.isoformat(), "available_at": quote.available_at.isoformat(),
                                  "reference": "midpoint", "regular": quote.regular},
                        "decided_at": decided_at.isoformat(), "paper_only": True, "own_decision": False}

            def before_sell(connection: Any, claimed: dict[str, Any] = claimed, token: str = token, quote: MirrorQuote = quote) -> None:
                mirror.guard(connection, claimed, token=token, status="SELL_EXECUTING")
                if not quote_valid(quote, read_clock()):
                    raise MirrorVetoAtEffect("QUOTE_STALE_AT_EFFECT")

            def after_sell(connection: Any, trade_id: str, executed_at: datetime, claimed: dict[str, Any] = claimed, token: str = token,
                           quote: MirrorQuote = quote, record: LedgerRecord = record, fill: dict[str, Any] = fill, quantity: float = quantity,
                           decided_at: datetime = decided_at, reason: str = action.reason, pending: dict[str, Any] = pending) -> None:
                divergence = dict(pending.get("divergence") or {})
                divergence["sell"] = _divergence(record, side="SELL", quote=quote, fill_price=fill["fill_price"], quantity=quantity,
                                                 decided_at=decided_at, executed_at=executed_at)
                mirror.receipt(connection, claimed, token=token, status="SELL_EXECUTING", updates={
                    "status": "CLOSED", "reason": reason, "sell_trade_id": trade_id, "sell_at": executed_at, "sell_fill_price": fill["fill_price"],
                    "divergence": divergence})

            try:
                trade = repo.execute_trade(dict(live_experiment), cycle_id=cycle_id, candidate=candidate, side="SELL", quantity=quantity,
                                           signal_price=quote.midpoint, fill_price=fill["fill_price"], fx=fx, fees=fill["fees_usd"],
                                           slippage=fill["slippage_usd"], reason=f"{LABEL}: mirror of V2 ledger exit {record.exit_cause} (command {command[:12]})",
                                           decision=decision, quote_as_of=quote.source_at, before_effect=before_sell, after_effect=after_sell)
            except MirrorClaimLost as exc:
                summary["deferred"] += 1
                count(str(exc))
                continue
            except MirrorVetoAtEffect as exc:
                mirror.release(claimed, token=token, from_status="SELL_EXECUTING", to_status="EXIT_PENDING", reason=str(exc), now=read_clock())
                summary["deferred"] += 1
                count(str(exc))
                continue
            except ValueError as exc:
                mirror.release(claimed, token=token, from_status="SELL_EXECUTING", to_status="EXIT_PENDING", reason=f"PAPER_SELL_REJECTED:{exc}", now=read_clock())
                count("PAPER_SELL_REJECTED")
                continue
            live_experiment = repo.experiment(str(experiment["code"])) or live_experiment
            summary["sells"] += 1
            count("SELL")
    return summary


def _merge(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    merged = {key: first[key] + second[key] for key in ("buys", "sells", "skipped", "deferred", "dispositions", "blocked")}
    reasons = dict(first["reasons"])
    for reason, value in second["reasons"].items():
        reasons[reason] = reasons.get(reason, 0) + value
    return {**merged, "reasons": reasons}


def run_once(*, ledger_row: Mapping[str, Any], mirror_epoch: str, repo: R2D2Repository, mirror: MirrorRepository, experiment: Mapping[str, Any],
             quotes: QuoteSource, resolve_market: MarketResolver, now: datetime, activated_at: datetime, exits_only: bool = False,
             clock: Clock | None = None, fx: float = 1.0) -> dict[str, Any]:
    """One mirror cycle under the mirror-epoch lock: read confirmed facts, recover by reading, apply this cycle's transitions and
    exits, then re-read the book and the vetoes and plan the entries (I4); log the cycle."""
    if activated_at.tzinfo is None:
        raise MirrorInputError("ACTIVATION_NOT_AWARE")
    with mirror.cycle_lock(mirror_epoch) as acquired:
        if not acquired:
            return {"cycle_id": None, "mirror_epoch": mirror_epoch, "status": "CYCLE_LOCKED_ELSEWHERE", "actions": 0, "buys": 0, "sells": 0,
                    "skipped": 0, "deferred": 0, "dispositions": 0, "blocked": 0, "reasons": {"CYCLE_LOCKED_ELSEWHERE": 1}, "label": LABEL}
        ledger = read_ledger(ledger_row)
        live_experiment = repo.experiment(str(experiment["code"])) or dict(experiment)
        verify_experiment_binding(live_experiment, epoch=ledger.epoch, mirror_epoch=mirror_epoch)
        if live_experiment.get("status") == "completed":
            raise MirrorInputError("MIRROR_EXPERIMENT_CLOSED")
        recovered = reconcile(ledger=ledger, mirror_epoch=mirror_epoch, repo=repo, mirror=mirror, experiment=experiment, now=now)
        positions, cash, nav = _book(repo, live_experiment)
        marked = marked_excess(positions, cash, nav)
        experiment_id = str(experiment["id"])
        planned = plan(ledger, mirror.load(mirror_epoch, ledger.epoch, experiment_id), activated_at=activated_at, exits_only=exits_only,
                       entries_paused=bool(live_experiment.get("entries_paused")), marked=marked)
        transitions = [action for action in planned if action.kind not in ENTRY_KINDS]
        cycle_id = repo.start_cycle(experiment_id, list(MARKETS))
        try:
            summary = execute(transitions, ledger=ledger, mirror_epoch=mirror_epoch, repo=repo, mirror=mirror, experiment=experiment, cycle_id=cycle_id,
                              quotes=quotes, resolve_market=resolve_market, now=now, clock=clock, exits_only=exits_only, fx=fx)
            # Entries only after this cycle's transitions are durable: the book, the pause flag and the obligations are re-read.
            live_experiment = repo.experiment(str(experiment["code"])) or live_experiment
            positions, cash, nav = _book(repo, live_experiment)
            marked = marked_excess(positions, cash, nav)
            entries = [action for action in plan(ledger, mirror.load(mirror_epoch, ledger.epoch, experiment_id), activated_at=activated_at,
                                                 exits_only=exits_only, entries_paused=bool(live_experiment.get("entries_paused")), marked=marked)
                       if action.kind in ENTRY_KINDS]
            summary = _merge(summary, execute(entries, ledger=ledger, mirror_epoch=mirror_epoch, repo=repo, mirror=mirror, experiment=experiment,
                                              cycle_id=cycle_id, quotes=quotes, resolve_market=resolve_market, now=now, clock=clock,
                                              exits_only=exits_only, fx=fx))
            actions = transitions + entries
        except Exception as exc:
            repo.finish_cycle(cycle_id, "failed", len(ledger.records), len(planned), 0, error=type(exc).__name__, metadata={"mirror": MIRROR_ID, "label": LABEL})
            raise
        # PG-S2: r2d2_cycles only admits running/succeeded/partial/failed/market_closed/scheduled. A cycle whose orders were all
        # executed or deferred by rule is `succeeded`; one where the paper engine rejected an order or a row was blocked is `partial`.
        cycle_status = "partial" if (summary["blocked"] or any(reason.startswith("PAPER_") for reason in summary["reasons"])) else "succeeded"
        repo.finish_cycle(cycle_id, cycle_status, len(ledger.records), len(actions), summary["buys"] + summary["sells"],
                          metadata={"mirror": MIRROR_ID, "label": LABEL, "mirror_epoch": mirror_epoch, "epoch": ledger.epoch,
                                    "ledger_version": ledger.version, "ledger_state_sha": ledger.state_sha, "vetoed": ledger.vetoed,
                                    "data_gate_blocked": ledger.data_gate_blocked, "source_vetoes": list(ledger.source_vetoes),
                                    "marked_excess": marked, "exits_only": exits_only, **recovered, **summary})
        return {"cycle_id": cycle_id, "cycle_status": cycle_status, "epoch": ledger.epoch, "mirror_epoch": mirror_epoch,
                "ledger_version": ledger.version, "ledger_state_sha": ledger.state_sha, "vetoed": ledger.vetoed,
                "data_gate_blocked": ledger.data_gate_blocked, "terminal_reasons": list(ledger.terminal_reasons),
                "source_vetoes": list(ledger.source_vetoes), "marked_excess": marked, "actions": len(actions), **recovered, **summary,
                "status": "COMPLETED", "label": LABEL}


# ---------------------------------------------------------------- publication (aggregates only; never evidence)

def public_summary(*, repo: R2D2Repository, mirror: MirrorRepository, experiment: Mapping[str, Any], mirror_epoch: str, epoch: str,
                   terminal_reasons: Iterable[str] = (), source_vetoes: Iterable[str] = (), now: datetime | None = None) -> dict[str, Any]:
    """Daily public aggregates of the mirror. No symbols, no episode keys, no statistical verdict."""
    clock_now = now or _utc_now()
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

    return {"schema": "R2D2_V2_MIRROR_PUBLIC_SUMMARY_V4", "label": LABEL, "statement": STATEMENT, "is_evidence": False,
            "mirror": MIRROR_ID, "mirror_version": MIRROR_VERSION, "mirror_epoch": mirror_epoch, "experiment_code": live_experiment["code"],
            "mirrored_epoch": epoch, "as_of": clock_now.isoformat(), "nav_paper_usd": round(nav, 2), "cash_usd": round(cash, 2),
            "open_positions": len(positions), "marked_excess": marked_excess(positions, cash, nav),
            "status_counts": {status: sum(1 for r in rows if r.get("status") == status) for status in STATUSES},
            "orders_today": sum(1 for r in rows if _day(r.get("buy_at"))) + sum(1 for r in rows if _day(r.get("sell_at"))),
            "divergence_buy": {"mean_price_bps": _mean(buys, "price_diff_bps"), "mean_latency_seconds": _mean(buys, "latency_seconds"), "count": len(buys)},
            "divergence_sell": {"mean_price_bps": _mean(sells, "price_diff_bps"), "mean_latency_seconds": _mean(sells, "latency_seconds"), "count": len(sells)},
            "active_vetoes": sorted(set(terminal_reasons) | set(source_vetoes)), "entries_paused": bool(live_experiment.get("entries_paused")),
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
    initial_session: date
    receipt_sha: str

    @classmethod
    def verify(cls, data: bytes, expected_sha: str, *, build_sha: str, now: datetime) -> "MirrorRelease":
        """The receipt names its first mirrored session; the cursor is at or before that session's official open (a real XNYS
        session), the publication is strictly before that open, and the three signatures and pins are present (C4)."""
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
        declared = body.get("initial_session")
        try:
            session_day = date.fromisoformat(declared) if isinstance(declared, str) else None
        except ValueError:
            session_day = None
        if session_day is None:
            raise MirrorInputError("MIRROR_RELEASE_INITIAL_SESSION_MISSING")
        if session_day != cursor.astimezone(NEW_YORK).date():
            raise MirrorInputError("MIRROR_RELEASE_INITIAL_SESSION_MISMATCH")
        bounds = session_bounds(session_day)
        if bounds is None:
            raise MirrorInputError("MIRROR_RELEASE_CURSOR_NOT_A_SESSION")
        if cursor > bounds[0]:
            raise MirrorInputError("MIRROR_RELEASE_CURSOR_AFTER_OPEN")  # the cursor is at (or before) the official open of the first mirrored session
        if published >= bounds[0]:
            raise MirrorInputError("MIRROR_RELEASE_PUBLISHED_NOT_BEFORE_OPEN")
        if cursor > now:
            raise MirrorInputError("MIRROR_RELEASE_NOT_YET_ACTIVE")
        return cls(mirror_epoch, epoch, code, str(body["code_revision"]), review, order, published, cursor, session_day, receipt_sha)


# ---------------------------------------------------------------- production adapters

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
    """Worker loop. OFF unless enabled; the pinned release is verified BEFORE any database initialization and re-verified every cycle."""
    if os.environ.get("C3PO_R2D2_V2_MIRROR_ENABLED", "").lower() != "true":
        print('{"status":"OFF","reason":"C3PO_R2D2_V2_MIRROR_ENABLED is not true"}')
        return 0
    import importlib

    from .config import get_settings

    try:  # the shadow store ships with the V2 generator (PR #383); without it there is no ledger to mirror
        PostgresShadowStore = importlib.import_module("app.r2d2_v2_store").PostgresShadowStore
    except ImportError as exc:
        raise MirrorInputError("SHADOW_STORE_MODULE_MISSING") from exc

    settings = get_settings()
    release_path = Path(getattr(settings, "r2d2_v2_mirror_release_file", ""))
    expected_sha = str(getattr(settings, "r2d2_v2_mirror_release_sha", ""))
    epoch = str(getattr(settings, "r2d2_v2_mirror_epoch", ""))
    code = str(getattr(settings, "r2d2_v2_mirror_experiment_code", DEFAULT_EXPERIMENT_CODE))
    cycle_seconds = float(getattr(settings, "r2d2_v2_mirror_cycle_seconds", 20))
    exits_only = bool(getattr(settings, "r2d2_v2_mirror_exits_only", False))
    registry_root = Path(getattr(settings, "r2d2_v2_mirror_registry_root", ""))
    release = MirrorRelease.verify(release_path.read_bytes(), expected_sha, build_sha=settings.build_sha, now=_utc_now())
    if release.epoch != epoch or release.experiment_code != code:
        raise MirrorInputError("MIRROR_RELEASE_DOES_NOT_MATCH_SETTINGS")
    token = str(getattr(settings, "eodhd_api_token", "")).strip()
    if not token:
        raise MirrorInputError("QUOTE_FEED_TOKEN_MISSING")
    database = Database(settings)
    database.initialize()
    repo = R2D2Repository(database)
    mirror = MirrorRepository(database)
    experiment = ensure_mirror_experiment(repo, code=code, epoch=epoch, mirror_epoch=release.mirror_epoch)
    store = PostgresShadowStore(database.connection)
    tape = QuoteTape()
    wanted: set[str] = set()
    stop = threading.Event()
    threading.Thread(target=lambda: asyncio.run(stream_quotes(tape, token, lambda: set(wanted), stop)), name="r2d2-v2-mirror-quotes", daemon=True).start()
    resolve = RegistryMarketResolver(registry_root)
    logger.info("%s worker started: mirror epoch %s, shadow epoch %s, experiment %s (%s)", MIRROR_ID, release.mirror_epoch, epoch, code, LABEL)
    while True:
        started = time_module.monotonic()
        try:
            now = _utc_now()
            MirrorRelease.verify(release_path.read_bytes(), expected_sha, build_sha=settings.build_sha, now=now)
            row = store.read(epoch)
            if row is None:
                logger.warning("shadow epoch %s not found; mirror idle", epoch)
            else:
                wanted.update(record.symbol for record in read_ledger(row).records if record.kind == "PORTFOLIO")
                result = run_once(ledger_row=row, mirror_epoch=release.mirror_epoch, repo=repo, mirror=mirror, experiment=experiment, quotes=tape,
                                  resolve_market=resolve, now=now, activated_at=release.initial_cursor_at, exits_only=exits_only, clock=_utc_now)
                logger.info("mirror cycle %s", json.dumps(result, default=str, sort_keys=True))
        except MirrorInputError as exc:
            logger.error("mirror halted this cycle: %s", exc)
        except Exception:
            logger.exception("unhandled mirror error")
        time_module.sleep(max(0.0, cycle_seconds - (time_module.monotonic() - started)))


if __name__ == "__main__":
    raise SystemExit(main())
