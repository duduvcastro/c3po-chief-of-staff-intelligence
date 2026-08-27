from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pytest

from app.microstructure_tape_probe import (
    MAX_LOGICAL_WINDOW_REQUESTS,
    ProbeCase,
    TapeProbeError,
    classify_tape_case,
    deduplicate_windows,
    run_probe,
)
from app.r2d2_exit_policy_study import canonical_sha256, sha256_file


NOW = datetime(2026, 8, 21, 16, 4, 14, tzinfo=timezone.utc)


def _case(
    case_id: str = "entry:one",
    *,
    signal: float = 100.0,
    quote_as_of: datetime = NOW,
) -> ProbeCase:
    return ProbeCase(
        case_id=case_id,
        study="entry_quality_v1",
        fill_id=case_id.rsplit(":", 1)[-1],
        episode_id=None,
        market="NYSE",
        symbol="ABC",
        side="BUY",
        session_date=date(2026, 8, 21),
        signal_price=signal,
        executed_at=NOW,
        quote_as_of=quote_as_of,
        gate_classification="tolerance_band",
        gate_breach_bps=6.0,
        gate_matched_anchor="quote_as_of",
        gate_matched_offset_minutes=0,
    )


def _trade(
    price: float,
    *,
    conditions: tuple[str, ...] = (),
    trade_id: str = "t1",
) -> dict[str, Any]:
    return {
        "trade_id": trade_id,
        "event_at": NOW,
        "available_at": NOW + timedelta(milliseconds=1),
        "price": price,
        "size": 10.0,
        "exchange": 11,
        "conditions": conditions,
    }


@pytest.mark.parametrize(
    ("trades", "conditions", "expected", "reason"),
    (
        (
            [_trade(100.01, conditions=("2",))],
            {"2": False},
            "condition_explained",
            "non_high_low",
        ),
        (
            [_trade(100.01, conditions=("1",))],
            {"1": True},
            "aggregation_diff",
            "normal_trade",
        ),
        (
            [_trade(100.20)],
            {},
            "no_tape_support",
            "no_trade_within_10bps",
        ),
        (
            [_trade(100.05)],
            {},
            "inconclusive",
            "between_2_and_10bps",
        ),
        (
            [],
            {},
            "inconclusive",
            "provider_window_empty",
        ),
    ),
)
def test_tape_categories_are_exclusive_and_ordered(
    trades: list[dict[str, Any]],
    conditions: dict[str, bool | None],
    expected: str,
    reason: str,
) -> None:
    result = classify_tape_case(_case(), trades, conditions)

    assert result["classification"] == expected
    assert reason in result["classification_reason"]


def test_windows_deduplicate_by_symbol_session_and_quote_minute() -> None:
    cases = [
        _case("entry:one", quote_as_of=NOW),
        _case("exit:two", quote_as_of=NOW + timedelta(seconds=35)),
        _case("exit:three", quote_as_of=NOW + timedelta(minutes=1)),
    ]

    windows = deduplicate_windows(cases)

    assert len(windows) == 2
    assert [case.case_id for case in windows[0].cases] == ["entry:one", "exit:two"]
    assert windows[0].start_at == NOW.replace(second=0) - timedelta(minutes=5)
    assert windows[0].end_at == NOW.replace(second=0) + timedelta(minutes=6)


class FakeTapeClient:
    def __init__(self, *, fail_sample: bool = False) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.fail_sample = fail_sample

    def iter_raw_trades_between(
        self,
        symbol: str,
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int = 50_000,
    ) -> Iterable[dict[str, Any]]:
        self.calls.append(("trades", (symbol, start_at, end_at, limit)))
        if self.fail_sample and limit != 1:
            raise RuntimeError("sample failed")
        if limit == 1:
            return []
        return [{
            "id": "tape-one",
            "participant_timestamp": int(NOW.timestamp() * 1_000_000_000),
            "sip_timestamp": int((NOW + timedelta(milliseconds=1)).timestamp() * 1_000_000_000),
            "price": 100.01,
            "size": 10,
            "exchange": 11,
            "conditions": [2],
        }]

    def trade_conditions(self) -> list[dict[str, Any]]:
        self.calls.append(("conditions", None))
        return [{
            "id": 2,
            "update_rules": {"consolidated": {"updates_high_low": False}},
        }]


def _plan() -> dict[str, Any]:
    case = _case()
    window = deduplicate_windows([case])[0]
    return {
        "execution_ready": True,
        "execution_blockers": [],
        "frozen_contract": {"signed": True},
        "frozen_inputs": {"source": "fixtures"},
        "logical_cap": {
            "maximum_window_requests": MAX_LOGICAL_WINDOW_REQUESTS,
            "entitlement_probe_requests": 1,
            "sample_window_requests": 1,
            "total_window_requests": 2,
            "passed": True,
        },
        "sample": {
            "case_count": 1,
            "window_count": 1,
            "windows": [asdict(window)],
        },
    }


def test_run_proves_entitlement_before_conditions_and_sample(tmp_path: Path) -> None:
    client = FakeTapeClient()

    manifest, report = run_probe(
        plan=_plan(),
        client=client,
        output=tmp_path / "evidence",
        generated_at=NOW,
    )

    assert [call[0] for call in client.calls] == ["trades", "conditions", "trades"]
    assert client.calls[0][1][-1] == 1
    assert report["status"] == "COMPLETE"
    assert report["classification_counts"]["condition_explained"] == 1
    assert report["report_sha256"] == canonical_sha256({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    assert manifest["entitlement_proof"]["passed"] is True
    sums = json.loads((tmp_path / "evidence" / "SHA256SUMS.json").read_text())
    for relative, expected in sums.items():
        assert sha256_file(tmp_path / "evidence" / relative) == expected
    with gzip.open(
        tmp_path / "evidence" / "raw" / "massive-trades.ndjson.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        row = json.loads(handle.readline())
    assert row["provider_row"]["conditions"] == [2]


def test_run_preserves_partial_evidence_on_window_failure(tmp_path: Path) -> None:
    _manifest, report = run_probe(
        plan=_plan(),
        client=FakeTapeClient(fail_sample=True),
        output=tmp_path / "partial",
        generated_at=NOW,
    )

    assert report["status"] == "PARTIAL"
    assert report["analysis_interpretable"] is False
    assert report["error"] == "sample failed"
    assert (tmp_path / "partial" / "raw" / "massive-trades.ndjson.gz").is_file()


def test_run_refuses_a_blocked_plan(tmp_path: Path) -> None:
    plan = _plan()
    plan["execution_ready"] = False
    plan["execution_blockers"] = ["logical_window_request_cap_exceeded"]

    with pytest.raises(TapeProbeError, match="logical_window_request_cap_exceeded"):
        run_probe(
            plan=plan,
            client=FakeTapeClient(),
            output=tmp_path / "blocked",
        )
