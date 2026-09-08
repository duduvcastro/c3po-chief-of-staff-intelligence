"""Offline synthetic registry, price bytes and externally verified receipt stubs."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib

import pytest

from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_causal_list import (DAILY_SCHEMA, REGISTRY_SCHEMA, build_commitment, digest)
from app.r2d2_v2_sources import FileShadowSource, SourceUnavailable, canonical

DAY = date(2026, 9, 8)
EPOCH = "R2D2-V2-DIAG"
BUILT = datetime(2026, 9, 4, 20, 5, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def calendar():
    return ShadowCalendar()


def inputs(calendar, symbols=("SYNTH",), bar_count=61):
    bars = []
    for day in calendar.details(DAY)["previous_sessions"][-bar_count:]:
        at = calendar.details(day)["close"].isoformat()
        bars.append({"session_date": day.isoformat(), "open": 100, "high": 101, "low": 99, "close": 100,
            "volume": 150000, "complete": True, "regular_session": True, "source_at": at, "available_at": at})
    daily = {"bars": bars, "splits": [], "adjustment": "RAW_UNADJUSTED", "coverage_verified": True,
             "split_coverage_verified": True, "source_at": "2026-09-04T20:00:00Z", "available_at": "2026-09-04T20:02:00Z"}
    registry = {"schema": REGISTRY_SCHEMA, "source_id": "synthetic-registry", "source_at": "2026-09-04T20:00:01Z",
        "available_at": "2026-09-04T20:01:00Z", "captured_at": "2026-09-04T20:01:00Z", "coverage_verified": True,
        "instruments": [{"symbol": symbol, "market": "NASDAQ", "security_type": "COMMON_STOCK", "classification_verified": True} for symbol in symbols]}
    contract = {"schema": DAILY_SCHEMA, "source_id": "synthetic-raw-daily", "source_at": "2026-09-04T20:00:00Z",
        "available_at": "2026-09-04T20:02:00Z", "instruments": [{"symbol": symbol, "daily": deepcopy(daily)} for symbol in symbols]}
    return registry, contract


def build(calendar, registry=None, daily=None, **kwargs):
    if registry is None:
        registry, daily = inputs(calendar)
    return build_commitment(epoch=EPOCH, day=DAY, built_at=kwargs.pop("built_at", BUILT), calendar=calendar,
        registry_bytes=canonical(registry), daily_bytes=canonical(daily), **kwargs)


def receipts(commitment):
    binding = {key: commitment[key] for key in ("epoch", "session", "manifest_sha", "amendment_sha", "list_sha256", "n_cut")}
    binding["commitment_sha256"] = digest(commitment)
    audit = {"event_id": "build-receipt-1", "event_type": "r2d2.v2.causal_list_built", "occurred_at": commitment["built_at"], "payload": binding}
    publication = {"event_id": "publication-receipt-1", "event_type": "r2d2.v2.causal_list_published",
        "occurred_at": "2026-09-05T12:00:01Z", "payload": {**binding, "build_audit_event_id": audit["event_id"],
            "channel": "relay", "publication_reference": "synthetic/commitment.json", "published_at": "2026-09-05T12:00:00Z"}}
    return {"commitment": commitment, "audit_receipt": audit, "publication_receipt": publication}


def publish(tmp_path, envelope, verified=True):
    root = tmp_path.resolve() / "private-spool"
    parent = root / "causal_list" / EPOCH
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    for path in (root, root / "causal_list", parent):
        path.chmod(0o700)
    target = parent / (DAY.isoformat() + ".json")
    target.write_bytes(canonical(envelope))
    target.chmod(0o600)
    # Independent frozen evidence simulates the durable audit store, not file assertions.
    persisted = {event["event_id"]: deepcopy(event) for event in (envelope["audit_receipt"], envelope["publication_receipt"])}
    def verify(receipt, expected):
        actual = persisted.get(receipt["event_id"])
        return actual == receipt and {key: actual[key] for key in expected} == expected
    source = FileShadowSource(root, causal_receipt_verifier=verify if verified else None)
    return source, target, persisted


def test_selection_receipts_raw_hashes_and_limited_coverage(calendar, tmp_path):
    registry, daily = inputs(calendar)
    commitment = build(calendar, registry, daily)
    assert commitment["list"] == ["SYNTH"]
    assert commitment["previous_session"] == "2026-09-04"  # holiday Monday never inferred as a session
    assert commitment["registry_sha256"] == hashlib.sha256(canonical(registry)).hexdigest()
    assert commitment["daily_contract_sha256"] == hashlib.sha256(canonical(daily)).hexdigest()
    source, path, _ = publish(tmp_path, receipts(commitment))
    result = source.causal_list(EPOCH, DAY, NOW, calendar)
    assert result["status"] == "AVAILABLE" and result["symbols"] == ["SYNTH"]
    assert result["envelope_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["coverage"] == {"numerator": 1, "denominator": 1, "ratio": 1.0,
        "scope": "FILTERED_PROVIDER_REGISTRY_ONLY", "outside_registry_observed": False, "complete_exchange_universe": False}


@pytest.mark.parametrize("count,selected", [(61, True), (21, True), (20, True), (19, False)])
def test_adv_window_is_twenty_not_atr_sixty_one(calendar, count, selected):
    registry, daily = inputs(calendar, bar_count=count)
    result = build(calendar, registry, daily)
    assert bool(result["list"]) is selected
    assert result["counts"]["reasons"].get("ADV_WINDOW_INCOMPLETE", 0) == int(not selected)


def test_non_liquidity_history_cannot_change_selection(calendar):
    registry, daily = inputs(calendar)
    daily["instruments"][0]["daily"]["bars"][0]["close"] = None
    assert build(calendar, registry, daily)["list"] == ["SYNTH"]


def test_twenty_sessions_include_d_minus_one_and_not_shifted_window(calendar):
    registry, daily = inputs(calendar)
    bars = daily["instruments"][0]["daily"]["bars"]
    bars[-1]["volume"] = 149999
    assert build(calendar, registry, daily)["counts"]["reasons"]["ADV_BELOW_15000000"] == 1
    bars.pop()
    result = build(calendar, registry, daily)
    assert result["list"] == [] and result["counts"]["reasons"]["ADV_WINDOW_INCOMPLETE"] == 1


@pytest.mark.parametrize("change,reason", [
    (lambda row: row.update(adjustment="ADJUSTED"), "DAILY_CONTRACT_INVALID"),
    (lambda row: row.update(split_coverage_verified=False), "DAILY_CONTRACT_INVALID"),
    (lambda row: row["bars"][-1].update(complete=False), "ADV_WINDOW_INCOMPLETE"),
    (lambda row: row["bars"][-1].update(source_at="2026-09-04T19:59:59Z"), "DAILY_NOT_OFFICIAL_CLOSE"),
    (lambda row: row["bars"][-1].update(available_at="2026-09-04T20:06:00Z"), "SOURCE_FUTURE_OR_REVERSED"),
])
def test_raw_daily_causal_failures_are_counted(calendar, change, reason):
    registry, daily = inputs(calendar)
    change(daily["instruments"][0]["daily"])
    result = build(calendar, registry, daily)
    assert result["list"] == [] and result["counts"]["reasons"][reason] == 1


def test_price_adv_boundaries_classification_and_denominator(calendar):
    registry, daily = inputs(calendar, ("A", "B", "C", "D", "E", "F"))
    registry["instruments"][1].update(classification_verified=False)
    registry["instruments"][2].update(security_type="ETF")
    registry["instruments"][3].update(market="NYSE", security_type="COMMON_STOCK_ADR")
    for bar in daily["instruments"][0]["daily"]["bars"]:
        bar.update(open=5, high=5, low=5, close=5, volume=3000000)
    for bar in daily["instruments"][4]["daily"]["bars"]:
        bar.update(open=4.9999, high=4.9999, low=4.9999, close=4.9999, volume=4000000)
    daily["instruments"][5]["daily"]["bars"][-1]["volume"] = 149999
    result = build(calendar, registry, daily)
    assert result["list"] == ["A", "D"]
    assert result["counts"]["filtered"] == 4
    assert result["counts"]["reasons"] == {"DATA_INELIGIBLE": 1, "CLASSIFICATION_EXCLUDED": 1,
        "CLOSE_BELOW_5": 1, "ADV_BELOW_15000000": 1, "NOT_IN_CAUSAL_LIST": 2, "N_CUT_EXCLUDED": 0}


def test_fixed_550_liquidity_order_and_symbol_tie_break(calendar):
    symbols = tuple(f"S{i:04d}" for i in range(552))
    registry, daily = inputs(calendar, tuple(reversed(symbols)), bar_count=20)
    for bar in daily["instruments"][0]["daily"]["bars"]:
        bar["volume"] *= 2  # S0551 precedes every lower-ADV name
    result = build(calendar, registry, daily)
    assert result["n_cut"] == 550
    assert result["list"] == ["S0551", *symbols[:549]]
    assert result["counts"]["reasons"]["N_CUT_EXCLUDED"] == 2


@pytest.mark.parametrize("built", ["2026-09-04T20:00:00Z", "2026-09-08T04:00:00Z"])
def test_construction_window_is_strict_after_close_before_midnight(calendar, built):
    with pytest.raises(SourceUnavailable, match="CAUSAL_LIST_LATE"):
        build(calendar, built_at=datetime.fromisoformat(built))


def test_self_reported_receipt_without_external_confirmation_is_missing(calendar, tmp_path):
    source, _, _ = publish(tmp_path, receipts(build(calendar)), verified=False)
    result = source.causal_list(EPOCH, DAY, NOW, calendar)
    assert result["status"] == "MISSING"
    assert result["diagnostics"] == [{"code": "AUDIT_RECEIPT_UNVERIFIED"}]


@pytest.mark.parametrize("target", ["audit_receipt", "publication_receipt"])
def test_receipts_require_exact_durable_event_not_file_claim(calendar, tmp_path, target):
    envelope = receipts(build(calendar))
    source, path, persisted = publish(tmp_path, envelope)
    persisted.pop(envelope[target]["event_id"])
    result = source.causal_list(EPOCH, DAY, NOW, calendar)
    expected = "AUDIT_RECEIPT_UNVERIFIED" if target == "audit_receipt" else "PUBLICATION_RECEIPT_UNVERIFIED"
    assert result["diagnostics"] == [{"code": expected}]
    assert path.exists()  # file presence/mtime never fills the missing audit fact


@pytest.mark.parametrize("change,code", [
    (lambda e: e["commitment"].update(n_cut=551), "CAUSAL_COMMITMENT_MISMATCH"),
    (lambda e: e["commitment"].update(list=[]), "CAUSAL_COMMITMENT_MISMATCH"),
    (lambda e: e["commitment"].update(registry_sha256="f" * 64), "CAUSAL_COMMITMENT_MISMATCH"),
    (lambda e: e["audit_receipt"].update(occurred_at="2026-09-04T20:05:01+00:00"), "AUDIT_RECEIPT_BINDING"),
    (lambda e: e["publication_receipt"]["payload"].update(build_audit_event_id="foreign"), "PUBLICATION_RECEIPT_BINDING"),
])
def test_tampered_commitment_or_cross_receipt_binding_is_rejected(calendar, tmp_path, change, code):
    envelope = receipts(build(calendar))
    change(envelope)
    source, _, _ = publish(tmp_path, envelope)
    assert source.causal_list(EPOCH, DAY, NOW, calendar)["diagnostics"] == [{"code": code}]


def test_publication_at_ten_is_late_even_with_valid_external_receipt(calendar, tmp_path):
    envelope = receipts(build(calendar))
    envelope["publication_receipt"].update(occurred_at=NOW.isoformat())
    envelope["publication_receipt"]["payload"]["published_at"] = NOW.isoformat()
    source, _, _ = publish(tmp_path, envelope)
    assert source.causal_list(EPOCH, DAY, NOW, calendar)["diagnostics"] == [{"code": "CAUSAL_LIST_LATE"}]


@pytest.mark.parametrize("mode", ["traversal", "symlink", "world-readable", "future"])
def test_file_reader_boundaries_and_unavailable_future(calendar, tmp_path, mode):
    source, path, _ = publish(tmp_path, receipts(build(calendar)))
    epoch, now = EPOCH, NOW
    if mode == "traversal":
        epoch = "../" + EPOCH
    elif mode == "symlink":
        other = path.with_suffix(".raw")
        path.rename(other)
        path.symlink_to(other)
    elif mode == "world-readable":
        path.chmod(0o644)
    else:
        now = BUILT - timedelta(seconds=1)
    result = source.causal_list(epoch, DAY, now, calendar)
    assert result["status"] == "MISSING" and result["symbols"] == []


def test_completed_capture_may_precede_contract_availability(calendar):
    registry, daily = inputs(calendar)
    registry["captured_at"] = "2026-09-04T20:00:30Z"
    assert build(calendar, registry, daily)["list"] == ["SYNTH"]
    registry["captured_at"] = "2026-09-04T20:01:01Z"
    with pytest.raises(SourceUnavailable, match="REGISTRY_CAPTURE_NOT_D_MINUS_ONE"):
        build(calendar, registry, daily)


def test_adr_uses_signed_classification_token_without_silent_alias(calendar):
    registry, daily = inputs(calendar)
    registry["instruments"][0]["security_type"] = "COMMON_STOCK_ADR"
    assert build(calendar, registry, daily)["list"] == ["SYNTH"]
    registry["instruments"][0]["security_type"] = "ADR"
    assert build(calendar, registry, daily)["counts"]["reasons"]["CLASSIFICATION_EXCLUDED"] == 1


def test_prior_publication_verified_after_deadline_is_not_retroactive_publication(calendar, tmp_path):
    envelope = receipts(build(calendar))
    envelope["publication_receipt"].update(occurred_at=(NOW + timedelta(seconds=1)).isoformat())
    envelope["publication_receipt"]["payload"]["published_at"] = (NOW - timedelta(seconds=1)).isoformat()
    source, _, _ = publish(tmp_path, envelope)
    before_verification = source.causal_list(EPOCH, DAY, NOW, calendar)
    assert before_verification["status"] == "MISSING"
    after_verification = source.causal_list(EPOCH, DAY, NOW + timedelta(seconds=2), calendar)
    assert after_verification["status"] == "AVAILABLE"
    assert after_verification["publication_at"] == (NOW - timedelta(seconds=1)).isoformat()
