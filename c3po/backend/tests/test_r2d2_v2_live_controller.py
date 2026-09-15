from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace
from threading import Thread

import pytest

from app.market_data import eodhd_stream as streams
from app import r2d2_v2_live_controller as live
from app.r2d2_v2_store import digest, ShadowIntegrityError
from tests.test_r2d2_v2_live_group import fixture


@pytest.fixture
def clock(monkeypatch):
    seconds = [100.]
    monkeypatch.setattr(streams, "monotonic", lambda: seconds[0])
    monkeypatch.setattr(live, "monotonic", lambda: seconds[0])
    return seconds


def test_lease_expires_without_controller_or_database(clock):
    stream = streams.EodhdRealtimeStream("")
    stream.set_group("positions", ["OLD"], priority=200)
    stream.set_v2_group(["NEW"], capacity=2, ttl=15)
    clock[0] += 15
    assert stream._desired_symbols() == ("OLD",)
    assert stream.v2_status()["status"] == "LEASE_EXPIRED"


def test_other_group_concurrent_growth_evicts_only_v2_without_truncating(clock):
    stream = streams.EodhdRealtimeStream("", max_symbols=3)
    stream.set_group("analysis", ["A"], priority=110)
    stream.set_v2_group(["B", "C"], capacity=3, ttl=15)
    thread = Thread(target=lambda: stream.set_group("positions", ["D"], priority=200))
    thread.start(); thread.join()
    assert set(stream._desired_symbols()) == {"A", "D"}
    assert stream.v2_status()["status"] == "CAPACITY_CHANGED"
    assert stream._groups["analysis"][2] == ("A",)


def test_effective_limit_includes_configured_stream_and_other_groups(clock):
    stream = streams.EodhdRealtimeStream("", max_symbols=1)
    stream.set_group("dashboard", ["A"], priority=140)
    with pytest.raises(ValueError, match="CAPACITY"):
        stream.set_v2_group(["B"], capacity=550, ttl=15)
    assert stream._desired_symbols() == ("A",)


def test_group_update_deduplicates_and_counts_incremental_without_names_in_status(clock):
    stream = streams.EodhdRealtimeStream("", max_symbols=3)
    stream.set_group("positions", ["SYNTH"])
    receipt = stream.set_v2_group(["SYNTH", "OTHER", "OTHER"], capacity=3, ttl=15)
    assert receipt["incremental_count"] == 1 and receipt["desired_count"] == 2
    assert '"SYNTH"' not in json.dumps(receipt)
    with pytest.raises(ValueError, match="LEASE"):
        stream.set_group("r2d2-v2-live", ["UNAUTHORIZED"])


def test_send_is_not_ack_and_reconnect_clears_evidence(clock):
    stream = streams.EodhdRealtimeStream("")
    stream.set_v2_group(["SYNTH"], capacity=1, ttl=15)
    stream._set_feed_state("quote", "connected")
    stream._v2_sent("quote", {"SYNTH"}, stream._v2_generation)
    status = stream.v2_status()
    assert status["provider_ack_verified"] is False and status["readiness"] == "NOT_PROVEN"
    assert "trade" not in status["feeds"] and "received_count" not in status["feeds"]["quote"]
    stream._v2_received("quote", "SYNTH")
    assert stream.v2_status()["feeds"]["quote"]["received_count"] == 1
    stream._set_feed_state("quote", "connecting")
    stream._set_feed_state("quote", "connected")
    assert stream.v2_status()["feeds"] == {}


def test_stale_send_generation_cannot_validate_changed_group(clock):
    stream = streams.EodhdRealtimeStream("")
    stream.set_v2_group(["SYNTH"], capacity=2, ttl=15)
    generation = stream._v2_generation
    stream.set_v2_group(["OTHER"], capacity=2, ttl=15)
    stream._v2_sent("trade", {"OTHER"}, generation)
    assert stream.v2_status()["feeds"] == {}


def setup_controller(tmp_path, clock):
    release, saved = fixture()
    now = [datetime(2026, 9, 18, 15, tzinfo=timezone.utc)]
    settings = SimpleNamespace(r2d2_v2_live_policy_file=str(tmp_path / "policy.json"),
                               r2d2_v2_live_policy_sha="a"*64)
    policy = {"mode": "LIVE", "capacity": 3, "valid_until": (now[0]+timedelta(hours=1)).isoformat()}
    stream = streams.EodhdRealtimeStream("")
    stream.set_group("positions", ["OLD"], priority=200)
    controller = live.LiveGroupController(settings, stream, clock=lambda: now[0],
        policy_reader=lambda *args: policy, inventory=lambda *args: (release, saved))
    return controller, stream, saved, now, policy


def test_admission_then_close_refreshes_both_books_without_v1_loop(tmp_path, clock):
    c, stream, saved, now, policy = setup_controller(tmp_path, clock)
    assert c.step()["status"] == "SUBSCRIPTION_REQUESTED"
    assert set(stream._desired_symbols()) == {"OLD", "SYNTH"}
    for book in ["research", "portfolio"]:
        saved["state"]["ledger"][book]["synthetic-entry"]["status"] = "CLOSED"
    saved["state_sha"] = digest(saved["state"])
    now[0] += timedelta(seconds=5)
    c.step()
    assert stream._desired_symbols() == ("OLD",)


@pytest.mark.parametrize("failure", ["corrupt", "database", "revoked", "timeout", "stopped"])
def test_failures_remove_only_v2_and_block_receipt(tmp_path, clock, failure):
    c, stream, saved, now, policy = setup_controller(tmp_path, clock)
    c.step()
    if failure == "corrupt":
        saved["state_sha"] = "0"*64
    elif failure == "database":
        def unavailable(*a): raise RuntimeError("secret-dsn-and-symbol")
        c.inventory = unavailable
    elif failure == "revoked":
        def revoked(*a): raise ShadowIntegrityError("LIVE_POLICY_HASH_MISMATCH")
        c.policy_reader = revoked
    elif failure == "timeout":
        original = c.inventory
        def slow(*a):
            result = original(*a); now[0] += timedelta(seconds=12); return result
        c.inventory = slow
    else:
        c.stop_event.set()
    receipt = c.step()
    assert receipt["readiness"] == "BLOCKED" and stream._desired_symbols() == ("OLD",)
    assert "secret" not in json.dumps(receipt)


def test_stop_during_inventory_read_cannot_reactivate_group(tmp_path, clock):
    c, stream, saved, now, policy = setup_controller(tmp_path, clock)
    original = c.inventory
    def stop_while_reading(*a):
        c.stop(); return original(*a)
    c.inventory = stop_while_reading
    assert c.step()["status"] == "LIVE_CONTROLLER_STOPPED"
    assert stream._desired_symbols() == ("OLD",)


def test_proof_changes_group_then_expires_and_restart_cannot_replay(tmp_path, clock):
    c, stream, saved, now, policy = setup_controller(tmp_path, clock)
    tmp_path.chmod(0o700)
    policy.update(mode="PROOF", valid_from=now[0].isoformat(),
                  valid_until=(now[0]+timedelta(seconds=60)).isoformat(), symbols=["A", "B"])
    assert c.step()["subscription"]["desired_count"] == 1
    now[0] += timedelta(seconds=20); clock[0] += 20
    assert c.step()["subscription"]["desired_count"] == 2
    now[0] += timedelta(seconds=20); clock[0] += 20
    assert c.step()["subscription"]["desired_count"] == 1
    c._persist(c.last_receipt)
    assert (tmp_path / "policy.json.proof.ndjson").exists()
    now[0] += timedelta(seconds=20); clock[0] += 20
    assert c.step()["readiness"] == "BLOCKED"
    assert stream._desired_symbols() == ("OLD",)
    rebuilt = live.LiveGroupController(c.settings, stream, clock=lambda: now[0]-timedelta(seconds=60),
                                       policy_reader=c.policy_reader)
    assert rebuilt.step()["readiness"] == "BLOCKED"


def test_off_start_has_no_file_db_or_thread_side_effect(tmp_path):
    c = live.LiveGroupController(SimpleNamespace(r2d2_v2_live_policy_file="", r2d2_v2_live_policy_sha=""), None)
    c.start()
    assert c.thread is None and list(tmp_path.iterdir()) == []


def test_real_policy_hash_window_and_attestations(tmp_path, monkeypatch):
    now = datetime(2026, 9, 17, 14, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(live, "current_package_sha", lambda: "b"*64)
    p = {"schema": "R2D2_V2_LIVE_POLICY_V1", "order_sha": live.ORDER_SHA,
         "mode": "PROOF", "capacity": 10, "package_sha": "b"*64, "code_revision": "c"*40,
         "c8_receipt_sha": "d"*64, "head_go_sha": "e"*64, "causal_list_receipt_sha": "f"*64,
         "symbols": ["A", "B"], "list_sha": digest(["A", "B"]),
         "valid_from": now.isoformat(), "valid_until": (now+timedelta(seconds=60)).isoformat()}
    path = tmp_path / "policy.json"
    data = json.dumps(p).encode(); path.write_bytes(data); path.chmod(0o600)
    settings = SimpleNamespace(r2d2_v2_live_policy_file=str(path),
        r2d2_v2_live_policy_sha=hashlib.sha256(data).hexdigest(), build_sha="c"*40)
    assert live.read_policy(settings, now)["symbols"] == ["A", "B"]
    with pytest.raises(ShadowIntegrityError, match="OUTSIDE"):
        live.read_policy(settings, now+timedelta(seconds=60))
    path.write_bytes(data+b" ")
    with pytest.raises(ShadowIntegrityError, match="HASH"):
        live.read_policy(settings, now)


def test_existing_socket_loop_sends_group_and_counts_actual_payloads(clock, monkeypatch):
    import asyncio
    stream = streams.EodhdRealtimeStream("synthetic-no-network")
    stream.set_v2_group(["SYNTH"], capacity=1, ttl=15)
    sent = []

    class Socket:
        def __init__(self): self.n = 0
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def send(self, message): sent.append(json.loads(message))
        async def recv(self):
            self.n += 1
            if self.n == 1: return '{"status_code":200}'
            stream._stop.set()
            return json.dumps({"s":"SYNTH", "t":1789470000000, "bp":101, "ap":102})

    monkeypatch.setattr(streams.websockets, "connect", lambda *a, **kw: Socket())
    observed = []
    original = stream._record_quote
    def capture_receipt(payload):
        original(payload)
        observed.append(stream.v2_status())
    asyncio.run(stream._run_feed("quote", "us-quote", capture_receipt))
    assert sent == [{"action":"subscribe", "symbols":"SYNTH"}]
    assert observed[0]["feeds"]["quote"]["received_count"] == 1
    assert observed[0]["feeds"]["quote"]["sent_count"] == 1
    assert observed[0]["provider_ack_verified"] is False
    assert stream.v2_status()["feeds"] == {}  # STOP clears connection evidence.


def test_thread_start_failure_does_not_escape_into_worker(tmp_path, monkeypatch):
    stream = streams.EodhdRealtimeStream("")
    settings = SimpleNamespace(r2d2_v2_live_policy_file=str(tmp_path/'policy'), r2d2_v2_live_policy_sha="a"*64)
    c = live.LiveGroupController(settings, stream)
    def fail(*a): raise RuntimeError("synthetic")
    monkeypatch.setattr(live.Thread, "start", fail)
    c.start()
    assert stream.v2_status()["desired_count"] == 0


def test_capacity_refusal_keeps_reason_and_withdrawal_evidence(tmp_path, clock):
    c, stream, saved, now, policy = setup_controller(tmp_path, clock)
    c.step()
    policy["capacity"] = 1
    receipt = c.step()
    assert receipt["status"] == "V2_CAPACITY_EXCEEDED"
    assert receipt["subscription"]["status"] == "CAPACITY_EXCEEDED"
    assert receipt["subscription"]["withdrawals"][-1]["reason"] == "CAPACITY_EXCEEDED"


def test_withdrawal_evidence_survives_drop_and_records_actual_send(clock):
    stream = streams.EodhdRealtimeStream("")
    stream.set_v2_group(["SYNTH"], capacity=2, ttl=15)
    stream._set_feed_state("quote", "connected")
    stream._v2_sent("quote", {"SYNTH"}, stream._v2_generation)
    stream._v2_received("quote", "SYNTH")
    stream.set_group("r2d2-v2-live", [])
    stream._v2_unsubscribed("quote", {"SYNTH"})
    receipt = stream.v2_status()["withdrawals"][-1]
    assert receipt["feeds_before"]["quote"]["received_count"] == 1
    assert receipt["unsubscribe_sent"]["quote"]["count"] == 1
    assert "SYNTH" not in json.dumps(receipt)


def test_live_journal_and_stale_temporary_file(tmp_path, clock):
    c, stream, saved, now, policy = setup_controller(tmp_path, clock)
    tmp_path.chmod(0o700)
    (tmp_path / 'policy.json.status.json.tmp').write_text('stale')
    receipt = c.step()
    c._persist(receipt)
    c._persist(receipt)
    assert len((tmp_path / 'policy.json.live.ndjson').read_text().splitlines()) == 2
    assert stream.v2_status()["desired_count"] == 1


def test_stop_event_checked_inside_stream_lock(clock):
    from threading import Event
    stream = streams.EodhdRealtimeStream("")
    stopped = Event(); stopped.set()
    with pytest.raises(ValueError, match="LIVE_CONTROLLER_STOPPED"):
        stream.set_v2_group(["SYNTH"], capacity=1, ttl=15, stop_event=stopped)
    assert stream.v2_status()["desired_count"] == 0


def test_proof_can_start_after_one_poll_plus_small_io_delay(tmp_path, clock):
    c, stream, saved, now, policy = setup_controller(tmp_path, clock)
    tmp_path.chmod(0o700)
    policy.update(mode="PROOF", valid_from=now[0].isoformat(),
                  valid_until=(now[0]+timedelta(seconds=60)).isoformat(), symbols=["A", "B"])
    now[0] += timedelta(seconds=5.1)
    assert c.step()["status"] == "SUBSCRIPTION_REQUESTED"
    assert c.proof_used
