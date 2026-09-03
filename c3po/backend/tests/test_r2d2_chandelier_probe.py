from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.r2d2_candidate_f_backtest import (
    CandidateBacktestError,
    EXPECTED_SESSIONS,
    MIN_FIVE_MINUTE_BARS_PER_SYMBOL_SESSION,
    PRIOR_FAILED_WORKFLOW_RUN_ID,
    PRIOR_PROBE_REPORT_SHA256,
    SCHEMA_VERSION as BACKTEST_SCHEMA_VERSION,
    _candidate_f_wrapper,
    _coverage_shortfalls,
    _json_default,
    _premature_exit_metrics,
    _require_frozen_coverage,
    _require_sha256,
    SYMBOLS,
    aggregate_massive_five_minute_rows,
    canonical_sha256 as backtest_sha256,
)
from app.r2d2_chandelier_probe import (
    ChandelierProbeError,
    FiveMinuteBar,
    INVALID_PROBE_V2_REPORT_SHA256,
    INVALID_PROBE_V2_WORKFLOW_RUN_ID,
    SCHEMA_VERSION as PROBE_SCHEMA_VERSION,
    TradeAudit,
    _require_cohort_source_coverage,
    aggregate_five_minutes,
    analyze_stop_regret,
    analyze_winning_episode,
    atr14_sma,
    chandelier_e,
)
from app.r2d2_exit_policy_engine import Episode, LedgerFill, StudyBar


UTC = timezone.utc


def _fill(
    *,
    fill_id: str,
    side: str,
    at: datetime,
    price: float,
    quantity: float = 10.0,
    realized: float | None = None,
    reason: str = "",
    stop: float = 95.0,
) -> LedgerFill:
    gross = price * quantity
    return LedgerFill(
        id=fill_id,
        market="NASDAQ",
        symbol="TEST",
        name="Test",
        side=side,
        quantity=quantity,
        signal_price_local=price,
        fill_price_local=price,
        fx_to_usd=1.0,
        gross_value_usd=gross,
        fees_usd=0.0,
        slippage_usd=0.0,
        realized_pnl_usd=realized,
        reason=reason,
        decision_snapshot={"stop_price": stop} if side == "BUY" else {},
        executed_at=at,
        quote_as_of=at,
    )


def _episode(*, sell_reason: str = "Tactical profit", sell_price: float = 105.0) -> Episode:
    opened = datetime(2026, 8, 26, 14, 2, tzinfo=UTC)
    closed = datetime(2026, 8, 26, 14, 56, tzinfo=UTC)
    return Episode(
        id="episode-1",
        market="NASDAQ",
        symbol="TEST",
        name="Test",
        fills=(
            _fill(fill_id="buy", side="BUY", at=opened, price=100.0),
            _fill(
                fill_id="sell", side="SELL", at=closed, price=sell_price,
                realized=(sell_price - 100.0) * 10.0, reason=sell_reason,
            ),
        ),
        opened_at=opened,
        closed_at=closed,
    )


def test_five_minute_aggregation_uses_real_sparse_rows_and_fixed_window() -> None:
    window = datetime(2026, 8, 26, 13, 30, tzinfo=UTC)
    minutes = [
        StudyBar("TEST", window + timedelta(minutes=index), 100 + index, 101 + index, 99, 100 + index, 10)
        for index in (1, 3, 4)
    ]
    sparse = aggregate_five_minutes(minutes)
    assert len(sparse) == 1
    assert sparse[0].start_at == window
    assert sparse[0].source_minutes == 3
    assert sparse[0].open == 101
    assert sparse[0].high == 105
    assert sparse[0].low == 99
    assert sparse[0].close == 104
    assert sparse[0].volume == 30
    assert aggregate_five_minutes([]) == []

    candidate = aggregate_massive_five_minute_rows([
        {
            "timestamp": bar.start_at,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in minutes
    ], symbol="TEST")
    assert candidate == [{
        "timestamp": sparse[0].start_at,
        "open": sparse[0].open,
        "high": sparse[0].high,
        "low": sparse[0].low,
        "close": sparse[0].close,
        "volume": sparse[0].volume,
        "source_minutes": sparse[0].source_minutes,
    }]


def test_sparse_aggregation_aligns_to_window_and_never_fills_empty_window() -> None:
    rows = [
        {
            "timestamp": datetime(2026, 8, 26, 13, minute, tzinfo=UTC),
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
            "volume": 12,
        }
        for minute in (31, 41)
    ]
    result = aggregate_massive_five_minute_rows(rows, symbol="TEST")
    assert [row["timestamp"] for row in result] == [
        datetime(2026, 8, 26, 13, 30, tzinfo=UTC),
        datetime(2026, 8, 26, 13, 40, tzinfo=UTC),
    ]
    assert datetime(2026, 8, 26, 13, 35, tzinfo=UTC) not in {
        row["timestamp"] for row in result
    }
    assert [row["source_minutes"] for row in result] == [1, 1]


def test_frozen_coverage_guard_remains_at_seventy_without_attrition() -> None:
    session = EXPECTED_SESSIONS[0]
    start = datetime(session.year, session.month, session.day, 13, 30, tzinfo=UTC)
    bars = {
        "ADP": [
            {"timestamp": start + timedelta(minutes=5 * index)}
            for index in range(MIN_FIVE_MINUTE_BARS_PER_SYMBOL_SESSION - 1)
        ],
    }
    assert len(SYMBOLS) == 40
    assert len(EXPECTED_SESSIONS) == 10
    assert MIN_FIVE_MINUTE_BARS_PER_SYMBOL_SESSION == 70
    assert BACKTEST_SCHEMA_VERSION == "R2D2-CANDIDATE-E-F-BACKTEST-v2"
    assert PROBE_SCHEMA_VERSION == "R2D2-CHANDELIER-PROBE-v3"
    assert PRIOR_FAILED_WORKFLOW_RUN_ID == 33714916267
    assert PRIOR_PROBE_REPORT_SHA256 == (
        "159b2eca56b8a5e42b0158a2a61409c3fb33589691735aa7fdb2098478ac9191"
    )
    assert _coverage_shortfalls(
        bars,
        symbols=("ADP",),
        sessions=(session,),
    ) == {"ADP": {session.isoformat(): 69}}
    with pytest.raises(CandidateBacktestError, match="incomplete symbol-session coverage"):
        _require_frozen_coverage(
            bars,
            symbols=("ADP",),
            sessions=(session,),
        )

    bars["ADP"].append({"timestamp": start + timedelta(minutes=5 * 69)})
    _require_frozen_coverage(
        bars,
        symbols=("ADP",),
        sessions=(session,),
    )


def test_reports_pin_both_superseded_run_provenances() -> None:
    root = Path(__file__).resolve().parents[3]
    backtest_source = (
        root / "c3po" / "backend" / "app" / "r2d2_candidate_f_backtest.py"
    ).read_text(encoding="utf-8")
    probe_source = (
        root / "c3po" / "backend" / "app" / "r2d2_chandelier_probe.py"
    ).read_text(encoding="utf-8")
    assert '"prior_failed_workflow_run_id": PRIOR_FAILED_WORKFLOW_RUN_ID' in backtest_source
    assert INVALID_PROBE_V2_WORKFLOW_RUN_ID == 33716979776
    assert INVALID_PROBE_V2_REPORT_SHA256 == (
        "5ffbe91b99e02a9ca88d119dbd00dff621c357f51a806aa6aa0160828689f676"
    )
    assert '"supersedes": [' in probe_source
    assert '"workflow_run_id": PRIOR_FAILED_WORKFLOW_RUN_ID' in probe_source
    assert '"report_sha256": PRIOR_PROBE_REPORT_SHA256' in probe_source
    assert '"workflow_run_id": INVALID_PROBE_V2_WORKFLOW_RUN_ID' in probe_source
    assert '"report_sha256": INVALID_PROBE_V2_REPORT_SHA256' in probe_source


def test_probe_source_coverage_requires_every_cohort_xnys_session() -> None:
    cohort = (_episode(),)
    stale_sources = tuple(
        (date(2026, 8, day), Path(f"/archive/2026-08-{day:02d}.jsonl"))
        for day in (17, 18, 19, 20, 21)
    )
    with pytest.raises(
        ChandelierProbeError,
        match="minute aggregate source coverage is missing required session.*2026-07-29",
    ):
        _require_cohort_source_coverage(cohort, stale_sources)

    required_dates = tuple(
        date.fromisoformat(value)
        for value in (
            "2026-07-29", "2026-07-30", "2026-07-31",
            "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07",
            "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14",
            "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21",
            "2026-08-24", "2026-08-25", "2026-08-26",
        )
    )
    complete_sources = tuple(
        (session, Path(f"/archive/{session.isoformat()}.jsonl"))
        for session in required_dates
    )
    assert _require_cohort_source_coverage(cohort, complete_sources) == required_dates

    missing_prior_session = tuple(
        item for item in complete_sources if item[0] != date(2026, 8, 24)
    )
    with pytest.raises(ChandelierProbeError, match="2026-08-24"):
        _require_cohort_source_coverage(cohort, missing_prior_session)


def test_probe_a_never_treats_absent_or_atrless_path_as_zero_effect() -> None:
    episode = _episode(sell_price=103.0)
    absent = analyze_winning_episode(episode, ())
    assert absent["eligibility"] == "censored_no_observable_price_path"
    assert absent["counterfactual_f_net_pnl_usd"] is None
    assert absent["avoidable_giveback_usd"] is None

    one_bar = (
        FiveMinuteBar(
            "TEST",
            datetime(2026, 8, 26, 14, 5, tzinfo=UTC),
            100,
            101,
            99,
            100,
            1_000,
            1,
        ),
    )
    atrless = analyze_winning_episode(episode, one_bar)
    assert atrless["eligibility"] == "censored_insufficient_atr_path"
    assert atrless["counterfactual_f_net_pnl_usd"] is None
    assert atrless["avoidable_giveback_usd"] is None

    partial_history = [
        FiveMinuteBar(
            "TEST",
            datetime(2026, 8, 26, 11, 15, tzinfo=UTC) + timedelta(minutes=5 * index),
            100,
            101,
            99,
            100,
            1_000,
            5,
        )
        for index in range(33)
    ]
    partial_history.extend((
        FiveMinuteBar(
            "TEST", datetime(2026, 8, 26, 14, 0, tzinfo=UTC),
            100, 120, 99, 119, 1_000, 5,
        ),
        FiveMinuteBar(
            "TEST", datetime(2026, 8, 26, 14, 5, tzinfo=UTC),
            119, 120, 100, 101, 1_000, 5,
        ),
    ))
    partially_evaluable = analyze_winning_episode(episode, partial_history)
    assert partially_evaluable["eligibility"] == "censored_insufficient_atr_path"
    assert partially_evaluable["counterfactual_f_net_pnl_usd"] is None


def test_atr_and_ratchet_contract_are_independent_of_asserted_business_result() -> None:
    start = datetime(2026, 8, 26, 13, 30, tzinfo=UTC)
    bars = [
        FiveMinuteBar("TEST", start + timedelta(minutes=5 * index), 100, 101, 99, 100, 1_000, 5)
        for index in range(35)
    ]
    assert atr14_sma(bars, 34) == pytest.approx(2.0)
    stop_e = chandelier_e(original_stop=95.0, high_water=110.0, atr=2.0)
    assert stop_e == pytest.approx(105.0)
    expanded_e = chandelier_e(original_stop=95.0, high_water=110.0, atr=6.0)
    assert expanded_e == pytest.approx(95.0)
    assert max(stop_e, expanded_e) == pytest.approx(105.0)


def test_probe_a_detects_ratchet_only_exit_and_reduced_giveback() -> None:
    episode = _episode(sell_price=103.0)
    start = datetime(2026, 8, 26, 11, 0, tzinfo=UTC)
    bars = [
        FiveMinuteBar("TEST", start + timedelta(minutes=5 * index), 100, 100.2, 99.8, 100, 1_000, 5)
        for index in range(35)
    ]
    bars.extend((
        FiveMinuteBar("TEST", datetime(2026, 8, 26, 14, 5, tzinfo=UTC), 100, 110, 100, 110, 1_000, 5),
        FiveMinuteBar("TEST", datetime(2026, 8, 26, 14, 10, tzinfo=UTC), 110, 121, 100, 106, 1_000, 5),
    ))
    row = analyze_winning_episode(
        episode,
        bars,
        {"sell": TradeAudit("chandelier_2tick", 104.0, 1.0, episode.closed_at)},
    )
    assert row["eligibility"] == "eligible"
    assert row["ratchet_only_exit_observed"] is True
    assert row["counterfactual_f_net_pnl_usd"] > row["actual_net_pnl_usd"]
    assert row["avoidable_giveback_usd"] > 0
    assert row["maximum_trail_loosen_bps"] > 0
    assert row["actual_exit_engine"] == "chandelier_2tick"


def test_probe_a_rejects_close_that_becomes_available_after_actual_exit() -> None:
    episode = _episode(sell_price=103.0)
    start = datetime(2026, 8, 26, 11, 0, tzinfo=UTC)
    bars = [
        FiveMinuteBar(
            "TEST", start + timedelta(minutes=5 * index),
            100, 100.2, 99.8, 100, 1_000, 5,
        )
        for index in range(35)
    ]
    bars.extend((
        FiveMinuteBar(
            "TEST", datetime(2026, 8, 26, 14, 5, tzinfo=UTC),
            100, 110, 100, 110, 1_000, 5,
        ),
        FiveMinuteBar(
            "TEST", datetime(2026, 8, 26, 14, 55, tzinfo=UTC),
            110, 121, 100, 106, 1_000, 5,
        ),
    ))
    row = analyze_winning_episode(episode, bars)
    assert row["eligibility"] == "eligible"
    assert row["ratchet_only_exit_observed"] is False
    assert row["f_exit_at"] is None
    assert row["counterfactual_f_net_pnl_usd"] == row["actual_net_pnl_usd"]
    assert row["avoidable_giveback_usd"] == 0.0
    assert row["maximum_trail_loosen_bps"] == 0.0


def test_probe_b_uses_only_strictly_later_same_session_bars() -> None:
    episode = _episode(
        sell_reason="Immediate hard stop at mark -0.8%",
        sell_price=99.0,
    )
    exit_at = episode.closed_at
    assert exit_at is not None
    bars = [
        StudyBar("TEST", exit_at.replace(second=0, microsecond=0), 99, 106, 98, 105, 100),
        StudyBar("TEST", exit_at.replace(second=0, microsecond=0) + timedelta(minutes=1), 100, 106, 100, 105, 100),
    ]
    row = analyze_stop_regret(
        episode,
        bars,
        {"sell": TradeAudit("hard_stop", 99.0, 1.0, exit_at)},
    )
    assert row is not None
    assert row["eligibility"] == "eligible"
    assert row["recovered_above_entry_same_session"] is True
    assert row["reached_plus_1r_same_session"] is True


def test_probe_b_distinguishes_missing_session_from_no_later_bar() -> None:
    episode = _episode(
        sell_reason="Immediate hard stop at mark -0.8%",
        sell_price=99.0,
    )
    exit_at = episode.closed_at
    assert exit_at is not None
    audit = {"sell": TradeAudit("hard_stop", 99.0, 1.0, exit_at)}

    absent = analyze_stop_regret(episode, (), audit)
    assert absent is not None
    assert absent["eligibility"] == "censored_no_observable_exit_session_bars"

    exit_bar_only = (
        StudyBar(
            "TEST",
            exit_at.replace(second=0, microsecond=0),
            99,
            100,
            98,
            99,
            100,
        ),
    )
    no_later = analyze_stop_regret(episode, exit_bar_only, audit)
    assert no_later is not None
    assert no_later["eligibility"] == "censored_no_later_same_session_bar"


def test_candidate_f_forwards_monotonic_stop_to_frozen_exit_function() -> None:
    class State:
        pass

    received: list[float] = []

    def original(**kwargs: Any) -> tuple[str, State]:
        received.append(float(kwargs["stop_price"]))
        return "hold", State()

    wrapped = _candidate_f_wrapper(original)
    state = State()
    _, state = wrapped(
        state=state,
        technical={"atr": 1.0},
        quote_price=110.0,
        stop_price=95.0,
        high_water=110.0,
    )
    _, state = wrapped(
        state=state,
        technical={"atr": 8.0},
        quote_price=106.0,
        stop_price=95.0,
        high_water=110.0,
    )
    assert received == pytest.approx([107.5, 107.5])
    assert getattr(state, "_candidate_f_stop") == pytest.approx(107.5)


def test_backtest_self_hash_survives_json_datetime_serialization() -> None:
    import json

    payload: dict[str, Any] = {
        "generated_at": datetime(2026, 9, 2, 4, 0, tzinfo=UTC),
        "expires_at": datetime(2026, 10, 2, 4, 0, tzinfo=UTC),
    }
    payload["report_sha256"] = backtest_sha256(payload)
    loaded = json.loads(json.dumps(payload, default=_json_default))
    expected = loaded.pop("report_sha256")
    assert backtest_sha256(loaded) == expected


def test_frozen_source_hash_is_strictly_validated() -> None:
    digest = "a" * 64
    assert _require_sha256(digest.upper()) == digest
    with pytest.raises(CandidateBacktestError, match="64 hexadecimal"):
        _require_sha256("not-a-digest")


def test_backtest_premature_exit_rate_uses_later_same_session_bar() -> None:
    from types import SimpleNamespace

    at = datetime(2026, 8, 10, 14, 0, tzinfo=UTC)
    report = SimpleNamespace(trades=[
        SimpleNamespace(
            symbol="AAPL", side="BUY", timestamp=at, price=100.0,
            quantity=10.0, reason="entry",
        ),
        SimpleNamespace(
            symbol="AAPL", side="SELL", timestamp=at + timedelta(minutes=5),
            price=98.0, quantity=10.0, reason="Adaptive intraday stop executed",
        ),
    ])
    bars: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in SYMBOLS}
    bars["AAPL"] = [
        {"timestamp": at + timedelta(minutes=5), "high": 110.0},
        {"timestamp": at + timedelta(minutes=10), "high": 101.0},
    ]
    result = _premature_exit_metrics(report, bars)
    assert result["eligible_stop_exit_leg_count"] == 1
    assert result["premature_exit_percent"] == 100.0


def test_workflow_pins_read_only_window_retention_and_frozen_policy() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (
        root / ".github" / "workflows" / "r2d2-chandelier-study.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "RUN R2D2 CHANDELIER STUDY" in workflow
    assert "SET TRANSACTION READ ONLY" not in workflow
    assert "bc79ca195c19bee9b9ef18c3098d28ae6c149597" in workflow
    assert "00:00-08:00 America/Sao_Paulo" in workflow
    assert "retention-days: 30" in workflow
    assert "gh pr comment 348" in workflow
    assert 'host_identity="$(id -u):$(id -g)"' in workflow
    assert workflow.count('--user "$host_identity"') == 3
    study_step = workflow.split("- name: Run production read-only probes", 1)[1].split(
        "- name: Download reduced artifact", 1,
    )[0]
    ssh_command = study_step.split("<<'REMOTE'", 1)[0]
    assert "ServerAliveInterval=30" in ssh_command
    assert "ServerAliveCountMax=20" in ssh_command
    remote = study_step.split("<<'REMOTE'", 1)[1].split("\n          REMOTE", 1)[0]
    compose_runs = remote.split('"${compose[@]}" run --rm -T')[1:]
    assert len(compose_runs) == 3
    assert all("</dev/null" in command.split("\n\n", 1)[0] for command in compose_runs)
    oneoff_guard = remote.split("active_api_oneoffs=", 1)[1].split(
        'host_identity="$(id -u):$(id -g)"', 1,
    )[0]
    assert "docker ps" in oneoff_guard
    assert "com.docker.compose.project=c3po" in oneoff_guard
    assert "com.docker.compose.oneoff=True" in oneoff_guard
    assert "com.docker.compose.service=api" in oneoff_guard
    assert "refusing overlapping study" in oneoff_guard
    assert "exit 13" in oneoff_guard
    assert remote.index("active_api_oneoffs=") < remote.index('"${compose[@]}" run --rm -T')
    assert 'test -w "$STUDY_OUTPUT"' in workflow
    assert 'HOST_OUTPUT="$HOST_OUTPUT_ROOT/run-$RUN_ID"' in workflow
    assert "frozen-candidate-e-source.tar.gz.sha256" in workflow
    assert "frozen source provenance mismatch" in workflow
    assert "docker compose up" not in workflow
    assert "docker compose restart" not in workflow
    assert 'if b["eligible_stop_out_count"]:' in workflow
    assert "0 elegíveis; recuperação N/D (denominador vazio)." in workflow
    assert "None%" not in workflow


def test_probe_source_pins_database_read_only_and_query_fingerprint() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "c3po" / "backend" / "app" / "r2d2_chandelier_probe.py").read_text(
        encoding="utf-8",
    )
    assert 'connection.execute("SET TRANSACTION READ ONLY")' in source
    assert 'connection.execute(\n            "SHOW transaction_read_only"' in source
    assert "QUERY_SHA256 = hashlib.sha256(QUERY_TEXT.encode" in source
    build_report_source = source.split("def build_report(", 1)[1]
    assert build_report_source.index(
        "required_source_sessions = _require_cohort_source_coverage"
    ) < build_report_source.index("reader.read(sources, symbols)")
    assert '"source_lookback_session_count": SOURCE_LOOKBACK_SESSIONS' in source
    assert '"source_coverage_verified": True' in source
