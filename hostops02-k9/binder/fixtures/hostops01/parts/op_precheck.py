OPERATION='GO_READONLY_HOSTOPS_PRECHECK_01'
PHASE='READONLY_HOSTOPS_PRECHECK'
REQUEST_SCHEMA='READONLY_HOSTOPS_PRECHECK_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS_PRECHECK_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS_PRECHECK_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS_PRECHECK_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS_PRECHECK_PLAN_V1'
SOURCE_NAME='precheck_readonly.py'
WRITES_ALLOWED=False
DATES=READ_DATES
EVIDENCE_REQUIRED=False
EVIDENCE_OPERATIONS=()
MAX_GATE_SPAN_SECONDS=3600
COMPLETE_OUTCOME='PRECHECK_ALL_OBSERVED'
PARTIAL_OUTCOME='PARTIAL_OBSERVED'
EXPIRED_OUTCOME='PARTIAL_OR_WINDOW_EXPIRED'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='PARTIAL_OBSERVED'
ESCAPED_OUTCOME='PARTIAL_OBSERVED'
PLAN_KEYS=frozenset(('groups','journal_placement','data_volume_path','journal_leaf','existing_journal_leaves','capacity','unit_names','image_reference'))
PRODUCTION_REFERENCE=REPOSITORY+':production'
# Names that hold, or will hold, a secret: type, owner, mode and link count only. Never a size, a timestamp or an identity.
SECRET_BEARING=[RDR_CONFIG+'/secret.env',SUP_CONFIG+'/token']
PRESENCE_ONLY=['/etc/.git','/etc/.etckeeper','/run/reboot-required']
CORE_PATTERN_PATH='/proc/sys/kernel/core_pattern'
MAX_SCAN_ENTRIES=4096
EXPIRED=('GO_EXPIRED','CLOCK_REVERSED')
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
# The exact fixed argv prefixes. The signed request carries this table. No command here changes anything.
COMMANDS={'image':['docker',['image','inspect','--format',IMAGE_FORMAT],'the fixed reference '+PRODUCTION_REFERENCE],
          'image_ls':['docker',['image','ls','--no-trunc','--format',LS_FORMAT,REPOSITORY],None]}
SCOPE_STATEMENT=('Reads and changes nothing: one row (device, inode, owner, group, mode) per component of each parent directory the '
                 'write operations pin, the presence and metadata of every planned destination, the unit lookup directories, the '
                 'boot identifier hash, and the local ID and tags of '+PRODUCTION_REFERENCE+'. For names that hold a secret only '
                 'type, owner, mode and link count; for a unit file found at a signed name no size. Its rows are what the write '
                 'requests sign; it authorises no write.')
SIDE_EFFECTS=['every docker command: the Docker CLI loads the client configuration file of root when one exists; its content never reaches this process',
              'docker image ls was never run by this family on this host: this operation is its first run']
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,
       'binaries':BINARIES,'commands':COMMANDS,'command_environment':COMMAND_ENVIRONMENT,
       'chains':dict(CHAIN_PATHS,UNIT_DIRECTORY=UNIT_DIRECTORY,DATA_VOLUME='<data volume>',CAPACITY_PARENT='<parent of the capacity root>'),
       'layout':{'groups':[group for group in GROUPS if group!='RETENTION_TAG'],
                 'journal_placements':{'A':SUP_STATE_PARENT+'/<journal leaf>','B':'<data volume>/<journal leaf>'},
                 'table':layout(['SUPERVISOR','JOURNAL_LEAF','READER','CAPACITY'],'<data volume>','<journal leaf>',
                                {'root_path':'<capacity parent>/<capacity root>','receipt_directory_path':RDR_STATE+'/<receipts>'},'B')},
       'name_pattern':LEAF,'name_deny':NAME_DENY,'forbidden_zones':FORBIDDEN_ZONES,'fixed_paths_never_at_or_below_a_parameter':FIXED_PATHS,
       'unit_directory':UNIT_DIRECTORY,'unit_name_pattern':UNIT_NAME,
       'unit_files_reported':['exists','type','uid','gid','mode_octal','links','device','inode'],
       'conflict_scan':CONFLICT_SCAN_SCOPE,
       'secret_bearing_names':{'paths':SECRET_BEARING,'reported':['exists','type','uid','gid','mode_octal','links'],'opened':False},
       'presence_only':PRESENCE_ONLY,'image_reference':PRODUCTION_REFERENCE,
       'file_contents_read':[BOOT_ID_PATH,CORE_PATTERN_PATH+' (only whether its first byte is a pipe sign is reported)'],
       'side_effects':SIDE_EFFECTS,
       'never':['any write','file contents other than file_contents_read','a size, timestamp, device or inode of a secret-bearing name',
                'container environment','docker exec or run','systemctl','shell','network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'call_seconds':CALL_SECONDS,'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS,
                 'command_output_bytes':MAX_COMMAND_BYTES,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,
                 'scan_names':MAX_SCAN_NAMES,'directory_entries':MAX_SCAN_ENTRIES,'listing_rows':MAX_LISTING_ROWS,
                 'receipt_bytes':RECEIPT_LIMIT}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeScan):
    """Read primitives and the fixed commands. This source has no call that creates, changes or removes anything."""


def validate_plan(plan):
    groups=plan['groups']
    need(type(groups) is list and 'RETENTION_TAG' not in groups,'GROUPS_INVALID')
    validate_parameters(groups,plan['data_volume_path'],plan['journal_leaf'],plan['existing_journal_leaves'],plan['capacity'],plan['journal_placement'])
    need(unit_names(plan['unit_names']),'UNIT_NAME_INVALID')
    need(plan['image_reference']==PRODUCTION_REFERENCE,'IMAGE_REFERENCE_INVALID')

def planned(plan):
    table=layout(plan['groups'],plan['data_volume_path'],plan['journal_leaf'],plan['capacity'],plan['journal_placement'])
    chains=dict(chain_paths(table,plan['data_volume_path'],plan['capacity']),UNIT_DIRECTORY=UNIT_DIRECTORY)
    return table,chains

def effects_of(plan):
    table,chains=planned(plan)
    return {'operation':OPERATION,'journal_placement':plan['journal_placement'],'existing_journal_leaves':plan['existing_journal_leaves'],
            'chains':chains,'destinations':[row['path'] for row in table],
            'unit_names':plan['unit_names'],'secret_bearing_names':SECRET_BEARING,'presence_only':PRESENCE_ONLY,
            'image_reference':plan['image_reference'],'writes':0,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME


def chain(host,path,gate,volume):
    """One observed row per component, in exactly the six-key form a write request signs, plus what a signer must
    see before signing it: type, setgid, whether the code would accept the row, and mount points by device change."""
    rows=[];fd=None
    try:fd=descend(host,path,gate,rows)
    except Exception as error:
        return dict(safe(error),path=path,rows=rows)
    try:
        notes=[];device=None
        for row in rows:
            notes.append({'path':row['path'],'mode_octal':'%04o'%row['mode'],'setgid':bool(row['mode']&stat.S_ISGID),
                          'root_owned_not_group_or_other_writable':row_root_safe(row),
                          'world_writable_without_sticky':world_writable_without_sticky(row),
                          'accepted_by_the_write_operations':row_accepted(row,volume) is None,
                          'mount_point_by_device_change':device is None or row['device']!=device})
            device=row['device']
        v=host.fstatvfs(fd)
        need(all(type(value) is int and value>=0 for value in (v.f_frsize,v.f_bavail)) and v.f_frsize>0,'STATVFS_INVALID')
        return {'status':'COMPLETE','path':path,'rows':rows,'notes':notes,
                'direct_parent_setgid':bool(rows[-1]['mode']&stat.S_ISGID),
                'bytes_available_to_non_root_f_bavail':v.f_bavail*v.f_frsize}
    finally:host.close(fd)

def destination(host,row,gate,table):
    """Proved absence (with the first missing component) or presence with metadata. A directory is also counted, and its
    entries are split into table-defined children and others; no name is reported."""
    found=probe(host,row['path'],gate);found.pop('links',None)
    result=dict(found,key=row['key'],path=row['path'])
    if found.get('status')=='COMPLETE' and found.get('exists') and found['type']=='dir':
        fd=descend(host,row['path'],gate)
        try:
            result['entries']=count_entries(host,fd,gate,MAX_SCAN_ENTRIES);defined=0
            for child in table:
                if child['parent'].get('entry')!=row['key']:continue
                gate()
                try:host.lstat(PurePosixPath(child['path']).name,fd);defined+=1
                except FileNotFoundError:pass
            result['table_defined_children']=defined;result['other_entries']=result['entries']-defined
        finally:host.close(fd)
        result['conforms_to_layout']=(found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%DIRECTORY_MODE)
    return result

def secret_bearing(host,path,gate):
    found=probe(host,path,gate)
    if found.get('status')!='COMPLETE':return {key:found.get(key) for key in ('status','code','at')}
    if not found['exists']:return {'status':'COMPLETE','exists':False,'absent_at':found['absent_at']}
    return {'status':'COMPLETE','exists':True,**{key:found[key] for key in ('type','uid','gid','mode_octal','links')}}

def presence(host,path,gate):
    found=probe(host,path,gate)
    if found.get('status')!='COMPLETE':return {key:found.get(key) for key in ('status','code','at')}
    return {'status':'COMPLETE','exists':found['exists']}

def unit_file(host,name,gate):
    fd=descend(host,UNIT_DIRECTORY,gate)
    try:
        gate()
        try:named=host.lstat(name,fd)
        except FileNotFoundError:return {'status':'COMPLETE','exists':False}
        # No size: this operation cannot tell whether the file is the signed render, and the size of a foreign unit
        # with an inline secret would measure it.
        return {'status':'COMPLETE','exists':True,**{key:value for key,value in file_row(named).items() if key!='size'}}
    finally:host.close(fd)

def core_pattern(host,gate):
    """Whether the kernel pipes core dumps to a handler. Only that boolean is reported."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW;parts=PurePosixPath(CORE_PATTERN_PATH).parts[1:]
    gate();fd=host.open('/',flags)
    try:
        for part in parts[:-1]:
            gate();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child
        gate();leaf=host.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:raw=host.read(leaf,1)
        finally:host.close(leaf)
    finally:host.close(fd)
    need(type(raw) is bytes and len(raw)==1,'CORE_PATTERN_UNREADABLE')
    return {'status':'COMPLETE','is_pipe':raw==b'|'}

def _reduce_scan(receipt):
    scan=receipt['items'].get('conflicts')
    if type(scan) is dict and type(scan.get('directories')) is dict:
        scan['directories']={name:item.get('status') for name,item in scan['directories'].items()}
def _reduce_notes(receipt):
    for item in (receipt['items'].get('chains') or {}).values():
        if type(item) is dict:item.pop('notes',None)
def _reduce_items(receipt):
    receipt['items']={name:{'status':item.get('status') if type(item) is dict and 'status' in item else 'REDUCED'}
                      for name,item in receipt['items'].items()}
REDUCTIONS=[('SCAN_DIRECTORIES_REDUCED_TO_STATUS',_reduce_scan),('CHAIN_NOTES_DROPPED',_reduce_notes),('ITEMS_REDUCED_TO_STATUS',_reduce_items)]

def statuses(value,found):
    if type(value) is dict:
        if 'status' in value:found.append((value['status'],value.get('code')))
        for item in value.values():statuses(item,found)
    elif type(value) is list:
        for item in value:statuses(item,found)

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    table,chains=planned(plan);commands=Commands(host,gate);items={};volume=plan['data_volume_path']
    def run(name,action):
        try:
            gate();items[name]=action()
        except Exception as error:items[name]=safe(error)
    def each(names,action):
        return {name:attempt(lambda name=name:action(name)) for name in names}
    items['actor']=attempt(lambda:dict(zip(('uid','gid'),host.identity()),status='COMPLETE'))
    run('boot',lambda:{'status':'COMPLETE','boot_id_sha256':boot_id_sha256(host,gate)})
    run('chains',lambda:{name:chain(host,chains[name],gate,volume) for name in sorted(chains)})
    run('destinations',lambda:{row['key']:attempt(lambda row=row:destination(host,row,gate,table)) for row in table})
    run('secret_bearing_names',lambda:each(SECRET_BEARING,lambda path:secret_bearing(host,path,gate)))
    run('presence_only',lambda:each(PRESENCE_ONLY,lambda path:presence(host,path,gate)))
    run('unit_files',lambda:each(plan['unit_names'],lambda name:unit_file(host,name,gate)))
    run('conflicts',lambda:conflict_scan(host,plan['unit_names'],gate))
    run('core_pattern',lambda:core_pattern(host,gate))
    def image():
        try:facts=image_facts(commands,plan['image_reference'])
        except CommandFailed as error:raise CommandFailed('IMAGE_ABSENT_OR_UNREADABLE',error.returncode) from None
        return dict(facts,status='COMPLETE' if facts['repo_tags_all_valid'] and facts['reference_among_repo_tags'] else 'PARTIAL',
                    reference=plan['image_reference'],
                    binds='this ID binds only if it is read after the deploy of the merged revision; it is specific to this image store')
    run('image',image)
    def listed():
        rows=listing(commands);inspected=items.get('image',{}).get('id')
        return {'status':'COMPLETE','rows':rows,'contains_inspected_id':None if inspected is None else any(row['id']==inspected for row in rows),
                'retention_tags_present':sorted(row['tag'] for row in rows if re.fullmatch(TAG,row['tag']))}
    run('image_listing',listed)
    try:
        ended,elapsed=clock(),monotonic()-mark
        need(ended>=begun and elapsed>=0,'CLOCK_REVERSED')
        items['clock']={'status':'COMPLETE','utc_start':begun.isoformat(),'utc_end':ended.isoformat(),'monotonic_elapsed_ms':int(elapsed*1000)}
    except Exception as error:items['clock']=safe(error)
    found=[];statuses(items,found)
    problems=sorted({code for status,code in found if status!='COMPLETE' and type(code) is str})
    incomplete=any(status!='COMPLETE' for status,_ in found);expired=any(code in EXPIRED for _,code in found)
    try:gate()
    except Refused:expired=True
    outcome=EXPIRED_OUTCOME if expired else PARTIAL_OUTCOME if incomplete else COMPLETE_OUTCOME
    status=COMPLETE_STATUS if outcome==COMPLETE_OUTCOME else PARTIAL_STATUS
    receipt=envelope(status,outcome,None if status==COMPLETE_STATUS else (problems+['ITEMS_NOT_COMPLETE'])[0],
        dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),items=items,problems=problems[:32],
             commands_started=commands.calls,mutating_calls=state.counts(),writes=0,secret_bytes_read=0,
             file_contents_read=[BOOT_ID_PATH,CORE_PATTERN_PATH],installation_authorized=False,activation_authorized=False))
    return seal(receipt)
