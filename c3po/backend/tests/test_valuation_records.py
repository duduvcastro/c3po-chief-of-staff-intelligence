"""Ben Kenobi Records: the permanent ledger of the SERVED official TP (V3.2 rev 7 §7-bis, the owner's "um só para tudo").

A record is appended when the official selection changes what it serves (``Database.capture_served_valuation_changes``, run
after every generation insert): the served rows of the head — what Last Jedi, Dark Side, the One Pager and R2D2 read — compared
with the ledger's own latest record per (market, symbol). Producer snapshots (universe, on-demand, One Pager) are no longer
read by the ledger; the rows written before (``tp_source`` NULL, migration 054) are the LEGACY regime: never rewritten, and
labelled as such by the API and the tab."""
import re
import threading
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from app import main as app_main
from app import valuation_official as official
from app.config import Settings
from app.database import LEGACY_TP_SOURCE_ONE_PAGER, LEGACY_TP_SOURCE_PRODUCER, Database
from app.market_data.b3_screener import B3ScreenerService
from app.market_data.us_screener import USScreeningService
from app.schemas import ValuationChangeResponse
from app.valuation_accuracy import SERVED_CAPTURE
from app.valuation_official_engine import SOURCE_BLEND, SOURCE_INTERNAL

DB_DIR = Path(__file__).resolve().parents[2] / "db"
NIGHT = datetime(2026, 10, 19, 23, 0, tzinfo=timezone.utc)


def valuation_row(tp: float, buy_in: float, consensus: float, confidence: float, *, internal_tp: float | None = None,
                  internal_buy_in: float | None = None, symbol: str = "PRNR3", name: str = "Priner Servicos Industriais") -> dict[str, Any]:
    """A producer row the official selection can serve under both sources: the blend (``our_tp``/``buy_in``, the consensus
    inside), the internal TP and buy-in, and the producer's internal view (rev 9)."""
    internal = internal_tp if internal_tp is not None else tp
    return {
        "symbol": symbol,
        "name": name,
        "currency": "BRL",
        "price": 18.40,
        "our_tp": tp,
        "buy_in": buy_in,
        "internal_tp": internal,
        "internal_buy_in": internal_buy_in if internal_buy_in is not None else buy_in,
        "internal_score": 70.0, "internal_status": "full_match", "internal_expected_total_return_percent": 15.0,
        "public_consensus_tp": consensus,
        "consensus_weight_percent": 25.0,
        "valuation_confidence": confidence,
        "analyst_count": 4,
    }


def _us_row(symbol: str, tp: float, *, internal_tp: float | None = None, name: str | None = None) -> dict[str, Any]:
    return valuation_row(tp, tp * 0.8, tp * 1.1, 80, internal_tp=internal_tp, internal_buy_in=(internal_tp or tp) * 0.8, symbol=symbol,
                         name=name or symbol) | {"currency": "USD", "price": tp * 0.85}


def _publish(database: Database, market: str, rows: list[dict[str, Any]], at: datetime, methodology_id: str, version: int = 9) -> str:
    return database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", methodology_id,
                                           {"market": market, "source": "Brapi + EODHD", "methodology_version": version},
                                           {"rows": rows, "universe_size": len(rows)}, at)


def _database(tmp_path) -> tuple[Database, str]:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    return database, database.ensure_methodology_version("c3po_equity_valuation", 9, {}, "test")


def _bootstrap(database: Database, methodology_id: str, b3_rows: list[dict[str, Any]], at: datetime) -> dict[str, str]:
    """The three markets the bootstrap needs (B3 last: its publication activates the first generation)."""
    return {
        "NASDAQ": _publish(database, "NASDAQ", [_us_row("AAPL", 250.0, internal_tp=230.0)], at, methodology_id),
        "NYSE": _publish(database, "NYSE", [_us_row("KO", 70.0, internal_tp=66.0)], at, methodology_id),
        "B3": _publish(database, "B3", b3_rows, at, methodology_id),
    }


def _wall() -> datetime:
    return datetime.now(timezone.utc)


def _noon_zone() -> timezone:
    """A fixed zone where the wall clock reads about noon: a freeze of minutes never reaches ITS midnight (the bound
    ``freeze_selection`` enforces in ``FREEZE_NIGHTLY_ZONE``), whenever the suite runs — as the P1 tests do."""
    return timezone(timedelta(hours=12 - datetime.now(timezone.utc).hour))


def _activation(database: Database) -> datetime:
    head = official.current_generation(database)
    assert head is not None
    return database._selection_instant(head["activated_at"])


def _switch_to_internal(database: Database, monkeypatch, cycles: dict[str, str]) -> dict[str, Any]:
    """The mesa's switch as it ran on 20/10 (select_generation, explicit order); the lock receipt is this proposal's, as the
    P1 tests authorize it."""
    report = official.before_after_report(database, cycles=cycles, targeted={})
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256", report["report_sha256"])
    return official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="P1 switch",
                                      source=SOURCE_INTERNAL, source_version="9", before_after_sha256=report["report_sha256"])


def _rollback_to_blend(database: Database, cycles: dict[str, str]) -> dict[str, Any]:
    return official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="rollback", source=SOURCE_BLEND)


def _served(database: Database) -> dict[tuple[str, str], dict[str, Any]]:
    """What every consumer serves right now (official_rows of the head, per market, plus its targeted admissions)."""
    head = official.current_generation(database)
    served = {(market, symbol): item for market in official.MARKETS
              for symbol, item in official.official_rows(database, market, generation=head).items()}
    for symbol in (head or {}).get("targeted") or {}:
        item = official.official_row(database, "B3", symbol, generation=head)
        if item is not None:
            served.setdefault(("B3", symbol), item)
    return served


def _latest(database: Database) -> dict[tuple[str, str], dict[str, Any]]:
    _, records = database.list_valuation_changes(limit=300)
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:  # newest first, as the tab lists them
        latest.setdefault((record["market"], record["symbol"]), record)
    return latest


def _assert_ledger_states_what_is_served(database: Database) -> None:
    """The latest record of every served symbol states the served TP and buy-in (at the precision the tab shows) and their source.
    Its generation is the one that STARTED serving those numbers — a later generation serving the same numbers appends nothing."""
    served = _served(database)
    latest = _latest(database)
    assert served, "the fixture serves nothing"
    for key, item in served.items():
        record = latest[key]
        assert record["tp_source"] == item["tp_source"] and record["legacy"] is False and record["tp_source_label"] == item["tp_source"], key
        assert round(record["new_tp"], 2) == round(item["our_tp"], 2) and round(record["new_buy_in"], 2) == round(item["buy_in"], 2), key
        assert database.valuation_official_selection(str(record["generation_id"])) is not None, key


# ------------------------------------------------------------------ the tab's contract, on the served ledger


def test_valuation_records_capture_only_real_changes_and_sort_newest_first(tmp_path) -> None:
    database, methodology_id = _database(tmp_path)
    first_at = datetime(2026, 8, 13, 23, 0, tzinfo=timezone.utc)
    _bootstrap(database, methodology_id, [valuation_row(28.0, 17.0, 26.0, 82)], first_at)
    _publish(database, "B3", [valuation_row(28.0, 17.0, 26.0, 82)], first_at + timedelta(hours=1), methodology_id)  # same served row
    _publish(database, "B3", [valuation_row(31.5, 18.2, 29.0, 87)], first_at + timedelta(days=1), methodology_id)
    activated = _activation(database)

    total, records = database.list_valuation_changes(limit=10, symbol="PRNR3")

    assert total == 2
    assert records[0]["changed_at"] == activated  # when the served number changed: the generation's activation
    assert records[0]["old_tp"] == 28.0 and records[0]["new_tp"] == 31.5
    assert records[0]["old_buy_in"] == 17.0 and records[0]["new_buy_in"] == 18.2
    assert records[0]["trigger_type"] == "market_data" and records[0]["tp_source"] == SOURCE_BLEND
    assert records[0]["metadata"]["changed_fields"] == ["c3po_tp", "buy_in", "consensus_tp", "confidence"]
    assert records[1]["trigger_type"] == "initial"


def test_valuation_records_carry_logo_url_from_the_latest_universe_snapshot(tmp_path) -> None:
    """Ben Kenobi Records used to render a broken logo: the frontend fetched it from
    /api/v1/company-logo/{symbol} -- an endpoint that does not exist in this backend.
    The B3/US screeners already store a logo_url per company in their universe rows
    (row["logo_url"]); list_valuation_changes() cross-references those (already computed, no
    extra network/storage) so each record carries a real logo_url instead of relying on a
    /api/v1/company-logo/{symbol} proxy or a market-agnostic external CDN
    guess that only ever worked for US tickers.
    """
    database, methodology_id = _database(tmp_path)
    row = valuation_row(28.0, 17.0, 26.0, 82) | {"logo_url": "https://cdn.example.com/prnr3.png"}
    _bootstrap(database, methodology_id, [row], datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc))

    _, records = database.list_valuation_changes(limit=10, symbol="PRNR3")

    assert records[0]["logo_url"] == "https://cdn.example.com/prnr3.png"


def test_valuation_records_filter_by_company_market_and_trigger(tmp_path) -> None:
    database, methodology_id = _database(tmp_path)
    at = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    _publish(database, "NASDAQ", [_us_row("AMZN", 285.0, name="Amazon.com, Inc.")], at, methodology_id)
    _publish(database, "NYSE", [_us_row("KO", 70.0)], at, methodology_id)
    _publish(database, "B3", [valuation_row(28.0, 17.0, 26.0, 82)], at, methodology_id)
    # a One Pager is a CONSUMER of the served TP: its snapshot is no longer a ledger stream (it never changes the TP)
    database.save_analysis_snapshot("one_pager_valuation", "US:AMZN", methodology_id, {"market": "NASDAQ", "methodology_version": 9},
                                    {"row": {"symbol": "AMZN", "company_name": "Amazon.com, Inc.", "currency": "USD", "price": 210.0,
                                             "c3po_tp": 285.0, "consensus_tp": 270.0, "buy_in": 198.0, "confidence": 86}}, at)

    total, records = database.list_valuation_changes(symbol="amazon", market="NASDAQ", trigger_type="initial")

    assert total == 1
    assert records[0]["symbol"] == "AMZN"
    assert records[0]["company_name"] == "Amazon.com, Inc."
    assert records[0]["metadata"]["analysis_type"] == "valuation_official_selection"


def test_valuation_records_do_not_use_symbol_as_same_time_tiebreaker(tmp_path, monkeypatch) -> None:
    database, methodology_id = _database(tmp_path)
    ids = count(1)
    monkeypatch.setattr("app.database.uuid4", lambda: UUID(int=next(ids)))
    row_a = valuation_row(22.0, 16.0, 21.0, 80, symbol="AAAA3", name="Alpha")
    row_z = valuation_row(24.0, 17.0, 23.0, 82, symbol="ZZZZ3", name="Zeta")

    _bootstrap(database, methodology_id, [row_a, row_z], datetime(2026, 8, 14, 20, 0, tzinfo=timezone.utc))

    _, records = database.list_valuation_changes(limit=10, market="B3")

    assert [item["symbol"] for item in records] == ["ZZZZ3", "AAAA3"]  # same instant: the later insertion first, never by symbol


def test_initial_record_does_not_inherit_an_old_ir_event(tmp_path) -> None:
    database, methodology_id = _database(tmp_path)
    database.register_ir_securities([{
        "market": "B3", "symbol": "PRNR3", "company_name": "Priner",
        "name_key": "PRINER", "exchange": "B3",
    }])
    company = database.list_ir_companies("B3")[0]
    event_at = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    database.save_ir_events([{
        "source_code": "cvm", "external_id": "old-prnr3-itr", "company_id": company["id"],
        "market": "B3", "symbol": "PRNR3", "company_name": "Priner",
        "event_type": "Financial Results", "title": "ITR antigo", "summary": "Old CVM filing",
        "published_at": event_at, "published_time_precision": "datetime",
        "reference_date": None, "official_url": "https://dados.cvm.gov.br/",
        "document_url": None, "materiality": "high", "valuation_relevant": True,
        "valuation_status": "incorporated", "raw_metadata": {}, "collected_at": event_at,
    }])
    _bootstrap(database, methodology_id, [valuation_row(28.0, 17.0, 26.0, 82)], event_at + timedelta(days=1))

    _, records = database.list_valuation_changes(limit=10, symbol="PRNR3")

    assert records[0]["trigger_type"] == "initial"
    assert records[0]["source_name"] == "C3PO Valuation Engine" and records[0]["source_url"] is None
    assert "Old CVM filing" not in records[0]["trigger_summary"] and "event_id" not in records[0]["metadata"]


def test_a_served_initial_record_is_born_in_the_form_db_009_rewrites_at_every_start(tmp_path) -> None:
    """db/009 runs at every start and sets summary/source/url of EVERY ``initial`` record and drops its ``event_id``: a served
    initial record already carries exactly those values (the constants are read from the migration itself), so that start-up
    UPDATE never changes the content of a served record."""
    sql = (DB_DIR / "009_fix_initial_valuation_records.sql").read_text(encoding="utf-8")
    summary = re.search(r"trigger_summary = '([^']*)'", sql)
    source_name = re.search(r"source_name = '([^']*)'", sql)
    assert summary and source_name and "source_url = NULL" in sql and "metadata - 'event_id'" in sql
    assert (Database._INITIAL_SUMMARY, Database._INITIAL_SOURCE_NAME) == (summary.group(1), source_name.group(1))
    database, methodology_id = _database(tmp_path)
    _bootstrap(database, methodology_id, [valuation_row(28.0, 17.0, 26.0, 82)], NIGHT)

    initials = [item for item in database._valuation_changes if item["trigger_type"] == "initial"]

    assert len(initials) == 3
    for record in initials:
        rewritten = {**record, "trigger_summary": summary.group(1), "source_name": source_name.group(1), "source_url": None,
                     "metadata": {key: value for key, value in record["metadata"].items() if key != "event_id"}}
        assert rewritten == record


# ------------------------------------------------------------------ the SERVED TP: equal to what Last Jedi shows


class _StubHttp:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def get_json(self, url, *, params=None, headers=None):  # pragma: no cover - the re-serve never calls the provider
        self.calls.append(url)
        raise AssertionError("Last Jedi re-serves from the official selection: the producer is never run here")


def _last_jedi_b3_row(symbol: str, *, tp: float, internal_tp: float, risk: float, price: float = 20.0) -> dict[str, Any]:
    """A published B3 universe row the B3 screener ranks into Last Jedi (validated TP, ``full_match`` in both views, Power Zone
    upside), with a blend TP (consensus inside) different from the internal TP."""
    buy_in, internal_buy_in = price * 0.95, price * 0.93
    return {
        "symbol": symbol, "issuer": symbol[:4], "name": f"{symbol} SA", "logo_url": None, "sector": "Utilities",
        "valuation_profile": "utilities", "price": price, "change_percent": 0.5, "volume": 1_000_000.0,
        "adtv_90d": 25_000_000.0, "market_cap": 2_000_000_000.0, "our_tp": tp, "internal_tp": internal_tp,
        "buy_in": buy_in, "internal_buy_in": internal_buy_in, "upside_percent": (tp / price - 1) * 100,
        "expected_total_return_percent": 30.0, "price_vs_buy_in_percent": (price / buy_in - 1) * 100,
        "buy_in_models": {"Market Structure": buy_in}, "internal_buy_in_models": {"Market Structure": internal_buy_in},
        "score": 90.0, "risk_score": risk, "valuation_confidence": 80.0, "method_dispersion_percent": 20.0, "quality_score": 80,
        "status": "full_match", "thesis": "t", "risk": "r", "as_of": "2026-10-19T21:00:00+00:00",
        "tp_validation_status": "validated", "tp_validation_score": 85.0,
        "public_consensus_tp": tp * 1.3, "analyst_count": 8, "consensus_weight_percent": 25.0,
        "internal_score": 88.0, "internal_status": "full_match", "internal_expected_total_return_percent": 25.0,
    }


def _last_jedi(database: Database) -> tuple[B3ScreenerService, USScreeningService]:
    settings = Settings(brapi_token="", auth_cookie_secure=False)  # no credential: a producer build would raise at once
    b3 = B3ScreenerService(settings, database, _StubHttp())  # type: ignore[arg-type]
    b3._matrix_macro = {"selic": 0.12, "ipca12m": 0.045}
    us = USScreeningService(settings, database, None, None)  # type: ignore[arg-type]  # _served_rows reads the selection only
    return b3, us


def _assert_ben_kenobi_equals_last_jedi(database: Database, b3: B3ScreenerService, us: USScreeningService) -> list[str]:
    latest = _latest(database)
    items = b3.screen().items  # Last Jedi B3 (/api/v1/candidates/b3), re-served from the selection
    assert items, "the fixture ranks nothing into Last Jedi"
    for item in items:
        record = latest[("B3", item.symbol)]
        assert round(record["new_tp"], 2) == item.our_tp and round(record["new_buy_in"], 2) == item.buy_in, item.symbol
        assert record["tp_source"] == item.tp_source and record["legacy"] is False, item.symbol
    generation = official.current_generation(database)
    for market in ("NASDAQ", "NYSE"):  # Last Jedi US (/api/v1/candidates/nasdaq|nyse) serves these rows
        for row in us._served_rows(market, generation):
            record = latest[(market, row["symbol"])]
            assert round(record["new_tp"], 2) == round(row["our_tp"], 2) and round(record["new_buy_in"], 2) == round(row["buy_in"], 2)
            assert record["tp_source"] == row["tp_source"] and record["legacy"] is False
    return [item.symbol for item in items]


def test_ben_kenobi_shows_what_last_jedi_shows_before_and_after_the_switch_and_on_the_next_night(tmp_path, monkeypatch) -> None:
    database, methodology_id = _database(tmp_path)
    rows = [_last_jedi_b3_row("AAAA3", tp=30.0, internal_tp=28.0, risk=5.0), _last_jedi_b3_row("BBBB3", tp=29.0, internal_tp=27.0, risk=6.0),
            _last_jedi_b3_row("CCCC3", tp=26.0, internal_tp=25.0, risk=40.0), _last_jedi_b3_row("DDDD3", tp=27.0, internal_tp=26.5, risk=41.0)]
    cycles = _bootstrap(database, methodology_id, rows, NIGHT)
    b3, us = _last_jedi(database)

    assert _assert_ben_kenobi_equals_last_jedi(database, b3, us) == ["AAAA3", "BBBB3"]  # blend era: the blend is served
    _assert_ledger_states_what_is_served(database)

    generation = _switch_to_internal(database, monkeypatch, cycles)

    assert _assert_ben_kenobi_equals_last_jedi(database, b3, us) == ["AAAA3", "BBBB3"]
    _assert_ledger_states_what_is_served(database)
    latest = _latest(database)
    assert {key: record["new_tp"] for key, record in latest.items() if key[0] == "B3"} == {
        ("B3", "AAAA3"): 28.0, ("B3", "BBBB3"): 27.0, ("B3", "CCCC3"): 25.0, ("B3", "DDDD3"): 26.5}  # the internal TP: no consensus inside
    assert all(record["generation_id"] == generation["generation_id"] and record["metadata"]["consensus_weight_percent"] == 0.0
               for record in latest.values())

    # the next night under the internal source: the ledger follows the served TP, never the producer's blend
    nightly = [_last_jedi_b3_row("AAAA3", tp=31.0, internal_tp=28.5, risk=5.0), _last_jedi_b3_row("BBBB3", tp=29.5, internal_tp=27.0, risk=6.0),
               _last_jedi_b3_row("CCCC3", tp=26.0, internal_tp=25.0, risk=40.0), _last_jedi_b3_row("DDDD3", tp=27.0, internal_tp=26.5, risk=41.0)]
    before = len(database._valuation_changes)
    _publish(database, "B3", nightly, _wall(), methodology_id)

    assert _assert_ben_kenobi_equals_last_jedi(database, b3, us) == ["AAAA3", "BBBB3"]
    _assert_ledger_states_what_is_served(database)
    added = database._valuation_changes[before:]
    # AAAA3's served (internal) TP moved; BBBB3's blend moved (29.0 → 29.5) with its consensus, but its served TP did not: the
    # ledger states the consensus beside an unchanged TP (27.0), never the blend; CCCC3/DDDD3 served the same numbers: nothing
    assert [(item["symbol"], item["old_tp"], item["new_tp"], item["metadata"]["changed_fields"]) for item in added] == [
        ("AAAA3", 28.0, 28.5, ["c3po_tp", "consensus_tp"]), ("BBBB3", 27.0, 27.0, ["consensus_tp"])]
    assert all(item["trigger_type"] == "market_data" and item["tp_source"] == SOURCE_INTERNAL for item in added)


def test_a_generation_switch_and_a_rollback_each_append_one_record_per_served_symbol(tmp_path, monkeypatch) -> None:
    database, methodology_id = _database(tmp_path)
    cycles = _bootstrap(database, methodology_id, [valuation_row(40.0, 32.0, 48.0, 72, internal_tp=36.0, internal_buy_in=29.0)], NIGHT)
    before = len(database._valuation_changes)

    switched = _switch_to_internal(database, monkeypatch, cycles)

    switch_records = database._valuation_changes[before:]
    assert sorted((item["market"], item["symbol"]) for item in switch_records) == [("B3", "PRNR3"), ("NASDAQ", "AAPL"), ("NYSE", "KO")]
    petr = next(item for item in switch_records if item["symbol"] == "PRNR3")
    assert (petr["trigger_type"], petr["old_tp"], petr["new_tp"], petr["old_buy_in"], petr["new_buy_in"]) == ("methodology", 40.0, 36.0, 32.0, 29.0)
    assert petr["tp_source"] == SOURCE_INTERNAL and petr["generation_id"] == switched["generation_id"]
    assert petr["metadata"]["previous_tp_source"] == SOURCE_BLEND and "tp_source" in petr["metadata"]["changed_fields"]
    assert petr["trigger_title"] == f"TP oficial servido: {SOURCE_INTERNAL} (antes: {SOURCE_BLEND})"
    served_row = official.official_row(database, "B3", "PRNR3")
    assert served_row is not None and petr["metadata"]["official_row_sha256"] == served_row["official_row_sha256"]

    middle = len(database._valuation_changes)
    rolled = _rollback_to_blend(database, cycles)

    rollback_records = database._valuation_changes[middle:]
    assert len(rollback_records) == 3 and {item["generation_id"] for item in rollback_records} == {rolled["generation_id"]}
    assert all(item["trigger_type"] == "methodology" and item["tp_source"] == SOURCE_BLEND
               and item["metadata"]["previous_tp_source"] == SOURCE_INTERNAL for item in rollback_records)
    assert next(item for item in rollback_records if item["symbol"] == "PRNR3")["new_tp"] == 40.0
    _assert_ledger_states_what_is_served(database)


def test_legacy_records_are_never_rewritten_and_are_labelled_legacy(tmp_path, monkeypatch) -> None:
    """The rows written before the served ledger (producer blend rows, One Pager rows) stay exactly as they were — through the
    boundary, the switch and the next night — and the API states them as legacy, by stream; the boundary with the served
    regime is appended once per symbol."""
    database, methodology_id = _database(tmp_path)
    legacy_universe = {"id": "legacy-1", "snapshot_id": "s-legacy", "market": "B3", "symbol": "PRNR3", "company_name": "Priner",
                       "changed_at": datetime(2026, 10, 1, tzinfo=timezone.utc), "trigger_type": "market_data", "trigger_title": "legacy",
                       "trigger_summary": "C3PO TP passou de R$ 39,00 para R$ 40,00.", "source_name": "Brapi + EODHD", "source_url": None,
                       "currency": "BRL", "old_tp": 39.0, "new_tp": 40.0, "tp_change_percent": 2.56, "old_buy_in": 31.0, "new_buy_in": 32.0,
                       "old_consensus_tp": 47.0, "new_consensus_tp": 48.0, "price": 18.4, "old_confidence": 72.0, "new_confidence": 72.0,
                       "methodology_name": "C3PO Valuation Model", "methodology_version": 9,
                       "metadata": {"changed_fields": ["c3po_tp"], "analysis_type": "valuation_universe", "consensus_weight_percent": 25.0}}
    legacy_one_pager = {**legacy_universe, "id": "legacy-op", "snapshot_id": "s-op", "market": "NASDAQ", "symbol": "AAPL", "company_name": "Apple",
                        "changed_at": datetime(2026, 10, 2, tzinfo=timezone.utc), "trigger_type": "web_research", "currency": "USD",
                        "new_tp": 250.0, "new_buy_in": 200.0, "metadata": {"analysis_type": "one_pager_valuation"}}
    database._valuation_changes.extend([dict(legacy_universe), dict(legacy_one_pager)])
    cycles = _bootstrap(database, methodology_id, [valuation_row(40.0, 32.0, 48.0, 72, internal_tp=36.0, internal_buy_in=29.0)], NIGHT)

    boundary = _latest(database)
    assert boundary[("B3", "PRNR3")]["trigger_type"] == "methodology" and boundary[("B3", "PRNR3")]["metadata"]["previous_tp_source"] is None
    assert boundary[("B3", "PRNR3")]["metadata"]["previous_tp_source_label"] == LEGACY_TP_SOURCE_PRODUCER
    assert (boundary[("B3", "PRNR3")]["old_tp"], boundary[("B3", "PRNR3")]["new_tp"]) == (40.0, 40.0)  # same number, another regime: stated once
    assert boundary[("NASDAQ", "AAPL")]["metadata"]["previous_tp_source_label"] == LEGACY_TP_SOURCE_ONE_PAGER
    assert boundary[("NASDAQ", "AAPL")]["metadata"]["previous_record_id"] == "legacy-op"
    assert "registro legado" in boundary[("B3", "PRNR3")]["trigger_summary"]
    assert database.capture_served_valuation_changes() == 0  # idempotent: the ledger already states what the head serves

    _switch_to_internal(database, monkeypatch, cycles)
    _publish(database, "B3", [valuation_row(41.0, 33.0, 50.0, 72, internal_tp=37.0, internal_buy_in=30.0)], _wall(), methodology_id)

    assert database._valuation_changes[0] == legacy_universe and database._valuation_changes[1] == legacy_one_pager  # never rewritten
    _, records = database.list_valuation_changes(limit=300)
    labels = {record["id"]: (record["legacy"], record["tp_source"], record["generation_id"], record["tp_source_label"]) for record in records}
    assert labels["legacy-1"] == (True, None, None, LEGACY_TP_SOURCE_PRODUCER)
    assert labels["legacy-op"] == (True, None, None, LEGACY_TP_SOURCE_ONE_PAGER)
    assert all(not legacy for record_id, (legacy, *_) in labels.items() if record_id not in {"legacy-1", "legacy-op"})
    assert sum(1 for record in records if record["metadata"].get("previous_tp_source_label") == LEGACY_TP_SOURCE_PRODUCER) == 1  # one boundary
    _assert_ledger_states_what_is_served(database)


def test_no_duplicate_records_for_a_repeated_capture_a_freeze_a_concurrent_capture_or_a_repeated_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(official, "FREEZE_NIGHTLY_ZONE", _noon_zone())
    database, methodology_id = _database(tmp_path)
    cycles = _bootstrap(database, methodology_id, [valuation_row(40.0, 32.0, 48.0, 72, internal_tp=36.0, internal_buy_in=29.0)], NIGHT)
    assert len(database._valuation_changes) == 3

    assert database.capture_served_valuation_changes() == 0  # the same head, captured again
    _publish(database, "B3", [valuation_row(40.0, 32.0, 48.0, 72, internal_tp=36.0, internal_buy_in=29.0)], NIGHT + timedelta(hours=1),
             methodology_id)  # a new cycle serving the same numbers: a new generation, nothing new served
    now = _wall()
    official.freeze_selection(database, now=now, until=now + timedelta(minutes=30), reason="test", activated_by="mesa")  # same rows
    assert len(database._valuation_changes) == 3

    # the switch lands while the capture is down: the ledger lags the head; eight captures then race for it
    monkeypatch.setattr(database, "_capture_served_after_selection", lambda: None)
    switched = _switch_to_internal(database, monkeypatch, cycles)
    monkeypatch.undo()
    barrier = threading.Barrier(8)
    appended: list[int] = []

    def capture() -> None:
        barrier.wait()
        appended.append(database.capture_served_valuation_changes())

    threads = [threading.Thread(target=capture) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(appended) == [0] * 7 + [3]
    served_records = [item for item in database._valuation_changes if item.get("generation_id") == switched["generation_id"]]
    assert sorted((item["market"], item["symbol"]) for item in served_records) == [("B3", "PRNR3"), ("NASDAQ", "AAPL"), ("NYSE", "KO")]
    # the store itself refuses a second record of the same (generation, market, symbol), as migration 054's unique index does
    duplicate = {**served_records[0], "id": "another-id", "new_tp": 1.0}
    fresh = {**served_records[0], "id": "fresh-1", "generation_id": "not-yet-recorded"}
    database._store_valuation_changes([duplicate, fresh, {**fresh, "id": "fresh-2"}])  # one per key, within the batch too
    assert len([item for item in database._valuation_changes if item.get("generation_id") == switched["generation_id"]]) == 3
    assert [item["id"] for item in database._valuation_changes if item.get("generation_id") == "not-yet-recorded"] == ["fresh-1"]
    keys = [(item.get("generation_id"), item["market"], item["symbol"]) for item in database._valuation_changes if item.get("generation_id")]
    assert len(keys) == len(set(keys))
    with pytest.raises(ValueError, match="only records of the official selection"):  # the producer-row stream is never written again
        database._store_valuation_changes([{**served_records[0], "id": "legacy-style", "generation_id": None, "tp_source": None}])


def test_cycles_that_are_never_served_are_never_recorded(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(official, "FREEZE_NIGHTLY_ZONE", _noon_zone())
    database, methodology_id = _database(tmp_path)
    _bootstrap(database, methodology_id, [valuation_row(40.0, 32.0, 48.0, 72)], NIGHT)
    before = database.list_valuation_changes(limit=300)[0]
    now = _wall()
    official.freeze_selection(database, now=now, until=now + timedelta(minutes=30), reason="test", activated_by="mesa")
    _publish(database, "B3", [valuation_row(44.0, 35.0, 52.0, 72)], _wall(), methodology_id)  # held by the freeze: never served

    assert database.list_valuation_changes(limit=300)[0] == before
    assert _latest(database)[("B3", "PRNR3")]["new_tp"] == 40.0 == _served(database)[("B3", "PRNR3")]["our_tp"]


def test_the_ir_propagation_shape_records_one_change_and_a_targeted_admission_is_recorded(tmp_path) -> None:
    database, methodology_id = _database(tmp_path)
    _bootstrap(database, methodology_id, [valuation_row(40.0, 32.0, 48.0, 72)], NIGHT)
    changed = valuation_row(42.0, 33.0, 50.0, 72)
    database.save_analysis_snapshot("security_valuation", "PRNR3", methodology_id, {"methodology_version": 9}, {"row": changed},
                                    _wall())  # an on-demand cycle of a universe member: never admitted, never served
    _publish(database, "B3", [changed], _wall(), methodology_id)

    _, records = database.list_valuation_changes(limit=10, symbol="PRNR3")
    assert [(item["trigger_type"], item["old_tp"], item["new_tp"]) for item in records] == [("market_data", 40.0, 42.0), ("initial", None, 40.0)]

    # an on-demand valuation of a symbol OUTSIDE the universe is admitted into a new generation: it is served, so it is recorded
    database.save_analysis_snapshot("security_valuation", "WEGE3", methodology_id, {"methodology_version": 9},
                                    {"row": valuation_row(50.0, 40.0, 60.0, 75, symbol="WEGE3", name="WEG")}, _wall())
    head = official.current_generation(database)
    assert head is not None and "WEGE3" in head["targeted"]
    wege = _latest(database)[("B3", "WEGE3")]
    assert (wege["trigger_type"], wege["new_tp"], wege["metadata"]["official_scope"], wege["generation_id"]) == (
        "initial", 50.0, "targeted", head["generation_id"])
    _assert_ledger_states_what_is_served(database)


def test_a_us_symbol_gets_the_trigger_of_its_ir_event(tmp_path) -> None:
    """ir_security_map keys a US listing as "US" (db/002): the capture asks for the events of NASDAQ/NYSE symbols under "US"
    (the producer-row capture asked under NASDAQ/NYSE and never found one, since #27)."""
    database, methodology_id = _database(tmp_path)
    _bootstrap(database, methodology_id, [valuation_row(40.0, 32.0, 48.0, 72)], NIGHT)
    database.register_ir_securities([{"market": "US", "symbol": "AAPL", "company_name": "Apple Inc.", "name_key": "APPLE", "exchange": "NASDAQ"}])
    company = database.list_ir_companies("US")[0]
    filed_at = _wall()
    database.save_ir_events([{
        "source_code": "sec", "external_id": "aapl-10q", "company_id": company["id"], "market": "US", "symbol": "AAPL",
        "company_name": "Apple Inc.", "event_type": "Financial Results", "title": "10-Q Apple", "summary": "Quarterly report",
        "published_at": filed_at, "published_time_precision": "datetime", "reference_date": None,
        "official_url": "https://www.sec.gov/", "document_url": "https://www.sec.gov/aapl-10q", "materiality": "high",
        "valuation_relevant": True, "valuation_status": "incorporated", "raw_metadata": {}, "collected_at": filed_at,
    }])
    _publish(database, "NASDAQ", [_us_row("AAPL", 260.0, internal_tp=240.0)], _wall(), methodology_id)

    record = _latest(database)[("NASDAQ", "AAPL")]
    assert (record["trigger_type"], record["trigger_title"], record["source_name"]) == ("financial_results", "10-Q Apple", "SEC")
    assert record["source_url"] == "https://www.sec.gov/aapl-10q" and record["metadata"]["event_id"]


def test_a_capture_failure_never_fails_the_generation(tmp_path, monkeypatch, caplog) -> None:
    database, methodology_id = _database(tmp_path)

    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(official, "official_rows", broken)
    _bootstrap(database, methodology_id, [valuation_row(40.0, 32.0, 48.0, 72)], NIGHT)

    assert official.current_generation(database) is not None  # the generation was written
    assert database.list_valuation_changes(limit=10)[0] == 0
    assert "served capture failed" in caplog.text
    monkeypatch.undo()
    assert database.capture_served_valuation_changes() == 3  # the next capture catches up: the ledger re-diffs against itself


def test_a_legacy_record_dated_after_the_activation_is_still_followed_by_the_served_one(tmp_path) -> None:
    """A legacy One Pager row dated after the head's activation is the symbol's latest: the served record that follows it is
    dated right after it, so the tab's latest row per company is always the served one."""
    database, methodology_id = _database(tmp_path)
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    database._valuation_changes.append({
        "id": "legacy-op", "snapshot_id": "s-op", "market": "NASDAQ", "symbol": "AAPL", "company_name": "Apple", "changed_at": future,
        "trigger_type": "web_research", "trigger_title": "One Pager", "trigger_summary": "", "source_name": "EODHD", "source_url": None,
        "currency": "USD", "old_tp": None, "new_tp": 250.0, "tp_change_percent": None, "old_buy_in": None, "new_buy_in": 200.0,
        "old_consensus_tp": None, "new_consensus_tp": 275.0, "price": 212.5, "old_confidence": None, "new_confidence": 80.0,
        "methodology_name": "C3PO Valuation Model", "methodology_version": 9, "metadata": {"analysis_type": "one_pager_valuation"}})
    _bootstrap(database, methodology_id, [valuation_row(40.0, 32.0, 48.0, 72)], NIGHT)

    latest = _latest(database)[("NASDAQ", "AAPL")]
    assert latest["tp_source"] == SOURCE_BLEND and latest["changed_at"] == future + timedelta(microseconds=1)
    assert database.capture_served_valuation_changes() == 0


def test_the_api_states_the_tp_source_of_every_record(tmp_path, monkeypatch) -> None:
    database, methodology_id = _database(tmp_path)
    database._valuation_changes.append({
        "id": "legacy-1", "snapshot_id": "s-legacy", "market": "B3", "symbol": "PRNR3", "company_name": "Priner",
        "changed_at": datetime(2026, 10, 1, tzinfo=timezone.utc), "trigger_type": "market_data", "trigger_title": "legacy",
        "trigger_summary": "", "source_name": "Brapi + EODHD", "source_url": None, "currency": "BRL", "old_tp": 39.0, "new_tp": 40.0,
        "tp_change_percent": 2.56, "old_buy_in": 31.0, "new_buy_in": 32.0, "old_consensus_tp": 47.0, "new_consensus_tp": 48.0,
        "price": 18.4, "old_confidence": 72.0, "new_confidence": 72.0, "methodology_name": "C3PO Valuation Model", "methodology_version": 9,
        "metadata": {"changed_fields": ["c3po_tp"], "analysis_type": "valuation_universe"}})
    cycles = _bootstrap(database, methodology_id, [valuation_row(40.0, 32.0, 48.0, 72, internal_tp=36.0, internal_buy_in=29.0)], NIGHT)
    generation = _switch_to_internal(database, monkeypatch, cycles)
    monkeypatch.setattr(app_main, "database", database)

    response = app_main.valuation_records(limit=100, offset=0, q="PRNR3", market="B3", trigger_type=None)
    payload = ValuationChangeResponse.model_validate(response.model_dump(mode="json")).model_dump(mode="json")

    states = [(item["tp_source"], item["generation_id"], item["legacy"], item["tp_source_label"], item["new_tp"]) for item in payload["items"]]
    assert states[0] == (SOURCE_INTERNAL, generation["generation_id"], False, SOURCE_INTERNAL, 36.0)  # the served TP, stated
    assert states[-1] == (None, None, True, LEGACY_TP_SOURCE_PRODUCER, 40.0)  # the legacy blend row, stated as legacy
    assert [item["metadata"].get("capture") for item in payload["items"][:-1]] == [SERVED_CAPTURE] * (len(states) - 1)
    # the global search shows the latest record of the company: the served one, stated as such
    search = app_main.global_search(None, q="PRNR3")  # type: ignore[arg-type]  # the tests' settings require no auth: the request is unused
    found = search["valuations"][0]
    assert (found["symbol"], found["new_tp"], found["tp_source"], found["legacy"], found["tp_source_label"]) == (
        "PRNR3", 36.0, SOURCE_INTERNAL, False, SOURCE_INTERNAL)


# ------------------------------------------------------------------ the migration and the frontend


def test_migration_054_is_additive_and_idempotent() -> None:
    sql = (DB_DIR / "054_valuation_change_served_tp.sql").read_text(encoding="utf-8")
    statements = re.sub(r"--[^\n]*", "", sql).upper()
    assert not re.search(r"\b(UPDATE|DELETE|DROP|TRUNCATE|DEFAULT)\b", statements)  # nothing rewritten, no legacy row stamped
    assert "ADD COLUMN TP_SOURCE TEXT;" in statements  # nullable, no default: the legacy rows stay NULL
    assert "ADD COLUMN GENERATION_ID UUID REFERENCES VALUATION_OFFICIAL_SELECTION(GENERATION_ID);" in statements
    assert statements.count("ADD COLUMN") == 2 and statements.count("IF NOT EXISTS") == 3  # each column only when missing, index once
    assert "CREATE UNIQUE INDEX IF NOT EXISTS VALUATION_CHANGE_GENERATION_SYMBOL" in statements
    assert "WHERE GENERATION_ID IS NOT NULL" in statements
    numbers = [path.name.split("_", 1)[0] for path in DB_DIR.glob("*.sql") if path.name[:1].isdigit()]
    assert numbers.count("054") == 1


def test_the_ben_kenobi_tab_shows_the_source_of_every_record() -> None:
    page = (Path(__file__).resolve().parents[2] / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    record_type = page[page.index("interface ValuationChangeRecord {"):page.index("interface ValuationChangeResponse {")]
    for field in ("tp_source?: string | null;", "generation_id?: string | null;", "legacy?: boolean;", "tp_source_label?: string | null;"):
        assert field in record_type
    assert "function valuationRecordTpSource(" in page and "function IQTpSourceBadge(" in page
    assert 'label="C3PO TP"' in page and "note={<IQTpSourceBadge record={record} />}" in page
    assert "TP oficial servido" in page and "Registro legado · TP do produtor (blend com consenso)" in page
    assert "Registro legado · One Pager (fonte não registrada)" in page
    assert 'legacy_one_pager: ' in page or '"legacy_one_pager"' in page
    css = (Path(__file__).resolve().parents[2] / "frontend" / "app" / "globals.css").read_text(encoding="utf-8")
    assert ".iq-tp-source-served" in css and ".iq-tp-source-legacy" in css


@pytest.mark.parametrize("label", [LEGACY_TP_SOURCE_PRODUCER, LEGACY_TP_SOURCE_ONE_PAGER])
def test_legacy_labels_are_never_an_official_source(label: str) -> None:
    from app.valuation_official_engine import OFFICIAL_SOURCES

    assert label not in OFFICIAL_SOURCES and label.startswith("legacy_")
