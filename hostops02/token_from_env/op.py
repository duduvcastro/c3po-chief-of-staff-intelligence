OPERATION='GO_WRITE_HOSTOPS02_TOKEN_FROM_ENV_01'
PHASE='WRITE_SUPERVISOR_TOKEN_FROM_THE_DEPLOY_ENVIRONMENT_FILE'
REQUEST_SCHEMA='WRITE_HOSTOPS02_TOKEN_FROM_ENV_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_TOKEN_FROM_ENV_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_TOKEN_FROM_ENV_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_TOKEN_FROM_ENV_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_TOKEN_FROM_ENV_PLAN_V1'
SOURCE_NAME='token_from_env.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_WEEKEND'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
PROVISION_OPERATION='GO_WRITE_SUPERVISOR_READER_PROVISION_01'
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='TOKEN_PLACED_METADATA_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_SEE_TOKEN_FILE_STATE'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_TOKEN_FILE_MAY_EXIST'
PLAN_KEYS=frozenset(('config_chain','deploy_directory','evidence_boot_id_sha256'))

# ---- the constants of this operation. A request cannot move any of them: they are bytes of the signed source.
# The days: the token must exist before the readback of Sunday 2026-10-04 09:50 BRT and before the first session.
# The date class of the core (WRITE_WEEKEND) also holds 2026-10-02; this source narrows it to the two days below.
TOKEN_DAYS=('2026-10-03','2026-10-04')
# Where the supervisor reads the token (README of c3po/deployment/massive-supervisor at dd4ec4bb, "Token procedure"),
# and what it accepts there (r2d2_v2_massive_supervisor.py:38-55, private_bytes, and :114-115, the read): a regular
# file, one link, owned by the effective uid of the supervisor (uid 0), mode 0600, 1 to 4096 bytes, decoded as UTF-8,
# stripped, not empty and without a line break.
CONFIG_DIRECTORY='/etc/c3po-bar'
CONFIG_DIRECTORY_MODE=0o700
TOKEN_NAME='token'
TOKEN_PATH=CONFIG_DIRECTORY+'/'+TOKEN_NAME
TOKEN_FILE_MODE=0o600
TOKEN_MAX_FILE_BYTES=4096
TOKEN_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
# Where the value comes from: the environment file of the deploy tree, which docker compose reads for every backend
# service (c3po/compose.yml: env_file ../.env) and which holds MASSIVE_API_TOKEN (README line 207). The backend accepts
# C3PO_MASSIVE_API_TOKEN or MASSIVE_API_TOKEN, the first one present winning (c3po/backend/app/config.py:116-118,
# pydantic AliasChoices; names matched without regard to case). Both names are looked for, in any case.
ENV_FILE_NAME='.env'
MAX_ENV_FILE_BYTES=65536
TOKEN_KEYS=('C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN')
# The value: what every reader of the file takes as the same bytes (no quote, space, "#", "$" or backslash), one line,
# ASCII, 16 to 512 characters. The supervisor needs a non-empty single line after strip(); this grammar implies it.
TOKEN_VALUE_GRAMMAR='[A-Za-z0-9._~+/=-]{16,512}'
TOKEN_VALUE=TOKEN_VALUE_GRAMMAR.encode('ascii')
# The lines of the environment file, as docker compose's dotenv parser delimits its statements. A file in which any
# line is none of these is refused whole: a statement boundary that differs from compose's could hide a definition.
ENV_LINE_BLANK=rb'[ \t]*'
ENV_LINE_COMMENT=rb'[ \t]*#.*'
ENV_LINE_STATEMENT=rb'([ \t]*)(export[ \t]+)?([A-Za-z0-9_.\[\]-]+)([ \t]*)(?:([=:])([ \t]*)(.*))?'
ENV_QUOTED_TAIL=rb'[ \t]*(?:#.*)?'
ENV_RULES=['the file holds no carriage return and no NUL byte',
           'every line is blank (spaces and tabs), a comment (# after spaces and tabs), or a statement: optional spaces and tabs, '
           'optional "export" and spaces or tabs, a name of the characters A-Z a-z 0-9 _ . - [ ], optional spaces or tabs, and then '
           'either nothing (a name taken from the environment of compose) or "=" or ":", optional spaces or tabs and a value',
           'a value that begins with a quote ends on the same line at the next quote of the same kind, holds no backslash, and is '
           'followed by nothing but spaces, tabs and an optional comment; a value that does not begin with a quote ends at the end '
           'of its line and does not begin with a vertical tab, a form feed or a byte above 127',
           'a statement whose name equals MASSIVE_API_TOKEN or C3PO_MASSIVE_API_TOKEN without regard to case is a definition; every '
           'definition is exactly NAME=VALUE: the name in capitals, at the start of the line, no "export", "=" with no space on either side',
           'at least one definition; every definition of both names byte-equal (compose keeps the last of a name, the backend the '
           'first of the two names present)',
           'the value matches '+TOKEN_VALUE_GRAMMAR+' to the end of its line (no quote, space, comment, "$" or backslash)']
WRITE_ALLOWANCE_SECONDS=15                # what must be left of the budget before the creation (the writes take milliseconds)
TOKEN_STATES=('NOT_ATTEMPTED','NOT_CREATED','CREATE_UNCERTAIN','WITHDRAWN','WITHDRAWN_NOT_DURABLE','LEFT_UNVERIFIED','PLACED_VERIFIED')

SCOPE_STATEMENT=('Reads the environment file .env of the signed deploy directory once, in memory, and places the value it holds for '
                 'MASSIVE_API_TOKEN (or C3PO_MASSIVE_API_TOKEN; every definition byte-equal) as the provider token of the supervisor: '
                 'one exclusive create of '+TOKEN_PATH+' (root:root 0600, one link, the value and one newline) relative to the held '
                 'descriptor of the configuration directory whose identity the request signs from the receipt of supervisor operation 2, '
                 'fsync of the file and of the directory, and a readback by descriptor of owner, mode, links, size within 1-4096 and the '
                 'bytes, compared in memory. A file that exists at that name is never touched. If a step after the creation fails, the '
                 'file this run created is removed while its name still shows the inode this run holds, and only then. On 2026-10-03 or '
                 '2026-10-04 UTC only. No process is started, no environment of a process and no container is read, nothing is activated, '
                 'and the receipt never carries the value, a digest of it, its length or a line count.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'token_days':list(TOKEN_DAYS),
       'paths':{'config_directory':CONFIG_DIRECTORY,'token_file':TOKEN_PATH,'environment_file':'<the signed deploy directory>/'+ENV_FILE_NAME},
       'token_file':{'type':'regular file','uid':0,'gid':0,'mode_octal':'%04o'%TOKEN_FILE_MODE,'links':1,'content':'the value, then one newline',
                     'bytes':'1 to %d, never reported'%TOKEN_MAX_FILE_BYTES,'umask_octal':'0077',
                     'creation':'one open O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC relative to the held descriptor of the configuration directory',
                     'withdrawal':'only after its own creation succeeded and a later step failed, only while the name shows the inode this run holds '
                                  'with one link; never after the expiry of the GO or a replaced directory'},
       'config_directory':{'path':CONFIG_DIRECTORY,'uid':0,'gid':0,'mode_octal':'%04o'%CONFIG_DIRECTORY_MODE,'rows':'signed, from "/"'},
       'environment_file':{'name':ENV_FILE_NAME,'max_bytes':MAX_ENV_FILE_BYTES,'keys':list(TOKEN_KEYS),'value_grammar':TOKEN_VALUE_GRAMMAR,'rules':ENV_RULES,
                           'chain':'walked from "/" without following a link and not signed: every component a directory, above the deploy directory '
                                   'root-owned and closed to group and other, none writable by any user without the sticky bit',
                           'file':'regular, not world-writable, owned by root or by the owner of the deploy directory, unchanged while read'},
       'receipt_never':['the value','a digest of the value','the length of the value','a line count','any byte of the environment file'],
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'<the signed deploy directory>/'+ENV_FILE_NAME+' (in memory)',TOKEN_PATH+' (the readback, in memory)'],
       'processes_started':0,
       'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the token file this run created','a process','docker','systemctl',
                'a shell','a network connection','the environment of a process or of a container','activation','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'environment_file_bytes':MAX_ENV_FILE_BYTES,'token_file_bytes':TOKEN_MAX_FILE_BYTES,'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeFiles):
    """Everything this source can do to the host: the read primitives and the creating calls of the files part. No process."""


# ---------------------------------------------------------------- the environment file, in memory
def value_boundary(value):
    """A value ends where compose's parser ends it: a quoted one at its closing quote, an unquoted one at the end of its
    line. Only the forms whose end is certain are accepted."""
    if value[:1] in (b'"',b"'"):
        closing=value.find(value[:1],1)            # -1 when the quote is not closed on this line: the tail is then the
        need(b'\\' not in value[1:closing] and re.fullmatch(ENV_QUOTED_TAIL,value[closing+1:]) is not None,'ENV_FILE_SYNTAX_UNSUPPORTED')   # whole value, refused
    else:
        need(value[:1] not in (b'\x0b',b'\x0c') and (not value or value[0]<0x80),'ENV_FILE_SYNTAX_UNSUPPORTED')

def token_definitions(raw):
    """[(name, start, end)] of every definition of the two names, as offsets of the value in raw. Raises Refused with a
    constant code for a file outside the accepted subset or a definition that is not the plain form. Nothing of the
    bytes leaves this function but offsets."""
    need(b'\r' not in raw and b'\x00' not in raw,'ENV_FILE_SYNTAX_UNSUPPORTED')
    names={key.encode('ascii'):key for key in TOKEN_KEYS}
    found=[];position=0;size=len(raw)
    while position<=size:
        end=raw.find(b'\n',position)
        if end<0:end=size
        line=raw[position:end]
        if re.fullmatch(ENV_LINE_BLANK,line) is None and re.fullmatch(ENV_LINE_COMMENT,line) is None:
            match=re.fullmatch(ENV_LINE_STATEMENT,line)
            need(match is not None,'ENV_FILE_SYNTAX_UNSUPPORTED')
            lead,export,key,space,separator,gap,value=match.groups()
            if separator is not None:value_boundary(value)
            if key.upper() in names:
                need(not lead and export is None and key in names and not space and separator==b'=' and not gap,'ENV_TOKEN_DEFINITION_NOT_PLAIN')
                found.append((names[key],position+len(key)+1,end))
        position=end+1
    return found

def token_content(raw,found):
    """The value every definition holds, and one newline, in a new bytearray (zeroed by the caller after use)."""
    need(found,'ENV_TOKEN_ABSENT')
    view=memoryview(raw)
    try:
        first=view[found[0][1]:found[0][2]]
        need(all(view[start:end]==first for _,start,end in found),'ENV_TOKEN_DEFINITIONS_DISAGREE')
        need(re.fullmatch(TOKEN_VALUE,first) is not None,'ENV_TOKEN_VALUE_GRAMMAR')
        content=bytearray(len(first)+1);content[:len(first)]=first;content[len(first)]=0x0a
        return content
    finally:view.release()

def zero(buffer):
    """Best effort: the bytearray that held the value is overwritten in place. Immutable copies made by the interpreter
    (the bytes read from the file) cannot be overwritten; they are only dropped."""
    if type(buffer) is bytearray:
        for index in range(len(buffer)):buffer[index]=0


def validate_plan(plan):
    rows=validate_chain(plan['config_chain'],CONFIG_DIRECTORY,receives_entry=True)         # every row root-owned, closed to group and other
    need((rows[-1]['gid'],rows[-1]['mode'])==(0,CONFIG_DIRECTORY_MODE),'CONFIG_DIRECTORY_NOT_ROOT_0700')
    deploy=plan['deploy_directory']
    need(clean_path(deploy),'DEPLOY_DIRECTORY_INVALID')
    need(not inside(deploy,CONFIG_DIRECTORY) and not inside(CONFIG_DIRECTORY,deploy),'DEPLOY_DIRECTORY_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(instant(plan['window']['not_before']).date().isoformat() in TOKEN_DAYS,'WINDOW_NOT_ON_A_TOKEN_DAY')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    deploy=plan['deploy_directory']
    return {'operation':OPERATION,
            'config_directory':dict(chain_effects(plan['config_chain']),required={'uid':0,'gid':0,'mode_octal':'%04o'%CONFIG_DIRECTORY_MODE}),
            'token_file':{'path':TOKEN_PATH,'expect':'ABSENT','uid':0,'gid':0,'mode_octal':'%04o'%TOKEN_FILE_MODE,'links':1,
                          'content':'the value of the environment file, then one newline','size':'within 1-%d (a boolean, never the size)'%TOKEN_MAX_FILE_BYTES},
            'environment_file':{'path':deploy+'/'+ENV_FILE_NAME,'deploy_directory':deploy,'keys':list(TOKEN_KEYS),'value_grammar':TOKEN_VALUE_GRAMMAR,
                                'chain':'walked by this run, not signed'},
            'token_days':list(TOKEN_DAYS),'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':False,'process_started':False,'activation':False,'value_in_receipt':False}
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the reads before the creation
DEPLOY_CODES={'SYMLINK_COMPONENT':'DEPLOY_CHAIN_SYMLINK','COMPONENT_NOT_DIRECTORY':'DEPLOY_CHAIN_NOT_A_DIRECTORY','PATH_CHANGED':'DEPLOY_CHAIN_CHANGED_DURING_WALK',
              'CHAIN_ROW_UNSAFE':'DEPLOY_CHAIN_NOT_ROOT_OWNED_ABOVE_THE_DEPLOY_DIRECTORY','CHAIN_ROW_WORLD_WRITABLE':'DEPLOY_CHAIN_WORLD_WRITABLE'}
ENV_CODES={'FILE_NOT_REGULAR':'ENV_FILE_NOT_REGULAR','FILE_TOO_LARGE':'ENV_FILE_TOO_LARGE','FILE_CHANGED_DURING_READ':'ENV_FILE_CHANGED_DURING_READ'}
def renamed(error,table):return Refused(table.get(str(error),str(error)))

def chain_facts():
    return {'walked_without_following_a_link':None,'root_owned_and_closed_above_the_deploy_directory':None,'no_component_world_writable_without_sticky':None}
def environment_facts():
    return {'present':None,'regular':None,'not_world_writable':None,'owner_root_or_the_deploy_directory_owner':None,'within_the_size_bound':None,
            'unchanged_during_read':None,'syntax_within_the_accepted_subset':None,'every_definition_plain':None,
            'names_defined':{key:None for key in TOKEN_KEYS},'definitions_agree':None,'value_grammar_met':None}

def deploy_chain(host,deploy,gate,facts):
    """The deploy directory, walked from "/" without following a link, and the rows as read judged by the family's rule
    with the deploy directory as the open root. Returns the held descriptor and the observed rows (which stay here)."""
    observed=[]
    try:fd=descend(host,deploy,gate,observed)
    except FileNotFoundError:raise Refused('DEPLOY_DIRECTORY_ABSENT') from None
    except Refused as error:raise renamed(error,DEPLOY_CODES) from None
    try:
        facts['walked_without_following_a_link']=True
        facts['root_owned_and_closed_above_the_deploy_directory']=all(row_root_safe(row) for row in observed[:-1])
        facts['no_component_world_writable_without_sticky']=not any(world_writable_without_sticky(row) for row in observed)
        try:validate_chain(observed,deploy,open_root=deploy)
        except Refused as error:raise renamed(error,DEPLOY_CODES) from None
        return fd,observed
    except BaseException:
        host.close(fd);raise

def environment_bytes(host,fd,owner,gate,facts):
    """The bytes of the environment file of the held deploy directory, read once, unchanged while read."""
    gate()
    try:named=host.lstat(ENV_FILE_NAME,fd)
    except FileNotFoundError:raise Refused('ENV_FILE_ABSENT') from None
    facts['present']=True
    need(stat.S_ISREG(named.st_mode),'ENV_FILE_NOT_REGULAR');facts['regular']=True
    need(not named.st_mode&0o002,'ENV_FILE_WORLD_WRITABLE');facts['not_world_writable']=True
    need(named.st_uid in (0,owner),'ENV_FILE_OWNER_UNEXPECTED');facts['owner_root_or_the_deploy_directory_owner']=True
    try:raw,info=read_regular(host,ENV_FILE_NAME,fd,gate,MAX_ENV_FILE_BYTES)
    except FileNotFoundError:raise Refused('ENV_FILE_CHANGED_DURING_READ') from None
    except Refused as error:raise renamed(error,ENV_CODES) from None
    facts['within_the_size_bound']=True
    gate()
    try:after=host.lstat(ENV_FILE_NAME,fd)
    except FileNotFoundError:raise Refused('ENV_FILE_CHANGED_DURING_READ') from None
    need(stat_signature(info)==stat_signature(named)==stat_signature(after),'ENV_FILE_CHANGED_DURING_READ')
    facts['unchanged_during_read']=True
    return raw

def environment_token(raw,facts):
    """The parse, with its facts: which names were found and that the rules held (booleans only)."""
    found=token_definitions(raw);facts['syntax_within_the_accepted_subset']=True;facts['every_definition_plain']=True
    facts['names_defined']={key:any(name==key for name,_,_ in found) for key in TOKEN_KEYS}
    content=token_content(raw,found)
    facts['definitions_agree']=True;facts['value_grammar_met']=True
    return content


# ---------------------------------------------------------------- the creation, its readback and its withdrawal
def token_row():
    return {'path':TOKEN_PATH,'state':'NOT_ATTEMPTED','code':None,'errno':None,'created':False,'fsync_file':False,'fsync_directory':False,
            'device':None,'inode':None,'regular':None,'uid_0':None,'gid_0':None,'mode_0600':None,'single_link':None,'size_within_1_4096':None,
            'on_the_device_of_the_directory':None,'readback_same_inode':None,'readback_bytes_equal_what_was_written':None,
            'meets_the_supervisor_file_rules':None,'withdrawn':False,'withdrawal_code':None,'withdrawal_errno':None,'fsync_directory_after_withdrawal':False}

def metadata_facts(info,row,config):
    row.update(regular=stat.S_ISREG(info.st_mode),uid_0=info.st_uid==0,gid_0=info.st_gid==0,mode_0600=stat.S_IMODE(info.st_mode)==TOKEN_FILE_MODE,
               single_link=info.st_nlink==1,size_within_1_4096=1<=info.st_size<=TOKEN_MAX_FILE_BYTES,
               on_the_device_of_the_directory=info.st_dev==config.identity[0])
    row['meets_the_supervisor_file_rules']=all(row[key] for key in ('regular','uid_0','mode_0600','single_link','size_within_1_4096'))
    return row['meets_the_supervisor_file_rules'] and row['gid_0'] and row['on_the_device_of_the_directory']

def withdraw(fd,row,config,host,gate,state,code,error=None):
    """The one removal of this source: the file it created, after a later step failed, while the name still shows the
    inode of the descriptor held and that inode has one link. Anything else at the name is left in place."""
    row['code']=code
    if error is not None:row['errno']=number(error)
    row['state']='LEFT_UNVERIFIED'
    try:
        named=host.lstat(TOKEN_NAME,config.fd);held=host.fstat(fd)
        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino) or named.st_nlink!=1:
            row['withdrawal_code']='TOKEN_NAME_NOT_THIS_RUNS_FILE';return row
        mutate(state,gate,lambda:host.unlink(TOKEN_NAME,config.fd))
    except Refused as error:
        row['withdrawal_code']=code_of(error,'GO_EXPIRED');return row
    except OSError as error:
        row.update(withdrawal_code='TOKEN_WITHDRAWAL_FAILED',withdrawal_errno=number(error));return row
    except Exception:
        if state.pending:state.unknown()
        row['withdrawal_code']='TOKEN_WITHDRAWAL_UNCERTAIN';return row
    row.update(withdrawn=True,state='WITHDRAWN_NOT_DURABLE')
    try:host.fsync(config.fd)
    except OSError as error:
        row.update(withdrawal_code='FSYNC_FAILED',withdrawal_errno=number(error));return row
    row.update(state='WITHDRAWN',fsync_directory_after_withdrawal=True);return row

def place_token(content,config,host,gate,state):
    """One exclusive create, the writes, fsync of the file, its metadata, fsync of the directory, the readback by
    descriptor. Returns the ledger row; never raises for a failure of the host (an interrupt or the death of the process
    is not caught)."""
    row=token_row();fd=None;view=memoryview(content)
    try:
        try:fd=mutate(state,gate,lambda:host.create(TOKEN_NAME,TOKEN_CREATE_FLAGS,TOKEN_FILE_MODE,config.fd))
        except Refused as error:
            row['code']=code_of(error,'GO_EXPIRED');return row
        except OSError as error:
            row.update(state='NOT_CREATED',errno=number(error),
                       code='TOKEN_FILE_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))
            return row
        except Exception:
            if state.pending:state.unknown()
            row.update(state='CREATE_UNCERTAIN',code='TOKEN_CREATE_UNCERTAIN');return row
        row['created']=True;row['state']='LEFT_UNVERIFIED'
        try:
            written=0
            try:
                while written<len(content):
                    size=mutate(state,gate,lambda:host.write(fd,view[written:]))
                    if type(size) is not int or size<=0:return withdraw(fd,row,config,host,gate,state,'TOKEN_WRITE_INCOMPLETE')
                    written+=size
            except Refused as error:
                row['code']=code_of(error,'GO_EXPIRED');return row
            except OSError as error:return withdraw(fd,row,config,host,gate,state,filesystem_code(error),error)
            try:host.fsync(fd);row['fsync_file']=True
            except OSError as error:return withdraw(fd,row,config,host,gate,state,'FSYNC_FAILED',error)
            try:
                info=host.fstat(fd);row.update(device=info.st_dev,inode=info.st_ino)
                if not (metadata_facts(info,row,config) and info.st_size==len(content)):
                    return withdraw(fd,row,config,host,gate,state,'TOKEN_METADATA_MISMATCH')
            except OSError as error:return withdraw(fd,row,config,host,gate,state,'TOKEN_STAT_FAILED',error)
            try:host.fsync(config.fd);row['fsync_directory']=True
            except OSError as error:return withdraw(fd,row,config,host,gate,state,'FSYNC_FAILED',error)
            # the readback: the directory proved again from "/", the name opened again without following a link
            try:config.verify(gate)
            except Refused as error:
                row['code']=code_of(error,'PARENT_REPLACED');return row
            try:
                raw,seen=read_regular(host,TOKEN_NAME,config.fd,gate,TOKEN_MAX_FILE_BYTES)
                row['readback_same_inode']=(seen.st_dev,seen.st_ino)==(info.st_dev,info.st_ino)
                row['readback_bytes_equal_what_was_written']=raw==content
                raw=None
                if not (row['readback_same_inode'] and row['readback_bytes_equal_what_was_written'] and metadata_facts(seen,row,config)):
                    return withdraw(fd,row,config,host,gate,state,'READBACK_MISMATCH')
            except Refused as error:
                if str(error) in ('GO_EXPIRED','CLOCK_REVERSED'):
                    row['code']=str(error);return row
                return withdraw(fd,row,config,host,gate,state,'READBACK_MISMATCH')
            except OSError as error:return withdraw(fd,row,config,host,gate,state,'READBACK_UNAVAILABLE',error)
            row.update(state='PLACED_VERIFIED',code=None);return row
        except Exception:
            # a failure that is neither an OS error nor a refusal (the call it interrupted is uncertain): the file of this
            # run is withdrawn by identity, as after any other failure
            if state.pending:state.unknown()
            return withdraw(fd,row,config,host,gate,state,'TOKEN_PLACEMENT_FAILED')
    finally:
        view.release()
        if fd is not None:
            try:host.close(fd)
            except Exception:pass

def left_by_this_run(row):
    if row['state'] in ('PLACED_VERIFIED','LEFT_UNVERIFIED'):return 1
    return None if row['state']=='CREATE_UNCERTAIN' else 0


def _reduce_config(receipt):receipt['config_directory']={'rows_reduced_for_size':len((receipt.get('config_directory') or {}).get('rows') or [])}
REDUCTIONS=[('CONFIG_ROWS_REDUCED_TO_COUNT',_reduce_config)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    deploy=plan['deploy_directory']                           # pure: everything below reads the host
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    config_rows=[];chain=chain_facts();environment=environment_facts();precheck={'token_file_absent':None,'seconds_left_before_the_creation':None}
    pinned=[];held=[];buffers=[];token=[token_row()]
    def finish(status,outcome,code,extra):
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),
            config_directory={'rows':config_rows,'pinned':bool(pinned)},deploy_chain=chain,environment_file=environment,precheck=precheck,
            token_file=token[0],objects_left_by_this_run=left_by_this_run(token[0]),pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            config=Pinned(host,walk_pinned(host,plan['config_chain'],gate,config_rows),rows=plan['config_chain']);pinned.append(config)
            gate()
            try:host.lstat(TOKEN_NAME,config.fd)
            except FileNotFoundError:precheck['token_file_absent']=True
            else:
                precheck['token_file_absent']=False;raise Refused('TOKEN_FILE_PRESENT')
            fd,observed=deploy_chain(host,deploy,gate,chain);held.append(fd)
            raw=environment_bytes(host,fd,observed[-1]['uid'],gate,environment)
            content=environment_token(raw,environment);buffers.append(content);raw=None
            # The last refusals that cost nothing on the host: the time the creation and the readback may take, and the
            # configuration directory proved again from "/" just before the creation.
            left=gate();precheck['seconds_left_before_the_creation']=int(left)
            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            config.verify(gate)
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed
        token[0]=row=place_token(content,config,host,gate,state)
        stop=None if row['state']=='PLACED_VERIFIED' else (row['code'] or 'TOKEN_NOT_PLACED')
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for buffer in buffers:zero(buffer)
        for fd in held:
            try:host.close(fd)
            except Exception:pass
        for handle in pinned:
            try:handle.close()
            except Exception:pass
