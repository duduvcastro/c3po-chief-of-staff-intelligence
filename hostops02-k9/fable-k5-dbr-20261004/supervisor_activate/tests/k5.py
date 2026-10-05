"""Fixtures of K5 (supervisor operation 5, B11): the emulated host as operations (2), (4b), the token and (3) leave it
(placement A, units installed and not reloaded, readback L6 met), a request plan built from it exactly as a binder
copies it from the read-only receipts, and a model of systemd for the four systemctl verbs this source uses.

The model of systemd (Systemd below) is this file's reading of documented behaviour, not an observation of the host:
`enable --now` of a timer with OnBootSec=30s on a host up for more than 30 s starts its service at once (SUP, operation
5); the supervisor refuses outside the session window with exit 78; RestartPreventExitStatus=78 keeps systemd from
restarting it; reset-failed clears the failed state. What the model settles after is time paused by the run."""
from datetime import datetime,timezone
import json
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
SERVICE='c3po-massive.service'
TIMER='c3po-massive.timer'
UNITS='/etc/systemd/system'
LINK=UNITS+'/timers.target.wants/'+TIMER
PATHS={'CONFIG':'/etc/c3po-bar','MANIFESTS':'/etc/c3po-bar/manifests','DOCKER_CLI':'/etc/c3po-bar/docker-cli',
       'STATE':'/var/lib/c3po-bar/supervisor','JOURNAL':'/var/lib/c3po-bar/journal'}
RETENTION='c3po/backend:massive-supervisor-epoch03'
TOKEN_CANARY=b'never-emit-token-canary-value\n'
# The timer as operation 3 rendered it (the template is public; its sha256 is the one of E3's plan)
TIMER_BYTES=(b'[Unit]\nDescription=Start approved Massive session before XNYS open\n\n[Timer]\nOnBootSec=30s\n'
             b'OnCalendar=Mon..Fri *-*-* 09:29:00 America/New_York\nPersistent=false\nAccuracySec=1s\nUnit=c3po-massive.service\n\n'
             b'[Install]\nWantedBy=timers.target\n')
SERVICE_BYTES=b'[Unit]\nDescription=Bounded daily Massive minute producer (synthetic body for the tests)\n[Service]\nType=exec\nRestartPreventExitStatus=78\n'
NOW=datetime(2026,10,5,21,0,tzinfo=timezone.utc)         # Monday 18:00 BRT, inside the B11 band of A2 (20:38-23:30Z)
RESET_NOW=datetime(2026,10,5,21,20,tzinfo=timezone.utc)   # the RESET of that evening, a few minutes later

def K():return f.load(DIRECTORY)


class Systemd:
    """The unit states of the manager for the three units the source reads, and what each verb does to them."""
    def __init__(self,host):
        self.host=host;self.reloads=0;self.calls=[]
        self.reload_rc=0;self.enable_rc=0;self.enable_effect=True;self.reset_rc=0;self.reset_effect=True
        self.outcome='78';self.settle_after=0.0;self.started_at=None;self.invocations=0
        self.leave_container=False;self.take_claim=False;self.after_reload=None
        self.start_after=None;self.enabled_at=None;self.create_link=True;self.next_elapse='Tue 2026-10-06 09:29:00 EDT';self.after_reset_shows=[]
        self.service={'Id':SERVICE,'LoadState':'loaded','ActiveState':'inactive','SubState':'dead','Result':'success','ExecMainCode':'0',
                      'ExecMainStatus':'0','NRestarts':'0','InvocationID':'','UnitFileState':'static','FragmentPath':UNITS+'/'+SERVICE,'DropInPaths':''}
        self.timer={'Id':TIMER,'LoadState':'loaded','ActiveState':'inactive','SubState':'dead','Result':'success','UnitFileState':'disabled',
                    'FragmentPath':UNITS+'/'+TIMER,'DropInPaths':'','NextElapseUSecRealtime':'','LastTriggerUSec':'n/a'}
    def start_service(self):
        self.invocations+=1;self.started_at=self.host.paused
        self.service.update(ActiveState='activating',SubState='start',InvocationID='%032x'%(0xabc0+self.invocations))
    def advance(self):
        if self.enabled_at is not None and self.host.paused-self.enabled_at>=self.start_after:
            self.enabled_at=None;self.start_service()
        if self.started_at is None or self.service['ActiveState']!='activating':return
        if self.host.paused-self.started_at<self.settle_after:return
        if self.outcome=='78':
            self.service.update(ActiveState='failed',SubState='failed',Result='exit-code',ExecMainCode='1',ExecMainStatus='78')
        elif self.outcome=='1':                     # an attempt that failed: systemd restarts it (and a claim was taken)
            self.service.update(ActiveState='activating',SubState='auto-restart',Result='exit-code',ExecMainCode='1',ExecMainStatus='1',NRestarts='1')
        elif self.outcome=='0':
            self.service.update(ActiveState='inactive',SubState='dead',Result='success',ExecMainCode='1',ExecMainStatus='0')
        elif self.outcome=='78-after-a-restart':      # a refusal after systemd had already restarted the service once
            self.service.update(ActiveState='failed',SubState='failed',Result='exit-code',ExecMainCode='1',ExecMainStatus='78',NRestarts='1')
        elif self.outcome=='125':
            self.service.update(ActiveState='failed',SubState='failed',Result='exit-code',ExecMainCode='1',ExecMainStatus='125',NRestarts='0')
        if self.take_claim:self.host.tree.add(PATHS['STATE']+'/2026-10-05.claim-1',kind='file',mode=0o600)
        if self.leave_container:
            self.host.docker.containers.append(hostemu.container('c3po-massive',hostemu.BACKEND,hostemu.BACKEND,[],running=False))
        self.started_at=None
    def __call__(self,args):
        self.calls.append(list(args))
        if args==['daemon-reload']:
            self.reloads+=1
            if self.after_reload is not None:self.after_reload(self)
            return self.reload_rc,b''
        if args==['enable','--now',TIMER]:
            if not self.enable_effect:return self.enable_rc,b''
            if self.create_link:self.host.tree.add(LINK,kind='symlink',mode=0o777).target='/etc/systemd/system/'+TIMER
            self.timer.update(UnitFileState='enabled',ActiveState='active',SubState='waiting',
                              NextElapseUSecRealtime=self.next_elapse,LastTriggerUSec='Mon 2026-10-05 18:00:01 -03')
            if self.start_after is None:self.start_service()
            else:self.enabled_at=self.host.paused
            return self.enable_rc,b''
        if args==['reset-failed',SERVICE]:
            if not self.reset_effect:return self.reset_rc,b''
            if self.service['ActiveState']=='failed':self.service.update(ActiveState='inactive',SubState='dead',Result='success')
            self.pending_after_reset=list(self.after_reset_shows)
            return self.reset_rc,b''
        assert args[0]=='show' and args[2::2]==['-p']*((len(args)-2)//2),args
        unit,wanted=args[1],args[3::2]
        if unit==SERVICE:
            self.advance()
            if getattr(self,'pending_after_reset',None):self.service.update(self.pending_after_reset.pop(0))
            values=self.service
        elif unit==TIMER:values=self.timer
        else:values=dict({'Id':unit,'LoadState':'not-found','ActiveState':'inactive','SubState':'dead','UnitFileState':''},**self.host.units.get(unit,{}))
        return 0,''.join('%s=%s\n'%(key,values[key]) for key in sorted(wanted,reverse=True) if key in values).encode()

class SystemdHost(hostemu.FakeHost):
    """The emulated host with the systemd model in place of the three read-only verbs of the core's emulation."""
    def systemctl(self,args):return self.systemd(args)


def world():
    """The host as operations (2), (4b), the token and (3) leave it under placement A, with the readback L6 met."""
    k=K();host=f.world(k);host.__class__=SystemdHost;host.systemd=Systemd(host)
    hostemu.provision_supervisor(host)
    for name in ('epoch.json','maintenance.lock'):host.tree.add(PATHS['JOURNAL']+'/'+name,kind='file',mode=0o600,content=b'{}' if name=='epoch.json' else b'')
    host.tree.add(PATHS['CONFIG']+'/token',kind='file',mode=0o600,content=TOKEN_CANARY)
    host.tree.add(UNITS+'/'+SERVICE,kind='file',mode=0o644,content=SERVICE_BYTES)
    host.tree.add(UNITS+'/'+TIMER,kind='file',mode=0o644,content=TIMER_BYTES)
    host.docker.images[0]['RepoTags'].append(RETENTION)
    return k,host

def unit(host,name):
    node=host.tree.get(UNITS+'/'+name)
    return {'name':name,'sha256':f.sha(bytes(node.content)),'bytes':len(node.content),'device':node.dev,'inode':node.ino}

def fields(host,mode='ACTIVATE'):
    return {'mode':mode,'unit_directory':hostemu.rows(host,UNITS),'units':{'service':unit(host,SERVICE),'timer':unit(host,TIMER)},
            'supervisor_paths':{key:hostemu.rows(host,path) for key,path in PATHS.items()},
            'expected_entries':{'JOURNAL':2,'STATE':0,'DOCKER_CLI':0},'image_id':hostemu.BACKEND,'retention_reference':RETENTION,
            'invocation_id':None if mode=='ACTIVATE' else host.systemd.service['InvocationID'],'evidence_boot_id_sha256':f.BOOT_SHA}

def activated(host):
    """What an ACTIVATE leaves when the immediate start ended in the refusal: link, timer on, service failed by 78."""
    systemd=host.systemd;systemd.calls.append(['enable','--now',TIMER]);systemd.calls.pop()
    host.tree.add(LINK,kind='symlink',mode=0o777).target='/etc/systemd/system/'+TIMER
    systemd.timer.update(UnitFileState='enabled',ActiveState='active',SubState='waiting',NextElapseUSecRealtime=systemd.next_elapse,
                         LastTriggerUSec='Mon 2026-10-05 18:00:01 -03')
    systemd.service.update(ActiveState='failed',SubState='failed',Result='exit-code',ExecMainCode='1',ExecMainStatus='78',NRestarts='0',
                           InvocationID='%032x'%0xabc1)
    return host

def case(now=None,mode='ACTIVATE'):
    """(docs, host): a bound fixture that completes on a fresh emulated host (for RESET: after a complete ACTIVATE)."""
    k,host=world()
    if mode=='RESET':activated(host)
    return f.Docs(k,fields(host,mode),now=(NOW if mode=='ACTIVATE' else RESET_NOW) if now is None else now),host

def state_of(host):
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True),\
           json.dumps([host.systemd.service,host.systemd.timer],sort_keys=True)
def verbs(host):
    """The systemctl verbs the run gave, show excluded."""
    return [call for call in host.systemd.calls if call[0]!='show']
