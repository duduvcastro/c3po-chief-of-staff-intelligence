OPERATION='GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01'
PHASE='WRITE_INSTALL_UNITS_NO_ACTIVATION'
REQUEST_SCHEMA='WRITE_HOSTOPS_INSTALL_UNITS_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS_INSTALL_UNITS_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS_INSTALL_UNITS_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS_INSTALL_UNITS_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS_INSTALL_UNITS_PLAN_V1'
SOURCE_NAME='install_units.py'
WRITES_ALLOWED=True
DATES=WRITE_DATES
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CREATED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('unit_directory','units','network_allowlist','journal_placement','data_volume_path','deploy_tree_path',
                     'template_revision','acknowledged_leftovers','daemon_reload_owner','evidence_boot_id_sha256'))
UNIT_KEYS=frozenset(('key','destination_name','mode','profile','template_b64','template_sha256','placeholders',
                     'rendered_sha256','rendered_bytes','expect'))
UNIT_MODE=0o644
TEMPORARY='.hostops-%s-%d.partial'
MAX_LEFTOVERS=16
SCOPE_STATEMENT=('Creates only the listed unit files in /etc/systemd/system, root:root, mode 0644, each written under a '
                 'dot-prefixed temporary name that systemd does not load, fsynced, then linked to its final name (a link never '
                 'replaces anything), after which the temporary of this run is removed once its identity is proved; a temporary '
                 'whose file could not be completed is withdrawn the same way, and nothing else is ever removed. No process '
                 'is started: no systemctl verb, no daemon-reload, no enablement, no drop-in, no overwrite, no chmod, chown or '
                 'rename. The manager is reloaded by the owner named in effects.daemon_reload, under that owner\'s own GO, never '
                 'by this operation. A spent GO is never retried; after anything other than the success criterion the host '
                 'state is established by a read-only operation under its own GO.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,
       'unit_directory':UNIT_DIRECTORY,'unit_name_pattern':UNIT_NAME,'max_units':MAX_UNITS,
       'every_file':{'type':'regular file','uid':0,'gid':0,'mode_octal':'0644','umask_octal':'0022','links':1},
       'temporary_name':TEMPORARY%('<first 16 hex of the GO hash>',0),'leftover_pattern':LEFTOVER,
       'expect':['ABSENT: created exclusively','PRESENT with signed device, inode and link count: verified against the signed render, never touched'],
       'profiles':{'frozen_templates':FROZEN_TEMPLATES,'required_for_name':REQUIRED_PROFILE,'all':list(PROFILES),
                   'supervisor_occurrences':OCCURRENCES,'generic_kinds':list(KINDS)},
       'grammar':{'path':VALUE_PATH,'network':NETWORK,'forbidden_networks':list(FORBIDDEN_NETWORKS),'image_id':IMAGE_ID,
                  'placeholder':PLACEHOLDER,'container_data':CONTAINER_DATA,'path_length':MAX_PATH_LENGTH,
                  'component_length':MAX_COMPONENT_LENGTH},
       'journal_placement':{'signed':list(PLACEMENTS),'provided_top_level_directories':list(PROVIDED_TOP_LEVEL),'fixed_container_targets':list(FIXED_TARGETS),
                            'every_placement':'the host journal root neither equals, contains nor is contained in the state root or the configuration '
                                              'directory; the container journal root likewise against the fixed targets; neither private root inside the data volume',
                            'A':'host journal root outside the data volume and outside the signed deploy tree; container journal root exactly one new '
                                'top-level directory, none of the provided ones',
                            'B':'host journal root a leaf of the data volume; container journal root '+CONTAINER_DATA+'/<the same leaf>',
                            'not_checked_here':'that the host journal root is not a mount point: this operation does not open it (OP_PROVISION creates it '
                                               'on its parent\'s device; OP_READBACK compares the devices)'},
       'conflict_scan':CONFLICT_SCAN_SCOPE,'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'a regular file found at a signed destination name, only to say whether its bytes equal the signed render: '
                             'of a file that is not the signed render no digest and no size is reported',
                             'the text of symbolic links of a unit type in the lookup directories (alias detection)',
                             'the unit files this run installed (readback inside the run)'],
       'external_processes':0,
       'never':['a process','systemctl','daemon-reload','enablement link','drop-in','overwrite','chmod','chown','rename',
                'removal of anything but the temporary this run created and proved by identity','repair of an existing object',
                'docker','container environment','shell','network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'template_bytes':MAX_TEMPLATE_BYTES,
                 'template_bytes_total':MAX_TEMPLATE_BYTES_TOTAL,'render_bytes':MAX_RENDER_BYTES,'scan_names':MAX_SCAN_NAMES,
                 'receipt_bytes':RECEIPT_LIMIT}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeScan):
    """Everything this operation can do to the host: the read primitives and these six calls. It starts no process."""
    def umask(self,mask):return os.umask(mask)
    def create(self,name,flags,mode,dir_fd):return os.open(name,flags,mode,dir_fd=dir_fd)
    def write(self,fd,data):return os.write(fd,data)
    def fsync(self,fd):os.fsync(fd)
    def link(self,source,target,dir_fd):os.link(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd,follow_symlinks=False)
    def unlink(self,name,dir_fd):os.unlink(name,dir_fd=dir_fd)


def validate_plan(plan):
    rows=chain_rows(plan['unit_directory'],UNIT_DIRECTORY)
    need(all(row_root_safe(row) for row in rows),'CHAIN_ROW_UNSAFE')
    need(not rows[-1]['mode']&stat.S_ISGID,'PARENT_SETGID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(text(plan['template_revision'],'[0-9a-f]{40}'),'TEMPLATE_REVISION_UNBOUND')
    need(text(plan['daemon_reload_owner'],'[A-Z][A-Z0-9_]{2,63}') and plan['daemon_reload_owner']!='UNBOUND','RELOAD_OWNER_UNBOUND')
    validate_allowlist(plan['network_allowlist'])
    units=plan['units']
    need(type(units) is list and 0<len(units)<=MAX_UNITS,'UNITS_INVALID')
    for unit in units:
        need(type(unit) is dict and set(unit)==set(UNIT_KEYS) and text(unit['key'],'[A-Z][A-Z0-9_]{0,31}')
             and type(unit['mode']) is int and unit['mode']==UNIT_MODE and type(unit['placeholders']) is dict,'UNITS_INVALID')
        need(unit_name(unit['destination_name']),'UNIT_NAME_INVALID')
        expect=unit['expect']
        need(expect=='ABSENT' or (type(expect) is dict and set(expect)=={'device','inode','links'} and integer(expect['device'])
                                  and integer(expect['inode'],1) and integer(expect['links'],1,2)),'EXPECT_INVALID')
    need(len({unit['key'] for unit in units})==len(units)
         and len({unit['destination_name'] for unit in units})==len(units),'UNIT_NAME_DUPLICATE')
    volume,placement,tree=plan['data_volume_path'],plan['journal_placement'],plan['deploy_tree_path']
    supervisor=any(unit['profile']==SERVICE_PROFILE for unit in units)
    need((volume is not None)==supervisor,'DATA_VOLUME_PATH')
    # The placement and the deploy tree belong to the supervisor service alone; a list without it signs neither.
    need(supervisor or (placement is None and tree is None),'PLACEMENT_UNKNOWN')
    total=0
    for unit in units:
        render_unit(unit,plan['network_allowlist'],volume,placement,tree);total+=len(decode_template(unit))
    need(total<=MAX_TEMPLATE_BYTES_TOTAL,'TEMPLATE_TOO_LARGE')
    leftovers=plan['acknowledged_leftovers']
    need(type(leftovers) is list and len(leftovers)<=MAX_LEFTOVERS,'LEFTOVERS_INVALID')
    for item in leftovers:
        need(type(item) is dict and set(item)=={'name','device','inode'} and text(item['name'],LEFTOVER)
             and integer(item['device']) and integer(item['inode'],1),'LEFTOVERS_INVALID')
    need(len({item['name'] for item in leftovers})==len(leftovers),'LEFTOVERS_INVALID')
    need(any(unit['expect']=='ABSENT' for unit in units),'NOTHING_TO_CREATE')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,'directory':UNIT_DIRECTORY,'directory_row':plan['unit_directory'][-1],
            'chain_sha256':sha(canonical(plan['unit_directory'])),
            'units':[{'destination_name':unit['destination_name'],'mode_octal':'%04o'%unit['mode'],'profile':unit['profile'],
                      'template_sha256':unit['template_sha256'],'rendered_sha256':unit['rendered_sha256'],
                      'rendered_bytes':unit['rendered_bytes'],'substitutions':unit['placeholders'],
                      'expect':'ABSENT' if unit['expect']=='ABSENT' else 'PRESENT'} for unit in plan['units']],
            'files_to_create':sum(1 for unit in plan['units'] if unit['expect']=='ABSENT'),
            'network_allowlist':plan['network_allowlist'],'journal_placement':plan['journal_placement'],
            'data_volume_path':plan['data_volume_path'],'deploy_tree_path':plan['deploy_tree_path'],
            'template_revision':plan['template_revision'],
            'acknowledged_leftovers':[item['name'] for item in plan['acknowledged_leftovers']],
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'daemon_reload':{'performed_by_this_operation':False,'owner':plan['daemon_reload_owner']},
            'external_processes':0,'pre_existing_objects_modified':False,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME


def precheck(plan,host,gate,rendered,detail,go16):
    """Everything is looked at before the first creation, by lstat (and, for a regular file already at a destination
    name, by reading it to say whether it is the signed render). Returns (pinned directory, refusal code or None)."""
    observed=[];detail['unit_directory']=observed
    fd=walk_pinned(host,plan['unit_directory'],gate,observed)
    directory=Pinned(host,fd,rows=plan['unit_directory'])
    rows=[];states=set()
    for unit,content in zip(plan['units'],rendered):
        name=unit['destination_name'];expect=unit['expect']
        row={'key':unit['key'],'destination_name':name,'expected':'ABSENT' if expect=='ABSENT' else 'PRESENT'}
        rows.append(row);gate()
        try:named=host.lstat(name,fd)
        except FileNotFoundError:named=None
        if named is None:
            row['observed']='ABSENT';row['state']='OK_ABSENT' if expect=='ABSENT' else 'EXPECTED_PRESENT_ABSENT'
        else:
            facts=file_row(named);size=facts.pop('size');row['observed']='PRESENT';row.update(facts);equal=None
            if stat.S_ISREG(named.st_mode):
                try:
                    raw,info=read_regular(host,name,fd,gate,MAX_RENDER_BYTES)
                    equal=raw==content and (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino)
                except Refused as error:row['read_code']=code_of(error,'FILE_UNREADABLE')
                row['bytes_equal_signed_render']=equal
                # A digest or a size is reported only for bytes proved equal to the signed render (they are then the
                # signed values). A foreign unit may carry an inline secret; its digest would be an offline test for it.
                if equal:row.update(sha256=sha(raw),size=size)
            conforms=bool(equal and named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==UNIT_MODE)
            if not stat.S_ISREG(named.st_mode):row['state']='OCCUPIED_NOT_REGULAR'
            elif expect=='ABSENT':row['state']='PRESENT_EQUAL_NOT_SIGNED' if conforms and named.st_nlink in (1,2) else 'PRESENT_FOREIGN'
            elif conforms and (named.st_dev,named.st_ino,named.st_nlink)==(expect['device'],expect['inode'],expect['links']):
                row['state']='OK_PRESENT'
            else:row['state']='PRESENT_IDENTITY_MISMATCH'
        states.add(row['state'])
    scan=conflict_scan(host,[unit['destination_name'] for unit in plan['units']],gate)
    signed={item['name']:(item['device'],item['inode']) for item in plan['acknowledged_leftovers']}
    seen={item['name']:(item['device'],item['inode']) for item in scan['leftovers']}
    own={TEMPORARY%(go16,index) for index,unit in enumerate(plan['units']) if unit['expect']=='ABSENT'}
    scan['leftovers_acknowledged']=sorted(name for name in seen if signed.get(name)==seen[name])
    scan['leftovers_not_acknowledged']=sorted(name for name in seen if signed.get(name)!=seen[name])
    detail['precheck']={'units':rows,'conflicts':scan}
    present=[row['observed']=='PRESENT' for row in rows];code=None
    # Fixed precedence. None of these says that an installation happened: they say what exists.
    if 'OCCUPIED_NOT_REGULAR' in states:code='UNIT_NAME_OCCUPIED'
    elif 'PRESENT_FOREIGN' in states:code='UNIT_PRESENT_FOREIGN_CONTENT'
    elif states&{'EXPECTED_PRESENT_ABSENT','PRESENT_IDENTITY_MISMATCH'} or set(signed)-set(seen):code='EXPECTATION_MISMATCH'
    elif 'PRESENT_EQUAL_NOT_SIGNED' in states:
        # "All present" is said only of one-link files with no unacknowledged temporary beside them; a name that still
        # shares its inode with a temporary is the state an interrupted run leaves.
        settled=all(present) and all(row['links']==1 for row in rows) and not scan['leftovers_not_acknowledged'] and scan['leftover_count']<=MAX_FINDINGS
        code='ALL_UNITS_PRESENT' if settled else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'
    elif scan['leftover_count']>MAX_FINDINGS or scan['leftovers_not_acknowledged']:
        code='TEMPORARY_NAME_OCCUPIED' if own&set(scan['leftovers_not_acknowledged']) else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'
    elif own&set(seen):code='TEMPORARY_NAME_OCCUPIED'
    elif 'DROP_IN_PRESENT' in scan['finding_codes']:code='DROP_IN_PRESENT'
    elif 'OWN_DEPENDENCY_DIRECTORY_PRESENT' in scan['finding_codes']:code='OWN_DEPENDENCY_DIRECTORY_PRESENT'
    elif 'ENABLEMENT_LINK_PRESENT' in scan['finding_codes']:code='ENABLEMENT_LINK_PRESENT'
    elif 'ALIAS_LINK_PRESENT' in scan['finding_codes']:code='ALIAS_LINK_PRESENT'
    elif 'UNIT_SHADOWED_IN_OTHER_PATH' in scan['finding_codes']:code='UNIT_SHADOWED_IN_OTHER_PATH'
    elif scan['status']!='COMPLETE':code='CONFLICT_SCAN_UNAVAILABLE'
    return directory,code

def number(error):return error.errno if isinstance(error,OSError) and type(error.errno) is int else None

def remove_own_temporary(temp,fd,directory,host,gate,state,entry):
    """The single removal of the family: the temporary this run created, and only while the name still shows the
    inode of the descriptor held. Anything else at that name is left in place. Returns a code, or None; the errno of a
    failed removal goes to its own field, so the errno of the failure that led here is kept."""
    try:
        named=host.lstat(temp,directory.fd);held=host.fstat(fd)
        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino):return 'TEMPORARY_REPLACED'
        mutate(state,gate,lambda:host.unlink(temp,directory.fd))
        entry['temporary_removed']=True
    except Refused as error:return code_of(error,'GO_EXPIRED')
    except OSError as error:
        entry['temporary_removal_errno']=number(error);return 'TEMPORARY_REMOVAL_FAILED'
    try:host.fsync(directory.fd);entry['fsync_directory_after_removal']=True
    except OSError as error:
        entry['temporary_removal_errno']=number(error);return 'FSYNC_FAILED'
    return None

def install_unit(index,unit,content,directory,host,gate,state,go16):
    """One unit: exclusive temporary, unbuffered writes, fsync, exact metadata, link to the final name, fsync of the
    directory, removal of the temporary. Returns the ledger row. Nothing is repaired and nothing raises past here."""
    name=unit['destination_name'];temp=TEMPORARY%(go16,index)
    entry={'key':unit['key'],'path':UNIT_DIRECTORY+'/'+name,'state':'NOT_ATTEMPTED','code':None,'errno':None,'bytes':None,
           'sha256_signed':unit['rendered_sha256'],'sha256_observed':None,'mode_octal':None,'uid':None,'gid':None,'links':None,
           'device':None,'inode':None,'temporary_name':temp,'temporary_removed':False,'temporary_removal_code':None,
           'temporary_removal_errno':None,'fsync_file':False,'fsync_directory_after_link':False,'fsync_directory_after_removal':False}
    def failed(code,error=None,**more):
        entry.update(code=code,**more)
        if error is not None:entry['errno']=number(error)
        return entry
    def withdrawn(code,error=None):
        """A failure before the final name exists (never the expiry and replaced-directory paths, which do not come
        here): the temporary of this run is withdrawn by the same gated removal as after the link, relative to the
        descriptor held, and only if the name still shows the file's descriptor. Otherwise it stays, labelled."""
        failed(code,error)
        entry['temporary_removal_code']=remove_own_temporary(temp,fd,directory,host,gate,state,entry)
        if entry['temporary_removed']:entry['state']='NOT_CREATED'
        return entry
    try:directory.verify(gate)
    except Refused as error:return failed(code_of(error,'PARENT_REPLACED'))
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    try:fd=mutate(state,gate,lambda:host.create(temp,flags,UNIT_MODE,directory.fd))
    except Refused as error:return failed(code_of(error,'GO_EXPIRED'))
    except OSError as error:
        return failed('TEMPORARY_NAME_OCCUPIED' if error.errno==errno.EEXIST else filesystem_code(error),error,state='NOT_CREATED')
    entry['state']='TEMPORARY_ONLY'
    try:
        written=0
        try:
            while written<len(content):
                size=mutate(state,gate,lambda:host.write(fd,content[written:written+65536]))
                if type(size) is not int or size<=0:return withdrawn('WRITE_INCOMPLETE')
                written+=size
        except Refused as error:return failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:return withdrawn(filesystem_code(error),error)
        entry['bytes']=written
        try:host.fsync(fd);entry['fsync_file']=True
        except OSError as error:return withdrawn('FSYNC_FAILED',error)
        try:
            info=host.fstat(fd)
            entry.update(mode_octal='%04o'%stat.S_IMODE(info.st_mode),uid=info.st_uid,gid=info.st_gid,links=info.st_nlink,
                         device=info.st_dev,inode=info.st_ino)
            if not (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0 and info.st_gid==0
                    and stat.S_IMODE(info.st_mode)==UNIT_MODE and info.st_size==len(content)
                    and info.st_dev==directory.identity[0]):return withdrawn('CREATED_METADATA_MISMATCH')
        except OSError as error:return withdrawn('CREATED_STAT_FAILED',error)
        try:directory.verify(gate)
        except Refused as error:return failed(code_of(error,'PARENT_REPLACED'))
        # link() acts on the name, not on the descriptor held: the name is looked at again right before it. A swap
        # after this lstat is not excluded; it is caught after the link (TEMPORARY_REPLACED, in-run readback).
        try:
            gate();named=host.lstat(temp,directory.fd)
            if (named.st_dev,named.st_ino,named.st_nlink)!=(info.st_dev,info.st_ino,1):return failed('TEMPORARY_REPLACED')
        except Refused as error:return failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:return failed('TEMPORARY_REPLACED',error)
        # Complete, fsynced bytes are the only thing that ever appears under a name systemd loads.
        try:mutate(state,gate,lambda:host.link(temp,name,directory.fd))
        except Refused as error:return failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:
            if error.errno!=errno.EEXIST:return withdrawn(filesystem_code(error),error)
            # Something took the name after the precheck. It is not touched; only this run's own temporary is withdrawn.
            failed('DESTINATION_APPEARED_AFTER_PRECHECK',error)
            entry['temporary_removal_code']=remove_own_temporary(temp,fd,directory,host,gate,state,entry)
            if entry['temporary_removed']:entry['state']='NOT_CREATED'
            return entry
        entry['state']='LINKED_TEMPORARY_PRESENT'
        try:host.fsync(directory.fd);entry['fsync_directory_after_link']=True
        except OSError as error:return failed('FSYNC_FAILED',error)
        code=entry['temporary_removal_code']=remove_own_temporary(temp,fd,directory,host,gate,state,entry)
        if entry['temporary_removed']:entry['state']='INSTALLED_NOT_DURABLE'
        if code is not None:return failed(code,errno=entry['temporary_removal_errno'])
        try:entry['links']=host.fstat(fd).st_nlink
        except OSError as error:return failed('CREATED_STAT_FAILED',error)
        if entry['links']!=1:return failed('CREATED_METADATA_MISMATCH')
        entry['state']='INSTALLED_DURABLE';return entry
    finally:
        try:host.close(fd)
        except Exception:pass

def readback(plan,rendered,directory,host,gate,ledger):
    """Inside the run: each final name opened again without following a link; same inode as created, one link, exact
    owner and mode, bytes equal to the signed render."""
    result={'status':'COMPLETE','code':None}
    try:
        directory.verify(gate)
        for unit,content,entry in zip(plan['units'],rendered,ledger):
            raw,info=read_regular(host,unit['destination_name'],directory.fd,gate,MAX_RENDER_BYTES)
            entry['sha256_observed']=sha(raw)
            same=entry['state']!='INSTALLED_DURABLE' or (info.st_dev,info.st_ino)==(entry['device'],entry['inode'])
            need(raw==content and same and info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)==UNIT_MODE
                 and (info.st_nlink==1 or entry['state']!='INSTALLED_DURABLE'),'READBACK_HASH_MISMATCH')
    except Exception as error:
        result.update(status='UNAVAILABLE',code=code_of(error,'READBACK_UNAVAILABLE'))
    return result

def _reduce_scan(receipt):
    scan=(receipt.get('precheck') or {}).get('conflicts')
    if type(scan) is dict:scan['directories']={name:item.get('status') for name,item in scan.get('directories',{}).items()}
def _reduce_precheck(receipt):
    table=receipt.get('precheck') or {}
    receipt['precheck']={'units':[{'key':row.get('key'),'state':row.get('state')} for row in table.get('units',[])],
                         'finding_codes':(table.get('conflicts') or {}).get('finding_codes')}
REDUCTIONS=[('SCAN_DIRECTORIES_REDUCED_TO_STATUS',_reduce_scan),('PRECHECK_REDUCED_TO_STATES',_reduce_precheck)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    # Pure step: every unit is rendered again from the signed bytes and values and must hash to the signed render.
    rendered=[render_unit(unit,plan['network_allowlist'],plan['data_volume_path'],plan['journal_placement'],plan['deploy_tree_path']) for unit in plan['units']]
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'unit_directory':[],'precheck':None};ledger=[];directory=None;go16=bound['go_sha256'][:16]
    def finish(status,outcome,code,extra):
        try:
            ended,elapsed=clock(),monotonic()-mark
            timing={'utc_start':begun.isoformat(),'utc_end':ended.isoformat(),'monotonic_elapsed_ms':int(elapsed*1000)}
        except Exception:timing=None
        left=sum(1 for row in ledger if row['state'] in ('TEMPORARY_ONLY','INSTALLED_DURABLE','INSTALLED_NOT_DURABLE'))
        left+=2*sum(1 for row in ledger if row['state']=='LINKED_TEMPORARY_PRESENT')
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing,
            mutating_calls=state.counts(),unit_directory=detail['unit_directory'],precheck=detail['precheck'],ledger=ledger,
            external_processes=0,daemon_reload_owner=plan['daemon_reload_owner'],objects_left_by_this_run=left,
            pre_existing_objects_modified=False,**extra))
        return seal(receipt)
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o022)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            directory,code=precheck(plan,host,gate,rendered,detail,go16)
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:
            return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        stop=None
        for index,(unit,content) in enumerate(zip(plan['units'],rendered)):
            if unit['expect']!='ABSENT' or stop is not None:
                ledger.append({'key':unit['key'],'path':UNIT_DIRECTORY+'/'+unit['destination_name'],'code':None,
                               'state':'NOT_ATTEMPTED' if unit['expect']=='ABSENT' else 'PRESENT_VERIFIED_NOT_TOUCHED',
                               'sha256_signed':unit['rendered_sha256'],'sha256_observed':None});continue
            entry=install_unit(index,unit,content,directory,host,gate,state,go16);ledger.append(entry)
            if entry['state']!='INSTALLED_DURABLE':stop=entry['code'] or 'INSTALL_FAILED'
        check=None
        if stop is None:
            check=readback(plan,rendered,directory,host,gate,ledger)
            if check['status']!='COMPLETE':stop=check['code'] or 'READBACK_UNAVAILABLE'
        extra={'phase_reached':'CREATION','readback':check}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        if directory is not None:
            try:directory.close()
            except Exception:pass
