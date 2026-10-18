"""The PIT reading rules of the §7.3 panel (``valuation_pit_panel``), kept OUT of the pinned panel module: the unattested
horizon on hand-built records, and the guard that ``valuation_panel`` itself carries none of the PIT rules (its bytes are
pinned by PREREG_VALUATION_DECISOR_V1 §17). The superseded-run rule and the service over real re-executor records are
pinned in ``tests/test_valuation_pit_rerun.py``."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from app import valuation_panel as panel
from app import valuation_pit_panel as pit_panel
from tests.test_valuation_panel import _record

UTC = timezone.utc
INSTANT = datetime(2026, 9, 4, 22, 0, tzinfo=UTC)


def test_the_official_horizon_12m_is_present_while_an_unattested_literal_is_read_as_missing() -> None:
    """P2-1: the official emitter's block (``consensus_block`` defaults the horizon to ``12m``) is ``present``; the PIT
    re-executor's ``N/D`` — a literal that attests nothing (design §3) — is ``consensus_unattested:horizon``, as None/"",
    with the literal kept in the block reported and the record untouched."""
    record = _record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=INSTANT)
    assert record["decomposition"]["consensus"]["horizon"] == "12m" and pit_panel.consensus_of(record) == panel._consensus_of(record)
    assert pit_panel.consensus_of(record)[1] == "present"
    assert pit_panel.UNATTESTED_HORIZONS == ("N/D",)
    for literal in pit_panel.UNATTESTED_HORIZONS:
        unattested = _record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=INSTANT, consensus_horizon=literal)
        stored = copy.deepcopy(unattested)
        consensus, status = pit_panel.consensus_of(unattested)
        assert status == "consensus_unattested:horizon" and consensus["horizon"] == literal and consensus["tp"] == 275.0  # reported, never compared
        assert unattested == stored  # the record is read, never rewritten (its row_sha256 stays the stored one)
        assert panel._consensus_of(unattested)[1] == "present"  # the pinned panel knows no such literal: only the PIT panel reads it
        # the first missing field still names the cause, in the PROMO-2 (c) order
        no_source = _record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=INSTANT, consensus_horizon=literal, consensus_origin_source=None)
        assert no_source["decomposition"]["consensus"]["source"] is None
        assert pit_panel.consensus_of(no_source)[1] == "consensus_unattested:source" and pit_panel.consensus_of(no_source)[0]["horizon"] == literal
    for missing in (None, ""):
        block = {**record["decomposition"]["consensus"], "horizon": missing}
        blank = {**record, "decomposition": {**record["decomposition"], "consensus": block}}
        assert pit_panel.consensus_of(blank) == panel._consensus_of(blank) and pit_panel.consensus_of(blank)[1] == "consensus_unattested:horizon"


def test_the_pinned_panel_module_carries_no_pit_rule() -> None:
    """``valuation_panel.py`` is pinned byte for byte (PREREG_VALUATION_DECISOR_V1 §17): the PIT rules live in
    ``valuation_pit_panel`` only, and the PIT receipt names them under its own schema."""
    for name in ("UNATTESTED_HORIZONS", "SUPERSEDED_RUN", "PIT_RERUN_ANALYSIS_TYPE", "superseded_run_keys", "refuse_superseded_runs"):
        assert not hasattr(panel, name), name
    rules = pit_panel.pit_rules()
    assert rules["schema"] == pit_panel.PIT_SCHEMA_VERSION == f"{panel.SCHEMA_VERSION}+PIT-v1"
    assert rules["unattested_horizons"] == ["N/D"] and pit_panel.SUPERSEDED_RUN in rules["superseded_run_rule"]
    assert pit_panel.DEFAULT_SOURCES == ("v3_2_shadow",)
