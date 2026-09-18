"""Contract of the official target price across consumers (Valuation Engine V3.2 rev 7, §7-bis, Passo 0; I-TP1/I-TP3).

1. A static sweep over ``app/``: outside the official producers and the engines' own modules, no module may put a
   target price (``our_tp``, ``c3po_tp``, ``calibrated_tp``, ``tp``) where a COMPUTATION produced it — by assignment,
   by subscript/attribute assignment, in a dict literal or as a keyword argument — and conversions (``float(...)``,
   ``round(...)``, ``_float(...)``) are transparent: what they wrap is what counts (rev 2, F393-8). Only reads
   (a name, an attribute, a subscript, ``x.get(...)``, a constant) and the producer engine's own calls pass.
2. Every operational consumer resolves the SAME official row for the same (market, symbol, generation): One Pager,
   R2D2 v1 and the screeners' served responses agree with the selection and its immutable records, stamped.
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
# The official producers (today's official engine), the engine module, and the engines that exist to be COMPARED.
PRODUCERS_AND_ENGINES = {
    "market_data/us_screener.py", "market_data/b3_screener.py", "valuation_official_engine.py",
    "valuation_v2_engine.py", "valuation_v2_shadow.py", "valuation_v2_data.py", "valuation_v2_peer_quality.py",
    "valuation_v3_engine.py", "valuation_v3_shadow.py", "valuation_v3_ab.py", "valuation_v3_inputs.py", "valuation_v3_macro.py",
    "valuation_official.py", "ir_valuation.py", "valuation_accuracy.py",
    "valuation_pit_rerun.py",  # the point-in-time re-execution of the V3 engine: a PRODUCER of the diagnostic `v3_2_shadow` records (never served, never selectable)
}
CONVERSIONS = {"float", "int", "round", "_float", "_positive", "positive", "number", "_number", "_bounded_tp", "_clamp", "clamp", "str"}
ENGINE_CALLS = {"official_blend_v1", "official_buy_in_v1", "foreign_bridge_tp_v1"}  # the producer engine, callable only in producer role
MUTATOR_CALLS = {"setattr", "setitem"}  # positional (target, name, value) mutators: setattr(...) / operator.setitem(...)


def _call_name(node: ast.Call) -> str:
    func = node.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _is_computation(node: ast.AST) -> bool:
    """True when a value is PRODUCED by arithmetic/aggregation rather than READ. Conversions are transparent."""
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Constant)):
        return False
    if isinstance(node, ast.Call):
        name = _call_name(node)
        if name in ENGINE_CALLS:
            return False
        if name in CONVERSIONS:
            return any(_is_computation(argument) for argument in node.args) or any(_is_computation(kw.value) for kw in node.keywords)
        if name == "get" and isinstance(node.func, ast.Attribute):  # dict/mapping access is a read
            return False
        return True  # statistics.mean(...), min/max over methods, any other producer of a number
    if isinstance(node, ast.IfExp):
        return _is_computation(node.body) or _is_computation(node.orelse)
    if isinstance(node, ast.BoolOp):
        return any(_is_computation(value) for value in node.values)
    return True  # BinOp, UnaryOp, comparisons, comprehensions, lambdas...


def _target_is_tp(target: ast.expr) -> bool:
    if isinstance(target, ast.Name):
        return target.id in TP_NAMES
    if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
        return str(target.slice.value) in TP_NAMES
    if isinstance(target, ast.Attribute):
        return target.attr in TP_NAMES
    if isinstance(target, ast.Starred):
        return _target_is_tp(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(_target_is_tp(element) for element in target.elts)  # `our_tp, x = ...` / `[our_tp, y] = ...`
    return False


def _tp_assignment_findings(target: ast.expr, value: ast.expr, label: str, lineno: int) -> list[str]:
    """Handles both scalar targets and tuple/list (un)packing, matched element-wise when shapes line up."""
    if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)) and len(target.elts) == len(value.elts):
        return [
            f"{label}:{lineno}: unpacking assignment of a computed TP"
            for element, element_value in zip(target.elts, value.elts)
            if _target_is_tp(element) and _is_computation(element_value)
        ]
    if _target_is_tp(target) and _is_computation(value):
        return [f"{label}:{lineno}: assignment of a computed TP"]
    return []


def tp_computations(source: str, label: str) -> list[str]:
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                found.extend(_tp_assignment_findings(target, node.value, label, node.lineno))
        elif isinstance(node, ast.AnnAssign) and node.value is not None and _target_is_tp(node.target) and _is_computation(node.value):
            found.append(f"{label}:{node.lineno}: annotated assignment of a computed TP")
        elif isinstance(node, ast.AugAssign) and _target_is_tp(node.target):
            found.append(f"{label}:{node.lineno}: augmented assignment to a TP")
        elif isinstance(node, ast.NamedExpr) and _target_is_tp(node.target) and _is_computation(node.value):
            found.append(f"{label}:{node.lineno}: walrus assignment of a computed TP")
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and str(key.value) in TP_NAMES and _is_computation(value):
                    found.append(f"{label}:{node.lineno}: dict literal with a computed TP")
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg in TP_NAMES and _is_computation(keyword.value):
                    found.append(f"{label}:{node.lineno}: keyword argument with a computed TP")
            if _call_name(node) in MUTATOR_CALLS and len(node.args) >= 3:
                name_arg, value_arg = node.args[1], node.args[2]
                if isinstance(name_arg, ast.Constant) and str(name_arg.value) in TP_NAMES and _is_computation(value_arg):
                    found.append(f"{label}:{node.lineno}: positional mutator call with a computed TP")
    return found


def test_no_consumer_computes_a_target_price_outside_the_official_producers() -> None:
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        rel = str(path.relative_to(APP))
        if rel in PRODUCERS_AND_ENGINES or rel.startswith("r2d2_v2_"):
            continue
        offenders.extend(tp_computations(path.read_text(encoding="utf-8"), rel))
    assert offenders == [], "TP computed outside the official producers (V3.2 rev 7 §7-bis, I-TP1):\n" + "\n".join(offenders)


def test_the_sweep_catches_the_mutants_codex_used_and_keeps_reads() -> None:
    # F393-8 positive controls: the same computation hidden in a conversion, a subscript assignment, a dict field, a keyword
    mutants = {
        "float": "def f(a, b):\n    our_tp = float(a * b)\n",
        "subscript": "def f(row, a, b):\n    row['our_tp'] = a * b\n",
        "dict": "def f(a, b):\n    return {'c3po_tp': a * b}\n",
        "keyword": "def f(a, b):\n    return Row(tp=a * b)\n",
        "round_mean": "import statistics\ndef f(values):\n    calibrated_tp = round(statistics.mean(values), 2)\n",
        "augmented": "def f(our_tp, k):\n    our_tp *= k\n",
        "attribute": "def f(item, a, b):\n    item.our_tp = a / b\n",
        "conditional": "def f(a, b, flag):\n    tp = a * b if flag else a\n",
        # F393-adversarial: tuple/list unpacking, positional mutator calls, and the walrus operator
        "tuple_target": "def f(a, b):\n    our_tp, x = a * b, 1\n",
        "list_target": "def f(a, b):\n    [our_tp, y] = [a * b, 1]\n",
        "setattr": "def f(row, a, b):\n    setattr(row, 'our_tp', a * b)\n",
        "operator_setitem": "import operator\ndef f(row, a, b):\n    operator.setitem(row, 'our_tp', a * b)\n",
        "walrus": "def f(a, b):\n    return (our_tp := a * b)\n",
    }
    for name, source in mutants.items():
        assert tp_computations(source, name), f"mutant not caught: {name}"
    # negative controls: reads and conversions of reads are allowed
    for name, source in {
        "read": "def f(row):\n    our_tp = row['our_tp']\n",
        "get": "def f(row):\n    c3po_tp = _float(row.get('our_tp'))\n",
        "constant": "def f():\n    c3po_tp = 0.0\n",
        "attribute_read": "def f(item):\n    tp = item.our_tp\n",
        "dict_read": "def f(record):\n    return {'tp': record['tp'], 'our_tp': float(record['tp'])}\n",
        "engine": "def f(a, b, w):\n    c3po_tp = official_blend_v1(a, b, w)\n",
        # F393-adversarial: a positional string argument that names a TP field but reads it, never writes it
        "logger_format_string": "def f(logger, row):\n    logger.info('our_tp %s', row['our_tp'])\n",
        "getattr_read": "def f(row):\n    return getattr(row, 'our_tp')\n",
        "tuple_unpack_read": "def f(row):\n    our_tp, y = row['our_tp'], 1\n",
        "setattr_read": "def f(row):\n    setattr(row, 'our_tp', row['our_tp'])\n",
    }.items():
        assert tp_computations(source, name) == [], f"false positive: {name}"


def test_the_one_pager_no_longer_blends_the_consensus_into_the_tp() -> None:
    source = (APP / "one_pager.py").read_text(encoding="utf-8")
    assert "internal_tp * (1 - consensus_weight)" not in source
    assert "official_row(" in source and "_official_valuation" in source and 'role == "producer"' in source


def test_r2d2_reads_the_official_selection_not_a_raw_snapshot() -> None:
    source = (APP / "r2d2.py").read_text(encoding="utf-8")
    assert "official_rows(self.repo.database, market, generation=generation)" in source and "generation = current_generation(self.repo.database)" in source
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
    one_pager_view = official.official_row(database, "US", "AAPL", generation=generation)
    r2d2_view = official.official_rows(database, "NASDAQ", generation=generation)["AAPL"]
    served = official.official_stamp(database, "NASDAQ", generation=generation)
    record = database.valuation_predictions_for_cycle(cycles["NASDAQ"], source=official.SOURCE_OFFICIAL)["AAPL"]
    assert one_pager_view is not None
    assert one_pager_view["our_tp"] == r2d2_view["our_tp"] == record["tp"] == 250.0 and one_pager_view["buy_in"] == r2d2_view["buy_in"] == record["buy_in"] == 200.0
    assert one_pager_view["generation_id"] == r2d2_view["generation_id"] == served["official_generation_id"] == generation["generation_id"]
    assert one_pager_view["official_cycle_id"] == r2d2_view["official_cycle_id"] == served["official_cycle_id"] == cycles["NASDAQ"]
    assert one_pager_view["tp_source"] == r2d2_view["tp_source"] == served["tp_source"] == official.SOURCE_OFFICIAL
    assert one_pager_view["official_row_sha256"] == r2d2_view["official_row_sha256"] == record["row_sha256"] and len(record["row_sha256"]) == 64


def test_every_consumer_serves_the_internal_tp_with_its_stamp_after_the_switch_without_being_edited(monkeypatch) -> None:
    """Passo 1 (I-TP1/I-TP3/I-TP4): the switch is a new selection line; One Pager, R2D2 v1 and the screeners' served
    responses resolve the SAME internal record for the same (market, symbol, generation), stamped ``official_internal_v1``,
    the consensus beside — no consumer module changed (the sweep above still passes on the same tree)."""
    from app.valuation_official_engine import SOURCE_INTERNAL

    database = _database()
    now = datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc)
    rows = {
        "B3": [{"symbol": "PETR4", "our_tp": 40.0, "buy_in": 32.0, "price": 36.0, "internal_tp": 39.0, "internal_buy_in": 31.0, "signal_quality": "validated"}],
        "NASDAQ": [{"symbol": "AAPL", "our_tp": 250.0, "buy_in": 200.0, "price": 220.0, "internal_tp": 245.0, "internal_buy_in": 196.0, "public_consensus_tp": 275.0,
                    "analyst_count": 20, "consensus_weight_percent": 35.0, "signal_quality": "validated"}],
        "NYSE": [{"symbol": "KO", "our_tp": 70.0, "buy_in": 60.0, "price": 65.0, "internal_tp": 68.0, "internal_buy_in": 58.0, "signal_quality": "validated"}],
    }
    cycles = {market: database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1", {"methodology_version": 7},
                                                       {"rows": rows[market], "universe_size": 1}, now + timedelta(minutes=i))
              for i, market in enumerate(official.MARKETS)}
    blend = official.current_generation(database)
    assert blend is not None and blend["source"] == official.SOURCE_OFFICIAL
    report = official.before_after_report(database)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    generation = official.select_generation(database, cycles=cycles, now=datetime.now(timezone.utc), activated_by="mesa", reason="P1",
                                            source=SOURCE_INTERNAL, source_version="7", before_after_sha256=report["report_sha256"])
    assert generation["source"] == SOURCE_INTERNAL and official.current_generation(database) == generation
    one_pager_view = official.official_row(database, "US", "AAPL", generation=generation)
    r2d2_view = official.official_rows(database, "NASDAQ", generation=generation)["AAPL"]
    served = official.official_stamp(database, "NASDAQ", generation=generation)
    record = database.valuation_predictions_for_cycle(cycles["NASDAQ"], source=SOURCE_INTERNAL)["AAPL"]
    assert one_pager_view is not None
    assert one_pager_view["our_tp"] == r2d2_view["our_tp"] == record["tp"] == 245.0 and one_pager_view["buy_in"] == r2d2_view["buy_in"] == record["buy_in"] == 196.0
    assert one_pager_view["public_consensus_tp"] == r2d2_view["public_consensus_tp"] == record["consensus_tp"] == 275.0  # displayed beside, never inside
    assert one_pager_view["consensus_weight_percent"] == r2d2_view["consensus_weight_percent"] == record["consensus_weight_percent"] == 0.0
    assert one_pager_view["generation_id"] == r2d2_view["generation_id"] == served["official_generation_id"] == generation["generation_id"]
    assert one_pager_view["tp_source"] == r2d2_view["tp_source"] == served["tp_source"] == official.item_stamp(r2d2_view)["tp_source"] == SOURCE_INTERNAL
    assert one_pager_view["official_row_sha256"] == r2d2_view["official_row_sha256"] == record["row_sha256"]
    # the previous generation still resolves the blend for a replay
    assert official.official_row(database, "US", "AAPL", generation=blend)["our_tp"] == 250.0  # type: ignore[index]
