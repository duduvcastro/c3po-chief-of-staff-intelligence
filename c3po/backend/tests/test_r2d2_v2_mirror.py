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
    LABEL, Action, MirrorInputError, MirrorQuote, MirrorRelease, MirrorRepository, command_id, ensure_mirror_experiment, plan,
    public_summary, quote_valid, read_ledger, run_once,
)

EPOCH = "R2D2-V2-SHADOW-TEST"
MIRROR_EPOCH = "R2D2-V2-MIRROR-TEST-1"
T0 = datetime(2026, 9, 14, 14, 1, tzinfo=timezone.utc)
ACTIVATED = T0 - timedelta(hours=1)


def _record(symbol: str, *, status: str = "OPEN", quantity: float = 100.0, opened_at: datetime = T0, kind: str = "PORTFOLIO",
            exit_cause: str | None = None, exit_price: float | None = None, exit_at: datetime | None = None) -> dict:
    return {"episode_key": f"ep-{symbol}", "instrument_key": f"US:{symbol}", "session": "2026-09-14", "opened_at": opened_at.isoformat(),
            "maturity_at": (opened_at + timedelta(days=14)).isoformat(), "arm": "ELIGIBLE", "kind": kind,
            "geometry": {"P": 50.0, "B": 50.05, "C": 50.09, "S": 48.0, "T": 54.2, "R_unit": 2.09}, "q0": quantity, "quantity": quantity,
            "status": status, "exit_cause": exit_cause, "exit_price": exit_price, "exit_at": exit_at.isoformat() if exit_at else None,
            "exit_available_at": (exit_at + timedelta(seconds=1)).isoformat() if exit_at else None,
            "exit_interval": [exit_at.isoformat(), (exit_at + timedelta(minutes=1)).isoformat()] if exit_at else None}


def _row(records: list[dict], *, terminal: list[str] | None = None, mode: str = "CERTIFIED", epoch: str = EPOCH, version: int = 3) -> dict:
    state = {"epoch": epoch, "mode": mode, "ledger": {"session": "2026-09-14", "terminal_reasons": terminal or [],
                                                     "portfolio": {r["episode_key"]: r for r in records}, "research": {}}}
    return {"state": state, "state_sha": hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest(), "version": version}


class FakeQuotes:
    def __init__(self, mids: dict[str, float], *, status: str = "live", age: float = 1.0, spread: float = 0.02) -> None:
        self.mids, self.status, self.age, self.spread = mids, status, age, spread

    def quote(self, market: str, symbol: str, now: datetime) -> MirrorQuote | None:
        mid = self.mids.get(symbol)
        if mid is None:
            return None
        return MirrorQuote(mid - self.spread / 2, mid + self.spread / 2, now - timedelta(seconds=self.age), self.status)


def _setup(capital: float = 1_000_000.0):
    settings = Settings(database_url="", r2d2_start_date="2026-09-14", r2d2_checkpoint_days=90, r2d2_starting_capital_usd=capital)
    database = Database(settings)
    repo = R2D2Repository(database)
    memory = MirrorRepository(database)
    experiment = ensure_mirror_experiment(repo, code="R2D2-V2-MIRROR-001", epoch=EPOCH, mirror_epoch=MIRROR_EPOCH, starting_capital=capital, now=T0)
    return repo, memory, experiment


def _resolve(symbol: str) -> str | None:
    return {"AAA": "NASDAQ", "BBB": "NYSE", "CCC": "NASDAQ"}.get(symbol)


def _run(repo, memory, experiment, ledger, quotes, now, **kwargs):
    return run_once(ledger_row=ledger, mirror_epoch=MIRROR_EPOCH, repo=repo, mirror=memory, experiment=experiment, quotes=quotes,
                    resolve_market=_resolve, now=now, activated_at=ACTIVATED, **kwargs)


def test_read_ledger_accepts_only_certified_shadow_epochs_with_a_ledger() -> None:
    view = read_ledger(_row([_record("AAA"), _record("BBB", kind="RESEARCH", quantity=1.0)], terminal=["NAV_FLOOR"]))
    assert view.epoch == EPOCH and view.version == 3 and view.vetoed and view.terminal_reasons == ("NAV_FLOOR",)
    assert [r.symbol for r in view.records] == ["AAA", "BBB"] and view.records[0].kind == "PORTFOLIO" and view.records[1].kind == "RESEARCH"
    assert view.records[0].entry_price == 50.0 and view.records[0].stop == 48.0 and view.records[0].opened_at == T0
    closed = read_ledger(_row([_record("AAA", status="CLOSED", exit_cause="TARGET", exit_price=54.2, exit_at=T0)])).records[0]
    assert closed.exit_interval == (T0.isoformat(), (T0 + timedelta(minutes=1)).isoformat())  # intervals stay intervals
    for bad, code in [(_row([], mode="DIAGNOSTIC"), "SHADOW_MODE_NOT_CERTIFIED"), (_row([], epoch="R2D2-V2-DIAG-1"), "SHADOW_EPOCH_NOT_CERTIFIED"),
                      ({"state": {"epoch": EPOCH, "mode": "CERTIFIED", "ledger": None}, "state_sha": "0" * 64, "version": 1}, "SHADOW_LEDGER_MISSING"),
                      ({**_row([]), "version": "1"}, "SHADOW_VERSION_INVALID"),
                      (_row([_record("AAA", status="CLOSED", exit_cause="WEIRD", exit_price=51.0, exit_at=T0)]), "LEDGER_EXIT_CAUSE_INVALID"),
                      (_row([{**_record("AAA"), "opened_at": "2026-09-14T14:01:00"}]), "LEDGER_TIMESTAMP_NAIVE"),
                      (_row([{**_record("AAA"), "quantity": 0}]), "LEDGER_NUMBER_INVALID")]:
        with pytest.raises(MirrorInputError, match=code):
            read_ledger(bad)


def test_plan_mirrors_only_recorded_portfolio_decisions_and_honours_every_veto() -> None:
    exit_at = T0 + timedelta(hours=2)
    records = [_record("AAA"), _record("BBB", opened_at=ACTIVATED - timedelta(minutes=1)), _record("CCC", kind="RESEARCH", quantity=1.0),
               _record("DDD", status="CLOSED", exit_cause="TARGET", exit_price=54.2, exit_at=exit_at),
               _record("EEE", status="CLOSED", exit_cause="STOP", exit_price=48.0, exit_at=exit_at),
               _record("FFF", status="CLOSED", exit_cause="TIME", exit_price=50.0, exit_at=exit_at)]
    view = read_ledger(_row(records))
    no_exits = {"ep-FFF": {"status": "BUY_PENDING"}}
    actions = {a.episode_key: a for a in plan(view, no_exits, activated_at=ACTIVATED)}
    assert set(actions) == {"ep-AAA", "ep-BBB", "ep-DDD", "ep-EEE", "ep-FFF"}  # research never mirrored
    assert actions["ep-AAA"].kind == "BUY" and actions["ep-BBB"] == Action("SKIP", view.records[1], "OPENED_BEFORE_INITIAL_CURSOR", "ep-BBB")
    assert actions["ep-DDD"].kind == "SKIP" and actions["ep-DDD"].reason == "CLOSED_BEFORE_MIRROR"
    assert actions["ep-EEE"].kind == "SKIP" and actions["ep-EEE"].reason == "CLOSED_BEFORE_MIRROR"
    assert actions["ep-FFF"].kind == "SKIP" and actions["ep-FFF"].reason == "CLOSED_BEFORE_MIRROR_EXECUTION"  # BUY pending, virtual already closed
    # a mirrored position whose virtual closed this cycle: SELL due, and the exit obligation blocks new BUYs in the same cycle
    mirrored = {"ep-DDD": {"status": "OPEN"}, "ep-FFF": {"status": "BUY_PENDING"}}
    actions = {a.episode_key: a for a in plan(view, mirrored, activated_at=ACTIVATED)}
    assert actions["ep-DDD"].kind == "SELL" and actions["ep-DDD"].reason == "LEDGER_EXIT_RECORDED:TARGET"
    assert actions["ep-AAA"] == Action("DEFER", view.records[0], "EXIT_PENDING_BLOCKS_BUYS", "ep-AAA")
    assert [a.kind for a in plan(view, mirrored, activated_at=ACTIVATED)][:1] == ["SKIP"] and [a.kind for a in plan(view, mirrored, activated_at=ACTIVATED)][-1] == "DEFER"  # exits before entries
    for kwargs, reason in [({"exits_only": True}, "EXITS_ONLY_BY_DESK_ORDER"), ({"entries_paused": True}, "MIRROR_ENTRIES_PAUSED")]:
        kinds = {a.episode_key: (a.kind, a.reason) for a in plan(view, no_exits, activated_at=ACTIVATED, **kwargs)}
        assert kinds["ep-AAA"] == ("DEFER", reason)
    vetoed = {a.episode_key: (a.kind, a.reason) for a in plan(read_ledger(_row(records, terminal=["GAP_LOSS_LIMIT"])), mirrored, activated_at=ACTIVATED)}
    assert vetoed["ep-AAA"] == ("DEFER", "LEDGER_VETO:GAP_LOSS_LIMIT;EXIT_PENDING_BLOCKS_BUYS") and vetoed["ep-DDD"][0] == "SELL"
    # a pending exit blocks new BUYs; a BUY_PENDING command with the ledger still open is retried; an OPEN episode that vanished awaits disposition
    pending = {"ep-DDD": {"status": "EXIT_PENDING"}, "ep-AAA": {"status": "BUY_PENDING"}, "ep-GONE": {"status": "OPEN"}}
    kinds = {a.episode_key: (a.kind, a.reason) for a in plan(view, pending, activated_at=ACTIVATED)}
    assert kinds["ep-DDD"] == ("SELL", "EXIT_PENDING_RETRY") and kinds["ep-AAA"] == ("BUY", "COMMAND_REGISTERED_EFFECT_PENDING")
    assert kinds["ep-GONE"] == ("DISPOSITION", "EPISODE_ABSENT_FROM_LEDGER")
    fresh = {a.episode_key: (a.kind, a.reason) for a in plan(read_ledger(_row(records + [_record("GGG")])), pending, activated_at=ACTIVATED)}
    assert fresh["ep-GGG"] == ("DEFER", "EXIT_PENDING_BLOCKS_BUYS")
    assert [a for a in plan(view, {"ep-AAA": {"status": "OPEN"}, **mirrored}, activated_at=ACTIVATED) if a.episode_key == "ep-AAA"] == []


def test_quote_validity_is_regular_bid_ask_at_most_ten_seconds_old_and_never_future() -> None:
    now = T0
    assert quote_valid(MirrorQuote(10.0, 10.02, now - timedelta(seconds=9), "live"), now)
    assert not quote_valid(MirrorQuote(10.0, 10.02, now - timedelta(seconds=11), "live"), now)
    assert not quote_valid(MirrorQuote(10.0, 10.02, now + timedelta(seconds=1), "live"), now)  # future tick
    assert not quote_valid(MirrorQuote(10.0, 10.02, now, "delayed"), now)
    assert not quote_valid(MirrorQuote(10.05, 10.0, now, "live"), now)  # crossed
    assert not quote_valid(MirrorQuote(0.0, 10.0, now, "live"), now)
    assert not quote_valid(MirrorQuote(float("nan"), 10.0, now, "live"), now)
    assert not quote_valid(MirrorQuote(10.0, 10.02, datetime(2026, 9, 14, 14, 1), "live"), now)  # naive clock
    assert not quote_valid(None, now)
    assert MirrorQuote(10.0, 10.02, now, "live").midpoint == pytest.approx(10.01)


def test_run_once_registers_commands_before_effects_and_records_divergences() -> None:
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.10, "BBB": 30.0})
    ledger = _row([_record("AAA"), _record("BBB", quantity=10.12345678)])
    result = _run(repo, memory, experiment, ledger, quotes, T0 + timedelta(seconds=30))
    assert result["buys"] == 2 and result["sells"] == 0 and result["label"] == LABEL and result["vetoed"] is False
    positions = {row["symbol"]: row for row in repo.positions(experiment["id"])}
    assert positions["AAA"]["quantity"] == 100.0 and positions["BBB"]["quantity"] == 10.12345678  # q preserved, eight decimals
    assert positions["AAA"]["last_price_local"] == pytest.approx(50.10 * 1.001)  # midpoint + simulator friction, not the ledger price
    assert positions["AAA"]["stop_price_local"] == 48.0  # the ledger's own reference, no mirror decision
    rows = memory.load(EPOCH)
    aaa = rows["ep-AAA"]
    assert aaa["status"] == "OPEN" and aaa["command_id"] == command_id(MIRROR_EPOCH, EPOCH, "ep-AAA", "BUY") and aaa["command_sha"]
    assert aaa["buy_trade_id"] and aaa["buy_quantity"] == 100.0 and aaa["mirror_epoch"] == MIRROR_EPOCH
    trade = next(t for t in repo.memory["trades"] if t["id"] == aaa["buy_trade_id"])
    assert trade["decision_snapshot"]["command_id"] == aaa["command_id"] and trade["decision_snapshot"]["own_decision"] is False
    buy = aaa["divergence"]["buy"]
    assert buy["ledger_price"] == 50.0 and buy["mirror_fill_price"] == pytest.approx(50.1501) and buy["latency_seconds"] == 30.0 and buy["reconciled"] is False
    assert buy["quote_as_of"] and buy["decided_at"] and buy["mirror_at"]
    # repeating the same ledger emits nothing: the command already has its receipt
    again = _run(repo, memory, experiment, ledger, quotes, T0 + timedelta(seconds=60))
    assert again["buys"] == 0 and again["sells"] == 0 and again["actions"] == 0 and len(repo.memory["trades"]) == 2
    # the ledger records an exit: the mirrored quantity of that episode is sold at the simulator's price, with the interval kept as interval
    exit_at = T0 + timedelta(hours=1)
    closed = _row([_record("AAA", status="CLOSED", exit_cause="TARGET", exit_price=54.2, exit_at=exit_at), _record("BBB", quantity=10.12345678)], version=4)
    quotes.mids["AAA"] = 54.0
    result = _run(repo, memory, experiment, closed, quotes, exit_at + timedelta(seconds=5))
    assert result["sells"] == 1 and result["buys"] == 0 and result["ledger_version"] == 4
    assert "AAA" not in {row["symbol"] for row in repo.positions(experiment["id"])}
    rows = memory.load(EPOCH)
    sell = rows["ep-AAA"]["divergence"]["sell"]
    assert rows["ep-AAA"]["status"] == "CLOSED" and rows["ep-AAA"]["ledger_exit_cause"] == "TARGET" and rows["ep-AAA"]["sell_trade_id"]
    assert rows["ep-AAA"]["command_id"] == command_id(MIRROR_EPOCH, EPOCH, "ep-AAA", "SELL")
    assert sell["ledger_price"] == 54.2 and sell["mirror_fill_price"] == pytest.approx(54.0 * 0.999) and sell["latency_seconds"] == 4.0
    assert sell["ledger_exit_interval"] == [exit_at.isoformat(), (exit_at + timedelta(minutes=1)).isoformat()]
    assert "buy" in rows["ep-AAA"]["divergence"]  # the buy divergence is kept, never reconciled
    summary = public_summary(repo=repo, mirror=memory, experiment=experiment, epoch=EPOCH, terminal_reasons=[], now=exit_at)
    assert summary["label"] == LABEL and summary["is_evidence"] is False and summary["status_counts"]["CLOSED"] == 1 and summary["status_counts"]["OPEN"] == 1
    assert summary["open_positions"] == 1 and summary["divergence_sell"]["count"] == 1 and "AAA" not in json.dumps(summary)


def test_exit_pending_persists_without_a_quote_blocks_new_buys_and_never_invents_a_fill() -> None:
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.0, "BBB": 20.0})
    _run(repo, memory, experiment, _row([_record("AAA")]), quotes, T0)
    exit_at = T0 + timedelta(hours=1)
    closed = [_record("AAA", status="CLOSED", exit_cause="STOP", exit_price=48.0, exit_at=exit_at), _record("BBB", opened_at=exit_at)]
    quotes.status = "delayed"  # no valid quote: the exit obligation is registered and persists; the new admission is blocked
    result = _run(repo, memory, experiment, _row(closed, version=4), quotes, exit_at + timedelta(seconds=5))
    rows = memory.load(EPOCH)
    assert rows["ep-AAA"]["status"] == "EXIT_PENDING" and rows["ep-AAA"]["sell_trade_id"] is None and rows["ep-AAA"]["command_registered_at"]
    assert result["sells"] == 0 and result["deferred"] == 2 and result["reasons"] == {"QUOTE_NOT_VALID_EXIT_PENDING": 1, "EXIT_PENDING_BLOCKS_BUYS": 1}
    assert {row["symbol"] for row in repo.positions(experiment["id"])} == {"AAA"}  # the position is neither erased nor sold at an invented price
    registered_at = rows["ep-AAA"]["command_registered_at"]
    quotes.status = "live"  # the quote returns: the pending exit executes, then the blocked admission proceeds on the next cycle
    result = _run(repo, memory, experiment, _row(closed, version=5), quotes, exit_at + timedelta(minutes=3))
    rows = memory.load(EPOCH)
    assert result["sells"] == 1 and rows["ep-AAA"]["status"] == "CLOSED" and rows["ep-AAA"]["command_registered_at"] == registered_at
    assert rows["ep-AAA"]["divergence"]["sell"]["latency_seconds"] == pytest.approx(179.0)
    result = _run(repo, memory, experiment, _row(closed, version=6), quotes, exit_at + timedelta(minutes=4))
    assert result["buys"] == 1 and memory.load(EPOCH)["ep-BBB"]["status"] == "OPEN"


def test_uncertain_effect_is_recovered_by_reading_never_by_a_second_order() -> None:
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.0})
    ledger = _row([_record("AAA")])
    _run(repo, memory, experiment, ledger, quotes, T0)
    row = memory.load(EPOCH)["ep-AAA"]
    # simulate a crash after the paper effect and before the receipt: the mirror memory still says BUY_PENDING
    memory.upsert({**row, "status": "BUY_PENDING", "buy_trade_id": None, "buy_at": None, "buy_quantity": None, "buy_fill_price": None, "divergence": None})
    result = _run(repo, memory, experiment, ledger, quotes, T0 + timedelta(minutes=1))
    recovered = memory.load(EPOCH)["ep-AAA"]
    assert result["buy_adopted"] == 1 and result["buys"] == 0 and len(repo.memory["trades"]) == 1  # no second order
    assert recovered["status"] == "OPEN" and recovered["reason"] == "EFFECT_RECOVERED_BY_READING" and recovered["buy_trade_id"] == row["buy_trade_id"]
    assert recovered["buy_quantity"] == 100.0 and recovered["divergence"]["buy"]["mirror_fill_price"] == pytest.approx(50.05)
    # a different payload under the same command identity blocks instead of executing
    memory.upsert({**recovered, "status": "BUY_PENDING", "command_sha": "0" * 64})
    result = _run(repo, memory, experiment, _row([_record("AAA")], version=4), quotes, T0 + timedelta(minutes=2))
    assert result["conflicts"] == 1 and memory.load(EPOCH)["ep-AAA"]["status"] == "BLOCKED" and len(repo.memory["trades"]) == 1


def test_caps_include_friction_reject_permanently_and_use_one_aggregated_us_limit() -> None:
    repo, memory, experiment = _setup(capital=10_000.0)
    # 100 shares at ~50 = 5,015 including friction > 6% of a 10k NAV: rejected permanently, nothing forced
    result = _run(repo, memory, experiment, _row([_record("AAA")]), FakeQuotes({"AAA": 50.0}), T0)
    row = memory.load(EPOCH)["ep-AAA"]
    assert result["skipped"] == 1 and row["status"] == "SKIPPED" and row["reason"] == "CAP_PER_NAME_6PCT" and row["command_id"] and repo.positions(experiment["id"]) == []
    result = _run(repo, memory, experiment, _row([_record("AAA")], version=4), FakeQuotes({"AAA": 20.0}), T0 + timedelta(minutes=1))
    assert result["actions"] == 0  # never retried at a better price
    # aggregated US cap: NASDAQ + NYSE positions count together against 48%
    repo2, memory2, experiment2 = _setup(capital=100_000.0)
    admissions = [_record(s, quantity=110.0) for s in ("AAA", "BBB", "CCC")]  # 3 × ~5.5k = 16.5% of NAV, under every cap
    result = _run(repo2, memory2, experiment2, _row(admissions), FakeQuotes({"AAA": 50.0, "BBB": 50.0, "CCC": 50.0}), T0)
    assert result["buys"] == 3
    big = [_record("DDD", quantity=1000.0)] + admissions
    with_ddd = FakeQuotes({"AAA": 50.0, "BBB": 50.0, "CCC": 50.0, "DDD": 50.0})
    result = run_once(ledger_row=_row(big, version=4), mirror_epoch=MIRROR_EPOCH, repo=repo2, mirror=memory2, experiment=experiment2, quotes=with_ddd,
                      resolve_market=lambda s: "NYSE" if s == "DDD" else _resolve(s), now=T0 + timedelta(minutes=1), activated_at=ACTIVATED)
    assert memory2.load(EPOCH)["ep-DDD"]["reason"] == "CAP_PER_NAME_6PCT"  # 50k > 6k per name; the 48% US gate is aggregated over both exchanges
    assert mirror_module.CAPS["gross_us_percent"] == 48.0 and "gross_per_market_percent" not in mirror_module.CAPS


def test_unresolved_market_absent_position_and_experiment_isolation() -> None:
    repo, memory, experiment = _setup()
    result = _run(repo, memory, experiment, _row([_record("ZZZ", quantity=1.0)]), FakeQuotes({"ZZZ": 5.0}), T0)
    assert memory.load(EPOCH)["ep-ZZZ"]["reason"] == "MARKET_UNRESOLVED" and result["skipped"] == 1
    exit_at = T0 + timedelta(hours=1)
    memory.upsert({"epoch": EPOCH, "episode_key": "ep-CCC", "symbol": "CCC", "market": "NASDAQ", "experiment_id": experiment["id"], "status": "OPEN"})
    result = _run(repo, memory, experiment, _row([_record("CCC", status="CLOSED", exit_cause="TIME", exit_price=50.0, exit_at=exit_at)]),
                  FakeQuotes({"CCC": 50.0}), exit_at)
    assert memory.load(EPOCH)["ep-CCC"]["status"] == "CLOSED" and memory.load(EPOCH)["ep-CCC"]["reason"] == "POSITION_ABSENT_AT_EXIT" and result["sells"] == 0
    assert experiment["code"] == "R2D2-V2-MIRROR-001" and experiment["cash_balance"] == 1_000_000.0 and experiment["mandate"]["mode"] == "paper_only"
    assert experiment["mandate"]["real_broker_execution"] is False and experiment["mandate"]["is_evidence"] is False and experiment["mandate"]["mirror_epoch"] == MIRROR_EPOCH
    with pytest.raises(MirrorInputError, match="MIRROR_EXPERIMENT_CODE_INVALID"):
        ensure_mirror_experiment(repo, code="R2D2-90D-001", epoch=EPOCH, mirror_epoch=MIRROR_EPOCH)
    with pytest.raises(MirrorInputError, match="MEMORY_MODE_HOLDS_ANOTHER_EXPERIMENT"):
        ensure_mirror_experiment(repo, code="R2D2-V2-MIRROR-002", epoch=EPOCH, mirror_epoch=MIRROR_EPOCH)


def test_release_receipt_requires_three_signatures_pinned_code_and_an_initial_cursor() -> None:
    body = {"schema": "R2D2_V2_MIRROR_RELEASE_V1", "mirror_epoch": MIRROR_EPOCH, "epoch": EPOCH, "experiment_code": "R2D2-V2-MIRROR-001",
            "code_revision": "abc123", "review_sha": "f" * 64, "owner_order_ref": "#348 5562730016", "initial_cursor_at": ACTIVATED.isoformat(),
            "signatures": [{"party": "CODEX"}, {"party": "FABLE"}, {"party": "DUDU"}]}
    data = json.dumps(body).encode()
    sha = hashlib.sha256(data).hexdigest()
    release = MirrorRelease.verify(data, sha, build_sha="abc123", now=T0)
    assert release.epoch == EPOCH and release.mirror_epoch == MIRROR_EPOCH and release.initial_cursor_at == ACTIVATED and release.receipt_sha == sha
    for change, code in [({"code_revision": "other"}, "MIRROR_RELEASE_CODE_REVISION_MISMATCH"),
                         ({"signatures": [{"party": "FABLE"}, {"party": "DUDU"}]}, "MIRROR_RELEASE_SIGNATURES_INCOMPLETE"),
                         ({"initial_cursor_at": (T0 + timedelta(days=1)).isoformat()}, "MIRROR_RELEASE_NOT_YET_ACTIVE"),
                         ({"mirror_epoch": "R2D2-90D-001"}, "MIRROR_RELEASE_MIRROR_EPOCH_INVALID")]:
        altered = json.dumps({**body, **change}).encode()
        with pytest.raises(MirrorInputError, match=code):
            MirrorRelease.verify(altered, hashlib.sha256(altered).hexdigest(), build_sha="abc123", now=T0)
    with pytest.raises(MirrorInputError, match="MIRROR_RELEASE_SHA_MISMATCH"):
        MirrorRelease.verify(data, "0" * 64, build_sha="abc123", now=T0)


def test_worker_is_off_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("C3PO_R2D2_V2_MIRROR_ENABLED", raising=False)
    assert mirror_module.main([]) == 0
    assert '"status":"OFF"' in capsys.readouterr().out
