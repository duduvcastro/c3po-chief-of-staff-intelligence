from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.config import Settings
from app.database import Database


def valuation_row(tp: float, buy_in: float, consensus: float, confidence: float) -> dict:
    return {
        "symbol": "PRNR3",
        "name": "Priner Servicos Industriais",
        "currency": "BRL",
        "price": 18.40,
        "our_tp": tp,
        "buy_in": buy_in,
        "public_consensus_tp": consensus,
        "valuation_confidence": confidence,
        "analyst_count": 4,
    }


def test_valuation_records_capture_only_real_changes_and_sort_newest_first(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    methodology_id = database.ensure_methodology_version("c3po_equity_valuation", 9, {}, "test")
    first_at = datetime(2026, 8, 13, 23, 0, tzinfo=timezone.utc)
    second_at = first_at + timedelta(days=1)
    inputs = {
        "market": "B3",
        "source": "Brapi + EODHD",
        "methodology_name": "C3PO Valuation Model",
        "methodology_version": 9,
    }

    database.save_analysis_snapshot(
        "valuation_universe",
        "B3_UNIVERSE",
        methodology_id,
        inputs,
        {"rows": [valuation_row(28.0, 17.0, 26.0, 82)]},
        first_at,
    )
    database.save_analysis_snapshot(
        "valuation_universe",
        "B3_UNIVERSE",
        methodology_id,
        inputs,
        {"rows": [valuation_row(28.0, 17.0, 26.0, 82)]},
        first_at + timedelta(hours=1),
    )
    database.save_analysis_snapshot(
        "valuation_universe",
        "B3_UNIVERSE",
        methodology_id,
        inputs,
        {"rows": [valuation_row(31.5, 18.2, 29.0, 87)]},
        second_at,
    )

    total, records = database.list_valuation_changes(limit=10)

    assert total == 2
    assert records[0]["changed_at"] == second_at
    assert records[0]["old_tp"] == 28.0
    assert records[0]["new_tp"] == 31.5
    assert records[0]["old_buy_in"] == 17.0
    assert records[0]["new_buy_in"] == 18.2
    assert records[0]["trigger_type"] == "market_data"
    assert records[1]["trigger_type"] == "initial"


def test_valuation_records_carry_logo_url_from_the_latest_universe_snapshot(tmp_path) -> None:
    """Ben Kenobi Records bug (2026-08-19): B3 rows showed no company logo at
    all. valuation_change_records never stored its own logo_url (and never
    should need to -- no new column/migration), but the B3/US screeners
    already capture one per company in their own universe snapshot rows.
    list_valuation_changes() cross-references those (already computed, no
    extra API calls) instead of relying on the frontend's broken
    /api/v1/company-logo/{symbol} proxy or a market-agnostic external CDN
    guess that only ever worked for US tickers.
    """
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    methodology_id = database.ensure_methodology_version("c3po_equity_valuation", 9, {}, "test")
    row = valuation_row(28.0, 17.0, 26.0, 82) | {"logo_url": "https://cdn.example.com/prnr3.png"}
    database.save_analysis_snapshot(
        "valuation_universe", "B3_UNIVERSE", methodology_id,
        {"market": "B3", "methodology_version": 9},
        {"rows": [row]},
        datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc),
    )

    _, records = database.list_valuation_changes(limit=10)

    assert records[0]["logo_url"] == "https://cdn.example.com/prnr3.png"


def test_valuation_records_filter_by_company_market_and_trigger(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    methodology_id = database.ensure_methodology_version("c3po_equity_valuation", 9, {}, "test")
    database.save_analysis_snapshot(
        "one_pager_valuation",
        "US:AMZN",
        methodology_id,
        {
            "market": "US",
            "source": "SEC + issuer RI",
            "source_url": "https://www.sec.gov/",
            "trigger_title": "Amazon One Pager recalculado",
            "methodology_name": "C3PO Valuation Model",
            "methodology_version": 9,
        },
        {
            "row": {
                "symbol": "AMZN",
                "company_name": "Amazon.com, Inc.",
                "currency": "USD",
                "price": 210.0,
                "c3po_tp": 285.0,
                "consensus_tp": 270.0,
                "buy_in": 198.0,
                "confidence": 86,
            }
        },
        datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc),
    )

    total, records = database.list_valuation_changes(symbol="amazon", market="US", trigger_type="initial")

    assert total == 1
    assert records[0]["symbol"] == "AMZN"
    assert records[0]["company_name"] == "Amazon.com, Inc."


def test_valuation_records_do_not_use_symbol_as_same_time_tiebreaker(tmp_path, monkeypatch) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    methodology_id = database.ensure_methodology_version("c3po_equity_valuation", 9, {}, "test")
    ids = iter(UUID(int=value) for value in range(1, 5))
    monkeypatch.setattr("app.database.uuid4", lambda: next(ids))
    row_a = valuation_row(22.0, 16.0, 21.0, 80) | {"symbol": "AAAA3", "name": "Alpha"}
    row_z = valuation_row(24.0, 17.0, 23.0, 82) | {"symbol": "ZZZZ3", "name": "Zeta"}

    database.save_analysis_snapshot(
        "valuation_universe",
        "B3_UNIVERSE",
        methodology_id,
        {"market": "B3", "methodology_version": 9},
        {"rows": [row_a, row_z]},
        datetime(2026, 8, 14, 20, 0, tzinfo=timezone.utc),
    )

    _, records = database.list_valuation_changes(limit=10)

    assert [item["symbol"] for item in records] == ["ZZZZ3", "AAAA3"]


def test_initial_record_does_not_inherit_an_old_ir_event(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
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
    methodology_id = database.ensure_methodology_version("c3po_equity_valuation", 9, {}, "test")
    database.save_analysis_snapshot(
        "valuation_universe",
        "B3_UNIVERSE",
        methodology_id,
        {"market": "B3", "source": "Brapi + EODHD", "methodology_version": 9},
        {"rows": [valuation_row(28.0, 17.0, 26.0, 82)]},
        event_at + timedelta(days=1),
    )

    _, records = database.list_valuation_changes(limit=10)

    assert records[0]["trigger_type"] == "initial"
    assert records[0]["source_name"] == "Brapi + EODHD"
    assert "Old CVM filing" not in records[0]["trigger_summary"]
