from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2PaperService, _accepted_shadow_candidate, _paper_buy_execution
from app.r2d2_exit_policy_engine import StudyBar
from app.r2d2_shadow_candidate_log import (
    SPEC_SHA256,
    R2D2ShadowCandidateLog,
    build_observation,
    canonical_sha256,
)
from app.r2d2_shadow_candidate_outcomes import (
    ShadowCandidateOutcomeError,
    _report_hash,
    build_plan,
    build_report,
    candidate_fill,
    measure_candidate_outcome,
    write_report_package,
)
from app import r2d2_shadow_candidate_outcomes as outcome_module


ROOT = Path(__file__).resolve().parents[2]
SESSION = date(2026, 8, 28)
OBSERVED_AT = datetime(2026, 8, 28, 14, 0, 30, tzinfo=timezone.utc)


def _settings(*, enabled: bool = True, evidence_dir: Path | None = None) -> Settings:
    return Settings(
        database_url="",
        r2d2_start_date="2026-08-17",
        r2d2_shadow_candidate_log_enabled=enabled,
        r2d2_shadow_candidate_outcomes_enabled=True,
        r2d2_shadow_candidate_evidence_dir=(
            evidence_dir or Path("/tmp/r2d2-shadow-candidate-test")
        ),
    )


def _candidate(symbol: str = "TEST", *, composite: float = 68.0) -> dict[str, Any]:
    return {
        "market": "NASDAQ",
        "symbol": symbol,
        "name": f"{symbol} Incorporated",
        "currency": "USD",
        "security_type": "Stock",
        "price": 100.0,
        "quote_as_of": OBSERVED_AT - timedelta(seconds=3),
        "quote_status": "live",
        "upside": 12.0,
        "buy_in_distance": 4.0,
        "risk_score": 50.0,
        "fundamental_score": 70.0,
        "technical_score": 64.0,
        "composite_score": composite,
        "pretrade_rank": composite,
        "confidence": 58.0,
        "day_change": 1.2,
        "raw_cash_volume_usd": 35_000_000.0,
        "spread_bps": 2.0,
        "stop_price": 99.0,
        "technical_reviewed": True,
        "technical_validated": True,
        "technical_indicators": {
            "data_status": "live",
            "atr": 0.5,
            "atr_percent": 0.5,
            "vwap": 99.8,
            "ema8": 99.9,
        },
        "valuation_basis": "test fixture",
        "policy_epoch": "policy-a-resume-2026-08-26",
        "methodology_version": "test-methodology",
        "learning_version": 1,
        "entry_policy": {"min_composite_score": 62.0},
    }


def _observation(
    symbol: str = "TEST",
    *,
    experiment_id: str = "00000000-0000-0000-0000-000000000001",
    cycle_id: str = "00000000-0000-0000-0000-000000000002",
) -> dict[str, Any]:
    return build_observation(
        experiment_id=experiment_id,
        cycle_id=cycle_id,
        observed_at=OBSERVED_AT,
        candidate=_candidate(symbol),
        cascade_step="entry_quality",
        reason_id="confidence_below_floor",
        decision="rejected",
        rejection_class="quality",
        reason_detail=["Valuation confidence below adaptive floor"],
    )


def _bars(symbol: str = "TEST") -> list[StudyBar]:
    return [
        StudyBar(
            symbol=symbol,
            start_at=OBSERVED_AT.replace(second=0),
            open=100.0,
            high=100.2,
            low=99.8,
            close=100.0,
            volume=1000.0,
        ),
        StudyBar(
            symbol=symbol,
            start_at=OBSERVED_AT.replace(second=0) + timedelta(minutes=1),
            open=100.0,
            high=102.0,
            low=99.9,
            close=101.5,
            volume=1200.0,
        ),
    ]


def test_frozen_shadow_candidate_spec_is_byte_identical_to_signed_hash() -> None:
    path = ROOT / "docs" / "R2D2_SHADOW_CANDIDATE_LOG_V1.md"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SPEC_SHA256
    attestation = (
        ROOT / "docs" / "R2D2_SHADOW_CANDIDATE_LOG_V1_CODEX_ATTESTATION.md"
    ).read_text(encoding="utf-8")
    assert SPEC_SHA256 in attestation
    assert "GO técnico" in attestation


def test_migration_is_append_only_and_splits_quality_from_capacity() -> None:
    migration = (ROOT / "db" / "040_r2d2_shadow_candidate_log.sql").read_text(
        encoding="utf-8"
    )
    assert "quality_rejected BOOLEAN NOT NULL" in migration
    assert "capacity_rejected BOOLEAN NOT NULL" in migration
    assert "R2D2-SHADOW-CANDIDATE-OBSERVATION-v1" in migration
    assert migration.count("'entry_execution'") == 1
    assert (
        "UNIQUE (experiment_id, session_date, market, symbol, policy_epoch, decision)"
        in migration
    )
    assert migration.count("BEFORE UPDATE OR DELETE") == 3
    assert migration.count("BEFORE TRUNCATE") == 3
    assert "r2d2_shadow_candidates is append-only" not in migration
    assert "RAISE EXCEPTION '% is append-only', TG_TABLE_NAME" in migration


def test_observation_freezes_point_in_time_without_mutating_candidate() -> None:
    candidate = _candidate()
    before = copy.deepcopy(candidate)
    row = _observation()

    candidate["technical_indicators"]["atr"] = 999.0

    assert before != candidate
    assert row["point_in_time"]["technical_indicators"]["atr"] == 0.5
    assert row["quality_rejected"] is True
    assert row["capacity_rejected"] is False
    unsigned = {
        key: value for key, value in row.items()
        if key not in {"id", "candidate_sha256"}
    }
    assert row["candidate_sha256"] == canonical_sha256(unsigned)


def test_store_deduplicates_first_rejection_but_allows_later_acceptance() -> None:
    settings = _settings()
    database = Database(settings)
    store = R2D2ShadowCandidateLog(database)
    rejected = _observation()
    duplicate = _observation()
    accepted = build_observation(
        experiment_id=rejected["experiment_id"],
        cycle_id=rejected["cycle_id"],
        observed_at=OBSERVED_AT + timedelta(minutes=5),
        candidate=_candidate(),
        cascade_step="entry_execution",
        reason_id="entry_accepted",
        decision="accepted",
        rejection_class="none",
        trade_id="00000000-0000-0000-0000-000000000003",
    )

    result = store.append_observations([rejected, duplicate, accepted])

    assert result == {"attempted": 3, "written": 2, "deduplicated": 1}
    assert [row["decision"] for row in store.observations()] == ["rejected", "accepted"]


def test_store_keeps_same_symbol_when_policy_epoch_changes() -> None:
    settings = _settings()
    store = R2D2ShadowCandidateLog(Database(settings))
    first = _observation()
    candidate = _candidate()
    candidate["policy_epoch"] = "policy-b-resume-2026-08-28"
    second = build_observation(
        experiment_id=first["experiment_id"],
        cycle_id=first["cycle_id"],
        observed_at=OBSERVED_AT + timedelta(minutes=5),
        candidate=candidate,
        cascade_step="entry_quality",
        reason_id="confidence_below_floor",
        decision="rejected",
        rejection_class="quality",
    )

    result = store.append_observations([first, second])

    assert result["written"] == 2
    assert {row["policy_epoch"] for row in store.observations()} == {
        "policy-a-resume-2026-08-26",
        "policy-b-resume-2026-08-28",
    }


def test_store_refuses_an_observation_with_a_mismatched_self_hash() -> None:
    settings = _settings()
    store = R2D2ShadowCandidateLog(Database(settings))
    row = _observation()
    store.append_observations([row])
    store.database._r2d2_shadow_candidates[0]["reason_id"] = "tampered"  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="invalid candidate_sha256"):
        store.observations()


def _service_run(*, logger_enabled: bool) -> tuple[R2D2PaperService, Any]:
    settings = _settings(enabled=logger_enabled)
    service = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    experiment = service.ensure_initialized()
    service.repo.memory["experiment"].update({
        "policy_epoch": "policy-a-resume-2026-08-26",
        "methodology_version": "test-methodology",
    })
    candidate = _candidate("EQUIV")
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._mark_and_exit = lambda *args, **kwargs: 0  # type: ignore[method-assign]
    service._us_candidates = (  # type: ignore[method-assign]
        lambda market, now: [copy.deepcopy(candidate)] if market == "NASDAQ" else []
    )
    service._enrich_technicals = lambda candidates, **kwargs: None  # type: ignore[method-assign]
    service._entry_decision = lambda item: (  # type: ignore[method-assign]
        "REJECT", ["Valuation confidence below adaptive 60.00% floor"]
    )
    dashboard = service.run_cycle(datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc))
    assert service.repo.memory["experiment"]["id"] == experiment["id"]
    return service, dashboard


def _execution_fingerprint(service: R2D2PaperService) -> str:
    decisions = [
        {
            "market": row["market"],
            "symbol": row["symbol"],
            "action": row["action"],
            "reasons": row["reasons"],
            "inputs": row["inputs"],
            "trade_id": row["trade_id"],
        }
        for row in service.repo.memory["decisions"]
    ]
    return canonical_sha256({
        "positions": service.repo.memory["positions"],
        "trades": service.repo.memory["trades"],
        "decisions": decisions,
    })


def test_hot_path_plan_and_execution_are_identical_with_logger_on_and_off() -> None:
    disabled, disabled_dashboard = _service_run(logger_enabled=False)
    enabled, enabled_dashboard = _service_run(logger_enabled=True)

    assert _execution_fingerprint(enabled) == _execution_fingerprint(disabled)
    assert enabled_dashboard.open_positions == disabled_dashboard.open_positions == 0
    assert enabled_dashboard.stats.total_transactions == disabled_dashboard.stats.total_transactions == 0
    rows = enabled._shadow_candidate_log.observations()
    assert len(rows) == 1
    assert rows[0]["reason_id"] == "confidence_below_floor"


def test_daily_cap_still_observes_every_remaining_candidate() -> None:
    settings = _settings(enabled=True)
    settings.r2d2_max_daily_orders = 0
    service = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    service.ensure_initialized()
    service.repo.memory["experiment"]["policy_epoch"] = "policy-a-resume-2026-08-26"
    candidates = [_candidate("CAP1"), _candidate("CAP2"), _candidate("CAP3")]
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._mark_and_exit = lambda *args, **kwargs: 0  # type: ignore[method-assign]
    service._us_candidates = (  # type: ignore[method-assign]
        lambda market, now: copy.deepcopy(candidates) if market == "NASDAQ" else []
    )
    service._enrich_technicals = lambda candidates, **kwargs: None  # type: ignore[method-assign]

    dashboard = service.run_cycle(datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc))

    rows = service._shadow_candidate_log.observations()
    assert {row["symbol"] for row in rows} == {"CAP1", "CAP2", "CAP3"}
    assert {row["reason_id"] for row in rows} == {"daily_order_cap"}
    assert all(row["capacity_rejected"] is True for row in rows)
    assert dashboard.last_cycle is not None
    metadata = dashboard.last_cycle.metadata["shadow_candidate_log"]
    assert metadata["attempted"] == len(candidates)
    assert metadata["population_count"] == len(candidates)
    assert metadata["observed_count"] == len(candidates)
    assert metadata["population_complete"] is True


def test_shadow_sink_failure_never_changes_trading_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _service_run(logger_enabled=True)
    monkeypatch.setattr(
        service._shadow_candidate_log,
        "append_observations",
        lambda rows: (_ for _ in ()).throw(RuntimeError("evidence disk unavailable")),
    )
    before = _execution_fingerprint(service)

    dashboard = service.run_cycle(datetime(2026, 8, 28, 14, 1, tzinfo=timezone.utc))

    assert dashboard.last_cycle is not None
    assert dashboard.last_cycle.status == "succeeded"
    assert dashboard.last_cycle.metadata["shadow_candidate_log"]["status"] == "degraded"
    assert dashboard.last_cycle.metadata["shadow_candidate_log"]["population_complete"] is False
    assert before != _execution_fingerprint(service)
    assert service.repo.memory["decisions"][-1]["action"] == "REJECT"


def test_synthetic_fill_reuses_exact_paper_buy_friction() -> None:
    settings = _settings()
    store = R2D2ShadowCandidateLog(Database(settings))
    observation = _observation()

    fill, source = candidate_fill(observation, store)
    execution = _paper_buy_execution(
        market="NASDAQ", price=100.0, quantity=1.0, fx=1.0,
    )

    assert source == "synthetic_paper_buy"
    assert fill.fill_price_local == execution["fill_price"]
    assert fill.gross_value_usd == execution["gross_value_usd"]
    assert fill.fees_usd == execution["fees_usd"]
    assert fill.slippage_usd == execution["slippage_usd"]


def test_accepted_observation_uses_the_executed_trade_snapshot() -> None:
    candidate = _candidate()
    candidate["price"] = 99.0
    candidate["quote_as_of"] = OBSERVED_AT - timedelta(minutes=2)
    executed_quote_at = OBSERVED_AT - timedelta(seconds=2)
    trade = {
        "signal_price_local": 100.0,
        "quote_as_of": executed_quote_at,
        "decision_snapshot": {
            **candidate,
            "price": 100.0,
            "quote_as_of": executed_quote_at,
            "stop_price": 99.1,
        },
    }

    snapshot = _accepted_shadow_candidate(candidate, trade)

    assert snapshot["price"] == 100.0
    assert snapshot["quote_as_of"] == executed_quote_at
    assert snapshot["stop_price"] == 99.1
    assert candidate["price"] == 99.0


def test_accepted_candidate_reuses_linked_immutable_trade() -> None:
    settings = _settings()
    database = Database(settings)
    store = R2D2ShadowCandidateLog(database)
    trade_id = "00000000-0000-0000-0000-000000000003"
    execution = _paper_buy_execution(
        market="NASDAQ", price=100.0, quantity=2.0, fx=1.0,
    )
    database._r2d2_memory = {  # type: ignore[attr-defined]
        "trades": [{
            "id": trade_id,
            "cycle_id": "00000000-0000-0000-0000-000000000002",
            "market": "NASDAQ",
            "symbol": "TEST",
            "name": "TEST Incorporated",
            "side": "BUY",
            "quantity": 2.0,
            "signal_price_local": 100.0,
            "fill_price_local": execution["fill_price"],
            "fx_to_usd": 1.0,
            "gross_value_usd": execution["gross_value_usd"],
            "fees_usd": execution["fees_usd"],
            "slippage_usd": execution["slippage_usd"],
            "realized_pnl_usd": None,
            "reason": "Tactical quality-momentum route passed",
            "decision_snapshot": {
                **_candidate(),
                "entry_decision_reasons": ["Tactical quality-momentum route passed"],
            },
            "executed_at": OBSERVED_AT,
            "quote_as_of": OBSERVED_AT - timedelta(seconds=3),
        }],
    }
    observation = build_observation(
        experiment_id="00000000-0000-0000-0000-000000000001",
        cycle_id="00000000-0000-0000-0000-000000000002",
        observed_at=OBSERVED_AT,
        candidate=_candidate(),
        cascade_step="entry_execution",
        reason_id="entry_accepted",
        decision="accepted",
        rejection_class="none",
        trade_id=trade_id,
    )

    fill, source = candidate_fill(observation, store)

    assert source == "linked_trade"
    assert fill.id == trade_id
    assert fill.quantity == 2.0
    assert fill.fill_price_local == execution["fill_price"]


def test_outcome_uses_signed_entry_engine_and_keeps_bar_unavailable_outside_violation() -> None:
    settings = _settings()
    store = R2D2ShadowCandidateLog(Database(settings))
    observation = _observation()
    fill, source = candidate_fill(observation, store)
    measured_at = datetime(2026, 8, 29, 3, 15, tzinfo=timezone.utc)

    available = measure_candidate_outcome(
        observation=observation,
        fill=fill,
        fill_source=source,
        bars=_bars(),
        qqq_bars=(),
        measured_at=measured_at,
    )
    unavailable = measure_candidate_outcome(
        observation=observation,
        fill=fill,
        fill_source=source,
        bars=(),
        qqq_bars=(),
        measured_at=measured_at,
    )

    assert available["coverage_classification"] == "available"
    assert available["barrier_category"] == "upper_first"
    assert available["counterfactual_r"] == 1.0
    assert unavailable["coverage_classification"] == "bar_unavailable"
    assert unavailable["barrier_category"] is None
    assert unavailable["outcome_payload"]["market_compatibility"]["classification"] == "bar_unavailable"


def test_daily_report_is_hashed_and_emits_non_authorizing_ledger_drafts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(evidence_dir=tmp_path)
    database = Database(settings)
    store = R2D2ShadowCandidateLog(database)
    observation = _observation()
    store.append_observations([observation])
    before = canonical_sha256(store.observations())
    monkeypatch.setattr(
        outcome_module,
        "_read_price_paths",
        lambda settings, records: ({"TEST": _bars(), "QQQ": []}, {"fixture": True}),
    )

    plan = build_plan(
        store=store,
        experiment_id=observation["experiment_id"],
        session_date=SESSION,
    )
    report, outcomes, jsonl_bytes = build_report(
        settings=settings,
        store=store,
        experiment_id=observation["experiment_id"],
        session_date=SESSION,
        generated_at=datetime(2026, 8, 29, 3, 15, tzinfo=timezone.utc),
    )
    output = tmp_path / "session_date=2026-08-28"
    write_report_package(output, report, jsonl_bytes)

    assert plan["read_only"] is True
    assert canonical_sha256(store.observations()) == before
    assert report["classification"] == "INSUFFICIENT_SAMPLE"
    assert report["report_sha256"] == _report_hash(report)
    assert report["daily_jsonl"]["sha256"] == hashlib.sha256(jsonl_bytes).hexdigest()
    assert report["preregistered_metrics"]["rejection_distribution_by_cascade_step"] == {
        "entry_quality": 1,
    }
    assert report["preregistered_metrics"]["renounced_r_by_cascade_step"] == {
        "entry_quality": {"decided_count": 1, "sum_r": 1.0, "median_r": 1.0},
    }
    assert len(outcomes) == 1
    for line in report["ledger_candidate_lines"]:
        assert line["governance"]["ledger_admission_authorized"] is False
        assert line["governance"]["requires_table_approval"] is True
        unsigned = {key: value for key, value in line.items() if key != "candidate_sha256"}
        assert line["candidate_sha256"] == canonical_sha256(unsigned)
    serialized = json.loads(jsonl_bytes.decode("utf-8"))
    unsigned_line = {
        key: value for key, value in serialized.items() if key != "line_sha256"
    }
    assert serialized["line_sha256"] == canonical_sha256(unsigned_line)
    assert (output / "SHA256SUMS.json").is_file()


def test_plan_cli_never_initializes_or_mutates_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings()
    database = Database(settings)
    repository = R2D2PaperService(  # type: ignore[arg-type]
        settings, database, None, None, None,
    ).repo
    repository.ensure_experiment(settings)
    monkeypatch.setattr(
        database,
        "initialize",
        lambda: pytest.fail("read-only plan must not initialize the database"),
    )
    monkeypatch.setattr(outcome_module, "get_settings", lambda: settings)
    monkeypatch.setattr(outcome_module, "Database", lambda _settings: database)

    assert outcome_module.main(["plan", "--session", SESSION.isoformat()]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["read_only"] is True
    assert payload["trading_state_writes"] == 0


def test_session_run_publishes_then_recovers_without_duplicate_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(evidence_dir=tmp_path)
    database = Database(settings)
    service = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    experiment = service.ensure_initialized()
    store = R2D2ShadowCandidateLog(database)
    store.append_observations([_observation(experiment_id=str(experiment["id"]))])
    monkeypatch.setattr(
        outcome_module,
        "_read_price_paths",
        lambda settings, records: ({"TEST": _bars(), "QQQ": []}, {"fixture": True}),
    )
    output = tmp_path / "session_date=2026-08-28"
    generated_at = datetime(2026, 8, 29, 3, 15, tzinfo=timezone.utc)

    first = outcome_module.run_session(
        settings=settings,
        database=database,
        session_date=SESSION,
        output=output,
        generated_at=generated_at,
    )
    second = outcome_module.run_session(
        settings=settings,
        database=database,
        session_date=SESSION,
        output=output,
        generated_at=generated_at + timedelta(minutes=1),
    )

    assert first["outcomes_written"] == 1
    assert second["outcomes_written"] == 0
    assert second["recovered_existing_package"] is True
    assert len(store.outcomes(SESSION)) == 1
    assert store.report_exists(str(experiment["id"]), SESSION) is True


def test_compose_arms_hot_logger_and_isolates_nightly_worker() -> None:
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    pipeline = (ROOT.parent / ".github" / "workflows" / "c3po-pipeline.yml").read_text(
        encoding="utf-8"
    )
    assert 'C3PO_R2D2_SHADOW_CANDIDATE_LOG_ENABLED: "true"' in compose
    assert "r2d2-shadow-candidate-worker:" in compose
    assert 'C3PO_R2D2_SHADOW_CANDIDATE_OUTCOMES_ENABLED: "true"' in compose
    assert 'command: ["python", "-m", "app.r2d2_shadow_candidate_worker"]' in compose
    assert 'ps -q r2d2-shadow-candidate-worker' in pipeline
    assert "import app.r2d2_shadow_candidate_worker" in pipeline
    assert 'if [ "$rollback_has_shadow_worker" != "true" ]' in pipeline
    assert 'stop r2d2-shadow-candidate-worker' in pipeline


def test_report_package_publish_is_atomic_across_mid_write_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "session_date=2026-08-28"
    report = {"schema_version": "fixture", "report_sha256": "a" * 64}
    original = outcome_module.write_immutable_json
    calls = 0

    def fail_first_write(path: Path, payload: dict[str, Any]) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated disk interruption")
        original(path, payload)

    monkeypatch.setattr(outcome_module, "write_immutable_json", fail_first_write)
    with pytest.raises(OSError, match="simulated disk interruption"):
        write_report_package(output, report, b'{"fixture":true}\n')

    assert not output.exists()
    assert not list(tmp_path.glob(".*.tmp"))

    monkeypatch.setattr(outcome_module, "write_immutable_json", original)
    write_report_package(output, report, b'{"fixture":true}\n')
    assert (output / "candidates.jsonl").is_file()
    assert (output / "report.json").is_file()
    assert (output / "SHA256SUMS.json").is_file()


def test_recovery_refuses_an_immutable_package_for_another_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(evidence_dir=tmp_path)
    database = Database(settings)
    service = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    experiment = service.ensure_initialized()
    observation = _observation(experiment_id=str(experiment["id"]))
    store = R2D2ShadowCandidateLog(database)
    store.append_observations([observation])
    monkeypatch.setattr(
        outcome_module,
        "_read_price_paths",
        lambda settings, records: ({"TEST": _bars(), "QQQ": []}, {"fixture": True}),
    )
    report, _outcomes, jsonl_bytes = build_report(
        settings=settings,
        store=store,
        experiment_id=str(experiment["id"]),
        session_date=SESSION,
        generated_at=datetime(2026, 8, 29, 3, 15, tzinfo=timezone.utc),
    )
    output = tmp_path / "wrong-session"
    write_report_package(output, report, jsonl_bytes)

    with pytest.raises(ShadowCandidateOutcomeError, match="different session"):
        outcome_module.run_session(
            settings=settings,
            database=database,
            session_date=date(2026, 8, 27),
            output=output,
        )
