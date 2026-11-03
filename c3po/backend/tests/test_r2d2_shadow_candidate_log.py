from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2PaperService, _accepted_shadow_candidate, _paper_buy_execution
from app.r2d2_shadow_candidate_log import (
    CASCADE_STEPS,
    SPEC_SHA256,
    R2D2ShadowCandidateLog,
    build_observation,
    canonical_sha256,
)


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


def _cascade_steps_from_sql(path: Path) -> frozenset[str]:
    migration = path.read_text(encoding="utf-8")
    match = re.search(
        r"cascade_step\s+IN\s*\((?P<values>.*?)\)",
        migration,
        flags=re.DOTALL,
    )
    assert match is not None, f"cascade_step constraint missing from {path.name}"
    return frozenset(re.findall(r"'([^']+)'", match.group("values")))


def _producer_cascade_steps() -> frozenset[str]:
    def static_string_choices(expression: ast.expr) -> set[str]:
        if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
            return {expression.value}
        if isinstance(expression, ast.IfExp):
            return (
                static_string_choices(expression.body)
                | static_string_choices(expression.orelse)
            )
        return set()

    source_path = ROOT / "backend" / "app" / "r2d2.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    steps: set[str] = set()
    calls = 0
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "observe_shadow_candidate"
        ):
            continue
        calls += 1
        cascade_keyword = next(
            (keyword for keyword in node.keywords if keyword.arg == "cascade_step"),
            None,
        )
        assert cascade_keyword is not None, "producer call omitted cascade_step"
        literal_steps = static_string_choices(cascade_keyword.value)
        assert literal_steps, "producer cascade_step must remain statically auditable"
        steps.update(literal_steps)
    assert calls > 0, "no shadow-candidate producer calls found"
    return frozenset(steps)


def test_producer_allowlist_and_database_constraints_have_exact_step_parity() -> None:
    producer_steps = _producer_cascade_steps()
    base_schema = ROOT / "db" / "040_r2d2_shadow_candidate_log.sql"
    live_amendment = ROOT / "db" / "043_r2d2_shadow_candidate_cascade_steps.sql"
    base_schema_steps = _cascade_steps_from_sql(base_schema)
    live_amendment_steps = _cascade_steps_from_sql(live_amendment)

    assert producer_steps == CASCADE_STEPS
    assert base_schema_steps == CASCADE_STEPS
    assert live_amendment_steps == CASCADE_STEPS
    amendment_sql = live_amendment.read_text(encoding="utf-8")
    constraint_name = "r2d2_shadow_candidates_cascade_step_check"
    assert f"DROP CONSTRAINT IF EXISTS {constraint_name}" in amendment_sql
    assert f"ADD CONSTRAINT {constraint_name}" in amendment_sql


@pytest.mark.parametrize(
    ("cascade_step", "reason_id", "rejection_class"),
    [
        ("entry_confirmation", "entry_confirmation_pending", "quality"),
        ("entry_cycle_capacity", "entry_cycle_capacity", "capacity"),
    ],
)
def test_runtime_cascade_steps_serialize_with_their_rejection_class(
    cascade_step: str,
    reason_id: str,
    rejection_class: str,
) -> None:
    row = build_observation(
        experiment_id="00000000-0000-0000-0000-000000000001",
        cycle_id="00000000-0000-0000-0000-000000000002",
        observed_at=OBSERVED_AT,
        candidate=_candidate(),
        cascade_step=cascade_step,
        reason_id=reason_id,
        decision="rejected",
        rejection_class=rejection_class,
    )

    assert row["cascade_step"] == cascade_step
    assert row["reason_id"] == reason_id
    assert row["quality_rejected"] is (rejection_class == "quality")
    assert row["capacity_rejected"] is (rejection_class == "capacity")
    unsigned = {
        key: value for key, value in row.items()
        if key not in {"id", "candidate_sha256"}
    }
    assert row["candidate_sha256"] == canonical_sha256(unsigned)


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


def test_same_session_loss_reentry_is_logged_without_an_executed_trade() -> None:
    settings = _settings(enabled=True)
    service = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    service.ensure_initialized()
    service.repo.memory["experiment"].update({
        "policy_epoch": "policy-a-resume-2026-08-26",
        "methodology_version": "test-methodology",
    })
    candidate = _candidate("STOPPED")
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._mark_and_exit = lambda *args, **kwargs: 0  # type: ignore[method-assign]
    service._us_candidates = (  # type: ignore[method-assign]
        lambda market, now: [copy.deepcopy(candidate)] if market == "NASDAQ" else []
    )
    service._enrich_technicals = lambda candidates, **kwargs: None  # type: ignore[method-assign]
    service.repo.loss_exit_on_session = lambda *args, **kwargs: True  # type: ignore[method-assign]

    dashboard = service.run_cycle(datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc))

    assert dashboard.last_cycle is not None
    assert dashboard.last_cycle.status == "succeeded"
    rows = service._shadow_candidate_log.observations()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "STOPPED"
    assert rows[0]["decision"] == "rejected"
    assert rows[0]["reason_id"] == "session_loss_reentry_lock"
    assert rows[0]["trade_id"] is None


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














