OPERATION='GO_READONLY_SUPERVISOR_READBACK_01'
PHASE='READONLY_SUPERVISOR_READBACK'
REQUEST_SCHEMA='READONLY_HOSTOPS_READBACK_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS_READBACK_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS_READBACK_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS_READBACK_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS_READBACK_PLAN_V1'
SOURCE_NAME='readback_readonly.py'
WRITES_ALLOWED=False
DATES=READ_DATES
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=()
MAX_GATE_SPAN_SECONDS=3600
COMPLETE_OUTCOME='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
MISMATCH_OUTCOME='OBSERVED_ALL_EXPECTATIONS_NOT_MET'
RECONCILIATION_OUTCOME='RECONCILIATION_OBSERVED_NOTHING_GATED'
PARTIAL_OUTCOME='PARTIAL_OBSERVED'
EXPIRED_OUTCOME='PARTIAL_OR_WINDOW_EXPIRED'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='PARTIAL_OBSERVED'
ESCAPED_OUTCOME='PARTIAL_OBSERVED'
INSTALL_COMPLETE='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
PLAN_KEYS=frozenset(('mode','install','provision','evidence_boot_id_sha256','unit_directory','service','timer','substitutions',
                     'network_allowlist','journal_placement','journal_mount_point','deploy_tree_path','data_volume','layout','retention_reference','image_revision','free_space_floor_bytes',
                     'sessions_retained','other_writers_allowance_bytes','catalog'))
UNIT_FILE_KEYS=frozenset(('template_b64','rendered_sha256','rendered_bytes','device','inode'))
SERVICE_NAME='c3po-massive.service'
TIMER_NAME='c3po-massive.timer'
UNITS=[SERVICE_NAME,TIMER_NAME]
UNIT_MODE=0o644
DIRECTORY_MODE=0o700
TOKEN_MODE=0o600
LAYOUT_KEYS=('SUP_CONFIG','SUP_MANIFESTS','SUP_DOCKER_CLI','SUP_STATE_PARENT','SUP_STATE','SUP_JOURNAL')
REPOSITORY='c3po/backend'
PRODUCTION_REFERENCE=REPOSITORY+':production'
TAG='massive-supervisor-[a-z0-9][a-z0-9.-]{0,40}'
# README "Activation gate" item 4: the producer's floor, plus one session's own budget for each session retained before
# space is next freed, plus the signed allowance for every other writer of that filesystem. Recomputed here.
PRODUCER_FLOOR_BYTES=53687091200
SESSION_BYTES=603979776
MAX_SESSIONS_RETAINED=366
MAX_ALLOWANCE_BYTES=1<<50
# Wrong at any reload state: the manager refused the unit text, could not read it, or the name is masked.
BAD_LOAD_STATES=('bad-setting','error','masked')
INIT_COUNTED='a regular file owned by uid 0, not writable by group or other, with an execute bit'
MINIMUM_SYSTEMD=240
MINIMUM_DOCKER=[20,10]
DOCKER_UNIT='docker.service'
CATALOG_NAMES=('epoch.json','maintenance.lock')
MAX_CATALOG_ENTRIES=64
MAX_COUNT=100000
INIT_CANDIDATES=['/usr/bin/docker-init','/usr/libexec/docker/docker-init','/usr/local/bin/docker-init','/usr/sbin/docker-init']
REBOOT_MARKER='/run/reboot-required'
EXPIRED=('GO_EXPIRED','CLOCK_REVERSED')
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl','/bin/systemctl']}
VERSION_FORMAT='{{json .Server.Version}}'
INFO_FIELDS=[('security_options','SecurityOptions'),('driver','Driver'),('driver_status','DriverStatus'),
             ('docker_root_dir','DockerRootDir'),('init_binary','InitBinary'),('server_version','ServerVersion')]
# One docker info call for all six fields, as in the reviewed read-only family.
INFO_FORMAT='{'+','.join('"'+key+'":{{json .'+field+'}}' for key,field in INFO_FIELDS)+'}'
UNIT_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','WantedBy','RequiredBy','TriggeredBy')
def _show(unit,keys):return ['show',unit]+[part for key in keys for part in ('-p',key)]
# The exact fixed argv prefixes. The signed request carries this table. No command here changes anything.
COMMANDS={'systemd_version':['systemctl',['--version'],None],
          'docker_unit':['systemctl',_show(DOCKER_UNIT,('Id','ActiveState','SubState','UnitFileState')),None],
          'timer_enabled':['systemctl',['is-enabled',TIMER_NAME],None],
          'image':['docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID, or the signed retention reference'],
          'info':['docker',['info','--format',INFO_FORMAT],None],
          'version':['docker',['version','--format',VERSION_FORMAT],None]}
COMMANDS.update({'unit:'+unit:['systemctl',_show(unit,UNIT_PROPERTIES),None] for unit in UNITS})
SCOPE_STATEMENT=('Reads and changes nothing: the two installed unit files (bytes and metadata), the six values as they stand in the '
                 'installed service, owner, group and mode of every path of the layout and, under placement B only, of the data volume '
                 'root (under placement A the data volume is not read), the filesystem of the journal root, the token by one '
                 'lstat (never opened; never its size, a digest or a timestamp), the names and metadata of the catalog files, free '
                 'space against the signed floor, drop-in and dependency directories, the docker-init candidates, and the fixed '
                 'systemctl and docker commands of the scope. No systemctl verb other than show, is-enabled and --version. '
                 'Only the outcome named as success criterion satisfies the readback half of the activation gate; a '
                 'reconciliation readback never does. This operation authorises no installation and no activation.')
SIDE_EFFECTS=['docker info, run once: the Docker CLI executes every installed CLI plugin binary as root with the single argument '
              'docker-cli-plugin-metadata, and the daemon answers by running its init and runtime binaries with --version; no setting is changed',
              'every docker command runs with DOCKER_CONFIG set to the unit\'s own configuration directory, and only after that directory was '
              'seen to exist, root:root 0700 and empty; whether the Docker CLI writes into an empty configuration directory was never observed '
              'on this host, so the directory is counted before and after and a change is reported as its own finding',
              'systemctl show of a unit the manager has not loaded makes the manager load it from disk; no daemon-reload is run, so of LoadState '
              'only bad-setting, error and masked are findings (they are wrong at any reload state); loaded, not-found and stub are reported',
              'the docker and systemctl entries are known from the upstream sources; systemctl is-enabled and the five extra show properties were never run by this family on this host']
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,
       'binaries':BINARIES,'commands':COMMANDS,'command_environment':COMMAND_ENVIRONMENT,
       'docker_config':'<HOST_CONFIG_DIR>/docker-cli, passed as DOCKER_CONFIG to the docker commands only',
       'units':UNITS,'unit_directory':UNIT_DIRECTORY,'frozen_templates':FROZEN_TEMPLATES,
       'layout':{'keys':list(LAYOUT_KEYS),'every_directory':{'type':'dir','uid':0,'gid':0,'mode_octal':'0700'},
                 'unit_file':{'uid':0,'gid':0,'mode_octal':'0644','links':1},
                 'token':{'path':'<HOST_CONFIG_DIR>/token','uid':0,'gid':0,'mode_octal':'0600','links':1,
                          'reported':['type','uid','gid','mode_octal','links','size_within_1_4096'],'opened':False},
                 'configuration_directory_entries':'counted, names never reported: manifests, docker-cli and the token, nothing else',
                 'catalog':{'names':list(CATALOG_NAMES),'uid':0,'gid':0,'mode_octal':'0600','links':1,'opened':False}},
       'minimums':{'systemd':MINIMUM_SYSTEMD,'docker':MINIMUM_DOCKER},
       'free_space_floor':{'formula':'producer_floor_bytes + bytes_per_session * sessions_retained + other_writers_allowance_bytes',
                           'producer_floor_bytes':PRODUCER_FLOOR_BYTES,'bytes_per_session':SESSION_BYTES,'sessions_retained_at_least':1,
                           'measured':'f_bavail * f_frsize of the filesystem of the journal root, on the journal root itself'},
       'lstat_only':{'docker_init':INIT_CANDIDATES,'docker_init_counted':INIT_COUNTED,'reboot_marker':REBOOT_MARKER},
       'conflict_scan':CONFLICT_SCAN_SCOPE,
       'image':{'revision_label':REVISION_LABEL+' of the pinned image must equal the signed revision',
                'production_reference':PRODUCTION_REFERENCE+' among the tags of the pinned image is reported, not gated'},
       'modes':{'GATE':COMPLETE_OUTCOME,'RECONCILIATION':RECONCILIATION_OUTCOME+' (never exit 0)'},
       'file_contents_read':[BOOT_ID_PATH,UNIT_DIRECTORY+'/'+SERVICE_NAME,UNIT_DIRECTORY+'/'+TIMER_NAME],
       'reported_not_gated':['LoadState loaded, not-found and stub','docker rootless and user-namespace flags','reboot marker',
                             'whether the pinned image still carries '+PRODUCTION_REFERENCE],
       'load_states_that_are_findings':list(BAD_LOAD_STATES),
       'side_effects':SIDE_EFFECTS,
       'never':['any write','the token content, size, digest or timestamps','the content of a catalog file or of a manifest',
                'container environment','docker exec or run','systemctl verbs other than show, is-enabled and --version',
                'daemon-reload','shell','network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'call_seconds':CALL_SECONDS,'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS,
                 'command_output_bytes':MAX_COMMAND_BYTES,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,
                 'unit_bytes':MAX_RENDER_BYTES,'catalog_entries':MAX_CATALOG_ENTRIES,'scan_names':MAX_SCAN_NAMES,
                 'receipt_bytes':RECEIPT_LIMIT}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeScan):
    """Read primitives and the fixed commands. This source has no call that creates, changes or removes anything."""


def render_of(plan,name):
    """The signed unit rendered again, with the signed placement."""
    return render_unit(unit_of(plan,name),plan['network_allowlist'],plan['data_volume']['path'],plan['journal_placement'],plan['deploy_tree_path'])
def unit_of(plan,name):
    """The signed description of one of the two supervisor units, in the shape the shared renderer validates."""
    item=plan['service'] if name==SERVICE_NAME else plan['timer'];profile=REQUIRED_PROFILE[name]
    return {'destination_name':name,'profile':profile,'template_b64':item['template_b64'],'template_sha256':FROZEN_TEMPLATES[profile],
            'placeholders':plan['substitutions'] if name==SERVICE_NAME else {},'rendered_sha256':item['rendered_sha256'],
            'rendered_bytes':item['rendered_bytes']}
def identity_pair(item,strict_mode,code):
    """device and inode copied from an earlier receipt: integers, or both null in a reconciliation readback."""
    numbers=integer(item['device']) and integer(item['inode'],1)
    need(numbers or (not strict_mode and item['device'] is None and item['inode'] is None),code)

def validate_plan(plan):
    mode=plan['mode'];need(type(mode) is str and mode in ('GATE','RECONCILIATION'),'MODE_INVALID');gated=mode=='GATE'
    install,provision=plan['install'],plan['provision']
    need(type(install) is dict and set(install)=={'receipt_sha256','outcome'} and type(provision) is dict
         and set(provision)=={'receipt_sha256'},'RECEIPTS_INVALID')
    if gated:
        need(hexpin(install['receipt_sha256']) and install['outcome']==INSTALL_COMPLETE,'INSTALL_RECEIPT_UNBOUND')
        need(hexpin(provision['receipt_sha256']),'PROVISION_RECEIPT_UNBOUND')
        need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    else:
        need((install['receipt_sha256'] is None or hexpin(install['receipt_sha256']))
             and (install['outcome'] is None or text(install['outcome'],CODE)),'INSTALL_RECEIPT_UNBOUND')
        need(provision['receipt_sha256'] is None or hexpin(provision['receipt_sha256']),'PROVISION_RECEIPT_UNBOUND')
        need(plan['evidence_boot_id_sha256'] is None or hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    chain_rows(plan['unit_directory'],UNIT_DIRECTORY)
    volume,placement=plan['data_volume'],plan['journal_placement']
    need(type(volume) is dict and set(volume)=={'path','rows'} and type(volume['path']) is str,'DATA_VOLUME_INVALID')
    validate_allowlist(plan['network_allowlist'])
    validate_substitutions(plan['substitutions'],plan['network_allowlist'],volume['path'],placement,plan['deploy_tree_path'])
    # The filesystem the authorisation names for the journal root: its mount point ("/" when /var/lib is on the root
    # filesystem, as the receipt of 2026-10-02 read it in an earlier boot and OP_PRECHECK reads it again in the boot of
    # the write; the data volume root under placement B).
    point=plan['journal_mount_point']
    need(type(point) is str and (point=='/' or clean_path(point)),'JOURNAL_MOUNT_POINT_UNBOUND')
    need(inside(plan['substitutions']['HOST_JOURNAL_ROOT'],point) and point!=plan['substitutions']['HOST_JOURNAL_ROOT'],'JOURNAL_MOUNT_POINT_UNBOUND')
    # Under placement A the data volume is not part of the layout: its path is signed for the path rules only, no row
    # of it is signed and nothing of it is read.
    if placement=='B':chain_rows(volume['rows'],volume['path'])
    else:need(volume['rows'] is None,'DATA_VOLUME_INVALID')
    for name in UNITS:
        item=plan['service'] if name==SERVICE_NAME else plan['timer']
        need(type(item) is dict and set(item)==set(UNIT_FILE_KEYS),'UNITS_INVALID')
        identity_pair(item,gated,'UNITS_INVALID')
        render_of(plan,name)
    layout=plan['layout']
    need(type(layout) is dict and set(layout)==set(LAYOUT_KEYS),'LAYOUT_INVALID')
    for key in LAYOUT_KEYS:
        need(type(layout[key]) is dict and set(layout[key])=={'device','inode'},'LAYOUT_INVALID')
        identity_pair(layout[key],gated,'LAYOUT_INVALID')
    need(type(plan['retention_reference']) is str and re.fullmatch(re.escape(REPOSITORY)+':'+TAG,plan['retention_reference']) is not None,
         'TAG_INVALID')
    need(text(plan['image_revision'],'[0-9a-f]{40}'),'IMAGE_REVISION_UNBOUND')
    sessions,allowance=plan['sessions_retained'],plan['other_writers_allowance_bytes']
    need(integer(sessions,1,MAX_SESSIONS_RETAINED) and integer(allowance,0,MAX_ALLOWANCE_BYTES),'FLOOR_TERMS_INVALID')
    # The floor is not a free number: it is the gate's formula on the two signed terms, and both are in the effects.
    need(type(plan['free_space_floor_bytes']) is int
         and plan['free_space_floor_bytes']==PRODUCER_FLOOR_BYTES+SESSION_BYTES*sessions+allowance,'FLOOR_NOT_THE_GATE_FORMULA')
    catalog=plan['catalog']
    need(type(catalog) is dict and set(catalog)=={'expected','receipt_sha256','device','inode'}
         and type(catalog['expected']) is str and catalog['expected'] in ('INITIALISED','NOT_YET'),'CATALOG_INVALID')
    if catalog['expected']=='INITIALISED':
        need(hexpin(catalog['receipt_sha256']) and integer(catalog['device']) and integer(catalog['inode'],1),'CATALOG_INVALID')
    else:need(catalog['receipt_sha256'] is None and catalog['device'] is None and catalog['inode'] is None,'CATALOG_INVALID')

def layout_paths(values):
    config,state=values['HOST_CONFIG_DIR'],values['HOST_STATE_ROOT']
    return {'SUP_CONFIG':config,'SUP_MANIFESTS':config+'/manifests','SUP_DOCKER_CLI':config+'/docker-cli',
            'SUP_STATE_PARENT':str(PurePosixPath(state).parent),'SUP_STATE':state,'SUP_JOURNAL':values['HOST_JOURNAL_ROOT']}

def identities_of(plan):
    """Every identity this readback compares, copied from earlier receipts. Its hash is in the effects, so a GO cannot
    stay the same while a pinned device or inode in the request changes."""
    pair=lambda item:{'device':item['device'],'inode':item['inode']}
    return {'unit_directory':plan['unit_directory'],'service':pair(plan['service']),'timer':pair(plan['timer']),
            'layout':{key:pair(plan['layout'][key]) for key in LAYOUT_KEYS},'data_volume_rows':plan['data_volume']['rows'],
            'catalog':pair(plan['catalog'])}

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,'mode':plan['mode'],'install_receipt_sha256':plan['install']['receipt_sha256'],
            'install_outcome':plan['install']['outcome'],'provision_receipt_sha256':plan['provision']['receipt_sha256'],
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'units':{SERVICE_NAME:plan['service']['rendered_sha256'],TIMER_NAME:plan['timer']['rendered_sha256']},
            'substitutions':plan['substitutions'],'network_allowlist':plan['network_allowlist'],
            'journal_placement':plan['journal_placement'],'journal_mount_point':plan['journal_mount_point'],
            'deploy_tree_path':plan['deploy_tree_path'],'data_volume_read':plan['journal_placement']=='B',
            'layout_paths':layout_paths(plan['substitutions']),'data_volume_path':plan['data_volume']['path'],
            'token_path':plan['substitutions']['HOST_CONFIG_DIR']+'/token',
            'image_id':plan['substitutions']['IMAGE_ID'],'image_revision':plan['image_revision'],
            'retention_reference':plan['retention_reference'],
            'free_space_floor_bytes':plan['free_space_floor_bytes'],'sessions_retained':plan['sessions_retained'],
            'other_writers_allowance_bytes':plan['other_writers_allowance_bytes'],
            'unit_directory_row':plan['unit_directory'][-1],
            'data_volume_root_row':plan['data_volume']['rows'][-1] if plan['data_volume']['rows'] else None,
            'identities_sha256':sha(canonical(identities_of(plan))),
            'catalog':{'expected':plan['catalog']['expected'],'receipt_sha256':plan['catalog']['receipt_sha256']},
            'gates_activation_readback':plan['mode']=='GATE','writes':0,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME if plan['mode']=='GATE' else RECONCILIATION_OUTCOME


def properties(raw,keys):
    need(re.fullmatch(rb'[ -~\n]*',raw) is not None,'PROPERTY_OUTPUT_INVALID')
    found={}
    for line in raw.decode('ascii').splitlines():
        if not line:continue
        key,separator,value=line.partition('=')
        need(separator=='=','PROPERTY_LINE_INVALID')
        if key in keys:
            need(key not in found and text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'PROPERTY_VALUE_INVALID');found[key]=value
    return {key:found.get(key) for key in keys},sorted(set(keys)-set(found))

def done(status='COMPLETE',findings=(),**fields):
    """One observation: whether it could be made (status) and, separately, whether what was seen is what was signed."""
    codes=sorted(set(findings))
    return dict(fields,status=status,findings=codes,matches=(not codes) if status=='COMPLETE' else None)

class Reader:
    """The observations of one readback. Each method is one item of the receipt and fails on its own."""
    def __init__(self,plan,host,gate):
        self.plan,self.host,self.gate=plan,host,gate;self.commands=Commands(host,gate)
        self.values=plan['substitutions'];self.paths=layout_paths(self.values)
        self.same_boot=True;self.service_bytes=None;self.docker_config=None;self.init_present=None
        self.unit_file_state=None

    def boot(self):
        seen=boot_id_sha256(self.host,self.gate);signed=self.plan['evidence_boot_id_sha256']
        self.same_boot=signed is None or seen==signed
        # Device numbers may be renumbered by a reboot: one finding here instead of one per row, and rows compare without the device.
        return done(findings=[] if self.same_boot else ['EVIDENCE_FROM_EARLIER_BOOT'],boot_id_sha256=seen,
                    evidence_boot_id_sha256=signed,device_numbers_compared=self.same_boot)

    def identity(self,info,signed):
        """True, False, or None when the request carries no identity (reconciliation)."""
        if signed['inode'] is None:return None
        return info.st_ino==signed['inode'] and (not self.same_boot or info.st_dev==signed['device'])

    def units(self):
        rows=[];findings=[];files={}
        fd=descend(self.host,UNIT_DIRECTORY,self.gate,rows)
        try:
            signed=self.plan['unit_directory']
            directory_equal=len(rows)==len(signed) and all(row_equal(seen,row,self.same_boot) for seen,row in zip(rows,signed))
            if not directory_equal:findings.append('UNIT_DIRECTORY_IDENTITY_MISMATCH')
            for name in UNITS:
                item=self.plan['service'] if name==SERVICE_NAME else self.plan['timer'];self.gate()
                try:named=self.host.lstat(name,fd)
                except FileNotFoundError:
                    files[name]={'exists':False};findings.append('UNIT_ABSENT');continue
                row=dict(file_row(named),exists=True,sha256_signed=item['rendered_sha256']);files[name]=row
                if not stat.S_ISREG(named.st_mode):
                    findings.append('UNIT_NOT_REGULAR');continue
                try:raw,info=read_regular(self.host,name,fd,self.gate,MAX_RENDER_BYTES)
                except Refused as error:
                    if str(error)=='FILE_CHANGED_DURING_READ':raise Refused('UNIT_CHANGED_DURING_READ') from None
                    raise
                need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'UNIT_CHANGED_DURING_READ')
                row.update(sha256=sha(raw),bytes=len(raw),bytes_equal_signed_render=sha(raw)==item['rendered_sha256'],
                           identity_equal_install_receipt=self.identity(info,item))
                if name==SERVICE_NAME:self.service_bytes=raw
                if not (info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)==UNIT_MODE and info.st_nlink==1):
                    findings.append('UNIT_METADATA')
                if row['identity_equal_install_receipt'] is False:findings.append('UNIT_IDENTITY_CHANGED')
                if not row['bytes_equal_signed_render']:findings.append('UNIT_BYTES_MISMATCH')
            return done(findings=findings,unit_directory=rows,unit_directory_equal_signed=directory_equal,files=files)
        finally:self.host.close(fd)

    def values_in_installed_bytes(self):
        need(self.service_bytes is not None,'SERVICE_BYTES_UNAVAILABLE')
        template=decode_template(unit_of(self.plan,SERVICE_NAME))
        extracted=extract_values(template,self.service_bytes)
        placement=self.plan['journal_placement']
        if extracted is None:return done(findings=['VALUES_NOT_EXTRACTABLE'],extracted=None,signed=self.values,signed_placement=placement)
        # The placement the values on disk correspond to: the signed placement's own path rules, applied to what was extracted.
        try:
            placement_rules(extracted,self.plan['data_volume']['path'],placement,self.plan['deploy_tree_path'])
            conform,rule=True,None
        except Refused as error:conform,rule=False,code_of(error,'PLACEMENT_RULE')
        findings=([] if extracted==self.values else ['VALUES_MISMATCH'])+([] if conform else ['PLACEMENT_MISMATCH'])
        return done(findings=findings,extracted=extracted,signed=self.values,signed_placement=placement,
                    extracted_values_conform_to_the_signed_placement=conform,placement_rule_broken=rule,
                    basis='parsed from the installed bytes against the literal segments of the frozen template')

    def layout(self):
        rows={};findings=[];unavailable=False
        for key in LAYOUT_KEYS:
            found=attempt(lambda key=key:probe(self.host,self.paths[key],self.gate));found['path']=self.paths[key]
            rows[key]=found
            if found.get('status')!='COMPLETE':unavailable=True;continue
            if not found['exists']:
                findings.append('LAYOUT_ENTRY_ABSENT');continue
            found.pop('links',None)
            found['metadata_matches']=(found['type'],found['uid'],found['gid'],found['mode_octal'])==('dir',0,0,'%04o'%DIRECTORY_MODE)
            signed=self.plan['layout'][key]
            found['identity_equal_provision_receipt']=None if signed['inode'] is None else (
                found['inode']==signed['inode'] and (not self.same_boot or found['device']==signed['device']))
            if not found['metadata_matches']:findings.append('LAYOUT_METADATA')
            if found['identity_equal_provision_receipt'] is False:findings.append('LAYOUT_IDENTITY_CHANGED')
        counts={}
        for key in ('SUP_DOCKER_CLI','SUP_MANIFESTS','SUP_STATE'):
            if rows[key].get('exists') and rows[key].get('type')=='dir':
                counts[key]=attempt(lambda key=key:{'status':'COMPLETE','entries':self.count(self.paths[key])})
                if counts[key].get('status')!='COMPLETE':unavailable=True
        cli=rows['SUP_DOCKER_CLI']
        if counts.get('SUP_DOCKER_CLI',{}).get('status')=='COMPLETE':
            if counts['SUP_DOCKER_CLI']['entries']:findings.append('DOCKER_CONFIG_NOT_EMPTY')
            elif cli.get('metadata_matches'):self.docker_config=self.paths['SUP_DOCKER_CLI']
        # The filesystem the journal root is on: one row per component from "/", and from the device numbers its mount
        # point, which must be the one the authorisation names; and the journal root is not itself a mount point (its
        # device is the device of the directory it is in). Read only when the journal root was seen to exist.
        journal=rows['SUP_JOURNAL'];signed_point=self.plan['journal_mount_point']
        filesystem={'placement':self.plan['journal_placement'],'signed_mount_point':signed_point,'status':'NOT_OBSERVED'}
        if journal.get('exists') and journal.get('type')=='dir':
            chain=[]
            try:
                self.host.close(descend(self.host,self.paths['SUP_JOURNAL'],self.gate,chain))
                point=mount_point_of(chain);own=chain[-1]['device']!=chain[-2]['device']
                filesystem.update(status='COMPLETE',device=chain[-1]['device'],parent_device=chain[-2]['device'],mount_point_by_device_change=point,
                                  mount_point_equals_signed=point==signed_point,journal_root_is_a_mount_point=own)
                if own:findings.append('JOURNAL_ROOT_IS_A_MOUNT_POINT')
                elif point!=signed_point:findings.append('JOURNAL_FILESYSTEM_MISMATCH')
            except Exception as error:
                filesystem.update(safe(error));unavailable=True
        if self.plan['journal_placement']!='B':
            observed={'status':'COMPLETE','read':False,'reason':'placement A: the data volume is not part of the layout and nothing of it is read'}
            return done('PARTIAL' if unavailable else 'COMPLETE',findings,paths=rows,entry_counts=counts,journal_filesystem=filesystem,data_volume=observed)
        volume=self.plan['data_volume'];seen=[]
        try:
            self.host.close(descend(self.host,volume['path'],self.gate,seen))
            equal=len(seen)==len(volume['rows']) and all(row_equal(a,b,self.same_boot) for a,b in zip(seen,volume['rows']))
            observed={'status':'COMPLETE','read':True,'rows':seen,'equal_signed_rows':equal,'recorded_not_required_to_be_root':True}
            if not equal:findings.append('DATA_VOLUME_ROW_CHANGED')
        except Exception as error:
            observed=dict(safe(error),rows=seen);unavailable=True
        return done('PARTIAL' if unavailable else 'COMPLETE',findings,paths=rows,entry_counts=counts,journal_filesystem=filesystem,data_volume=observed)

    def count(self,path):
        fd=descend(self.host,path,self.gate)
        try:return count_entries(self.host,fd,self.gate,MAX_COUNT)
        finally:self.host.close(fd)

    def token(self):
        """One lstat through the configuration directory, and a count of that directory's entries. The file is never
        opened; no size, digest, timestamp or name leaves here."""
        fd=descend(self.host,self.paths['SUP_CONFIG'],self.gate)
        try:
            self.gate()
            # Entries of the configuration directory, on the descriptor held: the two directories and the token, nothing
            # else (an abandoned token.new, an editor backup). Names never leave this function.
            entries=count_entries(self.host,fd,self.gate,MAX_COUNT)
            try:named=self.host.lstat('token',fd)
            except FileNotFoundError:
                return done(findings=['TOKEN_ABSENT']+(['CONFIG_DIRECTORY_ENTRIES'] if entries!=2 else []),exists=False,
                            configuration_directory_entries=entries,configuration_directory_entries_expected=2)
            regular=stat.S_ISREG(named.st_mode);findings=[] if entries==3 else ['CONFIG_DIRECTORY_ENTRIES']
            within=bool(1<=named.st_size<=4096) if regular else None
            if not regular:findings.append('TOKEN_NOT_REGULAR')
            if not (named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==TOKEN_MODE and named.st_nlink==1):
                findings.append('TOKEN_METADATA')
            if regular and not within:findings.append('TOKEN_SIZE_POLICY')
            return done(findings=findings,exists=True,type=kind(named.st_mode),uid=named.st_uid,gid=named.st_gid,
                        mode_octal='%04o'%stat.S_IMODE(named.st_mode),links=named.st_nlink,size_within_1_4096=within,
                        configuration_directory_entries=entries,configuration_directory_entries_expected=3)
        finally:self.host.close(fd)

    def journal(self):
        """Catalog names and metadata, and free space, on one descriptor of the journal root. No catalog file is opened."""
        catalog=self.plan['catalog'];fd=descend(self.host,self.paths['SUP_JOURNAL'],self.gate)
        try:
            held=self.host.fstat(fd);names=[]
            for name in self.host.names(fd):
                names.append(name);need(len(names)<=MAX_CATALOG_ENTRIES,'CATALOG_ENTRY_LIMIT')
            files={};findings=[]
            for name in CATALOG_NAMES:
                if name not in names:continue
                self.gate();named=self.host.lstat(name,fd)
                files[name]={'type':kind(named.st_mode),'uid':named.st_uid,'gid':named.st_gid,
                             'mode_octal':'%04o'%stat.S_IMODE(named.st_mode),'links':named.st_nlink}
                if not (stat.S_ISREG(named.st_mode) and named.st_uid==0 and named.st_gid==0
                        and stat.S_IMODE(named.st_mode)==TOKEN_MODE and named.st_nlink==1):findings.append('CATALOG_METADATA')
            foreign=len([name for name in names if name not in CATALOG_NAMES])
            if catalog['expected']=='INITIALISED':
                if set(names)!=set(CATALOG_NAMES):findings.append('CATALOG_ENTRIES')
                # The catalog binds device and inode of its root: a renumbered device is a real finding, in any boot.
                if (held.st_dev,held.st_ino)!=(catalog['device'],catalog['inode']):findings.append('CATALOG_IDENTITY_MISMATCH')
            elif names:findings=[code for code in findings if code!='CATALOG_METADATA']+['CATALOG_UNEXPECTED']
            section=done(findings=findings,expected=catalog['expected'],entries=len(names),known_files=files,other_entries=foreign,
                         root_device=held.st_dev,root_inode=held.st_ino)
            def space():
                v=self.host.fstatvfs(fd);values=(v.f_frsize,v.f_blocks,v.f_bfree,v.f_bavail)
                need(all(type(value) is int and value>=0 for value in values) and v.f_frsize>0,'STATVFS_INVALID')
                available=v.f_bavail*v.f_frsize;floor=self.plan['free_space_floor_bytes']
                return done(findings=[] if available>=floor else ['FREE_SPACE_BELOW_FLOOR'],
                            bytes_available_to_non_root_f_bavail=available,bytes_free_for_root_f_bfree=v.f_bfree*v.f_frsize,
                            bytes_total=v.f_blocks*v.f_frsize,signed_floor_bytes=floor,at_or_above_signed_floor=available>=floor,
                            sessions_retained=self.plan['sessions_retained'],other_writers_allowance_bytes=self.plan['other_writers_allowance_bytes'],
                            bytes_above_signed_floor=available-floor,filesystem_device=held.st_dev)
            return section,attempt(space)
        finally:self.host.close(fd)

    def conflicts(self):
        scan=conflict_scan(self.host,UNITS,self.gate)
        findings=list(scan['finding_codes'])+(['PRIOR_TEMPORARY_PRESENT'] if scan['leftover_count'] else [])
        return done(scan['status'],findings,conflict_rows=scan['findings'],
                    **{key:value for key,value in scan.items() if key not in ('status','findings')})

    def docker_init(self):
        candidates={path:attempt(lambda path=path:probe(self.host,path,self.gate)) for path in INIT_CANDIDATES}
        status=combined(candidates.values())
        def counted(value):
            # A name that merely exists (a dangling link, a directory, a file nobody can execute) is not an init binary.
            if value.get('exists') is not True or value.get('type')!='file' or value.get('uid')!=0:return False
            mode=int(value['mode_octal'],8);return not mode&0o022 and bool(mode&0o111)
        present=sorted(path for path,value in candidates.items() if counted(value))
        other=sorted(path for path,value in candidates.items() if value.get('exists') is True and not counted(value))
        self.init_present=True if present else False if status=='COMPLETE' else None
        return done(status,candidates={path:{key:value for key,value in item.items() if key!='links'} for path,item in candidates.items()},
                    present_paths=present,present_not_counted_paths=other,counted=INIT_COUNTED,any_present=self.init_present,lstat_only=True)

    def reboot_marker(self):
        found=probe(self.host,REBOOT_MARKER,self.gate)
        if found.get('status')!='COMPLETE':return found
        return done(exists=found['exists'],reported_not_gated=True)

    def systemd_version(self):
        raw=self.commands.output('systemd_version').split(b'\n',1)[0]
        need(re.fullmatch(rb'[ -~]{1,200}',raw) is not None,'VERSION_LINE_INVALID')
        line=raw.decode('ascii');match=re.match(r'systemd ([0-9]{1,5})(?![0-9])',line)
        need(match is not None,'VERSION_LINE_INVALID');number=int(match.group(1))
        return done(findings=[] if number>=MINIMUM_SYSTEMD else ['SYSTEMD_TOO_OLD'],first_line=line,number=number,minimum=MINIMUM_SYSTEMD)

    def docker_unit(self):
        values,missing=properties(self.commands.output('docker_unit'),('Id','ActiveState','SubState','UnitFileState'))
        need(not missing,'PROPERTY_MISSING')
        return done(findings=[] if (values['Id'],values['ActiveState'])==(DOCKER_UNIT,'active') else ['DOCKER_UNIT_NOT_ACTIVE'],properties=values)

    def unit(self,name):
        values,missing=properties(self.commands.output('unit:'+name),UNIT_PROPERTIES)
        need(not missing,'PROPERTY_MISSING');need(values['Id']==name,'UNIT_ID_MISMATCH');findings=[]
        if values['ActiveState']!='inactive':findings.append('UNIT_NOT_INACTIVE')
        if values['LoadState'] in BAD_LOAD_STATES:findings.append('UNIT_LOAD_STATE')
        if values['FragmentPath'] not in ('',UNIT_DIRECTORY+'/'+name):findings.append('FRAGMENT_PATH_MISMATCH')
        if values['DropInPaths']:findings.append('DROP_IN_REPORTED_BY_MANAGER')
        if values['WantedBy'] or values['RequiredBy']:findings.append('REVERSE_DEPENDENCY_REPORTED_BY_MANAGER')
        if values['TriggeredBy'] not in ('',TIMER_NAME if name==SERVICE_NAME else ''):findings.append('TRIGGER_REPORTED_BY_MANAGER')
        if name==TIMER_NAME:
            self.unit_file_state=values['UnitFileState']
            if values['UnitFileState'] not in ('','disabled'):findings.append('TIMER_NOT_DISABLED')
        return done(findings=findings,properties=values,load_state=values['LoadState'],load_states_that_are_findings=list(BAD_LOAD_STATES))

    def timer_enabled(self):
        returncode,raw=self.commands.call('timer_enabled')
        need(re.fullmatch(rb'[a-z-]{1,32}\n?',raw) is not None,'IS_ENABLED_NO_ANSWER')
        word=raw.decode('ascii').strip();findings=[]
        if word!='disabled':findings.append('TIMER_NOT_DISABLED')
        if self.unit_file_state not in (None,'',word):findings.append('ENABLEMENT_SOURCES_DISAGREE')
        # is-enabled exits non-zero for "disabled": the status is recorded and is not a command failure here.
        return done(findings=findings,word=word,returncode=returncode,unit_file_state_from_show=self.unit_file_state)

    def docker_config_count(self):
        need(self.docker_config is not None,'DOCKER_CONFIG_DIRECTORY_UNAVAILABLE')
        return self.count(self.docker_config)

    def image(self,reference,mismatch):
        need(self.docker_config is not None,'DOCKER_CONFIG_DIRECTORY_UNAVAILABLE')
        try:facts=image_facts(self.commands,reference,self.docker_config)
        except CommandFailed as error:raise CommandFailed('IMAGE_ABSENT_OR_UNREADABLE',error.returncode) from None
        equal=facts['id']==self.values['IMAGE_ID'];findings=[] if equal else [mismatch]
        if reference!=self.values['IMAGE_ID'] and equal and not facts['reference_among_repo_tags']:findings.append(mismatch)
        extra={}
        if reference==self.values['IMAGE_ID']:
            # The pinned image itself: its revision label against the signed one (a finding), and whether it still is
            # the production image (reported: after a later deploy the unit keeps its ID by design).
            signed=self.plan['image_revision'];listed=PRODUCTION_REFERENCE in facts['repo_tags']
            extra={'signed_revision':signed,'revision_equal_signed':facts['revision_label']==signed,
                   'production_reference_among_repo_tags':True if listed else False if facts['repo_tag_count']==len(facts['repo_tags']) else None,
                   'production_reference_reported_not_gated':True}
            if not extra['revision_equal_signed']:findings.append('IMAGE_REVISION_MISMATCH')
        return done(findings=findings,reference=reference,signed_image_id=self.values['IMAGE_ID'],id_equal=equal,**facts,**extra)

    def daemon(self):
        need(self.docker_config is not None,'DOCKER_CONFIG_DIRECTORY_UNAVAILABLE')
        row=decode(self.commands.output('info',docker_config=self.docker_config))
        need(set(row)=={key for key,_ in INFO_FIELDS},'DAEMON_INFO_INVALID')
        # A CLI that cannot reach the daemon may still print zero values and exit 0: an empty version is no answer.
        need(type(row['server_version']) is str and row['server_version']!='','DAEMON_INFO_EMPTY')
        options=row['security_options']
        need(options is None or (type(options) is list and len(options)<=16
                                 and all(text(item,'[A-Za-z0-9_.,=:/-]{1,128}') for item in options)),'DAEMON_FIELD_INVALID')
        need(text(row['init_binary'],'[A-Za-z0-9_./-]{0,128}'),'DAEMON_FIELD_INVALID')
        version=strict(self.commands.output('version',docker_config=self.docker_config))
        need(text(version,'[0-9A-Za-z.+~_-]{1,64}'),'DAEMON_FIELD_INVALID')
        match=re.match(r'([0-9]{1,4})\.([0-9]{1,4})(?![0-9])',version);need(match is not None,'DAEMON_FIELD_INVALID')
        number=[int(match.group(1)),int(match.group(2))];names=[item.split(',')[0] for item in options or []];findings=[]
        if number<MINIMUM_DOCKER:findings.append('DOCKER_TOO_OLD')
        if row['init_binary']=='' or self.init_present is False:findings.append('INIT_BINARY_MISSING')
        return done('COMPLETE' if self.init_present is not None else 'PARTIAL',findings,init_binary=row['init_binary'],
                    init_executable_present_on_host=self.init_present,server_version=version,server_version_number=number,
                    minimum=MINIMUM_DOCKER,rootless_reported='name=rootless' in names,userns_remap_reported='name=userns' in names,
                    rootless_and_userns_reported_not_gated=True)


def _reduce_scan(receipt):
    scan=receipt['items'].get('conflicts')
    if type(scan) is dict and type(scan.get('directories')) is dict:
        scan['directories']={name:item.get('status') for name,item in scan['directories'].items()}
def _reduce_items(receipt):
    receipt['items']={name:{key:item.get(key) for key in ('status','matches','findings','code')} for name,item in receipt['items'].items()}
REDUCTIONS=[('SCAN_DIRECTORIES_REDUCED_TO_STATUS',_reduce_scan),('ITEMS_REDUCED_TO_STATUS',_reduce_items)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    reader=Reader(plan,host,gate);items={}
    def run(name,action):
        try:
            gate();items[name]=action()
        except Exception as error:items[name]=safe(error)
    items['actor']=attempt(lambda:done(findings=[] if tuple(host.identity())==(0,0) else ['EXECUTOR_IDENTITY'],
                                       **dict(zip(('uid','gid'),host.identity()))))
    run('boot',reader.boot)
    run('units',reader.units)
    run('values',reader.values_in_installed_bytes)
    run('layout',reader.layout)
    run('token',reader.token)
    try:
        gate();items['catalog'],items['free_space']=reader.journal()
    except Exception as error:items['catalog']=safe(error);items['free_space']=safe(error)
    run('conflicts',reader.conflicts)
    run('docker_init',reader.docker_init)
    run('systemd_version',reader.systemd_version)
    run('docker_unit',reader.docker_unit)
    for name in UNITS:run('unit:'+name,lambda name=name:reader.unit(name))
    run('timer_enabled',reader.timer_enabled)
    before=attempt(reader.docker_config_count)
    run('image',lambda:reader.image(reader.values['IMAGE_ID'],'IMAGE_ID_MISMATCH'))
    run('retention_tag',lambda:reader.image(plan['retention_reference'],'RETENTION_TAG_MISMATCH'))
    run('docker_daemon',reader.daemon)
    after=attempt(reader.docker_config_count)
    if type(before) is int and type(after) is int:
        # Counted before and after the docker commands, separately: a change during this run has its own code.
        items['docker_config']=done(findings=(['DOCKER_CONFIG_NOT_EMPTY'] if before else [])+(['DOCKER_CONFIG_CHANGED_DURING_RUN'] if after!=before else []),
                                    path=reader.docker_config,entries_before=before,entries_after=after)
    else:items['docker_config']=before if type(before) is dict else after
    run('reboot_marker',reader.reboot_marker)
    try:
        ended,elapsed=clock(),monotonic()-mark
        need(ended>=begun and elapsed>=0,'CLOCK_REVERSED')
        items['clock']=done(utc_start=begun.isoformat(),utc_end=ended.isoformat(),monotonic_elapsed_ms=int(elapsed*1000))
    except Exception as error:items['clock']=safe(error)
    findings=sorted({code for item in items.values() for code in item.get('findings') or []})
    incomplete=sorted(name for name,item in items.items() if item.get('status')!='COMPLETE')
    expired=any(item.get('code') in EXPIRED for item in items.values())
    try:gate()
    except Refused:expired=True
    reconciliation=plan['mode']!='GATE'
    if reconciliation:findings=sorted(set(findings)|{'INSTALL_RECEIPT_NOT_COMPLETE'})
    if expired:outcome=EXPIRED_OUTCOME
    elif incomplete:outcome=PARTIAL_OUTCOME
    elif reconciliation:outcome=RECONCILIATION_OUTCOME
    elif findings:outcome=MISMATCH_OUTCOME
    else:outcome=COMPLETE_OUTCOME
    # Exit 0 exists for exactly one outcome; a reconciliation readback takes its own branch above and never reaches it.
    status=COMPLETE_STATUS if outcome==COMPLETE_OUTCOME else PARTIAL_STATUS
    receipt=envelope(status,outcome,None if status==COMPLETE_STATUS else findings[0] if findings else 'ITEMS_NOT_COMPLETE',
        dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),mode=plan['mode'],items=items,findings=findings,
             items_not_complete=incomplete,expectations_met=outcome==COMPLETE_OUTCOME,
             commands_started=reader.commands.calls,mutating_calls=state.counts(),writes=0,secret_bytes_read=0,
             file_contents_read=['the two signed unit files',BOOT_ID_PATH],activation_authorized=False,
             installation_authorized=False))
    return seal(receipt)
