"""Fixtures of K13 (the reader switch): the emulated host as it must be when the reader is launched (the producer unit,
the three reader units, the launcher, pins.env, secret.env, the journal root with its catalog, the release, all
installed by earlier operations), the systemctl verbs the core's emulation does not know, and the request plan built
from that host exactly as a binder would copy it from a read-only receipt of the same boot.

ReaderHost SUBCLASSES the core's FakeHost (the core is never edited): it adds enable --now, start --no-block,
reset-failed, disable --now and stop --no-block with the behaviour systemd documents (an enabled timer whose OnBootSec
has passed starts its service at once; a service whose ExecCondition files are missing is skipped, not failed). That
behaviour is emulated only: none of it was observed on the host. Every byte, number, ID and value here is synthetic
except the unit templates (tests/unit_texts.py, copied by command from the reader candidate and the producer request)."""
import copy
import json
from pathlib import Path

import family as f
import hostemu
import unit_texts

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
EPOCH='R2D2-V2-SHADOW-2026-10-05'
DATA=hostemu.DATA
UNITS='/etc/systemd/system'
CONFIG='/etc/c3po-reader'
LAUNCHER_DIRECTORY=CONFIG+'/launcher'
JOURNAL='/var/lib/c3po-bar/journal'
CONTAINER_JOURNAL='/c3po-bar-journal'
CAPACITY='/var/lib/c3po-capacity'
SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
SOURCE_TARGET='/c3po-source'
RELEASE_DIRECTORY=DATA+'/r2d2-v2-release-20261005'
RELEASE_NAME='release.CERTIFIED.json'
RELEASE=b'{"note":"synthetic bytes, never a release","schema":"SYNTHETIC_RELEASE"}'
LAUNCHER=b''.join(b'# SYNTHETIC TEST BYTES %03d: NOT THE READER LAUNCHER\n'%index for index in range(30))
SECRET_LINE=('C3PO_DATABASE_URL=postgresql://c3po:'+hostemu.SECRET+'@db:5432/c3po\n').encode()
ACTIVATION=b'C3PO_R2D2_V2_SHADOW_ENABLED=true\nC3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true\n'
NETWORK='c3po_internal'
SERVICE='c3po-reader.service'
TIMER='c3po-reader.timer'
ALERT='c3po-reader-alert.service'
PRODUCER='c3po-massive.service'
READER_ARGS=['-I','-B','/c3po-reader/reader_launcher.py']

def K():return f.load(DIRECTORY)

def render(template,values):
    text=template
    for key,value in values.items():text=text.replace(('@%s@'%key).encode(),value.encode())
    assert b'@' not in text;return text
def reader_service(image=hostemu.BACKEND,journal=JOURNAL,container_journal=CONTAINER_JOURNAL,data=DATA,capacity=CAPACITY,config=CONFIG,
                   source=SOURCE_ROOT,source_target=SOURCE_TARGET):
    """RDR's template with the fifth read-only bind of Codex decision 6 (the epoch source root at a top-level target),
    inserted after the launcher bind, as K4 PINS requires of B2's unit bytes."""
    template=unit_texts.READER_SERVICE_TEMPLATE
    anchor=b'  --mount type=bind,source=@HOST_CONFIG_DIR@/launcher,target=/c3po-reader,readonly \\\n'
    assert template.count(anchor)==1
    if source is not None:template=template.replace(anchor,anchor+('  --mount type=bind,source=%s,target=%s,readonly \\\n'%(source,source_target)).encode())
    return render(template,{'IMAGE_ID':image,'HOST_DATA_ROOT':data,'HOST_JOURNAL_ROOT':journal,'CONTAINER_JOURNAL_ROOT':container_journal,
                                                      'HOST_CAPACITY_ROOT':capacity,'HOST_CONFIG_DIR':config,'NETWORK':NETWORK})
def producer_service(image=hostemu.BACKEND,journal=JOURNAL,container_journal=CONTAINER_JOURNAL):
    return render(unit_texts.PRODUCER_SERVICE_TEMPLATE,{'IMAGE_ID':image,'HOST_JOURNAL_ROOT':journal,'CONTAINER_JOURNAL_ROOT':container_journal,
                                                        'HOST_STATE_ROOT':'/var/lib/c3po-bar/supervisor','HOST_CONFIG_DIR':'/etc/c3po-bar','NETWORK':'bridge'})
UNIT_BYTES={SERVICE:reader_service(),TIMER:unit_texts.READER_TIMER,ALERT:unit_texts.READER_ALERT,PRODUCER:producer_service()}

def pins_values(release=RELEASE,launcher=LAUNCHER,revision=hostemu.REVISION,journal=CONTAINER_JOURNAL):
    return [('C3PO_BUILD_SHA',revision),('C3PO_R2D2_V2_SHADOW_RELEASE_FILE','/app/day-d-data/r2d2-v2-release-20261005/'+RELEASE_NAME),
            ('C3PO_R2D2_V2_SHADOW_RELEASE_SHA',f.sha(release)),('C3PO_R2D2_V2_SHADOW_SOURCE_DIR',SOURCE_TARGET),
            ('C3PO_R2D2_MICROSTRUCTURE_RAW_DIR','/app/day-d-data/provider=eodhd/microstructure/raw'),('C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR',journal),
            ('C3PO_R2D2_V2_CAPACITY_REQUIRED','true'),('C3PO_R2D2_V2_CAPACITY_VETO_MODE','DISPATCH_AND_DERIVATION_ONLY'),
            ('C3PO_R2D2_V2_CAPACITY_CONFIG_FILE','/c3po-capacity/config/week.static.capacity.json'),('C3PO_R2D2_V2_CAPACITY_CONFIG_SHA','c'*64),
            ('C3PO_R2D2_V2_SHADOW_POLL_SECONDS','1.0'),('C3PO_READER_LAUNCHER_SHA256',f.sha(launcher))]
def pins_bytes(values=None):return ''.join('%s=%s\n'%item for item in (values or pins_values())).encode('ascii')
PINS=pins_bytes()

def epoch_bytes(host,epoch=EPOCH):
    node=host.tree.get(JOURNAL)
    return f.canonical({'schema':'MASSIVE_SESSION_ROOT_V1','epoch':epoch,'device':node.dev,'inode':node.ino})

SWITCH_FORMS=('enable --now','start --no-block','reset-failed','disable --now','stop --no-block')
class ReaderHost(hostemu.FakeHost):
    """hostemu.FakeHost with the five systemctl switches of K13 (documented systemd behaviour, emulated only).
    Knobs: switch_returncode[form] (exit status), switch_no_effect (forms that change nothing), timer_starts_service
    (OnBootSec has passed: starting the timer starts the service), start_creates_container (the service's docker run
    creates c3po-reader at once, of reader_image), stop_settles (stop --no-block ends in inactive at once, else deactivating)."""
    def systemctl(self,args):
        form=' '.join(args[:-1])
        if args[0] not in ('enable','start','reset-failed','disable','stop'):return hostemu.FakeHost.systemctl(self,args)
        assert form in SWITCH_FORMS and len(args)==len(form.split())+1,'systemctl switch outside the emulated set: %r'%args
        unit=args[-1];self.switches.append(list(args))
        if form not in self.switch_no_effect:
            if form=='enable --now':
                assert unit==TIMER;self.is_enabled[TIMER]='enabled';self.units[TIMER].update(ActiveState='active',SubState='waiting',UnitFileState='enabled')
                if self.timer_starts_service:self.start_reader()
            elif form=='start --no-block':
                assert unit==SERVICE;self.start_reader()
            elif form=='reset-failed':
                assert unit==SERVICE
                if self.units[SERVICE]['ActiveState']=='failed':self.units[SERVICE].update(ActiveState='inactive',SubState='dead',Result='success')
            elif form=='disable --now':
                assert unit==TIMER;self.is_enabled[TIMER]='disabled';self.units[TIMER].update(ActiveState='inactive',SubState='dead',UnitFileState='disabled')
            else:
                assert unit==SERVICE
                if self.units[SERVICE]['ActiveState'] in ('active','activating'):
                    self.units[SERVICE].update(ActiveState='inactive' if self.stop_settles else 'deactivating',SubState='dead' if self.stop_settles else 'stop')
                    if self.stop_settles:self.remove_reader()
        self.log.append(('switch',form,unit))
        return self.switch_returncode.get(form,0),b''
    def start_reader(self):
        unit=self.units[SERVICE]
        if unit['ActiveState'] in ('active','activating'):return
        if not all(self.tree.get(CONFIG+'/'+name) is not None for name in ('secret.env','pins.env','activation.env')):return     # ExecCondition: skipped
        unit.update(ActiveState='activating',SubState='start-pre')
        if self.start_creates_container:
            self.docker.containers.append(reader_container(image=self.reader_image));unit.update(ActiveState='active',SubState='running')
    def remove_reader(self):
        self.docker.containers=[item for item in self.docker.containers if item['Name']!='/c3po-reader']
    def unit_state(self):return json.dumps({'units':self.units,'enabled':self.is_enabled},sort_keys=True)

def reader_container(image=hostemu.BACKEND,running=True,name='c3po-reader',args=None):
    item=hostemu.container(name,image,image,['SYNTHETIC=1'],running=running)
    item['Path']='python';item['Args']=list(READER_ARGS if args is None else args);item['ExecIDs']=None;return item

COMMANDS={'api':['uvicorn','app.main:app'],'investor-relations-worker':['-m','app.ir_worker'],'valuation-worker':['-m','app.valuation_worker'],
          'server-usage-worker':['-m','app.server_usage_worker'],'r2d2-shadow-candidate-worker':['-m','app.r2d2_shadow_candidate_worker'],
          'r2d2-worker':['-m','app.r2d2_worker'],'web':['server.js'],'db':['postgres']}
def prepare(host):
    """What the weekend leaves (A1 provisioning, B2 units, A8 launcher, A7 secret.env, B6 pins.env, A9 catalog, M1 release)."""
    host.__class__=ReaderHost
    host.switches=[];host.switch_returncode={};host.switch_no_effect=set();host.timer_starts_service=True;host.start_creates_container=False;host.stop_settles=False
    host.reader_image=hostemu.BACKEND
    tree=host.tree
    for name,raw in UNIT_BYTES.items():tree.add(UNITS+'/'+name,kind='file',mode=0o644,content=raw)
    tree.add(CONFIG,mode=0o700);tree.add(CONFIG+'/docker-cli',mode=0o700);tree.add(LAUNCHER_DIRECTORY,mode=0o700)
    tree.add(LAUNCHER_DIRECTORY+'/reader_launcher.py',kind='file',mode=0o600,content=LAUNCHER)
    tree.add(CONFIG+'/secret.env',kind='file',mode=0o600,content=SECRET_LINE)
    tree.add(CONFIG+'/pins.env',kind='file',mode=0o600,content=PINS)
    tree.add('/var/lib/c3po-reader',mode=0o700)
    for path in ('/var/lib/c3po-bar','/var/lib/c3po-bar/supervisor',JOURNAL,CAPACITY,CAPACITY+'/config','/var/lib/c3po',SOURCE_ROOT):tree.add(path,mode=0o700)
    tree.add(JOURNAL+'/maintenance.lock',kind='file',mode=0o600,content=b'')
    tree.add(JOURNAL+'/epoch.json',kind='file',mode=0o600,content=epoch_bytes(host))
    tree.add(RELEASE_DIRECTORY,dev=hostemu.DATA_DEVICE,mode=0o700)
    tree.add(RELEASE_DIRECTORY+'/'+RELEASE_NAME,kind='file',dev=hostemu.DATA_DEVICE,mode=0o600,content=RELEASE)
    for item in host.docker.containers:
        service=item['Config']['Labels'].get('com.docker.compose.service')
        item['Path']='python';item['Args']=list(COMMANDS.get(service,['-m','app.unknown']));item['ExecIDs']=None
    common={'LoadState':'loaded','DropInPaths':'','NeedDaemonReload':'no','Result':'success','SubState':'dead','ActiveState':'inactive'}
    host.units[SERVICE]=dict(common,Id=SERVICE,UnitFileState='static',FragmentPath=UNITS+'/'+SERVICE)
    host.units[TIMER]=dict(common,Id=TIMER,UnitFileState='disabled',FragmentPath=UNITS+'/'+TIMER)
    host.is_enabled[TIMER]='disabled'
    return host
def world(k=None):return prepare(f.world(k or K()))

def files_member(host,mode='ACTIVATE'):
    def digest(path):return f.sha(bytes(host.tree.get(path).content))
    out={'reader_service':digest(UNITS+'/'+SERVICE),'reader_timer':digest(UNITS+'/'+TIMER),'reader_alert':digest(UNITS+'/'+ALERT),
         'producer_service':digest(UNITS+'/'+PRODUCER),'launcher':digest(LAUNCHER_DIRECTORY+'/reader_launcher.py'),'pins':digest(CONFIG+'/pins.env')}
    return out
def fields(host,mode='ACTIVATE',floor=56706990080):
    """The plan's own members, read from the emulated host as a binder copies them from a read-only receipt."""
    rows=hostemu.rows
    out={'mode':mode,'evidence_boot_id_sha256':f.BOOT_SHA,'unit_rows':rows(host,UNITS),'config_rows':rows(host,CONFIG),
         'launcher_rows':rows(host,LAUNCHER_DIRECTORY),'journal_rows':rows(host,JOURNAL),'release_rows':rows(host,RELEASE_DIRECTORY),
         'release':{'name':RELEASE_NAME,'sha256':f.sha(RELEASE)},'files':files_member(host,mode),'image_id':hostemu.BACKEND,
         'journal_free_floor_bytes':floor,'source_rows':rows(host,SOURCE_ROOT),'capacity_rows':rows(host,CAPACITY)}
    if mode=='DEACTIVATE':
        for key in ('unit_rows','config_rows','launcher_rows','journal_rows','release_rows','release','files','image_id','journal_free_floor_bytes','source_rows','capacity_rows'):out[key]=None
    return out

def activated(host):
    """The host after a complete ACTIVATE: the file, the timer enabled and waiting, the service running its container."""
    host.tree.add(CONFIG+'/activation.env',kind='file',mode=0o600,content=ACTIVATION)
    host.is_enabled[TIMER]='enabled';host.units[TIMER].update(ActiveState='active',SubState='waiting',UnitFileState='enabled')
    host.units[SERVICE].update(ActiveState='active',SubState='running');host.docker.containers.append(reader_container());return host
def failed(host):
    """The host after the reader unit gave up (start limit or a 78): activation in place, timer enabled, service failed."""
    host.tree.add(CONFIG+'/activation.env',kind='file',mode=0o600,content=ACTIVATION)
    host.is_enabled[TIMER]='enabled';host.units[TIMER].update(ActiveState='active',SubState='waiting',UnitFileState='enabled')
    host.units[SERVICE].update(ActiveState='failed',SubState='failed',Result='exit-code');return host

MOMENT={'ACTIVATE':'2026-10-05T10:40:00+00:00','RESTART':'2026-10-06T12:00:00+00:00','DEACTIVATE':'2026-10-09T20:40:00+00:00'}
def case(now=None,mode='ACTIVATE',setup=None,**options):
    """(docs, host): a bound fixture that completes on the emulated host of that mode (now=None: 17:00 UTC on 10-05 for
    ACTIVATE, as the conformance suite expects; the plan's own instants with the mode's MOMENT)."""
    k=K();host=world(k)
    if mode=='RESTART':failed(host)
    if mode=='DEACTIVATE':activated(host)
    if setup is not None:setup(host)
    return f.Docs(k,fields(host,mode),now=now,**options),host

def at(mode):
    from datetime import datetime
    return datetime.fromisoformat(MOMENT[mode])

def state_of(host):
    """Everything a run could change on the emulated host: the tree, the engine, the units."""
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True),host.unit_state()
