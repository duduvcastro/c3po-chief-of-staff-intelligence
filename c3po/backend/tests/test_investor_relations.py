import io
import zipfile
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.config import Settings
from app.cvm_fundamentals import extract_itr_official_fundamentals
from app.database import Database
from app.investor_relations import (
    RI_URL_OVERRIDES,
    SEC_FULLTEXT_KEYWORDS,
    LinkCollector,
    InvestorRelationsService,
    is_ri_navigation_link,
    normalize_company_name,
)
from app.market_data.b3_screener import B3ScreenerService


def service(tmp_path):
    settings = Settings(
        database_url="",
        migrations_dir=tmp_path,
        investor_relations_output_dir=tmp_path / "ir-pdf",
    )
    database = Database(settings)
    return InvestorRelationsService(settings, database), database


def test_company_normalization_and_cvm_classification(tmp_path):
    ir, _ = service(tmp_path)
    assert normalize_company_name("Petróleo Brasileiro S.A. - Petrobras") == "PETROLEO BRASILEIRO PETROBRAS"
    assert ir._classify_cvm("Fato Relevante", "",) == ("Material Fact", "high", True)
    assert ir._classify_cvm("Dados Econômico-Financeiros", "Press-release") == ("Financial Results", "high", True)


def test_link_collector_uses_nested_image_alt_text():
    parser = LinkCollector()
    parser.feed('<a href="https://api.mziq.com/document"><img alt="Release de Resultados 2T26"></a>')
    assert parser.links == [("https://api.mziq.com/document", "Release de Resultados 2T26")]


def test_generic_ri_page_links_are_labeled_collected_not_page_last_modified(tmp_path, monkeypatch):
    """The RI page's HTTP Last-Modified header describes when the PAGE was
    last edited, not when any individual linked document was published.
    Every document found on the same page must be honestly labeled
    'collected' (first-seen), never a falsely precise shared 'datetime'.
    """
    ir, _ = service(tmp_path)
    company = {
        "id": "company-1", "ri_url": "https://ri.example.com/investors",
        "market": "B3", "company_name": "Example Co", "regulator_id": None,
        "symbols": ["EXPL3"],
    }
    page_text = (
        '<a href="https://ri.example.com/docs/press-release.pdf">Press Release</a>'
        '<a href="https://ri.example.com/docs/financial-results.pdf">Financial Results</a>'
    )
    monkeypatch.setattr(
        ir, "_fetch_ri_page",
        lambda url: (page_text, {"last-modified": "Wed, 20 Aug 2026 12:00:00 GMT"}),
    )
    collected_at = datetime(2026, 8, 25, 9, 58, tzinfo=timezone.utc)

    _, events = ir._collect_ri_company(company, collected_at)

    assert len(events) == 2
    assert {event["title"] for event in events} == {"Press Release", "Financial Results"}
    for event in events:
        assert event["published_time_precision"] == "collected"
        assert event["published_at"] == collected_at


def test_ri_navigation_pages_do_not_become_valuation_events():
    source = "https://ri.jhsf.com.br/informacoes-financeiras/central-de-resultados/"
    assert is_ri_navigation_link("Central de Resultados", source, source)
    assert is_ri_navigation_link("Results Center", f"{source}?tab=2026", source)
    assert not is_ri_navigation_link(
        "Release de Resultados 2T26",
        "https://api.mziq.com/documentos/jhsf-2t26.pdf",
        source,
    )


def test_priner_official_ir_override_points_to_results_center():
    assert RI_URL_OVERRIDES["PRNR3"] == (
        "https://ri.priner.com.br/informacoes-aos-investidores/central-de-resultados/"
    )


def test_jhsf_official_ir_override_points_to_results_center():
    assert RI_URL_OVERRIDES["JHSF3"] == (
        "https://ri.jhsf.com.br/informacoes-financeiras/central-de-resultados/"
    )


def test_b3_ir_universe_excludes_fractional_tickers(tmp_path):
    ir, database = service(tmp_path)
    ir.register_b3_universe([
        {"symbol": "JHSF3", "name": "JHSF Participacoes"},
        {"symbol": "JHSF3F", "name": "JHSF Participacoes"},
    ])
    assert [item["symbol"] for item in database.ir_watch_symbols()] == ["JHSF3"]


def test_company_rename_merges_catalog_and_regulator_records(tmp_path):
    _, database = service(tmp_path)
    database.register_ir_securities([{
        "market": "B3", "company_name": "CVLB Brasil S.A.",
        "name_key": "CVLB BRASIL", "regulator_id": "12345", "exchange": "B3",
    }])
    database.register_ir_securities([{
        "market": "B3", "symbol": "CVLB3",
        "company_name": "CVLB Brasil em Recuperacao Judicial",
        "name_key": "CVLB BRASIL EM RECUPERACAO JUDICIAL", "exchange": "B3",
    }])

    database.register_ir_securities([{
        "market": "B3", "company_name": "CVLB Brasil em Recuperacao Judicial",
        "name_key": "CVLB BRASIL EM RECUPERACAO JUDICIAL",
        "regulator_id": "12345", "exchange": "B3",
    }])

    companies = database.list_ir_companies("B3")
    assert len(companies) == 1
    assert companies[0]["regulator_id"] == "12345"
    assert companies[0]["symbols"] == ["CVLB3"]


def test_regulator_evidence_is_valid_without_a_registered_issuer_page(tmp_path, monkeypatch):
    ir, database = service(tmp_path)
    ir.add_watch("TEST3", "B3", "Companhia Teste")
    company = database.list_ir_companies("B3")[0]
    published_at = datetime(2026, 8, 14, 12, tzinfo=timezone.utc)
    database.save_ir_events([{
        "source_code": "cvm", "external_id": "test3-cvm", "company_id": company["id"],
        "market": "B3", "symbol": "TEST3", "company_name": company["company_name"],
        "event_type": "Material Fact", "title": "Fato relevante", "summary": "Official filing",
        "published_at": published_at, "published_time_precision": "datetime",
        "reference_date": None, "official_url": "https://dados.cvm.gov.br/",
        "document_url": "https://www.rad.cvm.gov.br/example", "materiality": "high",
        "valuation_relevant": True, "valuation_status": "pending_review", "raw_metadata": {},
        "collected_at": published_at,
    }])
    monkeypatch.setattr(ir, "sync_cvm", lambda: (0, 0))

    result = ir.refresh_company("TEST3", "B3")

    assert result["verification_status"] == "regulator_only"
    assert result["ri_url"] == "https://dados.cvm.gov.br/"


def test_cvm_ipe_404_is_an_audited_partial_source_not_a_full_sync_failure(tmp_path, monkeypatch):
    ir, database = service(tmp_path)

    class MissingIpeClient:
        def get(self, url, **kwargs):
            return httpx.Response(404, request=httpx.Request("GET", url))

    ir.client = MissingIpeClient()
    monkeypatch.setattr(ir, "_cvm_structured_package", lambda kind, year, cutoff: (
        ([{
            "DENOM_CIA": "PETROLEO BRASILEIRO S.A. PETROBRAS",
            "CD_CVM": "9512",
            "CNPJ_CIA": "33.000.167/0001-01",
        }] if kind == "itr" else []),
        b"",
        f"https://dados.cvm.gov.br/{kind}-{year}.zip",
    ))
    monkeypatch.setattr(ir, "_register_brapi_b3_universe", lambda: None)
    monkeypatch.setattr(ir, "_register_cvm_ri_channels", lambda year, companies: 0)
    monkeypatch.setattr(ir, "_enrich_cvm_security_bridges", lambda rows, companies: None)
    monkeypatch.setattr(ir, "_cvm_insider_transactions", lambda year, cutoff: [])
    monkeypatch.setattr("app.investor_relations.extract_itr_official_fundamentals", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.investor_relations.save_official_fundamentals", lambda *args, **kwargs: None)

    records_read, records_written = ir.sync_cvm()

    assert records_read == 1
    assert records_written == 0
    run = next(iter(database._ingestion_runs.values()))
    assert run["status"] == "succeeded"
    assert "package unavailable (HTTP 404)" in run["error_summary"]


def test_cvm_ipe_rows_keep_the_existing_cutoff_behavior(tmp_path):
    ir, _ = service(tmp_path)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(
            "ipe_cia_aberta_2026.csv",
            (
                "Data_Entrega;Nome_Companhia\n"
                "2026-02-23;Evento antigo\n"
                "2026-02-24;Evento no corte\n"
            ).encode("latin-1"),
        )

    class AvailableIpeClient:
        def get(self, url, **kwargs):
            return httpx.Response(200, content=payload.getvalue(), request=httpx.Request("GET", url))

    ir.client = AvailableIpeClient()

    rows, available = ir._cvm_ipe_rows(2026, date(2026, 2, 24))

    assert available is True
    assert [row["Nome_Companhia"] for row in rows] == ["Evento no corte"]


def test_cvm_ipe_non_404_http_error_remains_fail_closed(tmp_path):
    ir, _ = service(tmp_path)

    class BrokenIpeClient:
        def get(self, url, **kwargs):
            return httpx.Response(503, request=httpx.Request("GET", url))

    ir.client = BrokenIpeClient()

    with pytest.raises(httpx.HTTPStatusError):
        ir._cvm_ipe_rows(2026, date(2026, 2, 24))


def test_new_ir_event_is_queued_once_for_every_mapped_security(tmp_path):
    _, database = service(tmp_path)
    database.register_ir_securities([{
        "market": "B3", "symbol": "TEST3", "company_name": "Companhia Teste",
        "name_key": "COMPANHIA TESTE", "exchange": "B3",
    }])
    company = database.list_ir_companies("B3")[0]
    first_seen = datetime(2026, 8, 14, 12, tzinfo=timezone.utc)
    event = {
        "source_code": "cvm", "external_id": "test3-result", "company_id": company["id"],
        "market": "B3", "symbol": "TEST3", "company_name": company["company_name"],
        "event_type": "Financial Results", "title": "Resultados 2T26", "summary": "Official filing",
        "published_at": first_seen, "published_time_precision": "datetime",
        "reference_date": date(2026, 6, 30), "official_url": "https://dados.cvm.gov.br/",
        "document_url": None, "materiality": "high", "valuation_relevant": True,
        "valuation_status": "pending_review", "raw_metadata": {}, "collected_at": first_seen,
    }
    database.save_ir_events([event])
    claimed = database.claim_ir_valuation_updates()
    assert [(item["market"], item["symbol"]) for item in claimed] == [("B3", "TEST3")]
    database.finish_ir_valuation_updates(claimed, succeeded=True, incorporate_events=True)

    incorporated = database.latest_valuation_ir_events(["TEST3"])["TEST3"]
    assert incorporated["valuation_status"] == "incorporated"
    assert incorporated["review_note"] == "Automatically incorporated after successful valuation refresh."

    database.save_ir_events([{**event, "collected_at": first_seen + timedelta(hours=1)}])
    assert database.claim_ir_valuation_updates() == []
    refreshed = database.latest_valuation_ir_events(["TEST3"])["TEST3"]
    assert refreshed["collected_at"] == first_seen
    assert refreshed["valuation_status"] == "incorporated"


def test_recollecting_undated_ri_event_keeps_first_seen_chronology(tmp_path):
    _, database = service(tmp_path)
    first_seen = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)
    event = {
        "source_code": "ri", "external_id": "stable-document", "company_id": None,
        "market": "B3", "symbol": "TEST3", "company_name": "Companhia Teste",
        "event_type": "Issuer Update", "form": "RI", "title": "Documento sem data",
        "summary": "Official issuer page", "published_at": first_seen,
        "published_time_precision": "collected", "reference_date": None,
        "official_url": "https://ri.example.com", "document_url": "https://ri.example.com/document.pdf",
        "materiality": "medium", "valuation_relevant": False,
        "valuation_status": "informational", "raw_metadata": {}, "collected_at": first_seen,
    }
    database.save_ir_events([event])

    recollected_at = first_seen + timedelta(days=4)
    database.save_ir_events([{**event, "published_at": recollected_at, "collected_at": recollected_at}])

    refreshed = database.list_ir_events(monitored_only=False)[0]
    assert refreshed["published_at"] == first_seen
    assert refreshed["collected_at"] == first_seen


def test_ir_event_is_incorporated_only_after_every_security_is_applied(tmp_path):
    _, database = service(tmp_path)
    for symbol in ("TEST3", "TEST4"):
        database.register_ir_securities([{
            "market": "B3", "symbol": symbol, "company_name": "Companhia Teste",
            "name_key": "COMPANHIA TESTE", "exchange": "B3",
        }])
    company = database.list_ir_companies("B3")[0]
    published_at = datetime(2026, 8, 19, 12, tzinfo=timezone.utc)
    database.save_ir_events([{
        "source_code": "cvm", "external_id": "test-multi-security",
        "company_id": company["id"], "market": "B3", "symbol": "TEST3",
        "company_name": company["company_name"], "event_type": "Financial Results",
        "title": "Resultados 2T26", "summary": "Official filing",
        "published_at": published_at, "published_time_precision": "datetime",
        "reference_date": date(2026, 6, 30), "official_url": "https://dados.cvm.gov.br/",
        "document_url": None, "materiality": "high", "valuation_relevant": True,
        "valuation_status": "pending_review", "raw_metadata": {}, "collected_at": published_at,
    }])

    claimed = database.claim_ir_valuation_updates()
    assert {item["symbol"] for item in claimed} == {"TEST3", "TEST4"}
    database.finish_ir_valuation_updates(
        [claimed[0]], succeeded=True, incorporate_events=True,
    )
    assert database.latest_valuation_ir_events(["TEST3"])["TEST3"]["valuation_status"] == "pending_review"

    database.finish_ir_valuation_updates(
        [claimed[1]], succeeded=True, incorporate_events=True,
    )
    assert database.latest_valuation_ir_events(["TEST3"])["TEST3"]["valuation_status"] == "incorporated"


def test_cvm_itr_extraction_quarterizes_ytd_and_scales_thousands():
    def statement(name, rows):
        header = (
            "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;"
            "ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA\n"
        )
        return header + "\n".join(rows) + "\n"

    dre_rows = [
        "00.000.000/0001-00;2026-03-31;1;TESTE S.A.;1;DRE;REAL;MIL;PENÚLTIMO;2025-01-01;2025-03-31;3.01;Receita;80;S",
        "00.000.000/0001-00;2026-03-31;1;TESTE S.A.;1;DRE;REAL;MIL;ÚLTIMO;2026-01-01;2026-03-31;3.01;Receita;100;S",
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;1;DRE;REAL;MIL;PENÚLTIMO;2025-01-01;2025-06-30;3.01;Receita;200;S",
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;1;DRE;REAL;MIL;PENÚLTIMO;2025-04-01;2025-06-30;3.01;Receita;120;S",
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;1;DRE;REAL;MIL;ÚLTIMO;2026-01-01;2026-06-30;3.01;Receita;260;S",
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;1;DRE;REAL;MIL;ÚLTIMO;2026-04-01;2026-06-30;3.01;Receita;160;S",
        "00.000.000/0001-00;2026-03-31;1;TESTE S.A.;1;DRE;REAL;MIL;ÚLTIMO;2026-01-01;2026-03-31;3.11.01;Lucro;20;S",
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;1;DRE;REAL;MIL;ÚLTIMO;2026-01-01;2026-06-30;3.11.01;Lucro;55;S",
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;1;DRE;REAL;MIL;ÚLTIMO;2026-04-01;2026-06-30;3.11.01;Lucro;35;S",
    ]
    bpa_rows = [
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;1;BPA;REAL;MIL;ÚLTIMO;2026-06-30;2026-06-30;1.01.01;Caixa;40;S",
    ]
    bpp_rows = [
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;1;BPP;REAL;MIL;ÚLTIMO;2026-06-30;2026-06-30;2.03;PL;80;S",
    ]
    capital = (
        "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;QT_ACAO_ORDIN_CAP_INTEGR;QT_ACAO_PREF_CAP_INTEGR;"
        "QT_ACAO_TOTAL_CAP_INTEGR;QT_ACAO_ORDIN_TESOURO;QT_ACAO_PREF_TESOURO;QT_ACAO_TOTAL_TESOURO\n"
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;100;0;100;5;0;5\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("itr_cia_aberta_DRE_con_2026.csv", statement("DRE", dre_rows).encode("latin-1"))
        archive.writestr("itr_cia_aberta_BPA_con_2026.csv", statement("BPA", bpa_rows).encode("latin-1"))
        archive.writestr("itr_cia_aberta_BPP_con_2026.csv", statement("BPP", bpp_rows).encode("latin-1"))
        archive.writestr("itr_cia_aberta_composicao_capital_2026.csv", capital.encode("latin-1"))

    rows = extract_itr_official_fundamentals(
        buffer.getvalue(), year=2026,
        issuers={"00.000.000/0001-00": {"symbols": ["TEST3"], "company_name": "TESTE S.A."}},
        source_url="https://dados.cvm.gov.br/",
    )

    assert rows[0]["as_of"] == "2026-06-30"
    assert rows[0]["quarterlyIncome"][0]["totalRevenue"] == 160_000
    assert rows[0]["quarterlyIncome"][0]["netIncome"] == 35_000
    assert [
        (item["date"], item.get("totalRevenue"))
        for item in rows[0]["quarterlyIncome"]
        if item.get("totalRevenue") is not None
    ] == [
        ("2026-06-30", 160_000),
        ("2026-03-31", 100_000),
        ("2025-06-30", 120_000),
        ("2025-03-31", 80_000),
    ]
    assert rows[0]["sharesOutstanding"] == 95


def test_mziq_categories_support_push_based_templates(tmp_path):
    ir, _ = service(tmp_path)
    page = """
      <script>
        var categories = [];
        categories.push({
          title: 'Release',
          internal_name: 'release-priner',
          orderByPublished: true
        })
        categories.push({
          title: 'ITR/DFP',
          internal_name: 'investidores_informacoes_trimestrais_contabeis__itr'
        })
      </script>
    """

    assert ir._mziq_category_names(page) == [
        "release-priner",
        "investidores_informacoes_trimestrais_contabeis__itr",
    ]


def test_mziq_results_keep_quarter_reference_and_latest_publication_date(tmp_path):
    ir, database = service(tmp_path)
    ir.add_watch(
        "UNIP6",
        "B3",
        "UNIPAR CARBOCLORO S.A.",
        "https://ri.unipar.com/informacoes-aos-investidores/central-de-resultados/",
    )
    company = database.list_ir_companies("B3")[0]
    page = """
      <script>
        const fmId = 'unipar-id';
        const fmBase = 'https://api.mziq.com/mzfilemanager';
        var categories = [{"title":"Release","internal_name":"earnings_releases"}];
      </script>
    """

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"document_metas": [
                {
                    "id": "release-2t26", "file_title": "Release de Resultados 2T26",
                    "file_year": 2026, "file_quarter": 2,
                    "file_published_date": "2026-06-30T00:00:00.000Z",
                    "permalink": "https://api.mziq.com/release-2t26",
                    "internal_name": "earnings_releases",
                },
                {
                    "id": "itr-2t26", "file_title": "ITR/CVM 2T26",
                    "file_year": 2026, "file_quarter": 2,
                    "file_published_date": "2026-08-06T00:00:00.000Z",
                    "permalink": "https://api.mziq.com/itr-2t26",
                    "internal_name": "relatorio_cvm_itr",
                },
            ]}}

    class FakeClient:
        def post(self, *args, **kwargs):
            return FakeResponse()

    ir.client = FakeClient()
    events = ir._mziq_events(company, page, datetime(2026, 8, 6, tzinfo=timezone.utc))
    assert events is not None
    assert len(events) == 2
    assert {event["reference_date"] for event in events} == {date(2026, 6, 30)}
    assert {event["published_at"].date() for event in events} == {date(2026, 8, 6)}
    assert {event["published_at"].tzinfo for event in events} == {ir._mziq_publication_datetime("2026-08-06").tzinfo}
    assert all(event["valuation_status"] == "pending_review" for event in events)


def test_regulatory_event_drives_freshness_gate_and_pdf(tmp_path):
    ir, database = service(tmp_path)
    database.register_ir_securities([{
        "market": "B3",
        "symbol": "PRNR3",
        "company_name": "PRINER SERVICOS INDUSTRIAIS S.A.",
        "name_key": normalize_company_name("PRINER SERVICOS INDUSTRIAIS S.A."),
        "regulator_id": "24295",
        "exchange": "B3",
    }])
    company = database.list_ir_companies("B3")[0]
    published_at = datetime(2026, 8, 5, 21, 30, tzinfo=timezone.utc)
    database.save_ir_events([{
        "source_code": "cvm",
        "external_id": "PRNR3-2T26",
        "company_id": company["id"],
        "market": "B3",
        "symbol": "PRNR3",
        "company_name": company["company_name"],
        "regulator_id": "24295",
        "event_type": "Financial Results",
        "form": "Press-release",
        "title": "Resultados 2T26",
        "summary": "Release oficial",
        "published_at": published_at,
        "published_time_precision": "datetime",
        "reference_date": date(2026, 6, 30),
        "official_url": "https://dados.cvm.gov.br/",
        "document_url": "https://www.rad.cvm.gov.br/example",
        "materiality": "high",
        "valuation_relevant": True,
        "valuation_status": "pending_review",
        "raw_metadata": {},
        "collected_at": published_at,
    }])

    latest = database.latest_valuation_ir_events(["PRNR3"])["PRNR3"]
    stale = B3ScreenerService._ir_freshness("2026-03-31", latest)
    current = B3ScreenerService._ir_freshness("2026-06-30", latest)
    assert stale["ir_status"] == "pending_review"
    assert current["ir_status"] == "current"

    feed = ir.feed()
    assert feed.pending_reviews == 1
    assert feed.items[0].company_name == company["company_name"]
    pdf = ir.pdf.render(feed)
    assert pdf.read_bytes().startswith(b"%PDF")


def test_sec_fulltext_matches_aggregates_keywords_per_accession(tmp_path):
    ir, _ = service(tmp_path)
    calls = []

    class FakeResponse:
        def __init__(self, hits):
            self._hits = hits

        def raise_for_status(self):
            return None

        def json(self):
            return {"hits": {"hits": self._hits}}

    class FakeClient:
        def get(self, url, params=None):
            calls.append(params)
            keyword = (params or {}).get("q", "")
            if keyword == '"guidance"':
                return FakeResponse([{"_id": "0001234567-26-000111:ex99.htm"}])
            if keyword == '"acquisition"':
                return FakeResponse([{"_id": "0001234567-26-000111:ex99.htm"}, {"_id": "0009999999-26-000222:8k.htm"}])
            return FakeResponse([])

    ir.client = FakeClient()
    matches = ir._sec_fulltext_matches(["0001234567"], date(2026, 8, 1))

    assert matches == {
        "0001234567-26-000111": ["guidance", "acquisition"],
        "0009999999-26-000222": ["acquisition"],
    }
    # One request per keyword, all scoped to the given CIK -- confirms the
    # ciks filter (not just the keyword) is actually sent.
    assert len(calls) == len(SEC_FULLTEXT_KEYWORDS)
    assert all(call["ciks"] == "0001234567" for call in calls)


def test_sec_fulltext_matches_zero_pads_unpadded_ciks(tmp_path):
    """EDGAR full-text search matches CIKs by their exact zero-padded (10-digit)
    stored form -- an unpadded CIK doesn't error, it silently matches nothing
    (confirmed against the live API). _enrich_with_sec_fulltext must pad
    event["regulator_id"] before querying, or every match silently vanishes.
    """
    captured_ciks = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"hits": {"hits": []}}

    class FakeClient:
        def get(self, url, params=None):
            captured_ciks.append((params or {}).get("ciks"))
            return FakeResponse()

    ir, _ = service(tmp_path)
    ir.client = FakeClient()
    ir._sec_fulltext_matches(["320193"], date(2026, 8, 1))

    assert captured_ciks and all(ciks == "320193" for ciks in captured_ciks)
    # _sec_fulltext_matches itself does no padding -- that's _enrich_with_sec_fulltext's
    # job, exercised below, so a caller must pad before calling this directly.


def test_enrich_with_sec_fulltext_pads_cik_and_skips_stale_events(tmp_path):
    ir, _ = service(tmp_path)
    now = datetime.now(timezone.utc)
    fresh_event = {
        "external_id": "0001234567-26-000111", "regulator_id": "1234567",
        "published_at": now - timedelta(days=1), "summary": "SEC form 8-K",
        "raw_metadata": {},
    }
    stale_event = {
        "external_id": "0009999999-26-000222", "regulator_id": "9999999",
        "published_at": now - timedelta(days=90), "summary": "SEC form 10-K",
        "raw_metadata": {},
    }
    events = [fresh_event, stale_event]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"hits": {"hits": [{"_id": "0001234567-26-000111:ex99.htm"}]}}

    class FakeClient:
        def get(self, url, params=None):
            assert params["ciks"] == "0001234567"
            return FakeResponse()

    ir.client = FakeClient()
    ir._enrich_with_sec_fulltext(events)

    assert "Menções:" in fresh_event["summary"]
    assert fresh_event["raw_metadata"]["fulltext_keywords"]
    assert stale_event["summary"] == "SEC form 10-K"
    assert stale_event["raw_metadata"] == {}


def test_enrich_with_sec_fulltext_is_best_effort_on_failure(tmp_path):
    ir, _ = service(tmp_path)
    event = {
        "external_id": "0001234567-26-000111", "regulator_id": "1234567",
        "published_at": datetime.now(timezone.utc), "summary": "SEC form 8-K",
        "raw_metadata": {},
    }

    class FakeClient:
        def get(self, url, params=None):
            raise RuntimeError("EDGAR is down")

    ir.client = FakeClient()
    ir._enrich_with_sec_fulltext([event])

    assert event["summary"] == "SEC form 8-K"


def _service_with_finnhub(tmp_path):
    settings = Settings(
        database_url="",
        migrations_dir=tmp_path,
        investor_relations_output_dir=tmp_path / "ir-pdf",
        finnhub_api_token="test-token",
    )
    database = Database(settings)
    return InvestorRelationsService(settings, database), database


def test_finnhub_insider_events_builds_ir_events_from_recent_transactions(tmp_path):
    ir, _ = _service_with_finnhub(tmp_path)
    recent = (date.today() - timedelta(days=5)).isoformat()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{
                "name": "COOK TIMOTHY D", "share": 511000, "change": -223986,
                "filingDate": recent, "transactionDate": recent,
                "transactionCode": "S", "transactionPrice": 227.5,
            }]}

    class FakeClient:
        def get(self, url, *, params=None):
            assert params["symbol"] == "AAPL"
            return FakeResponse()

    ir.finnhub.client = FakeClient()
    events = ir._finnhub_insider_events("AAPL", "0000320193", None, "Apple Inc.")

    assert len(events) == 1
    event = events[0]
    assert event["source_code"] == "sec"
    assert event["market"] == "US"
    assert event["event_type"] == "Insider Transaction"
    assert event["materiality"] == "low"
    assert event["valuation_relevant"] is False
    assert "venda" in event["title"]
    assert event["external_id"] == f"finnhub-insider-AAPL-{recent}-cook-timothy-d-S"


def test_finnhub_insider_events_filters_out_transactions_older_than_lookback(tmp_path):
    ir, _ = _service_with_finnhub(tmp_path)
    stale = (date.today() - timedelta(days=200)).isoformat()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{
                "name": "OLD INSIDER", "share": 100, "change": 100,
                "filingDate": stale, "transactionDate": stale,
                "transactionCode": "P", "transactionPrice": 10.0,
            }]}

    class FakeClient:
        def get(self, url, *, params=None):
            return FakeResponse()

    ir.finnhub.client = FakeClient()
    events = ir._finnhub_insider_events("AAPL", "0000320193", None, "Apple Inc.")

    assert events == []


def test_finnhub_insider_events_is_a_noop_without_an_api_token(tmp_path):
    ir, _ = service(tmp_path)  # default helper -- no finnhub_api_token configured

    class FakeClient:
        def get(self, *args, **kwargs):
            raise AssertionError("must not call Finnhub without a configured API token")

    ir.finnhub.client = FakeClient()
    assert ir._finnhub_insider_events("AAPL", "0000320193", None, "Apple Inc.") == []


def test_finnhub_insider_events_is_best_effort_on_failure(tmp_path):
    ir, _ = _service_with_finnhub(tmp_path)

    class FakeClient:
        def get(self, *args, **kwargs):
            raise RuntimeError("Finnhub is down")

    ir.finnhub.client = FakeClient()
    assert ir._finnhub_insider_events("AAPL", "0000320193", None, "Apple Inc.") == []


def _service_with_eodhd(tmp_path):
    settings = Settings(
        database_url="",
        migrations_dir=tmp_path,
        investor_relations_output_dir=tmp_path / "ir-pdf",
        eodhd_api_token="test-token",
    )
    database = Database(settings)
    return InvestorRelationsService(settings, database), database


class FakeEodhdHttp:
    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, *, params=None, headers=None):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_eodhd_insider_events_builds_ir_events_from_recent_transactions(tmp_path):
    """Root-caused 2026-08-20 (data-source audit): EODHD's All-in-one plan
    includes its own SEC Form 4 feed, but it was never called anywhere --
    only Finnhub's insider data was ever used. Now used as a fallback
    (never summed with Finnhub's, since both source the same underlying
    filings and would double-count the same real-world transactions).
    """
    ir, _ = _service_with_eodhd(tmp_path)
    recent = (date.today() - timedelta(days=5)).isoformat()
    ir.eodhd.http = FakeEodhdHttp({
        "data": [{
            "accession_number": "acc-1", "filed_at": recent, "period_of_report": recent,
            "non_derivative": [{
                "reporting_owner_name": "COOK TIMOTHY D", "transaction_code": "S",
                "acquired_or_disposed": "D", "shares_amount": 223986,
                "price_per_share": 227.5, "shares_owned_after": 511000,
                "transaction_date": f"{recent}T00:00:00+00:00",
            }],
            "derivative": [], "footnotes": [],
        }],
        "meta": {}, "links": {"next": None},
    })

    events = ir._eodhd_insider_events("AAPL", "0000320193", None, "Apple Inc.")

    assert len(events) == 1
    event = events[0]
    assert event["source_code"] == "sec"
    assert event["market"] == "US"
    assert event["event_type"] == "Insider Transaction"
    assert "venda" in event["title"]
    assert event["external_id"] == f"eodhd-insider-AAPL-{recent}-cook-timothy-d-S"
    # Deliberately distinct from Finnhub's prefix so the two never collide.
    assert not event["external_id"].startswith("finnhub-")


def test_eodhd_insider_events_is_a_noop_without_an_api_token(tmp_path):
    ir, _ = service(tmp_path)  # default helper -- no eodhd_api_token configured
    ir.eodhd.http = FakeEodhdHttp(RuntimeError("must not be called"))

    assert ir._eodhd_insider_events("AAPL", "0000320193", None, "Apple Inc.") == []


def test_eodhd_insider_events_is_best_effort_on_failure(tmp_path):
    ir, _ = _service_with_eodhd(tmp_path)
    ir.eodhd.http = FakeEodhdHttp(RuntimeError("EODHD is down"))

    assert ir._eodhd_insider_events("AAPL", "0000320193", None, "Apple Inc.") == []


def test_eodhd_insider_events_used_only_as_a_fallback_when_finnhub_has_nothing(tmp_path):
    """Confirms the actual dedup safeguard: EODHD is skipped entirely when
    Finnhub already returned data for the symbol, so the same real-world
    transaction never gets counted from both sources."""
    settings = Settings(
        database_url="",
        migrations_dir=tmp_path,
        investor_relations_output_dir=tmp_path / "ir-pdf",
        finnhub_api_token="test-token",
        eodhd_api_token="test-token",
    )
    database = Database(settings)
    ir = InvestorRelationsService(settings, database)
    recent = (date.today() - timedelta(days=5)).isoformat()

    class FakeFinnhubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{
                "name": "COOK TIMOTHY D", "share": 511000, "change": -223986,
                "filingDate": recent, "transactionDate": recent,
                "transactionCode": "S", "transactionPrice": 227.5,
            }]}

    class FakeFinnhubClient:
        def get(self, url, *, params=None):
            return FakeFinnhubResponse()

    ir.finnhub.client = FakeFinnhubClient()
    ir.eodhd.http = FakeEodhdHttp(RuntimeError("must not be called when Finnhub already has data"))

    finnhub_events = ir._finnhub_insider_events("AAPL", "0000320193", None, "Apple Inc.")
    events = finnhub_events or ir._eodhd_insider_events("AAPL", "0000320193", None, "Apple Inc.")

    assert len(events) == 1
    assert events[0]["external_id"].startswith("finnhub-")


def test_finnhub_sentiment_event_is_deduped_by_iso_week(tmp_path):
    ir, _ = _service_with_finnhub(tmp_path)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "sentiment": {"bullishPercent": 0.7, "bearishPercent": 0.3},
                "buzz": {"articlesInLastWeek": 12},
                "companyNewsScore": 0.6,
            }

    class FakeClient:
        def get(self, url, *, params=None):
            return FakeResponse()

    ir.finnhub.client = FakeClient()
    events = ir._finnhub_sentiment_event("AAPL", None, "Apple Inc.")

    assert len(events) == 1
    event = events[0]
    assert event["source_code"] == "finnhub"
    assert event["event_type"] == "News Sentiment"
    assert event["materiality"] == "low"
    assert event["valuation_relevant"] is False
    iso_year, iso_week, _ = datetime.now(timezone.utc).isocalendar()
    assert event["external_id"] == f"finnhub-sentiment-AAPL-{iso_year}-W{iso_week:02d}"


def test_finnhub_sentiment_event_is_noop_when_no_sentiment_available(tmp_path):
    ir, _ = _service_with_finnhub(tmp_path)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class FakeClient:
        def get(self, url, *, params=None):
            return FakeResponse()

    ir.finnhub.client = FakeClient()
    assert ir._finnhub_sentiment_event("AAPL", None, "Apple Inc.") == []


def test_finnhub_news_events_only_keeps_keyword_matches(tmp_path):
    ir, _ = _service_with_finnhub(tmp_path)
    now_ts = int(datetime.now(timezone.utc).timestamp())

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"id": 1, "headline": "Apple announces new acquisition", "summary": "", "source": "Reuters", "url": "https://x/1", "datetime": now_ts},
                {"id": 2, "headline": "Apple stock closes flat on Tuesday", "summary": "Routine market recap.", "source": "Wire", "url": "https://x/2", "datetime": now_ts},
            ]

    class FakeClient:
        def get(self, url, *, params=None):
            return FakeResponse()

    ir.finnhub.client = FakeClient()
    events = ir._finnhub_news_events("AAPL", None, "Apple Inc.", date(2026, 8, 1), date(2026, 8, 19))

    assert len(events) == 1
    event = events[0]
    assert event["source_code"] == "finnhub"
    assert event["event_type"] == "News Mention"
    assert event["external_id"] == "finnhub-news-1"
    assert "acquisition" in event["raw_metadata"]["matched_keywords"]


def test_sync_finnhub_news_is_a_noop_without_an_api_token(tmp_path):
    ir, _ = service(tmp_path)  # default helper -- no finnhub_api_token configured

    class FakeClient:
        def get(self, *args, **kwargs):
            raise AssertionError("must not call Finnhub without a configured API token")

    ir.finnhub.client = FakeClient()
    assert ir.sync_finnhub_news() == (0, 0)


def _zip_bytes(filename: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(filename, content)
    return buffer.getvalue()


def _vlmo_con_csv(rows: list[str]) -> bytes:
    header = (
        "CNPJ_Companhia;Nome_Companhia;Data_Referencia;Versao;Tipo_Empresa;Empresa;"
        "Tipo_Cargo;Tipo_Movimentacao;Descricao_Movimentacao;Tipo_Operacao;Tipo_Ativo;"
        "Caracteristica_Valor_Mobiliario;Intermediario;Data_Movimentacao;Quantidade;"
        "Preco_Unitario;Volume\n"
    )
    return (header + "\n".join(rows) + "\n").encode("latin-1")


class ZipHttpResponse:
    def __init__(self, *, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class ZipHttpClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, *args, **kwargs):
        self.calls.append(url)
        return self.response


def test_cvm_insider_transactions_keeps_only_own_company_buy_sell_rows(tmp_path):
    """Row shapes below are exactly what dados.cvm.gov.br returned for
    vlmo_cia_aberta_con_2026.csv when checked live (2026-08-19) -- balance
    rows (no real transaction), and rows about a *related* entity's shares
    (Tipo_Empresa != "Companhia") must both be excluded."""
    rows = [
        # Real buy of the reporting company's own shares -- keep.
        "00.001.180/0001-26;AXIA ENERGIA S.A.;2026-01-01;2;Companhia;AXIA ENERGIA S.A.;"
        "Conselho de Administração ou Vinculado;Compra à vista;;Crédito;Ações;PNB;Itaú;"
        "2026-01-07;7600;52.3100000000;397556.0000000000",
        # Opening balance -- not a transaction, drop.
        "00.000.000/0001-91;BANCO DO BRASIL S.A.;2026-01-01;1;Companhia;BCO BRASIL S.A.;"
        "Controlador ou Vinculado;Saldo Inicial;;Crédito;Ações;ON;;;2865417084;;",
        # Sale, but of a *related* (Controlada) entity's shares -- drop.
        "11.111.111/0001-11;TESTE HOLDING S.A.;2026-01-01;1;Controlada;SUBSIDIARIA S.A.;"
        "Diretor ou Vinculado;Venda à vista;;Débito;Ações;ON;XP;2026-01-10;1000;10.0000000000;10000.0000000000",
        # Real sale, but before the cutoff -- drop.
        "00.001.180/0001-26;AXIA ENERGIA S.A.;2025-06-01;1;Companhia;AXIA ENERGIA S.A.;"
        "Diretor ou Vinculado;Venda à vista;;Débito;Ações;PNB;Itaú;2025-06-01;500;40.0000000000;20000.0000000000",
    ]
    response = ZipHttpResponse(content=_zip_bytes("vlmo_cia_aberta_con_2026.csv", _vlmo_con_csv(rows)))
    ir, _ = service(tmp_path)
    ir.client = ZipHttpClient(response)

    result = ir._cvm_insider_transactions(2026, date(2026, 1, 1))

    assert len(result) == 1
    assert result[0]["Nome_Companhia"] == "AXIA ENERGIA S.A."
    assert result[0]["Tipo_Movimentacao"] == "Compra à vista"


def test_cvm_insider_transactions_returns_empty_on_404(tmp_path):
    ir, _ = service(tmp_path)
    ir.client = ZipHttpClient(ZipHttpResponse(status_code=404))

    assert ir._cvm_insider_transactions(2099, date(2026, 1, 1)) == []


def test_cvm_insider_events_resolves_symbol_by_cnpj_and_formats_in_portuguese(tmp_path):
    ir, _ = service(tmp_path)
    rows = [{
        "CNPJ_Companhia": "00.001.180/0001-26", "Nome_Companhia": "AXIA ENERGIA S.A.",
        "Tipo_Empresa": "Companhia", "Tipo_Cargo": "Conselho de Administração ou Vinculado",
        "Tipo_Movimentacao": "Compra à vista", "Caracteristica_Valor_Mobiliario": "PNB",
        "Data_Movimentacao": "2026-01-07", "Quantidade": "7600", "Preco_Unitario": "52.31",
    }]
    company_by_tax_id = {
        "00.001.180/0001-26": {
            "id": "company-1", "symbols": ["ELET3", "ELET6"],
            "company_name": "AXIA ENERGIA S.A.", "regulator_id": "2437", "tax_id": "00.001.180/0001-26",
        },
    }

    events = ir._cvm_insider_events(rows, company_by_tax_id)

    assert len(events) == 1
    event = events[0]
    assert event["source_code"] == "cvm"
    assert event["market"] == "B3"
    assert event["symbol"] == "ELET3"
    assert event["event_type"] == "Insider Transaction"
    assert event["materiality"] == "low"
    assert event["valuation_relevant"] is False
    assert "compra de 7.600 ações" in event["title"]
    assert "R$ 52.31/ação" in event["summary"]
    assert event["external_id"].startswith("cvm-insider-")


def test_cvm_insider_events_skips_rows_with_unresolvable_cnpj(tmp_path):
    ir, _ = service(tmp_path)
    rows = [{
        "CNPJ_Companhia": "99.999.999/0001-99", "Nome_Companhia": "DESCONHECIDA S.A.",
        "Tipo_Empresa": "Companhia", "Tipo_Cargo": "Diretor ou Vinculado",
        "Tipo_Movimentacao": "Venda à vista", "Caracteristica_Valor_Mobiliario": "ON",
        "Data_Movimentacao": "2026-01-07", "Quantidade": "100", "Preco_Unitario": "10.00",
    }]

    assert ir._cvm_insider_events(rows, {}) == []


def test_insider_net_signal_reflects_buy_sell_balance_and_sample_confidence():
    assert B3ScreenerService._insider_net_signal(None) == 0.0
    assert B3ScreenerService._insider_net_signal({"buy_count": 0, "sell_count": 0, "total_count": 0}) == 0.0

    thin = B3ScreenerService._insider_net_signal({"buy_count": 1, "sell_count": 0, "total_count": 1})
    full_buy = B3ScreenerService._insider_net_signal({"buy_count": 4, "sell_count": 0, "total_count": 4})
    full_sell = B3ScreenerService._insider_net_signal({"buy_count": 0, "sell_count": 4, "total_count": 4})

    assert 0 < thin < full_buy
    assert full_buy == 1.0
    assert full_sell == -1.0


def test_matrix_risk_score_lowers_on_insider_buying_and_raises_on_selling():
    """Root-caused 2026-08-20: governance_risk (10% weight of _matrix_risk_score)
    was a hardcoded 50.0 constant despite CVM VLMO insider data being fully
    ingested and available. Now driven by row["insider_net_signal"], bounded
    to a governance_risk range of [30, 70] so it can't dominate the score.
    """
    row = {
        "valuation_profile": "general", "beta": 1.0, "volatility_90d": 0.30,
        "debt_to_equity": 1.0, "earnings_growth": 0.10, "profit_margin": 0.10,
        "adtv_90d": 20_000_000,
    }

    neutral = B3ScreenerService._matrix_risk_score({**row, "insider_net_signal": 0.0})
    buying = B3ScreenerService._matrix_risk_score({**row, "insider_net_signal": 1.0})
    selling = B3ScreenerService._matrix_risk_score({**row, "insider_net_signal": -1.0})
    no_signal_at_all = B3ScreenerService._matrix_risk_score(row)

    assert buying < neutral < selling
    assert no_signal_at_all == neutral
