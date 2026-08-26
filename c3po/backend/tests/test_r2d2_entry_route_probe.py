from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.r2d2_entry_quality_study import PolicyEpoch
from app.r2d2_entry_route_probe import build_probe_report, main
from app.r2d2_exit_policy_engine import LedgerFill
from app.r2d2_exit_policy_study import canonical_sha256


UTC = timezone.utc
OPEN = datetime(2026, 8, 26, 13, 31, tzinfo=UTC)


def _fill(
    fill_id: str,
    side: str,
    at: datetime,
    *,
    symbol: str = "TEST",
    quantity: float = 10.0,
    basis: str = "canonical C3PO valuation universe",
    realized: float | None = None,
    administrative: bool = False,
) -> LedgerFill:
    snapshot = {"valuation_basis": basis}
    if administrative:
        snapshot["operator_wind_down"] = True
    return LedgerFill(
        id=fill_id,
        market="NASDAQ",
        symbol=symbol,
        name=symbol,
        side=side,
        quantity=quantity,
        signal_price_local=100.0,
        fill_price_local=100.1 if side == "BUY" else 99.9,
        fx_to_usd=1.0,
        gross_value_usd=quantity * (100.1 if side == "BUY" else 99.9),
        fees_usd=0.4,
        slippage_usd=1.0,
        realized_pnl_usd=realized,
        reason="test",
        decision_snapshot=snapshot,
        executed_at=at,
        quote_as_of=at,
    )


def _epoch() -> PolicyEpoch:
    return PolicyEpoch(
        policy_epoch="policy-a-resume-2026-08-26",
        effective_from=datetime(2026, 8, 26, 13, 30, tzinfo=UTC),
        effective_to=None,
        deployed_commit="abc",
        code_provenance_status="AUDITED_DEPLOY",
        policy_code_sha256="hash",
        workflow_run_id=1,
        effective_from_evidence="test",
    )


def test_probe_groups_opening_route_and_excludes_wind_down_episode() -> None:
    fills = [
        _fill("buy-1", "BUY", OPEN, basis="full-exchange provisional technical scan"),
        _fill("sell-1", "SELL", OPEN + timedelta(minutes=10), realized=25.0),
        _fill("buy-admin", "BUY", OPEN + timedelta(minutes=20), symbol="ADMIN"),
        _fill(
            "sell-admin",
            "SELL",
            OPEN + timedelta(minutes=30),
            symbol="ADMIN",
            realized=-10.0,
            administrative=True,
        ),
    ]

    report = build_probe_report(
        fills,
        [_epoch()],
        experiment={"id": "exp", "code": "R2D2", "status": "running"},
        policy_epoch_evidence={"sha256": "epochs"},
        generated_at=datetime(2026, 8, 26, 20, 0, tzinfo=UTC),
    )

    assert report["construction"]["constructed_episode_count"] == 2
    assert report["construction"]["organic_episode_count"] == 1
    assert report["construction"]["administrative_episode_count"] == 1
    assert report["provisional_symbols"] == ["TEST"]
    assert report["groups"] == [{
        "era": "policy-a-resume-2026-08-26",
        "valuation_basis": "full-exchange provisional technical scan",
        "policy_epochs": ["policy-a-resume-2026-08-26"],
        "episode_count": 1,
        "closed_episode_count": 1,
        "open_episode_count": 0,
        "buy_count": 1,
        "buy_gross_value_usd": 1001.0,
        "allocated_cost_basis_usd": 1001.4,
        "winner_count": 1,
        "loser_count": 0,
        "flat_count": 0,
        "net_realized_pnl_usd": 25.0,
        "provisional_symbols": ["TEST"],
    }]
    observed = report.pop("report_sha256")
    assert observed == canonical_sha256(report)


def test_probe_keeps_open_episode_without_inventing_outcome() -> None:
    report = build_probe_report(
        [_fill("buy", "BUY", OPEN)],
        [_epoch()],
        experiment={"id": "exp", "code": "R2D2", "status": "running"},
        policy_epoch_evidence={"sha256": "epochs"},
        generated_at=datetime(2026, 8, 26, 20, 0, tzinfo=UTC),
    )

    group = report["groups"][0]
    assert group["episode_count"] == 1
    assert group["closed_episode_count"] == 0
    assert group["open_episode_count"] == 1
    assert group["winner_count"] == 0
    assert group["loser_count"] == 0
    assert group["net_realized_pnl_usd"] == 0.0
    assert report["episode_rows"][0]["net_realized_pnl_usd"] is None


def test_probe_cli_passes_full_settings_to_database(
    tmp_path,
    monkeypatch,
) -> None:
    import app.r2d2_entry_route_probe as probe_module

    settings = type("SettingsStub", (), {"r2d2_experiment_code": "R2D2"})()
    observed = []

    class DatabaseStub:
        def __init__(self, received) -> None:
            observed.append(received)

    class ReaderStub:
        def __init__(self, _database) -> None:
            pass

        def read(self, _code):
            return {"id": "exp", "code": "R2D2", "status": "running"}, []

    epoch = _epoch()
    monkeypatch.setattr(probe_module, "get_settings", lambda: settings)
    monkeypatch.setattr(probe_module, "Database", DatabaseStub)
    monkeypatch.setattr(probe_module, "LedgerReader", ReaderStub)
    monkeypatch.setattr(
        probe_module,
        "_load_policy_epochs",
        lambda _path: ([epoch], {"sha256": "epochs"}),
    )

    output = tmp_path / "probe.json"
    assert main([
        "--policy-epochs",
        str(tmp_path / "epochs.json"),
        "--output",
        str(output),
    ]) == 0
    assert observed == [settings]
