import io
import zipfile
from datetime import date, datetime, timedelta, timezone

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
    database.finish_ir_valuation_updates(claimed, succeeded=True)

    database.save_ir_events([{**event, "collected_at": first_seen + timedelta(hours=1)}])
    assert database.claim_ir_valuation_updates() == []
    assert database.latest_valuation_ir_events(["TEST3"])["TEST3"]["collected_at"] == first_seen


def test_cvm_itr_extraction_quarterizes_ytd_and_scales_thousands():
    def statement(name, rows):
        header = (
            "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;"
            "ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA\n"
        )
        return header + "\n".join(rows) + "\n"

    dre_rows = [
        "00.000.000/0001-00;2026-03-31;1;TESTE S.A.;1;DRE;REAL;MIL;ÚLTIMO;2026-01-01;2026-03-31;3.01;Receita;100;S",
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;1;DRE;REAL;MIL;ÚLTIMO;2026-01-01;2026-06-30;3.01;Receita;260;S",
        "00.000.000/0001-00;2026-03-31;1;TESTE S.A.;1;DRE;REAL;MIL;ÚLTIMO;2026-01-01;2026-03-31;3.11.01;Lucro;20;S",
        "00.000.000/0001-00;2026-06-30;1;TESTE S.A.;1;DRE;REAL;MIL;ÚLTIMO;2026-01-01;2026-06-30;3.11.01;Lucro;55;S",
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
