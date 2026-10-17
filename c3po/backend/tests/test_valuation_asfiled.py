"""Valuation as-filed (owner 2026-10-17): the as-of bridge, the shadow reconciliation against EODHD, the US revaluation
trigger (migration 053) and its wiring — Investor Relations polling, the IR valuation processor, the nightly cut and
the US producer's shadow hook. Everything behind C3PO_VALUATION_ASFILED_ENABLED, default off. No network."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from app import valuation_asfiled as asfiled
from app import valuation_worker
from app.config import Settings
from app.database import Database
from app.investor_relations import InvestorRelationsService
from app.ir_valuation import InvestorRelationsValuationProcessor
from app.market_data.us_screener import USScreeningService
from app.sec_xbrl import SecRateLimiter, SecXbrlClient, SecXbrlIngestor
from app.statement_vintages import StatementVintageStore
from app.valuation_policy import METHODOLOGY_VERSION

from tests import asfiled_fixtures as fx

DB_DIR = Path(__file__).resolve().parents[2] / "db"
UTC = timezone.utc
TEN_K = "0000999001-26-000005"
EIGHT_K = fx.EIGHT_K_RESULTS["accession"]


class NoWaitLimiter(SecRateLimiter):
    def __init__(self) -> None:
        super().__init__(8.0, clock=lambda: 0.0, sleep=lambda seconds: None)

    def acquire(self) -> None:
        return None


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"database_url": "", "sec_contact": "contact-placeholder.invalid", "valuation_asfiled_enabled": True,
                              "auth_cookie_secure": False}
    values.update(overrides)
    return Settings(**values)


def _client(fake: fx.EdgarFake) -> SecXbrlClient:
    return SecXbrlClient(_settings(), http=httpx.Client(transport=fake.transport()), limiter=NoWaitLimiter())


def _ingested(*, include_restatement: bool = False, database: Database | None = None) -> Database:
    database = database or Database(_settings())
    ingestor = SecXbrlIngestor(database, _client(fx.EdgarFake()), backfill_per_poll=5)
    ingestor.poll({"SYNT": "NASDAQ"}, {"SYNT": fx.CIK}, now=datetime(2026, 2, 21, tzinfo=UTC))
    if include_restatement:
        ingestor.client = _client(fx.EdgarFake(include_restatement=True))
        ingestor.poll({"SYNT": "NASDAQ"}, {"SYNT": fx.CIK}, now=datetime(2026, 3, 11, tzinfo=UTC))
    return database


# -- the bridge --------------------------------------------------------------------------------------------------------

def test_as_of_fundamentals_sees_only_what_was_accepted_by_then() -> None:
    database = _ingested()
    accepted_10k = fx.true_instant("20260220163000")
    before = asfiled.as_of_fundamentals(database, fx.CIK, accepted_10k - timedelta(seconds=1))
    assert before["period_end"] == "2025-09-30"
    assert before["ttm"]["revenue"] == pytest.approx(100 + 98 + 92 + 97)  # Q4 2024 = FY 2024 − 9M 2024 = 360 − 263
    assert before["ttm"]["net_income"] == pytest.approx(14 + 13 + 12 + 13)
    assert before["ttm"]["eps_diluted"] == pytest.approx(0.14 + 0.13 + 0.12 + 0.13)
    assert before["ttm"]["d_and_a"] == pytest.approx(3 + 3 + 3 + 3)  # cash-flow facts are year-to-date only: every quarter derived
    assert before["ttm"]["operating_cash_flow"] == pytest.approx(24 + 23 + 22 + 23) and before["ttm"]["capex"] == pytest.approx(24)
    assert before["derived"]["ebitda"] == pytest.approx((19 + 18 + 17 + 18) + 12)
    assert before["derived"]["free_cash_flow"] == pytest.approx(92 - 24)
    assert before["balance"]["cash"] == 66 and before["balance_dates"]["cash"] == "2025-09-30"
    assert before["derived"]["total_debt"] == pytest.approx(184 + 10 + 5)  # long + current maturities + commercial paper
    assert before["balance"]["shares_outstanding"] == 950 and before["balance_dates"]["shares_outstanding"] == "2025-10-25"
    assert TEN_K not in before["documents"] and before["missing"] == []

    after = asfiled.as_of_fundamentals(database, fx.CIK, accepted_10k)  # accepted AT as_of counts
    assert after["period_end"] == "2025-12-31" and after["ttm"]["revenue"] == pytest.approx(400)
    assert after["quarters"]["revenue"][0] == {"period_start": "2025-10-01", "period_end": "2025-12-31", "value": 110.0, "derived": True}
    assert after["balance"]["shares_outstanding"] == 1000  # the FY 2025 cover reports two classes: summed
    assert after["derived"]["total_debt"] == pytest.approx(180 + 12 + 6) and after["balance"]["cash"] == 70
    assert TEN_K in after["documents"] and after["latest_accepted_at"] == accepted_10k.isoformat()
    q4 = [item for item in after["provenance"]["revenue"] if item["period_end"] == "2025-12-31"]
    assert q4 and q4[0]["doc_id"] == TEN_K and q4[0]["derived_quarter"] is True and q4[0]["first_publication"] is True

    nothing = asfiled.as_of_fundamentals(database, fx.CIK, datetime(2024, 1, 1, tzinfo=UTC))
    assert nothing["documents"] == [] and nothing["period_end"] is None and nothing["ttm"]["revenue"] is None
    assert set(nothing["missing"]) >= {"revenue", "cash", "total_debt"}


def test_a_restatement_supersedes_the_original_only_from_its_own_acceptance() -> None:
    database = _ingested(include_restatement=True)
    restated_at = fx.true_instant("20260310163000")
    old = asfiled.as_of_fundamentals(database, fx.CIK, restated_at - timedelta(seconds=1))
    new = asfiled.as_of_fundamentals(database, fx.CIK, restated_at)
    quarters = lambda report: {item["period_end"]: item["value"] for item in report["quarters"]["revenue"]}  # noqa: E731
    assert quarters(old)["2025-09-30"] == 100 and quarters(old)["2025-12-31"] == 110
    assert quarters(new)["2025-09-30"] == fx.RESTATED_Q3_REVENUE and quarters(new)["2025-12-31"] == 400 - (92 + 98 + fx.RESTATED_Q3_REVENUE)
    assert new["ttm"]["revenue"] == pytest.approx(400)  # the year still adds up
    assert "0000999001-26-000008" in new["documents"] and "0000999001-26-000008" not in old["documents"]


def test_balances_are_read_at_the_ttm_quarter_end_never_from_an_older_quarter() -> None:
    database = Database(_settings())
    accepted = datetime(2026, 2, 20, 21, 30, tzinfo=UTC)

    def row(concept: str, end: str, value: float, start: str | None = None, doc: str = "D-1") -> dict[str, Any]:
        return {"market": "US", "issuer_key": "0000999003", "source": "sec_xbrl_companyfacts", "doc_id": doc, "form": "10-K",
                "period_start": start, "period_end": end, "concept": concept, "unit": "USD", "value": value, "filed_date": "2026-02-20",
                "accepted_at": accepted}

    StatementVintageStore(database).insert_vintages("US", "0000999003", [
        row("us-gaap:Revenues", "2025-12-31", 400, "2025-01-01"), row("us-gaap:Revenues", "2025-09-30", 290, "2025-01-01"),
        row("us-gaap:LongTermDebtNoncurrent", "2025-12-31", 180), row("us-gaap:LongTermDebtNoncurrent", "2025-09-30", 184),
        row("us-gaap:CommercialPaper", "2025-09-30", 50),  # repaid by year end: absent at 12-31, never carried forward
        row("us-gaap:CashAndCashEquivalentsAtCarryingValue", "2025-09-30", 66),
    ])
    report = asfiled.as_of_fundamentals(database, "0000999003", accepted)
    assert report["period_end"] == "2025-12-31" and report["derived"]["total_debt"] == 180
    assert report["balance"]["short_term_borrowings"] is None and report["balance"]["cash"] is None and "cash" in report["missing"]


def _split_issuer(database: Database, issuer: str, *, q2_cover: int, q2_eps: tuple[float, float]) -> datetime:
    """Q3 2024 10-Q, FY 2024 10-K, Q1 2025 10-Q and a Q2 2025 10-Q whose cover count and EPS are ``q2_cover``/``q2_eps``
    (a 10:1 split before it: 1000 and (0.1, 0.2)); returns the Q2 10-Q's acceptance."""
    documents = {  # doc → (form, acceptance, cover date, cover share count)
        "Q3-24": ("10-Q", datetime(2024, 11, 5, 21, 30, tzinfo=UTC), "2024-10-25", 100),
        "FY-24": ("10-K", datetime(2025, 2, 20, 21, 30, tzinfo=UTC), "2025-02-10", 100),
        "Q1-25": ("10-Q", datetime(2025, 5, 5, 20, 30, tzinfo=UTC), "2025-04-25", 100),
        "Q2-25": ("10-Q", datetime(2025, 8, 5, 20, 30, tzinfo=UTC), "2025-07-25", q2_cover),
    }
    facts = [  # (doc, field, start, end, value)
        ("Q3-24", "revenue", "2024-07-01", "2024-09-30", 100), ("Q3-24", "revenue", "2024-01-01", "2024-09-30", 300),
        ("Q3-24", "eps", "2024-07-01", "2024-09-30", 1.0), ("Q3-24", "eps", "2024-01-01", "2024-09-30", 3.0),
        ("FY-24", "revenue", "2024-01-01", "2024-12-31", 400), ("FY-24", "eps", "2024-01-01", "2024-12-31", 4.0),
        ("Q1-25", "revenue", "2025-01-01", "2025-03-31", 100), ("Q1-25", "eps", "2025-01-01", "2025-03-31", 1.0),
        ("Q2-25", "revenue", "2025-04-01", "2025-06-30", 100), ("Q2-25", "revenue", "2025-01-01", "2025-06-30", 200),
        ("Q2-25", "eps", "2025-04-01", "2025-06-30", q2_eps[0]), ("Q2-25", "eps", "2025-01-01", "2025-06-30", q2_eps[1]),
    ]
    concepts = {"revenue": ("us-gaap:Revenues", "USD"), "eps": ("us-gaap:EarningsPerShareDiluted", "USD/shares")}

    def row(doc: str, concept: str, unit: str, start: str | None, end: str, value: float) -> dict[str, Any]:
        form, accepted, _, _ = documents[doc]
        return {"market": "US", "issuer_key": issuer, "source": "sec_xbrl_companyfacts", "doc_id": doc, "form": form, "period_start": start,
                "period_end": end, "concept": concept, "unit": unit, "value": value, "filed_date": accepted.date(), "accepted_at": accepted}

    rows = [row(doc, *concepts[name], start, end, value) for doc, name, start, end, value in facts]
    rows += [row(doc, "dei:EntityCommonStockSharesOutstanding", "shares", None, cover, count) for doc, (_, _, cover, count) in documents.items()]
    StatementVintageStore(database).insert_vintages("US", issuer, rows)
    return documents["Q2-25"][1]


def test_ttm_eps_is_never_summed_across_a_share_split() -> None:
    # review finding: after a 10:1 split the pre-split Q1 10-Q EPS (1.0) won over the post-split 6M − 3M (0.1), and the
    # prior year's quarters are pre-split too: 0.1 + 1.0 + 1.0 + 1.0 = 3.1 against a split-adjusted 0.4
    database = Database(_settings())
    accepted = _split_issuer(database, "0000999004", q2_cover=1000, q2_eps=(0.1, 0.2))
    report = asfiled.as_of_fundamentals(database, "0000999004", accepted)
    assert report["period_end"] == "2025-06-30" and report["ttm"]["revenue"] == pytest.approx(400)
    assert report["ttm"]["eps_diluted"] is None and "eps_diluted" in report["missing"]
    assert report["warnings"] == [asfiled.EPS_SHARE_BASIS_CHANGED]
    steady = Database(_settings())  # the same issuer without a split (a 2 % buyback): summed as before
    accepted = _split_issuer(steady, "0000999004", q2_cover=98, q2_eps=(1.0, 2.0))
    report = asfiled.as_of_fundamentals(steady, "0000999004", accepted)
    assert report["ttm"]["eps_diluted"] == pytest.approx(4.0) and report["warnings"] == []
    assert sum(item["derived_quarter"] for item in report["provenance"]["eps_diluted"]) == 2  # Q4 2024 = FY − 9M, two facts


def test_a_ttm_that_is_a_fiscal_year_takes_the_years_reported_eps() -> None:
    database = _ingested()
    report = asfiled.as_of_fundamentals(database, fx.CIK, fx.true_instant("20260220163000"))
    assert report["ttm"]["eps_diluted"] == pytest.approx(0.55)
    [fact] = report["provenance"]["eps_diluted"]
    assert (fact["period_start"], fact["period_end"], fact["doc_id"], fact["derived_quarter"]) == ("2025-01-01", "2025-12-31", TEN_K, False)


def test_total_debt_adds_long_and_short_without_double_counting() -> None:
    assert asfiled.total_debt({"long_term_debt": 100.0, "debt_current": 20.0, "long_term_debt_current": 5.0, "short_term_borrowings": 3.0}) == 120.0
    assert asfiled.total_debt({"long_term_debt": 100.0, "long_term_debt_current": 5.0, "short_term_borrowings": 3.0}) == 108.0
    assert asfiled.total_debt({"long_term_debt_including_current": 105.0, "long_term_debt_current": 5.0, "short_term_borrowings": 3.0}) == 108.0
    assert asfiled.total_debt({"short_term_borrowings": 3.0}) == 3.0
    assert asfiled.total_debt({}) is None


# -- the shadow reconciliation -----------------------------------------------------------------------------------------

def _eodhd(**overrides: Any) -> dict[str, Any]:
    fundamentals = {
        "financialsAsOf": "2025-12-31", "totalRevenue": 401.0, "trailingEps": 0.55, "ebitda": 88.0, "totalCash": 70.0,
        "totalDebt": 250.0, "totalEquity": 360.0, "sharesOutstanding": None,
        "quarterlyIncome": [{"date": "2025-12-31", "netIncome": 16, "operatingIncome": 21}, {"date": "2025-09-30", "netIncome": 14, "operatingIncome": 19},
                            {"date": "2025-06-30", "netIncome": 13, "operatingIncome": 18}, {"date": "2025-03-31", "netIncome": 12, "operatingIncome": 17}],
        "quarterlyCashFlow": [{"date": "2025-12-31", "depreciation": 4, "totalCashFromOperatingActivities": 26, "capitalExpenditures": -7},
                              {"date": "2025-09-30", "depreciation": 3, "totalCashFromOperatingActivities": 24, "capitalExpenditures": -6},
                              {"date": "2025-06-30", "depreciation": 3, "totalCashFromOperatingActivities": 23, "capitalExpenditures": -6},
                              {"date": "2025-03-31", "depreciation": 3, "totalCashFromOperatingActivities": 22, "capitalExpenditures": -6}],
    }
    fundamentals.update(overrides)
    return fundamentals


def test_the_reconciliation_compares_every_field_like_for_like() -> None:
    database = _ingested()
    report = asfiled.reconcile_with_eodhd(asfiled.as_of_fundamentals(database, fx.CIK, datetime(2026, 3, 1, tzinfo=UTC)), _eodhd())
    statuses = {name: item["status"] for name, item in report["fields"].items()}
    assert statuses == {
        "revenue_ttm": "agree", "net_income_ttm": "agree", "eps_diluted_ttm": "agree", "operating_income_ttm": "agree", "d_and_a_ttm": "agree",
        "ebitda_ttm": "agree", "operating_cash_flow_ttm": "agree", "capex_ttm": "agree", "cash": "agree", "total_debt": "disagree",
        "stockholders_equity": "agree", "shares_outstanding": "missing_eodhd",
    }
    assert report["fields"]["revenue_ttm"]["relative_difference"] == pytest.approx(1 / 401)
    assert report["period_aligned"] is True and report["asfiled_period_end"] == "2025-12-31"
    lagging = asfiled.reconcile_with_eodhd(asfiled.as_of_fundamentals(database, fx.CIK, datetime(2026, 3, 1, tzinfo=UTC)),
                                           _eodhd(financialsAsOf="2025-09-30", quarterlyIncome=[]))
    assert lagging["period_aligned"] is False and lagging["fields"]["net_income_ttm"]["status"] == "missing_eodhd"


def test_the_reconciliation_is_its_own_snapshot_and_never_touches_the_universe() -> None:
    database = _ingested()
    snapshot_id = asfiled.record_us_reconciliation(database, "NASDAQ", {"SYNT": _eodhd(), "MISS": _eodhd()}, as_of=datetime(2026, 3, 1, tzinfo=UTC))
    assert snapshot_id is not None
    saved = database.latest_analysis_snapshot(asfiled.RECONCILIATION_ANALYSIS, "NASDAQ_ASFILED_RECONCILIATION")
    assert saved is not None and saved["id"] == snapshot_id
    outputs = saved["outputs"]
    assert outputs["compared_symbols"] == 1 and outputs["unmapped"] == ["MISS"] and set(outputs["symbols"]) == {"SYNT"}
    assert outputs["fields"]["revenue_ttm"] == {"compared": 1, "agree": 1, "disagree": 0, "missing_asfiled": 0, "missing_eodhd": 0, "agreement_percent": 100.0}
    assert outputs["fields"]["total_debt"]["agreement_percent"] == 0.0
    assert database.latest_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE") is None
    assert asfiled.record_us_reconciliation(Database(_settings()), "NASDAQ", {"SYNT": _eodhd()}, as_of=datetime(2026, 3, 1, tzinfo=UTC)) is None


def test_the_us_producer_hook_is_shadow_only_and_never_fails_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any], datetime]] = []

    def record(database: Database, market: str, fundamentals: dict[str, Any], *, as_of: datetime) -> str:
        calls.append((market, fundamentals, as_of))
        raise RuntimeError("store unavailable")

    monkeypatch.setattr("app.market_data.us_screener.record_us_reconciliation", record)
    settings = _settings(eodhd_api_token="test")
    screener = USScreeningService(settings, Database(settings), SimpleNamespace(http=object()), SimpleNamespace())  # type: ignore[arg-type]
    fetched_at = datetime(2026, 3, 1, 21, tzinfo=UTC)
    screener._record_asfiled_reconciliation("NASDAQ", {"SYNT": {"totalRevenue": 1.0}, "EMPTY": {}}, ["SYNT", "EMPTY", "GONE"], fetched_at)
    assert calls == [("NASDAQ", {"SYNT": {"totalRevenue": 1.0}}, fetched_at)]  # the exception was logged, not raised
    source = (Path(__file__).resolve().parents[1] / "app" / "market_data" / "us_screener.py").read_text(encoding="utf-8")
    assert "if self.settings.valuation_asfiled_enabled:\n            self._record_asfiled_reconciliation(" in source


# -- the US revaluation trigger ----------------------------------------------------------------------------------------

def _universe_row(symbol: str, *, fundamentals_as_of: str, tp: float = 150.0) -> dict[str, Any]:
    return {"symbol": symbol, "security_type": "Stock", "our_tp": tp, "buy_in": tp * 0.8, "price": tp * 0.9, "internal_tp": tp * 0.98,
            "fundamentals_as_of": fundamentals_as_of}


def _publish(database: Database, market: str, rows: list[dict[str, Any]], at: datetime) -> str:
    return database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1", {"methodology_version": METHODOLOGY_VERSION},
                                           {"rows": rows, "universe_size": len(rows)}, at)


def _official(database: Database, at: datetime, *, synt_fundamentals: str) -> None:
    _publish(database, "B3", [{"symbol": "PETR4", "our_tp": 40.0, "buy_in": 32.0, "price": 36.0, "internal_tp": 39.0}], at)
    _publish(database, "NYSE", [_universe_row("KO", fundamentals_as_of="2025-12-31", tp=70.0)], at)
    _publish(database, "NASDAQ", [_universe_row("SYNT", fundamentals_as_of=synt_fundamentals),
                                  {**_universe_row("QQQ", fundamentals_as_of="2025-12-31"), "security_type": "ETF"}], at)


def test_an_accepted_filing_marks_the_us_tp_stale_and_the_covering_cut_clears_it() -> None:
    database = _ingested()
    _official(database, datetime(2026, 2, 20, 5, 0, tzinfo=UTC), synt_fundamentals="2025-09-30")
    assert asfiled.us_valuation_universe(database) == {"SYNT": "NASDAQ", "KO": "NYSE"}  # ETFs file no 10-Q
    now = datetime(2026, 2, 21, 0, 0, tzinfo=UTC)
    counts = asfiled.evaluate_us_filings(database, now=now)
    assert counts == {"filings": 2, "evaluated": 2, "stale": 2, "cleared": 0, "untracked": 0}
    marks = {(row["doc_id"], row["state"]): row for row in asfiled.TpStalenessStore(database).rows()}
    stale = marks[(TEN_K, "stale")]
    assert stale["reason"] == "tp_predates_acceptance" and stale["market"] == "NASDAQ" and stale["accepted_at"] == fx.true_instant("20260220163000")
    assert stale["queued_for_cut_at"] == datetime(2026, 2, 21, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))  # tonight's cut, 03:00Z
    assert stale["period_of_report"] == date(2025, 12, 31) and stale["expected_period_end"] == date(2025, 12, 31) and stale["covers_period"] is False
    # review finding: the 2026-02-20 cut is AFTER the 8-K 2.02 but its fundamentals (Q3) predate the quarter the 8-K
    # announces (Q4 2025): the pre-earnings TP is stale, never 'cleared'
    release = marks[(EIGHT_K, "stale")]
    assert release["reason"] == "fundamentals_predate_period" and release["expected_period_end"] == date(2025, 12, 31)
    assert release["covers_period"] is False and release["period_of_report"] == date(2026, 2, 12)  # the 8-K's own event date
    assert [row["doc_id"] for row in asfiled.stale_us_tps(database)["SYNT"]] == [EIGHT_K, TEN_K]
    assert asfiled.evaluate_us_filings(database, now=now)["stale"] == 0  # idempotent

    _publish(database, "NASDAQ", [_universe_row("SYNT", fundamentals_as_of="2025-09-30")], datetime(2026, 2, 21, 3, 10, tzinfo=UTC))
    lagging = asfiled.evaluate_us_filings(database, now=datetime(2026, 2, 21, 3, 20, tzinfo=UTC))
    assert lagging["cleared"] == 0 and len(asfiled.stale_us_tps(database)["SYNT"]) == 2  # the cut ran, its fundamentals predate Q4

    _publish(database, "NASDAQ", [_universe_row("SYNT", fundamentals_as_of="2025-12-31")], datetime(2026, 2, 22, 3, 10, tzinfo=UTC))
    revalued = asfiled.evaluate_us_filings(database, now=datetime(2026, 3, 9, tzinfo=UTC))  # older than the lookback: still re-checked
    assert revalued["cleared"] == 2 and asfiled.stale_us_tps(database) == {}
    cleared = {row["doc_id"]: row for row in asfiled.TpStalenessStore(database).rows() if row["state"] == "cleared"}
    assert cleared[TEN_K]["reason"] == "revalued_by_cut" and cleared[TEN_K]["covers_period"] is True
    assert cleared[TEN_K]["fundamentals_as_of"] == date(2025, 12, 31) and cleared[EIGHT_K]["reason"] == "revalued_by_cut"


def test_an_earnings_release_is_cleared_only_by_a_tp_whose_fundamentals_reach_the_announced_quarter() -> None:
    database = Database(_settings())
    store = StatementVintageStore(database)
    issuer = "0000999005"

    def filing(doc_id: str, form: str, accepted: datetime, period: str, items: str = "") -> dict[str, Any]:
        return {"market": "US", "issuer_key": issuer, "source": "sec_edgar", "doc_id": doc_id, "form": form, "items": items, "symbols": ["SYNT"],
                "period_of_report": period, "filed_date": accepted.date(), "accepted_at": accepted, "accepted_source": "sec_header"}

    # the issuer's statements so far (Q3 2025 10-Q) and, inside the lookback, its Q4 earnings release: no 10-K yet
    store.register_filings([filing("0000999005-25-000030", "10-Q", datetime(2025, 11, 5, 21, 30, tzinfo=UTC), "2025-09-30"),
                            filing("0000999005-26-000003", "8-K", datetime(2026, 2, 12, 21, 5, tzinfo=UTC), "2026-02-12", "2.02,9.01")])
    _official(database, datetime(2026, 2, 13, 3, 10, tzinfo=UTC), synt_fundamentals="2025-09-30")
    after_release =asfiled.evaluate_us_filings(database, now=datetime(2026, 2, 13, 4, tzinfo=UTC))
    assert after_release["stale"] == 1 and after_release["cleared"] == 0  # the cut after the release still has Q3 fundamentals
    _publish(database, "NASDAQ", [_universe_row("SYNT", fundamentals_as_of="2025-09-30")], datetime(2026, 2, 20, 3, 10, tzinfo=UTC))
    assert asfiled.evaluate_us_filings(database, now=datetime(2026, 2, 20, 4, tzinfo=UTC))["cleared"] == 0
    assert list(asfiled.stale_us_tps(database)) == ["SYNT"]  # the whole window until the provider carries Q4
    _publish(database, "NASDAQ", [_universe_row("SYNT", fundamentals_as_of="2025-12-31")], datetime(2026, 2, 21, 3, 10, tzinfo=UTC))
    assert asfiled.evaluate_us_filings(database, now=datetime(2026, 2, 21, 4, tzinfo=UTC))["cleared"] == 1
    assert asfiled.stale_us_tps(database) == {}


def test_the_announced_quarter_is_stepped_from_the_issuers_own_fiscal_calendar() -> None:
    at = lambda value: datetime.fromisoformat(value)  # noqa: E731
    # a calendar year: the Q4 release in February
    assert asfiled.announced_quarter_end(at("2026-02-12T21:05:00+00:00"), [date(2025, 9, 30)]) == date(2025, 12, 31)
    # the matching 10-K already registered (accepted after the release) gives the same quarter
    assert asfiled.announced_quarter_end(at("2026-02-12T21:05:00+00:00"), [date(2025, 9, 30), date(2025, 12, 31)]) == date(2025, 12, 31)
    # a 52/53-week year (quarters of thirteen weeks): 2025-09-27 → 2025-12-27
    assert asfiled.announced_quarter_end(at("2026-01-29T21:30:00+00:00"), [date(2025, 9, 27)]) == date(2025, 12, 27)
    # an off-calendar year closing in January, stepped twice from an older statement
    assert asfiled.announced_quarter_end(at("2026-02-19T12:00:00+00:00"), [date(2025, 7, 31)]) == date(2026, 1, 31)
    # the acceptance day is New York's: 2026-01-01 02:00Z is still 2025-12-31 there, so Q4 has not ended yet
    assert asfiled.announced_quarter_end(at("2026-01-01T02:00:00+00:00"), [date(2025, 9, 30)]) == date(2025, 9, 30)
    # no statement of the issuer registered yet: the latest calendar quarter end before the release
    assert asfiled.announced_quarter_end(at("2026-02-12T21:05:00+00:00"), []) == date(2025, 12, 31)
    assert asfiled.next_quarter_end(date(2025, 11, 30)) == date(2026, 2, 28) and asfiled.next_quarter_end(date(2026, 3, 28)) == date(2026, 6, 27)


def test_a_symbol_without_an_official_tp_is_untracked_once_and_marked_when_its_tp_arrives() -> None:
    database = _ingested()
    store = StatementVintageStore(database)
    store.register_filings([{"market": "US", "issuer_key": "0000999009", "source": "sec_edgar", "doc_id": "0000999009-26-000001", "form": "8-K",
                             "items": "2.02", "symbols": ["ZZZZ"], "filed_date": "2026-02-19", "accepted_at": datetime(2026, 2, 19, 21, tzinfo=UTC),
                             "accepted_source": "sec_header"}])
    _official(database, datetime(2026, 2, 20, 5, 0, tzinfo=UTC), synt_fundamentals="2025-12-31")
    now = datetime(2026, 2, 21, tzinfo=UTC)
    assert asfiled.evaluate_us_filings(database, now=now)["untracked"] == 1
    assert asfiled.evaluate_us_filings(database, now=now)["untracked"] == 0
    assert asfiled.evaluate_us_filings(Database(_settings()), now=now) == {"filings": 0, "evaluated": 0, "stale": 0, "cleared": 0, "untracked": 0}
    # review finding: 'untracked' is not terminal — the symbol enters the generation with a TP whose fundamentals predate
    # the quarter the release announces (no statement registered for the issuer: the calendar quarter, 2025-12-31)
    _publish(database, "NASDAQ", [_universe_row("SYNT", fundamentals_as_of="2025-12-31"), _universe_row("ZZZZ", fundamentals_as_of="2025-09-30")],
             datetime(2026, 2, 21, 3, 10, tzinfo=UTC))
    arrived = asfiled.evaluate_us_filings(database, now=datetime(2026, 2, 21, 4, tzinfo=UTC))
    assert arrived["stale"] == 1 and arrived["untracked"] == 0
    zzzz = asfiled.stale_us_tps(database)["ZZZZ"][0]
    assert zzzz["reason"] == "fundamentals_predate_period" and zzzz["expected_period_end"] == date(2025, 12, 31)
    # outside the lookback an untracked pair is history: never evaluated again
    other = "0000999009-26-000002"
    store.register_filings([{"market": "US", "issuer_key": "0000999009", "source": "sec_edgar", "doc_id": other, "form": "8-K", "items": "2.02",
                             "symbols": ["WWWW"], "filed_date": "2026-02-19", "accepted_at": datetime(2026, 2, 19, 22, tzinfo=UTC),
                             "accepted_source": "sec_header"}])
    assert asfiled.evaluate_us_filings(database, now=datetime(2026, 2, 21, 5, tzinfo=UTC))["untracked"] == 1
    _publish(database, "NASDAQ", [_universe_row("WWWW", fundamentals_as_of="2025-09-30")], datetime(2026, 3, 5, 3, 10, tzinfo=UTC))
    late = asfiled.evaluate_us_filings(database, now=datetime(2026, 3, 5, 4, tzinfo=UTC))
    assert late["stale"] == 0 and "WWWW" not in asfiled.stale_us_tps(database)


def test_the_ir_processor_runs_the_trigger_only_behind_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _ingested()
    _official(database, datetime(2026, 2, 20, 5, 0, tzinfo=UTC), synt_fundamentals="2025-09-30")
    off = InvestorRelationsValuationProcessor(database, SimpleNamespace())  # type: ignore[arg-type]
    assert off.process() == {"claimed": 0, "updated": [], "targeted_only": [], "failed": []}
    assert asfiled.TpStalenessStore(database).rows() == []
    monkeypatch.setattr("app.ir_valuation.datetime", _FrozenDatetime)
    on = InvestorRelationsValuationProcessor(database, SimpleNamespace(), asfiled_enabled=True)  # type: ignore[arg-type]
    result = on.process()
    assert result["claimed"] == 0 and result["us_revaluation"]["stale"] == 2  # the 10-K and the 8-K 2.02 (Q3 fundamentals)

    def broken(database: Database, *, now: datetime) -> dict[str, int]:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.ir_valuation.evaluate_us_filings", broken)
    assert on.process()["us_revaluation"] == {"error": "RuntimeError"}  # never blocks the B3 propagation


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> "_FrozenDatetime":  # type: ignore[override]
        frozen = cls(2026, 2, 21, 0, 0, tzinfo=UTC)
        return frozen.astimezone(tz) if tz else frozen


def test_the_nightly_cut_records_its_revaluation_only_behind_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(valuation_worker, "evaluate_us_filings", lambda database: calls.append(database) or {"cleared": 1})
    investor_relations = SimpleNamespace(sync=lambda source: SimpleNamespace(sources={source: "ok"}))
    screener = SimpleNamespace(screen=lambda refresh: SimpleNamespace(generated_at=datetime(2026, 2, 21, 3, tzinfo=UTC), universe_size=1, eligible_count=1, items=[]))
    us_screener = SimpleNamespace(refresh_all=lambda: {"NASDAQ": 1, "NYSE": 1})
    database = Database(_settings())
    valuation_worker.run_nightly(database, investor_relations, screener, us_screener)  # type: ignore[arg-type]
    assert calls == []
    valuation_worker.run_nightly(database, investor_relations, screener, us_screener, asfiled_enabled=True)  # type: ignore[arg-type]
    assert calls == [database]

    def broken(database: Database) -> dict[str, int]:
        raise RuntimeError("boom")

    monkeypatch.setattr(valuation_worker, "evaluate_us_filings", broken)
    valuation_worker.run_nightly(database, investor_relations, screener, us_screener, asfiled_enabled=True)  # type: ignore[arg-type]


def test_migration_053_is_append_only_and_marks_each_state_once() -> None:
    sql = (DB_DIR / "053_valuation_tp_staleness.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS valuation_tp_staleness" in sql
    assert "CONSTRAINT valuation_tp_staleness_once UNIQUE (doc_id, symbol, state)" in sql
    assert "state TEXT NOT NULL CHECK (state IN ('stale', 'cleared', 'untracked'))" in sql
    assert "BEFORE UPDATE OR DELETE ON valuation_tp_staleness" in sql and "BEFORE TRUNCATE ON valuation_tp_staleness" in sql
    assert "DROP TABLE" not in sql and "ALTER TABLE" not in sql and "DELETE FROM" not in sql
    assert max(len(line) for line in sql.splitlines()) <= 127
    for key in asfiled._STALENESS_KEYS:
        assert f"    {key} " in sql, key  # the writer's columns are the migration's


# -- the Investor Relations SEC polling --------------------------------------------------------------------------------

def _ir(**overrides: Any) -> tuple[InvestorRelationsService, Database]:
    settings = _settings(**overrides)
    database = Database(settings)
    return InvestorRelationsService(settings, database), database


def test_sec_events_carry_the_corrected_json_clock_and_the_header_clock_when_registered() -> None:
    ir, database = _ir()
    payload = fx.submissions()
    recent = payload["filings"]["recent"]
    index = recent["accessionNumber"].index(TEN_K)
    event = ir._sec_event(payload, recent, index, None, datetime(2025, 1, 1, tzinfo=UTC))
    assert event is not None and event["published_at"] == fx.true_instant("20260220163000")
    assert event["raw_metadata"]["acceptance_source"] == "sec_json_corrected"
    assert event["raw_metadata"]["acceptance_json_raw"] == fx.submissions_json_clock("20260220163000")
    header_clock = fx.true_instant("20260220163000") + timedelta(seconds=7)
    StatementVintageStore(database).register_filings([{
        "market": "US", "issuer_key": fx.CIK, "source": "sec_edgar", "doc_id": TEN_K, "form": "10-K", "filed_date": "2026-02-20",
        "accepted_at": header_clock, "accepted_source": "sec_header"}])
    insider = {"source_code": "sec", "external_id": "finnhub-insider-SYNT", "form": "Form 4", "published_at": datetime(2026, 2, 1, tzinfo=UTC),
               "raw_metadata": {"source": "finnhub"}}
    ir._apply_header_acceptances([event, insider])
    assert event["published_at"] == header_clock and event["raw_metadata"]["acceptance_source"] == "sec_header"
    assert insider["published_at"] == datetime(2026, 2, 1, tzinfo=UTC) and "acceptance_source" not in insider["raw_metadata"]


def test_every_sec_request_of_the_ir_client_waits_on_the_process_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    acquired: list[str] = []
    monkeypatch.setattr("app.investor_relations.process_rate_limiter", lambda rate: SimpleNamespace(acquire=lambda: acquired.append(str(rate))))
    ir, _ = _ir(sec_max_requests_per_second=3.0)
    ir._sec_fair_access(httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000999001.json"))
    ir._sec_fair_access(httpx.Request("GET", "https://efts.sec.gov/LATEST/search-index"))
    ir._sec_fair_access(httpx.Request("GET", "https://finnhub.io/api/v1/news"))
    assert acquired == ["3.0", "3.0"]


def test_the_asfiled_poll_is_off_by_default_and_refuses_without_the_sec_contact() -> None:
    ir, database = _ir(valuation_asfiled_enabled=False)
    assert ir.sync("sec_asfiled").sources == {"sec_asfiled": "ok · 0 records"}
    assert not any(run.get("source_code") == "sec_asfiled" for run in database._ingestion_runs.values())
    refused, database = _ir(sec_contact="")
    state = refused.sync("sec_asfiled").sources["sec_asfiled"]
    assert state.startswith("error · C3PO_SEC_CONTACT is not configured")
    runs = [run for run in database._ingestion_runs.values() if run.get("source_code") == "sec_asfiled"]
    assert len(runs) == 1 and runs[0]["status"] == "failed"


def test_the_asfiled_poll_extends_the_sec_polling_to_the_valuation_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = fx.EdgarFake()
    monkeypatch.setattr("app.investor_relations.SecXbrlClient", lambda settings: _client(fake))
    monkeypatch.setattr("app.investor_relations.datetime", _FrozenDatetime)
    ir, database = _ir()
    _publish(database, "NASDAQ", [_universe_row("SYNT", fundamentals_as_of="2025-09-30")], datetime(2026, 2, 20, 5, tzinfo=UTC))
    selected: list[str] = []
    original = ir.sync_sec_asfiled
    monkeypatch.setattr(ir, "sync_cvm", lambda: selected.append("cvm") or (0, 0))
    monkeypatch.setattr(ir, "sync_sec", lambda: selected.append("sec") or (0, 0))
    monkeypatch.setattr(ir, "sync_ri", lambda: selected.append("ri") or (0, 0))
    monkeypatch.setattr(ir, "sync_finnhub_news", lambda: selected.append("finnhub") or (0, 0))
    monkeypatch.setattr(ir, "sync_sec_asfiled", lambda: selected.append("sec_asfiled") or (0, 0))
    ir.sync("all")
    assert selected == ["cvm", "sec", "ri", "finnhub"]  # the heavy pass is the IR worker's own source, never part of "all"
    read, written = original()
    assert read == 1 and written > 7
    assert {row["doc_id"] for row in StatementVintageStore(database).filings("US")} >= {TEN_K, EIGHT_K}
    runs = [run for run in database._ingestion_runs.values() if run.get("source_code") == "sec_asfiled"]
    assert runs[-1]["status"] == "succeeded"
    assert ir._asfiled_ingestor is not None and original()[1] == 0  # the second poll reuses the ingestor and writes nothing new
