OPERATION='GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01'
PHASE='READONLY_K13R_READER_LIVENESS'
REQUEST_SCHEMA='READONLY_HOSTOPS02_K13R_READER_LIVENESS_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_K13R_READER_LIVENESS_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_K13R_READER_LIVENESS_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_K13R_READER_LIVENESS_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K13R_READER_LIVENESS_PLAN_V1'
SOURCE_NAME='k13r_reader_liveness.py'
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The reads follow a switch of the reader: the request cites the K13 receipt they read back.
SWITCH_OPERATION='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01'
EVIDENCE_OPERATIONS=(SWITCH_OPERATION,)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='READER_LIVE_ALL_EXPECTATIONS_MET'
STOPPED_OUTCOME='READER_STOPPED_ALL_EXPECTATIONS_MET'
MISMATCH_OUTCOME='READER_NOT_AS_EXPECTED'
PARTIAL_OUTCOME='READER_OBSERVATION_INCOMPLETE'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='RECEIPT_REDUCED_OBSERVATION_INCOMPLETE'
ESCAPED_OUTCOME='READER_OBSERVATION_INCOMPLETE'
LIVENESS_MODES=('LIVE','STOPPED')
MODE_OUTCOMES={'LIVE':COMPLETE_OUTCOME,'STOPPED':STOPPED_OUTCOME}
PLAN_KEYS=frozenset(('mode','image_id','evidence_boot_id_sha256','source_target'))

# ---- the reader of this epoch, as the reader README and the installed units fix it (the same constants as K13)
READER_EPOCH='R2D2-V2-SHADOW-2026-10-05'
SERVICE_UNIT='c3po-reader.service'
TIMER_UNIT='c3po-reader.timer'
UNIT_DIRECTORY='/etc/systemd/system'
READER_CONTAINER='c3po-reader'
# The four read-only binds of the reader README's unit: (source on the host, target in the container).
READER_BINDS=(('/mnt/day-d-data','/app/day-d-data'),('/var/lib/c3po-bar/journal','/c3po-bar-journal'),
              ('/var/lib/c3po-capacity','/c3po-capacity'),('/etc/c3po-reader/launcher','/c3po-reader'))
# Codex decision 6: the reader also binds the epoch source root (root-controlled chain) read-only at a top-level target
# signed in the plan (the C3PO_R2D2_V2_SHADOW_SOURCE_DIR of pins.env): a fifth bind. The data volume bind is reported
# (not_root_controlled_sources), never accepted silently as meeting the decision.
SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
SOURCE_TARGET='/c3po-[a-z0-9][a-z0-9-]*'
NOT_ROOT_CONTROLLED_SOURCES=('/mnt/day-d-data',)
# The unit's command: docker run ... IMAGE python -I -B /c3po-reader/reader_launcher.py, as uid 0, with an init process.
READER_PATH='python'
READER_ARGS=('-I','-B','/c3po-reader/reader_launcher.py')
READER_USER='0:0'
READER_MARKERS=('app.r2d2_v2_shadow_worker','reader_launcher.py')
NOT_A_READER_MARKER='--prepare-capacity-day'
SCAN_STATES=('running','paused','restarting')
# STOPPED requires one of these (review finding 5: deactivating is not stopped).
STOPPED_STATES=('inactive','failed')
MAX_COMMAND_WORDS=256
MAX_READER_MOUNTS=16
UNIT_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','Result','NRestarts')
# A timer has no NRestarts: systemctl show prints nothing for a property its unit type lacks (review finding 1).
TIMER_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','Result')
# Fixed templates. Mounts: .Mounts only (type, source, destination, mode, RW, propagation); README operation 6.
# Command: the main process and the run options that matter here. Neither names the environment of the container.
MOUNTS_FORMAT='{{json .Mounts}}'
COMMAND_FORMAT=('{"id":{{json .Id}},"path":{{json .Path}},"args":{{json .Args}},"init":{{json .HostConfig.Init}},'
                '"read_only":{{json .HostConfig.ReadonlyRootfs}},"user":{{json .Config.User}}}')
SCAN_FORMAT='{"id":{{json .Id}},"path":{{json .Path}},"args":{{json .Args}}}'

BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl','/bin/systemctl']}
COMMANDS={'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'the name c3po-reader','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'mounts':command_row('docker',['container','inspect','--format',MOUNTS_FORMAT],'the ID of the c3po-reader container','QUICK','READ'),
          'reader_command':command_row('docker',['container','inspect','--format',COMMAND_FORMAT],'the ID of the c3po-reader container','QUICK','READ'),
          'container_command':command_row('docker',['container','inspect','--format',SCAN_FORMAT],'one container ID of the listing','QUICK','READ'),
          'service_state':command_row('systemctl',['show',SERVICE_UNIT],None,'QUICK','READ',tail=[part for key in UNIT_PROPERTIES for part in ('-p',key)]),
          'timer_state':command_row('systemctl',['show',TIMER_UNIT],None,'QUICK','READ',tail=[part for key in TIMER_PROPERTIES for part in ('-p',key)]),
          'timer_enabled':command_row('systemctl',['is-enabled',TIMER_UNIT],None,'QUICK','READ')}

SCOPE_STATEMENT=('Reads, and changes nothing: the boot; systemctl show of '+SERVICE_UNIT+' and '+TIMER_UNIT+' and systemctl is-enabled of '
                 'the timer; docker ps -a; for the container named '+READER_CONTAINER+' its inspect through fixed templates (identity, '
                 'image, state, start instant, restart count; .Mounts only; the main command, the init flag, the read-only root '
                 'filesystem and the user); the main command of every other running container. Mode LIVE expects one running reader '
                 'of the signed image with its five read-only binds and the launcher command, the service active and the timer enabled; '
                 'mode STOPPED expects the timer disabled and inactive, the service inactive or failed and no reader container. No environment, '
                 'no command line, no log line and no unformatted inspect leaves the run: booleans, identities, states and counts only.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':READER_EPOCH,'modes':MODE_OUTCOMES,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'container':READER_CONTAINER,'binds':[list(pair) for pair in READER_BINDS],
       'source_bind':{'source':SOURCE_ROOT,'target':SOURCE_TARGET+' (signed in the plan)'},'not_root_controlled_sources':list(NOT_ROOT_CONTROLLED_SOURCES),
       'reader_command':{'path':READER_PATH,'args':list(READER_ARGS),'user':READER_USER,'init':True,'read_only_root':True},
       'reader_markers':list(READER_MARKERS),'not_a_reader_marker':NOT_A_READER_MARKER,'scan_states':list(SCAN_STATES),
       'unit_properties':list(UNIT_PROPERTIES),'timer_properties':list(TIMER_PROPERTIES),'stopped_states':list(STOPPED_STATES),'side_effects':[],'file_contents_read':[BOOT_ID_PATH],
       'not_observable_here':['docker top (not a reading verb of this core): the worker child and docker-init are not counted',
                              'docker logs (not a reading verb of this core): the STARTING notice is not read',
                              'the epoch row version (a database read)'],
       'never':['docker run','docker exec','docker logs','docker top','an unformatted docker inspect','a systemctl switch','a file write',
                'an environment value','a command line','a shell'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'containers':MAX_CONTAINERS,'mounts':MAX_READER_MOUNTS,'command_words':MAX_COMMAND_WORDS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """The read primitives and the fixed commands: nothing that can create, write or remove."""


def validate_plan(plan):
    need(plan['mode'] in LIVENESS_MODES,'MODE_INVALID')
    need(text(plan['image_id'],IMAGE_ID),'IMAGE_ID_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(text(plan['source_target'],SOURCE_TARGET) and plan['source_target'] not in [target for _,target in READER_BINDS],'SOURCE_TARGET_INVALID')

def effects_of(plan):
    """What the signers see without opening the request: the mode, what it expects, and that nothing changes."""
    live=plan['mode']=='LIVE'
    return {'operation':OPERATION,'epoch':READER_EPOCH,'mode':plan['mode'],'success_outcome':MODE_OUTCOMES[plan['mode']],
            'image_id':plan['image_id'],'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'expect':{'service':'active' if live else 'inactive or failed','timer':'enabled and active' if live else 'disabled and inactive',
                      'reader_container':'one, running, the signed image, five read-only binds, the launcher command' if live else 'none',
                      'other_readers':'none'},
            'source_bind':{'source':SOURCE_ROOT,'target':plan['source_target']},'binds_not_root_controlled':list(NOT_ROOT_CONTROLLED_SOURCES),
            'writes':0,'side_effects':[]}
def success_of(plan):return MODE_OUTCOMES[plan['mode']]


# ---------------------------------------------------------------- one item each
def item_of(findings=(),**fields):
    return dict(status='COMPLETE',findings=sorted(set(findings)),**fields)

def unit_values(commands,row,unit,properties):
    """systemctl show of one unit: the properties named, each exactly once (any order)."""
    raw=commands.output(row)
    need(re.fullmatch(rb'[ -~\n]*',raw) is not None,'UNIT_PROPERTIES_INVALID');values={}
    for line in raw.decode('ascii').splitlines():
        if not line:continue
        key,separator,value=line.partition('=');need(separator=='=','UNIT_PROPERTIES_INVALID')
        if key in properties:
            need(key not in values and text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'UNIT_PROPERTIES_INVALID');values[key]=value
    need(set(values)==set(properties) and values['Id']==unit,'UNIT_PROPERTIES_INVALID')
    return values

def unit_found(values,unit):
    """Findings common to both units: loaded from the installed file, no drop-in."""
    out=[]
    if values['LoadState']!='loaded':out.append('READER_UNIT_NOT_LOADED')
    if values['FragmentPath']!=UNIT_DIRECTORY+'/'+unit or values['DropInPaths']!='':out.append('READER_UNIT_NOT_THE_INSTALLED_FILE')
    return out

def reader_like(words):
    return any(marker in word for word in words for marker in READER_MARKERS) and not any(NOT_A_READER_MARKER in word for word in words)

def command_words(value):
    need(type(value.get('path')) is str and (value.get('args') is None or (type(value['args']) is list and len(value['args'])<=MAX_COMMAND_WORDS
                                                                         and all(type(word) is str for word in value['args']))),'CONTAINER_COMMAND_INVALID')
    return [value['path']]+list(value['args'] or [])

def mounts_of(raw):
    """The engine's own list of the reader's mounts: type, source, destination, RW. Nothing else is kept."""
    value=strict(raw)
    need(type(value) is list and len(value)<=MAX_READER_MOUNTS,'MOUNTS_INVALID');out=[]
    for mount in value:
        need(type(mount) is dict and type(mount.get('Type')) is str and type(mount.get('Source')) is str and type(mount.get('Destination')) is str
             and type(mount.get('RW')) is bool,'MOUNTS_INVALID')
        out.append({'type':mount['Type'],'source':mount['Source'],'destination':mount['Destination'],'rw':mount['RW']})
    return sorted(out,key=lambda mount:(mount['destination'],mount['source']))

class Liveness:
    """The observations. Each method returns one item or raises; perform() turns a raise into that item's UNAVAILABLE."""
    def __init__(self,plan,host,gate,commands):
        self.plan,self.host,self.gate,self.commands=plan,host,gate,commands;self.live=plan['mode']=='LIVE';self.containers=None;self.reader=None
    def boot(self):
        digest=boot_id_sha256(self.host,self.gate)
        return item_of(['BOOT_NOT_THE_EVIDENCE'] if digest!=self.plan['evidence_boot_id_sha256'] else [],boot_id_sha256=digest)
    def service(self):
        values=unit_values(self.commands,'service_state',SERVICE_UNIT,UNIT_PROPERTIES);findings=unit_found(values,SERVICE_UNIT)
        if self.live and values['ActiveState']!='active':findings.append('SERVICE_NOT_ACTIVE')
        if not self.live and values['ActiveState'] not in STOPPED_STATES:findings.append('SERVICE_NOT_STOPPED')
        return item_of(findings,**{key:values[key] for key in ('LoadState','ActiveState','SubState','Result','NRestarts')})
    def timer(self):
        values=unit_values(self.commands,'timer_state',TIMER_UNIT,TIMER_PROPERTIES);findings=unit_found(values,TIMER_UNIT)
        _,raw=self.commands.call('timer_enabled')
        need(re.fullmatch(rb'[a-z-]{1,32}\n?',raw) is not None,'TIMER_ENABLED_INVALID');word=raw.decode('ascii').strip()
        if self.live and (word!='enabled' or values['ActiveState']!='active'):findings.append('TIMER_NOT_ENABLED_AND_ACTIVE')
        if not self.live and (word!='disabled' or values['ActiveState']!='inactive'):findings.append('TIMER_NOT_DISABLED_AND_INACTIVE')
        return item_of(findings,enabled=word,ActiveState=values['ActiveState'],SubState=values['SubState'])
    def listing(self):
        self.containers=container_list(self.commands)
        own=[row for row in self.containers if row['name']==READER_CONTAINER];self.reader=own[0] if own else None
        findings=[]
        if self.live and (self.reader is None or self.reader['state']!='running'):findings.append('READER_CONTAINER_NOT_RUNNING')
        if not self.live and self.reader is not None:findings.append('READER_CONTAINER_PRESENT')
        return item_of(findings,containers=len(self.containers),reader=None if self.reader is None else {'id':self.reader['id'],'state':self.reader['state']})
    def container(self):
        need(self.reader is not None,'READER_CONTAINER_ABSENT')
        facts=container_facts(self.commands,READER_CONTAINER,expected_name=READER_CONTAINER)
        need(facts['id']==self.reader['id'],'READER_CONTAINER_CHANGED')
        findings=[]
        if facts['running'] is not True:findings.append('READER_CONTAINER_NOT_RUNNING')
        if facts['image_id']!=self.plan['image_id']:findings.append('READER_IMAGE_NOT_THE_PIN')
        return item_of(findings,id=facts['id'],state=facts['state'],running=facts['running'],image_equal_the_pin=facts['image_id']==self.plan['image_id'],
                       started_at=facts['started_at'],restarts=facts['restarts'],health=facts['health'])
    def mounts(self):
        need(self.reader is not None,'READER_CONTAINER_ABSENT')
        found=mounts_of(self.commands.output('mounts',self.reader['id']))
        expected=sorted([{'type':'bind','source':source,'destination':target,'rw':False} for source,target in READER_BINDS+((SOURCE_ROOT,self.plan['source_target']),)],
                        key=lambda mount:(mount['destination'],mount['source']))
        findings=[] if found==expected else ['READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS']
        if [mount for mount in found if mount['rw']]:findings.append('READER_MOUNT_WRITABLE')
        return item_of(findings,mounts=found,count=len(found),not_root_controlled_sources=[mount['source'] for mount in found if mount['source'] in NOT_ROOT_CONTROLLED_SOURCES])
    def command(self):
        need(self.reader is not None,'READER_CONTAINER_ABSENT')
        value=decode(self.commands.output('reader_command',self.reader['id']))
        need(set(value)=={'id','path','args','init','read_only','user'} and value['id']==self.reader['id'],'CONTAINER_COMMAND_INVALID')
        words=command_words(value);findings=[]
        if words!=[READER_PATH]+list(READER_ARGS):findings.append('READER_COMMAND_NOT_THE_LAUNCHER')
        if value['init'] is not True:findings.append('READER_WITHOUT_INIT')
        if value['read_only'] is not True:findings.append('READER_ROOT_NOT_READ_ONLY')
        if value['user']!=READER_USER:findings.append('READER_NOT_UID_0')
        return item_of(findings,launcher_command=words==[READER_PATH]+list(READER_ARGS),init=value['init'] is True,read_only_root=value['read_only'] is True,
                       uid_0=value['user']==READER_USER)
    def others(self):
        need(self.containers is not None,'CONTAINER_LIST_UNAVAILABLE')
        rows=[]
        for row in self.containers:
            if row['state'] not in SCAN_STATES or row['name']==READER_CONTAINER:continue
            value=decode(self.commands.output('container_command',row['id']))
            need(set(value)=={'id','path','args'} and value['id']==row['id'],'CONTAINER_COMMAND_INVALID')
            rows.append({'id':row['id'],'name':row['name'],'reader_like':reader_like(command_words(value))})
        return item_of(['READER_PROCESS_ELSEWHERE'] if [row for row in rows if row['reader_like']] else [],scanned=len(rows),
                       reader_like=[row['name'] for row in rows if row['reader_like']])

EXPIRED_CODES=('GO_EXPIRED','CLOCK_REVERSED')
def _reduce_items(receipt):
    receipt['items']={name:{key:item.get(key) for key in ('status','findings','code')} for name,item in (receipt.get('items') or {}).items()}
REDUCTIONS=[('ITEMS_REDUCED_TO_STATUS',_reduce_items)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    commands=Commands(host,gate);reader=Liveness(plan,host,gate,commands);items={};live=plan['mode']=='LIVE'      # pure: nothing is touched
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    def observe(label,action):
        """One item, observed on its own. An expiry stops the run; any other failure is that item's UNAVAILABLE."""
        started=monotonic()
        try:
            gate();found=action()
        except Exception as error:found=safe(error)
        found['elapsed_ms']=int((monotonic()-started)*1000);items[label]=found
        if found.get('status')=='UNAVAILABLE' and found.get('code') in EXPIRED_CODES:raise Refused(found['code'])
    def finish(stop=None):
        findings=sorted({code for item in items.values() for code in item.get('findings') or []})
        incomplete=sorted(label for label,item in items.items() if item.get('status')!='COMPLETE')
        if stop is not None:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,stop
        elif incomplete:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,findings[0] if findings else 'OBSERVATION_INCOMPLETE'
        elif findings:status,outcome,code=PARTIAL_STATUS,MISMATCH_OUTCOME,findings[0]
        else:status,outcome,code=COMPLETE_STATUS,success_of(plan),None
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),mode=plan['mode'],effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),items=items,
            findings=findings,items_not_complete=incomplete,expectations_met=status==COMPLETE_STATUS,writes=0,phase_reached='OBSERVATION')))
    try:
        need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')                  # first, before anything is looked at
        observe('boot',reader.boot)
        observe('service',reader.service)
        observe('timer',reader.timer)
        observe('containers',reader.listing)
        if live:
            observe('container',reader.container)
            observe('mounts',reader.mounts)
            observe('command',reader.command)
        observe('other_readers',reader.others)
    except Refused as error:
        code=code_of(error,'OBSERVATION_FAILED')
        if not items:
            return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code,dict(bound,phase_reached='BEFORE_ANY_OBSERVATION',mode=plan['mode'],
                                                                         mutating_calls=state.counts(),writes=0)))
        return finish(code)
    return finish()
