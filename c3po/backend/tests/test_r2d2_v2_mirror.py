from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import r2d2_v2_mirror as mirror_module
from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2Repository
from app.r2d2_v2_mirror import (
    LABEL, Action, MirrorInputError, MirrorQuote, MirrorRelease, MirrorRepository, command_id, ensure_mirror_experiment, marked_excess, plan,
    public_summary, quantity_precision_ok, quote_valid, read_ledger, run_once,
)

EPOCH = "R2D2-V2-SHADOW-TEST"
MIRROR_EPOCH = "R2D2-V2-MIRROR-TEST-1"
T0 = datetime(2026, 9, 14, 14, 1, tzinfo=timezone.utc)
ACTIVATED = datetime(2026, 9, 14, 13, 30, tzinfo=timezone.utc)  # 09:30 New York: the open of the first mirrored session
NY = mirror_module.NEW_YORK


def _record(symbol: str, *, status: str = "OPEN", quantity: float = 100.0, opened_at: datetime = T0, kind: str = "PORTFOLIO",
            exit_cause: str | None = None, exit_price: float | None = None, exit_at: datetime | None = None) -> dict:
    return {"episode_key": f"ep-{symbol}", "instrument_key": f"US:{symbol}", "session": "2026-09-14", "opened_at": opened_at.isoformat(),
            "maturity_at": (opened_at + timedelta(days=14)).isoformat(), "arm": "ELIGIBLE", "kind": kind,
            "geometry": {"P": 50.0, "B": 50.05, "C": 50.09, "S": 48.0, "T": 54.2, "R_unit": 2.09}, "q0": quantity, "quantity": quantity,
            "status": status, "exit_cause": exit_cause, "exit_price": exit_price, "exit_at": exit_at.isoformat() if exit_at else None,
            "exit_available_at": (exit_at + timedelta(seconds=1)).isoformat() if exit_at else None,
            "exit_interval": [exit_at.isoformat(), (exit_at + timedelta(minutes=1)).isoformat()] if exit_at else None}


def _row(records: list[dict], *, terminal: list[str] | None = None, mode: str = "CERTIFIED", epoch: str = EPOCH, version: int = 3,
         issues: dict | None = None) -> dict:
    state = {"epoch": epoch, "mode": mode, "active_data_issues": issues or {},
             "ledger": {"session": "2026-09-14", "terminal_reasons": terminal or [], "portfolio": {r["episode_key"]: r for r in records}, "research": {}}}
    return {"state": state, "state_sha": hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest(), "version": version}


class FakeQuotes:
    def __init__(self, mids: dict[str, float], *, status: str = "live", age: float = 1.0, spread: float = 0.02) -> None:
        self.mids, self.status, self.age, self.spread = mids, status, age, spread

    def quote(self, market: str, symbol: str, now: datetime) -> MirrorQuote | None:
        mid = self.mids.get(symbol)
        if mid is None:
            return None
        return MirrorQuote(mid - self.spread / 2, mid + self.spread / 2, now - timedelta(seconds=self.age), now - timedelta(seconds=self.age / 2), self.status)


def _setup(capital: float = 1_000_000.0):
    settings = Settings(database_url="", r2d2_start_date="2026-09-14", r2d2_checkpoint_days=90, r2d2_starting_capital_usd=capital)
    database = Database(settings)
    repo = R2D2Repository(database)
    memory = MirrorRepository(database)
    experiment = ensure_mirror_experiment(repo, code="R2D2-V2-MIRROR-001", epoch=EPOCH, mirror_epoch=MIRROR_EPOCH, starting_capital=capital, now=T0)
    return repo, memory, experiment


def _resolve(symbol: str) -> str | None:
    return {"AAA": "NASDAQ", "BBB": "NYSE", "CCC": "NASDAQ", "DDD": "NYSE"}.get(symbol)


def _run(repo, memory, experiment, ledger, quotes, now, **kwargs):
    return run_once(ledger_row=ledger, mirror_epoch=MIRROR_EPOCH, repo=repo, mirror=memory, experiment=experiment, quotes=quotes,
                    resolve_market=_resolve, now=now, activated_at=ACTIVATED, **kwargs)


def _rows(memory, experiment):
    return memory.load(MIRROR_EPOCH, EPOCH, experiment["id"])


def test_read_ledger_accepts_only_certified_shadow_epochs_and_carries_the_data_gate() -> None:
    view = read_ledger(_row([_record("AAA"), _record("BBB", kind="RESEARCH", quantity=1.0)], terminal=["NAV_FLOOR"]))
    assert view.epoch == EPOCH and view.version == 3 and view.vetoed and view.terminal_reasons == ("NAV_FLOOR",) and view.data_gate_blocked is False
    assert [r.symbol for r in view.records] == ["AAA", "BBB"] and view.records[0].kind == "PORTFOLIO" and view.records[1].kind == "RESEARCH"
    closed = read_ledger(_row([_record("AAA", status="CLOSED", exit_cause="TARGET", exit_price=54.2, exit_at=T0)])).records[0]
    assert closed.exit_interval == (T0.isoformat(), (T0 + timedelta(minutes=1)).isoformat())  # intervals stay intervals
    # the collector's data gate (#383 _admission_block): an active, unrestored issue of the current session vetoes the mirror too
    gate = _row([_record("AAA")], issues={"gap-1": {"session": "2026-09-14", "instrument": "*", "at": T0.isoformat(), "restored_instruments": []}})
    assert read_ledger(gate).data_gate_blocked is True and read_ledger(gate).vetoed is True
    restored = _row([_record("AAA")], issues={"gap-1": {"session": "2026-09-14", "instrument": "US:AAA", "at": T0.isoformat(), "restored_instruments": ["US:AAA"]}})
    assert read_ledger(restored).data_gate_blocked is False
    other_session = _row([_record("AAA")], issues={"gap-1": {"session": "2026-09-11", "instrument": "*", "at": T0.isoformat(), "restored_instruments": []}})
    assert read_ledger(other_session).data_gate_blocked is False
    for bad, code in [(_row([], mode="DIAGNOSTIC"), "SHADOW_MODE_NOT_CERTIFIED"), (_row([], epoch="R2D2-V2-DIAG-1"), "SHADOW_EPOCH_NOT_CERTIFIED"),
                      ({"state": {"epoch": EPOCH, "mode": "CERTIFIED", "ledger": None}, "state_sha": "0" * 64, "version": 1}, "SHADOW_LEDGER_MISSING"),
                      ({**_row([]), "version": "1"}, "SHADOW_VERSION_INVALID"),
                      (_row([_record("AAA", status="CLOSED", exit_cause="WEIRD", exit_price=51.0, exit_at=T0)]), "LEDGER_EXIT_CAUSE_INVALID"),
                      (_row([{**_record("AAA"), "opened_at": "2026-09-14T14:01:00"}]), "LEDGER_TIMESTAMP_NAIVE"),
                      (_row([{**_record("AAA"), "quantity": 0}]), "LEDGER_NUMBER_INVALID")]:
        with pytest.raises(MirrorInputError, match=code):
            read_ledger(bad)


def test_plan_applies_every_veto_before_any_unexecuted_buy_and_keeps_exit_obligations() -> None:
    exit_at = T0 + timedelta(hours=2)
    records = [_record("AAA"), _record("BBB", opened_at=ACTIVATED - timedelta(minutes=1)), _record("CCC", kind="RESEARCH", quantity=1.0),
               _record("DDD", status="CLOSED", exit_cause="TARGET", exit_price=54.2, exit_at=exit_at),
               _record("EEE", status="CLOSED", exit_cause="STOP", exit_price=48.0, exit_at=exit_at),
               _record("FFF", status="CLOSED", exit_cause="TIME", exit_price=50.0, exit_at=exit_at), _record("GGG", quantity=1.123456789)]
    view = read_ledger(_row(records))
    no_exits = {"ep-FFF": {"status": "BUY_PENDING", "buy_command_sha": None}}
    actions = {a.episode_key: a for a in plan(view, no_exits, activated_at=ACTIVATED)}
    assert set(actions) == {"ep-AAA", "ep-BBB", "ep-DDD", "ep-EEE", "ep-FFF", "ep-GGG"}  # research never mirrored
    assert actions["ep-AAA"].kind == "BUY" and actions["ep-BBB"] == Action("SKIP", view.records[1], "OPENED_BEFORE_INITIAL_CURSOR", "ep-BBB")
    assert actions["ep-DDD"].reason == "CLOSED_BEFORE_MIRROR" and actions["ep-EEE"].reason == "CLOSED_BEFORE_MIRROR"
    assert actions["ep-FFF"].kind == "SKIP" and actions["ep-FFF"].reason == "CLOSED_BEFORE_MIRROR_EXECUTION"  # BUY pending, virtual already closed
    assert actions["ep-GGG"] == Action("SKIP", view.records[6], "QUANTITY_PRECISION_INVALID", "ep-GGG")  # nine decimals: never rounded silently
    # I3: a registered BUY not yet executed obeys every veto in force (exits-only, pause, ledger veto, data gate, marked excess, exit obligation)
    pending = {"ep-AAA": {"status": "BUY_PENDING", "buy_command_sha": None}}
    for kwargs, reason in [({"exits_only": True}, "EXITS_ONLY_BY_DESK_ORDER"), ({"entries_paused": True}, "MIRROR_ENTRIES_PAUSED"),
                           ({"marked": "MARKED_EXCESS_PER_NAME_6PCT"}, "MARKED_EXCESS_PER_NAME_6PCT")]:
        assert {a.episode_key: (a.kind, a.reason) for a in plan(view, pending, activated_at=ACTIVATED, **kwargs)}["ep-AAA"] == ("DEFER", reason)
    vetoed = plan(read_ledger(_row(records, terminal=["GAP_LOSS_LIMIT"])), pending, activated_at=ACTIVATED)
    assert {a.episode_key: (a.kind, a.reason) for a in vetoed}["ep-AAA"] == ("DEFER", "LEDGER_VETO:GAP_LOSS_LIMIT")
    gated = read_ledger(_row(records, issues={"g": {"session": "2026-09-14", "instrument": "*", "at": T0.isoformat(), "restored_instruments": []}}))
    assert {a.episode_key: (a.kind, a.reason) for a in plan(gated, pending, activated_at=ACTIVATED)}["ep-AAA"] == ("DEFER", "COLLECTION_DATA_GATE_BLOCKED")
    # I4: a SELL due this cycle, a pending exit, an episode that vanished, or a BLOCKED row holding a position all block new BUYs
    for mirrored, expected in [({"ep-DDD": {"status": "OPEN", "buy_command_sha": None}}, "EXIT_OBLIGATION_BLOCKS_BUYS"),
                               ({"ep-DDD": {"status": "EXIT_PENDING"}}, "EXIT_OBLIGATION_BLOCKS_BUYS"),
                               ({"ep-GONE": {"status": "OPEN", "buy_trade_id": "t1"}}, "EXIT_OBLIGATION_BLOCKS_BUYS"),
                               ({"ep-DDD": {"status": "BLOCKED", "buy_trade_id": "t1"}}, "EXIT_OBLIGATION_BLOCKS_BUYS")]:
        kinds = {a.episode_key: (a.kind, a.reason) for a in plan(view, mirrored, activated_at=ACTIVATED)}
        assert kinds["ep-AAA"] == ("DEFER", expected), mirrored
    kinds = {a.episode_key: (a.kind, a.reason) for a in plan(view, {"ep-DDD": {"status": "BLOCKED", "buy_trade_id": "t1"}}, activated_at=ACTIVATED)}
    assert kinds["ep-DDD"] == ("SELL", "EXIT_OBLIGATION_AFTER_BLOCK")  # the exit obligation survives the block
    kinds = {a.episode_key: (a.kind, a.reason) for a in plan(view, {"ep-GONE": {"status": "OPEN", "buy_trade_id": "t1"}}, activated_at=ACTIVATED)}
    assert kinds["ep-GONE"] == ("DISPOSITION", "EPISODE_ABSENT_FROM_LEDGER")
    # I2: a payload that differs from the registered one blocks, in every state
    changed = {"ep-AAA": {"status": "OPEN", "buy_command_sha": "0" * 64}}
    assert {a.episode_key: (a.kind, a.reason) for a in plan(view, changed, activated_at=ACTIVATED)}["ep-AAA"] == ("BLOCK", "COMMAND_PAYLOAD_CONFLICT")
    changed = {"ep-AAA": {"status": "BUY_PENDING", "buy_command_sha": "0" * 64}}
    assert {a.episode_key: (a.kind, a.reason) for a in plan(view, changed, activated_at=ACTIVATED)}["ep-AAA"] == ("BLOCK", "COMMAND_PAYLOAD_CONFLICT")
    changed = {"ep-DDD": {"status": "EXIT_PENDING", "sell_command_sha": "0" * 64}}
    assert {a.episode_key: (a.kind, a.reason) for a in plan(view, changed, activated_at=ACTIVATED)}["ep-DDD"] == ("DISPOSITION", "EXIT_COMMAND_PAYLOAD_CONFLICT")
    order = [a.kind for a in plan(view, {"ep-DDD": {"status": "OPEN", "buy_command_sha": None}}, activated_at=ACTIVATED)]
    assert order.index("SELL") < order.index("DEFER")  # exits before entries


def test_quote_validity_requires_causal_clocks_regular_bid_ask_and_ten_seconds() -> None:
    now = T0
    good = MirrorQuote(10.0, 10.02, now - timedelta(seconds=9), now - timedelta(seconds=8), "live")
    assert quote_valid(good, now)
    assert not quote_valid(MirrorQuote(10.0, 10.02, now - timedelta(seconds=11), now - timedelta(seconds=10), "live"), now)  # too old
    assert not quote_valid(MirrorQuote(10.0, 10.02, now + timedelta(seconds=1), now + timedelta(seconds=2), "live"), now)  # future
    assert not quote_valid(MirrorQuote(10.0, 10.02, now - timedelta(seconds=1), now + timedelta(seconds=1), "live"), now)  # receipt in the future
    assert not quote_valid(MirrorQuote(10.0, 10.02, now - timedelta(seconds=1), now - timedelta(seconds=2), "live"), now)  # receipt before source
    assert not quote_valid(MirrorQuote(10.0, 10.02, now, now, "delayed"), now)
    assert not quote_valid(MirrorQuote(10.05, 10.0, now, now, "live"), now)  # crossed
    assert not quote_valid(MirrorQuote(0.0, 10.0, now, now, "live"), now)
    assert not quote_valid(MirrorQuote(float("nan"), 10.0, now, now, "live"), now)
    assert not quote_valid(MirrorQuote(10.0, 10.02, datetime(2026, 9, 14, 14, 1), now, "live"), now)  # naive clock
    assert not quote_valid(None, now)
    assert good.midpoint == pytest.approx(10.01)
    assert quantity_precision_ok(10.12345678) and not quantity_precision_ok(10.123456789) and quantity_precision_ok(100.0)


def test_run_once_registers_claims_executes_and_records_factual_fill_clocks() -> None:
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.10, "BBB": 30.0})
    ledger = _row([_record("AAA"), _record("BBB", quantity=10.12345678)])
    result = _run(repo, memory, experiment, ledger, quotes, T0 + timedelta(seconds=30))
    assert result["buys"] == 2 and result["sells"] == 0 and result["label"] == LABEL and result["vetoed"] is False and result["status"] == "COMPLETED"
    positions = {row["symbol"]: row for row in repo.positions(experiment["id"])}
    assert positions["AAA"]["quantity"] == 100.0 and positions["BBB"]["quantity"] == 10.12345678  # q preserved, eight decimals
    assert positions["AAA"]["last_price_local"] == pytest.approx(50.10 * 1.001) and positions["AAA"]["stop_price_local"] == 48.0
    rows = _rows(memory, experiment)
    aaa = rows["ep-AAA"]
    assert aaa["status"] == "OPEN" and aaa["buy_command_id"] == command_id(MIRROR_EPOCH, EPOCH, "ep-AAA", "BUY") and aaa["buy_command_sha"] and aaa["claim_token"] is None
    trade = next(t for t in repo.memory["trades"] if t["id"] == aaa["buy_trade_id"])
    assert trade["decision_snapshot"]["command_id"] == aaa["buy_command_id"] and trade["decision_snapshot"]["own_decision"] is False
    assert aaa["buy_at"] == trade["executed_at"]  # the factual fill instant of the paper engine, not the cycle start
    buy = aaa["divergence"]["buy"]
    assert buy["ledger_price"] == 50.0 and buy["mirror_fill_price"] == pytest.approx(50.1501) and buy["reconciled"] is False
    assert buy["quote_source_at"] and buy["quote_available_at"] and buy["decided_at"] == (T0 + timedelta(seconds=30)).isoformat()
    assert datetime.fromisoformat(buy["mirror_at"]) == trade["executed_at"]
    again = _run(repo, memory, experiment, ledger, quotes, T0 + timedelta(seconds=60))
    assert again["buys"] == 0 and again["sells"] == 0 and again["actions"] == 0 and len(repo.memory["trades"]) == 2
    exit_at = T0 + timedelta(hours=1)
    closed = _row([_record("AAA", status="CLOSED", exit_cause="TARGET", exit_price=54.2, exit_at=exit_at), _record("BBB", quantity=10.12345678)], version=4)
    quotes.mids["AAA"] = 54.0
    result = _run(repo, memory, experiment, closed, quotes, exit_at + timedelta(seconds=5))
    assert result["sells"] == 1 and result["buys"] == 0 and result["ledger_version"] == 4
    assert "AAA" not in {row["symbol"] for row in repo.positions(experiment["id"])}
    rows = _rows(memory, experiment)
    sell = rows["ep-AAA"]["divergence"]["sell"]
    assert rows["ep-AAA"]["status"] == "CLOSED" and rows["ep-AAA"]["sell_command_id"] == command_id(MIRROR_EPOCH, EPOCH, "ep-AAA", "SELL")
    assert sell["ledger_price"] == 54.2 and sell["mirror_fill_price"] == pytest.approx(54.0 * 0.999)
    assert sell["ledger_exit_interval"] == [exit_at.isoformat(), (exit_at + timedelta(minutes=1)).isoformat()] and "buy" in rows["ep-AAA"]["divergence"]
    summary = public_summary(repo=repo, mirror=memory, experiment=experiment, mirror_epoch=MIRROR_EPOCH, epoch=EPOCH, terminal_reasons=[], now=exit_at)
    assert summary["label"] == LABEL and summary["is_evidence"] is False and summary["status_counts"]["CLOSED"] == 1 and summary["status_counts"]["OPEN"] == 1
    assert summary["open_positions"] == 1 and summary["divergence_sell"]["count"] == 1 and "AAA" not in json.dumps(summary)


def test_exit_pending_persists_without_a_quote_blocks_new_buys_and_never_invents_a_fill() -> None:
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.0, "BBB": 20.0})
    _run(repo, memory, experiment, _row([_record("AAA")]), quotes, T0)
    exit_at = T0 + timedelta(hours=1)
    closed = [_record("AAA", status="CLOSED", exit_cause="STOP", exit_price=48.0, exit_at=exit_at), _record("BBB", opened_at=exit_at)]
    quotes.status = "delayed"
    result = _run(repo, memory, experiment, _row(closed, version=4), quotes, exit_at + timedelta(seconds=5))
    rows = _rows(memory, experiment)
    assert rows["ep-AAA"]["status"] == "EXIT_PENDING" and rows["ep-AAA"]["sell_trade_id"] is None and rows["ep-AAA"]["command_registered_at"]
    assert result["sells"] == 0 and result["reasons"] == {"QUOTE_NOT_VALID_EXIT_PENDING": 1, "EXIT_OBLIGATION_BLOCKS_BUYS": 1}
    assert {row["symbol"] for row in repo.positions(experiment["id"])} == {"AAA"}
    registered_at = rows["ep-AAA"]["command_registered_at"]
    quotes.status = "live"
    result = _run(repo, memory, experiment, _row(closed, version=5), quotes, exit_at + timedelta(minutes=3))
    rows = _rows(memory, experiment)
    assert result["sells"] == 1 and rows["ep-AAA"]["status"] == "CLOSED" and rows["ep-AAA"]["command_registered_at"] == registered_at
    result = _run(repo, memory, experiment, _row(closed, version=6), quotes, exit_at + timedelta(minutes=4))
    assert result["buys"] == 1 and _rows(memory, experiment)["ep-BBB"]["status"] == "OPEN"


def test_concurrent_execution_of_the_same_command_is_arbitrated_by_the_claim_and_the_cycle_lock() -> None:
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.0})
    ledger = _row([_record("AAA", quantity=10.0)])
    # I1: a second worker holding the cycle lock makes this cycle a no-op instead of a duplicate command
    lock = repo.database._r2d2_v2_mirror_lock  # type: ignore[attr-defined]
    lock.acquire()
    try:
        result = _run(repo, memory, experiment, ledger, quotes, T0)
    finally:
        lock.release()
    assert result["status"] == "CYCLE_LOCKED_ELSEWHERE" and result["actions"] == 0 and repo.memory["trades"] == []
    # I1: a command already claimed (BUY_EXECUTING) by another process is never executed again by this one
    _run(repo, memory, experiment, ledger, quotes, T0 + timedelta(seconds=1))
    row = _rows(memory, experiment)["ep-AAA"]
    assert row["status"] == "OPEN" and len(repo.memory["trades"]) == 1
    memory.upsert({**row, "status": "BUY_EXECUTING", "claim_token": "other-process", "buy_trade_id": None, "buy_quantity": None, "buy_fill_price": None, "divergence": None})
    result = _run(repo, memory, experiment, ledger, quotes, T0 + timedelta(seconds=2))
    adopted = _rows(memory, experiment)["ep-AAA"]
    assert result["buy_adopted"] == 1 and result["buys"] == 0 and len(repo.memory["trades"]) == 1  # the effect exists: adopted by reading, no second order
    assert adopted["status"] == "OPEN" and adopted["buy_trade_id"] == row["buy_trade_id"] and adopted["claim_token"] is None
    # a claim whose effect never happened is released (never re-executed blindly by another claimant in the same cycle)
    fresh_repo, fresh_memory, fresh_experiment = _setup()
    fresh_memory.upsert({"mirror_epoch": MIRROR_EPOCH, "epoch": EPOCH, "episode_key": "ep-AAA", "symbol": "AAA", "market": "NASDAQ",
                         "experiment_id": fresh_experiment["id"], "status": "BUY_EXECUTING", "claim_token": "dead-process",
                         "buy_command_id": command_id(MIRROR_EPOCH, EPOCH, "ep-AAA", "BUY"), "buy_command_sha": None})
    result = _run(fresh_repo, fresh_memory, fresh_experiment, ledger, quotes, T0 + timedelta(seconds=3))
    assert result["released"] == 1 and result["buys"] == 1 and len(fresh_repo.memory["trades"]) == 1
    assert _rows(fresh_memory, fresh_experiment)["ep-AAA"]["status"] == "OPEN"


def test_payload_conflicts_block_after_open_and_on_recovery_without_a_second_order() -> None:
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.0})
    ledger = _row([_record("AAA", quantity=10.0)])
    _run(repo, memory, experiment, ledger, quotes, T0)
    # I2: the ledger now presents q11 for an OPEN mirrored q10: BLOCKED, position kept, no order
    changed = _row([_record("AAA", quantity=11.0)], version=4)
    result = _run(repo, memory, experiment, changed, quotes, T0 + timedelta(minutes=1))
    row = _rows(memory, experiment)["ep-AAA"]
    assert result["blocked"] == 1 and row["status"] == "BLOCKED" and row["reason"] == "COMMAND_PAYLOAD_CONFLICT" and len(repo.memory["trades"]) == 1
    assert {p["symbol"] for p in repo.positions(experiment["id"])} == {"AAA"}
    # I4: the blocked row still holds a position: new BUYs stay blocked, and the ledger exit is still honoured
    with_new = _row([_record("AAA", quantity=11.0), _record("BBB", opened_at=T0 + timedelta(minutes=2))], version=5)
    result = _run(repo, memory, experiment, FakeQuotes({"AAA": 50.0, "BBB": 20.0}) and with_new, FakeQuotes({"AAA": 50.0, "BBB": 20.0}), T0 + timedelta(minutes=3))
    assert result["buys"] == 0 and result["reasons"].get("EXIT_OBLIGATION_BLOCKS_BUYS") == 1
    exit_at = T0 + timedelta(hours=1)
    closing = _row([_record("AAA", quantity=11.0, status="CLOSED", exit_cause="TIME", exit_price=50.0, exit_at=exit_at)], version=6)
    result = _run(repo, memory, experiment, closing, quotes, exit_at + timedelta(seconds=5))
    assert result["sells"] == 1 and _rows(memory, experiment)["ep-AAA"]["status"] == "CLOSED" and repo.positions(experiment["id"]) == []
    # I2 on recovery: a pending row whose registered payload differs from the executed effect is BLOCKED, never adopted
    repo2, memory2, experiment2 = _setup()
    _run(repo2, memory2, experiment2, ledger, quotes, T0)
    row2 = _rows(memory2, experiment2)["ep-AAA"]
    memory2.upsert({**row2, "status": "BUY_PENDING", "buy_command_sha": "0" * 64, "buy_trade_id": None, "divergence": None})
    result = _run(repo2, memory2, experiment2, ledger, quotes, T0 + timedelta(minutes=2))
    assert result["conflicts"] == 1 and _rows(memory2, experiment2)["ep-AAA"]["status"] == "BLOCKED" and len(repo2.memory["trades"]) == 1


def test_caps_use_the_us_name_across_exchanges_and_marked_excess_blocks_every_buy() -> None:
    repo, memory, experiment = _setup(capital=100_000.0)
    quotes = FakeQuotes({"AAA": 50.0, "BBB": 50.0})
    # C1: 100 shares of AAA on NASDAQ (5%) then another AAA episode listed on NYSE: the same US name would reach 10%
    _run(repo, memory, experiment, _row([_record("AAA")]), quotes, T0)
    second = {**_record("AAA"), "episode_key": "ep-AAA-2", "opened_at": (T0 + timedelta(minutes=1)).isoformat()}
    result = run_once(ledger_row=_row([_record("AAA"), second], version=4), mirror_epoch=MIRROR_EPOCH, repo=repo, mirror=memory, experiment=experiment,
                      quotes=quotes, resolve_market=lambda s: "NYSE", now=T0 + timedelta(minutes=2), activated_at=ACTIVATED)
    assert _rows(memory, experiment)["ep-AAA-2"]["reason"] == "CAP_PER_NAME_6PCT" and result["skipped"] == 1
    # C1: a name marked above 6% blocks every new BUY (no liquidation)
    for position in repo.memory["positions"].values():
        position["last_price_local"] = 65.0  # AAA now 6.5k on ~101.5k NAV
    result = _run(repo, memory, experiment, _row([_record("AAA"), _record("BBB", opened_at=T0 + timedelta(minutes=3))], version=5), quotes, T0 + timedelta(minutes=4))
    assert result["marked_excess"] == "MARKED_EXCESS_PER_NAME_6PCT" and result["buys"] == 0 and result["reasons"].get("MARKED_EXCESS_PER_NAME_6PCT") == 1
    assert {p["symbol"] for p in repo.positions(experiment["id"])} == {"AAA"}
    positions, cash, nav = mirror_module._book(repo, repo.experiment(experiment["code"]) or experiment)
    assert marked_excess(positions, cash, nav) == "MARKED_EXCESS_PER_NAME_6PCT"
    # permanent rejection on a 10k NAV: never retried at a better price
    repo3, memory3, experiment3 = _setup(capital=10_000.0)
    result = _run(repo3, memory3, experiment3, _row([_record("AAA")]), FakeQuotes({"AAA": 50.0}), T0)
    assert result["skipped"] == 1 and _rows(memory3, experiment3)["ep-AAA"]["reason"] == "CAP_PER_NAME_6PCT"
    assert _run(repo3, memory3, experiment3, _row([_record("AAA")], version=4), FakeQuotes({"AAA": 20.0}), T0 + timedelta(minutes=1))["actions"] == 0
    assert mirror_module.CAPS["gross_us_percent"] == 48.0 and "gross_per_market_percent" not in mirror_module.CAPS


def test_memory_scope_and_experiment_isolation() -> None:
    repo, memory, experiment = _setup()
    _run(repo, memory, experiment, _row([_record("AAA")]), FakeQuotes({"AAA": 50.0}), T0)
    # C3: another mirror epoch of the same shadow epoch does not inherit this memory
    assert memory.load("R2D2-V2-MIRROR-OTHER", EPOCH, experiment["id"]) == {} and memory.load(MIRROR_EPOCH, EPOCH, "other-experiment") == {}
    assert set(_rows(memory, experiment)) == {"ep-AAA"}
    with pytest.raises(MirrorInputError, match="MIRROR_ROW_SCOPE_MISSING"):
        memory.upsert({"epoch": EPOCH, "episode_key": "x", "symbol": "X", "status": "SKIPPED"})
    # an OPEN episode that vanished from the ledger awaits disposition and blocks new BUYs; a symbol without pinned exchange is skipped
    result = _run(repo, memory, experiment, _row([_record("ZZZ", quantity=1.0)]), FakeQuotes({"ZZZ": 5.0}), T0 + timedelta(minutes=1))
    assert result["dispositions"] == 1 and _rows(memory, experiment)["ep-AAA"]["status"] == "AWAITING_DISPOSITION" and result["reasons"].get("EXIT_OBLIGATION_BLOCKS_BUYS") == 1
    repo4, memory4, experiment4 = _setup()
    result = _run(repo4, memory4, experiment4, _row([_record("ZZZ", quantity=1.0)]), FakeQuotes({"ZZZ": 5.0}), T0 + timedelta(minutes=1))
    assert _rows(memory4, experiment4)["ep-ZZZ"]["reason"] == "MARKET_UNRESOLVED" and result["skipped"] == 1
    assert experiment["code"] == "R2D2-V2-MIRROR-001" and experiment["cash_balance"] == 1_000_000.0 and experiment["mandate"]["mode"] == "paper_only"
    assert experiment["mandate"]["real_broker_execution"] is False and experiment["mandate"]["is_evidence"] is False and experiment["mandate"]["mirror_epoch"] == MIRROR_EPOCH
    with pytest.raises(MirrorInputError, match="MIRROR_EXPERIMENT_CODE_INVALID"):
        ensure_mirror_experiment(repo, code="R2D2-90D-001", epoch=EPOCH, mirror_epoch=MIRROR_EPOCH)
    with pytest.raises(MirrorInputError, match="MEMORY_MODE_HOLDS_ANOTHER_EXPERIMENT"):
        ensure_mirror_experiment(repo, code="R2D2-V2-MIRROR-002", epoch=EPOCH, mirror_epoch=MIRROR_EPOCH)


def test_release_receipt_binds_publication_and_cursor_to_the_session_open() -> None:
    body = {"schema": "R2D2_V2_MIRROR_RELEASE_V1", "mirror_epoch": MIRROR_EPOCH, "epoch": EPOCH, "experiment_code": "R2D2-V2-MIRROR-001",
            "code_revision": "abc123", "review_sha": "f" * 64, "owner_order_ref": "#348 5563247154",
            "published_at": (ACTIVATED - timedelta(hours=2)).isoformat(), "initial_cursor_at": ACTIVATED.isoformat(),
            "signatures": [{"party": "CODEX"}, {"party": "FABLE"}, {"party": "DUDU"}]}
    data = json.dumps(body).encode()
    sha = hashlib.sha256(data).hexdigest()
    release = MirrorRelease.verify(data, sha, build_sha="abc123", now=T0)
    assert release.epoch == EPOCH and release.initial_cursor_at == ACTIVATED and release.published_at == ACTIVATED - timedelta(hours=2)
    for change, code in [({"code_revision": "other"}, "MIRROR_RELEASE_CODE_REVISION_MISMATCH"),
                         ({"signatures": [{"party": "FABLE"}, {"party": "DUDU"}]}, "MIRROR_RELEASE_SIGNATURES_INCOMPLETE"),
                         ({"initial_cursor_at": (T0 + timedelta(days=1)).isoformat(), "published_at": (T0 + timedelta(days=1)).isoformat()}, "MIRROR_RELEASE_CURSOR_AFTER_OPEN"),
                         ({"published_at": (ACTIVATED + timedelta(hours=1)).isoformat()}, "MIRROR_RELEASE_PUBLISHED_AFTER_CURSOR"),  # C4: published at 11h ET
                         ({"initial_cursor_at": datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc).isoformat()}, "MIRROR_RELEASE_CURSOR_AFTER_OPEN"),  # 11:00 New York
                         ({"mirror_epoch": "R2D2-90D-001"}, "MIRROR_RELEASE_MIRROR_EPOCH_INVALID")]:
        altered = json.dumps({**body, **change}).encode()
        with pytest.raises(MirrorInputError, match=code):
            MirrorRelease.verify(altered, hashlib.sha256(altered).hexdigest(), build_sha="abc123", now=T0)
    missing = json.dumps({k: v for k, v in body.items() if k != "published_at"}).encode()
    with pytest.raises(MirrorInputError, match="LEDGER_TIMESTAMP_INVALID"):
        MirrorRelease.verify(missing, hashlib.sha256(missing).hexdigest(), build_sha="abc123", now=T0)
    future = json.dumps({**body, "published_at": (T0 + timedelta(days=1)).isoformat(), "initial_cursor_at": (T0 + timedelta(days=1)).isoformat()}).encode()
    with pytest.raises(MirrorInputError, match="MIRROR_RELEASE_CURSOR_AFTER_OPEN|MIRROR_RELEASE_NOT_YET_ACTIVE"):
        MirrorRelease.verify(future, hashlib.sha256(future).hexdigest(), build_sha="abc123", now=T0)
    with pytest.raises(MirrorInputError, match="MIRROR_RELEASE_SHA_MISMATCH"):
        MirrorRelease.verify(data, "0" * 64, build_sha="abc123", now=T0)


def test_worker_is_off_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("C3PO_R2D2_V2_MIRROR_ENABLED", raising=False)
    assert mirror_module.main([]) == 0
    assert '"status":"OFF"' in capsys.readouterr().out
