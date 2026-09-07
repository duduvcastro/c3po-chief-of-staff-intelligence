from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app import r2d2_v2_mirror as mirror_module
from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2Repository
from app.r2d2_v2_mirror import (
    LABEL, Action, MirrorInputError, MirrorQuote, MirrorRelease, MirrorRepository, QuoteTape, command_id, ensure_mirror_experiment, execute,
    marked_excess, plan, public_summary, quantity_precision_ok, quote_valid, read_ledger, regular_session_at, run_once, source_admission_vetoes,
)

EPOCH = "R2D2-V2-SHADOW-TEST"
MIRROR_EPOCH = "R2D2-V2-MIRROR-TEST-1"
T0 = datetime(2026, 9, 14, 14, 1, tzinfo=timezone.utc)  # Monday 14/09/2026, 10:01 New York (regular session)
ACTIVATED = datetime(2026, 9, 14, 13, 30, tzinfo=timezone.utc)  # 09:30 New York: the open of the first mirrored session
NY = mirror_module.NEW_YORK
NAV0 = 1_000_000.0


def _record(symbol: str, *, status: str = "OPEN", quantity: float = 100.0, opened_at: datetime = T0, kind: str = "PORTFOLIO",
            exit_cause: str | None = None, exit_price: float | None = None, exit_at: datetime | None = None, mark: float | None = 50.0,
            order_unknown: bool = False) -> dict:
    return {"episode_key": f"ep-{symbol}", "instrument_key": f"US:{symbol}", "session": "2026-09-14", "opened_at": opened_at.isoformat(),
            "maturity_at": (opened_at + timedelta(days=14)).isoformat(), "arm": "ELIGIBLE", "kind": kind,
            "geometry": {"P": 50.0, "B": 50.05, "C": 50.09, "S": 48.0, "T": 54.2, "R_unit": 2.09}, "q0": quantity, "quantity": quantity,
            "status": status, "exit_cause": exit_cause, "exit_price": exit_price, "exit_at": exit_at.isoformat() if exit_at else None,
            "exit_available_at": (exit_at + timedelta(seconds=1)).isoformat() if exit_at else None,
            "exit_interval": [exit_at.isoformat(), (exit_at + timedelta(minutes=1)).isoformat()] if exit_at else None,
            "mark": mark if status == "OPEN" else None, "accounting_unknown": False, "order_unknown": order_unknown, "receivables": {}}


def _row(records: list[dict], *, terminal: list[str] | None = None, mode: str = "CERTIFIED", epoch: str = EPOCH, version: int = 3,
         issues: dict | None = None, cash: float | None = None, session_start_nav: float | None = NAV0) -> dict:
    marked = sum(float(r["quantity"]) * float(r["mark"]) for r in records if r["status"] == "OPEN" and r.get("mark") is not None)
    ledger = {"session": "2026-09-14", "terminal_reasons": terminal or [], "portfolio": {r["episode_key"]: r for r in records}, "research": {},
              "cash": NAV0 - marked if cash is None else cash, "session_start_nav": session_start_nav, "initial_nav": NAV0}
    state = {"epoch": epoch, "mode": mode, "active_data_issues": issues or {}, "ledger": ledger}
    return {"state": state, "state_sha": hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest(), "version": version}


class FakeQuotes:
    """A quote source with causal clocks, an optional hook run during the lookup (to model I/O and races), and a regularity flag."""

    def __init__(self, mids: dict[str, float], *, status: str = "live", age: float = 1.0, spread: float = 0.02, regular: bool = True, hook=None) -> None:
        self.mids, self.status, self.age, self.spread, self.regular, self.hook = mids, status, age, spread, regular, hook
        self.calls = 0

    def quote(self, market: str, symbol: str, now: datetime) -> MirrorQuote | None:
        self.calls += 1
        mid = self.mids.get(symbol)
        if mid is None:
            return None
        quote = MirrorQuote(mid - self.spread / 2, mid + self.spread / 2, now - timedelta(seconds=self.age), now - timedelta(seconds=self.age / 2),
                            self.status, regular=self.regular)
        if self.hook is not None:
            self.hook(symbol)
        return quote


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


def test_read_ledger_accepts_only_certified_shadow_epochs_and_carries_every_source_veto() -> None:
    view = read_ledger(_row([_record("AAA"), _record("BBB", kind="RESEARCH", quantity=1.0)], terminal=["NAV_FLOOR"]))
    assert view.epoch == EPOCH and view.version == 3 and view.vetoed and view.terminal_reasons == ("NAV_FLOOR",) and view.data_gate_blocked is False
    assert view.source_vetoes == () and [r.symbol for r in view.records] == ["AAA", "BBB"] and view.records[0].kind == "PORTFOLIO"
    closed = read_ledger(_row([_record("AAA", status="CLOSED", exit_cause="TARGET", exit_price=54.2, exit_at=T0)])).records[0]
    assert closed.exit_interval == (T0.isoformat(), (T0 + timedelta(minutes=1)).isoformat())  # intervals stay intervals
    # the collector's data gate (#383 _admission_block): an active, unrestored issue of the current session vetoes the mirror too
    gate = _row([_record("AAA")], issues={"gap-1": {"session": "2026-09-14", "instrument": "*", "at": T0.isoformat(), "restored_instruments": []}})
    assert read_ledger(gate).data_gate_blocked is True and read_ledger(gate).vetoed is True and read_ledger(gate).gated("US:AAA") is True
    restored = _row([_record("AAA")], issues={"gap-1": {"session": "2026-09-14", "instrument": "US:AAA", "at": T0.isoformat(), "restored_instruments": ["US:AAA"]}})
    assert read_ledger(restored).data_gate_blocked is False and read_ledger(restored).gated("US:AAA") is False
    # I5b: a wildcard gap the generator already restored for this name no longer gates the name (but still gates the others)
    partly = _row([_record("AAA")], issues={"gap-1": {"session": "2026-09-14", "instrument": "*", "at": T0.isoformat(), "restored_instruments": ["US:AAA"]}})
    assert read_ledger(partly).gated("US:AAA") is False and read_ledger(partly).gated("US:BBB") is True
    other_session = _row([_record("AAA")], issues={"gap-1": {"session": "2026-09-11", "instrument": "*", "at": T0.isoformat(), "restored_instruments": []}})
    assert read_ledger(other_session).data_gate_blocked is False and read_ledger(other_session).gated("US:AAA") is False
    # I5a: the generator's own admission vetoes are recomputed from its published state (NAV = cash + marks + unpaid receivables)
    assert source_admission_vetoes(_row([_record("AAA")])["state"]["ledger"]) == ()
    assert read_ledger(_row([_record("AAA")], cash=NAV0 * 0.975 - 5_000)).source_vetoes == ("DAILY_LOSS_LIMIT",)  # NAV 980k = 98%: limit is inclusive
    assert read_ledger(_row([_record("AAA")], cash=NAV0 * 0.98 - 5_000 + 0.01)).source_vetoes == ()
    assert read_ledger(_row([_record("AAA", order_unknown=True)])).source_vetoes == ("NAV_UNOBSERVABLE",)
    assert read_ledger(_row([_record("AAA", mark=None)])).source_vetoes == ("NAV_UNOBSERVABLE",)
    assert read_ledger(_row([_record("AAA")], session_start_nav=None)).source_vetoes == ("DAY_NAV_UNOBSERVABLE",)
    missing_cash = _row([_record("AAA")])
    del missing_cash["state"]["ledger"]["cash"]
    assert read_ledger(missing_cash).source_vetoes == ("NAV_UNOBSERVABLE",)  # an unknown NAV is never zero, never ignored
    receivable = _row([{**_record("AAA"), "receivables": {"d1": {"amount": 30_000.0, "paid": False}}}], cash=NAV0 * 0.98 - 5_000 - 20_000)
    assert read_ledger(receivable).source_vetoes == ()  # 955k + 5k + 30k unpaid = 990k > 980k
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
    # I5a: the generator's admission vetoes (daily loss, unobservable NAV) reach the mirror even when nothing is terminal
    loss = plan(read_ledger(_row(records, cash=NAV0 * 0.90)), pending, activated_at=ACTIVATED)
    assert {a.episode_key: (a.kind, a.reason) for a in loss}["ep-AAA"] == ("DEFER", "LEDGER_ADMISSION_VETO:DAILY_LOSS_LIMIT")
    unknown = plan(read_ledger(_row([{**r, "order_unknown": r["episode_key"] == "ep-AAA"} for r in records])), pending, activated_at=ACTIVATED)
    assert {a.episode_key: (a.kind, a.reason) for a in unknown}["ep-AAA"] == ("DEFER", "LEDGER_ADMISSION_VETO:NAV_UNOBSERVABLE")
    # I5b: the data gate is applied per name, as the generator applies it
    gated = read_ledger(_row(records, issues={"g": {"session": "2026-09-14", "instrument": "*", "at": T0.isoformat(), "restored_instruments": []}}))
    assert {a.episode_key: (a.kind, a.reason) for a in plan(gated, pending, activated_at=ACTIVATED)}["ep-AAA"] == ("DEFER", "COLLECTION_DATA_GATE_BLOCKED")
    partly = read_ledger(_row(records, issues={"g": {"session": "2026-09-14", "instrument": "*", "at": T0.isoformat(), "restored_instruments": ["US:AAA"]}}))
    assert {a.episode_key: (a.kind, a.reason) for a in plan(partly, pending, activated_at=ACTIVATED)}["ep-AAA"] == ("BUY", "COMMAND_REGISTERED_EFFECT_PENDING")
    other_name = read_ledger(_row(records, issues={"g": {"session": "2026-09-14", "instrument": "US:GGG", "at": T0.isoformat(), "restored_instruments": []}}))
    assert {a.episode_key: (a.kind, a.reason) for a in plan(other_name, pending, activated_at=ACTIVATED)}["ep-AAA"][0] == "BUY"
    # I4: a SELL due this cycle, a pending exit, an episode that vanished, or a BLOCKED row holding a position all block new BUYs
    for mirrored, expected in [({"ep-DDD": {"status": "OPEN", "buy_command_sha": None}}, "EXIT_OBLIGATION_BLOCKS_BUYS"),
                               ({"ep-DDD": {"status": "EXIT_PENDING"}}, "EXIT_OBLIGATION_BLOCKS_BUYS"),
                               ({"ep-GONE": {"status": "OPEN", "buy_trade_id": "t1"}}, "EXIT_OBLIGATION_BLOCKS_BUYS"),
                               ({"ep-DDD": {"status": "BLOCKED", "buy_trade_id": "t1"}}, "EXIT_OBLIGATION_BLOCKS_BUYS"),
                               ({"ep-FFF": {"status": "OPEN", "buy_trade_id": "t1", "buy_command_sha": "0" * 64}}, "EXIT_OBLIGATION_BLOCKS_BUYS")]:
        kinds = {a.episode_key: (a.kind, a.reason) for a in plan(view, mirrored, activated_at=ACTIVATED)}
        assert kinds["ep-AAA"] == ("DEFER", expected), mirrored
    kinds = {a.episode_key: (a.kind, a.reason) for a in plan(view, {"ep-DDD": {"status": "BLOCKED", "buy_trade_id": "t1"}}, activated_at=ACTIVATED)}
    assert kinds["ep-DDD"] == ("SELL", "EXIT_OBLIGATION_AFTER_BLOCK")  # the exit obligation survives the block
    kinds = {a.episode_key: (a.kind, a.reason) for a in plan(view, {"ep-GONE": {"status": "OPEN", "buy_trade_id": "t1"}}, activated_at=ACTIVATED)}
    assert kinds["ep-GONE"] == ("DISPOSITION", "EPISODE_ABSENT_FROM_LEDGER")
    # I2: a payload that differs from the registered one blocks, in every state, including the terminal receipts
    changed = {"ep-AAA": {"status": "OPEN", "buy_command_sha": "0" * 64}}
    assert {a.episode_key: (a.kind, a.reason) for a in plan(view, changed, activated_at=ACTIVATED)}["ep-AAA"] == ("BLOCK", "COMMAND_PAYLOAD_CONFLICT")
    changed = {"ep-AAA": {"status": "BUY_PENDING", "buy_command_sha": "0" * 64}}
    assert {a.episode_key: (a.kind, a.reason) for a in plan(view, changed, activated_at=ACTIVATED)}["ep-AAA"] == ("BLOCK", "COMMAND_PAYLOAD_CONFLICT")
    changed = {"ep-DDD": {"status": "EXIT_PENDING", "sell_command_sha": "0" * 64}}
    assert {a.episode_key: (a.kind, a.reason) for a in plan(view, changed, activated_at=ACTIVATED)}["ep-DDD"] == ("DISPOSITION", "EXIT_COMMAND_PAYLOAD_CONFLICT")
    ddd = view.by_key()["ep-DDD"]
    agreed = {"ep-DDD": {"status": "CLOSED", "buy_trade_id": "t1", "sell_trade_id": "t2", "buy_command_sha": mirror_module.digest(ddd.buy_payload()),
                         "sell_command_sha": mirror_module.digest(ddd.sell_payload())}}
    assert "ep-DDD" not in {a.episode_key for a in plan(view, agreed, activated_at=ACTIVATED)}  # the receipt is returned: no action
    for field in ("buy_command_sha", "sell_command_sha"):
        conflict = {"ep-DDD": {**agreed["ep-DDD"], field: "0" * 64}}
        kinds = {a.episode_key: (a.kind, a.reason) for a in plan(view, conflict, activated_at=ACTIVATED)}
        assert kinds["ep-DDD"] == ("BLOCK", "TERMINAL_RECEIPT_PAYLOAD_CONFLICT") and kinds["ep-AAA"][0] == "BUY"  # no position: no BUY veto
    skipped = {"ep-AAA": {"status": "SKIPPED", "reason": "CAP_PER_NAME_6PCT", "buy_command_sha": "0" * 64}}
    assert {a.episode_key: (a.kind, a.reason) for a in plan(view, skipped, activated_at=ACTIVATED)}["ep-AAA"] == ("BLOCK", "TERMINAL_RECEIPT_PAYLOAD_CONFLICT")
    order = [a.kind for a in plan(view, {"ep-DDD": {"status": "OPEN", "buy_command_sha": None}}, activated_at=ACTIVATED)]
    assert order.index("SELL") < order.index("DEFER")  # exits before entries


def test_quote_validity_requires_causal_clocks_regular_session_bid_ask_and_ten_seconds() -> None:
    now = T0
    good = MirrorQuote(10.0, 10.02, now - timedelta(seconds=9), now - timedelta(seconds=8), "live", regular=True)
    assert quote_valid(good, now)
    assert not quote_valid(MirrorQuote(10.0, 10.02, now - timedelta(seconds=9), now - timedelta(seconds=8), "live"), now)  # regularity not proven
    assert not quote_valid(MirrorQuote(10.0, 10.02, now - timedelta(seconds=11), now - timedelta(seconds=10), "live", regular=True), now)  # too old
    assert not quote_valid(MirrorQuote(10.0, 10.02, now + timedelta(seconds=1), now + timedelta(seconds=2), "live", regular=True), now)  # future
    assert not quote_valid(MirrorQuote(10.0, 10.02, now - timedelta(seconds=1), now + timedelta(seconds=1), "live", regular=True), now)  # receipt in the future
    assert not quote_valid(MirrorQuote(10.0, 10.02, now - timedelta(seconds=1), now - timedelta(seconds=2), "live", regular=True), now)  # receipt before source
    assert not quote_valid(MirrorQuote(10.0, 10.02, now, now, "delayed", regular=True), now)
    assert not quote_valid(MirrorQuote(10.05, 10.0, now, now, "live", regular=True), now)  # crossed
    assert not quote_valid(MirrorQuote(0.0, 10.0, now, now, "live", regular=True), now)
    assert not quote_valid(MirrorQuote(float("nan"), 10.0, now, now, "live", regular=True), now)
    assert not quote_valid(MirrorQuote(10.0, 10.02, datetime(2026, 9, 14, 14, 1), now, "live", regular=True), now)  # naive clock
    assert not quote_valid(None, now)
    assert good.midpoint == pytest.approx(10.01)
    assert quantity_precision_ok(10.12345678) and not quantity_precision_ok(10.123456789) and quantity_precision_ok(100.0)
    # C2: regularity is the official XNYS calendar at the instant, never the feed's status
    assert regular_session_at(T0) and regular_session_at(datetime(2026, 9, 14, 13, 30, tzinfo=timezone.utc))
    assert not regular_session_at(datetime(2026, 9, 14, 13, 29, 59, tzinfo=timezone.utc)) and not regular_session_at(datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc))
    assert not regular_session_at(datetime(2026, 9, 13, 14, 1, tzinfo=timezone.utc))  # Sunday
    assert not regular_session_at(datetime(2026, 9, 7, 14, 1, tzinfo=timezone.utc))  # Labor Day
    assert not regular_session_at(datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc))  # early close (13:00 NY) already passed
    assert regular_session_at(datetime(2026, 11, 27, 17, 59, tzinfo=timezone.utc))


def test_quote_tape_records_causal_bid_ask_from_raw_payloads_and_proves_the_session() -> None:
    tape = QuoteTape()
    received = T0
    tick = int((T0 - timedelta(seconds=2)).timestamp() * 1000)
    assert tape.record(json.dumps({"s": "AAA", "bp": 10.0, "ap": 10.02, "t": tick}), received) == "AAA"
    quote = tape.quote("NASDAQ", "AAA", T0)
    assert quote is not None and quote.regular is True and quote.status == "live" and quote_valid(quote, T0)
    assert quote.source_at == T0 - timedelta(seconds=2) and quote.available_at == T0 and quote.bid == 10.0 and quote.ask == 10.02
    assert tape.record(json.dumps({"s": "AAA", "bp": 10.0, "ap": 10.02, "t": tick - 1000}), received) is None and tape.rejected == {"TICK_REGRESSES": 1}
    assert tape.record(json.dumps({"s": "AAA", "bp": 10.0, "ap": 10.02, "t": tick + 5_000}), received) is None and tape.rejected["TICK_IN_FUTURE"] == 1
    assert tape.record(json.dumps({"s": "AAA", "bp": 10.05, "ap": 10.0, "t": tick + 1}), received) is None and tape.rejected["BID_ASK_INVALID"] == 1
    assert tape.record(json.dumps({"s": "AAA", "bp": 10.0, "ap": 10.02}), received) is None and tape.rejected["TICK_CLOCK_INVALID"] == 1
    assert tape.record("not json", received) is None and tape.record(json.dumps({"s": "ZZZ", "bp": 1, "ap": 1, "t": tick}), received, {"AAA"}) is None
    assert tape.record(json.dumps({"s": "AAA", "bp": 10.0, "ap": 10.02, "t": tick}), datetime(2026, 9, 14, 14, 1)) is None  # naive receipt clock
    assert tape.quote("NASDAQ", "AAA", T0) == quote  # nothing invalid replaced the last causal quote
    # a tick outside the official session (Sunday 10:01 NY) is recorded but never a valid quote for the mirror
    sunday = datetime(2026, 9, 13, 14, 1, tzinfo=timezone.utc)
    tape.record(json.dumps({"s": "BBB", "bp": 20.0, "ap": 20.02, "t": int((sunday - timedelta(seconds=1)).timestamp() * 1000)}), sunday)
    weekend = tape.quote("NYSE", "BBB", sunday)
    assert weekend is not None and weekend.regular is False and not quote_valid(weekend, sunday)
    assert tape.quote("NYSE", "CCC", T0) is None


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
    assert trade["decision_snapshot"]["quote"]["regular"] is True
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
    # I2: the terminal receipt is compared with the ledger on every repetition: a changed exit price blocks, never a new order
    assert _run(repo, memory, experiment, _row(closed["state"]["ledger"]["portfolio"].values() and list(closed["state"]["ledger"]["portfolio"].values()), version=5),
                quotes, exit_at + timedelta(seconds=10))["actions"] == 0
    tampered = _row([_record("AAA", status="CLOSED", exit_cause="TARGET", exit_price=55.0, exit_at=exit_at), _record("BBB", quantity=10.12345678)], version=6)
    result = _run(repo, memory, experiment, tampered, quotes, exit_at + timedelta(seconds=15))
    assert result["blocked"] == 1 and result["reasons"] == {"TERMINAL_RECEIPT_PAYLOAD_CONFLICT": 1} and len(repo.memory["trades"]) == 3
    blocked = _rows(memory, experiment)["ep-AAA"]
    assert blocked["status"] == "BLOCKED" and blocked["sell_trade_id"] == rows["ep-AAA"]["sell_trade_id"] and blocked["buy_trade_id"]  # receipts kept
    summary = public_summary(repo=repo, mirror=memory, experiment=experiment, mirror_epoch=MIRROR_EPOCH, epoch=EPOCH, terminal_reasons=[], now=exit_at)
    assert summary["label"] == LABEL and summary["is_evidence"] is False and summary["status_counts"]["BLOCKED"] == 1 and summary["status_counts"]["OPEN"] == 1
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
    # I4: entries are planned after this cycle's exits are durable, so the obligation lifted by the SELL no longer defers BBB
    assert result["buys"] == 1 and rows["ep-BBB"]["status"] == "OPEN"
    result = _run(repo, memory, experiment, _row(closed, version=6), quotes, exit_at + timedelta(minutes=4))
    assert result["actions"] == 0 and result["buys"] == 0 and len(repo.memory["trades"]) == 3


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
    assert memory.write({**row, "status": "BUY_EXECUTING", "claim_token": "other-process", "buy_trade_id": None, "buy_quantity": None, "buy_fill_price": None,
                         "divergence": None}, expected=("OPEN",), insert=False)[1] is True  # a foreign, in-flight claim (test harness)
    result = _run(repo, memory, experiment, ledger, quotes, T0 + timedelta(seconds=2))
    adopted = _rows(memory, experiment)["ep-AAA"]
    assert result["buy_adopted"] == 1 and result["buys"] == 0 and len(repo.memory["trades"]) == 1  # the effect exists: adopted by reading, no second order
    assert adopted["status"] == "OPEN" and adopted["buy_trade_id"] == row["buy_trade_id"] and adopted["claim_token"] is None
    # a claim whose effect never happened is released by compare-and-set of the observed token, then executed once
    fresh_repo, fresh_memory, fresh_experiment = _setup()
    fresh_memory.upsert({"mirror_epoch": MIRROR_EPOCH, "epoch": EPOCH, "episode_key": "ep-AAA", "symbol": "AAA", "market": "NASDAQ",
                         "experiment_id": fresh_experiment["id"], "status": "BUY_EXECUTING", "claim_token": "dead-process",
                         "buy_command_id": command_id(MIRROR_EPOCH, EPOCH, "ep-AAA", "BUY"), "buy_command_sha": None})
    result = _run(fresh_repo, fresh_memory, fresh_experiment, ledger, quotes, T0 + timedelta(seconds=3))
    assert result["released"] == 1 and result["buys"] == 1 and len(fresh_repo.memory["trades"]) == 1
    assert _rows(fresh_memory, fresh_experiment)["ep-AAA"]["status"] == "OPEN"
    # the release is a compare-and-set: a token that is not the observed one is never clobbered
    stale = _rows(fresh_memory, fresh_experiment)["ep-AAA"]
    assert fresh_memory.release(stale, token="not-the-token", from_status="OPEN", to_status="BUY_PENDING", reason="x", now=T0) is False


def test_claim_lost_or_veto_inside_the_effect_transaction_aborts_the_order() -> None:
    # I1: another process releases/takes the claim while this one is between claim and effect: the guard inside the
    # engine's transaction aborts the effect; nothing is executed twice and the row is left to its new owner
    repo, memory, experiment = _setup()
    ledger = _row([_record("AAA", quantity=10.0)])
    key = (MIRROR_EPOCH, EPOCH, "ep-AAA")

    def steal(symbol: str) -> None:
        current = memory.memory[key]
        assert current["status"] == "BUY_EXECUTING" and current["claim_token"]
        memory.release(current, token=current["claim_token"], from_status="BUY_EXECUTING", to_status="BUY_PENDING", reason="OTHER_PROCESS", now=T0)

    # the hook runs during the quote lookup, i.e. after registration... so model the race at the effect: wrap execute_trade
    original = repo.execute_trade

    def racing_execute_trade(*args, **kwargs):
        steal("AAA")
        return original(*args, **kwargs)

    repo.execute_trade = racing_execute_trade  # type: ignore[method-assign]
    result = _run(repo, memory, experiment, ledger, FakeQuotes({"AAA": 50.0}), T0)
    assert result["buys"] == 0 and result["reasons"] == {"CLAIM_LOST_BEFORE_EFFECT": 1} and repo.memory["trades"] == []
    assert _rows(memory, experiment)["ep-AAA"]["status"] == "BUY_PENDING" and _rows(memory, experiment)["ep-AAA"]["claim_token"] is None
    repo.execute_trade = original  # type: ignore[method-assign]
    assert _run(repo, memory, experiment, ledger, FakeQuotes({"AAA": 50.0}), T0 + timedelta(seconds=5))["buys"] == 1 and len(repo.memory["trades"]) == 1
    # I3: the pause flag raised between planning and the effect is re-read inside the effect: no BUY, claim released, retried later
    repo2, memory2, experiment2 = _setup()

    def pause(symbol: str) -> None:
        repo2.memory["experiment"]["entries_paused"] = True

    result = _run(repo2, memory2, experiment2, ledger, FakeQuotes({"AAA": 50.0}, hook=pause), T0)
    row = _rows(memory2, experiment2)["ep-AAA"]
    assert result["buys"] == 0 and result["reasons"] == {"MIRROR_ENTRIES_PAUSED_AT_EFFECT": 1} and repo2.memory["trades"] == []
    assert row["status"] == "BUY_PENDING" and row["claim_token"] is None and row["reason"] == "MIRROR_ENTRIES_PAUSED_AT_EFFECT"
    assert _run(repo2, memory2, experiment2, ledger, FakeQuotes({"AAA": 50.0}), T0 + timedelta(seconds=5))["reasons"] == {"MIRROR_ENTRIES_PAUSED": 1}
    repo2.memory["experiment"]["entries_paused"] = False
    assert _run(repo2, memory2, experiment2, ledger, FakeQuotes({"AAA": 50.0}), T0 + timedelta(seconds=10))["buys"] == 1
    # I3 for the desk order: exits-only raised at the effect is honoured too
    repo3, memory3, experiment3 = _setup()
    result = _run(repo3, memory3, experiment3, ledger, FakeQuotes({"AAA": 50.0}), T0, exits_only=True)
    assert result["buys"] == 0 and result["reasons"] == {"EXITS_ONLY_BY_DESK_ORDER": 1} and repo3.memory["trades"] == []


def test_quote_age_is_measured_after_the_lookup_and_again_at_the_effect() -> None:
    # C2: twenty seconds of I/O during the lookup: the quote is 21 s old when the decision is taken -> no order
    repo, memory, experiment = _setup()
    ledger = _row([_record("AAA", quantity=10.0)])
    state = {"now": T0}

    def slow(symbol: str) -> None:
        state["now"] = state["now"] + timedelta(seconds=20)

    result = _run(repo, memory, experiment, ledger, FakeQuotes({"AAA": 50.0}, hook=slow), T0, clock=lambda: state["now"])
    assert result["buys"] == 0 and result["reasons"] == {"QUOTE_NOT_VALID": 1} and repo.memory["trades"] == []
    assert _rows(memory, experiment) == {}  # nothing was registered on a stale quote
    # the same I/O at the effect (after the claim): the guard re-reads the clock and aborts; the claim is released
    repo2, memory2, experiment2 = _setup()
    state2 = {"now": T0}
    original = repo2.execute_trade

    def slow_effect(*args, **kwargs):
        state2["now"] = state2["now"] + timedelta(seconds=20)
        return original(*args, **kwargs)

    repo2.execute_trade = slow_effect  # type: ignore[method-assign]
    result = _run(repo2, memory2, experiment2, ledger, FakeQuotes({"AAA": 50.0}), T0, clock=lambda: state2["now"])
    row = _rows(memory2, experiment2)["ep-AAA"]
    assert result["buys"] == 0 and result["reasons"] == {"QUOTE_STALE_AT_EFFECT": 1} and repo2.memory["trades"] == []
    assert row["status"] == "BUY_PENDING" and row["claim_token"] is None
    # a fresh quote in the next cycle executes once, and the decision instant is the effect clock, not the cycle start
    repo2.execute_trade = original  # type: ignore[method-assign]
    state2["now"] = T0 + timedelta(minutes=1)
    result = _run(repo2, memory2, experiment2, ledger, FakeQuotes({"AAA": 50.0}), T0, clock=lambda: state2["now"])
    row = _rows(memory2, experiment2)["ep-AAA"]
    assert result["buys"] == 1 and row["status"] == "OPEN" and row["divergence"]["buy"]["decided_at"] == (T0 + timedelta(minutes=1)).isoformat()
    # a quote outside the official session never fills, whatever the feed says
    repo3, memory3, experiment3 = _setup()
    result = _run(repo3, memory3, experiment3, ledger, FakeQuotes({"AAA": 50.0}, regular=False), T0)
    assert result["buys"] == 0 and result["reasons"] == {"QUOTE_NOT_VALID": 1}


def test_payload_conflicts_block_after_open_on_recovery_and_in_the_same_cycle_before_entries() -> None:
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.0, "BBB": 20.0})
    ledger = _row([_record("AAA", quantity=10.0)])
    _run(repo, memory, experiment, ledger, quotes, T0)
    # I4: the ledger presents q11 for the OPEN mirrored q10 AND a new admission in the same cycle: BLOCKED, and no BUY this cycle
    changed = _row([_record("AAA", quantity=11.0), _record("BBB", opened_at=T0 + timedelta(minutes=1))], version=4)
    result = _run(repo, memory, experiment, changed, quotes, T0 + timedelta(minutes=2))
    row = _rows(memory, experiment)["ep-AAA"]
    assert result["blocked"] == 1 and result["buys"] == 0 and row["status"] == "BLOCKED" and row["reason"] == "COMMAND_PAYLOAD_CONFLICT"
    assert result["reasons"] == {"COMMAND_PAYLOAD_CONFLICT": 1, "EXIT_OBLIGATION_BLOCKS_BUYS": 1} and len(repo.memory["trades"]) == 1
    assert {p["symbol"] for p in repo.positions(experiment["id"])} == {"AAA"}
    # the blocked row still holds a position: new BUYs stay blocked in later cycles, and the ledger exit is still honoured
    result = _run(repo, memory, experiment, _row([_record("AAA", quantity=11.0), _record("BBB", opened_at=T0 + timedelta(minutes=1))], version=5), quotes, T0 + timedelta(minutes=3))
    assert result["buys"] == 0 and result["reasons"].get("EXIT_OBLIGATION_BLOCKS_BUYS") == 1
    exit_at = T0 + timedelta(hours=1)
    closing = _row([_record("AAA", quantity=11.0, status="CLOSED", exit_cause="TIME", exit_price=50.0, exit_at=exit_at)], version=6)
    result = _run(repo, memory, experiment, closing, quotes, exit_at + timedelta(seconds=5))
    assert result["sells"] == 1 and _rows(memory, experiment)["ep-AAA"]["status"] == "CLOSED" and repo.positions(experiment["id"]) == []
    # I2 on recovery: a pending row whose registered payload differs from the executed effect is BLOCKED, never adopted
    repo2, memory2, experiment2 = _setup()
    _run(repo2, memory2, experiment2, ledger, quotes, T0)
    row2 = _rows(memory2, experiment2)["ep-AAA"]
    assert memory2.write({**row2, "status": "BUY_PENDING", "buy_command_sha": "0" * 64, "buy_trade_id": None, "divergence": None},
                         expected=("OPEN",), insert=False)[1] is True  # a stale registration with another payload (test harness)
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


def test_memory_scope_and_the_immutable_experiment_binding() -> None:
    repo, memory, experiment = _setup()
    _run(repo, memory, experiment, _row([_record("AAA")]), FakeQuotes({"AAA": 50.0}), T0)
    # C3: another mirror epoch of the same shadow epoch does not inherit this memory
    assert memory.load("R2D2-V2-MIRROR-OTHER", EPOCH, experiment["id"]) == {} and memory.load(MIRROR_EPOCH, EPOCH, "other-experiment") == {}
    assert set(_rows(memory, experiment)) == {"ep-AAA"}
    with pytest.raises(MirrorInputError, match="MIRROR_ROW_SCOPE_MISSING"):
        memory.upsert({"epoch": EPOCH, "episode_key": "x", "symbol": "X", "status": "SKIPPED"})
    # C3: the experiment is bound to one (mirror epoch, shadow epoch) at creation; reuse by another mirror or shadow epoch is refused
    with pytest.raises(MirrorInputError, match="MIRROR_EXPERIMENT_BOUND_TO_ANOTHER_MIRROR"):
        ensure_mirror_experiment(repo, code="R2D2-V2-MIRROR-001", epoch=EPOCH, mirror_epoch="R2D2-V2-MIRROR-OTHER")
    with pytest.raises(MirrorInputError, match="MIRROR_EXPERIMENT_BOUND_TO_ANOTHER_MIRROR"):
        ensure_mirror_experiment(repo, code="R2D2-V2-MIRROR-001", epoch="R2D2-V2-SHADOW-OTHER", mirror_epoch=MIRROR_EPOCH)
    assert ensure_mirror_experiment(repo, code="R2D2-V2-MIRROR-001", epoch=EPOCH, mirror_epoch=MIRROR_EPOCH)["mandate"]["mirror_epoch"] == MIRROR_EPOCH
    with pytest.raises(MirrorInputError, match="MIRROR_EXPERIMENT_BOUND_TO_ANOTHER_MIRROR"):
        run_once(ledger_row=_row([_record("AAA")]), mirror_epoch="R2D2-V2-MIRROR-OTHER", repo=repo, mirror=memory, experiment=experiment,
                 quotes=FakeQuotes({"AAA": 50.0}), resolve_market=_resolve, now=T0 + timedelta(minutes=1), activated_at=ACTIVATED)
    # C3: a row never changes experiment
    row = _rows(memory, experiment)["ep-AAA"]
    with pytest.raises(MirrorInputError, match="MIRROR_ROW_EXPERIMENT_IMMUTABLE"):
        memory.upsert({**row, "experiment_id": "another-experiment"})
    assert _rows(memory, experiment)["ep-AAA"]["experiment_id"] == experiment["id"]
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


def test_release_receipt_binds_publication_and_cursor_to_an_official_session_open() -> None:
    body = {"schema": "R2D2_V2_MIRROR_RELEASE_V1", "mirror_epoch": MIRROR_EPOCH, "epoch": EPOCH, "experiment_code": "R2D2-V2-MIRROR-001",
            "code_revision": "abc123", "review_sha": "f" * 64, "owner_order_ref": "#348 5563247154", "initial_session": "2026-09-14",
            "published_at": (ACTIVATED - timedelta(hours=2)).isoformat(), "initial_cursor_at": ACTIVATED.isoformat(),
            "signatures": [{"party": "CODEX"}, {"party": "FABLE"}, {"party": "DUDU"}]}
    data = json.dumps(body).encode()
    sha = hashlib.sha256(data).hexdigest()
    release = MirrorRelease.verify(data, sha, build_sha="abc123", now=T0)
    assert release.epoch == EPOCH and release.initial_cursor_at == ACTIVATED and release.published_at == ACTIVATED - timedelta(hours=2)
    assert release.initial_session == date(2026, 9, 14)
    early = json.dumps({**body, "initial_cursor_at": (ACTIVATED - timedelta(hours=1)).isoformat()}).encode()  # cursor before the open is fine
    assert MirrorRelease.verify(early, hashlib.sha256(early).hexdigest(), build_sha="abc123", now=T0).initial_session == date(2026, 9, 14)
    labor_day = datetime(2026, 9, 7, 13, 30, tzinfo=timezone.utc)
    sunday = datetime(2026, 9, 13, 13, 30, tzinfo=timezone.utc)
    for change, code in [({"code_revision": "other"}, "MIRROR_RELEASE_CODE_REVISION_MISMATCH"),
                         ({"signatures": [{"party": "FABLE"}, {"party": "DUDU"}]}, "MIRROR_RELEASE_SIGNATURES_INCOMPLETE"),
                         ({"initial_cursor_at": (T0 + timedelta(days=1)).isoformat(), "published_at": (T0 + timedelta(days=1)).isoformat(),
                           "initial_session": "2026-09-15"}, "MIRROR_RELEASE_CURSOR_AFTER_OPEN"),
                         ({"published_at": (ACTIVATED + timedelta(hours=1)).isoformat()}, "MIRROR_RELEASE_PUBLISHED_AFTER_CURSOR"),  # published at 11h ET
                         ({"initial_cursor_at": datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc).isoformat()}, "MIRROR_RELEASE_CURSOR_AFTER_OPEN"),  # 11:00 New York
                         ({"mirror_epoch": "R2D2-90D-001"}, "MIRROR_RELEASE_MIRROR_EPOCH_INVALID"),
                         # C4: the official calendar governs — a holiday, a Sunday, a publication exactly at the open, a session that is not the cursor's
                         ({"initial_cursor_at": labor_day.isoformat(), "published_at": (labor_day - timedelta(hours=2)).isoformat(),
                           "initial_session": "2026-09-07"}, "MIRROR_RELEASE_CURSOR_NOT_A_SESSION"),
                         ({"initial_cursor_at": sunday.isoformat(), "published_at": (sunday - timedelta(hours=2)).isoformat(),
                           "initial_session": "2026-09-13"}, "MIRROR_RELEASE_CURSOR_NOT_A_SESSION"),
                         ({"published_at": ACTIVATED.isoformat()}, "MIRROR_RELEASE_PUBLISHED_NOT_BEFORE_OPEN"),
                         ({"initial_session": "2026-09-15"}, "MIRROR_RELEASE_INITIAL_SESSION_MISMATCH"),
                         ({"initial_session": None}, "MIRROR_RELEASE_INITIAL_SESSION_MISSING"),
                         ({"initial_session": "15/09/2026"}, "MIRROR_RELEASE_INITIAL_SESSION_MISSING")]:
        altered = json.dumps({**body, **change}).encode()
        with pytest.raises(MirrorInputError, match=code):
            MirrorRelease.verify(altered, hashlib.sha256(altered).hexdigest(), build_sha="abc123", now=T0)
    missing = json.dumps({k: v for k, v in body.items() if k != "published_at"}).encode()
    with pytest.raises(MirrorInputError, match="LEDGER_TIMESTAMP_INVALID"):
        MirrorRelease.verify(missing, hashlib.sha256(missing).hexdigest(), build_sha="abc123", now=T0)
    future = json.dumps({**body, "published_at": (T0 + timedelta(days=1)).isoformat(), "initial_cursor_at": (T0 + timedelta(days=1)).isoformat()}).encode()
    with pytest.raises(MirrorInputError, match="MIRROR_RELEASE_CURSOR_AFTER_OPEN|MIRROR_RELEASE_NOT_YET_ACTIVE|MIRROR_RELEASE_INITIAL_SESSION_MISMATCH"):
        MirrorRelease.verify(future, hashlib.sha256(future).hexdigest(), build_sha="abc123", now=T0)
    not_yet = json.dumps({**body, "initial_session": "2026-09-15", "published_at": datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc).isoformat(),
                          "initial_cursor_at": datetime(2026, 9, 15, 13, 30, tzinfo=timezone.utc).isoformat()}).encode()
    with pytest.raises(MirrorInputError, match="MIRROR_RELEASE_NOT_YET_ACTIVE"):
        MirrorRelease.verify(not_yet, hashlib.sha256(not_yet).hexdigest(), build_sha="abc123", now=T0)
    with pytest.raises(MirrorInputError, match="MIRROR_RELEASE_SHA_MISMATCH"):
        MirrorRelease.verify(data, "0" * 64, build_sha="abc123", now=T0)


def test_registration_never_reopens_a_command_executed_by_another_worker_in_the_lock_window() -> None:
    # Codex #387 round 3, I1: worker A read the ledger and the mirror (no row yet), looked a quote up and got suspended; worker B
    # registered, claimed and executed the same command and committed its OPEN receipt. When A resumes, its registration must
    # read-and-compare, never insert-or-overwrite: one trade, quantity 10 for a command of 10, and A defers.
    repo, memory, experiment = _setup()
    ledger = _row([_record("AAA", quantity=10.0)])
    view = read_ledger(ledger)
    record = view.records[0]
    quotes = FakeQuotes({"AAA": 50.0})

    def worker_b(symbol: str) -> None:
        if quotes.calls == 1:  # inside A's quote lookup, before A's registration
            execute([Action("BUY", record, "LEDGER_ADMISSION_RECORDED", record.episode_key)], ledger=view, mirror_epoch=MIRROR_EPOCH, repo=repo,
                    mirror=memory, experiment=experiment, cycle_id=repo.start_cycle(experiment["id"], ["NASDAQ", "NYSE"]),
                    quotes=FakeQuotes({"AAA": 50.0}), resolve_market=_resolve, now=T0)

    quotes.hook = worker_b
    result = _run(repo, memory, experiment, ledger, quotes, T0)
    assert result["buys"] == 0 and result["deferred"] == 1 and result["reasons"] == {"COMMAND_ALREADY_ADVANCED": 1}
    trades = repo.memory["trades"]
    assert len(trades) == 1 and trades[0]["quantity"] == 10.0
    row = _rows(memory, experiment)["ep-AAA"]
    assert row["status"] == "OPEN" and row["buy_trade_id"] == trades[0]["id"] and row["claim_token"] is None
    assert [p["quantity"] for p in repo.positions(experiment["id"])] == [10.0]
    # the next cycle reads the receipt and has nothing to do: no replay, no second token
    again = _run(repo, memory, experiment, ledger, quotes, T0 + timedelta(seconds=5))
    assert again["actions"] == 0 and len(repo.memory["trades"]) == 1


def test_conditional_writes_never_overwrite_a_row_advanced_elsewhere() -> None:
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.0})
    _run(repo, memory, experiment, _row([_record("AAA", quantity=10.0)]), quotes, T0)
    row = _rows(memory, experiment)["ep-AAA"]
    assert row["status"] == "OPEN"
    # a stale worker that still believes the command is pending cannot rewrite the OPEN receipt
    current, applied = memory.write({**row, "status": "BUY_PENDING", "claim_token": None, "buy_trade_id": None}, expected=("BUY_PENDING",), insert=True)
    assert applied is False and current["status"] == "OPEN" and current["buy_trade_id"] == row["buy_trade_id"]
    with pytest.raises(MirrorInputError, match="MIRROR_ROW_ADVANCED_ELSEWHERE"):
        memory.upsert({**row, "status": "BUY_PENDING", "claim_token": None, "buy_trade_id": None})
    # an exit obligation is only written over the OPEN/BLOCKED row that was read: a row CLOSED meanwhile stays CLOSED
    closed, applied = memory.write({**row, "status": "CLOSED", "reason": "closed-elsewhere"}, expected=("OPEN",), insert=False)
    assert applied is True and closed["status"] == "CLOSED"
    current, applied = memory.write({**row, "status": "EXIT_PENDING", "reason": "stale-worker"}, expected=("OPEN", "BLOCKED"), insert=False)
    assert applied is False and current["status"] == "CLOSED"
    # an update-only write of an absent row writes nothing
    assert memory.write({**row, "episode_key": "ep-ZZZ", "status": "EXIT_PENDING"}, expected=("OPEN",), insert=False) == (None, False)
    # execute(): a SELL planned for a row that another worker CLOSED between the read and the write is deferred, never executed
    exit_at = T0 + timedelta(hours=1)
    ledger = _row([_record("AAA", status="CLOSED", exit_cause="TARGET", exit_price=54.2, exit_at=exit_at, quantity=10.0)], version=4)
    memory.write({**closed, "status": "OPEN", "reason": "restored-for-the-test"}, expected=("CLOSED",), insert=False)
    view = read_ledger(ledger)
    record = view.records[0]
    mirrored = _rows(memory, experiment)
    memory.write({**mirrored["ep-AAA"], "status": "CLOSED", "reason": "closed-by-another-worker"}, expected=("OPEN",), insert=False)
    summary = execute([Action("SELL", record, "LEDGER_EXIT_RECORDED:TARGET", record.episode_key)], ledger=view, mirror_epoch=MIRROR_EPOCH, repo=repo,
                      mirror=memory, experiment=experiment, cycle_id=repo.start_cycle(experiment["id"], ["NASDAQ", "NYSE"]), quotes=quotes,
                      resolve_market=_resolve, now=exit_at + timedelta(seconds=5))
    assert summary["sells"] == 0 and summary["reasons"] == {"COMMAND_ALREADY_ADVANCED": 1}
    assert _rows(memory, experiment)["ep-AAA"]["status"] == "CLOSED" and len(repo.memory["trades"]) == 1


def test_source_marked_cap_excess_vetoes_new_buys_but_never_exits() -> None:
    # I5c: the generator's global marking veto (#383 `_admission`: gross > 48 % of NAV, cash < 5 % of NAV, any OPEN position marked
    # above 6 % of NAV) is inherited from the state the ledger publishes, in that order, with q and the paper caps untouched.
    view = read_ledger(_row([_record("AAA", quantity=1400.0, mark=50.0)]))  # 70 000 marked on a 1 M NAV: above 6 %
    assert view.source_vetoes == ("MARKED_CAP_EXCESS",) and view.vetoed
    assert source_admission_vetoes(_row([_record("AAA", quantity=1000.0, mark=50.0)])["state"]["ledger"]) == ()  # 50 000 = 5 %: admitted
    ten = [_record(f"S{index}", quantity=1000.0, mark=50.0) for index in range(10)]  # gross 500 000 > 48 % of NAV
    assert source_admission_vetoes(_row(ten)["state"]["ledger"]) == ("MARKED_CAP_EXCESS",)
    # cash < 5 % of NAV with gross within 48 % and no position above 6 %: only possible with unpaid receivables in the NAV
    eight = [_record(f"S{index}", quantity=100.0, mark=50.0) for index in range(8)]  # gross 40 000
    eight[0]["receivables"] = {"div": {"amount": 56_000.0, "paid": False}}  # NAV = 4 000 cash + 40 000 + 56 000 = 100 000
    assert source_admission_vetoes(_row(eight, cash=4_000.0, session_start_nav=100_000.0)["state"]["ledger"]) == ("MARKED_CAP_EXCESS",)
    assert source_admission_vetoes(_row([_record("AAA", quantity=1000.0, mark=50.0)], session_start_nav=2_000_000.0)["state"]["ledger"]) == ("DAILY_LOSS_LIMIT",)  # order preserved
    # exits keep flowing while the veto is in force; new BUYs are deferred by the ledger's own admission veto
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.0, "BBB": 30.0, "CCC": 50.0})
    _run(repo, memory, experiment, _row([_record("AAA", quantity=100.0)]), quotes, T0)
    exit_at = T0 + timedelta(hours=1)
    ledger = _row([_record("AAA", status="CLOSED", exit_cause="TARGET", exit_price=54.2, exit_at=exit_at, quantity=100.0),
                   _record("CCC", quantity=1400.0, mark=50.0, opened_at=exit_at - timedelta(minutes=5)), _record("BBB", opened_at=exit_at)], version=4)
    result = _run(repo, memory, experiment, ledger, quotes, exit_at + timedelta(seconds=5))
    assert result["sells"] == 1 and result["buys"] == 0 and result["source_vetoes"] == ["MARKED_CAP_EXCESS"]
    assert result["reasons"]["LEDGER_ADMISSION_VETO:MARKED_CAP_EXCESS"] == 2  # BBB and CCC deferred, nothing skipped permanently
    rows = _rows(memory, experiment)
    assert rows["ep-AAA"]["status"] == "CLOSED" and "ep-BBB" not in rows and "ep-CCC" not in rows


def test_effect_instant_is_measured_after_the_guards_not_before_the_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    # C2: time spent inside the guards (row locks, claim check, veto/quote re-read) never predates the effect: executed_at,
    # the receipt's mirror_at and the position clocks are read AFTER the guards.
    import time as _time
    original = MirrorRepository.guard

    def slow_guard(self, connection, row, *, token, status):
        _time.sleep(0.3)
        return original(self, connection, row, token=token, status=status)

    monkeypatch.setattr(MirrorRepository, "guard", slow_guard)
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.0})
    real_clock = lambda: datetime.now(timezone.utc)  # noqa: E731
    result = _run(repo, memory, experiment, _row([_record("AAA", quantity=10.0)]), quotes, real_clock(), clock=real_clock)
    assert result["buys"] == 1
    row = _rows(memory, experiment)["ep-AAA"]
    trade = repo.memory["trades"][0]
    decided_at = datetime.fromisoformat(row["divergence"]["buy"]["decided_at"])
    assert trade["executed_at"] - decided_at >= timedelta(seconds=0.3)
    assert row["buy_at"] == trade["executed_at"] and datetime.fromisoformat(row["divergence"]["buy"]["mirror_at"]) == trade["executed_at"]
    assert repo.positions(experiment["id"])[0]["opened_at"] == trade["executed_at"]


def test_cycle_status_is_supported_and_no_v1_decision_row_is_written() -> None:
    # PG-S2 / PG-S1: r2d2_cycles admits succeeded/partial/failed (never `completed`); the mirror has no V1 score and writes no
    # r2d2_decisions row — its audit record is the receipt and the trade's decision_snapshot, committed together.
    repo, memory, experiment = _setup()
    quotes = FakeQuotes({"AAA": 50.0})
    ledger = _row([_record("AAA", quantity=10.0)])
    result = _run(repo, memory, experiment, ledger, quotes, T0)
    assert result["cycle_status"] == "succeeded" and repo.memory["cycles"][-1]["status"] == "succeeded"
    assert repo.memory["decisions"] == [] and repo.memory["trades"][0]["decision_snapshot"]["command_id"]
    tampered = _row([_record("AAA", quantity=11.0)], version=4)  # payload conflict → BLOCK → partial
    result = _run(repo, memory, experiment, tampered, quotes, T0 + timedelta(seconds=5))
    assert result["blocked"] == 1 and result["cycle_status"] == "partial" and repo.memory["cycles"][-1]["status"] == "partial"
    assert all(cycle["status"] in ("succeeded", "partial", "failed") for cycle in repo.memory["cycles"])


def test_worker_is_off_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("C3PO_R2D2_V2_MIRROR_ENABLED", raising=False)
    assert mirror_module.main([]) == 0
    assert '"status":"OFF"' in capsys.readouterr().out
