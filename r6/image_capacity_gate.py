"""C6 bridge candidate: phases from actual image chronology, no DB/host reader.

PRE_OPEN process launch needs daily capacity/journal/manifest/epoch root, not
ready or session copy. The first SESSION transition separately needs ready,
session catalog and the actual accepted calendar window; a pre-launch check
cannot intercept the OPS launcher's later internal transition. Case B can lack
the copy until actual capture; AFTER_CAPTURE requires exact copy after verified
COMPLETE original. No callbacks default to acceptance or emit operational GO.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
import time
import image_path_adapter as image
from finite_batch import EPOCH,DAY,Hold,accepted,canonical,instant,need,validate_plan

PHASE_OPERATIONS={"BEFORE_READER_PROCESS_LAUNCH":{"reader_bound"},
                  "BEFORE_FIRST_READER":{"reader_cycle"},
                  "AFTER_FIRST_CYCLE":{"reader_cycle"},
                  "BEFORE_CAPTURE_LAUNCH":{"capture_launch"},
                  "AFTER_CAPTURE":{"capture_launch","capture_result"}}

@dataclass(frozen=True)
class Snapshot:
    receipt_raw:bytes
    row_raw:bytes
    records_raw:bytes
    manifest:image.FileEvidence
    observed_at:datetime
    epoch_catalog:image.FileEvidence
    journal_root:image.DirectoryPin
    settings_journal_directory:str
    ready:image.FileEvidence|None=None
    session_manifest:image.FileEvidence|None=None
    session_root:image.DirectoryPin|None=None
    session_close:datetime|None=None
    calendar_pin_sha256:str|None=None

def _native_utc():
    # Operational clocks are source-owned. Test-only monkeypatches are fixtures,
    # never independent evidence of a live namespace or physical UTC clock.
    return datetime.now(timezone.utc)

class _TimeBudget:
    def __init__(self,task):
        self.start_wall=instant(_native_utc());self.start_mono=time.monotonic()
        self.last_wall=self.start_wall;self.last_mono=self.start_mono
        self.not_before,self.not_after=instant(task["not_before"]),instant(task["not_after"])
        need(self.not_before<=self.start_wall<self.not_after,"IMAGE_TASK_WINDOW_CLOSED")
        self.deadline_mono=self.start_mono+min(task["budget_seconds"],
                              (self.not_after-self.start_wall).total_seconds())
        self.observed=None;self.fresh_deadline_mono=None
    def check(self):
        current,mark=instant(_native_utc()),time.monotonic()
        need(current>=self.last_wall and mark>=self.last_mono,"IMAGE_CLOCK_REGRESSION")
        self.last_wall,self.last_mono=current,mark
        need(self.not_before<=current<self.not_after,"IMAGE_TASK_WINDOW_CLOSED")
        need(mark<self.deadline_mono,"IMAGE_GATE_DEADLINE")
        if self.observed is not None:
            need(self.observed<=current and (current-self.observed).total_seconds()<=5
                 and mark<self.fresh_deadline_mono,"IMAGE_SNAPSHOT_NOT_FRESH")
        return current
    def observe(self,observed_at):
        current=self.check();observed=instant(observed_at)
        need(observed<=current and (current-observed).total_seconds()<=5,"IMAGE_SNAPSHOT_NOT_FRESH")
        self.observed=observed
        # Remaining freshness is measured by BOTH UTC and monotonic elapsed time.
        # A frozen/backward wall clock cannot extend a captured view's lifetime.
        self.fresh_deadline_mono=self.last_mono+5-(current-observed).total_seconds()
        return self.check()

class ImageCapacityGate:
    def __init__(self,scope,snapshot_read,snapshot_verify,*,journal_directory,clock=None):
        need(clock is None,"IMAGE_CLOCK_INJECTION_FORBIDDEN")
        need(isinstance(scope,image.Scope),"IMAGE_SCOPE_UNBOUND")
        self.scope=scope.validate();self.scope_hash=self.scope.scope_sha256
        need(type(journal_directory) is str,"IMAGE_JOURNAL_DIRECTORY_UNBOUND")
        path=Path(journal_directory)
        need(type(journal_directory) is str and path.is_absolute() and str(path)==journal_directory
             and ".." not in path.parts,"IMAGE_JOURNAL_DIRECTORY_UNBOUND")
        self.journal_directory=journal_directory
        self.snapshot_read,self.snapshot_verify=snapshot_read,snapshot_verify
    def __call__(self,plan,phase,now,task):
        need(phase in PHASE_OPERATIONS,"IMAGE_GATE_PHASE_INVALID")
        need(validate_plan(canonical(plan))==plan and task in plan["tasks"]
             and task["operation"] in PHASE_OPERATIONS[phase],"IMAGE_GATE_TASK_UNBOUND")
        need(self.scope.scope_sha256==self.scope_hash and self.scope.epoch==plan["epoch"]==EPOCH
             and self.scope.day==plan["session"]==DAY
             and self.scope.finite_authority_sha256==plan["authority_sha256"],"IMAGE_GATE_SCOPE_CHANGED")
        timing=_TimeBudget(task)
        current=timing.check()
        need(callable(self.snapshot_read),"REAL_IMAGE_SNAPSHOT_READER_UNAVAILABLE")
        snapshot=self.snapshot_read(self.scope,phase,current)
        current=timing.check()
        need(isinstance(snapshot,Snapshot),"REAL_IMAGE_SNAPSHOT_UNAVAILABLE")
        need(type(snapshot.row_raw) is bytes and type(snapshot.records_raw) is bytes
             and 0<len(snapshot.row_raw)<=image.DB_READBACK_LIMIT
             and 0<len(snapshot.records_raw)<=image.DB_READBACK_LIMIT
             and len(snapshot.row_raw)+len(snapshot.records_raw)<=image.DB_SNAPSHOT_LIMIT,
             "IMAGE_SNAPSHOT_SIZE_LIMIT")
        current=timing.observe(snapshot.observed_at)
        # Required real verifier: one consistent read_with_journal, writer
        # original, exact held files/ancestors/settings/mount namespace, scope,
        # source/runtime/revocations and calendar close against pinned calendar.
        accepted(self.snapshot_verify,snapshot,self.scope,phase,current,plan,task)
        current=timing.check()
        try:
            receipt=image.strict_json(snapshot.receipt_raw)
            row=image.strict_json(snapshot.row_raw,limit=image.DB_READBACK_LIMIT)
            # Decode one original record at a time; the phase gate still
            # verifies every record, epoch/sequence/key/hash and final head.
            records=image.parse_journal(snapshot.records_raw)
            image.journal_root_gate(self.scope,snapshot.epoch_catalog,snapshot.journal_root,
                     settings_journal_directory=snapshot.settings_journal_directory,
                     expected_journal_directory=self.journal_directory)
            args=self.scope,receipt,row,records,snapshot.manifest
            if phase=="BEFORE_READER_PROCESS_LAUNCH":
                image.reader_process_launch_gate(*args,now=current)
            elif phase=="BEFORE_FIRST_READER":
                need(snapshot.ready is not None and snapshot.session_manifest is not None
                     and snapshot.session_root is not None,"IMAGE_SESSION_EVIDENCE_MISSING")
                need(snapshot.calendar_pin_sha256==self.scope.calendar_pin_sha256
                     and snapshot.session_close is not None,"IMAGE_CALENDAR_CLOSE_UNBOUND")
                image.reader_gate(*args,snapshot.ready,snapshot.session_manifest,snapshot.session_root,
                     now=current,not_before=instant(task["not_before"]),not_after=instant(task["not_after"]),
                     session_close=instant(snapshot.session_close))
            elif phase=="AFTER_FIRST_CYCLE":image.after_first_cycle_gate(*args,now=current)
            elif phase=="BEFORE_CAPTURE_LAUNCH":
                image.capture_launch_gate(*args,now=current,not_before=instant(task["not_before"]),
                                           not_after=instant(task["not_after"]))
            else:image.after_capture_gate(*args,now=current)
        except image.Hold as error:raise Hold(str(error)) from None
        # Large snapshots and full-chain hashing consume real time too. Never
        # certify a stale view merely because the verifier returned promptly.
        current=timing.check()
        return None
