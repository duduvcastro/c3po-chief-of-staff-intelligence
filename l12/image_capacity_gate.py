"""Pure bridge from the finite core to the reviewed image capacity candidate.

The snapshot reader and its independent provenance/scope verifier are required
callbacks; this module supplies neither host/DB access nor a default acceptance.
Before the reader, daily_capacity + journal + manifest + ready + session root
are required. sessions.capacity_binding is first required AFTER its first cycle.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

import image_path_adapter as image
from finite_batch import EPOCH, DAY, Hold, accepted, instant, need


@dataclass(frozen=True)
class Snapshot:
    receipt_raw: bytes
    row_raw: bytes
    records_raw: bytes
    manifest: image.FileEvidence
    ready: image.FileEvidence
    session_manifest: image.FileEvidence
    session_root: image.DirectoryPin
    observed_at: datetime


class ImageCapacityGate:
    def __init__(self, scope, snapshot_read, snapshot_verify, *, clock=None):
        need(isinstance(scope, image.Scope), "IMAGE_SCOPE_UNBOUND")
        self.scope = scope.validate()
        self.scope_hash = self.scope.scope_sha256
        self.snapshot_read, self.snapshot_verify = snapshot_read, snapshot_verify
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def __call__(self, plan, phase, now):
        need(phase in ("BEFORE_FIRST_READER", "AFTER_FIRST_CYCLE"), "IMAGE_GATE_PHASE_INVALID")
        need(self.scope.scope_sha256 == self.scope_hash and self.scope.epoch == plan["epoch"] == EPOCH
             and self.scope.day == plan["session"] == DAY
             and self.scope.finite_authority_sha256 == plan["authority_sha256"], "IMAGE_GATE_SCOPE_CHANGED")
        need(callable(self.snapshot_read), "REAL_IMAGE_SNAPSHOT_READER_UNAVAILABLE")
        snapshot = self.snapshot_read(self.scope, phase, now)
        need(isinstance(snapshot, Snapshot), "REAL_IMAGE_SNAPSHOT_UNAVAILABLE")
        current, observed = instant(self.clock()), instant(snapshot.observed_at)
        need(observed <= current and (current - observed).total_seconds() <= 5, "IMAGE_SNAPSHOT_NOT_FRESH")
        # This verifier must attest a single real consistent read_with_journal,
        # original writer receipt, held file/ancestor identities, current image
        # binding authority, runtime/revocations, and exact source pins.
        accepted(self.snapshot_verify, snapshot, self.scope, phase, current)
        # Snapshot transport/verifier may be slow: use the actual post-callback
        # instant for ready/open-minus-ten checks and freshness, not entry time.
        current = instant(self.clock())
        need(observed <= current and (current - observed).total_seconds() <= 5, "IMAGE_SNAPSHOT_NOT_FRESH")
        try:
            receipt = image.strict_json(snapshot.receipt_raw)
            row = image.strict_json(snapshot.row_raw, limit=image.DB_READBACK_LIMIT)
            records = image.strict_json(snapshot.records_raw, limit=image.DB_READBACK_LIMIT)
            if phase == "BEFORE_FIRST_READER":
                image.reader_gate(self.scope, receipt, row, records, snapshot.manifest, snapshot.ready,
                                  snapshot.session_manifest, snapshot.session_root, now=current)
            else:
                image.check_capacity_manifest(self.scope, receipt, row, records, snapshot.manifest,
                                              require_session_binding=True)
        except image.Hold as error:
            raise Hold(str(error)) from None
        return None
