"""C6 phase gate using a limited, independently verified native DB projection.

Old full-snapshot ImageCapacityGate remains separately available. This new ABI
does not reinterpret old full-journal bytes as a compact snapshot or invent a
checkpoint. Runtime/FD/clock/authority/complete-chain proof remain mandatory.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import image_path_adapter as image
from image_capacity_gate import ImageCapacityGate, PHASE_OPERATIONS, _TimeBudget
from finite_batch import EPOCH,DAY,Hold,accepted,canonical,instant,need,validate_plan
from bounded_readback import BoundedReadbackDecoder,WIRE_LIMIT


@dataclass(frozen=True)
class BoundedSnapshot:
    receipt_raw:bytes
    readback_raw:bytes
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


class BoundedImageCapacityGate(ImageCapacityGate):
    def __init__(self,scope,snapshot_read,snapshot_verify,*,journal_directory,
                 readback_rule_raw,readback_rule_sha256,rule_verifier,readback_verifier,
                 request_sha256,bound_sha256,read_authority_raw,mode='REAL',clock=None):
        super().__init__(scope,snapshot_read,snapshot_verify,
                         journal_directory=journal_directory,clock=clock)
        self.decoder=BoundedReadbackDecoder(readback_rule_raw,readback_rule_sha256,
            rule_verifier,readback_verifier,request_sha256=request_sha256,
            bound_sha256=bound_sha256,read_authority_raw=read_authority_raw,mode=mode)

    def __call__(self,plan,phase,now,task):
        need(phase in PHASE_OPERATIONS,'IMAGE_GATE_PHASE_INVALID')
        need(validate_plan(canonical(plan))==plan and task in plan['tasks']
             and task['operation'] in PHASE_OPERATIONS[phase],'IMAGE_GATE_TASK_UNBOUND')
        need(image.sha(canonical(plan))==self.decoder.request_sha256,'BOUNDED_REQUEST_PLAN_CHANGED')
        need(self.scope.scope_sha256==self.scope_hash and self.scope.epoch==plan['epoch']==EPOCH
             and self.scope.day==plan['session']==DAY
             and self.scope.finite_authority_sha256==plan['authority_sha256'],'IMAGE_GATE_SCOPE_CHANGED')
        timing=_TimeBudget(task)
        current=timing.check()
        self.decoder.authorize(self.scope,phase,now=current,plan=plan,task=task)
        current=timing.check()
        need(callable(self.snapshot_read),'REAL_IMAGE_SNAPSHOT_READER_UNAVAILABLE')
        snapshot=self.snapshot_read(self.scope,phase,current)
        current=timing.check()
        need(type(snapshot)is BoundedSnapshot,'BOUNDED_IMAGE_SNAPSHOT_REQUIRED')
        need(type(snapshot.readback_raw)is bytes and 0<len(snapshot.readback_raw)<=WIRE_LIMIT,
             'BOUNDED_IMAGE_SNAPSHOT_SIZE_LIMIT')
        current=timing.observe(snapshot.observed_at)
        # Files/ancestors/mount namespace/runtime/revocations/calendar remain
        # exactly the old snapshot-verifier duty. The separate new readback
        # verifier owns integral DB origin/chain/selection/absence proof.
        accepted(self.snapshot_verify,snapshot,self.scope,phase,current,plan,task)
        current=timing.check()
        try:
            decoded=self.decoder.decode(snapshot.readback_raw,self.scope,phase,
                            now=current,plan=plan,task=task)
            need(decoded.observed_at==instant(snapshot.observed_at),'BOUNDED_OBSERVATION_CHANGED')
            current=timing.check()
            receipt=image.strict_json(snapshot.receipt_raw)
            image.journal_root_gate(self.scope,snapshot.epoch_catalog,snapshot.journal_root,
                     settings_journal_directory=snapshot.settings_journal_directory,
                     expected_journal_directory=self.journal_directory)
            args=self.scope,receipt,decoded.row,decoded.journal,snapshot.manifest
            if phase=='BEFORE_READER_PROCESS_LAUNCH':
                image.reader_process_launch_gate(*args,now=current)
            elif phase=='BEFORE_FIRST_READER':
                need(snapshot.ready is not None and snapshot.session_manifest is not None
                     and snapshot.session_root is not None,'IMAGE_SESSION_EVIDENCE_MISSING')
                need(snapshot.calendar_pin_sha256==self.scope.calendar_pin_sha256
                     and snapshot.session_close is not None,'IMAGE_CALENDAR_CLOSE_UNBOUND')
                image.reader_gate(*args,snapshot.ready,snapshot.session_manifest,snapshot.session_root,
                     now=current,not_before=instant(task['not_before']),not_after=instant(task['not_after']),
                     session_close=instant(snapshot.session_close))
            elif phase=='AFTER_FIRST_CYCLE':image.after_first_cycle_gate(*args,now=current)
            elif phase=='BEFORE_CAPTURE_LAUNCH':
                image.capture_launch_gate(*args,now=current,not_before=instant(task['not_before']),
                                          not_after=instant(task['not_after']))
            else:image.after_capture_gate(*args,now=current)
        except image.Hold as error:raise Hold(str(error)) from None
        timing.check()
        return None
