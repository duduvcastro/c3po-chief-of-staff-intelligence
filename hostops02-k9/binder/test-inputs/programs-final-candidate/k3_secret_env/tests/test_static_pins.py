"""Byte and text pins of K3: the identity of the source, its constants, the scope, the list of receipt codes, and what
the operation part never names. Every test here is named "static": a mutation run deselects them, so that no mutant
dies merely because a pinned text changed."""
import ast
import json
import re

import family as f
import k3env as e

def test_static_identity_dates_evidence_parts_and_constants():
    m=e.K().m
    assert (m.OPERATION,m.PHASE,m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED,m.DATE_CLASS)==('GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01',
        'WRITE_READER_SECRET_ENV_IN_MEMORY',True,False,'WRITE_EPOCH')
    assert m.DATES==('2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10') and m.MAX_GATE_SPAN_SECONDS==900
    assert m.EVIDENCE_OPERATIONS==('GO_WRITE_SUPERVISOR_READER_PROVISION_01','GO_READONLY_HOSTOPS02_EPOCH_READBACK_01') and m.EVIDENCE_REQUIRED is True
    assert (m.COMPLETE_OUTCOME,m.PARTIAL_OUTCOME,m.REFUSED_OUTCOME,m.REDUCED_OUTCOME,m.ESCAPED_OUTCOME)==('READER_SECRET_ENV_PLACED_AND_READ_BACK',
        'PARTIAL_SEE_SECRET_ENV_STATE','REFUSED_NOTHING_CHANGED','RECEIPT_REDUCED_STATE_REQUIRES_READBACK','PARTIAL_STATE_UNKNOWN_SECRET_ENV_MAY_EXIST')
    assert set(m.PLAN_KEYS)=={'config_chain','worker_container_id','evidence_boot_id_sha256'}
    assert (m.CONFIG_DIRECTORY,m.CONFIG_DIRECTORY_MODE,m.SECRET_ENV_NAME,m.SECRET_ENV_PATH,m.SECRET_ENV_MODE)==('/etc/c3po-reader',0o700,'secret.env','/etc/c3po-reader/secret.env',0o600)
    assert (m.SECRET_KEY,m.SECRET_ENVIRONMENT_NAMES,m.SECRET_LINE_PREFIX,m.SECRET_VALUE_GRAMMAR)==('C3PO_DATABASE_URL',('C3PO_DATABASE_URL',),b'C3PO_DATABASE_URL=',
                                                                                                  rb'[\x21\x23-\x5b\x5d-\x7e]{1,4096}')
    assert (m.WORKER_CONTAINER_NAME,m.WORKER_NAME_PREFIX,m.WORKER_COMPOSE_PROJECT,m.WORKER_COMPOSE_SERVICE)==('c3po-r2d2-worker-1','c3po-r2d2-worker-','c3po','r2d2-worker')
    assert (m.TEMPORARY_PREFIX,m.MAX_CONFIG_ENTRIES,m.WRITE_ALLOWANCE_SECONDS,m.READBACK_REQUEST)==('.hostops-',64,15,4116)
    assert (m.OTHER_ENV_FILES,m.OTHER_ENV_FILE_LIMIT)==(('activation.env','pins.env'),65536)
    assert m.SECRET_CREATE_FLAGS==m.os.O_WRONLY|m.os.O_CREAT|m.os.O_EXCL|m.os.O_NOFOLLOW|m.os.O_CLOEXEC and m.READBACK_FLAGS==m.os.O_RDONLY|m.os.O_NOFOLLOW|m.os.O_NONBLOCK
    assert m.LABELS_FORMAT=='{"project":{{json (index .Config.Labels "com.docker.compose.project")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}}}'
    spec=f.assembler().load_spec(e.DIRECTORY);assert spec.PARTS==['core','runner','docker','parents','files'] and spec.SUCCESS_IN_TEMPLATE is True
    assert m.BINARIES=={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
    assert sorted(m.COMMANDS)==['container','container_labels','container_list','container_secret_environment']
    assert m.CORE_SHA256=='232f4180a940186e86d7599c10c4fac143fcfe3950baa8e853a3910f84f5c1e6'

def test_static_scope_says_what_the_signers_must_see():
    m=e.K().m;scope=json.loads(m.canonical(m.SCOPE))
    assert scope['secret_env']['path']=='/etc/c3po-reader/secret.env' and scope['secret_env']['expect']=='ABSENT' and scope['secret_env']['links']==1
    assert scope['config_directory']['path']=='/etc/c3po-reader' and scope['config_directory']['mode_octal']=='0700'
    assert scope['receipt_never']==['a value','a digest of the value, of the line or of the file','a length of the value or of the line','the size of the file',
                                    'a block count or a timestamp of the file']
    assert len(scope['exceptions_to_the_core'])==2 and scope['exceptions_to_the_core'][0].startswith('rule 4 ') and scope['exceptions_to_the_core'][1].startswith('rule 5 and 6 ')
    assert 'with no temporary' in scope['exceptions_to_the_core'][0]
    assert scope['receipt_codes']==sorted(m.RECEIPT_CODES) and scope['receipt_code_otherwise']=='UNLISTED_CODE'
    for word in ('docker exec','docker run','compose','systemctl','a read of the deploy tree or of its .env','overwrite','a second attempt','activation','a temporary file'):
        assert word in scope['never']
    assert scope['commands']['container_secret_environment']['argv'][3]==m.secret_environment_format(('C3PO_DATABASE_URL',))
    assert 'M3' in scope['worker']['id_note'] and 'WORKER_CONTAINER_MISMATCH' in scope['worker']['id_note']
    for sentence in ('makes its own process non-dumpable (prctl PR_SET_DUMPABLE 0, read back 0 with PR_GET_DUMPABLE); otherwise it refuses with nothing changed',
                     'prints exactly that entry, read twice and compared (that entry only)','exactly one line C3PO_DATABASE_URL=<value> and a newline',
                     'while its name there still shows the '
                     'inode this run holds with one link, and only then; that removal is not stopped by the gate','On 2026-10-03 to 2026-10-10 UTC','the bytes compared in memory with the line (booleans only)',
                     'never carries a value, a digest, a length or a size of the value, of the line or of the file'):assert sentence in m.SCOPE_STATEMENT,sentence
    assert m.SCOPE_STATEMENT.startswith('First of all, before anything of the host is looked at') and len(m.SCOPE_STATEMENT)<=4000
    assert scope['process']['dumpable']==0 and scope['process']['otherwise']=='refused, nothing changed: PROCESS_DUMPABLE_NOT_DISABLED'

def test_static_the_list_of_receipt_codes_is_every_code_the_source_writes_and_nothing_else():
    """Both ways, by text: every code-shaped literal of the operation part that is a code is listed; every listed code
    occurs as a literal in the built source."""
    m=e.K().m;own=(e.DIRECTORY/'op.py').read_text();built=(e.DIRECTORY/'build'/'k3_secret_env.py').read_text()
    words=set(re.findall(r"'([A-Z][A-Z0-9_]{2,79})'",own))
    not_codes={m.OPERATION,m.PHASE,m.REQUEST_SCHEMA,m.AUTHORITY_SCHEMA,m.GO_SCHEMA,m.RECEIPT_SCHEMA,m.PLAN_SCHEMA,m.DATE_CLASS,m.PROVISION_OPERATION,
               m.EPOCH_READBACK_OPERATION,m.COMPLETE_OUTCOME,m.PARTIAL_OUTCOME,m.REFUSED_OUTCOME,m.REDUCED_OUTCOME,m.ESCAPED_OUTCOME,m.UNLISTED_CODE,m.SECRET_KEY,
               'CONFIG_ROWS_REDUCED','PRECHECK','EFFECTS','COMPLETE','ABSENT','QUICK','READ',
               # the core's codes of read_regular, mapped to OTHER_ENV_FILE_UNREADABLE before they can reach a receipt
               'FILE_NOT_REGULAR','FILE_TOO_LARGE','FILE_CHANGED_DURING_READ',
               # the core's parse code for a line of the name that is not NAME=VALUE, mapped to SECRET_VALUE_SHAPE (review 2)
               'SECRET_ENVIRONMENT_SHAPE',
               # the plan's refusals: codes of the core's receipt of a refused authentication, never of perform()
               'CONFIG_DIRECTORY_NOT_ROOT_0700','WORKER_CONTAINER_UNBOUND','EVIDENCE_BOOT_UNBOUND'}|set(m.SECRET_ENV_STATES)
    codes=words-not_codes
    assert codes<=m.RECEIPT_CODES,sorted(codes-m.RECEIPT_CODES)
    missing=[code for code in m.RECEIPT_CODES if "'%s'"%code not in built];assert missing==[],missing
    assert set(m.FILESYSTEM_CODES.values())|{'FILESYSTEM_ERROR'}<=m.RECEIPT_CODES and 'SECRET_ENVIRONMENT_VALUE' not in m.RECEIPT_CODES

def test_static_the_operation_part_never_names_a_size_a_digest_or_an_encoding_of_what_it_reads():
    """No st_size, st_blocks or timestamp, no hashing or encoding module, sha() only for the scope hash, no print, no
    logging, no repr of a value."""
    own=(e.DIRECTORY/'op.py').read_text();tree=ast.parse(own)
    attributes={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    names=[node.id for node in ast.walk(tree) if isinstance(node,ast.Name)]
    assert not {'st_size','st_blocks','st_mtime','st_mtime_ns','st_ctime','st_ctime_ns','st_atime','st_atime_ns'}&attributes
    assert not {'hashlib','base64','binascii','zlib','logging','repr','format','hex','stat_signature'}&set(names)
    assert names.count('sha')==1 and 'SCOPE_SHA256=sha(canonical(SCOPE))' in own and 'import' not in own
    assert not {'hex','hexdigest','digest','b64encode'}&attributes
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='decode']
    assert calls and all(isinstance(call.func.value,ast.Name) and call.func.value.id.endswith('_GRAMMAR') for call in calls),'decode only of constants'
    # the one use of len() on a value is the write loop and the readback prefix; no length is stored in any row
    assert not re.search(r"row\[[^\]]+\]\s*=\s*len\(|row\.update\([^)]*len\(content",own)

def test_static_the_operation_part_reaches_nothing_by_reflection():
    own=ast.parse((e.DIRECTORY/'op.py').read_text())
    assert not [node for node in ast.walk(own) if isinstance(node,ast.Attribute) and node.attr.startswith('__')]
    assert not {node.id for node in ast.walk(own) if isinstance(node,ast.Name)}&{'getattr','setattr','globals','locals','vars','eval','exec','compile','__import__','open','print'}
