"""Codex #387 round 2, I1: the PostgreSQL proof that an in-flight paper effect and a claim release never produce two effects.

Runs only against a controlled, disposable PostgreSQL named by C3PO_R2D2_V2_MIRROR_TEST_DATABASE_URL (never production):
the schema is created by the repository's own migrations (db/*.sql, including 047), the effect runs the real
`R2D2Repository.execute_trade` SQL path with the mirror's transaction hooks, and the concurrent release runs the real
`MirrorRepository.release` compare-and-set on its own connection.
"""
from __future__ import annotations

import os
import threading
from datetime import timedelta
from uuid import uuid4

import pytest

from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2Repository
from app.r2d2_v2_mirror import (MirrorClaimLost, MirrorRepository, command_id, digest, ensure_mirror_experiment, read_ledger)
from tests.test_r2d2_v2_mirror import EPOCH, MIRROR_EPOCH, T0, _record, _row

DSN = os.environ.get("C3PO_R2D2_V2_MIRROR_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN or "production" in DSN or "54.233.250.210" in DSN, reason="controlled PostgreSQL not configured")


def _fixture():
    settings = Settings(database_url=DSN, r2d2_start_date="2026-09-14", r2d2_checkpoint_days=90, r2d2_starting_capital_usd=1_000_000.0)
    database = Database(settings)
    database.initialize()
    repo = R2D2Repository(database)
    mirror = MirrorRepository(database)
    code = f"R2D2-V2-MIRROR-PG-{uuid4().hex[:8]}"
    mirror_epoch = f"{MIRROR_EPOCH}-{uuid4().hex[:8]}"
    experiment = ensure_mirror_experiment(repo, code=code, epoch=EPOCH, mirror_epoch=mirror_epoch, starting_capital=1_000_000.0, now=T0)
    record = read_ledger(_row([_record("AAA", quantity=10.0)])).records[0]
    command = command_id(mirror_epoch, EPOCH, record.episode_key, "BUY")
    row = mirror.upsert({"mirror_epoch": mirror_epoch, "epoch": EPOCH, "episode_key": record.episode_key, "symbol": "AAA", "market": "NASDAQ",
                         "experiment_id": experiment["id"], "status": "BUY_PENDING", "reason": "pg-proof", "buy_command_id": command,
                         "buy_command_sha": digest(record.buy_payload()), "command_registered_at": T0})
    claimed = mirror.claim(row, from_status="BUY_PENDING", to_status="BUY_EXECUTING", now=T0)
    assert claimed is not None
    return repo, mirror, experiment, record, command, claimed, mirror_epoch


def _effect(repo, mirror, experiment, record, command, claimed, *, before_extra=None):
    token = str(claimed["claim_token"])

    def before(connection) -> None:
        mirror.guard(connection, claimed, token=token, status="BUY_EXECUTING")
        if before_extra is not None:
            before_extra()

    def after(connection, trade_id, executed_at) -> None:
        mirror.receipt(connection, claimed, token=token, status="BUY_EXECUTING",
                       updates={"status": "OPEN", "reason": "pg-proof", "buy_trade_id": trade_id, "buy_at": executed_at,
                                "buy_quantity": record.quantity, "buy_fill_price": 50.05})

    candidate = {"market": "NASDAQ", "symbol": "AAA", "name": "AAA", "currency": "USD", "stop_price": 48.0, "price": 50.0,
                 "quote_as_of": T0, "risk_score": None}
    cycle_id = repo.start_cycle(str(experiment["id"]), ["NASDAQ", "NYSE"])
    return repo.execute_trade(dict(experiment), cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=record.quantity, signal_price=50.0,
                              fill_price=50.05, fx=1.0, fees=0.2, slippage=0.5, reason="pg proof", quote_as_of=T0,
                              decision={"command_id": command, "command_sha": digest(record.buy_payload()), "claim_token": token},
                              before_effect=before, after_effect=after)


def _scalar(repo, sql: str, params: tuple):
    with repo.database.connection() as connection:
        row = connection.execute(sql, params).fetchone()
    assert row is not None
    return row[0]


def _trades(repo, experiment, command) -> int:
    return int(_scalar(repo, "SELECT count(*) FROM r2d2_trades WHERE experiment_id=%s AND decision_snapshot->>'command_id'=%s", (experiment["id"], command)))


def test_release_waits_for_the_in_flight_effect_and_then_fails_so_the_effect_is_never_repeated() -> None:
    repo, mirror, experiment, record, command, claimed, mirror_epoch = _fixture()
    entered, gate = threading.Event(), threading.Event()
    outcome: dict = {}

    def in_flight():
        try:
            outcome["trade"] = _effect(repo, mirror, experiment, record, command, claimed,
                                       before_extra=lambda: (entered.set(), gate.wait(timeout=30)))
        except Exception as exc:  # pragma: no cover - surfaced by the assertions below
            outcome["error"] = exc

    worker = threading.Thread(target=in_flight)
    worker.start()
    assert entered.wait(15)  # the effect holds the mirror row lock and the experiment row lock, uncommitted
    # A second worker (own connections) reads no trade for the command: with READ COMMITTED the in-flight effect is invisible.
    assert mirror.trade_for_command(repo, str(experiment["id"]), command) is None
    released: dict = {}

    def release():
        released["ok"] = mirror.release(claimed, token=str(claimed["claim_token"]), from_status="BUY_EXECUTING", to_status="BUY_PENDING",
                                        reason="CLAIM_RELEASED_NO_EFFECT", now=T0 + timedelta(seconds=1))

    releaser = threading.Thread(target=release)
    releaser.start()
    releaser.join(timeout=3)
    assert releaser.is_alive()  # the compare-and-set is blocked by the row lock of the in-flight effect: it cannot reopen the command
    gate.set()
    worker.join(timeout=30)
    releaser.join(timeout=30)
    assert "error" not in outcome and released["ok"] is False  # the effect committed first; the CAS re-evaluated its predicate and matched nothing
    final = mirror.load(mirror_epoch, EPOCH, str(experiment["id"]))[record.episode_key]
    assert final["status"] == "OPEN" and final["buy_trade_id"] == outcome["trade"]["id"] and final["claim_token"] is None
    assert _trades(repo, experiment, command) == 1
    assert mirror.trade_for_command(repo, str(experiment["id"]), command)["id"] == outcome["trade"]["id"]  # type: ignore[index]


def test_a_claim_released_before_the_effect_locks_the_row_aborts_the_effect_without_a_trade() -> None:
    repo, mirror, experiment, record, command, claimed, mirror_epoch = _fixture()
    assert mirror.release(claimed, token=str(claimed["claim_token"]), from_status="BUY_EXECUTING", to_status="BUY_PENDING",
                          reason="CLAIM_RELEASED_NO_EFFECT", now=T0 + timedelta(seconds=1)) is True
    with pytest.raises(MirrorClaimLost):
        _effect(repo, mirror, experiment, record, command, claimed)
    final = mirror.load(mirror_epoch, EPOCH, str(experiment["id"]))[record.episode_key]
    assert final["status"] == "BUY_PENDING" and final["buy_trade_id"] is None and _trades(repo, experiment, command) == 0
    cash = _scalar(repo, "SELECT cash_balance FROM r2d2_experiments WHERE id=%s", (experiment["id"],))
    assert float(cash) == 1_000_000.0  # the aborted transaction left no trace: no position, no cash movement
