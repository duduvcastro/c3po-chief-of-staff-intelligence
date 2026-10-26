"""Beginning-book observations only. Synthetic rows/bytes, no real fiscal authority."""
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
import socket

import pytest

from app.statement_vintages import vintage_row_hash
from app.valuation_ensemble_adapters import BundleSources, adapt_company
from app.valuation_ensemble_inputs import canonical_hash, NotEvaluable
from app.valuation_ensemble_caller import run_shadow_cross_section
from app.valuation_ensemble_capture import CaptureRequest, OfficialCaptureClient, read_capture_receipt
from app.valuation_ensemble_originals import extract_sec_instance
from app.valuation_ensemble_original_package import CaptureReference, OriginalPackage
from app.valuation_ensemble_original_store import OriginalEvidenceStore
from app.valuation_ensemble_persistence import FileReceiptStore
from test_valuation_ensemble_adapters import T, fact, filing, source_bundle, request, premises
from test_valuation_ensemble_capture import Clock, Transport, Response, CONTACT, limits
from test_valuation_ensemble_original_package import sec_case
from test_valuation_ensemble_originals import artifact


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def fail(*args,**kwargs):pytest.fail("no network in beginning-book observations")
    monkeypatch.setattr(socket,"socket",fail);monkeypatch.setattr(socket,"create_connection",fail)


def bundle_with_income(spans,*,opening="2020-03-31"):
    bundle=source_bundle();bundle["facts"]=[x for x in bundle["facts"] if x["concept"]!="us-gaap:NetIncomeLoss"]
    for start,end,value in spans:
        bundle["facts"].append(fact("us-gaap:NetIncomeLoss",value,start=date.fromisoformat(start),end=date.fromisoformat(end)))
    if opening is not None:bundle["facts"].append(fact("us-gaap:StockholdersEquity",80,end=date.fromisoformat(opening)))
    return bundle


DIRECT=(("2020-04-01","2020-06-30",3),("2020-07-01","2020-09-30",4),
        ("2020-10-01","2020-12-31",5),("2021-01-01","2021-03-31",6))
YTD=(("2020-01-01","2020-03-31",9),("2020-01-01","2020-06-30",18),
     ("2020-01-01","2020-09-30",27),("2020-01-01","2020-12-31",40),("2021-01-01","2021-03-31",12))


def adapt(bundle):
    result=adapt_company(BundleSources(bundle),request())
    assert "book_equity_beginning" not in (result.company.facts if result.company else {})
    assert "book_equity_beginning" not in result.provenance.get("facts_available",[])
    return result,result.provenance["beginning_book_observation"]


def test_direct_consumed_chain_observes_exact_candidate_without_supplying_a_fact():
    result,opening=adapt(bundle_with_income(DIRECT));window=opening["window"]
    assert result.company.get("net_income_ttm")==18 and result.company.get("book_equity")==90
    assert window["status"]=="boundary_determinable" and window["required_opening_date"]=="2020-03-31"
    assert window["unique_support"] and window["exact_continuity"]
    assert len(window["selected_quarters_newest_first"])==4 and window["join_gap_days"]==[0,0,0]
    assert opening["candidate"]["value"]==80 and opening["candidate"]["period_end"]=="2020-03-31"
    assert not opening["model_fact_emitted"] and not opening["used_in_computation"]
    assert opening["reason"]=="opening_scope_class_basis_comparability_unattested"
    assert result.company.facts["net_income_ttm"].evidence.payload_sha256==canonical_hash(result.provenance["fact_derivations"]["net_income_ttm"])


@pytest.mark.parametrize("route",["opening_equity","old_unused_income"])
def test_invalid_local_capture_metadata_in_new_observations_preserves_durable_computation_and_denominators(tmp_path,route):
    bundle=bundle_with_income(DIRECT,opening=None)
    row=(fact("us-gaap:StockholdersEquity",80,end=date(2020,3,31)) if route=="opening_equity" else
         fact("us-gaap:NetIncomeLoss",7,start=date(2010,1,1),end=date(2010,3,31)))
    row["first_seen_at"]="bad";assert row["row_hash"]==vintage_row_hash(row)
    bundle["facts"].append(row);store=FileReceiptStore(tmp_path/"receipts")
    result=run_shadow_cross_section(BundleSources(bundle),(request(),replace(request(),symbol="MISSING")),premises(),store,reader_kind="offline_export")
    saved=store.read(result["run_key"])
    assert saved["input_inventory"]["requested_companies"]==2
    assert all(cell["requested"]==2 and cell["admissible"]==0 for cell in saved["input_inventory"]["models"].values())
    company=next(store.read(ref["run_key"]) for ref in saved["company_receipts"] if ref["symbol"]=="XYZ")
    assert company["computation"]["inputs"]["facts"]["net_income_ttm"]["value"]==18
    assert company["computation"]["inputs"]["facts"]["book_equity"]["value"]==90
    observation=company["adaptation"]["beginning_book_observation"]
    expected=("opening_equity_local_capture_metadata_invalid" if route=="opening_equity" else "ni_support_local_capture_metadata_invalid")
    assert observation["reason"]==expected and observation["candidate"] is None
    refusals=observation.get("metadata_refusals") or observation["window"]["metadata_refusals"]
    assert refusals[0]["captured_at"] is None and refusals[0]["capture_metadata_status"]=="invalid"
    assert refusals[0]["capture_metadata_reason"]=="unattested_local_capture_instant"
    if route=="old_unused_income":
        assert not observation["window"]["support_inventory_complete"] and not observation["window"]["unique_support"]
        assert observation["window"]["required_opening_date"] is None
    metric=saved["input_inventory"]["models"]["residual_income"]
    assert metric["beginning_book_observation_reasons"][expected]==1 and metric["beginning_book_facts_consumed"]==0
    assert "book_equity_beginning" not in company["computation"]["inputs"]["facts"]


@pytest.mark.parametrize("consumed",["income","latest_book"])
def test_existing_strict_capture_metadata_validation_for_consumed_facts_is_unchanged(consumed):
    bundle=bundle_with_income(DIRECT)
    row=next(row for row in bundle["facts"] if row["concept"]==("us-gaap:NetIncomeLoss" if consumed=="income" else "us-gaap:StockholdersEquity")
        and row["period_end"]==date(2021,3,31))
    row["first_seen_at"]="bad";assert row["row_hash"]==vintage_row_hash(row)
    with pytest.raises(NotEvaluable,match="unattested_instant"):adapt_company(BundleSources(bundle),request())


def test_local_metadata_refusal_never_masks_a_later_persistence_failure(tmp_path,monkeypatch):
    bundle=bundle_with_income(DIRECT)
    row=next(row for row in bundle["facts"] if row["concept"]=="us-gaap:StockholdersEquity" and row["period_end"]==date(2020,3,31))
    row["first_seen_at"]="bad"
    store=FileReceiptStore(tmp_path/"receipts")
    def disk_failure(receipt):raise OSError("synthetic_disk_failure")
    monkeypatch.setattr(store,"put",disk_failure)
    with pytest.raises(OSError,match="synthetic_disk_failure"):
        run_shadow_cross_section(BundleSources(bundle),(request(),),premises(),store,reader_kind="offline_export")


def test_ytd_telescoping_keeps_signed_and_cancelled_terms_in_the_actual_window():
    result,opening=adapt(bundle_with_income(YTD));window=opening["window"]
    assert result.company.get("net_income_ttm")==43
    assert window["selected_window_start"]=="2020-04-01" and window["selected_window_end"]=="2021-03-31"
    assert window["required_opening_date"]=="2020-03-31"
    terms=window["combined_raw_terms_including_cancellations"]
    assert len(terms)==5 and sum(x["coefficient"]==0 for x in terms)==2
    assert min(x["row"]["period_start"] for x in terms)=="2020-01-01" # Not the window start.
    assert any(t["coefficient"]==-1 for q in window["selected_quarters_newest_first"] for t in q["terms"])
    for q in window["selected_quarters_newest_first"]:
        if q["derived"]:
            assert [t["coefficient"] for t in q["terms"]]==[1,-1]
            assert date.fromisoformat(q["period_start"])==date.fromisoformat(q["terms"][1]["row"]["period_end"])+timedelta(days=1)


def test_fy_minus_nine_months_as_oldest_quarter_uses_its_effective_start():
    spans=(("2019-01-01","2019-09-30",27),("2019-01-01","2019-12-31",40),
           ("2020-01-01","2020-03-31",12),("2020-04-01","2020-06-30",14),("2020-07-01","2020-09-30",16))
    result,opening=adapt(bundle_with_income(spans,opening="2019-09-30"));window=opening["window"]
    assert result.company.get("net_income_ttm")==55
    assert window["selected_window_start"]=="2019-10-01" and window["required_opening_date"]=="2019-09-30"
    assert window["selected_quarters_newest_first"][-1]["derived"]


@pytest.mark.parametrize("last_end",["2020-09-26","2020-10-03"])
def test_actual_noncalendar_52_or53_week_dates_do_not_use_365_day_subtraction(last_end):
    spans=(("2019-09-29","2019-12-28",3),("2019-12-29","2020-03-28",4),
           ("2020-03-29","2020-06-27",5),("2020-06-28",last_end,6))
    result,opening=adapt(bundle_with_income(spans,opening="2019-09-28"))
    assert result.company.get("net_income_ttm")==18
    assert opening["window"]["required_opening_date"]=="2019-09-28"
    assert opening["window"]["fiscal_period_authority"]=="not_established_by_duration_heuristics"


@pytest.mark.parametrize("start,gap",[("2020-07-02",1),("2020-06-30",-1)])
def test_tolerance_admitted_gap_or_overlap_is_observed_without_changing_income(start,gap):
    spans=list(DIRECT);spans[1]=(start,spans[1][1],spans[1][2])
    result,opening=adapt(bundle_with_income(spans));window=opening["window"]
    assert result.company.get("net_income_ttm")==18
    assert window["reason"]=="ni_selected_quarters_gap_or_overlap" and gap in window["join_gap_days"]
    assert window["required_opening_date"] is None and opening["candidate"] is None


def test_reported_quarter_does_not_hide_an_equivalent_derived_support_path():
    result,opening=adapt(bundle_with_income((*YTD,("2020-04-01","2020-06-30",9))))
    window=opening["window"]
    assert result.company.get("net_income_ttm")==43
    assert window["reason"]=="ni_support_ambiguous" and window["support_path_count_lower_bound"]==2
    assert not window["unique_support"] and opening["candidate"] is None


def test_distinct_oldest_starts_cannot_be_chosen_based_on_where_equity_exists():
    result,opening=adapt(bundle_with_income((*DIRECT,("2020-03-31","2020-06-30",3))))
    window=opening["window"]
    assert result.company.get("net_income_ttm")==18 and window["reason"]=="ni_support_ambiguous"
    starts={path[-1]["period_start"] for path in window["alternative_exact_paths"]}
    assert starts=={"2020-03-31","2020-04-01"} and window["required_opening_date"] is None


def test_hidden_nine_month_prefix_derivations_are_checked_even_when_helper_keeps_one():
    spans=(("2019-01-01","2019-09-30",27),("2019-01-01","2019-10-01",27),("2019-01-01","2019-12-31",40),
        ("2019-07-01","2019-09-30",9),("2019-07-01","2019-10-01",9),
        ("2020-01-01","2020-03-31",12),("2020-04-01","2020-06-30",14))
    result,opening=adapt(bundle_with_income(spans,opening="2019-06-30"))
    assert result.company.get("net_income_ttm")==48 and opening["window"]["reason"]=="ni_support_ambiguous"


def test_engineering_support_bound_is_unassessed_instead_of_assuming_uniqueness():
    start=date(2019,1,1);spans=list(DIRECT)
    for low,high in ((80,100),(170,195),(260,285),(350,380)):
        spans.extend((start.isoformat(),(start+timedelta(days=days)).isoformat(),1) for days in range(low,high+1))
    for ordering in (spans,list(reversed(spans))):
        result,opening=adapt(bundle_with_income(ordering));window=opening["window"]
        assert result.company.get("net_income_ttm")==18
        assert window["reason"]=="ni_support_inventory_bound" and not window["support_inventory_complete"]
        assert not window["unique_support"] and window["required_opening_date"] is None and opening["candidate"] is None


@pytest.mark.parametrize("spans",[(("2020-01-01","2020-12-31",40),),
    (("2020-01-01","2020-03-31",9),("2020-01-01","2020-12-31",40),("2021-01-01","2021-03-31",12))])
def test_fy_or_three_totals_do_not_create_a_new_ttm_closure(spans):
    result,opening=adapt(bundle_with_income(spans))
    assert "net_income_ttm" not in result.company.facts and opening["reason"]=="net_income_ttm_unavailable"
    assert opening["candidate"] is None


@pytest.mark.parametrize("opening_date",[None,"2020-03-30","2020-04-01"])
def test_ending_or_nearby_equity_is_not_an_opening_candidate(opening_date):
    _,opening=adapt(bundle_with_income(DIRECT,opening=opening_date))
    assert opening["window"]["required_opening_date"]=="2020-03-31"
    assert opening["candidate"] is None and opening["reason"]=="exact_opening_equity_row_missing"


def test_future_and_duplicate_latest_opening_rows_do_not_supply_candidates():
    bundle=bundle_with_income(DIRECT,opening=None);future=T+timedelta(days=1)
    bundle["filings"].append(filing("future",accepted=future))
    bundle["facts"].append(fact("us-gaap:StockholdersEquity",80,end=date(2020,3,31),doc="future",accepted=future))
    _,opening=adapt(bundle)
    assert opening["candidate"] is None and opening["reason"]=="exact_opening_equity_row_missing"
    duplicate=bundle_with_income(DIRECT)
    duplicate["facts"].append(fact("us-gaap:StockholdersEquity",81,end=date(2020,3,31)))
    _,opening=adapt(duplicate)
    assert opening["candidate"] is None and opening["reason"]=="opening_equity_ineligible_or_ambiguous"


@pytest.mark.parametrize("change",[{"unit":"EUR"},{"issuer":"someone-else"}])
def test_opening_row_still_requires_existing_currency_and_issuer_checks(change):
    bundle=bundle_with_income(DIRECT,opening=None)
    bundle["facts"].append(fact("us-gaap:StockholdersEquity",80,end=date(2020,3,31),**change))
    _,opening=adapt(bundle)
    assert opening["candidate"] is None


def test_scope_flags_cannot_promote_an_observed_candidate_to_a_model_fact():
    bundle=bundle_with_income(DIRECT)
    bundle["scope_comparable"]=bundle["class_basis_proven"]=True
    for row in bundle["facts"]:row["scope_class_basis_proven"]=True
    result,opening=adapt(bundle)
    assert opening["candidate"]["value"]==80 and opening["scope_class_basis_comparability"]=="unattested"
    assert "book_equity_beginning" not in result.company.facts


def test_candidate_survives_late_price_refusal_but_is_never_available_as_required_fact(tmp_path):
    bundle=bundle_with_income(DIRECT);bundle["price_series"]["NASDAQ:XYZ"]={"status":"no_vintage"}
    store=FileReceiptStore(tmp_path/"receipts")
    result=run_shadow_cross_section(BundleSources(bundle),(request(),replace(request(),symbol="MISSING")),premises(),store,reader_kind="offline_export")
    saved=store.read(result["run_key"]);metric=saved["input_inventory"]["models"]["residual_income"]
    assert metric["requested"]==2 and metric["opening_boundaries_determinable"]==metric["exact_date_candidates_observed"]==1
    assert metric["beginning_book_facts_consumed"]==0 and metric["computable"]==metric["admissible"]==0
    company=next(store.read(x["run_key"]) for x in saved["company_receipts"] if x["symbol"]=="XYZ")
    cell=company["input_audit"]["models"]["residual_income"]
    assert cell["required_facts"]["net_income_ttm"]["status"]=="available"
    assert cell["required_facts"]["book_equity_beginning"]["status"]=="missing_or_ineligible"
    assert cell["beginning_book_observation"]["candidate_does_not_supply_required_fact"]


def test_original_and_capture_links_distinguish_observed_candidate_from_consumed_income_without_reread(tmp_path):
    bundle,package,target=sec_case();header_item,instance_item=package.items
    extras=''.join(f'<us-gaap:NetIncomeLoss contextRef="q{i}" unitRef="USD" decimals="0">{3+i}</us-gaap:NetIncomeLoss>' for i in range(3))
    for name,instant,value in (("opening","2020-03-31",80),("closing","2021-03-31",90)):
        extras+=(f'<xbrli:context id="{name}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000999001</xbrli:identifier></xbrli:entity>'
            f'<xbrli:period><xbrli:instant>{instant}</xbrli:instant></xbrli:period></xbrli:context>'
            f'<us-gaap:StockholdersEquity contextRef="{name}" unitRef="USD" decimals="0">{value}</us-gaap:StockholdersEquity>')
    raw=artifact("sec_xbrl_instance",instance_item.artifact.source_url,instance_item.artifact.payload.replace(b'</xbrli:xbrl>',extras.encode()+b'</xbrli:xbrl>'))
    extracted=extract_sec_instance(raw,header_item.artifact);rows=[]
    for value in extracted["facts"]:
        if not value["numeric"] or value["context"]["dimensions"]:continue
        row={"market":"US","issuer_key":extracted["issuer_key"],"doc_id":extracted["doc_id"],"document_version":1,
            "source":"sec_xbrl_companyfacts","form":extracted["form"],"filed_date":extracted["filed_date"],"accepted_at":extracted["accepted_at"],
            "concept":value["concept"],"unit":value["unit"],"value":Decimal(value["value"]),
            "period_start":value["context"]["period_start"],"period_end":value["context"]["period_end"]}
        row["row_hash"]=vintage_row_hash(row);rows.append(row)
    bundle["facts"]=rows;captures=OriginalEvidenceStore(tmp_path/"captures");clock=Clock()
    originals=(header_item,replace(instance_item,artifact=raw))
    client=OfficialCaptureClient(Transport([Response(x.artifact.payload) for x in originals],clock),
        limits(max_response_bytes=32768,max_total_body_bytes=65536),user_agent=CONTACT,clock=clock)
    items=[]
    for item in originals:
        captured=client.capture(CaptureRequest(item.artifact.kind,item.artifact.source_url),captures)
        record=read_capture_receipt(captures,captured["run_key"])
        items.append(replace(item,artifact=replace(item.artifact,captured_at=datetime.fromisoformat(record["body_received_at"])),
            capture=CaptureReference(captured["run_key"],captured["payload_sha256"])))
    class ChangingSources(BundleSources):
        calls=0
        def facts(self,*args):self.calls+=1;return super().facts(*args)
        def price_series(self,*args):
            for row in self.bundle["facts"]:row["value"]=Decimal(999)
            return super().price_series(*args)
    sources=ChangingSources(bundle);store=FileReceiptStore(tmp_path/"receipts");sink=OriginalEvidenceStore(tmp_path/"originals")
    result=run_shadow_cross_section(sources,(target,replace(target,symbol="MISSING")),premises(),store,reader_kind="offline_export",
        original_package=OriginalPackage(tuple(items)),original_store=sink,capture_store=captures)
    saved=store.read(result["run_key"]);company=next(store.read(x["run_key"]) for x in saved["company_receipts"] if x["symbol"]=="XYZ")
    assert sources.calls==1 and company["computation"]["inputs"]["facts"]["net_income_ttm"]["value"]==30
    reconciliation=company["original_reconciliation"];opening=reconciliation["beginning_book_observation"]
    candidate=next(x for x in reconciliation["row_ledger"] if x["observed_for"])
    assert candidate["canonical_row"]["value"]=="80" and candidate["used_by_fields"]==[]
    assert candidate["original"]["checked_content_equal"] and candidate["original"]["capture_linked_content_equal"]
    assert opening["candidate_row_references"] and opening["candidate_document_references"]
    assert opening["net_income_ttm_dependencies"]["all_capture_links_verified"]
    assert "book_equity_beginning" not in reconciliation["fields"]
    metric=saved["input_inventory"]["models"]["residual_income"]
    assert metric["requested"]==2 and metric["exact_date_candidates_observed"]==1 and metric["beginning_book_facts_consumed"]==0
    assert metric["all_required_capture_links_verified"]==0 and metric["admissible"]==0
