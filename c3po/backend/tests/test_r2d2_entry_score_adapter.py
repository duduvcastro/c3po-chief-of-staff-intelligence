from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import r2d2_entry_control
from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2PaperService, R2D2Repository
from app.r2d2_entry_score_adapter import ADAPTER_VERSION, R2D2EntryScoreAdapter


def _settings(*, adapter_enabled: bool = False) -> Settings:
    return Settings(
        database_url="",
        r2d2_start_date="2026-08-17",
        r2d2_entry_score_adapter_enabled=adapter_enabled,
    )


def _seed(
    database: Database,
    analysis_type: str,
    entity_key: str,
    outputs: dict,
    published_at: datetime,
) -> str:
    methodology_id = database.ensure_methodology_version(
        f"test-{analysis_type}", 1, {}, "entry-score adapter test",
    )
    return database.save_analysis_snapshot(
        analysis_type,
        entity_key,
        methodology_id,
        {"available_at": published_at.isoformat()},
        outputs,
        published_at,
    )


def _candidate(symbol: str, *, price: float, composite: float) -> dict:
    return {
        "market": "NASDAQ",
        "symbol": symbol,
        "price": price,
        "quote_as_of": datetime(2026, 8, 26, 13, 59, tzinfo=timezone.utc),
        "quote_status": "live",
        "valuation_basis": "canonical C3PO valuation universe",
        "composite_score": composite,
        "fundamental_score": composite + 2,
        "technical_score": composite - 3,
        "risk_score": 40,
        "pretrade_rank": composite + 1,
        "raw_cash_volume_usd": 42_000_000,
        "spread_bps": None,
        "technical_reviewed": True,
    }


def test_entry_score_adapter_uses_only_causal_nightly_sources_and_never_ab_as_v3() -> None:
    settings = _settings(adapter_enabled=True)
    database = Database(settings)
    repository = R2D2Repository(database)
    experiment = repository.ensure_experiment(settings)
    cycle_id = repository.start_cycle(experiment["id"], ["NASDAQ"])
    decision_at = datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc)
    source_at = decision_at - timedelta(hours=2)

    canonical_id = _seed(database, "valuation_universe", "NASDAQ_UNIVERSE", {
        "rows": [
            {"symbol": "AAA", "our_tp": 130.0},
            {"symbol": "BBB", "our_tp": 110.0},
        ],
    }, source_at)
    _seed(database, "valuation_v2_data", "NASDAQ_V2_DATA", {"packets": {}}, source_at)
    _seed(database, "valuation_v2_peer_quality", "US_V2_PEER_QUALITY", {"graph": {}}, source_at)
    v2_id = _seed(database, "valuation_v2_shadow", "NASDAQ_V2_SHADOW", {
        "results": {
            "AAA": {"v2_tp": 120.0},
            "BBB": {"v2_tp": 140.0},
        },
    }, source_at)
    _seed(database, "valuation_v3_ab_report", "AB-2026-08-24", {
        "results": {"AAA": {"v3_tp": 999.0}},
    }, source_at)
    # A later V2 snapshot exists in the database but was not available at the
    # decision. The adapter must retain the earlier source above.
    _seed(database, "valuation_v2_shadow", "NASDAQ_V2_SHADOW", {
        "results": {"AAA": {"v2_tp": 999.0}, "BBB": {"v2_tp": 1.0}},
    }, decision_at + timedelta(minutes=1))

    result = R2D2EntryScoreAdapter(database).record_cycle(
        experiment_id=experiment["id"],
        cycle_id=cycle_id,
        policy_epoch="policy-a-resume-2026-08-26",
        candidates=[
            _candidate("AAA", price=100.0, composite=80),
            _candidate("BBB", price=100.0, composite=70),
        ],
        decision_at=decision_at,
    )

    observations = R2D2EntryScoreAdapter(database).observations()
    assert result["written"] == 2
    assert len(observations) == 2
    aaa = next(item for item in observations if item["symbol"] == "AAA")
    bbb = next(item for item in observations if item["symbol"] == "BBB")
    assert aaa["source_references"]["canonical"]["snapshot_id"] == canonical_id
    assert aaa["source_references"]["v2_shadow"]["snapshot_id"] == v2_id
    assert len(aaa["source_references"]["v2_shadow"]["snapshot_sha256"]) == 64
    assert aaa["source_references"]["v3_shadow"] == {
        "status": "not_persisted",
        "ab_report_eligible": False,
    }
    assert aaa["valuation_comparisons"]["canonical"] == {
        "upside_percent": 30.0,
        "rank_percentile": 100.0,
    }
    assert bbb["valuation_comparisons"]["v2_shadow"] == {
        "upside_percent": 40.0,
        "rank_percentile": 100.0,
    }
    assert aaa["valuation_comparisons"]["v3_shadow"]["upside_percent"] is None
    assert aaa["raw_cash_volume_usd"] == 42_000_000
    assert aaa["spread_bps"] is None


def test_entry_score_adapter_excludes_source_not_yet_available_at_decision() -> None:
    settings = _settings(adapter_enabled=True)
    database = Database(settings)
    repository = R2D2Repository(database)
    experiment = repository.ensure_experiment(settings)
    cycle_id = repository.start_cycle(experiment["id"], ["NASDAQ"])
    decision_at = datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc)
    source_at = decision_at - timedelta(hours=1)
    _seed(database, "valuation_v2_shadow", "NASDAQ_V2_SHADOW", {
        "available_at": (decision_at + timedelta(seconds=1)).isoformat(),
        "results": {"AAA": {"v2_tp": 150.0}},
    }, source_at)

    R2D2EntryScoreAdapter(database).record_cycle(
        experiment_id=experiment["id"],
        cycle_id=cycle_id,
        policy_epoch="policy-a-resume-2026-08-26",
        candidates=[_candidate("AAA", price=100.0, composite=80)],
        decision_at=decision_at,
    )

    observation = R2D2EntryScoreAdapter(database).observations()[0]
    assert observation["source_references"]["v2_shadow"]["status"] == "not_yet_available"
    assert observation["source_references"]["v2_shadow"]["causal_at_decision"] is False
    assert observation["valuation_comparisons"]["v2_shadow"]["upside_percent"] is None


def test_entry_score_adapter_materializes_unchanged_snapshot_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(adapter_enabled=True)
    database = Database(settings)
    repository = R2D2Repository(database)
    experiment = repository.ensure_experiment(settings)
    decision_at = datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc)
    _seed(database, "valuation_universe", "NASDAQ_UNIVERSE", {
        "rows": [{"symbol": "AAA", "our_tp": 130.0}],
    }, decision_at - timedelta(hours=1))
    original = database.analysis_snapshot_at_or_before
    full_reads: list[tuple[str, str]] = []

    def counted(analysis_type: str, entity_key: str, cutoff: datetime) -> dict | None:
        full_reads.append((analysis_type, entity_key))
        return original(analysis_type, entity_key, cutoff)

    monkeypatch.setattr(database, "analysis_snapshot_at_or_before", counted)
    adapter = R2D2EntryScoreAdapter(database)
    for offset in range(2):
        adapter.record_cycle(
            experiment_id=experiment["id"],
            cycle_id=repository.start_cycle(experiment["id"], ["NASDAQ"]),
            policy_epoch="policy-a-resume-2026-08-26",
            candidates=[_candidate("AAA", price=100.0, composite=80)],
            decision_at=decision_at + timedelta(minutes=offset),
        )

    assert full_reads == [("valuation_universe", "NASDAQ_UNIVERSE")]


def test_entry_score_adapter_failure_is_visible_but_does_not_block_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(adapter_enabled=True)
    settings.r2d2_max_daily_orders = 0
    service = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    experiment = service.ensure_initialized()
    service.repo.memory["experiment"].update({
        "policy_epoch": "policy-a-resume-2026-08-26",
        "policy_epoch_started_at": datetime(2026, 8, 26, 13, 30, tzinfo=timezone.utc),
        "entry_score_adapter_version": ADAPTER_VERSION,
        "entry_score_adapter_enabled_at": datetime(2026, 8, 26, 13, 30, tzinfo=timezone.utc),
    })
    candidate = {
        **_candidate("FAIL", price=100.0, composite=80),
        "name": "Failure Test",
        "currency": "USD",
        "stop_price": 99.0,
    }
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._mark_and_exit = lambda *args, **kwargs: 0  # type: ignore[method-assign]
    service._us_candidates = (  # type: ignore[method-assign]
        lambda market, now: [candidate] if market == "NASDAQ" else []
    )
    service._enrich_technicals = lambda candidates, **kwargs: None  # type: ignore[method-assign]
    monkeypatch.setattr(
        service._entry_score_adapter,
        "record_cycle",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("append-only sink unavailable")),
    )

    dashboard = service.run_cycle(datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc))

    assert dashboard.open_positions == 0
    assert dashboard.last_cycle is not None
    assert dashboard.last_cycle.status == "partial"
    assert dashboard.last_cycle.metadata["entry_score_adapter"]["irrecoverable_gap"] is True
    assert dashboard.entry_score_adapter_status == "degraded"
    events = service.repo.database.list_audit_events(action="r2d2.entry_score_adapter_degraded")
    assert len(events) == 1
    assert events[0]["detail"]["failed"] == 1


def test_dashboard_uses_persisted_epoch_then_defers_to_worker_cycle_truth() -> None:
    settings = _settings(adapter_enabled=False)
    service = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    experiment = service.ensure_initialized()
    service.repo.memory["experiment"].update({
        "entries_paused": True,
        "policy_epoch": "policy-a-resume-2026-08-26",
        "entry_score_adapter_version": ADAPTER_VERSION,
    })

    armed = service.dashboard()

    assert armed.entry_score_adapter_enabled is True
    assert armed.entry_score_adapter_status == "armed"
    assert armed.entry_score_adapter_version == ADAPTER_VERSION

    service.repo.memory["experiment"]["entries_paused"] = False
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    service.repo.finish_cycle(
        cycle_id,
        "succeeded",
        0,
        0,
        0,
        metadata={
            "entry_score_adapter": {
                "enabled": False,
                "version": ADAPTER_VERSION,
                "status": "disabled",
            },
        },
    )

    disabled = service.dashboard()

    assert disabled.entry_score_adapter_enabled is False
    assert disabled.entry_score_adapter_status == "disabled"


def test_entry_score_adapter_runs_after_the_entry_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(adapter_enabled=True)
    settings.r2d2_entry_confirmation_reviews = 1
    service = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    service.ensure_initialized()
    service.repo.memory["experiment"].update({
        "policy_epoch": "policy-a-resume-2026-08-26",
        "entry_score_adapter_version": ADAPTER_VERSION,
    })
    candidate = {
        **_candidate("ORDER", price=100.0, composite=80),
        "name": "Ordering Test",
        "currency": "USD",
        "stop_price": 99.0,
    }
    calls: list[str] = []
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._mark_and_exit = lambda *args, **kwargs: 0  # type: ignore[method-assign]
    service._us_candidates = (  # type: ignore[method-assign]
        lambda market, now: [candidate] if market == "NASDAQ" else []
    )
    service._enrich_technicals = lambda candidates, **kwargs: None  # type: ignore[method-assign]
    service._entry_decision = lambda candidate: ("BUY", ["qualified"])  # type: ignore[method-assign]
    service._buy = (  # type: ignore[method-assign]
        lambda *args, **kwargs: calls.append("entry") or {"id": "trade"}
    )
    monkeypatch.setattr(
        service._entry_score_adapter,
        "record_cycle",
        lambda **kwargs: calls.append("adapter") or {
            "enabled": True,
            "version": ADAPTER_VERSION,
            "status": "healthy",
            "policy_epoch": "policy-a-resume-2026-08-26",
            "attempted": 1,
            "written": 1,
            "failed": 0,
        },
    )

    service.run_cycle(datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc))

    assert calls == ["entry", "adapter"]


def test_resume_is_plan_first_and_atomically_stamps_policy_epoch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings(adapter_enabled=False)
    database = Database(settings)
    repository = R2D2Repository(database)
    experiment = repository.ensure_experiment(settings)
    repository.set_entries_paused(
        experiment["code"], paused=True, operator="Dudu", reason="Evidence review",
    )
    monkeypatch.setattr(r2d2_entry_control, "Settings", lambda: settings)
    monkeypatch.setattr(r2d2_entry_control, "Database", lambda _: database)
    arguments = [
        "--resume",
        "--operator", "Dudu",
        "--reason", "Six-hands resume under unchanged policy A",
        "--policy-epoch", "policy-a-resume-2026-08-26",
    ]

    assert r2d2_entry_control.main(arguments) == 0
    blocked_plan = json.loads(capsys.readouterr().out)
    assert blocked_plan["resume_ready"] is False
    assert blocked_plan["state_change_required"] is True
    assert r2d2_entry_control.main([*arguments, "--execute"]) == 2
    blocked_execute = json.loads(capsys.readouterr().out)
    assert blocked_execute["entry_score_adapter"]["configured"] is False
    assert repository.experiment(experiment["code"])["entries_paused"] is True

    settings.r2d2_entry_score_adapter_enabled = True
    assert r2d2_entry_control.main(arguments) == 0
    ready_plan = json.loads(capsys.readouterr().out)
    assert ready_plan["resume_ready"] is True
    assert ready_plan["requested_policy_epoch"] == "policy-a-resume-2026-08-26"
    assert repository.experiment(experiment["code"])["entries_paused"] is True

    assert r2d2_entry_control.main([*arguments, "--execute"]) == 0
    executed = json.loads(capsys.readouterr().out)
    current = repository.experiment(experiment["code"])
    assert executed["entries_paused"] is False
    assert executed["policy_epoch"] == "policy-a-resume-2026-08-26"
    assert current["policy_epoch"] == "policy-a-resume-2026-08-26"
    assert current["entry_score_adapter_version"] == ADAPTER_VERSION
    assert current["status"] == "running"
    events = database.list_audit_events(action="r2d2.entries_resumed")
    assert len(events) == 1
    assert events[0]["actor"] == "Dudu"
    assert events[0]["detail"]["policy_epoch"] == "policy-a-resume-2026-08-26"
    assert events[0]["detail"]["entry_score_adapter_version"] == ADAPTER_VERSION


def test_resume_requires_policy_epoch() -> None:
    with pytest.raises(SystemExit, match="policy-epoch"):
        r2d2_entry_control.main([
            "--resume", "--operator", "Dudu", "--reason", "Missing epoch",
        ])
