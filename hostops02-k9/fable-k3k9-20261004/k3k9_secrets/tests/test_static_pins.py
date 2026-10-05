"""Byte and text pins of K3-K9: the settings names of the release it is frozen for (dd4ec4bb), where the worker gets its
environment, which names the release's example environment file defines; the identity of the source; the scope; the
list of receipt codes; the one placement constant; and what the operation part never names. Every test here is named
"static": a mutation run deselects them, so that no mutant dies merely because a pinned text changed. The comparisons
with the files of the release run when a tree of it is at hand and are skipped otherwise; the literal pins always run."""
import ast
import json
import os
from pathlib import Path
import re

import pytest

import family as f
import k3

RELEASE_FILES={'c3po/backend/app/config.py':'91619929a513074f2eee01a6bcd78342305e0066e61ac79f2afd087c2e035897',
               'c3po/compose.yml':'fd214c8e36e47cc88f58e947eebf33c959e81c42929c4ecbb9149f87bdbd499e',
               'c3po/.env.example':'f650a4db2f4ebffd7d5cf83856275cb78505477cec2c1873f394ba4c25908dcb'}
def release():
    """A directory holding the files of the release (each compared by hash): HOSTOPS02_TEST_RELEASE_TREE, work/release
    of this operation directory, or an extraction of dd4ec4bb above it; skipped otherwise."""
    candidates=[Path(os.environ['HOSTOPS02_TEST_RELEASE_TREE'])] if os.environ.get('HOSTOPS02_TEST_RELEASE_TREE') else []
    candidates+=[k3.DIRECTORY/'work'/'release']+list(k3.DIRECTORY.parents)[:6]
    for candidate in candidates:
        try:
            if all(f.sha((candidate/name).read_bytes())==pin for name,pin in RELEASE_FILES.items()):return candidate
        except OSError:continue
    pytest.skip('no tree of the release at hand (HOSTOPS02_TEST_RELEASE_TREE)')
def lines(relative):return (release()/relative).read_text().splitlines()

def test_static_the_settings_names_and_where_the_worker_gets_them():
    m=k3.K().m;config=lines('c3po/backend/app/config.py')
    assert config[19]=='    model_config = SettingsConfigDict(env_prefix="C3PO_", extra="ignore", populate_by_name=True)'
    assert config[27]=='    r2d2_risk_database_url: str = Field(default="", repr=False)' and m.RISK_URL_KEY=='C3PO_R2D2_RISK_DATABASE_URL'
    for index,(prefixed,plain) in zip((106,110,112),m.PROVIDER_TOKEN_NAMES):
        assert 'validation_alias=AliasChoices("%s", "%s")'%(prefixed,plain) in config[index],config[index]
    compose=lines('c3po/compose.yml');worker=compose.index('  r2d2-worker:')
    assert compose[worker+5:worker+7]==['    env_file:','      - ../.env']
    example=lines('c3po/.env.example')
    assert [example[32],example[34],example[35]]==['EODHD_API_TOKEN=','FINNHUB_API_TOKEN=','FMP_API_TOKEN=']

def test_static_identity_dates_evidence_parts_and_constants():
    m=k3.K().m
    assert (m.OPERATION,m.PHASE,m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED,m.DATE_CLASS)==('GO_WRITE_HOSTOPS02_K3K9_SECRETS_01',
        'WRITE_K9_SECRETS_ENVIRONMENT_FILES_AND_EMITTER_PASSWORD',True,False,'WRITE_SESSIONS')
    assert m.DATES==('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10') and m.MAX_GATE_SPAN_SECONDS==900
    assert m.EVIDENCE_OPERATIONS==('GO_WRITE_HOSTOPS02_K4_E0_01','GO_READONLY_HOSTOPS02_EPOCH_READBACK_01','GO_READONLY_HOSTOPS02_K9_PHASE_READ_01') and m.EVIDENCE_REQUIRED is True
    assert m.SOURCE_PATHS==('/mnt/day-d-data/.r2d2-v2-risk-secrets','/mnt/day-d-data/.r2d2-v2-risk-secrets/risk-database-url','/mnt/day-d-data/.c3po-role-executor-20260908-r2',
                            '/mnt/day-d-data/.c3po-role-executor-20260908-r2/secret','/mnt/day-d-data/.c3po-role-executor-20260908-r2/secret/password')
    assert m.SOURCE_ROW_KEYS==('path','device','inode','uid','gid','mode','mtime_ns','ctime_ns')
    assert (m.COMPLETE_OUTCOME,m.PARTIAL_OUTCOME,m.REFUSED_OUTCOME,m.REDUCED_OUTCOME,m.ESCAPED_OUTCOME)==('K9_SECRETS_PLACED_METADATA_VERIFIED',
        'PARTIAL_SEE_SECRET_FILE_STATES','REFUSED_NOTHING_CHANGED','RECEIPT_REDUCED_STATE_REQUIRES_READBACK','PARTIAL_STATE_UNKNOWN_SECRET_FILES_MAY_EXIST')
    assert set(m.PLAN_KEYS)=={'secrets_chain','data_volume_chain','source_rows','worker_container_id','evidence_boot_id_sha256'}
    assert (m.PROVIDER_TOKEN_GRAMMAR,m.RISK_URL_GRAMMAR,m.EMITTER_PASSWORD_GRAMMAR)==(rb'[A-Za-z0-9._~+/=-]{16,512}',rb'postgresql://[\x21-\x7e]{1,4082}',rb'[A-Za-z0-9_-]{64}')
    assert (m.RISK_URL_MAX_FILE_BYTES,m.EMITTER_PASSWORD_MAX_FILE_BYTES,m.WRITE_ALLOWANCE_SECONDS,m.RISK_URL_READER_PREFIX)==(4096,64,15,b'postgresql://c3po_v2_risk_reader:')
    assert (m.RISK_URL_DIRECTORY,m.RISK_URL_NAME,m.EMITTER_SOURCE_DIRECTORY,m.EMITTER_SOURCE_NAME)==('/mnt/day-d-data/.r2d2-v2-risk-secrets','risk-database-url',
        '/mnt/day-d-data/.c3po-role-executor-20260908-r2/secret','password')
    assert m.SECRET_CREATE_FLAGS==m.os.O_WRONLY|m.os.O_CREAT|m.os.O_EXCL|m.os.O_NOFOLLOW|m.os.O_CLOEXEC and m.READBACK_FLAGS==m.os.O_RDONLY|m.os.O_NOFOLLOW|m.os.O_NONBLOCK
    assert (m.K9_SECRET_FILE_MODE,m.K9_SECRETS_DIRECTORY_MODE,m.WORKER_CONTAINER_NAME,m.SOURCE_OPEN_ROOT)==(0o600,0o700,'c3po-r2d2-worker-1','/mnt/day-d-data')
    spec=f.assembler().load_spec(k3.DIRECTORY);assert spec.PARTS==['core','runner','docker','parents','files'] and spec.SUCCESS_IN_TEMPLATE is True
    assert m.BINARIES=={'docker':['/usr/bin/docker','/usr/local/bin/docker']} and sorted(m.COMMANDS)==['container_list']
    assert all(row['kind']=='READ' and row['class']=='QUICK' for row in m.COMMANDS.values())

def test_static_scope_says_what_the_signers_must_see():
    m=k3.K().m;scope=json.loads(m.canonical(m.SCOPE))
    assert scope['placement']=={'k9_root':'/var/lib/c3po/r2d2-v2-k9-20261005',
                                'status':'decision N-8 of the co-auditor (codex-n8-placement-20261004.txt, sha256 d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53)',
                                'k9_chain':'signed rows from "/", every row root-owned and not writable by group or other, no open root; the K9 root and secrets root:root 0700',
                                'source_open_root':'/mnt/day-d-data (the two walks of the files of September only)',
                                'secrets_directory':'/var/lib/c3po/r2d2-v2-k9-20261005/secrets','emitter_directory':'/var/lib/c3po/r2d2-v2-k9-20261005/secrets/emitter',
                                'files':['/var/lib/c3po/r2d2-v2-k9-20261005/secrets/provider.env','/var/lib/c3po/r2d2-v2-k9-20261005/secrets/risk-db.env',
                                         '/var/lib/c3po/r2d2-v2-k9-20261005/secrets/emitter/password']}
    assert scope['receipt_never']==['a value','a digest of a value, of a line or of a file','a length of a value or of a line','the size of a file','any byte of a source file']
    assert len(scope['exceptions_to_the_core'])==2 and scope['exceptions_to_the_core'][0].startswith('rule 4 ') and scope['exceptions_to_the_core'][1].startswith('rule 5 and 6')
    assert scope['receipt_codes']==sorted(m.RECEIPT_CODES) and scope['receipt_code_otherwise']=='UNLISTED_CODE'
    for word in ('docker exec','docker run','compose','systemctl','a read of the deploy tree or of its .env','overwrite','a second attempt','activation'):assert word in scope['never']
    assert set(scope['commands'])=={'container_list'}
    for sentence in ('makes its own process non-dumpable (prctl PR_SET_DUMPABLE 0, read back 0 with PR_GET_DUMPABLE); otherwise it refuses with nothing changed',
                     'each from its prefixed or its unprefixed name (every one present byte-equal',
                     'config.v2.json read twice inside protected Python','the content is never read back',
                     'while its name still shows the inode this run holds','On 2026-10-05 to 2026-10-10 UTC',
                     'never carries a value, a digest, a length or a size of a value, of a line or of a file'):assert sentence in m.SCOPE_STATEMENT,sentence
    assert m.SCOPE_STATEMENT.startswith('First of all, before anything of the host is looked at') and len(m.SCOPE_STATEMENT)<=4000
    assert scope['process']['dumpable']==0 and scope['process']['otherwise']=='refused, nothing changed: PROCESS_DUMPABLE_NOT_DISABLED'
    assert 'no worker inspect' in scope['process']['commands']

def test_static_the_list_of_receipt_codes_is_every_code_the_source_writes_and_nothing_else():
    """Both ways, by text: every code-shaped literal of the operation part that is a code is listed; every listed code
    occurs as a literal in the built source, or is one of the composed codes of the two files of September (a prefix of
    SOURCE_PREFIXES and a suffix that is a literal of CHAIN_CODES or of the operation part)."""
    m=k3.K().m;own=(k3.DIRECTORY/'op.py').read_text();built=(k3.DIRECTORY/'build'/'k3k9_secrets.py').read_text()
    words=set(re.findall(r"'([A-Z][A-Z0-9_]{2,79})'",own))
    not_codes={m.OPERATION,m.PHASE,m.REQUEST_SCHEMA,m.AUTHORITY_SCHEMA,m.GO_SCHEMA,m.RECEIPT_SCHEMA,m.PLAN_SCHEMA,m.DATE_CLASS,m.K4_E0_OPERATION,
               m.EPOCH_READBACK_OPERATION,m.K9_TREE_OPERATION,m.COMPLETE_OUTCOME,m.PARTIAL_OUTCOME,m.REFUSED_OUTCOME,m.REDUCED_OUTCOME,m.ESCAPED_OUTCOME,m.UNLISTED_CODE,m.RISK_URL_KEY,
               'SECRETS_ROWS_REDUCED_TO_COUNT','PRECHECK','EFFECTS','COMPLETE','ABSENT','EMITTER','PROPOSED','RISK_URL','EMITTER_PASSWORD',
               'SYMLINK_COMPONENT','COMPONENT_NOT_DIRECTORY','PATH_CHANGED','CHAIN_ROW_UNSAFE','CHAIN_ROW_WORLD_WRITABLE','FILE_NOT_REGULAR','FILE_TOO_LARGE',
               'FILE_CHANGED_DURING_READ','SECRET_ENVIRONMENT_VALUE','CREATED_DURABLE','QUICK','READ',
               # the plan's refusals: codes of the core's receipt of a refused authentication, never of perform()
               'K9_ROOT_NOT_ROOT_0700','SECRETS_DIRECTORY_NOT_ROOT_0700','WORKER_CONTAINER_UNBOUND','EVIDENCE_BOOT_UNBOUND','CHAIN_ROW_NOT_ROOT_GROUP',
               'DATA_VOLUME_NOT_A_MOUNT_POINT','SOURCE_ROWS_INVALID','SOURCE_ROWS_OFF_THE_DATA_VOLUME','SOURCE_ROWS_WRITABLE_BY_GROUP_OR_OTHER','SOURCE_ROWS_OWNER_UNEXPECTED'}|set(m.SECRET_FILE_STATES)|set(m.SOURCE_SUFFIXES)
    names=set(m.SECRET_ENVIRONMENT_NAMES)
    codes=words-not_codes-names
    assert codes<=m.RECEIPT_CODES,sorted(codes-m.RECEIPT_CODES)
    composed={prefix+'_'+suffix for prefix in m.SOURCE_PREFIXES for suffix in m.SOURCE_SUFFIXES}
    assert set(m.READ_CODES.values())|{'COMPONENT_ABSENT','COMPONENT_DIVERGES','FILE_ABSENT','FILE_NOT_REGULAR','FILE_LINKED','FILE_DIVERGES'}==set(m.SOURCE_SUFFIXES)
    missing=[code for code in m.RECEIPT_CODES-composed if "'%s'"%code not in built];assert missing==[],missing
    assert set(m.FILESYSTEM_CODES.values())|{'FILESYSTEM_ERROR'}<=m.RECEIPT_CODES and 'SECRET_ENVIRONMENT_VALUE' not in m.RECEIPT_CODES

def test_static_the_operation_part_never_names_a_size_a_digest_or_an_encoding_of_what_it_reads():
    """No st_size, no hashing or encoding module, sha() only for the scope hash, no print, no logging, no repr of a value."""
    own=(k3.DIRECTORY/'op.py').read_text();tree=ast.parse(own)
    attributes={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    names=[node.id for node in ast.walk(tree) if isinstance(node,ast.Name)]
    assert 'st_size' not in attributes and 'st_blocks' not in attributes and not {'hashlib','base64','binascii','zlib','logging','repr','format','hex'}&set(names)
    # sha() twice: the scope, and the effects' hash of the signed identity rows of the sources (metadata, no content)
    assert names.count('sha')==2 and 'SCOPE_SHA256=sha(canonical(SCOPE))' in own and "'source_rows_sha256':sha(canonical(plan['source_rows']))" in own and 'import' not in own
    assert not {'hex','hexdigest','digest','b64encode'}&attributes
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='decode']
    assert calls and all(isinstance(call.func.value,ast.Name) and (call.func.value.id.endswith('_GRAMMAR') or call.func.value.id=='RISK_URL_READER_PREFIX')
                         for call in calls),'decode only of constants'
    assert own.count("'/var/lib/c3po/r2d2-v2-k9-20261005'")==1

def test_static_the_operation_part_reaches_nothing_by_reflection():
    own=ast.parse((k3.DIRECTORY/'op.py').read_text())
    assert not [node for node in ast.walk(own) if isinstance(node,ast.Attribute) and node.attr.startswith('__')]
    assert not {node.id for node in ast.walk(own) if isinstance(node,ast.Name)}&{'getattr','setattr','globals','locals','vars','eval','exec','compile','__import__','open','print'}
