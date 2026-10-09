"""L12 R3 POSIX outer limiter candidate; no host/app/authority/installer.

A fixed DurableLedger claim is persisted in the parent before fork and before
ANY supplied callback. One supervised session owns one run_reserved operation.
ALL core callbacks, including clock and the inner transport, execute there.
Success needs complete packet, bounded whole-group cleanup, final wall/monotonic
window/deadline and parent terminal ledger. Timeout/loss/torn ledger consumes.

Only descendants which remain in this session/process group are contained.
Use the separately pinned inner runner INHERITED_OUTER_GROUP variant; OWN_SESSION
escapes outer killpg and is not certified by this candidate. A real kernel
containment/runtime package is still required. Under the selected same-disk ledger,
rollback of that disk cannot be independently detected by this candidate. Durable parent claim and
terminal fsync are native storage primitives: an OS-blocked filesystem cannot
be promised a hard realtime bound by this user-space candidate.
"""
from datetime import datetime,timezone
import hashlib,json,math,os,selectors,signal,stat,struct,threading,time
from pathlib import Path
import finite_batch as c

MAX_PACKET=16384
TICK=.01
STATUSES={"REFUSED_CONSUMED","UNCERTAIN_CONSUMED","ORIGINAL_COMPLETE_OBSERVED_CANDIDATE"}

def now():return datetime.now(timezone.utc)
def source_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class OuterLimiter:
    def __init__(self,*,core_sha256,outer_sha256,hard_budget_seconds,cleanup_budget_seconds=.5):
        c.need(c.pin(core_sha256) and c.pin(outer_sha256),"OUTER_SOURCE_PINS_REQUIRED")
        c.need(type(hard_budget_seconds) in (int,float) and math.isfinite(hard_budget_seconds)
               and 0<hard_budget_seconds<=1200,"OUTER_BUDGET_INVALID")
        c.need(type(cleanup_budget_seconds) in (int,float) and math.isfinite(cleanup_budget_seconds)
               and 0<cleanup_budget_seconds<=1,"OUTER_CLEANUP_BUDGET_INVALID")
        self.core_sha256,self.outer_sha256=core_sha256,outer_sha256
        self.hard_budget,self.cleanup_budget=hard_budget_seconds,cleanup_budget_seconds
    def _sources(self):
        c.need(source_sha(c.__file__)==self.core_sha256 and source_sha(__file__)==self.outer_sha256,"OUTER_SOURCE_PIN_CHANGED")
    @staticmethod
    def _send(fd,payload):
        raw=c.canonical(payload);c.need(len(raw)<=MAX_PACKET,"OUTER_PACKET_LIMIT")
        framed=struct.pack("!I",len(raw))+raw;offset=0
        while offset<len(framed):
            n=os.write(fd,framed[offset:]);c.need(n>0,"OUTER_PACKET_WRITE_UNCERTAIN");offset+=n
    def _worker(self,batch,op,key,write_fd,deadline):
        os.setsid()
        # No supplied callback runs before an independent same-group watchdog
        # exists. It survives a lost outer parent and cannot be parked by a
        # blocking native call in the callback worker's Python interpreter.
        group=os.getpgrp();dog=os.fork()
        if dog==0:
            os.close(write_fd)
            until=deadline
            while time.monotonic()<until:time.sleep(min(.01,max(.001,until-time.monotonic())))
            try:os.killpg(group,signal.SIGKILL)
            finally:os._exit(1)
        try:
            result=batch.run_reserved(op,key,terminal=False)
            self._send(write_fd,{"schema":"L12_OUTER_WORKER_PACKET_CANDIDATE_V1","operation":op,
                                 "attempt_key":key,"result":result})
        except BaseException:
            try:self._send(write_fd,{"schema":"L12_OUTER_WORKER_PACKET_CANDIDATE_V1","operation":op,
                                     "attempt_key":key,"failure":"WORKER_UNCERTAIN"})
            except BaseException:pass
        finally:
            os.close(write_fd)
        # Keep session leader alive so parent unconditionally terminates its
        # group even after successful packet delivery; no PID/group reuse gap.
        while True:signal.pause()
    def _cleanup(self,pid):
        uncertain=False
        try:os.killpg(pid,signal.SIGKILL)
        except ProcessLookupError:
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
        except PermissionError:
            uncertain=True
            try:os.kill(pid,signal.SIGKILL)
            except (ProcessLookupError,PermissionError):pass
        until=time.monotonic()+self.cleanup_budget
        while time.monotonic()<until:
            try:found,_=os.waitpid(pid,os.WNOHANG)
            except ChildProcessError:
                c.need(not uncertain,"OUTER_GROUP_CLEANUP_UNCERTAIN");return
            if found==pid:
                c.need(not uncertain,"OUTER_GROUP_CLEANUP_UNCERTAIN");return
            time.sleep(.005)
        raise c.Hold("OUTER_WORKER_REAP_UNCERTAIN")
    @staticmethod
    def _clock_guard(started,mark,last,deadline,task):
        current,wall=time.monotonic(),now()
        c.need(current>=last and abs((wall-started).total_seconds()-(current-mark))<=2,"OUTER_CLOCK_DISCONTINUITY")
        c.need(current<deadline and c.instant(task["not_before"])<=wall<c.instant(task["not_after"]),"OUTER_DEADLINE_OR_WINDOW")
        return current
    def run(self,batch,operation):
        c.need(type(batch) is c.FiniteBatch and type(batch.ledger) is c.DurableLedger,"OUTER_BATCH_TYPE_INVALID")
        matches=[t for t in batch.q["tasks"] if t["operation"]==operation]
        c.need(len(matches)==1,"OPERATION_NOT_IN_FINITE_PLAN")
        task=matches[0];started,mark=now(),time.monotonic()
        # This source-owned, native durable primitive has no supplied callback.
        # If it returns an uncertain/torn/busy claim it is never repeated.
        try:key=batch.reserve(operation)
        except c.ReservationFailure as error:
            return {"schema":"L12_OUTER_RESERVATION_CANDIDATE_V1","status":"REFUSED_CONSUMED" if error.consumed else "REFUSED_NOT_RESERVED",
                    "code":c.code(error),"inner_code":None,"operation":operation,"attempt_key":error.key,"effect_calls":0,
                    "reservation_durable":False,"recovery_required":bool(error.consumed),"automatic_retry":False,
                    "operational_GO_granted":False,"physical_host_certified":False,"worker_cleanup":"NOT_STARTED",
                    "original_receipt_sha256":None,"original_receipt_completed_at":None,"completed_at":c.iso(now())}
        result={"schema":"L12_OUTER_ATTEMPT_CANDIDATE_V1","status":"UNCERTAIN_CONSUMED","code":None,
                "operation":operation,"attempt_key":key,"automatic_retry":False,"effect_calls":None,"inner_code":None,
                "reservation_durable":True,"recovery_required":False,
                "original_receipt_sha256":None,"original_receipt_completed_at":None,"operational_GO_granted":False,"physical_host_certified":False,
                "worker_cleanup":"NOT_STARTED","inner_result":None}
        pid=read_fd=write_fd=None;selector=None;last=mark
        try:
            self._sources()
            c.need(os.name=="posix" and hasattr(os,"fork") and threading.active_count()==1,"OUTER_POSIX_SINGLE_THREAD_REQUIRED")
            c.need(type(task.get("budget_seconds")) in (int,float) and math.isfinite(task["budget_seconds"])
                   and 0<task["budget_seconds"]<=1200,"OUTER_TASK_BUDGET_INVALID")
            deadline=min(mark+self.hard_budget,mark+task["budget_seconds"],
                         mark+(c.instant(task["not_after"])-started).total_seconds())
            last=self._clock_guard(started,mark,last,deadline,task)
            read_fd,write_fd=os.pipe()
            pid=os.fork()
            if pid==0:
                os.close(read_fd)
                try:self._worker(batch,operation,key,write_fd,deadline)
                finally:os._exit(1)
            os.close(write_fd);write_fd=None;os.set_blocking(read_fd,False)
            selector=selectors.DefaultSelector();selector.register(read_fd,selectors.EVENT_READ)
            data=bytearray();size=None
            while size is None or len(data)<size+4:
                last=self._clock_guard(started,mark,last,deadline,task)
                if not selector.select(min(TICK,max(.0001,deadline-time.monotonic()))):continue
                piece=os.read(read_fd,65536)
                c.need(piece,"OUTER_WORKER_LOST")
                data.extend(piece);c.need(len(data)<=MAX_PACKET+4,"OUTER_PACKET_LIMIT")
                if size is None and len(data)>=4:
                    size=struct.unpack("!I",data[:4])[0];c.need(0<size<=MAX_PACKET,"OUTER_PACKET_LIMIT")
            c.need(len(data)==size+4,"OUTER_PACKET_INVALID")
            packet=c.strict(bytes(data[4:]));last=self._clock_guard(started,mark,last,deadline,task)
            c.need(packet.get("schema")=="L12_OUTER_WORKER_PACKET_CANDIDATE_V1" and packet.get("operation")==operation
                   and packet.get("attempt_key")==key,"OUTER_PACKET_INVALID")
            c.need(set(packet)=={"schema","operation","attempt_key","result"},"OUTER_WORKER_UNCERTAIN")
            inner=packet["result"]
            expected={"schema","status","code","inner_code","operation","attempt_key","effect_calls","original_receipt_sha256","original_receipt_completed_at",
                      "automatic_retry","operational_GO_granted","physical_host_certified","completed_at"}
            c.need(type(inner) is dict and set(inner)==expected and inner["schema"]=="L12_LOCAL_ATTEMPT_CANDIDATE_V1"
                   and inner["status"] in STATUSES and inner["operation"]==operation and inner["attempt_key"]==key
                   and inner["automatic_retry"] is False and inner["operational_GO_granted"] is False
                   and inner["physical_host_certified"] is False and type(inner["effect_calls"]) is int
                   and inner["effect_calls"] in (0,1) and (inner["code"] is None or
                   type(inner["code"]) is str and c.CODE.fullmatch(inner["code"]) is not None),"OUTER_PACKET_INVALID")
            if inner["status"]=="ORIGINAL_COMPLETE_OBSERVED_CANDIDATE":
                c.need(inner["effect_calls"]==1 and c.pin(inner["original_receipt_sha256"]),"OUTER_PACKET_INVALID")
                c.need(inner["completed_at"] is not None and started<=c.instant(inner["completed_at"])<=now(),"OUTER_PACKET_INVALID")
            result.update(status=inner["status"],code=inner["code"],effect_calls=inner["effect_calls"],
                          original_receipt_sha256=inner["original_receipt_sha256"],original_receipt_completed_at=inner["original_receipt_completed_at"],inner_result=inner)
        except BaseException as error:
            result["status"],result["code"]="UNCERTAIN_CONSUMED",c.code(error)
        finally:
            if selector is not None:selector.close()
            for fd in (read_fd,write_fd):
                if fd is not None:
                    try:os.close(fd)
                    except OSError:pass
            if pid is not None:
                try:self._cleanup(pid);result["worker_cleanup"]="GROUP_KILL_ISSUED_WORKER_REAPED"
                except BaseException as error:
                    result["status"],result["code"],result["worker_cleanup"]="UNCERTAIN_CONSUMED",c.code(error),"UNCERTAIN"
            try:
                if pid is not None:self._clock_guard(started,mark,last,deadline,task)
            except BaseException as error:result["status"],result["code"]="UNCERTAIN_CONSUMED",c.code(error)
        result["completed_at"]=c.iso(now())
        try:batch.ledger.finish(key,result)
        except BaseException:
            result["inner_code"]=result["code"]
            result["status"],result["code"]="UNCERTAIN_CONSUMED","TERMINAL_LEDGER_UNCERTAIN"
        return result
