"""Contract of the official target price across consumers (Valuation Engine V3.2 rev 7, §7-bis, Passo 0; I-TP1/I-TP3).

1. A static sweep over ``app/``: outside the official producers (the screeners) and the engines' own modules, no module
   may ASSIGN a target price from a computation (``our_tp = <expr>``, ``c3po_tp = <expr>``, ``calibrated_tp = <expr>``,
   ``tp = <expr>``) — only from a name, an attribute, a subscript, a constant or a plain conversion. This is the CI
   guard the spec requires from Passo 0 on: a consumer that starts computing a TP fails the build.
2. Every operational consumer resolves the SAME official row for the same (market, symbol, generation): One Pager,
   R2D2 v1 and the screeners' served responses agree with the selection, stamped with generation_id/tp_source.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import valuation_official as official
from app.config import Settings
from app.database import Database

APP = Path(__file__).resolve().parents[1] / "app"
TP_NAMES = {"our_tp", "c3po_tp", "calibrated_tp", "tp"}
# The official producers (today's official engine) and the engines that exist to be COMPARED, never served as the TP.
PRODUCERS_AND_ENGINES = {
    "market_data/us_screener.py", "market_data/b3_screener.py",
    "valuation_v2_engine.py", "valuation_v2_shadow.py", "valuation_v2_data.py", "valuation_v2_peer_quality.py",
    "valuation_v3_engine.py", "valuation_v3_shadow.py", "valuation_v3_ab.py", "valuation_v3_inputs.py", "valuation_v3_macro.py",
    "valuation_official.py", "ir_valuation.py", "valuation_accuracy.py",
}
CONVERSIONS = {"float", "int", "round", "_float", "_positive", "positive", "number", "_number", "_bounded_tp", "_clamp", "clamp", "abs", "max", "min"}


def _is_computation(node: ast.AST) -> bool:
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Constant)):
        return False
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        return name not in CONVERSIONS
    if isinstance(node, ast.IfExp):
        return _is_computation(node.body) or _is_computation(node.orelse)
    if isinstance(node, ast.BoolOp):
        return any(_is_computation(value) for value in node.values)
    return True  # BinOp, comparisons, comprehensions, lambdas...: a computation


def _tp_computations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        elif isinstance(node, ast.AugAssign):
            targets, value = [node.target], node  # any augmented assignment to a TP is a computation
        for target in targets:
            if isinstance(target, ast.Name) and target.id in TP_NAMES and value is not None and _is_computation(value):
                found.append(f"{path.name}:{node.lineno}: {target.id} = <computation>")
    return found


def test_no_consumer_computes_a_target_price_outside_the_official_producers() -> None:
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        rel = str(path.relative_to(APP))
        if rel in PRODUCERS_AND_ENGINES or rel.startswith("r2d2_v2_"):
            continue
        offenders.extend(_tp_computations(path))
    assert offenders == [], "TP computed outside the official producers (V3.2 rev 7 §7-bis, I-TP1):\n" + "\n".join(offenders)


def test_the_one_pager_no_longer_blends_the_consensus_into_the_tp() -> None:
    source = (APP / "one_pager.py").read_text(encoding="utf-8")
    assert "internal_tp * (1 - consensus_weight)" not in source
    assert "official_row(" in source and "_official_valuation" in source


def test_r2d2_reads_the_official_selection_not_a_raw_snapshot() -> None:
    source = (APP / "r2d2.py").read_text(encoding="utf-8")
    assert "official_rows(self.repo.database, market)" in source
    assert 'latest_analysis_snapshot(\n            "valuation_universe"' not in source
    assert "self.one_pagers._analyze(" not in source  # no same-day valuation backfill: a consumer never computes


def _database() -> Database:
    return Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))


def test_every_consumer_resolves_the_same_official_row_for_the_same_generation() -> None:
    database = _database()
    now = datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc)
    rows = {
        "B3": [{"symbol": "PETR4", "our_tp": 40.0, "buy_in": 32.0, "price": 36.0, "internal_tp": 39.0, "signal_quality": "validated"}],
        "NASDAQ": [{"symbol": "AAPL", "our_tp": 250.0, "buy_in": 200.0, "price": 220.0, "internal_tp": 245.0, "signal_quality": "validated"}],
        "NYSE": [{"symbol": "KO", "our_tp": 70.0, "buy_in": 60.0, "price": 65.0, "internal_tp": 68.0, "signal_quality": "validated"}],
    }
    cycles = {market: database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1", {"methodology_version": 7},
                                                       {"rows": rows[market], "universe_size": 1}, now + timedelta(minutes=i))
              for i, market in enumerate(official.MARKETS)}
    generation = official.current_generation(database)
    assert generation is not None and generation["cycles"] == cycles
    # One Pager path: official_row(market, symbol); R2D2 path: official_rows(market); served response: official_stamp(market)
    one_pager_view = official.official_row(database, "US", "AAPL")
    r2d2_view = official.official_rows(database, "NASDAQ")["AAPL"]
    served = official.official_stamp(database, "NASDAQ")
    assert one_pager_view is not None
    assert one_pager_view["our_tp"] == r2d2_view["our_tp"] == 250.0 and one_pager_view["buy_in"] == r2d2_view["buy_in"] == 200.0
    assert one_pager_view["generation_id"] == r2d2_view["generation_id"] == served["official_generation_id"] == generation["generation_id"]
    assert one_pager_view["official_cycle_id"] == r2d2_view["official_cycle_id"] == served["official_cycle_id"] == cycles["NASDAQ"]
    assert one_pager_view["tp_source"] == r2d2_view["tp_source"] == served["tp_source"] == official.SOURCE_OFFICIAL
    # the record behind the served number carries the same value and a content hash (the studies' provenance, TP-C)
    record = database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)
    assert record is not None and record["tp"] == 250.0 and record["cycle_id"] == cycles["NASDAQ"] and len(record["row_sha256"]) == 64
