from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from app import r2d2_wind_down
from app.config import Settings
from app.database import Database
from app.r2d2 import (
    R2D2PaperService,
    R2D2Repository,
    SAO_PAULO,
    _paper_exit_execution,
    _trade_is_strategy_excluded,
)
from app.r2d2_wind_down import R2D2WindDownService, WindDownPreconditionError


OPEN = datetime(2026, 8, 25, 13, 30, 30, tzinfo=timezone.utc)


def _settings() -> Settings:
    return Settings(
        database_url="",
        r2d2_start_date="2026-08-17",
        r2d2_checkpoint_days=90,
        r2d2_starting_capital_usd=1_000_000,
        r2d2_live_quote_max_age_seconds=90,
    )


def _seed_position(
    *,
    mark: float = 90.0,
    quote_as_of: datetime | None = None,
    decision_state: str = "hold",
    paused: bool = True,
) -> tuple[Settings, Database, R2D2Repository, dict[str, object]]:
    settings = _settings()
    database = Database(settings)
    repository = R2D2Repository(database)
    experiment = repository.ensure_experiment(settings)
    cycle_id = repository.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ",
        "symbol": "WDWN",
        "name": "Wind Down Test",
        "currency": "USD",
        "stop_price": 98.0,
    }
    repository.execute_trade(
        experiment,
        cycle_id=cycle_id,
        candidate=candidate,
        side="BUY",
        quantity=10.0,
        signal_price=100.0,
        fill_price=100.0,
        fx=1.0,
        fees=0.0,
        slippage=0.0,
        reason="Organic strategy entry",
        decision={"paper_only": True},
        quote_as_of=OPEN - timedelta(minutes=10),
    )
    repository.finish_cycle(cycle_id, "succeeded", 1, 1, 1)
    position = repository.memory["positions"][("NASDAQ", "WDWN")]
    position.update({
        "last_price_local": mark,
        "updated_at": OPEN - timedelta(seconds=3),
        "strategy_snapshot": {
            "quote_status": "live",
            "quote_as_of": (quote_as_of or OPEN - timedelta(seconds=2)).isoformat(),
            "decision_state": decision_state,
            "defense_streak": 4,
            "defense_reductions": 1,
        },
    })
    if paused:
        repository.set_entries_paused(
            experiment["code"],
            paused=True,
            operator="Dudu",
            reason="Six-hands review",
            changed_at=OPEN - timedelta(minutes=1),
        )
    return settings, database, repository, experiment


def test_wind_down_plan_is_read_only_and_uses_normal_sell_friction() -> None:
    settings, database, repository, _ = _seed_position(mark=105.0)
    service = R2D2WindDownService(settings, repository, clock=lambda: OPEN)
    before = {
        "positions": repository.positions(repository.memory["experiment"]["id"]),
        "trades": list(repository.memory["trades"]),
        "cycles": list(repository.memory["cycles"]),
        "events": list(database._audit_events),
    }

    plan = service.plan(operator="Dudu", reason="Approved administrative wind-down")

    expected = _paper_exit_execution(market="NASDAQ", price=105.0, quantity=10.0, fx=1.0)
    assert plan["mode"] == "plan"
    assert plan["ready_for_execute"] is True
    assert plan["state_change_required"] is True
    assert plan["position_count"] == 1
    assert plan["positions"][0]["fill_price_local"] == pytest.approx(expected["fill_price"])
    assert plan["positions"][0]["fees_usd"] == pytest.approx(expected["fees_usd"])
    assert plan["positions"][0]["slippage_usd"] == pytest.approx(expected["slippage_usd"])
    assert len(plan["plan_sha256"]) == 64
    assert repository.positions(repository.memory["experiment"]["id"]) == before["positions"]
    assert repository.memory["trades"] == before["trades"]
    assert repository.memory["cycles"] == before["cycles"]
    assert database._audit_events == before["events"]


def test_wind_down_executes_only_sells_and_separates_accounting_from_strategy() -> None:
    settings, database, repository, experiment = _seed_position(mark=90.0)
    service = R2D2WindDownService(settings, repository, clock=lambda: OPEN)

    result = service.execute(
        operator="Dudu",
        reason="Six-hands decision on 24/08 exit-policy evidence",
    )

    assert result["executed"] is True
    assert result["trade_count"] == 1
    assert result["remaining_positions"] == 0
    assert result["entries_paused"] is True
    assert result["experiment_status"] == "running"
    assert repository.positions(experiment["id"]) == []
    current = repository.experiment(experiment["code"])
    assert current is not None
    assert current["entries_paused"] is True
    assert current["status"] == "running"

    trades = repository.trades(experiment["id"])
    assert [item["side"] for item in trades] == ["SELL", "BUY"]
    sell = trades[0]
    assert sell["decision_snapshot"]["operator_wind_down"]["operator"] == "Dudu"
    assert sell["decision_snapshot"]["operator_wind_down"]["full_position"] is True
    assert sell["decision_snapshot"]["strategy_excluded"] is True
    assert _trade_is_strategy_excluded(sell) is True
    assert sell["fill_price_local"] == pytest.approx(89.91)
    assert sell["realized_pnl_usd"] < 0

    realized_sessions = repository.realized_pnl_by_session(experiment["id"])
    assert len(realized_sessions) == 1
    assert realized_sessions[0]["realized_pnl_usd"] == pytest.approx(sell["realized_pnl_usd"])
    assert repository.strategy_realized_pnl_by_session(experiment["id"]) == []
    assert repository.trade_summary(experiment["id"]) == {
        "total_transactions": 1,
        "positive_transactions": 0,
        "negative_transactions": 0,
    }
    assert repository.daily_learning_curve(experiment["id"]) == []
    assert repository.loss_exit_on_session(
        experiment["id"],
        "NASDAQ",
        "WDWN",
        sell["executed_at"].astimezone(SAO_PAULO).date(),
    ) is False

    events = database.list_audit_events(action="r2d2.operator_wind_down")
    assert len(events) == 1
    assert events[0]["actor"] == "Dudu"
    assert events[0]["detail"]["trade_ids"] == [sell["id"]]
    assert events[0]["detail"]["remaining_positions"] == 0

    repeated = service.execute(
        operator="Dudu",
        reason="Six-hands decision on 24/08 exit-policy evidence",
    )
    assert repeated["idempotent_noop"] is True
    assert repeated["trade_count"] == 0
    assert len(repository.trades(experiment["id"])) == 2
    assert len(database.list_audit_events(action="r2d2.operator_wind_down")) == 1

    repository.save_snapshot(
        experiment["id"],
        sell["executed_at"].astimezone(SAO_PAULO).date(),
        _settings().r2d2_starting_capital_usd + sell["realized_pnl_usd"],
        repository.experiment(experiment["code"])["cash_balance"],
        0.0,
        0,
        True,
    )
    learning_service = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    learning = learning_service._ensure_daily_learning(
        repository.experiment(experiment["code"]),
        sell["executed_at"].astimezone(SAO_PAULO).date() + timedelta(days=1),
    )
    assert learning["sample_trades"] == 0
    assert learning["metrics"]["average_daily_return_percent"] == 0.0


@pytest.mark.parametrize(
    ("paused", "quote_as_of", "now", "message"),
    [
        (False, OPEN - timedelta(seconds=2), OPEN, "new entries are not paused"),
        (True, OPEN - timedelta(seconds=91), OPEN, "maximum is 90s"),
        (True, OPEN - timedelta(seconds=2), OPEN - timedelta(minutes=1), "session is not open"),
    ],
)
def test_wind_down_fails_closed_before_any_sell(
    paused: bool,
    quote_as_of: datetime,
    now: datetime,
    message: str,
) -> None:
    settings, database, repository, experiment = _seed_position(
        paused=paused,
        quote_as_of=quote_as_of,
    )
    service = R2D2WindDownService(settings, repository, clock=lambda: now)

    with pytest.raises(WindDownPreconditionError, match=message):
        service.execute(operator="Dudu", reason="Approved wind-down")

    assert len(repository.positions(experiment["id"])) == 1
    assert [item["side"] for item in repository.trades(experiment["id"])] == ["BUY"]
    assert database.list_audit_events(action="r2d2.operator_wind_down") == []


def test_wind_down_rejects_a_quote_under_anomaly_validation() -> None:
    settings, _, repository, experiment = _seed_position(decision_state="validating quote")
    service = R2D2WindDownService(settings, repository, clock=lambda: OPEN)

    with pytest.raises(WindDownPreconditionError, match="under protection state"):
        service.execute(operator="Dudu", reason="Approved wind-down")

    assert len(repository.positions(experiment["id"])) == 1
    assert [item["side"] for item in repository.trades(experiment["id"])] == ["BUY"]


def test_wind_down_cli_is_plan_first(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings, _, repository, experiment = _seed_position(mark=102.0)
    service = R2D2WindDownService(settings, repository, clock=lambda: OPEN)
    monkeypatch.setattr(r2d2_wind_down, "Settings", lambda: settings)
    monkeypatch.setattr(
        r2d2_wind_down,
        "R2D2WindDownService",
        lambda _settings, _repository: service,
    )
    arguments = ["--operator", "Dudu", "--reason", "Approved wind-down"]

    assert r2d2_wind_down.main(arguments) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["mode"] == "plan"
    assert planned["state_change_required"] is True
    assert len(repository.positions(experiment["id"])) == 1

    assert r2d2_wind_down.main([*arguments, "--execute"]) == 0
    executed = json.loads(capsys.readouterr().out)
    assert executed["mode"] == "execute"
    assert executed["remaining_positions"] == 0
    assert len(repository.positions(experiment["id"])) == 0
