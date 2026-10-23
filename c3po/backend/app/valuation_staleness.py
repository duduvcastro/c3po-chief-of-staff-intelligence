"""The causal reader of migration 053 (``valuation_tp_staleness``) for the Decisor V1.

The as-filed front (``valuation_asfiled``: the trigger ``evaluate_us_filings`` and its store ``TpStalenessStore``) WRITES the
marks; this module only READS them, at a decision's clock. It lives apart from ``valuation_asfiled.py`` because that file
is a producer file the US point-in-time backtest hashes (``valuation_pit_rerun.IMPLEMENTATION_FILES``): the decisor's reader
must never move it.

* ``staleness_table_present`` — migration 053 applied where the database reads (PostgreSQL ``to_regclass``; in memory, the
  store's list on the ``Database``, present once a writer created it). Never creates anything.
* ``rows_known_at`` — the marks a reader at D could have read: ``recorded_at`` ≤ D and — PostgreSQL — ``created_at`` ≤ D −
  margin (the insert's transaction clock): a mark a later pass wrote, a pass replayed with a past clock, or a pass that
  straddles D and inserts after it never reaches a decision taken at D.
* ``us_staleness_at`` — per (filing, symbol) the latest state among them (a tie, which the trigger never writes, resolves to
  the stricter state) and the pairs still ``stale``.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .database import Database
from .statement_vintages import utc_instant
from .valuation_asfiled import CLEARED, STALE, UNTRACKED, _STALENESS_KEYS

STALENESS_TABLE = "valuation_tp_staleness"
# the order of the states of one (filing, symbol) when two marks share a recorded_at — the trigger never writes that (one
# mark per pair per pass); should it happen, the stricter state is the one a decision reads
_STATE_ORDER = {UNTRACKED: 0, CLEARED: 1, STALE: 2}


def staleness_table_present(database: Database) -> bool:
    """Whether migration 053 is applied where ``database`` reads. Never creates anything."""
    if not database.database_url:
        return isinstance(getattr(database, "_valuation_tp_staleness", None), list)
    with database.connection() as connection:
        found = connection.execute("SELECT to_regclass(%s)::text", (STALENESS_TABLE,)).fetchone()
    return bool(found and found[0])


def rows_known_at(database: Database, at: datetime, *, margin_seconds: int = 0) -> list[dict[str, Any]]:
    """The marks a reader at ``at`` could have read (see the module text). The memory double keeps no ``created_at`` (a
    test row may carry one: then it is applied too)."""
    clock = utc_instant(at)
    inserted_by = clock - timedelta(seconds=margin_seconds)
    if not database.database_url:
        return [
            dict(row) for row in getattr(database, "_valuation_tp_staleness", None) or []
            if utc_instant(row["recorded_at"]) <= clock and (row.get("created_at") is None or utc_instant(row["created_at"]) <= inserted_by)
        ]
    with database.connection() as connection:
        rows = connection.execute(
            f"SELECT {', '.join(key if key != 'id' else 'id::text' for key in _STALENESS_KEYS)} FROM {STALENESS_TABLE} "
            "WHERE recorded_at <= %s AND created_at <= %s ORDER BY recorded_at, doc_id, symbol, state",
            (clock, inserted_by),
        ).fetchall()
    return [dict(zip(_STALENESS_KEYS, row)) for row in rows]


def us_staleness_at(database: Database, at: datetime, *, margin_seconds: int = 0) -> dict[str, Any]:
    """The state of every (filing, symbol) AS KNOWN AT ``at``: ``{"status": "ok", "known_at", "marks_known",
    "latest_recorded_at", "pending": {symbol: [mark, …]}}`` — the full marks, oldest acceptance first — or
    ``{"status": "unavailable", "detail"}`` when the table is absent (migration 053 not applied). A ``cleared`` written
    after ``at`` never reaches it: a re-run of an old night reads what that night read. A read that fails raises."""
    clock = utc_instant(at)
    if not staleness_table_present(database):
        return {"status": "unavailable", "known_at": clock.isoformat(), "detail": f"{STALENESS_TABLE} absent (migration 053 not applied)"}
    known = rows_known_at(database, clock, margin_seconds=margin_seconds)
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
