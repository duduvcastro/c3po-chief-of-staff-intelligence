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
from app.r2d2_v2_mirror import (Action, MirrorClaimLost, MirrorRepository, command_id, digest, ensure_mirror_experiment, execute, read_ledger,
                                run_once)
from tests.test_r2d2_v2_mirror import ACTIVATED, EPOCH, MIRROR_EPOCH, T0, FakeQuotes, _record, _resolve, _row

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


def _bare_fixture():
    settings = Settings(database_url=DSN, r2d2_start_date="2026-09-14", r2d2_checkpoint_days=90, r2d2_starting_capital_usd=1_000_000.0)
    database = Database(settings)
    database.initialize()
    repo = R2D2Repository(database)
    mirror = MirrorRepository(database)
    code = f"R2D2-V2-MIRROR-PG-{uuid4().hex[:8]}"
    mirror_epoch = f"{MIRROR_EPOCH}-{uuid4().hex[:8]}"
    experiment = ensure_mirror_experiment(repo, code=code, epoch=EPOCH, mirror_epoch=mirror_epoch, starting_capital=1_000_000.0, now=T0)
    return repo, mirror, experiment, mirror_epoch


def _run(repo, mirror, experiment, mirror_epoch, ledger, quotes, now):
    return run_once(ledger_row=ledger, mirror_epoch=mirror_epoch, repo=repo, mirror=mirror, experiment=experiment, quotes=quotes,
                    resolve_market=_resolve, now=now, activated_at=ACTIVATED)


def test_run_once_completes_a_full_buy_then_sell_cycle_in_postgres() -> None:
    # Codex #387 round 3, PG-S1/PG-S2: the whole cycle on the real schema — cycle rows finish with a supported status, the
    # audit record needs no V1 score (no r2d2_decisions row), receipts and trades are committed together.
    repo, mirror, experiment, mirror_epoch = _bare_fixture()
    ledger = _row([_record("AAA", quantity=10.0)])
    result = _run(repo, mirror, experiment, mirror_epoch, ledger, FakeQuotes({"AAA": 50.0}), T0)
    assert result["buys"] == 1 and result["status"] == "COMPLETED" and result["cycle_status"] == "succeeded"
    assert _scalar(repo, "SELECT status FROM r2d2_cycles WHERE id=%s", (result["cycle_id"],)) == "succeeded"
    assert int(_scalar(repo, "SELECT count(*) FROM r2d2_decisions WHERE experiment_id=%s", (experiment["id"],))) == 0
    command = command_id(mirror_epoch, EPOCH, "ep-AAA", "BUY")
    assert _trades(repo, experiment, command) == 1
    row = mirror.load(mirror_epoch, EPOCH, str(experiment["id"]))["ep-AAA"]
    assert row["status"] == "OPEN" and row["claim_token"] is None and row["buy_trade_id"]
    assert float(_scalar(repo, "SELECT quantity FROM r2d2_positions WHERE experiment_id=%s AND symbol='AAA'", (experiment["id"],))) == 10.0
    exit_at = T0 + timedelta(hours=1)
    closed = _row([_record("AAA", status="CLOSED", exit_cause="TARGET", exit_price=54.2, exit_at=exit_at, quantity=10.0)], version=4)
    result = _run(repo, mirror, experiment, mirror_epoch, closed, FakeQuotes({"AAA": 54.0}), exit_at + timedelta(seconds=5))
    assert result["sells"] == 1 and result["cycle_status"] == "succeeded"
    assert _scalar(repo, "SELECT status FROM r2d2_cycles WHERE id=%s", (result["cycle_id"],)) == "succeeded"
    row = mirror.load(mirror_epoch, EPOCH, str(experiment["id"]))["ep-AAA"]
    assert row["status"] == "CLOSED" and row["sell_trade_id"] and "buy" in row["divergence"] and "sell" in row["divergence"]
    assert int(_scalar(repo, "SELECT count(*) FROM r2d2_positions WHERE experiment_id=%s", (experiment["id"],))) == 0
    assert int(_scalar(repo, "SELECT count(*) FROM r2d2_decisions WHERE experiment_id=%s", (experiment["id"],))) == 0
    # a repeated cycle over the same ledger has nothing to do and still finishes with a supported status
    result = _run(repo, mirror, experiment, mirror_epoch, closed, FakeQuotes({"AAA": 54.0}), exit_at + timedelta(seconds=10))
    assert result["actions"] == 0 and _scalar(repo, "SELECT status FROM r2d2_cycles WHERE id=%s", (result["cycle_id"],)) == "succeeded"


def test_a_worker_suspended_before_registration_never_reopens_a_command_executed_meanwhile_in_postgres() -> None:
    # Codex #387 round 3, I1: A reads no row and looks a quote up; while A is suspended, B registers, claims and commits the
    # effect (OPEN). A's registration then reads-and-compares on the real INSERT ... ON CONFLICT ... WHERE status = ANY(...):
    # the OPEN row is not touched, A defers, one trade of quantity 10 exists for a command of 10.
    repo, mirror, experiment, mirror_epoch = _bare_fixture()
    ledger = _row([_record("AAA", quantity=10.0)])
    view = read_ledger(ledger)
    record = view.records[0]
    entered, gate = threading.Event(), threading.Event()
    outcome: dict = {}

    def suspended(symbol: str) -> None:
        entered.set()
        gate.wait(timeout=30)

    def worker_a() -> None:
        try:
            outcome["result"] = _run(repo, mirror, experiment, mirror_epoch, ledger, FakeQuotes({"AAA": 50.0}, hook=suspended), T0)
        except Exception as exc:  # pragma: no cover - surfaced below
            outcome["error"] = exc

    thread = threading.Thread(target=worker_a)
    thread.start()
    assert entered.wait(15)
    summary_b = execute([Action("BUY", record, "LEDGER_ADMISSION_RECORDED", record.episode_key)], ledger=view, mirror_epoch=mirror_epoch, repo=repo,
                        mirror=mirror, experiment=experiment, cycle_id=repo.start_cycle(str(experiment["id"]), ["NASDAQ", "NYSE"]),
                        quotes=FakeQuotes({"AAA": 50.0}), resolve_market=_resolve, now=T0)
    assert summary_b["buys"] == 1
    gate.set()
    thread.join(timeout=60)
    assert "error" not in outcome
    result_a = outcome["result"]
    assert result_a["buys"] == 0 and result_a["reasons"] == {"COMMAND_ALREADY_ADVANCED": 1}
    command = command_id(mirror_epoch, EPOCH, "ep-AAA", "BUY")
    assert _trades(repo, experiment, command) == 1
    row = mirror.load(mirror_epoch, EPOCH, str(experiment["id"]))["ep-AAA"]
    assert row["status"] == "OPEN" and row["claim_token"] is None
    assert float(_scalar(repo, "SELECT quantity FROM r2d2_positions WHERE experiment_id=%s AND symbol='AAA'", (experiment["id"],))) == 10.0
    assert float(_scalar(repo, "SELECT cash_balance FROM r2d2_experiments WHERE id=%s", (experiment["id"],))) < 1_000_000.0
