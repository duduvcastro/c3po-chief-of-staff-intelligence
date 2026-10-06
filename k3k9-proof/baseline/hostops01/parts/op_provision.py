OPERATION='GO_WRITE_SUPERVISOR_READER_PROVISION_01'
PHASE='WRITE_PROVISION_DIRECTORIES_AND_RETENTION_TAG'
REQUEST_SCHEMA='WRITE_HOSTOPS_PROVISION_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS_PROVISION_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS_PROVISION_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS_PROVISION_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS_PROVISION_PLAN_V1'
SOURCE_NAME='provision_dirs.py'
WRITES_ALLOWED=True
DATES=WRITE_DATES
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='PROVISIONED_ALL_VERIFIED_DURABLE'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CREATED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('groups','journal_placement','data_volume_path','journal_leaf','existing_journal_leaves','capacity','chains','creates',
                     'retention_tag','evidence_boot_id_sha256'))
TAG_BUDGET_SECONDS=16
MAX_SCAN_ENTRIES=4096
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
# The exact fixed argv prefixes. The signed request carries this table. image_tag is the only mutating argv.
COMMANDS={'image':['docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID, or the signed retention reference'],
          'image_ls':['docker',['image','ls','--no-trunc','--format',LS_FORMAT,REPOSITORY],None],
          'image_tag':['docker',['image','tag'],'the signed image ID, then the signed retention reference']}
SCOPE_STATEMENT=('Creates only the listed directories, each by one mkdir relative to a held descriptor of its pinned parent, '
                 'root:root, mode 0700, and at most one image tag on the signed image ID. Never a file, never chmod, chown, '
                 'rename or removal, never anything inside the journal root, never the token, a manifest, a unit or secret.env. '
                 'An object that already exists is never touched: it is refused, or verified when the request signs it as '
                 'present. A spent GO is never retried; after anything other than the success criterion the host state is '
                 'established by a read-only operation under its own GO. The docker commands run with the client '
                 'configuration of root, not with the unit\'s empty DOCKER_CONFIG; the readback resolves the same image and '
                 'tag under the unit\'s configuration.')
SIDE_EFFECTS=['every docker command: the Docker CLI loads the client configuration file of root when one exists; its content never reaches this process',
              'docker image tag adds one reference to the image store; it is the only mutating command',
              'directory fsync of each new directory and of its parent',
              'the docker entries are known from the upstream source; image ls and image tag were never run by this family on this host']
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,
       'binaries':BINARIES,'commands':COMMANDS,'command_environment':COMMAND_ENVIRONMENT,
       'layout':{'groups':list(GROUPS),'journal_placements':{'A':SUP_STATE_PARENT+'/<journal leaf>: next to the state root, the data volume is not touched for it',
                                                              'B':'<data volume>/<journal leaf>: a leaf of the data volume'},
                 'table':layout(['SUPERVISOR','JOURNAL_LEAF','READER','CAPACITY'],'<data volume>','<journal leaf>',
                                {'root_path':'<capacity parent>/<capacity root>','receipt_directory_path':RDR_STATE+'/<receipts>'},'B'),
                 'journal_row_under_placement_a':[row for row in layout(['SUPERVISOR','JOURNAL_LEAF'],None,'<journal leaf>',None,'A') if row['key']=='SUP_JOURNAL']
                                                 +[row for row in layout(['JOURNAL_LEAF'],None,'<journal leaf>',None,'A')],
                 'never_a_mount_point':'every directory of the table has the device of the directory it is created in',
                 'every_entry':{'type':'directory','uid':0,'gid':0,'mode_octal':'0700','umask_octal':'0077'},
                 'receipt_directory_parent':['CAP_ROOT','RDR_STATE'],'capacity_root_parent':['DATA_VOLUME','CAPACITY_PARENT'],
                 'expect':['ABSENT: created exclusively','PRESENT with signed device, inode and entry count: verified, never touched'],
                 'retention_tag':{'repository':REPOSITORY,'tag_pattern':TAG}},
       'name_pattern':LEAF,'name_deny':NAME_DENY,'forbidden_zones':FORBIDDEN_ZONES,'fixed_paths_never_at_or_below_a_parameter':FIXED_PATHS,
       'chain_rows':{'outside_the_data_volume':'uid 0 and not writable by group or other',
                     'at_and_below_the_data_volume_root':'as signed, never writable by others without the sticky bit',
                     'direct_parent':'never setgid'},
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH],
       'side_effects':SIDE_EFFECTS,
       'never':['a file opened for writing','chmod','chown','rename','removal of anything','repair of an existing object',
                'anything inside the journal root','the provider token','a manifest','a unit file','secret.env',
                'container environment','docker exec or run','systemctl','daemon-reload','shell',
                'network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'call_seconds':CALL_SECONDS,'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS,
                 'command_output_bytes':MAX_COMMAND_BYTES,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,
                 'tag_budget_seconds':TAG_BUDGET_SECONDS,'listing_rows':MAX_LISTING_ROWS,'receipt_bytes':RECEIPT_LIMIT}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """Everything this operation can do to the host: the read primitives, the fixed commands, and these three calls."""
    def umask(self,mask):return os.umask(mask)
    def mkdir(self,name,mode,dir_fd):os.mkdir(name,mode,dir_fd=dir_fd)
    def fsync(self,fd):os.fsync(fd)


def validate_plan(plan):
    groups,volume,leaf=plan['groups'],plan['data_volume_path'],plan['journal_leaf']
    existing,capacity,placement=plan['existing_journal_leaves'],plan['capacity'],plan['journal_placement']
    validate_parameters(groups,volume,leaf,existing,capacity,placement)
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    table=layout(groups,volume,leaf,capacity,placement);creates=plan['creates']
    need(len({row['path'] for row in table})==len(table),'PATH_OVERLAP')      # defence in depth: the parameter rules above already exclude it
    need(type(creates) is list and len(creates)==len(table),'LAYOUT_MISMATCH')
    for item,row in zip(creates,table):
        need(type(item) is dict and set(item)==set(row)|{'expect'}
             and canonical({key:item[key] for key in row})==canonical(row),'LAYOUT_MISMATCH')
        expect=item['expect']
        need(expect=='ABSENT' or (type(expect) is dict and set(expect)=={'device','inode','entries'} and integer(expect['device'])
                                  and integer(expect['inode'],1) and integer(expect['entries'],0,MAX_SCAN_ENTRIES)),'EXPECT_INVALID')
    by={item['key']:item for item in creates}
    for item in creates:
        parent=item['parent'].get('entry')
        need(parent is None or by[parent]['expect']!='ABSENT' or item['expect']=='ABSENT','EXPECT_INVALID')
    validate_chains(plan['chains'],chain_paths(table,volume,capacity),volume)
    tag=plan['retention_tag']
    if 'RETENTION_TAG' in groups:
        need(type(tag) is dict and set(tag)=={'repository','tag','image_id','expect'} and tag['repository']==REPOSITORY
             and text(tag['tag'],TAG),'TAG_INVALID')
        need(text(tag['image_id'],IMAGE_ID),'IMAGE_ID')
        need(type(tag['expect']) is str and tag['expect'] in ('ABSENT','PRESENT'),'EXPECT_INVALID')
    else:need(tag is None,'TAG_INVALID')
    need(any(item['expect']=='ABSENT' for item in creates) or (tag is not None and tag['expect']=='ABSENT'),'NOTHING_TO_CREATE')

def journal_of(plan):
    """The journal root this request creates or signs as present: its placement, its path, and the filesystem it is on,
    named by the device and the mount point of the signed rows of the existing directory its chain ends at (the data
    volume root under placement B; /var/lib, or the existing private parent, under placement A). Every directory
    created below that row has its device, so this is the filesystem of the journal root. None without the group."""
    row=[item for item in plan['creates'] if item['key']=='SUP_JOURNAL']
    if not row:return None
    parent=row[0]['parent'];by={item['key']:item for item in plan['creates']}
    while 'entry' in parent:parent=by[parent['entry']]['parent']
    rows=plan['chains'][parent['chain']]
    return {'placement':plan['journal_placement'],'path':row[0]['path'],'filesystem_named_by_chain':parent['chain'],
            'filesystem_device':rows[-1]['device'],'mount_point_by_device_change':mount_point_of(rows),
            'data_volume_touched_for_the_journal':plan['journal_placement']=='B'}

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    tag,capacity=plan['retention_tag'],plan['capacity']
    return {'operation':OPERATION,'groups':plan['groups'],'data_volume_path':plan['data_volume_path'],
            'journal_leaf':plan['journal_leaf'],'existing_journal_leaves':plan['existing_journal_leaves'],'journal':journal_of(plan),
            'capacity':None if capacity is None else dict(capacity,receipts_inside_capacity_root=
                str(PurePosixPath(capacity['receipt_directory_path']).parent)==capacity['root_path']),
            'creates':[{'key':item['key'],'path':item['path'],'mode_octal':'%04o'%item['mode'],
                        'expect':'ABSENT' if item['expect']=='ABSENT' else 'PRESENT'} for item in plan['creates']],
            'directories_to_create':sum(1 for item in plan['creates'] if item['expect']=='ABSENT'),
            'direct_parents':{name:rows[-1] for name,rows in sorted(plan['chains'].items())},
            'chains_sha256':sha(canonical(plan['chains'])),
            'data_volume_root':volume_root_facts(plan['chains'],plan['data_volume_path']),
            'retention_tag':None if tag is None else {'reference':tag['repository']+':'+tag['tag'],'image_id':tag['image_id'],
                                                     'expect':tag['expect']},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'files_created':0,'pre_existing_objects_modified':False,'daemon_reload':False,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME


def precheck(plan,host,gate,commands,detail,parents,handles):
    """Everything is looked at before the first creation. Fills the tables as it reads and returns the refusal code, or None."""
    for name in sorted(plan['chains']):
        observed=[];detail['chains'][name]=observed
        fd=walk_pinned(host,plan['chains'][name],gate,observed)
        parents[name]=Pinned(host,fd,rows=plan['chains'][name])
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    rows=[];children={}
    for item in plan['creates']:
        row={'key':item['key'],'path':item['path'],'expected':'ABSENT' if item['expect']=='ABSENT' else 'PRESENT'}
        rows.append(row);reference=item['parent']
        parent=parents[reference['chain']] if 'chain' in reference else handles.get(reference['entry'])
        if parent is None:
            row['observed']='ABSENT_PARENT_ABSENT';continue
        name=PurePosixPath(item['path']).name;gate()
        try:named=host.lstat(name,parent.fd)
        except FileNotFoundError:
            row['observed']='ABSENT';continue
        row['observed']='PRESENT';row.update(shape(named))
        # What this code creates and nothing else: a directory, root:root, 0700, on the filesystem of the directory it
        # is in (a directory of the layout is never a mount point).
        row['conforms']=bool(stat.S_ISDIR(named.st_mode) and named.st_uid==0 and named.st_gid==0
                             and stat.S_IMODE(named.st_mode)==DIRECTORY_MODE and named.st_dev==parent.identity[0])
        if 'entry' in reference:children[reference['entry']]=children.get(reference['entry'],0)+1
        if stat.S_ISDIR(named.st_mode):
            gate();fd=host.open(name,flags,dir_fd=parent.fd)
            handle=Pinned(host,fd,parent=parent,name=name);handles[item['key']]=handle
            need(handle.identity[:2]==(named.st_dev,named.st_ino),'PARENT_CHANGED_DURING_WALK')
            row['entries']=count_entries(host,fd,gate,MAX_SCAN_ENTRIES)
    codes=set()
    for item,row in zip(plan['creates'],rows):
        if row['observed']=='PRESENT' and 'entries' in row:row['foreign_entries']=row['entries']-children.get(row['key'],0)
        expect=item['expect']
        if expect=='ABSENT':
            if row['observed']!='PRESENT':row['state']='OK_ABSENT'
            elif row['conforms'] and row.get('foreign_entries')==0:row['state']='PRESENT_NOT_SIGNED'
            else:row['state']='PRESENT_UNEXPECTED'
        elif row['observed']!='PRESENT':row['state']='EXPECTED_PRESENT_ABSENT'
        elif row['conforms'] and (row['device'],row['inode'],row.get('entries'))==(expect['device'],expect['inode'],expect['entries']):
            row['state']='OK_PRESENT'
        else:row['state']='PRESENT_IDENTITY_MISMATCH'
        codes.add(row['state'])
    detail['precheck']=rows
    present=[row['observed']=='PRESENT' for row in rows]
    code=None
    if 'PRESENT_UNEXPECTED' in codes:code='DESTINATION_PRESENT_UNEXPECTED'
    elif codes&{'EXPECTED_PRESENT_ABSENT','PRESENT_IDENTITY_MISMATCH'}:code='EXPECTATION_MISMATCH'
    elif 'PRESENT_NOT_SIGNED' in codes:
        # Origin unproven in every case: this is what exists, never a statement that an installation happened.
        if all(present):code='ALL_DESTINATIONS_PRESENT'
        elif present==sorted(present,reverse=True):code='PRIOR_PROVISION_PREFIX_PRESENT'
        else:code='PRESENT_SET_NOT_A_PREFIX'
    tag=plan['retention_tag']
    if tag is not None:
        facts={'reference':tag['repository']+':'+tag['tag'],'image_id':tag['image_id'],'expected':tag['expect'],'state':'NOT_ATTEMPTED',
               'code':None}
        detail['retention_tag']=facts
        try:
            try:image=image_facts(commands,tag['image_id'])
            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
            need(image['id']==tag['image_id'],'IMAGE_ID_MISMATCH');facts['image_present']=True
            listed=listing(commands);facts['listing_rows']=len(listed)
            # Absence of the tag is proved only by a listing that succeeded and that also shows the signed image.
            need(any(row['id']==tag['image_id'] for row in listed),'TAG_LISTING_INCONSISTENT')
            named=[row for row in listed if row['tag']==tag['tag']]
            facts['tag_present']=bool(named)
            facts['tag_points_to_signed_image']=named[0]['id']==tag['image_id'] if named else None
            if tag['expect']=='ABSENT':need(not named,'RETENTION_TAG_EXISTS')
            else:need(bool(named) and named[0]['id']==tag['image_id'],'EXPECTATION_MISMATCH')
        except Refused as error:
            facts['code']=code_of(error,'TAG_PRECHECK_FAILED');code=code or facts['code']
    return code

def create_directory(item,parent,host,gate,state,handles):
    """One mkdir and its proof. Returns the ledger row. Nothing is corrected: a created object that does not match is
    left in place and labelled. A failure after the mkdir succeeded is never reported as NOT_CREATED."""
    entry={'key':item['key'],'path':item['path'],'state':'NOT_ATTEMPTED','code':None,'errno':None,'observed':None,
           'fsync_directory':False,'fsync_parent':False}
    name=PurePosixPath(item['path']).name
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    try:parent.verify(gate)
    except Refused as error:
        entry['code']=code_of(error,'PARENT_REPLACED');return entry
    try:mutate(state,gate,lambda:host.mkdir(name,DIRECTORY_MODE,parent.fd))
    except Refused as error:
        entry['code']=code_of(error,'GO_EXPIRED');return entry
    except OSError as error:
        entry.update(state='NOT_CREATED',errno=error.errno if type(error.errno) is int else None,
                     code='DESTINATION_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))
        return entry
    entry['state']='CREATED_UNVERIFIED'
    try:fd=host.open(name,flags,dir_fd=parent.fd)
    except Exception as error:
        entry.update(code='CREATED_OPEN_FAILED',errno=error.errno if isinstance(error,OSError) and type(error.errno) is int else None)
        return entry
    try:
        handle=Pinned(host,fd,parent=parent,name=name);handles[item['key']]=handle
        info=host.fstat(fd);named=host.lstat(name,parent.fd)
        entry['observed']=shape(info)
        if (named.st_dev,named.st_ino)!=(info.st_dev,info.st_ino):
            entry['code']='CREATED_NAME_REPLACED';return entry
        if not (stat.S_ISDIR(info.st_mode) and info.st_uid==0 and info.st_gid==0
                and stat.S_IMODE(info.st_mode)==DIRECTORY_MODE and info.st_dev==parent.identity[0]):
            entry.update(state='CREATED_METADATA_MISMATCH',code='CREATED_METADATA_MISMATCH');return entry
    except Exception as error:
        entry.update(code='CREATED_STAT_FAILED',errno=error.errno if isinstance(error,OSError) and type(error.errno) is int else None)
        return entry
    try:entry['observed']['entries']=count_entries(host,fd,gate,MAX_SCAN_ENTRIES)
    except Exception as error:
        entry.update(code='CREATED_LIST_FAILED',errno=error.errno if isinstance(error,OSError) and type(error.errno) is int else None)
        return entry
    if entry['observed']['entries']:
        entry.update(state='CREATED_NOT_EMPTY',code='CREATED_NOT_EMPTY');return entry
    try:
        host.fsync(fd);entry['fsync_directory']=True
        host.fsync(parent.fd);entry['fsync_parent']=True
    except Exception as error:
        entry.update(state='CREATED_NOT_DURABLE',code='FSYNC_FAILED',
                     errno=error.errno if isinstance(error,OSError) and type(error.errno) is int else None)
        return entry
    entry['state']='CREATED_DURABLE';return entry

def create_tag(tag,facts,gate,state,commands):
    """Last step, only with budget left. The listing is read again; the tag command runs once; the result is read back."""
    reference=tag['repository']+':'+tag['tag']
    try:
        need(gate()>=TAG_BUDGET_SECONDS,'TAG_NOT_ATTEMPTED_BUDGET')
        listed=listing(commands)
        need(any(row['id']==tag['image_id'] for row in listed),'TAG_LISTING_INCONSISTENT')
        need(not any(row['tag']==tag['tag'] for row in listed),'TAG_APPEARED_AFTER_PRECHECK')
        gate()
    except Exception as error:
        # also an OS error while a process is started (no descriptor, no memory): the ledger still reaches the receipt
        facts.update(state='NOT_ATTEMPTED',code=code_of(error,'TAG_LISTING_UNAVAILABLE'));return
    state.issue()
    try:returncode,_=commands.call('image_tag',tag['image_id'],reference,capture=False)
    except Refused as error:
        code=code_of(error,'TAG_COMMAND_FAILED')
        if code in ('BINARY_UNAVAILABLE_OR_UNSAFE','COMMAND_SKIPPED_AFTER_TIMEOUT'):
            state.fail();facts.update(state='NOT_CREATED',code=code);return       # refused before any process existed
        state.unknown();facts.update(state='UNCERTAIN',code='TAG_COMMAND_TIMEOUT' if code=='COMMAND_TIMEOUT' else code);return
    except Exception:
        state.unknown();facts.update(state='UNCERTAIN',code='TAG_COMMAND_FAILED');return
    facts['returncode']=returncode
    if returncode!=0:
        # The CLI reported an error. The tag is called absent only if a listing that succeeds says so.
        try:absent=not any(row['tag']==tag['tag'] for row in listing(commands))
        except Exception:absent=False
        if absent:state.fail();facts.update(state='NOT_CREATED',code='TAG_COMMAND_FAILED')
        else:state.unknown();facts.update(state='UNCERTAIN',code='TAG_COMMAND_FAILED')
        return
    state.done();facts['state']='CREATED_UNVERIFIED'
    try:
        image=image_facts(commands,reference)
        facts['readback_id_equal']=image['id']==tag['image_id']
        need(facts['readback_id_equal'] and image['reference_among_repo_tags'],'TAG_READBACK_MISMATCH')
        facts['state']='CREATED_VERIFIED'
    except Exception as error:
        facts['code']='TAG_READBACK_MISMATCH' if code_of(error,'')=='TAG_READBACK_MISMATCH' else 'TAG_READBACK_UNAVAILABLE'

def readback(plan,host,gate,parents,handles,ledger):
    """Inside the run: every path of the table resolved again from '/', equal to the descriptor held; each directory
    holding exactly what it held before plus the children this run created in it; every pinned parent, the data
    volume root included, unchanged."""
    result={'status':'COMPLETE','entries':[],'parents_unchanged':None,'code':None}
    expected={item['key']:0 if item['expect']=='ABSENT' else item['expect']['entries'] for item in plan['creates']}
    for item in plan['creates']:
        if item['expect']=='ABSENT' and 'entry' in item['parent']:expected[item['parent']['entry']]+=1
    try:
        for row in ledger:
            handle=handles[row['key']];found=probe(host,row['path'],gate)
            same=bool(found.get('exists') and (found['device'],found['inode'])==handle.identity[:2]
                      and found['type']=='dir' and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%DIRECTORY_MODE))
            item={'key':row['key'],'resolves_to_held_descriptor':same,
                  'entries_as_expected':count_entries(host,handle.fd,gate,MAX_SCAN_ENTRIES)==expected[row['key']]}
            result['entries'].append(item)
            need(same and item['entries_as_expected'],'READBACK_MISMATCH')
        for name in sorted(parents):parents[name].verify(gate)
        result['parents_unchanged']=True
    except Exception as error:
        result.update(status='UNAVAILABLE',code=code_of(error,'READBACK_UNAVAILABLE'))
    return result

def _reduce_precheck(receipt):receipt['precheck']=[{'key':row.get('key'),'state':row.get('state')} for row in receipt.get('precheck') or []]
def _reduce_chains(receipt):receipt['chains']={name:len(rows) for name,rows in (receipt.get('chains') or {}).items()}
def _reduce_ledger(receipt):
    receipt['ledger']=[{'key':row.get('key'),'state':row.get('state'),'code':row.get('code')} for row in receipt.get('ledger') or []]
def _reduce_effects(receipt):receipt['effects']={'operation':OPERATION,'reduced_for_size':True}
# The record of what this run created is the last thing to lose detail, and it is never dropped.
REDUCTIONS=[('PRECHECK_REDUCED_TO_STATES',_reduce_precheck),('CHAINS_REDUCED_TO_COUNTS',_reduce_chains),
            ('EFFECTS_DROPPED',_reduce_effects),('LEDGER_REDUCED_TO_STATES',_reduce_ledger)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'chains':{},'precheck':[],'retention_tag':None};ledger=[];parents={};handles={}
    commands=Commands(host,gate);tag=plan['retention_tag']
    def finish(status,outcome,code,extra):
        try:
            ended,elapsed=clock(),monotonic()-mark
            timing={'utc_start':begun.isoformat(),'utc_end':ended.isoformat(),'monotonic_elapsed_ms':int(elapsed*1000)}
        except Exception:timing=None
        created=sum(1 for row in ledger if row['state'].startswith('CREATED'))
        tagged=detail['retention_tag'] is not None and detail['retention_tag'].get('state') in ('CREATED_VERIFIED','CREATED_UNVERIFIED')
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing,
            commands_started=commands.calls,mutating_calls=state.counts(),chains=detail['chains'],precheck=detail['precheck'],
            ledger=ledger,retention_tag=detail['retention_tag'],objects_left_by_this_run=created+(1 if tagged else 0),
            pre_existing_objects_modified=False,files_created=0,**extra))
        return seal(receipt)
    try:
        try:
            actor=host.identity()
            need(tuple(actor)==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            boot=boot_id_sha256(host,gate)
            need(boot==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            code=precheck(plan,host,gate,commands,detail,parents,handles)
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:
            return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        stop=None
        for item in plan['creates']:
            if item['expect']!='ABSENT':
                ledger.append({'key':item['key'],'path':item['path'],'state':'PRESENT_VERIFIED_NOT_TOUCHED','code':None,'errno':None,
                               'observed':None,'fsync_directory':False,'fsync_parent':False});continue
            if stop is not None:
                ledger.append({'key':item['key'],'path':item['path'],'state':'NOT_ATTEMPTED','code':None,'errno':None,
                               'observed':None,'fsync_directory':False,'fsync_parent':False});continue
            reference=item['parent']
            parent=parents[reference['chain']] if 'chain' in reference else handles[reference['entry']]
            entry=create_directory(item,parent,host,gate,state,handles);ledger.append(entry)
            if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'
        facts=detail['retention_tag']
        if tag is not None:
            if tag['expect']=='PRESENT':facts['state']='PRESENT_VERIFIED_NOT_TOUCHED'
            elif stop is None:
                create_tag(tag,facts,gate,state,commands)
                if facts['state']!='CREATED_VERIFIED':stop=facts['code'] or 'TAG_FAILED'
        check=None
        if stop is None:
            check=readback(plan,host,gate,parents,handles,ledger)
            if check['status']!='COMPLETE':stop=check['code'] or 'READBACK_UNAVAILABLE'
        extra={'phase_reached':'CREATION','readback':check}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for handle in list(handles.values())+list(parents.values()):
            try:handle.close()
            except Exception:pass
