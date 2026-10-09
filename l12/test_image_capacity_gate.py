"""NEW bridge fixtures: bytes only, no image/store/host/SQL/transport/owner."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path
import os
import tempfile
import unittest

import finite_batch as f
import image_capacity_gate as bridge
import image_path_adapter as image
from test_finite_batch import Fixture

OPEN = datetime(2026, 10, 12, 13, 30, tzinfo=timezone.utc)
NOW = OPEN - timedelta(hours=2)


def fixture(copied=False):
    # Every pin below hashes an explicitly synthetic literal; none is an
    # operational hash, human record, host identity or binding authorization.
    x = Fixture()
    digest = lambda name: f.sha(("SYNTHETIC_" + name).encode("ascii"))
    scope = image.Scope(build_sha=sha1(b"SYNTHETIC_BUILD").hexdigest(),
                        image_id="sha256:" + digest("IMAGE"), document_order_sha256=digest("ORDER"),
                        release_sha256=digest("RELEASE"), package_sha256=digest("PACKAGE"),
                        capacity_config_sha256=digest("CONFIG"), calendar_pin_sha256=digest("CALENDAR"),
                        runtime_authority_sha256=digest("RUNTIME_AUTHORITY"),
                        finite_authority_sha256=x.q["authority_sha256"], owner_uid=1000,
                        manifest_directory="/SYNTHETIC_NOT_HOST_MANIFESTS", session_open=OPEN,
                        not_before=NOW - timedelta(seconds=1), not_after=NOW + timedelta(seconds=8),
                        view_opens_at=NOW, require_go_mode="DELEGATED_ACT_B")
    doc = {"schema": "V2_DAILY_CAPACITY_BINDING_CANDIDATE_V1", "epoch": scope.epoch,
           "day": scope.day, "release_sha": scope.release_sha256,
           "monitored_symbols": ["FIXA", "FIXB"], "contract": {"SYNTHETIC_NOT_AUTHORITY": True}}
    binding = {"sha": image.digest(doc), "document": doc}
    state = {"epoch": scope.epoch, "release_sha": scope.release_sha256,
             "daily_capacity": {scope.day: binding}, "sessions": {}}
    if copied:
        state["sessions"][scope.day] = {"capacity_binding": deepcopy(binding)}
    payload = {"journal_key": "capacity-prepared:" + scope.day, "type": "CAPACITY_DAY_PREPARED",
               "session": scope.day, "plan_sha": binding["sha"], "payload": doc}
    record = {"epoch": scope.epoch, "sequence": 1, "journal_key": payload["journal_key"],
              "recorded_at": NOW.isoformat(), "payload": payload, "previous_sha": ""}
    record["record_sha"] = image.digest(record)
    records = [record]
    if copied:
        payload2 = {"journal_key": "SYNTHETIC_FIRST_READER_CYCLE", "type": "SYNTHETIC_NOT_EXECUTED",
                    "session": scope.day, "capacity_binding": deepcopy(binding)}
        second = {"epoch": scope.epoch, "sequence": 2, "journal_key": payload2["journal_key"],
                  "recorded_at": NOW.isoformat(), "payload": payload2, "previous_sha": record["record_sha"]}
        second["record_sha"] = image.digest(second)
        records.append(second)
    row = {"state": state, "state_sha": image.digest(state), "journal_head": records[-1]["record_sha"]}
    def file(value, inode):
        return image.FileEvidence(image.canonical(value), 900, inode, scope.owner_uid, 1000, 0o600, 1)
    manifest = file({"epoch": scope.epoch, "session": scope.day, "symbols": doc["monitored_symbols"],
                     "owner_uid": scope.owner_uid}, 901)
    receipt = {"fixture": "SYNTHETIC_NOT_IMAGE_RECEIPT", "schema": "R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1",
               "status": "PUBLISHED_VERIFIED", "code": None, "mode": "PUBLISH", "epoch": scope.epoch,
               "session": scope.day, "owner_uid": scope.owner_uid, "build_sha": scope.build_sha,
               "release_sha256": scope.release_sha256, "package_sha256": scope.package_sha256,
               "capacity_config_sha256": scope.capacity_config_sha256,
               "capacity_veto_mode": "DISPATCH_AND_DERIVATION_ONLY", "massive_bars_enabled": True,
               "cutoff_at": (OPEN - timedelta(minutes=10)).isoformat(), "go_mode": scope.require_go_mode,
               "go_sha256": digest("GO_FIXTURE_NOT_ACT"), "template_sha256": digest("TEMPLATE"),
               "binding_sha256": binding["sha"], "manifest_sha256": image.sha(manifest.raw), "symbol_count": 2,
               "file": {"uid": manifest.uid, "gid": manifest.gid, "mode": "0600", "nlink": 1,
                        "device": manifest.device, "inode": manifest.inode, "size_within_limit": True},
               "view": {"observed_at": NOW.isoformat(), "valid_until": (NOW + timedelta(seconds=5)).isoformat()}}
    root = image.DirectoryPin(900, 999, scope.owner_uid)
    ready = file({"epoch": scope.epoch, "session": scope.day}, 902)
    catalog = file({"schema": "MASSIVE_SESSION_V1", "epoch": scope.epoch, "session": scope.day,
                    "symbols": doc["monitored_symbols"], "device": root.device, "inode": root.inode}, 903)
    snapshot = bridge.Snapshot(image.canonical(receipt), image.canonical(row), image.canonical(records),
                               manifest, ready, catalog, root, NOW)
    return x, scope, snapshot


def fixture_verify(snapshot, *args):
    f.need(image.strict_json(snapshot.receipt_raw).get("fixture") == "SYNTHETIC_NOT_IMAGE_RECEIPT",
           "FIXTURE_IMAGE_ORIGINAL_INVALID")


class TestNewImageCapacityBridge(unittest.TestCase):
    def test_before_first_reader_does_not_create_binding_cycle(self):
        x, scope, snapshot = fixture(False)
        gate = bridge.ImageCapacityGate(scope, lambda *args: snapshot, fixture_verify, clock=lambda: NOW)
        self.assertIsNone(gate(x.q, "BEFORE_FIRST_READER", NOW))
        with self.assertRaisesRegex(f.Hold, "DB_SESSION_BINDING_MISSING_OR_CHANGED"):
            gate(x.q, "AFTER_FIRST_CYCLE", NOW)

    def test_after_first_cycle_requires_exact_persisted_copy(self):
        x, scope, snapshot = fixture(True)
        gate = bridge.ImageCapacityGate(scope, lambda *args: snapshot, fixture_verify, clock=lambda: NOW)
        self.assertIsNone(gate(x.q, "AFTER_FIRST_CYCLE", NOW))
        row = image.strict_json(snapshot.row_raw)
        row["state"]["sessions"][scope.day]["capacity_binding"]["sha"] = f.sha(b"SYNTHETIC_WRONG_COPY")
        row["state_sha"] = image.digest(row["state"])
        bad = replace(snapshot, row_raw=image.canonical(row))
        gate.snapshot_read = lambda *args: bad
        with self.assertRaisesRegex(f.Hold, "DB_SESSION_BINDING_MISSING_OR_CHANGED"):
            gate(x.q, "AFTER_FIRST_CYCLE", NOW)

    def test_missing_real_snapshot_verifier_is_closed(self):
        x, scope, snapshot = fixture()
        gate = bridge.ImageCapacityGate(scope, lambda *args: snapshot, None, clock=lambda: NOW)
        with self.assertRaisesRegex(f.Hold, "REAL_ADAPTER_UNAVAILABLE"):
            gate(x.q, "BEFORE_FIRST_READER", NOW)

    def test_delayed_snapshot_is_not_fresh(self):
        x, scope, snapshot = fixture()
        gate = bridge.ImageCapacityGate(scope, lambda *args: snapshot, fixture_verify,
                                        clock=lambda: NOW + timedelta(seconds=6))
        with self.assertRaisesRegex(f.Hold, "IMAGE_SNAPSHOT_NOT_FRESH"):
            gate(x.q, "BEFORE_FIRST_READER", NOW + timedelta(seconds=6))

    def test_manifest_inode_tamper_is_not_the_original_receipt_file(self):
        x, scope, snapshot = fixture()
        bad = replace(snapshot, manifest=replace(snapshot.manifest, inode=111111))
        gate = bridge.ImageCapacityGate(scope, lambda *args: bad, fixture_verify, clock=lambda: NOW)
        with self.assertRaisesRegex(f.Hold, "MANIFEST_READBACK_IDENTITY_MISMATCH"):
            gate(x.q, "BEFORE_FIRST_READER", NOW)

    def test_changed_authority_scope_is_not_delegated(self):
        x, scope, snapshot = fixture()
        gate = bridge.ImageCapacityGate(scope, lambda *args: snapshot, fixture_verify, clock=lambda: NOW)
        x.q["authority_sha256"] = f.sha(b"SYNTHETIC_OTHER_AUTHORITY")
        with self.assertRaisesRegex(f.Hold, "IMAGE_GATE_SCOPE_CHANGED"):
            gate(x.q, "BEFORE_FIRST_READER", NOW)

    def test_real_db_shape_is_not_limited_to_manifest_64k(self):
        x, scope, snapshot = fixture()
        row = image.strict_json(snapshot.row_raw)
        records = image.strict_json(snapshot.records_raw)
        row["state"]["historical_fixture_padding"] = "F" * 70000
        records[0]["payload"]["source_evidence_fixture_padding"] = "F" * 70000
        records[0]["record_sha"] = image.digest({k: v for k, v in records[0].items() if k != "record_sha"})
        row["state_sha"] = image.digest(row["state"])
        row["journal_head"] = records[0]["record_sha"]
        snapshot = replace(snapshot, row_raw=image.canonical(row), records_raw=image.canonical(records))
        self.assertGreater(len(snapshot.row_raw), image.LIMIT)
        self.assertGreater(len(snapshot.records_raw), image.LIMIT)
        gate = bridge.ImageCapacityGate(scope, lambda *args: snapshot, fixture_verify, clock=lambda: NOW)
        self.assertIsNone(gate(x.q, "BEFORE_FIRST_READER", NOW))

    def test_snapshot_verification_delay_is_checked_after_callback(self):
        x, scope, snapshot = fixture()
        current = [NOW]
        def verify(*args):
            fixture_verify(*args)
            current[0] += timedelta(seconds=6)
        gate = bridge.ImageCapacityGate(scope, lambda *args: snapshot, verify, clock=lambda: current[0])
        with self.assertRaisesRegex(f.Hold, "IMAGE_SNAPSHOT_NOT_FRESH"):
            gate(x.q, "BEFORE_FIRST_READER", NOW)

    def test_slow_snapshot_callback_cannot_cross_open_minus_ten(self):
        x, scope, snapshot = fixture()
        before_cutoff = OPEN - timedelta(seconds=12)
        # The writer's earlier manifest window remains immutable. A later fresh
        # reader readback may approach its separate open-minus-ten cutoff.
        snapshot = replace(snapshot, observed_at=before_cutoff)
        current = [before_cutoff]
        def read(*args):
            current[0] += timedelta(seconds=2)
            return snapshot
        gate = bridge.ImageCapacityGate(scope, read, fixture_verify, clock=lambda: current[0])
        with self.assertRaisesRegex(f.Hold, "READER_READY_WINDOW_CLOSED"):
            gate(x.q, "BEFORE_FIRST_READER", before_cutoff)

    def test_core_uses_pure_bridge_on_each_side_of_first_reader_effect(self):
        x, scope, before = fixture(False)
        _, _, after = fixture(True)
        x.now = NOW
        for task in x.q["tasks"]:
            task["not_before"] = f.iso(NOW)
            task["not_after"] = f.iso(NOW + timedelta(hours=1))
        x.rebuild()
        for role in ("e6", "admission_manifest", "post", "reader_bound"):
            x.receipts[role] = x.original(role, NOW - timedelta(hours=1))
        phases = []
        def snapshot_read(scope, phase, now):
            phases.append(phase)
            item = before if phase == "BEFORE_FIRST_READER" else after
            return replace(item, observed_at=now)
        gate = bridge.ImageCapacityGate(scope, snapshot_read, fixture_verify, clock=lambda: x.now)
        with tempfile.TemporaryDirectory(prefix="synthetic-bridge-", dir=Path(__file__).parent) as root:
            os.chmod(root, 0o700)
            path = Path(root) / "attempts.ledger"
            path.write_bytes(b"")
            os.chmod(path, 0o600)
            ledger = f.DurableLedger(root, f.measure_local_ledger(root))
            try:
                batch = f.FiniteBatch(x.bundle, ledger, replace(x.services, capacity_path=gate),
                                      clock=lambda: x.now, monotonic=lambda: x.ticks)
                result = batch.run("reader_cycle")
            finally:
                ledger.close()
        self.assertEqual(result["status"], "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE", result)
        self.assertEqual(result["effect_calls"], 1)
        self.assertEqual(phases, ["BEFORE_FIRST_READER", "AFTER_FIRST_CYCLE"])


if __name__ == "__main__":
    unittest.main()
