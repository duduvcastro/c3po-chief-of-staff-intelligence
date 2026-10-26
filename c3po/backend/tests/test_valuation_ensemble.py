from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from itertools import permutations
import math

import pytest

from app.valuation_ensemble_aggregation import PRIMARY_VARIANT, aggregate_variants
from app.valuation_ensemble_inputs import (
    AnalystTarget, CompanyInputs, Evidence, NotEvaluable, OfficialFact, Premises, Price,
    analyst_consensus, canonical_hash,
)
from app.valuation_ensemble_models import MODEL_IDS, ModelValue, evaluate_models
from app.valuation_ensemble_shadow import build_shadow_receipt


T = datetime(2021, 7, 1, 4, tzinfo=timezone.utc)
H = "a" * 64


def evidence(source="SEC", *, at=T-timedelta(days=1), doc="filing"):
    return Evidence(source, doc, at, H)


def company(symbol="TARGET", *, price=10.0, market="NASDAQ", **updates):
    source = "CVM" if market == "B3" else "SEC"
    currency = "BRL" if market == "B3" else "USD"
    values = dict(shares=10, operating_income_ttm=20, net_income_ttm=15, d_and_a_ttm=2,
                  operating_cash_flow_ttm=18, capex_ttm=4, change_working_capital_ttm=1,
                  net_borrowing_ttm=2, dividends_ttm=5, book_equity_beginning=80,
                  book_equity=90, debt=30, cash=10, normalized_operating_income=20,
                  maintenance_capex=2, revenue_ttm=100, current_assets=100, total_liabilities=40,
                  goodwill=10, intangible_assets_excluding_goodwill=5)
    values.update(updates)
    facts = {name: OfficialFact(value, "shares" if name == "shares" else currency,
                               date(2021, 3, 31), evidence(source)) for name, value in values.items()}
    return CompanyInputs(symbol, market, currency, T, "common-as-traded",
                         Price(price, currency, date(2021, 6, 30), "common-as-traded", evidence("PRICE")),
                         facts, "industrial", evidence(source), issuer_id=f"issuer:{symbol}")


def premises(**updates):
    values = dict(cost_of_equity=0.10, wacc=0.10, terminal_growth=0.0, tax_rate=0.25)
    values.update(updates)
    return Premises("construction-fixture-v1", values, (0.0, 0.0))


def results(c=None, p=None, peers=()):
    return {x.model: x for x in evaluate_models(c or company(), p or premises(), peers=peers)}


def targets():
    return (AnalystTarget("house A", 12, "USD", 252, evidence("ANALYST_CONSENSUS", doc="targetA")),
            AnalystTarget("house B", 18, "USD", 252, evidence("ANALYST_CONSENSUS", doc="targetB")))


def test_named_roster_and_cash_flow_discount_bases_have_analytic_witnesses():
    r = results()
    assert tuple(r) == MODEL_IDS
    assert len(r) == 16
    # FCFF=20*.75+2-4-1=12; EV=120, less net debt20, shares10 =>10.
    assert r["dcf_fcff"].value == pytest.approx(10)
    # FCFE=18-4+2=16; equityPV160, no second debt deduction =>16.
    assert r["dcf_fcfe"].value == pytest.approx(16)
    assert r["ddm_gordon"].value == pytest.approx(5)
    assert r["ddm_multistage"].value == pytest.approx(5)
    # RI=15-.1*80=7; book80+PV70, shares10 =>15.
    assert r["residual_income"].value == pytest.approx(15)
    assert r["earnings_power"].value == pytest.approx(13)
    assert r["capitalized_operating_cash_flow"].value == pytest.approx(18)
    assert r["ncav"].value == pytest.approx(6)
    assert r["tangible_book"].value == pytest.approx(7.5)


def test_fcff_uses_wacc_and_fcfe_uses_cost_of_equity_only():
    baseline = results()
    changed_ke = results(p=premises(cost_of_equity=.2))
    changed_wacc = results(p=premises(wacc=.2))
    assert changed_ke["dcf_fcff"] == baseline["dcf_fcff"]
    assert changed_wacc["dcf_fcfe"] == baseline["dcf_fcfe"]
    assert changed_ke["dcf_fcfe"].value < baseline["dcf_fcfe"].value
    assert changed_wacc["dcf_fcff"].value < baseline["dcf_fcff"].value


def test_missing_or_invalid_premises_never_receive_synthetic_default_values():
    r = results(p=Premises("explicit-empty"))
    assert r["dcf_fcff"].value is None
    assert r["dcf_fcfe"].reason == "missing_premise:cost_of_equity"
    assert results(p=premises(wacc=.01, terminal_growth=.02))["dcf_fcff"].reason == "discount_rate_not_above_terminal_growth"
    assert results(p=premises(tax_rate=1.1))["dcf_fcff"].reason == "tax_rate_out_of_range"
    assert results(p=replace(premises(), annual_growth_path=()))["dcf_fcff"].reason == "missing_explicit_growth_path"


@pytest.mark.parametrize("field,change,reason", [
    ("net_income_ttm", {"evidence": evidence(at=T+timedelta(microseconds=1))}, "available_after_T"),
    ("net_income_ttm", {"evidence": evidence("PROVIDER_CURRENT")}, "source_not_allowed"),
    ("net_income_ttm", {"period_end": date(2022, 1, 1)}, "period_after_T"),
    ("net_income_ttm", {"unit": "BRL"}, "unit_mismatch"),
    ("net_income_ttm", {"value": math.nan}, "invalid_number"),
    ("net_income_ttm", {"value": True}, "invalid_number"),
])
def test_future_wrong_source_unit_or_nonfinite_fact_cannot_enter_a_model(field, change, reason):
    c = company()
    facts = {**c.facts, field: replace(c.facts[field], **change)}
    r = results(replace(c, facts=facts))
    assert r["residual_income"].status == "not_evaluable"
    assert reason in r["residual_income"].reason
    assert r["ncav"].value == pytest.approx(6)  # unrelated eligible official facts still work


def test_missing_fact_has_explicit_reason_and_no_fake_numeric_value():
    c = company()
    c = replace(c, facts={k:v for k,v in c.facts.items() if k != "goodwill"})
    assert results(c)["tangible_book"] == ModelValue("tangible_book", None, "not_evaluable", "missing_fact:goodwill")
    assert results(company(current_assets=1))["ncav"].reason == "model_value_not_positive"


def test_b3_reads_only_cvm_facts_and_financial_companies_do_not_get_enterprise_models():
    assert results(company(market="B3"))["dcf_fcfe"].value == pytest.approx(16)
    c = company(market="B3")
    c = replace(c, facts={**c.facts, "shares": replace(c.facts["shares"], evidence=evidence("SEC"))})
    assert "source_not_allowed:SEC" in results(c)["dcf_fcfe"].reason
    r = results(replace(company(), financial_company=True))
    assert r["dcf_fcff"].reason == "enterprise_model_not_applicable_to_financial_company"
    assert r["dcf_fcfe"].status == "evaluated"


@pytest.mark.parametrize("change,reason", [
    ({"as_of": T.replace(tzinfo=None)}, "instant_without_timezone"),
    ({"price": Price(10, "USD", date(2021, 6, 30), "split-adjusted", evidence("PRICE"))}, "price_currency_or_share_basis_mismatch"),
    ({"price": Price(10, "USD", date(2022, 1, 1), "common-as-traded", evidence("PRICE"))}, "invalid_or_future_price"),
    ({"price": Price(10, "USD", date(2021, 6, 30), "common-as-traded", evidence("PRICE", at=T+timedelta(seconds=1)))}, "available_after_T"),
])
def test_invalid_packet_price_or_clock_refuses_entire_company(change, reason):
    with pytest.raises(NotEvaluable, match=reason):
        evaluate_models(replace(company(), **change), premises())


def test_peer_multiples_use_cross_section_at_T_and_exclude_the_target():
    peers = tuple(company(f"PEER{i}", price=20) for i in range(3))
    r = results(peers=peers+(company(price=100000),))
    for model in ("pe", "ev_ebitda", "ev_ebit", "ev_sales", "price_book", "price_operating_cash_flow"):
        assert r[model].value == pytest.approx(20)
    # Later facts, different economic cut, currency/sector mismatch cannot provide a peer.
    future = replace(peers[0], as_of=T+timedelta(seconds=1))
    assert results(peers=(future,*peers[1:]))["pe"].reason == "eligible_sector_peers_below_minimum"
    future_fact = replace(peers[0], facts={**peers[0].facts, "net_income_ttm":
                                         replace(peers[0].facts["net_income_ttm"], evidence=evidence(at=T+timedelta(days=1)))})
    assert results(peers=(future_fact,*peers[1:]))["pe"].reason == "eligible_multiple_peers_below_minimum"
    assert results(peers=(peers[0], peers[0], peers[1], peers[2]))["pe"].reason == "duplicate_peer_identity"


def test_sector_regression_fits_only_t_cross_section_and_refuses_extrapolation():
    # Exact ln(EV/sales)=1+2*margin, giving a known independent interpolation witness.
    peers = []
    for i, margin in enumerate((.1,.2,.3)):
        enterprise = math.exp(1+2*margin)*100
        peers.append(company(f"REG{i}", price=(enterprise-20)/10, operating_income_ttm=margin*100))
    r = results(peers=tuple(peers))
    expected = (math.exp(1.4)*100-20)/10
    assert r["sector_regression"].value == pytest.approx(expected)
    assert results(company(operating_income_ttm=50), peers=tuple(peers))["sector_regression"].reason == "sector_regression_extrapolation"
    assert results(peers=tuple(company(f"S{i}") for i in range(3)))["sector_regression"].reason == "sector_regression_singular"


def test_consensus_is_arithmetic_mean_of_latest_per_house_and_not_an_anchor():
    old = replace(targets()[0], target=100, evidence=evidence("ANALYST_CONSENSUS", at=T-timedelta(days=5)))
    outlier = AnalystTarget("house C", 60, "USD", 252, evidence("ANALYST_CONSENSUS", doc="targetC"))
    value, receipt = analyst_consensus((*targets(),old,outlier), company())
    assert value == pytest.approx(30)  # median would be18; duplicate house is not a third vote
    assert receipt["eligible_houses"] == 3
    models = tuple(ModelValue(str(i), x, "evaluated") for i,x in enumerate((8,10,12)))
    variants = aggregate_variants(models, value)
    assert variants["variants"]["median_with_consensus"]["value"] == 11
    assert variants["variants"]["median_without_consensus"]["value"] == 10


@pytest.mark.parametrize("bad,reason", [
    (replace(targets()[0], horizon_sessions=0), "horizon_unattested"),
    (replace(targets()[0], currency="BRL"), "house_or_currency_mismatch"),
    (replace(targets()[0], evidence=evidence("ANALYST_CONSENSUS", at=T+timedelta(seconds=1))), "available_after_T"),
    (replace(targets()[0], evidence=replace(evidence("ANALYST_CONSENSUS"), payload_sha256="unknown")), "missing_document_or_hash"),
])
def test_unattested_or_future_consensus_is_absent(bad, reason):
    value, receipt = analyst_consensus((bad,), company())
    assert value is None
    assert receipt["status"] == "not_evaluable"
    assert receipt["refused"][reason] == 1


def test_consensus_horizons_and_equal_clock_conflicts_fail_closed():
    assert analyst_consensus((targets()[0],replace(targets()[1],horizon_sessions=126)), company())[0] is None
    for items in permutations((targets()[0], replace(targets()[0],target=99), targets()[1])):
        assert analyst_consensus(items, company())[0] is None


def test_all_six_aggregations_and_explicit_twenty_percent_tail_policy():
    models = tuple(ModelValue(str(i), x, "evaluated") for i,x in enumerate((1,2,3,4,100)))
    r = aggregate_variants(models, 200)
    assert r["primary"] == PRIMARY_VARIANT == "median_with_consensus"
    assert len(r["variants"]) == 6
    assert r["variants"]["mean_without_consensus"]["value"] == 22
    assert r["variants"]["median_without_consensus"]["value"] == 3
    assert r["variants"]["trimmed_mean_20_without_consensus"]["value"] == 3
    assert r["variants"]["trimmed_mean_20_with_consensus"]["value"] == pytest.approx(27.25)
    assert r["variants"]["median_with_consensus"]["value"] == 3.5
    assert r["variants"]["trimmed_mean_20_with_consensus"]["trimmed_each_tail"] == 1


def test_absent_consensus_or_models_is_not_silently_a_different_primary():
    models = (ModelValue("one", 10, "evaluated"),ModelValue("two", None, "not_evaluable", "missing_fact"))
    r = aggregate_variants(models, None)
    assert r["variants"][PRIMARY_VARIANT]["value"] is None
    assert r["variants"][PRIMARY_VARIANT]["reason"] == "consensus_unavailable"
    assert r["variants"]["median_without_consensus"]["value"] == 10
    assert aggregate_variants((), 10)["variants"][PRIMARY_VARIANT]["reason"] == "no_fundamental_model"
    with pytest.raises(NotEvaluable, match="duplicate_model"):
        aggregate_variants((models[0],models[0]), 10)


def test_shadow_receipt_is_deterministic_carries_premises_and_cannot_promote_or_choose_horizon():
    first = build_shadow_receipt(company(), premises(), analyst_targets=targets())
    second = build_shadow_receipt(company(), premises(), analyst_targets=tuple(reversed(targets())))
    assert first == second
    assert first["payload_sha256"] == canonical_hash({k:v for k,v in first.items() if k != "payload_sha256"})
    assert first["source"] == "valuation_ensemble_shadow_v1"
    assert first["diagnostic_only"] and not first["served_source_changed"] and not first["buy_permission"]
    assert not first["signed_prereg"] and first["horizon_sessions"] is None
    assert first["premises"]["kind"] == "explicit_design_premises_not_market_observations"
    assert first["inputs"]["facts"]["net_income_ttm"]["evidence"]["source"] == "SEC"
    assert first["consensus"]["horizon_sessions"] == 252  # source horizon, NOT the decisory horizon


def test_price_session_uses_the_market_date_not_the_following_utc_date():
    # At00:30UTC it is still the previous civil day in both authorized markets.
    c = company()
    c = replace(c, as_of=datetime(2021,7,1,0,30,tzinfo=timezone.utc),
                price=replace(c.price, session_date=date(2021,7,1)))
    with pytest.raises(NotEvaluable, match="invalid_or_future_price"):
        evaluate_models(c, premises())


def test_cross_listings_and_classes_do_not_supply_extra_peer_votes_or_self_value():
    peers = tuple(company(f"PEER{i}", price=20) for i in range(3))
    other_class = replace(peers[0], symbol="OTHER_CLASS")
    assert results(peers=(*peers,other_class))["pe"].reason == "duplicate_peer_identity"
    self_class = replace(company(price=100000), symbol="TARGET_B")
    assert results(peers=(*peers,self_class))["pe"].value == pytest.approx(20)


def test_finite_large_values_do_not_overflow_while_averaging_or_taking_even_median():
    large = tuple(ModelValue(str(i), 1e308, "evaluated") for i in range(4))
    variants = aggregate_variants(large, 1e308)["variants"]
    assert all(x["value"] == 1e308 for x in variants.values())
    ts = tuple(replace(x,target=1e308) for x in targets())
    assert analyst_consensus(ts, company())[0] == 1e308


def test_house_name_case_and_spaces_cannot_create_multiple_votes():
    same = replace(targets()[0], house=" HOUSE A ", target=99,
                   evidence=evidence("ANALYST_CONSENSUS", at=T-timedelta(days=2)))
    value, receipt = analyst_consensus((*targets(),same),company())
    assert value == 15
    assert receipt["eligible_houses"] == 2


def test_equivalent_house_spelling_does_not_make_receipt_order_dependent():
    alias = replace(targets()[0],house=" HOUSE A ")
    receipts = [analyst_consensus(items,company()) for items in permutations((*targets(),alias))]
    assert all(item == receipts[0] for item in receipts)


def test_malformed_nonfinite_packet_refuses_receipt_instead_of_serializing_nan():
    c = company()
    c = replace(c, facts={**c.facts,"net_income_ttm":replace(c.facts["net_income_ttm"],value=math.inf)})
    with pytest.raises(NotEvaluable,match="non_serializable_input_packet"):
        build_shadow_receipt(c,premises())
