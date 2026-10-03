"""Byte and text pins of the token placement against the release it is frozen for (dd4ec4bb): the README's token
procedure, what the supervisor accepts (private_bytes and the read of the token), the two names the backend accepts and
how, where compose finds the environment file; and the identity of the source. Every test here is named "static": a
mutation run deselects them, so that no mutant dies merely because a pinned text changed. The comparisons with the files
of the release run when a tree of it is at hand (tok.release_tree) and are skipped otherwise; the literal pins always run."""
import json

import pytest

import family as f
import tok

def release():
    tree=tok.release_tree()
    if tree is None:pytest.skip('no tree of the release at hand (HOSTOPS02_TEST_RELEASE_TREE)')
    return tree
def lines(relative):return (release()/relative).read_text().splitlines()

def test_static_the_readme_token_procedure_is_what_the_source_carries_out():
    readme=lines('c3po/deployment/massive-supervisor/README.md')
    assert readme[158]=='## Token procedure'
    assert readme[161]=='- The file is created by **exclusive creation**, mode **0600**, owned by **uid 0**, under `umask 077`. It is a regular file with a single link, 1 to 4096 bytes, holding one line.'
    assert readme[163].startswith('- **Readback is metadata only:** uid, gid, mode, link count and whether the size is within 1–4096. Never the content, never a digest of the content, never the size itself')
    assert readme[174]=='  Every row is exit 78 after one claim. A single trailing newline is accepted (the value is stripped).'
    assert readme[206]=='- The host `.env` holds a `MASSIVE_API_TOKEN` for other purposes. This unit does **not** use it, and it must not be copied here through the environment. The unit passes no environment to the container.'
    assert '`private_bytes` lines 38–55 and the token read at lines 114–115' in readme[164]

def test_static_what_the_supervisor_accepts_is_what_the_source_writes_and_reads_back():
    m=tok.K().m;code=lines('c3po/backend/app/r2d2_v2_massive_supervisor.py')
    assert code[37]=='def private_bytes(path, maximum):'
    assert code[41]=='        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)'
    assert code[44:47]==['            _require(stat.S_ISREG(info.st_mode) and info.st_nlink==1',
                         '                     and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o600',
                         "                     and 0<info.st_size<=maximum,'SUPERVISOR_PRIVATE_FILE')"]
    assert code[113:115]==["            token=private_bytes(token_file,4096).decode('utf-8').strip()",
                           "            _require(bool(token) and '\\n' not in token and '\\r' not in token,'SUPERVISOR_TOKEN')"]
    assert (m.TOKEN_MAX_FILE_BYTES,m.TOKEN_FILE_MODE,m.TOKEN_PATH)==(4096,0o600,'/etc/c3po-bar/token')
    sources=lines('c3po/backend/app/r2d2_v2_sources.py')
    assert sources[157]=='    _require(stat.S_IMODE(info.st_mode) & 0o077 == 0, "SOURCE_DIRECTORY_NOT_PRIVATE")' and m.CONFIG_DIRECTORY_MODE&0o077==0

def test_static_the_two_names_of_the_backend_and_where_compose_reads_the_file():
    m=tok.K().m;config=lines('c3po/backend/app/config.py')
    assert config[19]=='    model_config = SettingsConfigDict(env_prefix="C3PO_", extra="ignore", populate_by_name=True)'
    assert config[115:118]==['    massive_api_token: str = Field(','        default="",','        validation_alias=AliasChoices("C3PO_MASSIVE_API_TOKEN", "MASSIVE_API_TOKEN"),']
    assert m.TOKEN_KEYS==('C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN')
    compose=lines('c3po/compose.yml')
    assert compose[30:32]==['    env_file:','      - ../.env'] and m.ENV_FILE_NAME=='.env'
    assert (release()/'c3po/.env.example').read_text().splitlines()[39]=='MASSIVE_API_TOKEN='

def test_static_identity_dates_evidence_and_parts():
    m=tok.K().m
    assert (m.OPERATION,m.PHASE,m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED,m.DATE_CLASS)==('GO_WRITE_HOSTOPS02_TOKEN_FROM_ENV_01',
        'WRITE_SUPERVISOR_TOKEN_FROM_THE_DEPLOY_ENVIRONMENT_FILE',True,False,'WRITE_WEEKEND')
    assert m.DATES==('2026-10-02','2026-10-03','2026-10-04') and m.TOKEN_DAYS==('2026-10-03','2026-10-04') and m.MAX_GATE_SPAN_SECONDS==900
    assert m.EVIDENCE_OPERATIONS==('GO_READONLY_HOSTOPS_PRECHECK_01','GO_WRITE_SUPERVISOR_READER_PROVISION_01') and m.EVIDENCE_REQUIRED is True
    assert (m.COMPLETE_OUTCOME,m.PARTIAL_OUTCOME,m.REFUSED_OUTCOME,m.REDUCED_OUTCOME,m.ESCAPED_OUTCOME)==('TOKEN_PLACED_METADATA_VERIFIED','PARTIAL_SEE_TOKEN_FILE_STATE',
        'REFUSED_NOTHING_CHANGED','RECEIPT_REDUCED_STATE_REQUIRES_READBACK','PARTIAL_STATE_UNKNOWN_TOKEN_FILE_MAY_EXIST')
    assert set(m.PLAN_KEYS)=={'config_chain','deploy_directory','evidence_boot_id_sha256'}
    assert (m.TOKEN_VALUE_GRAMMAR,m.MAX_ENV_FILE_BYTES,m.WRITE_ALLOWANCE_SECONDS)==('[A-Za-z0-9._~+/=-]{16,512}',65536,15)
    assert m.TOKEN_CREATE_FLAGS==m.os.O_WRONLY|m.os.O_CREAT|m.os.O_EXCL|m.os.O_NOFOLLOW|m.os.O_CLOEXEC
    spec=f.assembler().load_spec(tok.DIRECTORY);assert spec.PARTS==['core','parents','files'] and spec.SUCCESS_IN_TEMPLATE is True

def test_static_scope_says_what_the_signers_must_see():
    m=tok.K().m;scope=json.loads(m.canonical(m.SCOPE))
    assert scope['token_days']==['2026-10-03','2026-10-04'] and scope['paths']['token_file']=='/etc/c3po-bar/token' and scope['processes_started']==0
    assert scope['receipt_never']==['the value','a digest of the value','the length of the value','a line count','any byte of the environment file']
    assert scope['environment_file']['rules']==m.ENV_RULES and len(m.ENV_RULES)==7 and scope['environment_file']['keys']==list(m.TOKEN_KEYS)
    assert 'not writable by group or other' in scope['environment_file']['chain'] and 'closed' not in scope['environment_file']['chain']
    assert scope['environment_file']['file'].startswith('regular, one link, not world-writable')
    assert len(scope['exceptions_to_the_core'])==1 and scope['exceptions_to_the_core'][0].startswith('rule 4 ') and '/etc/c3po-bar/token' in scope['exceptions_to_the_core'][0]
    assert scope['receipt_codes']==sorted(m.RECEIPT_CODES) and scope['receipt_code_otherwise']=='UNLISTED_CODE'
    for word in ('a process','docker','the environment of a process or of a container','overwrite','a second attempt'):assert word in scope['never']
    for sentence in ('one exclusive create of /etc/c3po-bar/token (root:root 0600, one link, the value and one newline)','A file that exists at that name is never touched',
                     'while its name still shows the inode this run holds','On 2026-10-03 or 2026-10-04 UTC only','No process is started, no environment of a process',
                     'never carries the value, a digest of it, its length or a line count'):assert sentence in m.SCOPE_STATEMENT

def test_static_the_list_of_receipt_codes_is_every_code_the_source_writes_and_nothing_else():
    """Both ways, by text: every code-shaped literal of the operation part that is a code (not a schema, status, outcome,
    phase, state or fact name) is listed; every listed code occurs as a literal in the built source (the operation part
    or the core), so the list names nothing the run cannot write."""
    import re
    m=tok.K().m;own=(tok.DIRECTORY/'op.py').read_text();built=(tok.DIRECTORY/'build'/'token_from_env.py').read_text()
    words=set(re.findall(r"'([A-Z][A-Z0-9_]{2,79})'",own))
    not_codes={m.OPERATION,m.PHASE,m.REQUEST_SCHEMA,m.AUTHORITY_SCHEMA,m.GO_SCHEMA,m.RECEIPT_SCHEMA,m.PLAN_SCHEMA,m.DATE_CLASS,m.PROVISION_OPERATION,
               m.COMPLETE_OUTCOME,m.PARTIAL_OUTCOME,m.REFUSED_OUTCOME,m.REDUCED_OUTCOME,m.ESCAPED_OUTCOME,m.UNLISTED_CODE,'C3PO_MASSIVE_API_TOKEN',
               'MASSIVE_API_TOKEN','CONFIG_ROWS_REDUCED_TO_COUNT','PRECHECK','EFFECTS','COMPLETE','ABSENT','SYMLINK_COMPONENT','COMPONENT_NOT_DIRECTORY',
               'PATH_CHANGED','CHAIN_ROW_UNSAFE','CHAIN_ROW_WORLD_WRITABLE','FILE_NOT_REGULAR','FILE_TOO_LARGE','FILE_CHANGED_DURING_READ',
               # the plan's refusals: codes of the core's receipt of a refused authentication, never of perform()
               'CONFIG_DIRECTORY_NOT_ROOT_0700','DEPLOY_DIRECTORY_INVALID','EVIDENCE_BOOT_UNBOUND','WINDOW_NOT_ON_A_TOKEN_DAY'}|set(m.TOKEN_STATES)
    codes=words-not_codes
    assert codes<=m.RECEIPT_CODES,sorted(codes-m.RECEIPT_CODES)
    assert all("'%s'"%code in built for code in m.RECEIPT_CODES),sorted(code for code in m.RECEIPT_CODES if "'%s'"%code not in built)
    assert set(m.DEPLOY_CODES.values())|set(m.ENV_CODES.values())|set(m.FILESYSTEM_CODES.values())|{'FILESYSTEM_ERROR'}<=m.RECEIPT_CODES
