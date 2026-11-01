import copy
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access_control import required_permissions
from app.listed_universe import (
    CATALOGUE_ANALYSIS, Catalogue, Listing, buy_scope_allows,
    catalogue_from_payload, digest, parse_b3_titulos, parse_nasdaq_directory,
    read_universe, universe_response,
)
from app.listed_universe_api import listed_universe_router
from app.listed_universe_capture import decode_directory, main, record_catalogue

NOW = datetime(2026, 10, 26, 3, tzinfo=timezone.utc)


def nasdaq(rows, *, market="NASDAQ", footer=True):
    header = ("Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
              if market == "NASDAQ" else "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol")
    text = header + "\n" + "\n".join(rows) + "\n"
    if footer:
        text += "File Creation Time: 1023202621:00|||||||\n"
    return text.encode()


def b3_file(securities, *, missing_company=False):
    header = "00" + "TITULOS NEGOCIAVEIS".ljust(28) + "2026-10-23" + " " * 180
    company = "01ABCD" + "EMPRESA DE TESTE".ljust(60) + "EMPRESA".ljust(12) + " " * 142
    records = [header] + ([] if missing_company else [company])
    for symbol, spec, market in securities:
        row = [" "] * 220
        for start, end, value in [(0, 2, "02"), (2, 14, symbol), (14, 18, "ABCD"),
                                  (18, 21, "002"), (21, 81, "LOTE PADRAO"),
                                  (81, 93, "BRABCDACNOR1"), (108, 111, market), (133, 143, spec)]:
            row[start:end] = list(value.ljust(end - start))
        records.append("".join(row))
    records.append("09" + str(len(records) + 1).zfill(7) + " " * 211)
    return "\r\n".join(records).encode("latin-1") + b"\r\n"


def canonical(symbol="CHEAP", *, verdict="COMPRA_PERMITIDA"):
    return {"symbol": symbol, "our_tp": 10.0, "price": 0.5, "market_cap": 100.0,
            "cash_volume": 20.0, "buy_in": 8.0, "tp_source": "official_internal_v1",
            "tp_source_version": "32", "official_generation_id": "generation-1",
            "official_row_sha256": "a" * 64, "decisor_verdict": verdict}


def scope(*, members=None, verdict="PASS"):
    entries = ["CHEAP"] if members is None else members
    return {"schema": "PIT-BUY-POPULATION-v1", "market": "NASDAQ", "verdict": verdict,
            "approved_for_buy": True, "receipt_sha256": "a" * 64, "prereg_sha256": "b" * 64,
            "tp_source_version": "32", "valid_from": (NOW - timedelta(days=1)).isoformat(),
            "valid_until": (NOW + timedelta(days=1)).isoformat(),
            "members": entries, "population_sha256": digest(sorted(entries))}


def catalogue(listings):
    return Catalogue("NASDAQ", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                     "nasdaq-trader-pipe-v1", NOW.isoformat(), "2026-10-23T21:00:00-04:00", "f" * 64,
                     len(listings), {}, tuple(listings))


def test_full_official_inventory_has_no_300_cap_and_keeps_incomplete_names():
    rows = [f"S{i:04}|Company {i}|Q|N|N|100|N|N" for i in range(701)]
    source = parse_nasdaq_directory(nasdaq(rows), market="NASDAQ", received_at=NOW)
    response = universe_response(source, {}, now=NOW)
    assert response["quantity_limit"] is None
    assert response["universe_size"] == response["item_count"] == 701
    assert response["not_evaluable_count"] == 701
    assert {item["symbol"] for item in response["items"]} == {f"S{i:04}" for i in range(701)}
    assert all(item["our_tp"] is None and item["price"] is None for item in response["items"])
    assert all("canonical_valuation_missing" in item["not_evaluable_reasons"] for item in response["items"])


def test_minimum_failures_are_badges_and_do_not_remove_or_replace_the_canonical_tp():
    source = catalogue([Listing("NASDAQ", "CHEAP", "Low price company")])
    row = canonical()
    before = copy.deepcopy(row)
    result = universe_response(source, {"CHEAP": row}, population=scope(), now=NOW,
                               permissions={"CHEAP": {"buy_permission": True, "pit_artifacts_attested": True}})["items"][0]
    assert result["valuation_status"] == "valued"
    assert result["our_tp"] == 10.0
    assert all(badge["status"] == "below_minimum" for badge in result["minimum_badges"].values())
    assert result["buy_permission"] is True  # badge minima do not substitute the decisor or its PIT scope
    assert row == before


@pytest.mark.parametrize("evidence", [None, {}, scope(members=[]), scope(verdict="FAIL"), scope(verdict="VOID")])
def test_existing_permission_cannot_escape_the_verified_pit_population(evidence):
    item = universe_response(catalogue([Listing("NASDAQ", "CHEAP", "Company")]),
                             {"CHEAP": canonical()}, population=evidence, now=NOW)["items"][0]
    assert item["buy_permission"] is False
    assert item["buy_permission_reason"] == "pit_buy_scope_unverified"


@pytest.mark.parametrize("mutation", [
    {"market": "NYSE"}, {"tp_source_version": "33"}, {"approved_for_buy": False},
    {"valid_until": NOW.isoformat()}, {"valid_from": (NOW + timedelta(seconds=1)).isoformat()},
    {"population_sha256": "c" * 64}, {"members": "CHEAP"}, {"receipt_sha256": "not-a-digest"},
])
def test_scope_is_bound_to_market_version_time_and_population_digest(mutation):
    assert not buy_scope_allows(scope() | mutation, market="NASDAQ", symbol="CHEAP", tp_source_version="32", now=NOW)


def test_membership_cannot_turn_a_decisor_rejection_into_permission():
    item = universe_response(catalogue([Listing("NASDAQ", "CHEAP", "Company")]),
                             {"CHEAP": canonical(verdict="OBSERVAR")}, population=scope(), now=NOW)["items"][0]
    assert item["pit_population_member"] is True
    assert item["pit_buy_scope_verified"] is False
    assert item["buy_permission"] is False


def test_etfs_stay_on_existing_path_and_test_issues_and_other_exchanges_are_reconciled():
    raw = nasdaq(["A|Company|N|A|N|100|N|A", "ETF|Fund|N|ETF|Y|100|N|ETF",
                  "TEST|Test|N|TEST|N|100|Y|TEST", "ARCA|Other market|P|ARCA|N|100|N|ARCA"], market="NYSE")
    parsed = parse_nasdaq_directory(raw, market="NYSE", received_at=NOW)
    result = universe_response(parsed, {}, now=NOW)
    assert parsed.source_row_count == 4
    assert len(parsed.listings) + sum(parsed.excluded_counts.values()) == 4
    assert parsed.excluded_counts == {"test_issue": 1, "other_exchange": 1}
    assert result["etfs_on_existing_path"] == 1
    assert [item["symbol"] for item in result["items"]] == ["A"]


def test_real_equity_names_containing_bond_or_right_never_disappear():
    # Regression witnesses from the official files retrieved on26Oct. A company
    # name and the explanatory text of an ADS cannot be an exclusion predicate.
    raw = nasdaq(["OBAI|Our Bond, Inc. - Common Stock|Q|N|N|100|N|N"])
    cat = parse_nasdaq_directory(raw, market="NASDAQ", received_at=NOW)
    assert [item["symbol"] for item in universe_response(cat, {}, now=NOW)["items"]] == ["OBAI"]
    assert cat.listings[0].listing_class == "equity"
    raw_nyse = nasdaq(["WDH|Waterdrop Inc. American Depositary Shares (each representing the right to receive 10 Class A Ordinary Shares)|N|WDH|N|100|N|WDH"], market="NYSE")
    cat_nyse = parse_nasdaq_directory(raw_nyse, market="NYSE", received_at=NOW)
    assert [item["symbol"] for item in universe_response(cat_nyse, {}, now=NOW)["items"]] == ["WDH"]
    assert cat_nyse.listings[0].listing_class == "equity"


def test_ambiguous_non_etf_security_is_visible_without_guessing_its_type():
    raw = nasdaq(["WTEST|Example Inc. - Warrants|Q|N|N|100|N|N"])
    cat = parse_nasdaq_directory(raw, market="NASDAQ", received_at=NOW)
    response = universe_response(cat, {}, now=NOW)
    assert response["item_count"] == response["classification_pending_count"] == 1
    assert response["items"][0]["symbol"] == "WTEST"
    assert not response["items"][0]["buy_permission"]


@pytest.mark.parametrize("symbol,name", [
    ("OPENL", "Opendoor Technologies Inc - Series A Warrants exercisable for Common Stock"),
    ("OPENW", "Opendoor Technologies Inc - Series K Warrants exercisable for Common Stock"),
    ("OPENZ", "Opendoor Technologies Inc - Series Z Warrants exercisable for Common Stock"),
    ("HAVAR", "Havana Acquisition Corp. - Rights to receive one Ordinary Share"),
    ("AMPX.W", "Amprius Technologies Inc. Warrants to purchase Common Stock"),
    ("UNIT", "Example Inc. - Units, each containing one Ordinary Share and one Right"),
])
def test_conversion_clause_does_not_reclassify_contract_as_the_underlying_equity(symbol, name):
    source = parse_nasdaq_directory(nasdaq([f"{symbol}|{name}|Q|N|N|100|N|N"]),
                                    market="NASDAQ", received_at=NOW)
    assert source.listings[0].security_type == "Other"
    assert source.listings[0].listing_class == "classification_pending"
    response = universe_response(source, {}, now=NOW)
    assert response["classified_equity_count"] == 0
    assert [item["symbol"] for item in response["items"]] == [symbol]


@pytest.mark.parametrize("mutation", [{"valid_from": None}, {"valid_until": 123}, {"valid_until": True}])
def test_malformed_scope_date_keeps_inventory_visible_and_denies_permission(mutation):
    response = universe_response(catalogue([Listing("NASDAQ", "CHEAP", "Company")]),
                                 {"CHEAP": canonical()}, population=scope() | mutation, now=NOW)
    assert response["item_count"] == 1
    assert not response["items"][0]["buy_permission"]


@pytest.mark.parametrize("evidence", [[], ["untrusted"], 123, True])
def test_nonobject_scope_is_a_denial_not_an_api_failure(evidence):
    assert not buy_scope_allows(evidence, market="NASDAQ", symbol="CHEAP", tp_source_version="32", now=NOW)


@pytest.mark.parametrize("raw", [nasdaq(["A|Company|Q|N|N|100|N|N"], footer=False),
                                 nasdaq(["A|Company|Q|N|N|100|N|N"] * 2),
                                 nasdaq(["A|Company|Q|?|N|100|N|N"])])
def test_partial_duplicate_or_unknown_flag_directory_is_not_a_complete_inventory(raw):
    with pytest.raises(ValueError):
        parse_nasdaq_directory(raw, market="NASDAQ", received_at=NOW)


def test_b3_complete_file_has_no350_cap_and_retains_pending_classification():
    raw = b3_file([(f"AB{i:04}3", "ON", "010") for i in range(701)] + [("UNKNOWN11", "CI", "010")])
    parsed = parse_b3_titulos(raw, received_at=NOW)
    response = universe_response(parsed, {}, now=NOW)
    assert parsed.source_row_count == response["item_count"] == 702
    pending = next(item for item in response["items"] if item["symbol"] == "UNKNOWN11")
    assert "listing_classification_pending" in pending["not_evaluable_reasons"]


def test_b3_bad_count_truncated_or_missing_identity_fails_closed():
    raw = b3_file([("ABCD3", "ON", "010")])
    with pytest.raises(ValueError, match="220-byte"):
        parse_b3_titulos(raw[:-5], received_at=NOW)
    with pytest.raises(ValueError, match="count"):
        parse_b3_titulos(raw.replace(b"090000004", b"090000005"), received_at=NOW)
    with pytest.raises(ValueError, match="company identity"):
        parse_b3_titulos(b3_file([("ABCD3", "ON", "010")], missing_company=True), received_at=NOW)


def test_b3_derivative_and_fractional_records_do_not_duplicate_cash_listing():
    parsed = parse_b3_titulos(b3_file([("ABCD3", "ON", "010"), ("ABCD3F", "ON", "020"),
                                      ("ABCDX1", "ON", "070")]), received_at=NOW)
    assert [item.symbol for item in parsed.listings] == ["ABCD3"]
    assert parsed.excluded_counts == {"non_cash_market": 2}


def test_manifest_is_checked_on_reload_and_mutation_cannot_silently_change_coverage():
    original = catalogue([Listing("NASDAQ", "CHEAP", "Company")])
    assert catalogue_from_payload(original.payload()) == original
    tampered = original.payload()
    tampered["listings"].append({"market": "NASDAQ", "symbol": "NEW", "name": "New"})
    with pytest.raises(ValueError, match="digest mismatch"):
        catalogue_from_payload(tampered)


@pytest.mark.parametrize("mutation", [
    {"source_url": "https://vendor.example/list.txt"}, {"source_row_count": 300},
    {"source_row_count": True}, {"raw_sha256": "unverified"},
    {"excluded_counts": {"vendor_capped": -1}}, {"source_date": "no-date"},
])
def test_recomputed_manifest_cannot_launder_an_incomplete_or_nonofficial_inventory(mutation):
    payload = catalogue([Listing("NASDAQ", "CHEAP", "Company")]).payload()
    payload.update(mutation)
    payload.pop("manifest_sha256")
    payload["manifest_sha256"] = digest(payload)
    with pytest.raises(ValueError):
        catalogue_from_payload(payload)


def test_missing_history_evidence_and_invalid_numeric_values_are_not_invented():
    row = canonical() | {"price": float("nan"), "history_days": "bad", "our_tp": -1}
    item = universe_response(catalogue([Listing("NASDAQ", "CHEAP", "Company")]),
                             {"CHEAP": row}, population=scope(), now=NOW)["items"][0]
    assert item["price"] is item["our_tp"] is None
    assert set(item["not_evaluable_reasons"]) == {"price_missing", "canonical_tp_missing", "insufficient_history"}
    assert not item["buy_permission"]


def test_inventory_capture_is_separate_from_prediction_publication(tmp_path, capsys):
    raw = nasdaq(["A|Company|Q|N|N|100|N|N"])
    path = tmp_path / "official.txt"
    path.write_bytes(raw)
    assert main(["--market", "NASDAQ", "--input", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["recorded"] is result["valuation_published"] is result["buy_permission_promoted"] is False


def test_record_catalogue_uses_inventory_namespace_only():
    class Store:
        def ensure_methodology_version(self, key, version, inputs, note):
            assert key == "official_listing_inventory"
            return "method-1"

        def save_analysis_snapshot(self, kind, market, method, inputs, outputs, received):
            assert kind == CATALOGUE_ANALYSIS
            assert market == "NASDAQ" and method == "method-1"
            catalogue_from_payload(outputs)
            return "snapshot-1"

    assert record_catalogue(Store(), catalogue([Listing("NASDAQ", "CHEAP", "Company")])) == "snapshot-1"


def test_b3_zip_has_one_bounded_file_and_does_not_extract_to_filesystem():
    raw = b3_file([("ABCD3", "ON", "010")])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../../outside.txt", raw)
    assert decode_directory(buffer.getvalue(), "B3") == raw


def test_inventory_routes_reuse_existing_view_permissions_and_report_missing_capture():
    class Store:
        def analysis_snapshot_at_or_before(self, *args):
            return None

    app = FastAPI()
    app.include_router(listed_universe_router(Store()))
    with TestClient(app) as client:
        for module, permission in [("candidates", "candidates"), ("matrix-power", "matrix")]:
            path = f"/api/v1/{module}/nasdaq/universe"
            assert required_permissions(path) == (permission,)
            assert client.get(path).status_code == 503
        assert client.get("/api/v1/candidates/otc/universe").status_code == 422


def test_api_missing_inventory_does_not_fetch_a_provider_or_synthesize_a_capped_fallback():
    class Store:
        def analysis_snapshot_at_or_before(self, kind, market, at):
            assert kind == CATALOGUE_ANALYSIS and market == "NASDAQ"
            return None

    with pytest.raises(LookupError, match="not been captured"):
        read_universe(Store(), "NASDAQ", now=NOW)


def test_real_canonical_generation_id_is_stamped_without_mutating_official_rows(monkeypatch):
    from app.config import Settings
    from app.database import Database
    from app import valuation_official as official
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW - timedelta(hours=1)
    monkeypatch.setattr(official, "datetime", Clock)
    database = Database(Settings(database_url="", auth_cookie_secure=False))
    row = {key: value for key, value in canonical().items()
           if key not in {"official_generation_id", "tp_source", "tp_source_version", "official_row_sha256", "decisor_verdict"}}
    row.update({"internal_tp": 9.0, "internal_buy_in": 7.0,
                         "internal_score": 70.0, "internal_status": "full_match",
                         "internal_expected_total_return_percent": 10.0})
    at = NOW - timedelta(hours=2)
    method = database.ensure_methodology_version("fixture", 32, {}, "fixture")
    for market in ["B3", "NASDAQ", "NYSE"]:
        database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", method,
                                        {"methodology_version": 32}, {"rows": [row], "universe_size": 1}, at)
    record_catalogue(database, catalogue([Listing("NASDAQ", "CHEAP", "Company")]))
    generation = official.generation_at(database, NOW)
    raw = official.official_rows(database, "NASDAQ", generation=generation)
    assert raw["CHEAP"]["generation_id"] == generation["generation_id"]
    assert "official_generation_id" not in raw["CHEAP"]
    before = copy.deepcopy(raw)
    monkeypatch.setattr(official, "official_rows", lambda *args, **kwargs: raw)
    response = read_universe(database, "NASDAQ", now=NOW)
    item = response["items"][0]
    assert item["valuation_status"] == "valued"
    assert item["official_generation_id"] == generation["generation_id"]
    assert item["our_tp"] == raw["CHEAP"]["our_tp"]
    assert raw == before
    assert not item["buy_permission"]  # a TP record is not an artifact attestation
