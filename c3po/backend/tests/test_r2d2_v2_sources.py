"""Synthetic evidence files only: no providers, application imports or database."""
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from app import r2d2_v2_sources as sources

NOW = datetime(2026, 9, 8, 14, 0, 5, tzinfo=timezone.utc)
AT = "2026-09-08T14:00:00+00:00"


def digest(value):
    return hashlib.sha256(sources.canonical(value)).hexdigest()


def sealed(payload):
    envelope = {"schema": sources.SNAPSHOT_SCHEMA, "manifest_sha": sources.MANIFEST_SHA,
                "source_id": "audited-fixture", "provenance": {"producer": "fixture", "version": "v1", "payload_sha256": "a" * 64},
                "source_at": AT, "available_at": AT, "sequence": 1, **payload}
    envelope.pop("self_sha256", None)
    envelope["self_sha256"] = digest(envelope)
    return envelope


def instrument():
    bars = []
    day = NOW.date() - timedelta(days=95)
    while len(bars) < 61:
        if day.weekday() < 5:
            stamp = datetime(day.year, day.month, day.day, 20, tzinfo=timezone.utc).isoformat()
            bars.append({"session_date": day.isoformat(), "open": 100, "high": 102, "low": 99,
                         "close": 101, "volume": 1000000, "complete": True, "regular_session": True,
                         "source_at": stamp, "available_at": stamp})
        day += timedelta(days=1)
    return {"symbol": "SYNTH", "market": "NASDAQ", "security_type": "COMMON_STOCK", "classification_verified": True,
            "sequence": 1, "source_at": AT, "available_at": AT,
            "quote": {"bid": 100, "ask": 100.1, "bid_source_at": AT, "ask_source_at": AT, "available_at": AT},
            "daily": {"bars": bars, "splits": [], "adjustment": "RAW_UNADJUSTED", "coverage_verified": True,
                      "split_coverage_verified": True, "source_at": AT, "available_at": AT},
            "risk": {"value": 44, "producer": "fixture-risk", "source_at": AT, "available_at": AT},
            "earnings": {"coverage_verified": True, "window_start": "2026-09-08T00:00:00Z", "window_end": "2026-10-01T00:00:00Z",
                         "events": [], "source_at": AT, "available_at": AT}}


@pytest.fixture
def source_dir(tmp_path):
    # macOS /var can be a symlink; the fixture root is canonical, not the port.
    root = tmp_path.resolve() / "private-source"
    root.mkdir(mode=0o700)
    (root / "events").mkdir(mode=0o700)
    return root


def write(path, value):
    data = value if isinstance(value, bytes) else sources.canonical(value)
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def snapshot(root, row=None, **changes):
    envelope = sealed({"universe": {"coverage_verified": True, "instruments": [row or instrument()]}, **changes})
    write(root / "snapshot.json", envelope)
    return envelope


def event_body(kind="TRADE", **changes):
    body = {"type": kind, "at": AT, "available_at": AT, "session": NOW.date().isoformat(), "instrument_key": "NASDAQ:SYNTH"}
    extra = {
        "TRADE": {"price": 100, "regular": True}, "MARK": {"price": 100, "regular": False},
        "QUOTE": {"bid": 100, "ask": 100.1, "bid_at": AT, "ask_at": AT, "regular": True},
        "BAR": {"end_at": AT, "open": 100, "high": 103, "low": 99, "close": 102, "regular": True, "coverage_complete": True},
        "SPLIT": {"factor": 2}, "DIVIDEND_ENTITLEMENT": {"entitlement_id": "right-1", "net_per_share": 0.4},
        "DIVIDEND_PAYMENT": {"entitlement_id": "right-1"}, "EARNINGS": {"earnings_at": "2026-09-10T20:00:00Z"},
        "MATURITY": {}, "DATA_GAP": {"reason": "feed-missing"}, "SESSION_OPEN": {}, "SESSION_CLOSE": {},
    }[kind]
    body.update(extra)
    if kind == "BAR":
        body["at"] = "2026-09-08T13:59:00Z"
    if kind.startswith("SESSION_"):
        body.pop("instrument_key")
    body.update(changes)
    return body


def write_event(root, body=None, identity="evt-1", **changes):
    envelope = sealed({"schema": sources.EVENT_SCHEMA, "event_id": identity, "event": body or event_body(), **changes})
    path = write(root / "events" / f"{identity}.{envelope['self_sha256']}.json", envelope)
    return path, envelope


def test_snapshot_preserves_every_field_and_receipt(source_dir):
    before = instrument()
    envelope = snapshot(source_dir, before)
    result = sources.FileShadowSource(source_dir).snapshot(NOW)
    assert result["status"] == "AVAILABLE"
    row = result["universe"]["instruments"][0]
    assert row == {**before, "data_available": True, "diagnostics": []}
    assert result["self_sha256"] == envelope["self_sha256"]
    assert result["envelope_sha256"] == hashlib.sha256((source_dir / "snapshot.json").read_bytes()).hexdigest()
    assert result["provenance"] == envelope["provenance"]
    assert sources.capabilities()["production_ready"] is False


@pytest.mark.parametrize("change", [
    lambda row: row["risk"].update(value=None),
    lambda row: row["risk"].update(value="44"),
    lambda row: row["risk"].update(value=101),
    lambda row: row["risk"].update(value=True),
    lambda row: row["risk"].update(source_at="2026-09-09T00:00:00Z"),
    lambda row: row["quote"].update(bid_source_at="2026-09-08T13:59:54Z"),
    lambda row: row["quote"].update(bid=None),
    lambda row: row["quote"].update(ask=99),
    lambda row: row["earnings"].update(coverage_verified=False),
    lambda row: row["daily"].update(coverage_verified=False),
    lambda row: row["daily"].update(split_coverage_verified=False),
    lambda row: row["daily"].update(adjustment="RAW_SPLITS_KNOWN_ONLY"),
    lambda row: row["daily"]["bars"][0].update(complete=False),
    lambda row: row["daily"]["bars"][0].pop("regular_session"),
    lambda row: row["daily"]["bars"].pop(),
    lambda row: row.update(market=["NASDAQ"]),
    lambda row: row.update(security_type=None, classification_verified=False),
])
def test_invalid_completed_response_retains_raw_values_and_availability(source_dir, change):
    raw = instrument()
    change(raw)
    snapshot(source_dir, raw)
    result = sources.FileShadowSource(source_dir).snapshot(NOW)
    assert result["status"] == "AVAILABLE"
    observed = result["universe"]["instruments"][0]
    assert observed["data_available"] is False
    assert observed["diagnostics"]
    assert {key: observed[key] for key in raw} == raw
    assert observed["available_at"] == AT


def test_score_eligibility_is_not_a_source_gate(source_dir):
    raw = instrument()
    raw["risk"]["value"] = 99
    snapshot(source_dir, raw)
    result = sources.FileShadowSource(source_dir).snapshot(NOW)
    assert result["universe"]["instruments"][0]["data_available"] is True


def test_quote_ten_second_boundary_and_future_are_distinct(source_dir):
    raw = instrument()
    raw["quote"]["bid_source_at"] = "2026-09-08T13:59:55Z"
    snapshot(source_dir, raw)
    source = sources.FileShadowSource(source_dir)
    assert source.snapshot(NOW)["universe"]["instruments"][0]["data_available"] is True
    raw["quote"]["bid_source_at"] = "2026-09-08T14:00:01Z"
    snapshot(source_dir, raw)
    assert source.snapshot(NOW)["universe"]["instruments"][0]["data_available"] is False


def test_split_source_time_is_never_inferred(source_dir):
    raw = instrument()
    raw["daily"]["splits"] = [{"factor": 2, "effective_at": "2026-09-09T13:30:00Z", "source_at": AT, "available_at": AT}]
    snapshot(source_dir, raw)
    source = sources.FileShadowSource(source_dir)
    # Known future split is preserved, not prematurely applied by the port.
    assert source.snapshot(NOW)["universe"]["instruments"][0]["data_available"] is True
    raw["daily"]["splits"][0].pop("source_at")
    snapshot(source_dir, raw)
    seen = source.snapshot(NOW)["universe"]["instruments"][0]
    assert seen["data_available"] is False
    assert "source_at" not in seen["daily"]["splits"][0]


@pytest.mark.parametrize("change,code", [
    ({"manifest_sha": "b" * 64}, "MANIFEST_MISMATCH"),
    ({"schema": "OTHER"}, "SCHEMA_MISMATCH"),
    ({"source_at": "2026-09-09T00:00:00Z"}, "SOURCE_FUTURE_OR_REVERSED"),
    ({"available_at": "2026-09-09T00:00:00Z"}, "SOURCE_FUTURE_OR_REVERSED"),
    ({"source_at": "2026-09-08T14:00:00"}, "TIMESTAMP_NAIVE"),
    ({"provenance": {}}, "PROVENANCE_MISSING"),
])
def test_untrusted_envelope_is_missing_without_instrument_payload(source_dir, change, code):
    snapshot(source_dir, **change)
    result = sources.FileShadowSource(source_dir).snapshot(NOW)
    assert result["status"] == "MISSING"
    assert result["universe"]["instruments"] == []
    assert result["diagnostics"] == [{"code": code}]


@pytest.mark.parametrize("payload,code", [(b'{"schema":1,"schema":2}', "JSON_DUPLICATE_KEY"),
    (b'{"value":NaN}', "JSON_NONFINITE"), (b'{broken', "JSON_MALFORMED")])
def test_malformed_json_is_bounded_diagnostic(source_dir, payload, code):
    write(source_dir / "snapshot.json", payload)
    result = sources.FileShadowSource(source_dir).snapshot(NOW)
    assert result["status"] == "MISSING"
    assert result["diagnostics"] == [{"code": code}]


def test_envelope_hash_is_checked_against_actual_payload(source_dir):
    envelope = snapshot(source_dir)
    envelope["universe"]["instruments"][0]["risk"]["value"] = 1
    write(source_dir / "snapshot.json", envelope)
    assert sources.FileShadowSource(source_dir).snapshot(NOW)["diagnostics"] == [{"code": "ENVELOPE_HASH_MISMATCH"}]


def test_unknown_earnings_is_not_converted_to_no_events(source_dir):
    raw = instrument()
    raw["earnings"] = {"coverage_verified": False, "events": None, "source_at": AT, "available_at": AT}
    snapshot(source_dir, raw)
    seen = sources.FileShadowSource(source_dir).snapshot(NOW)["universe"]["instruments"][0]
    assert seen["data_available"] is False
    assert seen["earnings"]["events"] is None


@pytest.mark.parametrize("kind", ["file", "root", "ancestor", "events"])
def test_symlink_paths_are_never_followed(source_dir, kind):
    snapshot(source_dir)
    root = source_dir
    if kind == "file":
        real = root / "actual.json"
        (root / "snapshot.json").rename(real)
        (root / "snapshot.json").symlink_to(real)
    elif kind == "root":
        root = source_dir.parent / "linked"
        root.symlink_to(source_dir, target_is_directory=True)
    elif kind == "ancestor":
        linked_parent = source_dir.parent / "linked-parent"
        linked_parent.symlink_to(source_dir.parent, target_is_directory=True)
        root = linked_parent / source_dir.name
    else:
        actual = root / "actual-events"
        (root / "events").rename(actual)
        (root / "events").symlink_to(actual, target_is_directory=True)
    source = sources.FileShadowSource(root)
    if kind == "events":
        assert source.events(NOW) == []
        assert source.last_event_diagnostics
    else:
        assert source.snapshot(NOW)["status"] == "MISSING"


@pytest.mark.parametrize("kind", ["file", "directory", "oversize"])
def test_source_permissions_and_size_are_required(source_dir, kind, monkeypatch):
    snapshot(source_dir)
    if kind == "file":
        (source_dir / "snapshot.json").chmod(0o644)
    elif kind == "directory":
        source_dir.chmod(0o755)
    else:
        monkeypatch.setattr(sources, "MAX_SNAPSHOT_BYTES", 16)
    assert sources.FileShadowSource(source_dir).snapshot(NOW)["status"] == "MISSING"


@pytest.mark.parametrize("kind", ["BAR", "TRADE", "QUOTE", "MARK", "SPLIT", "DIVIDEND_ENTITLEMENT", "DIVIDEND_PAYMENT", "EARNINGS", "MATURITY", "DATA_GAP", "SESSION_OPEN", "SESSION_CLOSE"])
def test_event_shape_is_ledger_compatible_and_receipt_immutable(source_dir, kind):
    body = event_body(kind)
    _, envelope = write_event(source_dir, body)
    source = sources.FileShadowSource(source_dir)
    first = source.events(NOW)
    assert len(first) == 1 and not source.last_event_diagnostics
    assert {key: first[0][key] for key in body} == body
    assert first == source.events(NOW)
    assert first[0]["self_sha256"] == envelope["self_sha256"]
    assert first[0]["provenance"] == envelope["provenance"]
    # The real pure ledger accepts the file adapter's full event shape.
    from app.r2d2_v2_portfolio import apply_event, new_portfolio
    initial = new_portfolio()
    if kind == "SESSION_CLOSE":
        initial, _ = apply_event(initial, {**event_body("SESSION_OPEN"), "event_id": "open-first"})
    state, receipt = apply_event(initial, first[0])
    assert receipt["status"] == "APPLIED"
    _, second = apply_event(state, first[0])
    assert second["status"] == "DUPLICATE"


def test_event_preserves_actual_availability_separately_from_packaging(source_dir):
    body = event_body(available_at="2026-09-08T14:00:01Z")
    write_event(source_dir, body, available_at="2026-09-08T14:00:03Z")
    row = sources.FileShadowSource(source_dir).events(NOW)[0]
    assert row["available_at"] == body["available_at"]
    assert row["envelope_available_at"] == "2026-09-08T14:00:03Z"


@pytest.mark.parametrize("body", [event_body("BAR", coverage_complete=False),
    event_body("DIVIDEND_ENTITLEMENT", net_per_share=None), event_body("DATA_GAP")])
def test_observation_gaps_remain_explicit_events(source_dir, body):
    write_event(source_dir, body)
    observed = sources.FileShadowSource(source_dir).events(NOW)
    assert len(observed) == 1
    assert {key: observed[0][key] for key in body} == body


@pytest.mark.parametrize("body", [
    event_body("TRADE", type="PRICE"),
    event_body("DIVIDEND_ENTITLEMENT", type="DIVIDEND"),
    event_body("TRADE", regular=None),
    event_body("BAR", coverage_complete=None),
    event_body("QUOTE", bid_at="2026-09-08T14:00:01Z"),
    event_body("TRADE", at="2026-09-08T14:00:06Z"),
    event_body("BAR", trades=[{"at": "2026-09-08T14:00:00Z", "price": 100}]),
])
def test_invalid_event_blocks_complete_batch_instead_of_partial_tape(source_dir, body):
    write_event(source_dir, identity="valid")
    write_event(source_dir, body, identity="invalid")
    source = sources.FileShadowSource(source_dir)
    assert source.events(NOW) == []
    assert source.last_event_diagnostics


def test_complete_intrabar_trades_are_not_inferred(source_dir):
    trades = [{"at": "2026-09-08T13:59:01Z", "price": 99}, {"at": "2026-09-08T13:59:02Z", "price": 103}]
    write_event(source_dir, event_body("BAR", trades=trades))
    assert sources.FileShadowSource(source_dir).events(NOW)[0]["trades"] == trades


def test_changed_event_id_is_not_a_new_event(source_dir):
    original, _ = write_event(source_dir)
    source = sources.FileShadowSource(source_dir)
    assert len(source.events(NOW)) == 1
    original.unlink()
    write_event(source_dir, event_body(price=102))
    assert source.events(NOW) == []
    assert source.last_event_diagnostics == [{"code": "EVENT_ID_MUTATED"}]


def test_duplicate_event_id_and_filename_hash_fail_closed(source_dir):
    original, _ = write_event(source_dir)
    changed, _ = write_event(source_dir, event_body(price=102))
    source = sources.FileShadowSource(source_dir)
    assert source.events(NOW) == []
    assert source.last_event_diagnostics == [{"code": "EVENT_ID_DUPLICATED"}]
    changed.unlink()
    original.rename(original.with_name("evt-1." + "a" * 64 + ".json"))
    assert source.events(NOW) == []
    assert source.last_event_diagnostics == [{"code": "EVENT_RECEIPT_FILENAME"}]


def test_events_respect_bounded_directory_and_future_envelopes(source_dir, monkeypatch):
    write_event(source_dir)
    write_event(source_dir, identity="evt-2", available_at="2026-09-09T00:00:00Z")
    source = sources.FileShadowSource(source_dir)
    assert source.events(NOW) == []
    assert source.last_event_diagnostics == [{"code": "SOURCE_FUTURE_OR_REVERSED"}]
    monkeypatch.setattr(sources, "MAX_EVENT_FILES", 1)
    assert source.events(NOW) == []
    assert source.last_event_diagnostics == [{"code": "EVENT_FILE_LIMIT"}]


def test_existing_inventory_is_only_two_persisted_diagnostic_reads():
    class DatabaseStub:
        def __init__(self):
            self.calls = []
        def latest_analysis_snapshot(self, kind, entity):
            self.calls.append((kind, entity))
            return {"published_at": AT, "outputs": {"rows": [{"symbol": "SYNTH", "api_token": "do-not-project", "risk": 0}]}}
    database = DatabaseStub()
    result = sources.ExistingAppInventory(database).read(NOW)
    assert database.calls == [("valuation_universe", "NASDAQ_UNIVERSE"), ("valuation_universe", "NYSE_UNIVERSE")]
    assert result["universe"]["coverage_verified"] is False
    assert len(result["universe"]["instruments"]) == 2
    assert "do-not-project" not in json.dumps(result)
    assert result["production_ready"] is False
    assert len(result["capabilities"]["missing_producer_contracts"]) == 3


def test_existing_inventory_never_falls_back_to_provider_or_promotes_future():
    class DatabaseStub:
        def latest_analysis_snapshot(self, kind, entity):
            if entity == "NASDAQ_UNIVERSE":
                raise RuntimeError("secret-from-external-service")
            return {"published_at": "2026-09-09T00:00:00Z", "outputs": {"rows": [{"symbol": "SYNTH"}]}}
    result = sources.ExistingAppInventory(DatabaseStub()).read(NOW)
    assert result["universe"]["instruments"] == []
    assert "secret" not in json.dumps(result)
    assert len(result["diagnostics"]) == 2
