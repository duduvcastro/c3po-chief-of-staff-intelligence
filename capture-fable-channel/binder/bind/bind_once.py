#!/usr/bin/env python3
"""bind_once.py - one generic binder for the signed single-use "once" families. Local files only.

Capture-only candidate: REAL is restricted to the three PRIMARY/PRE captures of 08/10/2026.
An immutable per-sheet context and exact direct-owner GitHub API readbacks are required. Serialized snapshots
are not independently authenticated; the live API bridge, transport, runtime and dated authority need separate
review before operational use. The delivered Mac rev8 remains separate and unchanged.

It binds one operation of a sealed family directory (SHA256SUMS at its root) into one output directory and never
dispatches: the operator runs the family's own dispatch_once.py (prepare, then resume) by hand, as RUNBOOK.md says.

  prepare        --family DIR --operation NAME --params FILE --reference FILE --out DIR --mode real|rehearsal
                 Verifies the seal, binds the REQUEST, creates the private claim root and writes the sheet the owner
                 signs over (PREPARE.json) and the question to show him (OWNER_QUESTION.txt, Portuguese, BRT).
  sign           --bound DIR --sheet-sha256 HEX --signed-at UTC --owner-answer TEXT
                 After the owner answered. Writes AUTHORITY, GO, the final payload, DISPATCH.BOUND.json, the claim
                 root identity and SHA256SUMS. --sheet-sha256 is not a free value: it must be the sha256 of PREPARE.json.
                 --owner-answer is the owner's answer, verbatim: anything but the literal signature word is refused.
  check          --bound DIR [--family DIR] [--gates FILE] [--step prepare|resume]
                 Dry validation, writes nothing: the family's own authenticate() and the family's own dispatcher run
                 up to (not including) the creation of the claim, with injected clocks, on the bound bytes and on
                 unsigned and expired variants held in memory. For a HOSTOPS02 set also the dispatch gates its sheet
                 names (--gates: the evidence of each), the minutes to avoid (a minute to avoid is not a dispatch
                 verdict) and, for a spare, that its primary was never sent; --step resume (HOSTOPS02 only) is the
                 verdict before the resume (for K10 with its own gate before the resume).
  publish-proof  --bound DIR --comment-id ID --created-at UTC [--name PUBLICATION.PROOF.R2.json]
  status         --bound DIR [--show-findings]
                 verdict and hashes of a finished attempt; never a value read on the host.
  rehearsal-reference --out DIR     a fake transport reference (reserved .invalid target, marker files) for rehearsals.
  sealed-copy    --out DIR --source DIR [--source DIR ...]
                 HOSTOPS02: the frozen core and every accepted operation directory, only the files their seals list,
                 each taken from the first source root that holds it with its sealed hash.

Two profiles, recognised from the source module itself, never from a name:
  collection  the HOSTFACTS lineage (W1): request.collection, owner_evidence object and scope sentence added to the GO
  core        the HOSTOPS core (HOSTOPS01 and the sources that reuse it): exact key sets, request.plan, effects,
              scope_statement and success_criterion, evidence receipts

For the core profile the binder also applies, before the owner is asked, what section 12 of that family's contract
leaves to the binder: every cited receipt has its seal recomputed and its hash computed (never typed), plan values are
copied from receipts by pointer, units are rendered again by the reference loop, and the floor of a GATE readback is
compared with the figure of the precheck receipt. A cited receipt must be a receipt of the operation it is cited for, in
the schema of that operation's source in the same sealed family, bound to the host of the set being bound and complete
(or accepted as not complete by a parameter the sheet shows). A REAL request cites bound sets, never loose files: the
receipt is then the stored output of a finished attempt of a signed REAL set, verified as `status` verifies it. And the
plan members that section 11 of the contract derives from a receipt (PLAN_SOURCES) must equal that receipt's values,
whether they were typed or copied by pointer.

A set is REAL or REHEARSAL from its first byte. REAL takes its transport fields from an executed bound configuration
(read, never printed; the key and known-hosts files are never opened, only lstat-ed). REHEARSAL takes them from a
fake reference whose target is in the reserved .invalid domain; the two cannot be mixed in either direction.

Revision 4 (2026-10-04): the two K9 host programs of the delegated daily phases, K9R (GO_READONLY_HOSTOPS02_K9_PHASE_READ_01)
and K9W (GO_WRITE_HOSTOPS02_K9_PHASE_STEP_01), K9_INTERFACE_NOTE.md rev 2 section 10.4: section "K9" below (k9_rules), the
pinned grid file K9_GRID9.json beside this file, and one K9W PLUG block. The other operations are bound as in revision 3.

HOSTOPS02 (K2a catalog_init, K10 install_release, K11 epoch_readback, K6a activate): one sealed directory per operation,
assembled from a frozen core that lies beside it as ../core. Its accepted seal names that core; prepare verifies the core's
list and generation, runs the core's own `assemble.py --check` on the operation directory, and applies what each
operation's CONTRACT.txt leaves to the binder (the section "HOSTOPS02" below): evidence of other accepted families (each
item names its family directory), bind-time input files ({"$input": NAME, "as": FORM} in the plan), the K10 tools, a
spare that shadows a primary, and dispatch gates that `check --gates` evaluates minutes before the dispatch. Every
HOSTOPS02 request names the review of its bytes (the co-auditor's document, which must name the seal and the source
or the unbound final payload of these bytes, or the owner's own waiver record); a write is also gated, at dispatch, on
the co-auditor's written review of the BOUND set (A1, section 8). A HOSTOPS01 readback or install_units request may
cite the K2a set of operation 4b (by its family): the catalog it signs is then copied from that receipt.

One owner answer per sheet (signature models IND, EVE and PRE). The read grid (GRID) and the weekly model (WEEK) are not
implemented: a request declared as one of them is refused at prepare.

No secret and no host value is contained in or printed by this file. Exit codes: 0 done, 2 REFUSED (one JSON object,
printed on several lines, with a constant code; never a traceback); check exits 1 when the set is valid but this GO
cannot be used for a new dispatcher prepare (past the latest start, already prepared, or spent); status exits 1 when
there is no verified receipt.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import types

SHEET_SCHEMA = 'BIND_ONCE_PREPARE_SHEET_V1'
PARAMETERS_SCHEMA = 'BIND_ONCE_PARAMETERS_V1'
SEALS_SCHEMA = 'BIND_ONCE_ACCEPTED_SEALS_V1'
REHEARSAL_REFERENCE_SCHEMA = 'BIND_ONCE_REHEARSAL_TRANSPORT_REFERENCE_V1'
REAL, REHEARSAL = 'REAL', 'REHEARSAL'
REAL_OWNER = 'DUDU'
REAL_CHANNEL = 'REGISTRO_PELA_FABLE AskUserQuestion capture/policy candidate'
REAL_ANSWER = 'Assino'
SIGNATURE_MODELS = {'IND': 'individual (IND): esta resposta vale para este pedido e para nenhum outro',
                    'EVE': 'de véspera (EVE): esta resposta vale para este pedido e para nenhum outro, e é dada antes da janela',
                    'PRE': 'antecipada (PRE): esta resposta vale para este pedido e para nenhum outro, e é dada antes da janela'}
SIGNATURE_MODELS_NOT_IMPLEMENTED = ('GRID', 'WEEK')
REVIEW_KINDS = ('CODEX_REVIEWED', 'OWNER_WAIVED')
REHEARSAL_OWNER = 'REHEARSAL_NOT_THE_OWNER'
REHEARSAL_CHANNEL = 'REHEARSAL_NO_OWNER_WAS_ASKED'
REHEARSAL_ANSWER = 'REHEARSAL_NO_OWNER_ANSWER'
REHEARSAL_TARGET = 'rehearsal@bind-once-rehearsal.invalid'
REHEARSAL_KEY = b'NOT_A_KEY_BIND_ONCE_REHEARSAL\n'
REHEARSAL_HOSTS = b'NOT_KNOWN_HOSTS_BIND_ONCE_REHEARSAL\n'
REHEARSAL_PREFIX = 'rehearsal-'
REHEARSAL_PUBLICATION = 'REHEARSAL-NO-PUBLICATION'
RESERVED_DOMAINS = ('invalid', 'test', 'example', 'localhost')
REMOTE_COMMAND = 'sudo -n /usr/bin/python3 -I -B -'
COMMON_RUNTIME = ('dispatch_once.py', 'launcher_stdin.py', 'transport_once.py')
TEMPLATE_NAMES = ('REQUEST.UNBOUND.json', 'AUTHORITY.UNBOUND.json', 'GO.UNBOUND.json', 'DISPATCH.UNBOUND.json',
                  'PUBLICATION_PROOF.UNBOUND.json')
UNBOUND_PAYLOAD = 'FINAL_PAYLOAD.UNBOUND.py'
BLOBS = ('source', 'request', 'authority', 'go', 'payload')
CACHE_DIRECTORIES = ('__pycache__', '.pytest_cache')          # tolerated in a family directory (never imported from there), refused in a bound set
CLAIM_ROOT = '.dispatch-root'
BOUND_DIRECTORIES = (CLAIM_ROOT, 'templates')
PYCACHE_PLACEHOLDER = '<fresh-empty-0700-directory>'          # RUNBOOK blocks 6 and 9 create it with mktemp -d
HEX64 = '[0-9a-f]{64}'
CODE = '[A-Z][A-Z0-9_]{0,79}'
LABEL = '[a-z0-9][a-z0-9-]{0,39}'
TARGET = '[a-z_][a-z0-9_-]*@[A-Za-z0-9.-]+'
PROOF_NAME = r'PUBLICATION\.PROOF(\.R[2-9])?\.json'
COMMENT_ID = '[0-9]{6,20}'
UTC_SECOND = re.compile(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(Z|\+00:00)')
EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()
RECEIPT_STATUS = {'KNOWN_COMPLETE': 'METADATA_ONLY_REQUIRES_REVIEW', 'KNOWN_PARTIAL': 'PARTIAL_METADATA_REQUIRES_REVIEW'}
WEEKDAYS_PT = ('seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom')
CORE_ATTRIBUTES = ('authenticate', 'effects_of', 'success_of', 'perform', 'run', 'digests', 'Effects', 'Pins', 'SCOPE', 'SCOPE_SHA256',
                   'SCOPE_STATEMENT', 'PLAN_KEYS', 'PLAN_SCHEMA', 'REQUEST_KEYS', 'AUTHORITY_KEYS', 'GO_KEYS', 'DATES',
                   'MAX_GATE_SPAN_SECONDS', 'WRITES_ALLOWED', 'SOURCE_NAME', 'OPERATION', 'PHASE', 'RECEIPT_SCHEMA')
COLLECTION_ATTRIBUTES = ('authenticate', 'observe', 'collect', 'validate_collection', 'Pins', 'SCOPE', 'SCOPE_SHA256', 'SIDE_EFFECTS',
                         'DATES', 'COLLECTION_SCHEMA', 'OPERATION', 'PHASE', 'RECEIPT_SCHEMA')

# What the contract of a collection-profile family requires of the scope sentence of its GO. One entry per operation;
# an operation of that profile without an entry is refused, because the sentence is signed text and is not guessed.
COLLECTION_SCOPE_RULES = {
    'GO_READONLY_W1PREFLIGHT_01': {
        'title': 'read-only combined preflight',
        'decisions_header': "DECISIONS THAT NEED THE REVIEWER'S AND THE OWNER'S EXPLICIT ACCEPTANCE",
        'decisions': (1, 2, 3, 4, 5, 6, 11, 12, 13),
        'minimum_side_effects': 9,
        # The sealed dispatcher and source put no upper limit on the window (a whole UTC day passes them). The plan's limit
        # for a read gate is enforced here, at prepare and whenever the set is opened again.
        'max_window_seconds': 3600,
    },
}

# Section 12, step 2b, of the HOSTOPS01 contract: the floor of a GATE readback is compared, before the signature is asked
# for, with the figure the precheck receipt read on the chain that the provision receipt names. Names of that family.
PRECHECK_OPERATION = 'GO_READONLY_HOSTOPS_PRECHECK_01'
PROVISION_OPERATION = 'GO_WRITE_SUPERVISOR_READER_PROVISION_01'
INSTALL_OPERATION = 'GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01'
READBACK_OPERATION = 'GO_READONLY_SUPERVISOR_READBACK_01'
FLOOR_RULE = {'provision_operation': PROVISION_OPERATION, 'precheck_operation': PRECHECK_OPERATION}

# Section 11 of the HOSTOPS01 contract ("where each bound value comes from"), as a table. Each row: a member of the plan,
# the operation of the receipt it comes from, and the member of that receipt it must equal. "*" stands for each key of the
# plan member before it. A member that is null (or whose parent is null) is left to the family's own rules; a member
# that is not null needs exactly ONE cited receipt of that operation and must equal its value, typed or copied.
BOOT_POINTER = '/items/boot/boot_id_sha256'
PLAN_SOURCES = {
    PROVISION_OPERATION: (('/chains/*', PRECHECK_OPERATION, '/items/chains/*/rows'),
                          ('/evidence_boot_id_sha256', PRECHECK_OPERATION, BOOT_POINTER),
                          ('/retention_tag/image_id', PRECHECK_OPERATION, '/items/image/id')),
    INSTALL_OPERATION: (('/unit_directory', PRECHECK_OPERATION, '/items/chains/UNIT_DIRECTORY/rows'),
                        ('/evidence_boot_id_sha256', PRECHECK_OPERATION, BOOT_POINTER)),
    READBACK_OPERATION: (('/provision/receipt_sha256', PROVISION_OPERATION, '/metadata_sha256'),
                         ('/install/receipt_sha256', INSTALL_OPERATION, '/metadata_sha256'),
                         ('/install/outcome', INSTALL_OPERATION, '/outcome'),
                         ('/evidence_boot_id_sha256', PRECHECK_OPERATION, BOOT_POINTER),
                         ('/unit_directory', PRECHECK_OPERATION, '/items/chains/UNIT_DIRECTORY/rows')),
    # HOSTOPS02 (section 4 of K2a, section 5 of K10, section 8 of K6a). K11's sources are alternatives: see readback_rules.
    'GO_WRITE_HOSTOPS02_CATALOG_INIT_01': (('/evidence_boot_id_sha256', PRECHECK_OPERATION, BOOT_POINTER),
                                           ('/image_id', PRECHECK_OPERATION, '/items/image/id'),
                                           ('/image_revision', PRECHECK_OPERATION, '/items/image/revision_label')),
    'GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01': (('/parent', PRECHECK_OPERATION, '/items/chains/DATA_VOLUME/rows'),
                                              ('/evidence_boot_id_sha256', PRECHECK_OPERATION, BOOT_POINTER)),
    'GO_WRITE_HOSTOPS02_ACTIVATE_01': tuple((plan, 'GO_READONLY_HOSTOPS02_EPOCH_READBACK_01', receipt) for plan, receipt in (
        ('/live_parent', '/items/directory:LIVE_PARENT/observed_rows'), ('/release/parent', '/items/directory:RELEASE_PARENT/observed_rows'),
        ('/deploy_directory', '/items/directory:DEPLOY_TREE/observed_rows'), ('/lock/directory', '/items/directory:LOCK_DIRECTORY/observed_rows'),
        ('/evidence_boot_id_sha256', '/effects/evidence_boot_id_sha256'), ('/worker/image_id', '/effects/image/image_id'),
        ('/data_root', '/effects/worker/data_source'), ('/worker/mount_target', '/effects/worker/data_target'),
        ('/compose/project', '/effects/render/project'), ('/compose/env_file', '/effects/render/env_file'), ('/compose/files', '/effects/render/files'),
        ('/policy/sha256', '/effects/policy/sha256'), ('/policy/bytes', '/effects/policy/bytes'),
        ('/release/sha256', '/effects/release/sha256'), ('/release/bytes', '/effects/release/bytes'))),
}

# What the owner reads, in Portuguese. An operation without an entry must bring owner_summary_pt in its parameters.
OWNER_TEXT_PT = {
    'GO_READONLY_W1PREFLIGHT_01': (
        'consulta W1 (verificação combinada, só de leitura)',
        'O programa lê apenas estado e configuração do servidor de produção: se há reinício pendente e o que o segura, a trava '
        'de manutenção da época, os discos (números de dispositivo e espaço livre), os contêineres e serviços do C3PO em '
        'execução e as suas versões, as redes, os diretórios previstos para o supervisor e para o leitor (dono, permissões e '
        'contagens, sem nomes de arquivos) e os metadados do arquivo do token, sem abrir o conteúdo dele.\n'
        'Ele abre o conteúdo de nove arquivos de sistema e do controlador de segurança, nenhum com segredo, e não emite o '
        'texto de nenhum deles. Não lê senhas, chaves nem valores de variáveis dos serviços, e não grava, não altera, não '
        'instala e não reinicia nada; se uma consulta travar, ele só encerra essa consulta, que ele mesmo abriu.\n'
        'Ao assinar você aceita também as decisões 1 a 6 e 11 a 13 do contrato e os efeitos colaterais declarados das '
        'ferramentas: estão citados por extenso no texto formal do escopo (arquivo GO_SCOPE.txt), que é o que entra no '
        'documento assinado.'),
    'GO_READONLY_HOSTOPS_PRECHECK_01': (
        'pré-checagem do servidor (só de leitura)',
        'O programa lê e não muda nada: uma linha (dispositivo, inode, dono, grupo e permissões) de cada diretório-pai que as '
        'operações de gravação vão fixar, a presença e os metadados de cada destino planejado, os diretórios de unidades do '
        'sistema, o identificador de boot (só o hash dele) e o ID e as etiquetas da imagem c3po/backend:production.\n'
        'Dos nomes que guardam segredo ele só vê tipo, dono, permissões e número de links: nunca abre, nunca mede. As linhas '
        'que ele lê são as que os pedidos de gravação vão assinar; esta consulta não autoriza gravação nenhuma.'),
    'GO_WRITE_SUPERVISOR_READER_PROVISION_01': (
        'criação de diretórios e de uma etiqueta de imagem (GRAVAÇÃO)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR. Ela cria somente os diretórios listados nos efeitos (arquivo EFFECTS.json), cada um '
        'root:root com modo 0700, e no máximo uma etiqueta de retenção sobre o ID de imagem assinado.\n'
        'Nunca cria arquivo, nunca muda dono ou permissão, nunca renomeia nem remove, nunca toca no token, em manifesto, em '
        'unidade ou no secret.env. O que já existe não é tocado: ou a operação recusa, ou confere o que o pedido assinou '
        'como presente. Depois de qualquer resultado que não seja o critério de sucesso, o estado do servidor é '
        'estabelecido por uma consulta só de leitura, com assinatura própria.'),
    'GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01': (
        'instalação dos arquivos de unidade, sem ativação (GRAVAÇÃO)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR. Ela cria somente os arquivos de unidade listados nos efeitos (arquivo EFFECTS.json) '
        'em /etc/systemd/system, root:root com modo 0644, sem substituir nada que já exista.\n'
        'Nenhum processo é iniciado: nenhum comando do systemctl, nenhuma recarga do gerenciador, nenhuma ativação. A recarga '
        'fica com o responsável nomeado nos efeitos, sob a assinatura dele. Depois de qualquer resultado que não seja o '
        'critério de sucesso, o estado do servidor é estabelecido por uma consulta só de leitura, com assinatura própria.'),
    'GO_READONLY_SUPERVISOR_READBACK_01': (
        'releitura do supervisor (só de leitura)',
        'O programa lê e não muda nada: os dois arquivos de unidade instalados, os seis valores como estão no serviço '
        'instalado, dono, grupo e permissões de cada caminho do layout, o sistema de arquivos da raiz do diário, o token por '
        'um único lstat (nunca aberto, nunca medido), os nomes e metadados dos arquivos do catálogo, o espaço livre contra o '
        'piso assinado e os comandos fixos de systemctl e docker do escopo.\n'
        'Só o resultado nomeado como critério de sucesso satisfaz a metade "releitura" do portão de ativação. Esta consulta '
        'não autoriza instalação nem ativação.'),
}


class Refused(Exception):
    """A constant code; str(error) never carries a path, a target or a value read from a file."""


class DryStop(BaseException):
    """Raised inside the family's dispatcher at its first creating call, so that a dry run ends there."""


WROTE = []                                    # names created by this run, in order


def need(ok, code):
    if not ok:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def is_hash(value):
    return type(value) is str and re.fullmatch(HEX64, value) is not None and value != '0' * 64


def strict_json(raw, code):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, code)
            result[key] = value
        return result

    def constant(_):
        raise Refused(code)
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except Refused:
        raise
    except (ValueError, RecursionError):
        raise Refused(code)


def utc_now():
    return datetime.now(timezone.utc)


def parse_utc(text, code='TIME_NOT_UTC_SECONDS'):
    """Whole seconds, explicit UTC (Z or +00:00); anything else is refused."""
    match = UTC_SECOND.fullmatch(text) if type(text) is str else None
    need(match, code)
    try:
        return datetime.fromisoformat(match.group(1) + 'T' + match.group(2) + '+00:00')
    except ValueError:
        raise Refused(code)


def zulu(moment):
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def brt(moment):
    """Brasília time, UTC-3 all year (no daylight saving since 2019)."""
    local = moment - timedelta(hours=3)
    return '%s %s BRT' % (WEEKDAYS_PT[local.weekday()], local.strftime('%d/%m/%Y %H:%M:%S'))


def utc_instant(text):
    """An instant written by datetime.isoformat() in UTC (offset +00:00 required); ValueError otherwise."""
    moment = datetime.fromisoformat(text) if type(text) is str else None
    if moment is None or moment.utcoffset() != timedelta(0):
        raise ValueError('not a UTC instant')
    return moment


def window_of_sheet(window, watchdog):
    """The window member of the sheet, every field derived from the four UTC instants and the watchdog of the family."""
    latest = window['gate_end'] - timedelta(seconds=watchdog)
    return {'date_utc': window['start'].date().isoformat(), 'not_before': zulu(window['start']), 'not_after': zulu(window['end']),
            'gate_not_before': zulu(window['gate_start']), 'gate_not_after': zulu(window['gate_end']),
            'gate_span_seconds': int((window['gate_end'] - window['gate_start']).total_seconds()),
            'latest_start': zulu(latest), 'watchdog_seconds': watchdog,
            'brt': {'not_before': brt(window['start']), 'not_after': brt(window['end']), 'gate_not_before': brt(window['gate_start']),
                    'gate_not_after': brt(window['gate_end']), 'latest_start': brt(latest)}}


def free_text(value):
    """Operator text that enters the question shown to the owner: one line of printable characters that cannot be taken
    for a line of the binder (no signature word, no 64-hex string)."""
    return (type(value) is str and 20 <= len(value) <= 1500 and value.isprintable() and value == value.strip()
            and REAL_ANSWER.lower() not in value.lower() and re.search('[0-9A-Fa-f]{64}', value) is None)


def read_file(path, limit, code, private=False, allow_empty=False):
    """A regular file, never through a link in its last component. private: this user, 0600, one link."""
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise Refused(code)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_size <= limit and (allow_empty or info.st_size > 0), code)
        if private:
            need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1, code)
        chunks = []
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            chunks.append(block)
        raw = b''.join(chunks)
        need(len(raw) == info.st_size, code)
        return raw
    finally:
        os.close(fd)


def put(directory, name, raw):
    """Exclusive creation only (O_EXCL, O_NOFOLLOW, 0600), fsynced and read back. Nothing is ever overwritten."""
    need(type(raw) is bytes and len(raw) > 0, 'EMPTY_WRITE')
    path = Path(directory) / name
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise Refused('ALREADY_EXISTS_NEVER_OVERWRITTEN')
    WROTE.append(str(path))
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(raw)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    need(read_file(path, len(raw), 'WRITTEN_FILE_READ_BACK', private=True) == raw, 'WRITTEN_FILE_READ_BACK')
    return sha(raw)


def make_directory(path):
    try:
        os.mkdir(str(path), 0o700)
    except FileExistsError:
        raise Refused('ALREADY_EXISTS_NEVER_OVERWRITTEN')
    WROTE.append(str(path))
    os.chmod(str(path), 0o700)


def private_directory(path, code):
    try:
        info = os.lstat(str(path))
    except OSError:
        raise Refused(code)
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, code)
    return info


def clean_absolute(path):
    return (type(path) is str and path.startswith('/') and str(PurePosixPath(path)) == path
            and '..' not in PurePosixPath(path).parts and '\x00' not in path)


def binder_identity():
    here = Path(__file__).resolve()
    seals_raw = read_file(here.with_name('ACCEPTED_SEALS.json'), 65536, 'ACCEPTED_SEALS_MISSING')
    seals = strict_json(seals_raw, 'ACCEPTED_SEALS_INVALID')
    need(type(seals) is dict and seals.get('schema') == SEALS_SCHEMA and type(seals.get('seals')) is list
         and all(type(item) is dict and is_hash(item.get('sha256sums_sha256')) and type(item.get('family')) is str
                 and type(item.get('revision')) is str for item in seals['seals']), 'ACCEPTED_SEALS_INVALID')
    # A seal of the HOSTOPS02 kind (one sealed directory per operation, assembled from a frozen core that lies beside it)
    # names that core: the hash of its CORE_SHA256SUMS and its generation (the hash of its assemble.py).
    need(all('core' not in item or (type(item['core']) is dict and set(item['core']) - {'directory'} == {'sha256sums_sha256', 'generation_sha256'}
                                    and all(is_hash(item['core'][key]) for key in ('sha256sums_sha256', 'generation_sha256'))
                                    and core_directory_of(item) is not None) for item in seals['seals']), 'ACCEPTED_SEALS_INVALID')
    return {'binder_sha256': sha(read_file(here, 4 * 1024 * 1024, 'BINDER_UNREADABLE')), 'accepted_seals_sha256': sha(seals_raw)}, seals['seals']


# ---------------------------------------------------------------- the sealed family and one operation of it
def verify_family(directory, seals=None):
    """Every file of the family must be listed in the SHA256SUMS at its root with the right hash, and nothing else may be there.
    One exception, for the seals of the HOSTOPS02 kind only (an accepted seal that names a core; the accepted seals are read
    when `seals` is not given): the top-level directories work/ and review-*/ are outside the seal by their contracts
    ("their presence does not break it"); they are skipped, never read and never imported from, and their names are reported."""
    directory = Path(directory)
    need(directory.is_dir() and not directory.is_symlink(), 'FAMILY_NOT_FOUND')
    directory = directory.resolve()
    sums_raw = read_file(directory / 'SHA256SUMS', 1024 * 1024, 'FAMILY_NOT_FOUND')
    seals = binder_identity()[1] if seals is None else seals
    outside = any(item['sha256sums_sha256'] == sha(sums_raw) and 'core' in item for item in seals)
    unsealed = set()
    listed = {}
    try:
        lines = sums_raw.decode('ascii').splitlines()
    except UnicodeDecodeError:
        raise Refused('FAMILY_SUMS_INVALID')
    for line in lines:
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_./-]+)', line)
        need(match and match.group(2) not in listed and '..' not in match.group(2).split('/')
             and not match.group(2).startswith('/'), 'FAMILY_SUMS_INVALID')
        listed[match.group(2)] = match.group(1)
    need(listed, 'FAMILY_SUMS_INVALID')
    present = set()
    for path in directory.rglob('*'):
        relative = path.relative_to(directory)
        if set(relative.parts) & set(CACHE_DIRECTORIES):
            continue
        if outside and (relative.parts[0] == 'work' or relative.parts[0].startswith('review-')) and not path.is_symlink() and (
                len(relative.parts) > 1 or path.is_dir()):
            unsealed.add(relative.parts[0])
            continue
        if path.is_symlink() or not path.is_dir():
            present.add(str(relative))
    need(present - {'SHA256SUMS'} == set(listed), 'FAMILY_FILE_SET')
    files = {}
    for name, digest in listed.items():
        files[name] = read_file(directory / name, 8 * 1024 * 1024, 'FAMILY_FILE_SET')
        need(sha(files[name]) == digest, 'FAMILY_HASH')
    family = {'directory': directory, 'files': files, 'sums_sha256': sha(sums_raw)}
    if outside:
        family['unsealed_directories_skipped'] = sorted(unsealed)
    return family


def core_directory_of(seal):
    """rev 4: the directory, beside the operation directory, that holds the core a seal names: "core" unless the seal's
    core names another ("directory", one path component; K6b's core-k6b, K3's core_k3). None if the name is not one."""
    name = seal['core'].get('directory', CORE_DIRECTORY) if type(seal.get('core')) is dict else None
    return name if type(name) is str and re.fullmatch('core[A-Za-z0-9_-]{0,40}', name) else None


def accepted_seal(seals, sums_sha256):
    found = [item for item in seals if item['sha256sums_sha256'] == sums_sha256]
    need(len(found) == 1, 'FAMILY_SEAL_NOT_ACCEPTED')
    seal = {'family': found[0]['family'], 'revision': found[0]['revision'], 'sha256sums_sha256': sums_sha256}
    if 'core' in found[0]:
        seal['core'] = dict(found[0]['core'])
    return seal


def select_operation(family, operation):
    """The directory of the family (its root, or one directory below it) whose dispatch template names the operation."""
    need(type(operation) is str and re.fullmatch('GO_[A-Z0-9_]{1,76}', operation), 'OPERATION_NAME_INVALID')
    files, matches = family['files'], []
    for name in sorted(files):
        prefix, _, leaf = name.rpartition('/')
        if leaf == 'DISPATCH.UNBOUND.json' and prefix.count('/') == 0:
            template = strict_json(files[name], 'TEMPLATE_INVALID')
            if type(template) is dict and template.get('operation') == operation:
                matches.append(prefix)
    need(len(matches) == 1, 'OPERATION_NOT_IN_FAMILY')
    prefix = matches[0] + '/' if matches[0] else ''
    config = strict_json(files[prefix + 'DISPATCH.UNBOUND.json'], 'TEMPLATE_INVALID')
    pins = config.get('runtime_sha256')
    need(type(pins) is dict and set(COMMON_RUNTIME) < set(pins) and len(pins) == 4
         and all(re.fullmatch(r'[a-z0-9_]+\.py', name) for name in pins), 'TEMPLATE_INVALID')
    source_name = (set(pins) - set(COMMON_RUNTIME)).pop()
    names = tuple(pins) + TEMPLATE_NAMES + (UNBOUND_PAYLOAD,)
    need(all(prefix + name in files for name in names), 'FAMILY_FILE_SET')
    contract = files.get('CONTRACT.txt')
    if contract is None:
        # These newly supported families seal the operation and its build, but no CONTRACT.txt.
        # Bind the fixed owner disclosure and outcome to this operation's sealed runtime pins.
        # Old families still require their original contract; no external unsealed prose is used.
        need(operation in SEALED_PROGRAMS, 'FAMILY_FILE_SET')
        contract = canonical({'schema': 'CODEX_FIXED_BINDING_CONTRACT_01', 'operation': operation,
                              'runtime_sha256': pins, 'owner_text_pt': HOSTOPS02_TEXT_PT[operation],
                              'outcome_text_pt': OUTCOME_TEXT_PT[(operation, None)]})
    op = {name: files[prefix + name] for name in names}
    need(all(sha(op[name]) == pins[name] for name in pins), 'TEMPLATE_CHAIN')
    return {'files': op, 'source_name': source_name, 'runtime_names': tuple(sorted(pins)), 'directory': family['directory'] / matches[0],
            'contract_sha256': sha(contract)}


def load_runtime(sources, source_name, directory):
    """The four runtime modules from the hashed bytes, under their own names (the dispatcher imports its siblings by
    name); sys.modules is restored afterwards. __file__ is the path the dispatcher looks beside for its runtime pins."""
    order = (source_name, 'launcher_stdin.py', 'transport_once.py', 'dispatch_once.py')
    saved = {name[:-3]: sys.modules.get(name[:-3]) for name in order}
    loaded = {}
    try:
        for name in order:
            module = types.ModuleType(name[:-3])
            module.__file__ = str(Path(directory) / name)
            sys.modules[name[:-3]] = module
            exec(compile(sources[name], module.__file__, 'exec'), module.__dict__)
            loaded[name] = module
    except Refused:
        raise
    except Exception:
        raise Refused('RUNTIME_DOES_NOT_LOAD')
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return {'source': loaded[source_name], 'launcher': loaded['launcher_stdin.py'], 'transport': loaded['transport_once.py'],
            'dispatch': loaded['dispatch_once.py'], 'source_bytes': sources[source_name], 'source_name': source_name}


def profile_of(module):
    if all(hasattr(module, name) for name in CORE_ATTRIBUTES):
        return 'core'
    if all(hasattr(module, name) for name in COLLECTION_ATTRIBUTES):
        return 'collection'
    raise Refused('FAMILY_PROFILE_UNKNOWN')


def literal(source, suffix, code='DISPATCHER_LITERALS'):
    found = set(re.findall(r"'([A-Z0-9_]+" + suffix + r")'", source))
    need(len(found) == 1, code)
    return found.pop()


def dispatcher_facts(rt, files):
    """Names and the date set as the dispatcher's own text carries them; nothing is assumed from the family name."""
    text = files['dispatch_once.py'].decode('utf-8')
    dates = re.findall(r"start\.date\(\)\.isoformat\(\) in \(([^()]*)\)", text) + re.findall(r"start\.date\(\)\.isoformat\(\)==('[0-9-]{10}')", text)
    need(len(dates) == 1, 'DISPATCHER_LITERALS')
    date_set = re.findall(r"'(\d{4}-\d{2}-\d{2})'", dates[0])
    m = rt['source']
    need(date_set and date_set == list(m.DATES), 'DISPATCH_DATE_LITERAL')
    facts = {'intent_schema': literal(text, '_DISPATCH_INTENT_V1'), 'claim_schema': literal(text, '_GO_CLAIM_V1'),
             'publication_schema': literal(text, '_INTENT_PUBLICATION_V1'), 'config_schema': literal(text, '_DISPATCH_AUTHORIZATION_V1'),
             'dates': date_set}
    need("'" + m.RECEIPT_SCHEMA + "'" in text and "'" + m.OPERATION + "'" in text, 'DISPATCHER_LITERALS')
    return facts


def template_chain(op, rt, facts):
    """The unbound set must be the consistent, unsigned template of exactly this operation before anything is bound to it."""
    files, m = op['files'], rt['source']
    request, authority, go, config, proof = (strict_json(files[name], 'TEMPLATE_INVALID') for name in TEMPLATE_NAMES)
    need(all(type(item) is dict for item in (request, authority, go, config, proof)), 'TEMPLATE_INVALID')
    source_sha = sha(files[op['source_name']])
    ok = (request.get('operation') == authority.get('operation') == go.get('operation') == config.get('operation') == m.OPERATION
          and request.get('status') == authority.get('status') == go.get('status') == config.get('status') == proof.get('status') == 'UNBOUND'
          and config.get('decision') == 'UNBOUND' and config.get('schema') == facts['config_schema'] and proof.get('schema') == facts['publication_schema']
          and request.get('payload_sha256') == go.get('payload_sha256') == source_sha
          and authority.get('request_sha256') == go.get('request_sha256') == sha(files['REQUEST.UNBOUND.json'])
          and go.get('authority_sha256') == sha(files['AUTHORITY.UNBOUND.json'])
          and type(go.get('transport_binding')) is dict and go['transport_binding'].get('runtime_sha256') == config['runtime_sha256']
          and go['transport_binding'].get('remote_command') == config.get('remote_command') == REMOTE_COMMAND
          and go['transport_binding'].get('target') is None and go['transport_binding'].get('command_sha256') is None
          and config.get('single_use') is True and config.get('retry') is False and type(config.get('executor_uid')) is int
          and config['executor_uid'] == 0 and config.get('finalize_local_receipts_after_window') is True
          and type(config.get('watchdog_seconds')) is int and 1 <= config['watchdog_seconds'] <= 90
          and all(config.get(key) is None for key in ('attempt_directory', 'authorization_ref', 'command_sha256', 'host_binding_sha256',
                                                      'latest_start', 'not_before', 'not_after', 'owner', 'target'))
          and all(type(config.get(key)) is dict and set(config[key]) == {'path', 'sha256'} for key in BLOBS + ('ssh_key', 'known_hosts'))
          and all(document.get(key) is None for document in (request, authority, go) for key in ('host_binding_sha256', 'not_before', 'not_after'))
          and authority.get('owner') is None and go.get('owner') is None and go.get('action') is None
          and authority.get('execution_authorized') is False and go.get('execution_authorized') is False
          and go.get('claim_root_identity') == {'device': None, 'inode': None, 'path': None} == config.get('local_root_identity')
          and set(proof) == {'config_sha256', 'go_sha256', 'intent_sha256', 'owner', 'publication_ref', 'published_at', 'schema', 'status'})
    need(ok, 'TEMPLATE_CHAIN')
    try:
        built = rt['launcher'].build(files[op['source_name']], files['REQUEST.UNBOUND.json'], files['AUTHORITY.UNBOUND.json'], files['GO.UNBOUND.json'],
                                     expected_payload_sha256=source_sha, expected_request_sha256=sha(files['REQUEST.UNBOUND.json']),
                                     expected_authority_sha256=sha(files['AUTHORITY.UNBOUND.json']), expected_go_sha256=sha(files['GO.UNBOUND.json']))
    except ValueError:
        raise Refused('TEMPLATE_CHAIN')
    need(built == files[UNBOUND_PAYLOAD], 'TEMPLATE_CHAIN')
    return {'request': request, 'authority': authority, 'go': go, 'config': config, 'proof': proof, 'source_sha256': source_sha}


# ---------------------------------------------------------------- transport reference (read, never printed)
def host_binding(target, known_hosts_sha256):
    return sha(canonical({'known_hosts_sha256': known_hosts_sha256, 'target': target}))


def target_domain(target):
    return target.rsplit('@', 1)[-1].rstrip('.').rsplit('.', 1)[-1].lower()


def is_rehearsal_transport(fields):
    return (fields['target'] == REHEARSAL_TARGET and fields['ssh_key']['sha256'] == sha(REHEARSAL_KEY)
            and fields['known_hosts']['sha256'] == sha(REHEARSAL_HOSTS))


def has_rehearsal_trait(fields):
    return (target_domain(fields['target']) in RESERVED_DOMAINS or fields['ssh_key']['sha256'] == sha(REHEARSAL_KEY)
            or fields['known_hosts']['sha256'] == sha(REHEARSAL_HOSTS))


def lstat_reference(item, older_than=None):
    """lstat ONLY: the key and known-hosts files are never opened by the binder. What the dispatcher's read() will demand
    (real ancestors, regular, one link, 1..65536 bytes, this user, 0600) and, when a last use is known, that neither
    mtime nor ctime is later than it. No path is ever reported."""
    current = '/'
    for part in PurePosixPath(item['path']).parts[1:-1]:
        current = os.path.join(current, part)
        try:
            info = os.lstat(current)
        except OSError:
            raise Refused('SSH_REFERENCE_FILE')
        need(stat.S_ISDIR(info.st_mode), 'SSH_REFERENCE_FILE')
    try:
        info = os.lstat(item['path'])
    except OSError:
        raise Refused('SSH_REFERENCE_FILE')
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= 65536 and info.st_uid == os.geteuid()
         and stat.S_IMODE(info.st_mode) == 0o600, 'SSH_REFERENCE_FILE')
    return None if older_than is None else (info.st_mtime_ns < older_than and info.st_ctime_ns < older_than)


def load_reference(path, mode, enforce_age):
    """REAL: an executed bound dispatch configuration (its exit.json proves one successful single attempt of exactly that
    configuration). REHEARSAL: the fake reference written by `rehearsal-reference`. Returns fields and facts; the facts
    hold hashes and booleans only."""
    need(clean_absolute(str(path)), 'TRANSPORT_REFERENCE_PATH')
    raw = read_file(path, 65536, 'TRANSPORT_REFERENCE_UNREADABLE')
    reference = strict_json(raw, 'TRANSPORT_REFERENCE_SHAPE')
    need(type(reference) is dict and type(reference.get('target')) is str and re.fullmatch(TARGET, reference['target'])
         and reference.get('remote_command') == REMOTE_COMMAND, 'TRANSPORT_REFERENCE_SHAPE')
    for key in ('ssh_key', 'known_hosts'):
        item = reference.get(key)
        need(type(item) is dict and set(item) == {'path', 'sha256'} and clean_absolute(item['path']) and is_hash(item['sha256']),
             'TRANSPORT_REFERENCE_SHAPE')
    fields = {key: reference[key] for key in ('target', 'remote_command', 'ssh_key', 'known_hosts')}
    is_rehearsal_file = reference.get('schema') == REHEARSAL_REFERENCE_SCHEMA
    facts = {'path': str(path), 'sha256': sha(raw), 'kind': REHEARSAL if is_rehearsal_file else REAL}
    if mode == REHEARSAL:
        need(is_rehearsal_file and is_rehearsal_transport(fields), 'REHEARSAL_SET_WITH_REAL_TRANSPORT')
        for key in ('ssh_key', 'known_hosts'):
            lstat_reference(fields[key])
        facts['connection_files'] = {'lstat_only_never_opened': True, 'rehearsal_marker_files': True}
        command_sha256 = None
    else:
        need(not is_rehearsal_file and not has_rehearsal_trait(fields), 'REAL_SET_WITH_REHEARSAL_TRANSPORT')
        need(type(reference.get('schema')) is str and reference['schema'].endswith('_DISPATCH_AUTHORIZATION_V1') and reference.get('status') == 'BOUND'
             and reference.get('decision') == 'GO' and is_hash(reference.get('command_sha256'))
             and clean_absolute(reference.get('attempt_directory')), 'TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG')
        attempt = reference['attempt_directory']
        exit_raw = read_file(os.path.join(attempt, 'exit.json'), 65536, 'TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG', private=True)
        result = strict_json(exit_raw, 'TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG')
        need(type(result) is dict and result.get('config_sha256') == sha(raw) and result.get('status') in RECEIPT_STATUS
             and result.get('command_sha256') == reference['command_sha256'] and result.get('attempts') == 1
             and result.get('stderr_sha256') == EMPTY_SHA256, 'TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG')
        stamps = {}
        for name in ('spawn.claim', 'exit.json'):
            try:
                info = os.lstat(os.path.join(attempt, name))
            except OSError:
                raise Refused('TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG')
            need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid(), 'TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG')
            stamps[name] = info.st_mtime_ns
        older = [lstat_reference(fields[key], stamps['exit.json']) for key in ('ssh_key', 'known_hosts')]
        need(all(older) or not enforce_age, 'SSH_REFERENCE_CHANGED_SINCE_LAST_USE')
        facts['connection_files'] = {'lstat_only_never_opened': True, 'mtime_and_ctime_older_than_last_use_exit_json': all(older)}
        facts['last_use'] = {'operation': reference.get('operation'), 'status': result['status'], 'finished_at': result.get('finished_at'),
                             'exit_json_sha256': sha(exit_raw)}
        command_sha256 = reference['command_sha256']
    host = host_binding(fields['target'], fields['known_hosts']['sha256'])
    if 'host_binding_sha256' in reference:
        need(reference['host_binding_sha256'] == host, 'HOST_BINDING_NOT_REPRODUCED')
    return fields, facts, host, command_sha256


def mode_guard(mode, bound, owner, fields=None):
    """A rehearsal set never carries a real transport or the owner's name, and a real set never carries a rehearsal one."""
    need(mode in (REAL, REHEARSAL), 'MODE_INVALID')
    named = Path(bound).name.startswith(REHEARSAL_PREFIX)
    if mode == REHEARSAL:
        need(named, 'REHEARSAL_DIRECTORY_NAME')
        need(owner == REHEARSAL_OWNER, 'OWNER_MODE_MISMATCH')
        need(fields is None or is_rehearsal_transport(fields), 'REHEARSAL_SET_WITH_REAL_TRANSPORT')
    else:
        need(not Path(bound).name.lower().startswith('rehearsal'), 'REAL_SET_IN_REHEARSAL_DIRECTORY')
        need(owner == REAL_OWNER, 'OWNER_MODE_MISMATCH')
        need(fields is None or not has_rehearsal_trait(fields), 'REAL_SET_WITH_REHEARSAL_TRANSPORT')


# ---------------------------------------------------------------- parameters
MISSING = object()


def pointer_value(node, pointer):
    """The value at a JSON pointer ("/a/0/b") of a decoded document, or MISSING."""
    for part in pointer.split('/')[1:]:
        part = part.replace('~1', '/').replace('~0', '~')
        if type(node) is dict and part in node:
            node = node[part]
        elif type(node) is list and re.fullmatch('0|[1-9][0-9]{0,5}', part) and int(part) < len(node):
            node = node[int(part)]
        else:
            return MISSING
    return node


def resolve_references(value, receipts, copied, pointer=''):
    """{"$from": {"evidence": ROLE, "pointer": "/a/0/b"}} anywhere in the plan is replaced by that value of the cited
    receipt: rows are copied by command, never typed."""
    if type(value) is dict:
        if set(value) == {'$from'}:
            spec = value['$from']
            need(type(spec) is dict and set(spec) == {'evidence', 'pointer'} and type(spec['evidence']) is str and spec['evidence'] in receipts
                 and type(spec['pointer']) is str and spec['pointer'].startswith('/'), 'PLAN_REFERENCE_INVALID')
            node = pointer_value(receipts[spec['evidence']], spec['pointer'])
            need(node is not MISSING, 'PLAN_REFERENCE_NOT_FOUND')
            copied.append({'plan_pointer': pointer or '/', 'evidence_role': spec['evidence'], 'receipt_pointer': spec['pointer']})
            return json.loads(json.dumps(node))
        need('$from' not in value, 'PLAN_REFERENCE_INVALID')
        return {key: resolve_references(item, receipts, copied, pointer + '/' + key) for key, item in value.items()}
    if type(value) is list:
        return [resolve_references(item, receipts, copied, pointer + '/' + str(index)) for index, item in enumerate(value)]
    return value


def receipt_rules(family, operation, collection=False, sources=None):
    """What a receipt cited for `operation` must be: the receipt schema, the success outcome and the hash of the source of
    that operation in the sealed family being bound. An operation that family does not hold cannot be cited.
    collection (HOSTOPS02 requests only): a source of the collection profile (W1) is accepted too; its receipts carry no
    operation and no outcome, and the outcome is then None."""
    try:
        op = select_operation(family, operation)
        source = load_runtime(op['files'], op['source_name'], op['directory'])['source']
    except Refused:
        raise Refused('EVIDENCE_OPERATION_NOT_IN_THIS_FAMILY')
    schema, outcome = getattr(source, 'RECEIPT_SCHEMA', None), getattr(source, 'COMPLETE_OUTCOME', None)
    if sources is not None:
        sources.append(source)
    if collection and outcome is None and all(hasattr(source, name) for name in COLLECTION_ATTRIBUTES):
        need(type(schema) is str and getattr(source, 'OPERATION', None) == operation, 'EVIDENCE_OPERATION_NOT_IN_THIS_FAMILY')
        return schema, None, sha(op['files'][op['source_name']])
    need(type(schema) is str and type(outcome) is str and getattr(source, 'OPERATION', None) == operation, 'EVIDENCE_OPERATION_NOT_IN_THIS_FAMILY')
    return schema, outcome, sha(op['files'][op['source_name']])


def evidence_from_bound_set(directory, operation, mode, seal, blobs=None):
    """The receipt of a finished attempt of a signed set, verified as `status` verifies it: exit.json binds the configuration,
    the request and the GO of that set and the stored output, stderr is empty, and the receipt binds request, authority, GO,
    payload and host and carries its seal. The set must be of the mode and of the sealed family of the request being bound
    (a REAL set is signed by the owner; a REHEARSAL one never is)."""
    try:
        state = signed_state(directory)
        report, raw = attempt_report(state)
    except Refused as error:
        raise Refused('EVIDENCE_SET_' + str(error))
    sheet = state['sheet']
    need(sheet['mode'] == mode, 'EVIDENCE_SET_OF_THE_OTHER_MODE')
    need(sheet.get('family') == seal, 'EVIDENCE_SET_OF_ANOTHER_SEAL')
    need(sheet['operation'] == operation, 'EVIDENCE_SET_OF_ANOTHER_OPERATION')
    need(report['verified'] is True and raw is not None, 'EVIDENCE_SET_WITHOUT_A_VERIFIED_RECEIPT')
    if blobs is not None:          # what a later rule may read of that set besides its receipt (in memory only): request, exit record, GO
        blobs.update(request=state['files']['REQUEST.BOUND.json'], exit=state['attempt_raw']['exit'], go=state['raws'][2], sheet=sheet)
    return raw, {'mode': sheet['mode'], 'config_sha256': report['config_sha256'], 'request_sha256': report['request_sha256'],
                 'go_sha256': report['go_sha256'], 'exit_json_sha256': report['exit_json_sha256'], 'transport_status': report['status'],
                 'exit_json_binds_config_request_go_and_output': True, 'stderr_empty': True,
                 'relocated_copy': report['bound_set_is_a_relocated_copy']}


def load_evidence(items, base, mode, host, family, seal, seals=None, blobs=None, foreign=None):
    """Each cited receipt is read and its seal recomputed: the hash that enters the request is computed here. Its provenance
    is checked as far as local files allow: the operation it names, the schema of that operation in this sealed family, the
    payload hash of that operation's sealed source, the host binding of the set being bound, and a complete outcome unless
    the parameter accepts another one by name. A REAL request cites bound sets only ("bound"); a loose receipt file
    ("receipt_file") is for rehearsals.
    seals (a request of the HOSTOPS02 kind only): an item may name, by "family", the directory of ANOTHER accepted seal that
    holds the cited operation (each HOSTOPS02 operation is its own sealed directory, and they cite HOSTOPS01 and W1
    receipts); the receipt is then judged by that family's sealed source and a cited set must carry that family's seal. A
    receipt of the collection profile (W1) names no operation and no outcome: it is complete when its status is the one of
    KNOWN_COMPLETE. blobs, when given, receives per role the bytes a later rule reads (never printed).
    foreign (a request of the earlier families only): (accepted seals, the operations of other accepted seals an item may
    name by "family"): the HOSTOPS01 readback and install_units may cite the K2a set of operation 4b. Only such an item
    gets a "family" member on the sheet: a request that cites none is bound as before."""
    need(type(items) is list and len(items) <= 16, 'PARAMETERS_INVALID')
    entries, receipts, facts = [], {}, []
    other_families = seals is not None or bool(foreign and foreign[1])
    keys = {'role', 'operation', 'receipt_file', 'bound', 'accept_not_complete'} | ({'family'} if other_families else set())
    for item in items:
        need(type(item) is dict and {'role', 'operation'} <= set(item) <= keys
             and len(set(item) & {'receipt_file', 'bound'}) == 1 and item.get('accept_not_complete', True) is True
             and type(item['role']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,63}', item['role']) and item['role'] not in receipts
             and type(item['operation']) is str and re.fullmatch(CODE, item['operation'])
             and type(item.get('receipt_file', item.get('bound'))) is str and type(item.get('family', '')) is str, 'PARAMETERS_INVALID')
        need(seals is not None or 'family' not in item or item['operation'] in foreign[1], 'PARAMETERS_INVALID')
        cited_family, cited_seal = family, seal
        if 'family' in item:
            other = Path(item['family'])
            other = other if other.is_absolute() else base / other
            accepted = seals if seals is not None else foreign[0]
            try:
                cited_family = verify_family(other, accepted)
                cited_seal = accepted_seal(accepted, cited_family['sums_sha256'])
            except Refused:
                raise Refused('EVIDENCE_FAMILY_NOT_AN_ACCEPTED_SEAL')
        cited_source = []
        schema, success, source_sha256 = receipt_rules(cited_family, item['operation'], collection=seals is not None, sources=cited_source)
        path = Path(item.get('receipt_file', item.get('bound')))
        path = path if path.is_absolute() else base / path
        bound_set, exit_bound, extra = None, None, {}
        if 'bound' in item:
            raw, bound_set = evidence_from_bound_set(path, item['operation'], mode, cited_seal, extra)
        else:
            need(mode == REHEARSAL, 'EVIDENCE_OF_A_REAL_REQUEST_MUST_BE_A_BOUND_SET')
            raw = read_file(path, 65536 + 1, 'EVIDENCE_RECEIPT_UNREADABLE')
        receipt = strict_json(raw, 'EVIDENCE_RECEIPT_INVALID')
        need(type(receipt) is dict and is_hash(receipt.get('metadata_sha256')), 'EVIDENCE_RECEIPT_INVALID')
        body = dict(receipt)
        claimed = body.pop('metadata_sha256')
        need(sha(canonical(body)) == claimed, 'EVIDENCE_RECEIPT_SEAL')
        need(receipt.get('status') in RECEIPT_STATUS.values(), 'EVIDENCE_RECEIPT_NOT_A_RESULT')
        need(receipt.get('operation') == (None if success is None else item['operation']), 'EVIDENCE_RECEIPT_OPERATION')
        need(receipt.get('schema') == schema, 'EVIDENCE_RECEIPT_SCHEMA')
        need(receipt.get('payload_sha256') == source_sha256, 'EVIDENCE_RECEIPT_OF_OTHER_BYTES')          # produced by the sealed source of that operation
        need(receipt.get('host_binding_sha256') == host, 'EVIDENCE_RECEIPT_OF_ANOTHER_HOST')
        if 'receipt_file' in item:
            exit_path = path.parent / 'exit.json'
            if exit_path.is_file() and not exit_path.is_symlink():
                result = strict_json(read_file(exit_path, 65536, 'EVIDENCE_RECEIPT_EXIT_MISMATCH'), 'EVIDENCE_RECEIPT_EXIT_MISMATCH')
                need(type(result) is dict and result.get('stdout_sha256') == sha(raw) and result.get('status') in RECEIPT_STATUS
                     and RECEIPT_STATUS[result['status']] == receipt['status'], 'EVIDENCE_RECEIPT_EXIT_MISMATCH')
                exit_bound = True
        outcome = receipt.get('outcome')
        if seals is not None or 'family' in item:
            success = success_of_the_signed_mode(cited_source[0], receipt, success)
        complete = receipt['status'] == RECEIPT_STATUS['KNOWN_COMPLETE'] and outcome == success
        need(complete or item.get('accept_not_complete') is True, 'EVIDENCE_RECEIPT_NOT_COMPLETE')
        receipts[item['role']] = receipt
        entries.append({'role': item['role'], 'operation': item['operation'], 'receipt_sha256': claimed})
        fact = {'role': item['role'], 'operation': item['operation'], 'receipt_sha256': claimed, 'receipt_file_sha256': sha(raw),
                'receipt_status': receipt['status'], 'receipt_schema': schema,
                'outcome': outcome if type(outcome) is str and re.fullmatch(CODE, outcome) else None,
                'complete': complete, 'not_complete_accepted_by_parameter': not complete,
                'receipt_host_binding_is_the_one_of_this_set': True, 'receipt_payload_is_the_sealed_source_of_that_operation': True,
                'source': 'BOUND_SET' if bound_set else 'RECEIPT_FILE', 'bound_set': bound_set,
                'exit_json_binds_these_bytes': True if bound_set else exit_bound}
        if seals is not None or 'family' in item:
            fact['family'] = cited_seal
        facts.append(fact)
        if blobs is not None:
            blobs[item['role']] = dict(extra, receipt=raw, seal=cited_seal, path=str(path), source='bound' if 'bound' in item else 'receipt_file')
    return entries, receipts, facts


def success_of_the_signed_mode(source, receipt, success):
    """The success outcome of the mode a cited HOSTOPS02 receipt was signed in, read from its signed effects (which its
    source recomputed from the plan and compared with the authority and the GO): K2a names it (effects.success_outcome); K11
    says its mode and dry run, whose outcomes are constants of its source. Otherwise the source's COMPLETE_OUTCOME."""
    effects = receipt.get('effects') if type(receipt.get('effects')) is dict else {}
    if type(effects.get('success_outcome')) is str and effects.get('mode') in ('REAL', 'REHEARSAL'):
        return effects['success_outcome']
    if type(getattr(source, 'PRE_OUTCOME', None)) is str and effects.get('mode') == 'PRE':
        return source.PRE_OUTCOME if effects.get('dry_run') == 'FULL' else getattr(source, 'PRE_REDUCED_OUTCOME', None)
    # rev 4: the programs of SEALED_PROGRAMS whose success follows the signed mode (DBR PRIV/QUERIES, K5 ACTIVATE/RESET,
    # K13 ACTIVATE/RESTART/DEACTIVATE, ...): their own success_of, on the mode the receipt's effects signed
    if receipt.get('operation') in SEALED_PROGRAMS and (type(effects.get('mode')) is str or type(effects.get('step')) is str) and callable(getattr(source, 'success_of', None)):
        try:
            found = source.success_of({'mode': effects['mode']} if 'mode' in effects else {'step': effects['step']})
        except Exception:
            found = None
        if type(found) is str:
            return found
    # rev 4: K9R's success follows its signed mode (RESULT, PROBE, POLICY, TREE), a table of its sealed source
    modes = getattr(source, 'K9_SUCCESS', None)
    if receipt.get('operation') == K9R_OPERATION and type(modes) is dict and effects.get('mode') in modes and type(modes[effects['mode']]) is str:
        return modes[effects['mode']]
    return success


def plan_members(plan, pointer):
    """(key, value) pairs of the plan members a PLAN_SOURCES pointer names; "*" expands over the keys of an object."""
    head, star, _ = pointer.partition('/*')
    node = pointer_value(plan, head)
    if not star:
        return [(None, None if node is MISSING else node)]
    return [(key, node[key]) for key in sorted(node)] if type(node) is dict else []


def plan_sources(operation, plan, evidence_entries, receipts, table=None):
    """Section 11 of the core family's contract, by command: every plan member that comes from a receipt equals the value of
    the single cited receipt of that operation, whether the parameter typed it or copied it by pointer. A value of another
    boot, another receipt or another outcome is refused here, before the owner is asked. table: rows other than the
    operation's own PLAN_SOURCES (the catalog rows of a HOSTOPS01 readback that cites the K2a set)."""
    cited = {}
    for entry in evidence_entries:
        cited.setdefault(entry['operation'], []).append(receipts[entry['role']])
    boots = {canonical(pointer_value(receipt, BOOT_POINTER)) for receipt in cited.get(PRECHECK_OPERATION, []) if pointer_value(receipt, BOOT_POINTER) is not MISSING}
    need(len(boots) <= 1, 'CITED_PRECHECKS_OF_DIFFERENT_BOOTS')
    checked = []
    for plan_pointer, source_operation, receipt_pointer in (PLAN_SOURCES.get(operation, ()) if table is None else table):
        for key, value in plan_members(plan, plan_pointer):
            if value is None:
                continue
            need(len(cited.get(source_operation, [])) == 1, 'PLAN_VALUE_WITHOUT_ITS_SINGLE_CITED_RECEIPT')
            wanted = pointer_value(cited[source_operation][0], receipt_pointer if key is None else receipt_pointer.replace('*', key.replace('~', '~0').replace('/', '~1')))
            need(wanted is not MISSING and canonical(value) == canonical(wanted), 'PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT')
            checked.append({'plan_pointer': plan_pointer if key is None else plan_pointer.replace('*', key), 'operation': source_operation,
                            'receipt_pointer': receipt_pointer if key is None else receipt_pointer.replace('*', key)})
    return checked


def catalog_citation_rules(operation, mode, plan, entries, receipts, facts):
    """K2a CONTRACT 6 and HOSTOPS01 CONTRACT 7.1 and 11: the readback of operation 4 signs catalog{expected INITIALISED,
    receipt_sha256, device, inode} from the receipt of operation 4b (receipt_sha256 = its metadata_sha256; device and inode =
    script_line.device and .inode); install_units follows A9 KNOWN_COMPLETE in the plan. A request of these two operations
    may cite the K2a set by its family; it must then be the ONE complete REAL receipt (CATALOG_READY_VERIFIED, mode REAL:
    never the rehearsal's, never a partial one), of the boot the request signs, and for the readback the catalog triple and
    the image revision (against the precheck's reading of the image label) are compared with the cited receipts. A REAL
    readback that expects an INITIALISED catalog must cite it. Returns None when the request cites no K2a set (it is then
    bound exactly as before), else the checked rows and the role, for the sheet."""
    if operation not in HOSTOPS01_MAY_CITE:
        return None
    roles = [entry['role'] for entry in entries if entry['operation'] == CATALOG_OPERATION]
    catalog = plan.get('catalog') if type(plan.get('catalog')) is dict else {}
    if not roles:
        need(not (operation == READBACK_OPERATION and mode == REAL and catalog.get('expected') == 'INITIALISED'), 'CATALOG_WITHOUT_THE_CITED_4B_RECEIPT')
        return None
    need(len(roles) == 1, 'CATALOG_4B_RECEIPT_NOT_ONE')
    receipt, fact = receipts[roles[0]], [item for item in facts if item['role'] == roles[0]][0]
    need(fact['complete'] is True and receipt.get('mode') == 'REAL' and at(receipt, '/effects/mode') == 'REAL'
         and receipt.get('outcome') == CATALOG_READY_OUTCOME, 'CATALOG_4B_RECEIPT_NOT_THE_COMPLETE_REAL_ONE')
    need(at(receipt, '/effects/evidence_boot_id_sha256') == plan.get('evidence_boot_id_sha256'), 'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    checked = []
    if operation == READBACK_OPERATION:
        need(catalog.get('expected') == 'INITIALISED', 'CATALOG_EXPECTATION_NOT_THE_CITED_4B')
        checked = plan_sources(operation, plan, entries, receipts, CATALOG_CITATION_SOURCES)
        need(len(checked) == len(CATALOG_CITATION_SOURCES), 'CATALOG_EXPECTATION_NOT_THE_CITED_4B')
    return {'checked': checked, 'catalog_4b_receipt_cited': roles[0]}


def load_review(item, base, identity=None):
    """The owner's decision on writes makes Codex's review of the bytes a precondition of each write unless the owner waives
    it for that operation. A write request says which of the two holds and names the document that records it; the hash of
    that document is computed here, goes on the sheet and is quoted to the owner.
    identity (HOSTOPS02 requests): what the document must carry, as text, to be about THESE bytes (see review_of_these_bytes);
    without it (the earlier families) the document is only hashed, as before."""
    need(type(item) is dict and set(item) == {'kind', 'document_file'} and type(item['kind']) is str and item['kind'] in REVIEW_KINDS
         and type(item['document_file']) is str, 'REVIEW_OR_WAIVER_INVALID')
    path = Path(item['document_file'])
    raw = read_file(path if path.is_absolute() else base / path, 1024 * 1024, 'REVIEW_OR_WAIVER_DOCUMENT_UNREADABLE')
    found = {'kind': item['kind'], 'document_sha256': sha(raw), 'document_bytes': len(raw)}
    if identity is not None:
        found.update(review_of_these_bytes(item['kind'], raw, identity))
    return found


def hashes_named(raw, identity, keys):
    """The keys of `identity` whose 64-hex value the document carries as text (bytes compared: a log need not be UTF-8)."""
    return sorted(key for key in keys if identity.get(key) and identity[key].encode('ascii') in raw)


def names_these_bytes(raw, identity, also=()):
    """A document is about THESE bytes when it names, as text, the seal of the operation directory (its SHA256SUMS) and
    the payload: the assembled source or the unbound final payload (either one names the same payload bytes); `also`
    lists hashes it must carry besides (the core's seal, for the Linux job)."""
    named = hashes_named(raw, identity, ('seal', 'source', 'final_payload_unbound') + tuple(also))
    ok = 'seal' in named and ('source' in named or 'final_payload_unbound' in named) and all(key in named for key in also)
    return ok, named


def review_of_these_bytes(kind, raw, identity):
    """CODEX_REVIEWED: the co-auditor's document names the seal and the payload of these bytes (a review of other bytes,
    of the build before a repair, of a superseded seal, is refused). OWNER_WAIVED: the waiver is the owner's own act,
    recorded on its own before this request (A1, section 8): an owner decision record (schema OWNER_DECISION_V1) with his
    verbatim answer, the channel and the instant, that names this operation, its seal and its payload. The signature over
    this sheet is never the waiver."""
    ok, named = names_these_bytes(raw, identity)
    if kind == 'CODEX_REVIEWED':
        need(ok, 'REVIEW_DOCUMENT_DOES_NOT_NAME_THESE_BYTES')
        return {'names_these_bytes': named}
    record = strict_json(raw, 'OWNER_WAIVER_NOT_A_SIGNED_RECORD_FOR_THESE_BYTES')
    owner, channel = (REAL_OWNER, REAL_CHANNEL) if identity['mode'] == REAL else (REHEARSAL_OWNER, REHEARSAL_CHANNEL)
    evidence = record.get('owner_evidence') if type(record) is dict else None
    answer = record.get('owner_answer_verbatim') if type(record) is dict else None
    need(type(record) is dict and record.get('schema') == 'OWNER_DECISION_V1' and record.get('owner') == owner and type(answer) is str
         and 0 < len(answer) <= 200 and answer.isprintable() and type(evidence) is dict and evidence.get('channel') == channel
         and type(evidence.get('signed_at_utc')) is str and ok and identity['operation'].encode('ascii') in raw,
         'OWNER_WAIVER_NOT_A_SIGNED_RECORD_FOR_THESE_BYTES')
    signed = parse_utc(evidence['signed_at_utc'], 'OWNER_WAIVER_NOT_A_SIGNED_RECORD_FOR_THESE_BYTES')
    need(signed <= identity['now'], 'OWNER_WAIVER_NOT_A_SIGNED_RECORD_FOR_THESE_BYTES')
    return {'names_these_bytes': named, 'owner_waiver_signed_at_utc': zulu(signed)}


def reference_render(template, values):
    """The repository's reference loop, written here independently of the family's renderer: every @NAME@ is replaced by
    its value and no @ may be left."""
    need(type(values) is dict and all(type(name) is str and type(value) is str for name, value in values.items()), 'UNIT_RENDER_NOT_THE_REFERENCE_LOOP')
    try:
        text = template.decode('ascii')
        for name, value in values.items():
            text = text.replace('@' + name + '@', value)
        rendered = text.encode('ascii')
    except UnicodeError:
        raise Refused('UNIT_RENDER_NOT_THE_REFERENCE_LOOP')
    need(b'@' not in rendered, 'UNIT_RENDER_NOT_THE_REFERENCE_LOOP')
    return rendered


def presign_rules(plan, evidence_entries, receipts):
    """What section 12 of the core family's contract asks of the binder beyond the family's own code, by command:
    step 3, every unit of the plan rendered again by the reference loop and compared with the signed hash and size;
    step 2b, for a GATE readback, the floor against the figure of the precheck receipt on the chain the provision
    receipt names, and the journal mount point against the one in the provision receipt's effects."""
    done = {}
    units = [(unit, unit.get('placeholders') if type(unit) is dict else None) for unit in plan['units']] if type(plan.get('units')) is list else []
    units += [(plan[key], plan.get('substitutions')) for key in ('service', 'timer') if type(plan.get(key)) is dict and 'template_b64' in plan[key]]
    for unit, values in units:
        need(type(unit) is dict and type(unit.get('template_b64')) is str, 'UNIT_RENDER_NOT_THE_REFERENCE_LOOP')
        try:
            template = base64.b64decode(unit['template_b64'], validate=True)
        except ValueError:
            raise Refused('UNIT_RENDER_NOT_THE_REFERENCE_LOOP')
        rendered = reference_render(template, values)
        need(unit.get('rendered_sha256') == sha(rendered) and type(unit.get('rendered_bytes')) is int and unit['rendered_bytes'] == len(rendered)
             and ('template_sha256' not in unit or unit['template_sha256'] == sha(template)), 'UNIT_RENDER_NOT_THE_REFERENCE_LOOP')
    done['units_rendered_again_by_the_reference_loop'] = len(units)
    if 'free_space_floor_bytes' in plan and plan.get('mode') == 'GATE':
        cited = {}
        for entry in evidence_entries:
            cited.setdefault(entry['operation'], []).append(receipts[entry['role']])
        provision, precheck = cited.get(FLOOR_RULE['provision_operation'], []), cited.get(FLOOR_RULE['precheck_operation'], [])
        need(len(provision) == 1 and len(precheck) == 1, 'READBACK_FLOOR_EVIDENCE_MISSING')
        journal = provision[0].get('effects', {}).get('journal') if type(provision[0].get('effects')) is dict else None
        need(type(journal) is dict and type(journal.get('filesystem_named_by_chain')) is str, 'READBACK_FLOOR_EVIDENCE_MISSING')
        chains = precheck[0].get('items', {}).get('chains') if type(precheck[0].get('items')) is dict else None
        chain = chains.get(journal['filesystem_named_by_chain']) if type(chains) is dict else None
        available = chain.get('bytes_available_to_non_root_f_bavail') if type(chain) is dict else None
        need(type(available) is int and type(plan['free_space_floor_bytes']) is int, 'READBACK_FLOOR_EVIDENCE_MISSING')
        need(available >= plan['free_space_floor_bytes'], 'FREE_SPACE_BELOW_FLOOR_DO_NOT_ASK_FOR_THE_SIGNATURE')
        need(plan.get('journal_mount_point') == journal.get('mount_point_by_device_change'), 'READBACK_MOUNT_POINT_NOT_THE_PROVISION_ONE')
        done.update(floor_compared_on_chain=journal['filesystem_named_by_chain'], floor_met_by_the_precheck_figure=True,
                    journal_mount_point_is_the_one_in_the_provision_effects=True)
    return done


def load_parameters(path, operation, profile, template, extra=frozenset(), hostops02=False):
    raw = read_file(path, 1024 * 1024, 'PARAMETERS_UNREADABLE')
    params = strict_json(raw, 'PARAMETERS_INVALID')
    common = {'schema', 'operation', 'label', 'not_before', 'not_after', 'signature_model'}
    allowed = common | {'purpose_pt', 'owner_summary_pt', 'gate_not_before', 'gate_not_after'}
    writes = bool(template['request'].get('writes_allowed'))
    # A HOSTOPS02 request names the review of its bytes even when it writes nothing: K11 starts a container, and the order
    # conditions it on "programa revisto" (A1 4.2, C4; K11 CONTRACT 1 and 8, step 1).
    reviewed = writes or hostops02
    if profile == 'core':
        required, allowed = common | {'plan', 'evidence'}, allowed | {'plan', 'evidence'} | ({'review'} if reviewed else set()) | set(extra)
    else:
        extra = {'candidates'} if 'candidates' in template['request']['collection'] else set()
        required, allowed = common | extra, allowed | extra
    need(type(params) is dict and required <= set(params) <= allowed and params['schema'] == PARAMETERS_SCHEMA, 'PARAMETERS_INVALID')
    need(params['operation'] == operation, 'PARAMETERS_OPERATION_MISMATCH')
    need(type(params['label']) is str and re.fullmatch(LABEL, params['label']), 'PARAMETERS_LABEL')
    need(type(params['signature_model']) is str and params['signature_model'] in tuple(SIGNATURE_MODELS) + SIGNATURE_MODELS_NOT_IMPLEMENTED, 'PARAMETERS_INVALID')
    # One literal owner answer per sheet is all this binder records. A read of the grid, or a weekly signature, has no
    # owner answer of its own: binding it here would write that the owner answered.
    need(params['signature_model'] in SIGNATURE_MODELS, 'SIGNATURE_MODEL_NOT_IMPLEMENTED')
    need(not writes or 'review' in params, 'REVIEW_OR_WAIVER_MISSING_FOR_A_WRITE')
    need(not reviewed or 'review' in params, 'REVIEW_OR_WAIVER_MISSING_FOR_A_CONTAINER_RUN')
    for key in ('purpose_pt', 'owner_summary_pt'):
        need(key not in params or free_text(params[key]), 'PARAMETERS_FREE_TEXT')
    need(('gate_not_before' in params) == ('gate_not_after' in params), 'PARAMETERS_INVALID')
    fixed = operation in OWNER_TEXT_PT or (hostops02 and operation in HOSTOPS02_TEXT_PT)
    need(fixed or 'owner_summary_pt' in params, 'OWNER_SUMMARY_MISSING')
    need(not fixed or 'owner_summary_pt' not in params, 'OWNER_SUMMARY_IS_FIXED_FOR_THIS_OPERATION')
    start, end = parse_utc(params['not_before'], 'WINDOW_NOT_UTC_SECONDS'), parse_utc(params['not_after'], 'WINDOW_NOT_UTC_SECONDS')
    gate_start = parse_utc(params['gate_not_before'], 'WINDOW_NOT_UTC_SECONDS') if 'gate_not_before' in params else start
    gate_end = parse_utc(params['gate_not_after'], 'WINDOW_NOT_UTC_SECONDS') if 'gate_not_after' in params else end
    need(start < end and start <= gate_start < gate_end <= end, 'WINDOW_ORDER')
    need(start.date() == end.date(), 'WINDOW_CROSSES_UTC_MIDNIGHT')
    return params, sha(raw), raw, {'start': start, 'end': end, 'gate_start': gate_start, 'gate_end': gate_end}


# ---------------------------------------------------------------- HOSTOPS02: one sealed directory per operation, a frozen core beside it
# Each HOSTOPS02 operation (K2a catalog_init, K10 install_release, K11 epoch_readback, K6a activate) is its own sealed
# directory (SHA256SUMS at its root), assembled from the frozen core that lies beside it as ../core (CORE_SHA256SUMS).
# What their CONTRACT.txt leaves to the binder is below, operation by operation; what they leave to the DISPATCH (a gate
# that must hold minutes before the dispatcher's prepare, not when the owner signs) is evaluated by `check --gates`.
CORE_DIRECTORY = 'core'
CORE_SUMS = 'CORE_SHA256SUMS'
CORE_SKIPPED = ('__pycache__', '.pytest_cache', '_tmp')                       # what the core's own seal.py does not list
CORE_RUN_OUTPUT = r'linux_root/(TESTS\..*\.xml|SHAPES\.linux-root\.json)'     # what the core's Linux job writes while it runs
ASSEMBLY_SCHEMA = 'HOSTOPS02_ASSEMBLY_V1'
CATALOG_OPERATION = 'GO_WRITE_HOSTOPS02_CATALOG_INIT_01'
RELEASE_OPERATION = 'GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01'
EPOCH_READBACK_OPERATION = 'GO_READONLY_HOSTOPS02_EPOCH_READBACK_01'
ACTIVATE_OPERATION = 'GO_WRITE_HOSTOPS02_ACTIVATE_01'
W1_OPERATION = 'GO_READONLY_W1PREFLIGHT_01'
PRE_FULL_OUTCOME = 'EPOCH_DRY_RUN_PRE_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
POST_OUTCOME = 'EPOCH_READBACK_POST_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
RELEASE_INSTALLED_OUTCOME = 'RELEASE_INSTALLED_BYTES_READ_BACK_NOT_ACTIVATED'
REHEARSAL_CATALOG_OUTCOME = 'REHEARSAL_CATALOG_READY_VERIFIED'
SUNDAY_ONLY_FAILURE = 'M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR'      # K10 CONTRACT 6, step 12: the one check that fails on Sunday
GRID_READ_MAX_AGE_SECONDS = 3600              # K2a "a grid read of this boot, taken minutes before the dispatch": at most one hour (the K10 gate's figure)
GRID_READ_CLOCK_SKEW_SECONDS = 30
BOOT_MARGIN_SECONDS = 60                      # a boot that began at least this long before the evidence was taken is its boot (K10 predispatch)
MINUTES_TO_AVOID = ((5, 7), (10, 25), (35, 37))         # watchdog, controller cycle (K2a CONTRACT 5 step 6, K11 CONTRACT 8 step 7, the plan for the lock)
MIN_USABLE_MINUTES = 3                        # a gate must leave the dispatcher's prepare, the publication and the resume this many whole minutes
GATES_SCHEMA = 'BIND_ONCE_DISPATCH_GATES_V1'
INPUT_FORMS = ('b64', 'sha256', 'bytes')
CATALOG_READY_OUTCOME = 'CATALOG_READY_VERIFIED'
SPARE_REGISTRY_SCHEMA = 'BIND_ONCE_SPARE_REGISTRY_V1'
# A1 (definition of "despachado"; section 8): a spare replaces a primary that was provably never sent. For K2a and K6a a
# primary that the dispatcher prepared (claim and intent.json, no spawn.claim) is never sent once its latest start has
# passed: its resume is refused before spawn.claim (WINDOW_WITH_WATCHDOG). K10 keeps its contract's stricter rule (step 15).
SPARE_AFTER_A_PREPARED_PRIMARY = ('GO_WRITE_HOSTOPS02_CATALOG_INIT_01', 'GO_WRITE_HOSTOPS02_ACTIVATE_01',
                                  # rev 4, K9 (NOTE 5.7 rule 3: a SPARE only if its PRIMARY was never dispatched, A1's "no spawn.claim")
                                  'GO_READONLY_HOSTOPS02_K9_PHASE_READ_01', 'GO_WRITE_HOSTOPS02_K9_PHASE_STEP_01')
# The HOSTOPS01 operations that may cite the K2a set of operation 4b by its family (K2a CONTRACT 6; HOSTOPS01 CONTRACT 7.1 and
# 11), and, for the readback, the plan members taken from that receipt (and the image revision from the precheck the readback
# cites). Applied only when the request cites it: a request that cites no K2a set is bound as before.
HOSTOPS01_MAY_CITE = {READBACK_OPERATION: ('GO_WRITE_HOSTOPS02_CATALOG_INIT_01',), INSTALL_OPERATION: ('GO_WRITE_HOSTOPS02_CATALOG_INIT_01',)}
CATALOG_CITATION_SOURCES = (('/catalog/receipt_sha256', 'GO_WRITE_HOSTOPS02_CATALOG_INIT_01', '/metadata_sha256'),
                            ('/catalog/device', 'GO_WRITE_HOSTOPS02_CATALOG_INIT_01', '/script_line/device'),
                            ('/catalog/inode', 'GO_WRITE_HOSTOPS02_CATALOG_INIT_01', '/script_line/inode'),
                            ('/image_revision', PRECHECK_OPERATION, '/items/image/revision_label'))
HOSTOPS02 = {
    # inputs: bind-time files the plan takes by {"$input": NAME, "as": FORM}; spare: a second bound set may shadow a primary;
    # minutes: the contract names the minutes to avoid; linux_proof: the K10 gate of the binding.
    CATALOG_OPERATION: {'inputs': (), 'spare': True, 'minutes': True},          # A9's reserve on Sunday (A1 4.2, C2)
    RELEASE_OPERATION: {'inputs': ('release',), 'spare': True, 'minutes': False},
    EPOCH_READBACK_OPERATION: {'inputs': ('release', 'policy', 'override'), 'spare': False, 'minutes': True},
    ACTIVATE_OPERATION: {'inputs': ('policy', 'release', 'override'), 'spare': True, 'minutes': True},          # override: compared, not carried
    # rev 4: the two K9 host programs (K9_INTERFACE_NOTE.md rev 2, section 10.4); their rules are in the K9 section below
    'GO_READONLY_HOSTOPS02_K9_PHASE_READ_01': {'inputs': (), 'spare': True, 'minutes': True},          # K9R
    'GO_WRITE_HOSTOPS02_K9_PHASE_STEP_01': {'inputs': (), 'spare': True, 'minutes': True},             # K9W
    'GO_WRITE_HOSTOPS02_K4_E0_01': {'inputs': ('runner',), 'spare': False, 'minutes': True},           # K4 mode E0: the K9 tree and the runner
    'GO_WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_01': {'inputs': (), 'spare': False, 'minutes': True},
    'GO_WRITE_HOSTOPS02_K3K9_SECRETS_01': {'inputs': (), 'spare': False, 'minutes': True},            # K3-K9: the K9 secrets
    'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01': {'inputs': ('k8_contract',) + tuple('k8_file_%02d' % i for i in range(12)), 'spare': False, 'minutes': True},          # rev 4: K8
    'GO_WRITE_HOSTOPS02_K12_PREFLIGHT_01': {'inputs': ('k12_request',), 'spare': False, 'minutes': True},          # rev 4: K12P
    'GO_WRITE_HOSTOPS02_K12_WINDOW_01': {'inputs': ('k12_request',), 'spare': False, 'minutes': True},          # rev 4: K12W
    'GO_READONLY_HOSTOPS02_K12_COLLECT_01': {'inputs': ('k12_request',), 'spare': False, 'minutes': True},          # rev 4: K12C
    'GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01': {'inputs': (), 'spare': False, 'minutes': True},
    'GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01': {'inputs': (), 'spare': False, 'minutes': True},          # rev 4: K6B
    'GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01': {'inputs': (), 'spare': False, 'minutes': True},          # rev 4: K5
    'GO_READONLY_HOSTOPS02_DB_PRIV_01': {'inputs': (), 'spare': False, 'minutes': True},
    'GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01': {'inputs': (), 'spare': False, 'minutes': True},          # rev 4: DBR
    'GO_WRITE_HOSTOPS02_READER_UNITS_01': {'inputs': (), 'spare': False, 'minutes': True},          # rev 4: UNITS
    'GO_WRITE_HOSTOPS02_K4_FILES_01': {'inputs': ('k4_static_config','k4_launcher'), 'spare': False, 'minutes': True},          # rev 4: K4F
    'GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01': {'inputs': (), 'spare': False, 'minutes': True},          # rev 4: K3
    'GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01': {'inputs': (), 'spare': False, 'minutes': True},          # rev 4: K13
    'GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01': {'inputs': (), 'spare': False, 'minutes': True},          # rev 4: K13R
}


def hostops02_extra_keys(operation, seal):
    """The parameter keys a request of this kind may carry beyond the core profile's."""
    if 'core' not in seal or operation not in HOSTOPS02:
        return frozenset()
    rules = HOSTOPS02[operation]
    return frozenset(({'inputs'} if rules['inputs'] else set()) | ({'spare_of'} if rules['spare'] else set())
                     | ({'linux_proof', 'host_evidence_reason_pt'} if operation == RELEASE_OPERATION else {'linux_job'})
                     | ({'release_tree', 'rehearsal'} if operation == CATALOG_OPERATION else set())
                     | ({'siblings_tests'} if operation == EPOCH_READBACK_OPERATION else set())
                     | ({'k9_grid'} if operation in K9_PROGRAMS else set())
                     | ({'k8_document_sets'} if operation == 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01' else set())
                     | ({'k12_document_set'} if operation in ('GO_WRITE_HOSTOPS02_K12_PREFLIGHT_01','GO_WRITE_HOSTOPS02_K12_WINDOW_01','GO_READONLY_HOSTOPS02_K12_COLLECT_01') else set()))          # rev 4: the grid of the K9 note a daily K9 request is placed on


def hostops02_identity(family, op, seal, template, mode, moment, operation):
    """The hashes that name THESE bytes in a review, a waiver record or a Linux job record: the seal of the operation
    directory, the assembled source, the unbound final payload, the core's seal."""
    return {'seal': family['sums_sha256'], 'source': template['source_sha256'], 'final_payload_unbound': sha(op['files'][UNBOUND_PAYLOAD]),
            'core': seal['core']['sha256sums_sha256'], 'operation': operation, 'mode': mode, 'now': moment}


def core_assembly_check(core, directory):
    """The core's own check (assemble.py --check <operation directory>), as a separate isolated process whose bytecode
    cache prefix is a fresh empty directory (no cached bytecode can stand in for the sealed spec.py and op.py): BUILD_EQUAL."""
    python = '/usr/bin/python3' if os.path.exists('/usr/bin/python3') else sys.executable
    prefix = tempfile.mkdtemp(prefix='bind-once-assembly-check-')
    try:
        done = subprocess.run([python, '-I', '-B', '-X', 'pycache_prefix=' + prefix, str(Path(core) / 'assemble.py'), '--check', str(directory)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': tempfile.gettempdir()}, timeout=120)
    except (OSError, subprocess.SubprocessError):
        done = None
    finally:
        empty = not os.listdir(prefix)
        shutil.rmtree(prefix, ignore_errors=True)
    need(done is not None and done.returncode == 0 and done.stdout == b'BUILD_EQUAL\n' and done.stderr == b'' and empty, 'CORE_ASSEMBLY_CHECK_FAILED')
    return {'command': 'assemble.py --check', 'answer': 'BUILD_EQUAL', 'interpreter': python, 'bytecode_cache_prefix_stayed_empty': True}


def hostops02_core(family, seal, op, rt):
    """CONTRACT step 0/1 of every HOSTOPS02 operation: the frozen core beside the operation directory, every file as its
    CORE_SHA256SUMS lists it and nothing else, that list being the accepted one and its assemble.py the generation the
    source carries; the operation's build equal to what that core assembles (the core's own check); and the assembly
    record agreeing with the payload source, dispatcher, launcher, transport and unbound payload that are bound."""
    root = family['directory'].parent / core_directory_of(seal)          # rev 4: "core" unless the accepted seal names another
    need(root.is_dir() and not root.is_symlink(), 'CORE_NOT_FOUND')
    root = root.resolve()
    sums_raw = read_file(root / CORE_SUMS, 1024 * 1024, 'CORE_NOT_FOUND')
    need(sha(sums_raw) == seal['core']['sha256sums_sha256'], 'CORE_SEAL_NOT_ACCEPTED')
    listed = {}
    try:
        lines = sums_raw.decode('ascii').splitlines()
    except UnicodeDecodeError:
        raise Refused('CORE_SUMS_INVALID')
    for line in lines:
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_./-]+)', line)
        need(match and match.group(2) not in listed and '..' not in match.group(2).split('/') and not match.group(2).startswith('/'), 'CORE_SUMS_INVALID')
        listed[match.group(2)] = match.group(1)
    need(listed, 'CORE_SUMS_INVALID')
    present = set()
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if set(relative.parts) & set(CORE_SKIPPED) or path.suffix == '.pyc' or re.fullmatch(CORE_RUN_OUTPUT, relative.as_posix()):
            continue
        if path.is_symlink() or not path.is_dir():
            present.add(relative.as_posix())
    need(present - {CORE_SUMS} == set(listed), 'CORE_FILE_SET')
    for name, digest in sorted(listed.items()):
        need(sha(read_file(root / name, 8 * 1024 * 1024, 'CORE_FILE_SET')) == digest, 'CORE_HASH')
    generation = listed.get('assemble.py')
    m = rt['source']
    need(generation == seal['core']['generation_sha256'] == getattr(m, 'CORE_SHA256', None), 'CORE_GENERATION_NOT_THE_SOURCES')
    prefix = op['directory'].relative_to(family['directory']).as_posix()
    record = strict_json(family['files'].get(('' if prefix == '.' else prefix + '/') + 'ASSEMBLY.json', b''), 'ASSEMBLY_RECORD_NOT_THE_BUILD')
    files = op['files']
    expected = {'schema': ASSEMBLY_SCHEMA, 'operation': m.OPERATION, 'core_sha256': generation, 'source_sha256': sha(files[op['source_name']]),
                'module': op['source_name'][:-3], 'dispatcher_sha256': sha(files['dispatch_once.py']), 'launcher_sha256': sha(files['launcher_stdin.py']),
                'transport_sha256': sha(files['transport_once.py']), 'final_payload_sha256': sha(files[UNBOUND_PAYLOAD]), 'scope_sha256': m.SCOPE_SHA256,
                'dates': list(m.DATES)}
    need(type(record) is dict and all(record.get(key) == value for key, value in expected.items()), 'ASSEMBLY_RECORD_NOT_THE_BUILD')
    return {'core_sha256sums_sha256': sha(sums_raw), 'generation_sha256': generation, 'core_files': len(listed),
            'assembly_check': core_assembly_check(root, family['directory']),
            'assembly': {key: expected[key] for key in ('source_sha256', 'dispatcher_sha256', 'launcher_sha256', 'transport_sha256', 'final_payload_sha256')},
            'unsealed_directories_skipped': family.get('unsealed_directories_skipped', [])}


def binding_tool(family, name):
    """One of the bind-time tools a sealed operation directory carries (binding/<name>), from its sealed bytes, as a private
    module object (the tools have no action on import). The binder calls their pure functions with bytes it verified."""
    raw = family['files'].get('binding/' + name)
    need(raw is not None, 'BINDING_TOOL_MISSING')
    module = types.ModuleType('_bind_once_tool_%s_%s' % (name[:-3], sha(raw)[:12]))
    module.__file__ = str(family['directory'] / 'binding' / name)
    try:
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    except Exception:
        raise Refused('BINDING_TOOL_MISSING')
    return module, sha(raw)


# ---- bind-time input files (the release, the policy, the override): read here, hashed here, never typed
def load_inputs(params, base, allowed):
    items = params.get('inputs', {})
    need(type(items) is dict and len(items) <= max(8, len(allowed)) and all(type(name) is str and name in allowed and type(path) is str for name, path in items.items()),
         'BIND_INPUTS_INVALID')
    inputs = {}
    for name, path in sorted(items.items()):
        path = Path(path)
        inputs[name] = read_file(path if path.is_absolute() else base / path, 65536, 'BIND_INPUT_UNREADABLE')
    return inputs


def supervisor_unit_record(ctx, spec, pointer):
    """The exact five-field K5 record projected only from a proved L6 GATE observation.
    No caller path, identity or field map is accepted; provenance re-runs this derivation.
    """
    code = 'SUPERVISOR_UNIT_RECORD_INVALID'
    operation = ctx.get('operation', getattr(ctx.get('source'), 'OPERATION', None))
    mode = ctx.get('plan_mode', ctx.get('plan', {}).get('mode'))
    need(operation == 'GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01' and mode in ('ACTIVATE','RESET'), code)
    need(type(spec) is dict and set(spec) == {'evidence','kind'} and spec.get('evidence') == 'READBACK'
         and spec.get('kind') in ('service','timer') and pointer == '/units/' + spec['kind'], code)
    kind, role = spec['kind'], spec['evidence']
    name = {'service':'c3po-massive.service','timer':'c3po-massive.timer'}[kind]
    operations = ctx.get('operations', {entry['role']:entry['operation'] for entry in ctx.get('entries',[])})
    receipt = ctx.get('receipts',{}).get(role)
    facts = [entry for entry in ctx.get('evidence_facts',[]) if entry.get('role') == role]
    blob = ctx.get('blobs',{}).get(role)
    need(operations.get(role) == READBACK_OPERATION and type(receipt) is dict and len(facts) == 1
         and facts[0].get('complete') is True and facts[0].get('source') == 'BOUND_SET'
         and facts[0].get('operation') == READBACK_OPERATION
         and facts[0].get('receipt_sha256') == receipt.get('metadata_sha256')
         and facts[0].get('receipt_host_binding_is_the_one_of_this_set') is True
         and facts[0].get('receipt_payload_is_the_sealed_source_of_that_operation') is True
         and facts[0].get('exit_json_binds_these_bytes') is True and type(facts[0].get('bound_set')) is dict
         and facts[0]['bound_set'].get('stderr_empty') is True
         and facts[0]['bound_set'].get('exit_json_binds_config_request_go_and_output') is True
         and type(blob) is dict and blob.get('source') == 'bound', 'SUPERVISOR_UNIT_RECORD_NOT_BOUND_COMPLETE')
    need(receipt.get('schema') == 'READONLY_HOSTOPS_READBACK_RECEIPT_V1'
         and receipt.get('operation') == READBACK_OPERATION and receipt.get('mode') == 'GATE'
         and receipt.get('status') == RECEIPT_STATUS['KNOWN_COMPLETE']
         and receipt.get('outcome') == 'READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
         and receipt.get('expectations_met') is True and receipt.get('code') is None
         and receipt.get('findings') == [] and receipt.get('items_not_complete') == []
         and is_hash(receipt.get('metadata_sha256')), 'SUPERVISOR_UNIT_RECORD_NOT_BOUND_COMPLETE')
    body = dict(receipt);claimed = body.pop('metadata_sha256')
    need(sha(canonical(body)) == claimed, 'SUPERVISOR_UNIT_RECORD_RECEIPT_SEAL')
    boot = at(receipt, '/effects/evidence_boot_id_sha256')
    observed_boot = at(receipt, '/items/boot')
    need(is_hash(boot) and type(observed_boot) is dict
         and observed_boot.get('status') == 'COMPLETE' and observed_boot.get('matches') is True
         and observed_boot.get('findings') == [] and observed_boot.get('device_numbers_compared') is True
         and observed_boot.get('boot_id_sha256') == boot
         and observed_boot.get('evidence_boot_id_sha256') == boot, 'SUPERVISOR_UNIT_RECORD_BOOT_UNKNOWN')
    if 'plan' in ctx:
        need(boot == ctx['plan'].get('evidence_boot_id_sha256'), 'EVIDENCE_NOT_OF_THE_SAME_BOOT')
        need(ctx['plan'].get('mode') == mode, code)
    try:observed = datetime.fromisoformat(receipt.get('observed_at'))
    except (TypeError,ValueError):raise Refused('SUPERVISOR_UNIT_RECORD_CLOCK_INVALID') from None
    need(observed.tzinfo is not None, 'SUPERVISOR_UNIT_RECORD_CLOCK_INVALID')
    if 'window' in ctx:
        need(observed <= ctx['window']['start'], 'SUPERVISOR_UNIT_RECORD_PREDECESSOR_NOT_FINISHED')
    units = at(receipt, '/items/units')
    need(type(units) is dict and units.get('status') == 'COMPLETE' and units.get('matches') is True
         and units.get('findings') == [] and units.get('unit_directory_equal_signed') is True, code)
    files = units.get('files')
    need(type(files) is dict and set(files) == {'c3po-massive.service','c3po-massive.timer'}, code)
    item = files[name]
    need(type(item) is dict and set(item) == {'bytes','bytes_equal_signed_render','device','exists','gid',
         'identity_equal_install_receipt','inode','links','mode_octal','sha256','sha256_signed','size','type','uid'}
         and item.get('exists') is True and item.get('type') == 'file'
         and item.get('mode_octal') == '0644' and item.get('bytes_equal_signed_render') is True
         and item.get('identity_equal_install_receipt') is True and is_hash(item.get('sha256'))
         and item.get('sha256') == item.get('sha256_signed')
         and all(type(item.get(key)) is int and item[key] >= (1 if key in ('inode','bytes','size','links') else 0)
                 for key in ('device','inode','uid','gid','bytes','size','links'))
         and item['uid'] == item['gid'] == 0 and item['links'] == 1
         and item['bytes'] == item['size'] and item['bytes'] <= 65536, code)
    return {'name':name, 'sha256':item['sha256'], 'bytes':item['bytes'], 'device':item['device'], 'inode':item['inode']}


def supervisor_unit_record_provenance(ctx, entry):
    need(type(entry) is dict and set(entry) == {'plan_pointer','evidence_role','receipt_pointer',
         'receipt_transformation','supervisor_unit_kind'}
         and entry.get('receipt_transformation') == 'SUPERVISOR_UNIT_RECORD_V1'
         and entry.get('supervisor_unit_kind') in ('service','timer'), 'SUPERVISOR_UNIT_RECORD_INVALID')
    kind = entry['supervisor_unit_kind'];name = {'service':'c3po-massive.service','timer':'c3po-massive.timer'}[kind]
    need(entry['receipt_pointer'] == '/items/units/files/' + name, 'SUPERVISOR_UNIT_RECORD_INVALID')
    return supervisor_unit_record(ctx, {'evidence':entry['evidence_role'],'kind':kind}, entry['plan_pointer'])


def created_directory_chain(ctx, spec, pointer):
    """An exact CREATED_DURABLE leaf appended to its own proved parent chain.
    M1 release, M3 policy and K4 LAUNCHER each have one fixed producer, source shape and destination.
    The marker names only a cited role and fixed kind, never a path, key, mode or host identity.
    load_evidence must already have verified the BOUND bytes against their accepted family.
    Re-run this derivation for metadata provenance; no trust in a transformation tag alone.
    """
    code = 'CREATED_DIRECTORY_CHAIN_INVALID'
    operation = ctx.get('operation', getattr(ctx.get('source'), 'OPERATION', None))
    mode = ctx.get('plan_mode', ctx.get('plan', {}).get('mode'))
    need(type(spec) is dict and set(spec) == {'evidence', 'kind'} and type(spec['evidence']) is str
         and spec['kind'] in ('policy', 'release', 'launcher'), code)
    kind, role = spec['kind'], spec['evidence']
    destinations = {}
    if operation == BOOTSTRAP_OPERATION or (operation == K9R_OPERATION and mode == 'POLICY'):
        destinations = {'policy':'/policy_read/policy/directory/rows', 'release':'/policy_read/release/directory/rows'}
    elif operation == 'GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01' and mode in ('MOUNT','ENABLE','DISABLE_FAST','DISABLE_FULL'):
        destinations = {'policy':'/override/directory'}
    elif operation == 'GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01' and mode in ('ACTIVATE','RESTART'):
        destinations = {'release':'/release_rows', 'launcher':'/launcher_rows'}
    need(kind in destinations and pointer == destinations[kind], code)
    definitions = {
        'release': (RELEASE_OPERATION, 'WRITE_HOSTOPS02_INSTALL_RELEASE_RECEIPT_V1', RELEASE_INSTALLED_OUTCOME,
                    '/parent', '/effects/parent', 'RELEASE_DIRECTORY',
                    K9_DATA_VOLUME + '/r2d2-v2-release-20261005'),
        'policy': (ACTIVATE_OPERATION, 'WRITE_HOSTOPS02_ACTIVATE_RECEIPT_V1', 'ACTIVATE_WORKER_RECREATED_AND_VERIFIED',
                   '/chains/LIVE_PARENT', '/effects/live_parent', 'DIRECTORY',
                   K9_DATA_VOLUME + '/r2d2-v2-live/2026-10-05'),
        'launcher': ('GO_WRITE_HOSTOPS02_K4_FILES_01', 'WRITE_HOSTOPS02_K4_FILES_RECEIPT_V1', 'K4_FILES_DELIVERED_READ_BACK',
                     '/parent/reader', '/effects/reader_parent', 'LAUNCHER_DIRECTORY', '/etc/c3po-reader/launcher')}
    producer, schema, outcome, parent_pointer, parent_effect_pointer, directory_key, path = definitions[kind]
    operations = ctx.get('operations', {entry['role']: entry['operation'] for entry in ctx.get('entries', [])})
    receipt = ctx.get('receipts', {}).get(role)
    facts = [entry for entry in ctx.get('evidence_facts', []) if entry.get('role') == role]
    blob = ctx.get('blobs', {}).get(role)
    need(operations.get(role) == producer and type(receipt) is dict and len(facts) == 1
         and facts[0].get('complete') is True and facts[0].get('source') == 'BOUND_SET'
         and facts[0].get('operation') == producer and facts[0].get('receipt_sha256') == receipt.get('metadata_sha256')
         and facts[0].get('receipt_host_binding_is_the_one_of_this_set') is True
         and facts[0].get('receipt_payload_is_the_sealed_source_of_that_operation') is True
         and facts[0].get('exit_json_binds_these_bytes') is True and type(facts[0].get('bound_set')) is dict
         and facts[0]['bound_set'].get('stderr_empty') is True
         and facts[0]['bound_set'].get('exit_json_binds_config_request_go_and_output') is True
         and type(blob) is dict and blob.get('source') == 'bound', 'CREATED_DIRECTORY_CHAIN_NOT_BOUND_COMPLETE')
    need(receipt.get('operation') == producer and receipt.get('schema') == schema and receipt.get('outcome') == outcome
         and receipt.get('status') == RECEIPT_STATUS['KNOWN_COMPLETE'] and is_hash(receipt.get('metadata_sha256')),
         'CREATED_DIRECTORY_CHAIN_NOT_BOUND_COMPLETE')
    body = dict(receipt); claimed = body.pop('metadata_sha256')
    need(sha(canonical(body)) == claimed, 'CREATED_DIRECTORY_CHAIN_RECEIPT_SEAL')
    boot = receipt_boot(receipt)
    need(is_hash(boot), 'CREATED_DIRECTORY_CHAIN_BOOT_UNKNOWN')
    if 'plan' in ctx:
        need(boot == ctx['plan'].get('evidence_boot_id_sha256'), 'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    start, end = bootstrap_clock(receipt)
    need(type(at(receipt, '/clock/monotonic_elapsed_ms')) is int and at(receipt, '/clock/monotonic_elapsed_ms') >= 0,
         'CREATED_DIRECTORY_CHAIN_CLOCK_INVALID')
    if 'window' in ctx:
        need(end <= ctx['window']['start'], 'CREATED_DIRECTORY_CHAIN_PREDECESSOR_NOT_FINISHED')
    parents = pointer_value(receipt, parent_pointer)
    parent = pointer_value(receipt, parent_effect_pointer)
    expected_paths = (['/', '/etc', '/etc/c3po-reader'] if kind == 'launcher' else
                      ['/', '/mnt', K9_DATA_VOLUME] + ([K9_DATA_VOLUME + '/r2d2-v2-live'] if kind == 'policy' else []))
    need(type(parents) is list and len(parents) == len(expected_paths), code)
    for row, expected in zip(parents, expected_paths):
        need(type(row) is dict and set(row) == {'path', 'device', 'inode', 'uid', 'gid', 'mode'} and row['path'] == expected
             and all(type(row[key]) is int and row[key] >= (1 if key == 'inode' else 0) for key in ('device', 'inode', 'uid', 'gid', 'mode'))
             and row['mode'] <= 0o7777 and not row['mode'] & 0o002
             and (expected == K9_DATA_VOLUME or (row['uid'] == row['gid'] == 0 and not row['mode'] & 0o022)), code)
    need(type(parent) is dict and parent.get('path') == expected_paths[-1]
         and canonical(parent.get('row')) == canonical(parents[-1])
         and parent.get('chain_sha256') == sha(canonical(parents)), code)
    if kind == 'launcher':
        need(at(receipt, '/effects/mode') == 'LAUNCHER' and at(receipt, '/effects/epoch') == K9_EPOCH
             and at(receipt, '/delivered/mode') == 'LAUNCHER' and at(receipt, '/delivered/epoch') == K9_EPOCH
             and receipt.get('readback') == 'COMPLETE', code)
        expected_directory = {'path':path, 'mode_octal':'0700', 'uid':0, 'gid':0, 'expect':'ABSENT', 'entries_after':1}
        need(canonical(at(receipt, '/effects/directories')) == canonical([expected_directory]), code)
    else:
        directory = at(receipt, '/effects/directory')
        expected_directory = {'path': path, 'mode_octal': '0700', 'expect': 'ABSENT'}
        if kind == 'release':expected_directory.update(uid=0, gid=0)
        need(canonical(directory) == canonical(expected_directory), code)
    records = receipt.get('directories')
    need(type(records) is list and len(records) == 1, code)
    record = records[0]
    need(type(record) is dict and set(record) == {'key','path','state','code','errno','observed','fsync_directory','fsync_parent'}
         and record['key'] == directory_key and record['path'] == path and record['state'] == 'CREATED_DURABLE'
         and record['code'] is None and record['errno'] is None
         and record['fsync_directory'] is True and record['fsync_parent'] is True, code)
    observed = record['observed']
    need(type(observed) is dict and set(observed) == {'device','inode','uid','gid','type','mode_octal','entries'}
         and observed.get('type') == 'dir' and observed.get('mode_octal') == '0700'
         and type(observed.get('entries')) is int and observed['entries'] == 0
         and all(type(observed.get(key)) is int and observed[key] >= (1 if key == 'inode' else 0) for key in ('device','inode','uid','gid'))
         and observed['uid'] == observed['gid'] == 0 and observed['device'] == parents[-1]['device']
         and observed['inode'] != parents[-1]['inode'], code)
    leaf = {'path': path, 'mode': int(observed['mode_octal'], 8)}
    leaf.update({key: observed[key] for key in ('device','inode','uid','gid')})
    return json.loads(json.dumps(parents)) + [leaf]


def created_directory_chain_provenance(ctx, entry):
    """Only the exact whole-list operator record can claim the derived directory chain."""
    need(type(entry) is dict and set(entry) == {'plan_pointer','evidence_role','receipt_pointer',
         'receipt_transformation','created_directory_kind'}
         and entry.get('receipt_transformation') == 'CREATED_DIRECTORY_CHAIN_V1'
         and entry.get('created_directory_kind') in ('policy','release','launcher'), 'CREATED_DIRECTORY_CHAIN_INVALID')
    kind = entry['created_directory_kind']
    need(entry['receipt_pointer'] == {'release':'/parent','policy':'/chains/LIVE_PARENT','launcher':'/parent/reader'}[kind],
         'CREATED_DIRECTORY_CHAIN_INVALID')
    return created_directory_chain(ctx, {'evidence':entry['evidence_role'], 'kind':kind}, entry['plan_pointer'])


def resolve_hostops02(value, ctx, pointer=''):
    """The markers a HOSTOPS02 plan may carry besides {"$from": ...} (which resolve_references replaces afterwards), each
    replaced by command, never typed:
      {"$input": NAME, "as": "b64"|"sha256"|"bytes"}        the bytes of the input file NAME, their hash, their size
      {"$input": NAME, "as": "member", "member": KEY}       a top-level member of that file's JSON (a release's revision)
      {"$source": NAME}                                     a constant of the operation's sealed source (a pinned hash, a path)
      {"$ledger_row": {"evidence": ROLE, "path": P, "key": K}}   the six-key row of the directory P that a cited provision
                                                            receipt created (state CREATED_DURABLE, ledger key K)
      {"$concat": [ITEM, ...]}                              the lists ITEM (each resolved) joined: rows from "/" to a leaf"""
    inputs, used, copied = ctx['inputs'], ctx['used'], ctx['copied']
    if type(value) is dict and '$supervisor_unit_record' in value:
        need(set(value) == {'$supervisor_unit_record'}, 'SUPERVISOR_UNIT_RECORD_INVALID')
        spec = value['$supervisor_unit_record'];record = supervisor_unit_record(ctx, spec, pointer)
        copied.append({'plan_pointer':pointer, 'evidence_role':spec['evidence'],
                       'receipt_pointer':'/items/units/files/' + record['name'],
                       'receipt_transformation':'SUPERVISOR_UNIT_RECORD_V1', 'supervisor_unit_kind':spec['kind']})
        return record
    if type(value) is dict and '$created_directory_chain' in value:
        need(set(value) == {'$created_directory_chain'}, 'CREATED_DIRECTORY_CHAIN_INVALID')
        spec = value['$created_directory_chain']
        rows = created_directory_chain(ctx, spec, pointer)
        copied.append({'plan_pointer':pointer, 'evidence_role':spec['evidence'],
                       'receipt_pointer':{'release':'/parent','policy':'/chains/LIVE_PARENT','launcher':'/parent/reader'}[spec['kind']],
                       'receipt_transformation':'CREATED_DIRECTORY_CHAIN_V1', 'created_directory_kind':spec['kind']})
        return rows
    if type(value) is dict and '$bootstrap_source_rows' in value:
        spec=value['$bootstrap_source_rows'];operation=getattr(ctx['source'],'OPERATION',None)
        bootstrap_cited=any(r.get('operation')==BOOTSTRAP_OPERATION for r in ctx['receipts'].values())
        need(operation==BOOTSTRAP_OPERATION or (operation==K3K9_OPERATION and bootstrap_cited),
             'BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID')
        need(set(value)=={'$bootstrap_source_rows'} and type(spec) is dict and set(spec)=={'evidence','receipt_pointer'}
             and spec.get('evidence')=='TREE_PRE' and spec.get('receipt_pointer')=='/items/september_sources/components'
             and ctx['operations'].get('TREE_PRE')==K9R_OPERATION and pointer=='/source_rows',
             'BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID')
        receipt=ctx['receipts'].get('TREE_PRE',{})
        need(receipt.get('mode')=='TREE' and at(receipt,'/items/september_sources/status')=='COMPLETE'
             and at(receipt,'/items/september_sources/matches') is True and at(receipt,'/items/september_sources/findings')==[],
             'BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID')
        rows=bootstrap_source_rows(pointer_value(receipt,spec['receipt_pointer']))
        copied.append({'plan_pointer':pointer,'evidence_role':'TREE_PRE','receipt_pointer':spec['receipt_pointer'],
                       'receipt_transformation':'BOOTSTRAP_SOURCE_ROWS_V1'})
        return rows
    if type(value) is dict and '$input' in value:
        need(set(value) in ({'$input', 'as'}, {'$input', 'as', 'member'}) and value['$input'] in inputs
             and (value['as'] in INPUT_FORMS if 'member' not in value else value['as'] == 'member' and type(value['member']) is str), 'PLAN_INPUT_INVALID')
        raw = inputs[value['$input']]
        used.append({'plan_pointer': pointer or '/', 'input': value['$input'], 'as': value['as']})
        if value['as'] == 'member':
            body = strict_json(raw, 'PLAN_INPUT_INVALID')
            need(type(body) is dict and value['member'] in body and type(body[value['member']]) in (str, int), 'PLAN_INPUT_INVALID')
            return body[value['member']]
        return base64.b64encode(raw).decode('ascii') if value['as'] == 'b64' else sha(raw) if value['as'] == 'sha256' else len(raw)
    if type(value) is dict and '$source' in value:
        name = value['$source']
        need(set(value) == {'$source'} and type(name) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,63}', name)
             and type(getattr(ctx['source'], name, None)) in (str, int), 'PLAN_REFERENCE_INVALID')
        copied.append({'plan_pointer': pointer or '/', 'source_constant': name})
        return getattr(ctx['source'], name)
    if type(value) is dict and '$ledger_row' in value:
        spec = value['$ledger_row']
        need(set(value) == {'$ledger_row'} and type(spec) is dict and set(spec) == {'evidence', 'path', 'key'}
             and all(type(item) is str for item in spec.values()) and spec['evidence'] in ctx['receipts']
             and ctx['operations'].get(spec['evidence']) == PROVISION_OPERATION, 'PLAN_REFERENCE_INVALID')
        copied.append({'plan_pointer': pointer or '/', 'evidence_role': spec['evidence'], 'receipt_ledger_row': {'path': spec['path'], 'key': spec['key']}})
        return ledger_rows([(spec['evidence'], ctx['receipts'][spec['evidence']])], spec['path'], spec['key'])
    if type(value) is dict and '$concat' in value:
        need(set(value) == {'$concat'} and type(value['$concat']) is list and value['$concat'], 'PLAN_REFERENCE_INVALID')
        joined = []
        for index, item in enumerate(value['$concat']):
            origin = pointer + '/$concat/%d' % index
            first = len(copied)
            part = resolve_references(resolve_hostops02(item, ctx, origin), ctx['receipts'], copied, origin)
            need(type(part) is list, 'PLAN_REFERENCE_INVALID')
            additions = copied[first:]
            del copied[first:]
            offset = len(joined)
            for entry in additions:
                declared = entry.get('plan_pointer','')
                if declared == origin and type(entry.get('receipt_pointer')) is str:
                    for position in range(len(part)):
                        copied.append(dict(entry, plan_pointer=pointer+'/'+str(offset+position),
                                           receipt_pointer=entry['receipt_pointer']+'/'+str(position)))
                else:
                    prefix = origin+'/'
                    need(declared.startswith(prefix), 'PLAN_REFERENCE_INVALID')
                    suffix = declared[len(prefix):]
                    head, separator, tail = suffix.partition('/')
                    need(head.isdigit() and int(head)<len(part), 'PLAN_REFERENCE_INVALID')
                    copied.append(dict(entry, plan_pointer=pointer+'/'+str(offset+int(head))+(separator+tail if separator else '')))
            joined.extend(part)
        return joined
    if type(value) is dict:
        return {key: resolve_hostops02(item, ctx, pointer + '/' + key) for key, item in value.items()}
    if type(value) is list:
        return [resolve_hostops02(item, ctx, pointer + '/' + str(index)) for index, item in enumerate(value)]
    return value


def required_inputs(used, required):
    """Every member that holds input bytes, a hash or a size must have been taken from its input file, and every input file
    given must have been used."""
    taken = {(item['plan_pointer'], item['input'], item['as']) for item in used}
    need(all((pointer, name, form) in taken for pointer, (name, form) in required.items()), 'PLAN_MEMBER_NOT_FROM_ITS_INPUT_FILE')


def input_members(operation, plan):
    """{plan pointer: (input, form)} of the members a request of this operation takes from its input files."""
    def member(prefix, name, forms):
        return {prefix + '/' + key: (name, form) for key, form in forms}
    if operation == 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01':
        files = plan.get('files')
        need(type(files) is dict and len(files) <= 12, 'PLAN_DELIVERY_INPUTS_INVALID')
        forms = (('content_b64', 'b64'), ('sha256', 'sha256'), ('bytes', 'bytes'))
        found = member('/contract', 'k8_contract', forms)
        for index, key in enumerate(sorted(files)):
            need(type(key) is str and '/' not in key and '~' not in key, 'PLAN_DELIVERY_INPUTS_INVALID')
            found.update(member('/files/' + key, 'k8_file_%02d' % index, forms))
        return found
    if operation == 'GO_WRITE_HOSTOPS02_K4_FILES_01':
        kind = {'CHAIN_STATIC':'static_config','LAUNCHER':'launcher'}.get(plan.get('mode'))
        return member('/delivery/'+kind,'k4_'+kind,(('content_b64','b64'),('sha256','sha256'),('bytes','bytes'))) if kind else {}
    if operation in ('GO_WRITE_HOSTOPS02_K12_PREFLIGHT_01','GO_WRITE_HOSTOPS02_K12_WINDOW_01','GO_READONLY_HOSTOPS02_K12_COLLECT_01') and plan.get('capacity_request') is not None:
        return member('/capacity_request','k12_request',(('b64','b64'),('sha256','sha256')))
    if operation == RELEASE_OPERATION:
        return member('/release', 'release', (('content_b64', 'b64'), ('sha256', 'sha256'), ('bytes', 'bytes')))
    if operation == ACTIVATE_OPERATION:
        return dict(member('/policy', 'policy', (('content_b64', 'b64'), ('sha256', 'sha256'), ('bytes', 'bytes'))),
                    **member('/release', 'release', (('sha256', 'sha256'), ('bytes', 'bytes'))))
    if operation == EPOCH_READBACK_OPERATION:
        found = member('/release', 'release', (('sha256', 'sha256'), ('bytes', 'bytes')) + ((('content_b64', 'b64'),) if plan.get('mode') == 'PRE' else ()))
        if plan.get('policy') is not None:
            found.update(member('/policy', 'policy', (('content_b64', 'b64'), ('sha256', 'sha256'), ('bytes', 'bytes'))))
        if plan.get('render') is not None:
            found.update(member('/render', 'override', (('override_b64', 'b64'), ('override_sha256', 'sha256'), ('override_bytes', 'bytes'))))
        return found
    if operation == 'GO_WRITE_HOSTOPS02_K4_E0_01':          # rev 4: the runner file, read by the binder
        return member('/runner', 'runner', (('content_b64', 'b64'), ('sha256', 'sha256'), ('bytes', 'bytes')))
    return {}


def bind_inputs_in_request(operation, plan, effects=None):
    """{input: {sha256, bytes}} as the bound request carries them (what the owner is shown is derived again from it); for K6a
    the override, which the request does not carry, as its effects state the bytes the source derives and writes."""
    found = {}
    for pointer, (name, form) in input_members(operation, plan).items():
        if form in ('sha256', 'bytes'):
            found.setdefault(name, {})[form] = pointer_value(plan, pointer)
    if 'k12_request' in found:
        try:found['k12_request']['bytes'] = len(base64.b64decode(plan['capacity_request']['b64'],validate=True))
        except Exception:raise Refused('K12_CAPACITY_REQUEST_INVALID') from None
    if operation == ACTIVATE_OPERATION:
        rows = [item for item in (effects or {}).get('files', []) if type(item) is dict and item.get('key') == 'OVERRIDE']
        found['override'] = {'sha256': rows[0].get('sha256'), 'bytes': rows[0].get('bytes')} if len(rows) == 1 else None
    return found


# ---- reading cited receipts
def cited(ctx, operation):
    return [(entry['role'], ctx['receipts'][entry['role']]) for entry in ctx['entries'] if entry['operation'] == operation]


def complete_role(ctx, role):
    facts = [fact for fact in ctx['evidence_facts'] if fact.get('role') == role]
    return len(facts) == 1 and facts[0].get('complete') is True


def at(receipt, pointer):
    value = pointer_value(receipt, pointer)
    return None if value is MISSING else value


def ledger_rows(provisions, path, key):
    """The six-key row of a directory a cited HOSTOPS01 provision receipt CREATED (state CREATED_DURABLE), by its path and
    key: exactly one such row among the cited provision receipts (CONTRACT K2a section 4)."""
    rows = []
    for _, receipt in provisions:
        for entry in receipt.get('ledger') if type(receipt.get('ledger')) is list else []:
            observed = entry.get('observed') if type(entry) is dict else None
            if (type(observed) is dict and entry.get('path') == path and entry.get('key') == key and entry.get('state') == 'CREATED_DURABLE'
                    and observed.get('type') == 'dir' and type(observed.get('mode_octal')) is str and re.fullmatch('0[0-7]{3}', observed['mode_octal'])):
                rows.append({'path': path, 'device': observed.get('device'), 'inode': observed.get('inode'), 'uid': observed.get('uid'),
                             'gid': observed.get('gid'), 'mode': int(observed['mode_octal'], 8)})
    need(len(rows) == 1, 'PROVISION_LEDGER_ROW_NOT_FOUND')
    return rows[0]


def boot_of(operation, receipt):
    """The boot a cited receipt speaks of: a precheck's own reading, or the evidence boot an operation signed and ran in."""
    if operation == PRECHECK_OPERATION:
        return at(receipt, BOOT_POINTER)
    if operation in (PROVISION_OPERATION, INSTALL_OPERATION, CATALOG_OPERATION, RELEASE_OPERATION, EPOCH_READBACK_OPERATION, ACTIVATE_OPERATION):
        return at(receipt, '/effects/evidence_boot_id_sha256')
    return None


def full_pre(receipt, complete):
    """A K11 receipt that is the full dry run of Monday (CONTRACT K11 section 6, M2p)."""
    return (complete and receipt.get('outcome') == PRE_FULL_OUTCOME and receipt.get('mode') == 'PRE' and receipt.get('dry_run') == 'FULL'
            and at(receipt, '/effects/rehearses_install_release_and_activate') is True)


# ---- the rules of each operation's contract that the binder applies before the owner is asked
def catalog_rules(ctx):
    """K2a CONTRACT sections 4 and 5 (steps 1 and 2): every row of the three chains is the cited receipts' row, the first
    rows from the precheck's chains VAR_LIB and ETC, the last two from the provision ledger (CREATED_DURABLE); both
    receipts of the same boot; the provision's retention tag on the signed image ID. Image ID, image revision and boot are
    PLAN_SOURCES rows (the revision against the precheck's reading of the image label)."""
    plan, m = ctx['plan'], ctx['rt']['source']
    prechecks, provisions = cited(ctx, PRECHECK_OPERATION), cited(ctx, PROVISION_OPERATION)
    need(len(prechecks) == 1 and provisions and all(complete_role(ctx, role) for role, _ in prechecks + provisions), 'CATALOG_EVIDENCE_INCOMPLETE')
    precheck = prechecks[0][1]
    need(all(at(receipt, '/effects/evidence_boot_id_sha256') == plan['evidence_boot_id_sha256'] for _, receipt in provisions), 'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    tags = [receipt['retention_tag'] for _, receipt in provisions if type(receipt.get('retention_tag')) is dict]
    need(tags and all(tag.get('image_id') == plan['image_id'] and tag.get('state') in ('CREATED_VERIFIED', 'PRESENT_VERIFIED_NOT_TOUCHED') for tag in tags),
         'RETENTION_TAG_NOT_THE_SIGNED_IMAGE')
    var_lib, etc = at(precheck, '/items/chains/VAR_LIB/rows'), at(precheck, '/items/chains/ETC/rows')
    need(type(var_lib) is list and type(etc) is list, 'CATALOG_CHAIN_NOT_THE_RECEIPTS_ROWS')
    config_parent = m.UNIT_DOCKER_CONFIG.rsplit('/', 1)[0]
    docker = etc + [ledger_rows(provisions, config_parent, 'SUP_CONFIG'), ledger_rows(provisions, m.UNIT_DOCKER_CONFIG, 'SUP_DOCKER_CLI')]
    rows = plan['journal_chain'] if plan['mode'] == 'REAL' else plan['reference_chain']
    journal = var_lib + [ledger_rows(provisions, m.JOURNAL_PARENT, 'SUP_STATE_PARENT'), ledger_rows(provisions, rows[-1]['path'], 'SUP_JOURNAL')]
    need(canonical(plan['docker_config_chain']) == canonical(docker) and canonical(rows) == canonical(journal)
         and (plan['mode'] == 'REAL' or canonical(plan['journal_chain']) == canonical(var_lib)), 'CATALOG_CHAIN_NOT_THE_RECEIPTS_ROWS')
    release = release_tree_of(ctx) if 'release_tree' in ctx['params'] else None
    need(release is not None or ctx['mode'] == REHEARSAL, 'RELEASE_TREE_REQUIRED')
    need('rehearsal' not in ctx['params'] or plan['mode'] == 'REAL', 'PARAMETERS_INVALID')
    rehearsal = rehearsal_at_prepare(ctx) if 'rehearsal' in ctx['params'] else None
    return {'release_tree': release, 'rows_from_the_precheck': {'VAR_LIB': len(var_lib), 'ETC': len(etc)}, 'rows_from_the_provision_ledger': 4,
            'retention_tag_on_the_signed_image': True, 'precheck_observed_at': precheck.get('observed_at'),
            'plan_mode': plan['mode'], 'rehearsal_receipt': rehearsal,
            'dispatch_gates': ['K2A_REHEARSAL_RECEIPT_OF_THESE_BYTES', 'K2A_GRID_READ_PIN_NO_REBOOT'] if plan['mode'] == 'REAL' else []}


def k2a_rehearsal_checks(receipt, fact, family_seal, plan):
    """What the rehearsal receipt of A6 must show for the REAL request A9 (K2a CONTRACT 5 step 1 and 6: "the same bytes,
    argv, script, image and engine"): these bytes (the seal), the REHEARSAL mode, complete, the docker CLI's directory
    counted empty after the reads and after the run, the same boot, the same image ID and revision, the same pinned script
    and the same container path of the journal pair. {name: ok}."""
    return {'OF_THESE_BYTES': fact.get('family') == family_seal, 'MODE_REHEARSAL': receipt.get('mode') == 'REHEARSAL',
            'COMPLETE': fact['complete'] is True and receipt.get('outcome') == REHEARSAL_CATALOG_OUTCOME,
            'DOCKER_CONFIG_EMPTY_AFTER_THE_READS': at(receipt, '/precheck/docker_config_entries_after_the_reads') == 0,
            'DOCKER_CONFIG_EMPTY_AFTER_THE_RUN': at(receipt, '/docker_config/entries_after') == 0,
            'SAME_BOOT': at(receipt, '/effects/evidence_boot_id_sha256') == plan['evidence_boot_id_sha256'],
            'SAME_IMAGE': (at(receipt, '/effects/container/image_id'), at(receipt, '/effects/container/image_revision')) == (plan['image_id'], plan['image_revision']),
            'SAME_SCRIPT': at(receipt, '/effects/container/standard_input/sha256') == plan['script_sha256'],
            'SAME_CONTAINER_PATH': at(receipt, '/effects/container/bind/target') == plan['container_journal_root']}


def rehearsal_at_prepare(ctx):
    """K2a CONTRACT 5 step 1 puts the rehearsal receipt of these bytes BEFORE the signature of the REAL request. When A6 has
    run, the request names its set ("rehearsal": {"bound": ...}) and the owner is shown its result; when it has not, the
    question says that the receipt is a gate of the dispatch only (the plan signs A6 and A9 at one sitting). Never in
    request.evidence: it is never the 4b receipt."""
    item = ctx['params']['rehearsal']
    need(type(item) is dict and set(item) <= {'bound', 'receipt_file', 'family'} and len(set(item) & {'bound', 'receipt_file'}) == 1, 'PARAMETERS_INVALID')
    entries, receipts, facts = load_evidence([dict(item, role='A6_REHEARSAL', operation=CATALOG_OPERATION, accept_not_complete=True)], ctx['base'],
                                             ctx['mode'], ctx['host'], ctx['family'], ctx['seal'], ctx['seals'], {})
    checks = k2a_rehearsal_checks(receipts['A6_REHEARSAL'], facts[0], ctx['seal'], ctx['plan'])
    need(all(checks.values()), 'REHEARSAL_RECEIPT_NOT_THE_ONE_A9_NEEDS')
    return {'receipt_sha256': entries[0]['receipt_sha256'], 'outcome': receipts['A6_REHEARSAL'].get('outcome'), 'checks': sorted(checks),
            'source': facts[0]['source']}


README_COMMAND_PLACEHOLDERS = ('<HOST_JOURNAL_ROOT>', '<CONTAINER_JOURNAL_ROOT>', '<IMAGE_ID>', '$epoch')


def readme_command(text):
    """The command block of the supervisor README, "Catalog initialisation" (lines 336 to 339 at dd4ec4bb): the one fenced
    block holding "docker run", from that line through its continuation lines, split as the shell splits it. Returns
    (environment words, docker arguments, standard input words)."""
    blocks = re.findall(r'^```[a-z]*\n(.*?)^```$', text, re.S | re.M)
    found = [block for block in blocks if ' docker run ' in block]
    need(len(found) == 1, 'README_COMMAND_NOT_FOUND')
    lines = found[0].split('\n')
    start = [index for index, line in enumerate(lines) if ' docker run ' in line]
    need(len(start) == 1, 'README_COMMAND_NOT_FOUND')
    joined, index = [], start[0]
    while True:
        line = lines[index]
        joined.append(line[:-1] if line.endswith('\\') else line)
        if not line.endswith('\\'):
            break
        index += 1
        need(index < len(lines), 'README_COMMAND_NOT_FOUND')
    try:
        words = shlex.split(' '.join(joined))
    except ValueError:
        raise Refused('README_COMMAND_NOT_FOUND')
    need('docker' in words and '<' in words, 'README_COMMAND_NOT_FOUND')
    docker, redirect = words.index('docker'), words.index('<')
    need(docker < redirect, 'README_COMMAND_NOT_FOUND')
    return words[:docker], words[docker + 1:redirect], words[redirect + 1:]


def readme_argv_is_the_effects(readme, effects, mode):
    """K2a CONTRACT 5 step 4, by command: container.docker_arguments is the README's command word for word, its four
    placeholders replaced by the signed journal root, container path, image ID and epoch; DOCKER_CONFIG and the script on
    standard input as the README writes them."""
    try:
        environment, arguments, stdin = readme_command(readme.decode('utf-8'))
    except UnicodeDecodeError:
        raise Refused('README_COMMAND_NOT_FOUND')
    container = effects['container']
    values = {'<HOST_JOURNAL_ROOT>': container['bind']['source'], '<CONTAINER_JOURNAL_ROOT>': container['bind']['target'],
              '<IMAGE_ID>': container['image_id'], '$epoch': effects['epoch']}
    expected = []
    for word in arguments:
        for name, value in values.items():
            word = word.replace(name, value)
        expected.append(word)
    need(expected == list(container['docker_arguments']), 'DOCKER_ARGUMENTS_NOT_THE_READMES')
    need(environment == ['DOCKER_CONFIG=<HOST_CONFIG_DIR>/docker-cli'] and stdin == ['catalog-init.py']
         and (mode != 'REAL' or container['docker_config_variable'].endswith('/docker-cli')), 'DOCKER_ARGUMENTS_NOT_THE_READMES')
    return {'words': len(expected), 'placeholders_replaced': list(README_COMMAND_PLACEHOLDERS)}


def release_tree_of(ctx):
    """K2a CONTRACT 5, steps 2 and 4, by command against a tree of the release (dd4ec4bb): the script the plan signs is the
    lines between the two catalog-init-script markers of the supervisor README; in REAL the epoch is the EPOCH line of the
    release's epoch assembler; the docker arguments of the effects are the README's command."""
    plan, item = ctx['plan'], ctx['params']['release_tree']
    need(type(item) is str, 'PARAMETERS_INVALID')
    tree = Path(item) if Path(item).is_absolute() else ctx['base'] / item
    readme = read_file(tree / 'c3po' / 'deployment' / 'massive-supervisor' / 'README.md', 1024 * 1024, 'RELEASE_TREE_UNREADABLE')
    assembler = read_file(tree / 'c3po' / 'backend' / 'app' / 'r2d2_v2_epoch_assembler.py', 1024 * 1024, 'RELEASE_TREE_UNREADABLE')
    try:
        found = re.findall(r'^<!-- catalog-init-script:begin -->\n```python\n(.*?)```\n<!-- catalog-init-script:end -->$', readme.decode('utf-8'), re.S | re.M)
        epochs = re.findall(r"^EPOCH = '([^'\n]+)'$", assembler.decode('utf-8'), re.M)
    except UnicodeDecodeError:
        raise Refused('RELEASE_TREE_UNREADABLE')
    need(len(found) == 1 and sha(found[0].encode('utf-8')) == plan['script_sha256'], 'SCRIPT_NOT_THE_READMES')
    need(len(epochs) == 1 and (plan['mode'] != 'REAL' or plan['epoch'] == epochs[0]), 'EPOCH_NOT_THE_RELEASES')
    argv = readme_argv_is_the_effects(readme, ctx['effects'], plan['mode'])
    return {'readme_sha256': sha(readme), 'epoch_assembler_sha256': sha(assembler), 'script_is_the_readmes': True,
            'epoch_is_the_releases': plan['mode'] == 'REAL', 'docker_arguments_are_the_readmes': argv}


def linux_job_of(ctx):
    """K2a CONTRACT 5 step 0 and K6a CONTRACT 1 (b): the Linux job of the core and of this operation has run and exited 0 with
    its output attached. Neither contract lets the owner waive it: the only kind is LINUX_JOB_PASSED. No tool reads the
    record for these operations; it must at least be a record of THESE bytes: it names, as text, the seal of this operation
    directory, its payload (source or unbound final payload) and the seal of the core (the job log of a run carries them),
    so that the record of another build or of a superseded seal is refused. Its hash is quoted to the owner."""
    item = ctx['params']['linux_job']
    need(type(item) is dict and set(item) == {'kind', 'document_file'} and item['kind'] == 'LINUX_JOB_PASSED'
         and type(item['document_file']) is str, 'PARAMETERS_INVALID')
    path = Path(item['document_file'])
    raw = read_file(path if path.is_absolute() else ctx['base'] / path, 4 * 1024 * 1024, 'LINUX_JOB_RECORD_UNREADABLE')
    ok, named = names_these_bytes(raw, ctx['identity'], ('core',))
    need(ok, 'LINUX_JOB_RECORD_NOT_OF_THESE_BYTES')
    return {'kind': item['kind'], 'document_sha256': sha(raw), 'document_bytes': len(raw), 'names_these_bytes': named}


def linux_proof_of(ctx):
    """K10 CONTRACT 6, step 2: binding/linux_proof.py (sealed bytes) over the two junit files of the Linux job, with the
    VALIDATION.json, the payload and the SHA256SUMS of THIS sealed directory: LINUX_PROOF_ACCEPTED or nothing is bound."""
    item = ctx['params']['linux_proof']
    need(type(item) is dict and set(item) == {'root_junit', 'user_junit'} and all(type(value) is str for value in item.values()), 'PARAMETERS_INVALID')
    tool, tool_sha = binding_tool(ctx['family'], 'linux_proof.py')
    files = {}
    for label in ('root', 'user'):
        path = Path(item[label + '_junit'])
        found, code = tool.junit(str(path if path.is_absolute() else ctx['base'] / path))
        need(code is None, 'LINUX_PROOF_NOT_ACCEPTED')
        files[label] = found
    validation = strict_json(ctx['family']['files'].get('VALIDATION.json', b''), 'LINUX_PROOF_NOT_ACCEPTED')
    checks = tool.judge(files['root'], files['user'], validation, ctx['source_sha256'], ctx['family']['sums_sha256'])
    need(checks and all(ok for _, ok in checks), 'LINUX_PROOF_NOT_ACCEPTED')
    return {'decision': 'LINUX_PROOF_ACCEPTED', 'tool_sha256': tool_sha, 'checks': len(checks),
            'root_junit_sha256': files['root']['sha256'], 'user_junit_sha256': files['user']['sha256']}


def predispatch_checks(ctx, tool, step, role, blobs, now, claim):
    """binding/predispatch.py's own checks (sealed bytes), called with the bytes the binder verified and its clock."""
    checks = tool.checks_of(ctx['rt']['source'], ctx['source_sha256'], step, role, blobs, now, claim)
    return [name for name, _, ok in checks if not ok], len(checks)


def release_rules(ctx):
    """K10 CONTRACT sections 5 and 6, before the owner is asked: the Linux proof (REAL); the precheck rows and boot
    (PLAN_SOURCES); the host evidence (j) named in request.evidence; the release member computed by
    binding/release_fields.py from the input file with the three expectations taken from the cited full K11 PRE receipt
    (its effects: release.sha256, revision, package_sha256) and the PRE's release parent the same chain; the Sunday run
    of binding/predispatch.py on the cited W1 read, where only the check that fails by construction on Sunday may fail."""
    plan, params = ctx['plan'], ctx['params']
    prechecks, reads, pres = cited(ctx, PRECHECK_OPERATION), cited(ctx, W1_OPERATION), cited(ctx, EPOCH_READBACK_OPERATION)
    host_evidence = cited(ctx, PROVISION_OPERATION) + cited(ctx, INSTALL_OPERATION)
    need(len(prechecks) == 1 and len(reads) == 1 and len(pres) == 1 and cited(ctx, PROVISION_OPERATION) and cited(ctx, INSTALL_OPERATION),
         'RELEASE_EVIDENCE_INCOMPLETE')
    pre_role, pre = pres[0]
    need(full_pre(pre, complete_role(ctx, pre_role)), 'RELEASE_NOT_VERIFIED_BY_A_FULL_PRE')
    need(at(pre, '/effects/evidence_boot_id_sha256') == plan['evidence_boot_id_sha256'], 'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    need(at(pre, '/effects/release/parent/chain_sha256') == ctx['effects']['parent']['chain_sha256'], 'RELEASE_PARENT_NOT_THE_ONE_THE_PRE_READ')
    expected = {'sha256': at(pre, '/effects/release/sha256'), 'code_revision': at(pre, '/effects/revision'),
                'implementation_package_sha': at(pre, '/effects/package_sha256')}
    tool, tool_sha = binding_tool(ctx['family'], 'release_fields.py')
    try:
        item, facts = tool.judged(ctx['rt']['source'], ctx['inputs']['release'], expected, tool.DEPLOYED)
    except ValueError as error:
        code = str(error)
        raise Refused('RELEASE_FIELDS_' + (code if re.fullmatch(CODE, code) else 'REFUSED'))
    need(canonical(plan['release']) == canonical(item) and canonical(ctx['effects']['release']) == canonical(facts), 'RELEASE_MEMBER_NOT_THE_TOOLS')
    proof = linux_proof_of(ctx) if 'linux_proof' in params else None
    need(proof is not None or ctx['mode'] == REHEARSAL, 'LINUX_PROOF_REQUIRED')
    read = ctx['blobs'][reads[0][0]]
    need(read['source'] == 'bound', 'RELEASE_SUNDAY_READ_NOT_A_BOUND_SET')
    gate, gate_sha = binding_tool(ctx['family'], 'predispatch.py')
    failed, count = predispatch_checks(ctx, gate, 'prepare', 'primary', {
        'request': ctx['request_raw'], 'evidence': ctx['blobs'][prechecks[0][0]]['receipt'], 'm0-request': read['request'],
        'm0-receipt': read['receipt'], 'm0-exit': read['exit']}, ctx['now'], None)
    need(set(failed) <= {SUNDAY_ONLY_FAILURE}, 'RELEASE_SUNDAY_GATE_FAILED')
    # (j) names three receipts: A3 and A4 (two provisions) and B1. With one provision cited, the operator says why on the
    # sheet (for instance: A4 was cut with tier 1), and the owner reads it.
    reason = params.get('host_evidence_reason_pt')
    need(reason is None or free_text(reason), 'PARAMETERS_FREE_TEXT')
    need(len(cited(ctx, PROVISION_OPERATION)) >= 2 or reason is not None, 'RELEASE_HOST_EVIDENCE_A4_NOT_CITED_AND_NO_REASON')
    return {'release_fields': {'tool_sha256': tool_sha, 'expected_from_the_full_pre': dict(expected, role=pre_role), 'member_is_the_tools': True},
            'linux_proof': proof, 'linux_proof_required': ctx['mode'] == REAL,
            'host_evidence': [{'role': role, 'operation': receipt.get('operation'), 'complete': complete_role(ctx, role)} for role, receipt in host_evidence],
            'host_evidence_complete': all(complete_role(ctx, role) for role, _ in host_evidence),
            'provisions_cited': len(cited(ctx, PROVISION_OPERATION)), 'host_evidence_reason_pt': reason,
            'sunday_gate': {'tool_sha256': gate_sha, 'checks': count, 'failed': failed, 'role_of_the_read': reads[0][0]},
            'precheck_observed_at': prechecks[0][1].get('observed_at'), 'dispatch_gates': ['K10_M0_PREDISPATCH_DISPATCH_ALLOWED']}


def operation_of(family):
    """The one HOSTOPS02 operation a sealed operation directory holds, or None."""
    for operation in HOSTOPS02:
        try:
            return select_operation(family, operation)
        except Refused:
            continue
    return None


def siblings_of(ctx):
    """K11 CONTRACT 8, step 3: the sibling payload hashes the sealed suite ran against (SIBLINGS.txt, sealed) must be the
    payload sources of the accepted seals beside this directory; they are written next to the request (on the sheet)."""
    raw = ctx['family']['files'].get('SIBLINGS.txt', b'')
    found = {}
    for line in raw.decode('ascii', 'replace').splitlines():
        match = re.fullmatch(r'([a-z_]+)  op\.py ([0-9a-f]{64})  build/([a-z_]+)\.py ([0-9a-f]{64})  BUILD_EQUAL  SHA256SUMS ([0-9a-f]{64})', line)
        if match and match.group(1) == match.group(3):
            found[match.group(1)] = {'payload_sha256': match.group(4), 'recorded_sha256sums': match.group(5)}
    need(sorted(found) == ['activate', 'catalog_init', 'install_release'], 'SIBLINGS_NOT_THE_SEALED_SIBLINGS')
    sources = {}
    for name, item in sorted(found.items()):
        try:
            sibling = verify_family(ctx['family']['directory'].parent / name, ctx['seals'])
            seal = accepted_seal(ctx['seals'], sibling['sums_sha256'])
            op = operation_of(sibling)
            sources[name] = load_runtime(op['files'], op['source_name'], op['directory'])['source'] if op else None
        except Refused:
            raise Refused('SIBLINGS_NOT_THE_SEALED_SIBLINGS')
        need('core' in seal and sha(sibling['files'].get('build/%s.py' % name, b'')) == item['payload_sha256'] and sources[name] is not None,
             'SIBLINGS_NOT_THE_SEALED_SIBLINGS')
        item.update(seal=seal['sha256sums_sha256'], recorded_seal_is_the_accepted_seal=item['recorded_sha256sums'] == seal['sha256sums_sha256'])
    return found, sources


def readback_rules(ctx):
    """K11 CONTRACT sections 7 and 8: every cited receipt that names a boot names the plan's; the image ID and the revision
    are the cited read's (the precheck's image reading, else a cited K11's effects); every signed row is the row of a cited
    receipt (rows null: observed, compared with nothing); the release says this revision and package; the bytes of the
    release, the policy and the override come from their input files; the sibling payloads are the sealed ones."""
    plan = ctx['plan']
    boots = [boot_of(entry['operation'], ctx['receipts'][entry['role']]) for entry in ctx['entries']]
    boots = [boot for boot in boots if boot is not None]
    need(boots, 'READBACK_EVIDENCE_WITHOUT_A_BOOT')
    need(all(boot == plan['evidence_boot_id_sha256'] for boot in boots), 'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    prechecks, readbacks, provisions = cited(ctx, PRECHECK_OPERATION), cited(ctx, EPOCH_READBACK_OPERATION), cited(ctx, PROVISION_OPERATION)
    if prechecks:
        need(len(prechecks) == 1, 'IMAGE_WITHOUT_A_CITED_READ')
        reading = (at(prechecks[0][1], '/items/image/id'), at(prechecks[0][1], '/items/image/revision_label'), prechecks[0][0])
    else:
        need(len(readbacks) == 1, 'IMAGE_WITHOUT_A_CITED_READ')
        reading = (at(readbacks[0][1], '/effects/image/image_id'), at(readbacks[0][1], '/effects/revision'), readbacks[0][0])
    need((plan['image']['image_id'], plan['revision']) == reading[:2], 'IMAGE_NOT_THE_ONE_OF_THE_CITED_READ')

    def observed(name):
        return [at(receipt, '/items/directory:%s/observed_rows' % name) for _, receipt in readbacks]
    journal = []
    if prechecks and provisions:
        try:
            journal = [at(prechecks[0][1], '/items/chains/VAR_LIB/rows') + [ledger_rows(provisions, '/var/lib/c3po-bar', 'SUP_STATE_PARENT'),
                                                                          ledger_rows(provisions, '/var/lib/c3po-bar/journal', 'SUP_JOURNAL')]]
        except (Refused, TypeError):
            journal = []
    members = (('release', plan['release']['parent'], [at(receipt, '/items/chains/DATA_VOLUME/rows') for _, receipt in prechecks] + observed('RELEASE_PARENT')),
               ('live', (plan['live'] or {}).get('parent'), observed('LIVE_PARENT')),
               ('deploy_tree', plan['deploy']['tree'], observed('DEPLOY_TREE')),
               ('lock_directory', plan['deploy']['lock_directory'], observed('LOCK_DIRECTORY')),
               ('bind_probe', (plan['bind_probe'] or {}).get('directory'), observed('BIND_PROBE') + journal))
    signed = {}
    for name, chain, sources in members:
        rows = chain.get('rows') if type(chain) is dict else None
        if rows is None:
            continue
        need(any(source is not None and canonical(rows) == canonical(source) for source in sources), 'PLAN_ROWS_NOT_THE_ROWS_OF_A_CITED_RECEIPT')
        signed[name] = len(rows)
    body = strict_json(ctx['inputs']['release'], 'REVISION_NOT_THE_RELEASES')
    need(type(body) is dict and body.get('code_revision') == plan['revision'] and body.get('implementation_package_sha') == plan['package_sha256'],
         'REVISION_NOT_THE_RELEASES')
    siblings, sources = siblings_of(ctx)
    install, activate = sources['install_release'], sources['activate']
    need((plan['release']['parent']['path'], plan['release']['directory_name'], plan['release']['file_name'])
         == (install.DATA_VOLUME, install.RELEASE_DIRECTORY_NAME, install.RELEASE_FILE_NAME), 'RELEASE_PLACE_NOT_THE_SIBLINGS')
    need(plan['limits'] is None or (plan['limits']['data_volume_free_bytes'] == install.FREE_BYTES_FLOOR == activate.FREE_BYTES_FLOOR
                                    and plan['limits']['data_volume_free_inodes'] == activate.FREE_INODES_FLOOR), 'LIMITS_NOT_THE_SIBLINGS_FLOORS')
    tests = siblings_tests_of(ctx, siblings)
    worker = worker_and_image_of(ctx)
    gates = ['K11_POST_AFTER_THE_COMPLETE_INSTALL'] if plan['mode'] == 'POST' else []
    return {'mode': plan['mode'], 'dry_run': plan['dry_run'], 'image_and_revision_from': reading[2], 'rows_signed_from_cited_receipts': signed,
            'release_says_this_revision_and_package': True, 'release_place_and_floors_are_the_siblings': True, 'siblings': siblings,
            'siblings_tests': tests, 'worker_and_image_compared_with': worker, 'dispatch_gates': gates}


def siblings_tests_of(ctx, siblings):
    """K11 CONTRACT 8, step 3: once the siblings are sealed, tests/test_siblings.py and tests/test_conformance.py run again
    beside them, and the sibling hashes they ran against are written next to the request. SIBLINGS.txt (sealed with K11)
    may name earlier seals of a sibling; then the request names the record of a run of K11's suite beside the ACCEPTED
    siblings ("siblings_tests": {"document_file": ...}; the Linux job log of the tier, which ran K11's suite beside them, is
    one): it must name K11's seal and the three accepted sibling seals as text. REAL: required whenever a recorded seal is
    not the accepted one. The question says which holds."""
    stale = sorted(name for name, item in siblings.items() if not item['recorded_seal_is_the_accepted_seal'])
    item = ctx['params'].get('siblings_tests')
    if item is None:
        need(not stale or ctx['mode'] == REHEARSAL, 'SIBLINGS_TESTS_NOT_RERUN_FOR_THE_ACCEPTED_SEALS')
        return {'stale_recorded_seals': stale, 'record': None}
    need(type(item) is dict and set(item) == {'document_file'} and type(item['document_file']) is str, 'PARAMETERS_INVALID')
    path = Path(item['document_file'])
    raw = read_file(path if path.is_absolute() else ctx['base'] / path, 4 * 1024 * 1024, 'SIBLINGS_TESTS_RECORD_UNREADABLE')
    wanted = [ctx['family']['sums_sha256']] + [siblings[name]['seal'] for name in sorted(siblings)]
    need(all(value.encode('ascii') in raw for value in wanted), 'SIBLINGS_TESTS_RECORD_NOT_OF_THE_ACCEPTED_SEALS')
    return {'stale_recorded_seals': stale, 'record': {'document_sha256': sha(raw), 'document_bytes': len(raw),
                                                      'names_the_seals': ['epoch_readback'] + sorted(siblings)}}


def worker_and_image_of(ctx):
    """K11 CONTRACT 7: image.reference, image.image_id, worker.container, worker.data_source and worker.data_target come
    from a read of the host. Where the request cites a W1 read, they are compared with it: exactly one container of that
    name, running the signed image ID under the signed reference, with a bind mount of data_source at data_target."""
    plan, reads = ctx['plan'], cited(ctx, W1_OPERATION)
    if not reads:
        return None
    for role, receipt in reads:
        rows = at(receipt, '/observation/sections/containers/rows')
        rows = [row for row in rows if type(row) is dict and row.get('name') == plan['worker']['container']] if type(rows) is list else []
        need(len(rows) == 1 and (rows[0].get('image_id'), rows[0].get('image_reference')) == (plan['image']['image_id'], plan['image']['reference'])
             and any(type(mount) is dict and mount.get('type') == 'bind' and (mount.get('source'), mount.get('destination'))
                     == (plan['worker']['data_source'], plan['worker']['data_target']) for mount in rows[0].get('mounts') or []),
             'WORKER_OR_IMAGE_NOT_THE_ONES_OF_THE_CITED_READ')
    return [role for role, _ in reads]


def activate_rules(ctx):
    """K6a CONTRACT sections 8 and 9: exactly one cited K11 receipt, the full PRE with its observed rows, of the boot the
    plan names (PLAN_SOURCES: the four chains, the boot, the image ID, the data bind, the compose inputs, the hashes and
    sizes of the policy and the release); this request's override is the one that PRE rendered, its four values are the
    rendered ones; the live parent receives an entry; and, computed here independently of the source, the four values,
    the override bytes and the policy digest as the assembler of the release computes it equal what effects_of() says."""
    plan, effects = ctx['plan'], ctx['effects']
    readbacks = cited(ctx, EPOCH_READBACK_OPERATION)
    need(len(readbacks) == 1 and full_pre(readbacks[0][1], complete_role(ctx, readbacks[0][0]))
         and at(readbacks[0][1], '/effects/rows_in_receipt') is True, 'ACTIVATE_EVIDENCE_NOT_ONE_FULL_PRE')
    role, pre = readbacks[0]
    live = at(pre, '/items/directory:LIVE_PARENT')
    need(type(live) is dict and live.get('setgid') is False and live.get('rows_acceptable_to_a_write') is True
         and live.get('judged_as_receiving_an_entry') is True, 'LIVE_PARENT_NOT_ACCEPTABLE_TO_A_WRITE')
    files = {item['key']: item for item in effects['files']}
    need(effects['directory']['path'] == at(pre, '/effects/live/path') and effects['release']['path'] == at(pre, '/effects/release/path')
         and files['OVERRIDE']['sha256'] == at(pre, '/effects/render/override_sha256')
         and canonical(effects['recreate']['environment']) == canonical(at(pre, '/effects/render/environment'))
         and effects['revision'] == at(pre, '/effects/revision'), 'ACTIVATE_NOT_WHAT_THE_PRE_RENDERED')

    def seen_by_the_worker(path):
        need(path.startswith(plan['data_root'].rstrip('/') + '/'), 'ACTIVATE_DERIVED_VALUES_NOT_REPRODUCED')
        return plan['worker']['mount_target'] + path[len(plan['data_root']):]
    live_path = plan['live_parent'][-1]['path'].rstrip('/') + '/' + plan['directory_name']
    release_path = plan['release']['parent'][-1]['path'].rstrip('/') + '/' + plan['release']['directory_name'] + '/' + plan['release']['file_name']
    four = {'C3PO_R2D2_V2_LIVE_POLICY_FILE': seen_by_the_worker(live_path + '/' + plan['policy']['name']),
            'C3PO_R2D2_V2_LIVE_POLICY_SHA': sha(ctx['inputs']['policy']),
            'C3PO_R2D2_V2_SHADOW_RELEASE_FILE': seen_by_the_worker(release_path), 'C3PO_R2D2_V2_SHADOW_RELEASE_SHA': sha(ctx['inputs']['release'])}
    override = json.dumps({'services': {'r2d2-worker': {'environment': four}}}, sort_keys=True).encode('ascii')
    policy = strict_json(ctx['inputs']['policy'], 'ACTIVATE_DERIVED_VALUES_NOT_REPRODUCED')
    try:
        digest = sha(json.dumps(policy, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8'))
    except (TypeError, ValueError):
        raise Refused('ACTIVATE_DERIVED_VALUES_NOT_REPRODUCED')
    need(canonical(four) == canonical(effects['recreate']['environment']) and (files['OVERRIDE']['sha256'], files['OVERRIDE']['bytes']) == (sha(override), len(override))
         and digest == effects['policy']['content_digest_sha256'], 'ACTIVATE_DERIVED_VALUES_NOT_REPRODUCED')
    # the override file the signatories hold (the one K11 PRE rendered) is byte for byte what this request will write
    need(ctx['inputs'].get('override') == override, 'OVERRIDE_FILE_NOT_THE_ONE_ACTIVATE_WRITES')
    instants = at(pre, '/effects/policy/valid_at')
    try:          # K11 CONTRACT 7: valid_at holds the starts of M3's gates; the PRE accepted the policy at this one
        verified = type(instants) is list and any(datetime.fromisoformat(item) == ctx['window']['gate_start'] for item in instants)
    except (TypeError, ValueError):
        verified = False
    need(verified, 'POLICY_NOT_VERIFIED_AT_THIS_GATE')
    return {'full_pre': role, 'override_is_the_one_the_pre_rendered': True, 'four_values_override_and_policy_digest_reproduced': True,
            'override_sha256': sha(override), 'policy_digest_sha256': digest, 'live_parent_receives_an_entry': True,
            'dispatch_gates': ['K6A_AFTER_THE_COMPLETE_POST_READBACK']}


RULES_OF = {CATALOG_OPERATION: catalog_rules, RELEASE_OPERATION: release_rules, EPOCH_READBACK_OPERATION: readback_rules,
            ACTIVATE_OPERATION: activate_rules}


# ================================================================ K9 (binder revision 4)
# The two host programs of the delegated daily phases of epoch R2D2-V2-SHADOW-2026-10-05: K9R (reads: RESULT, PROBE, POLICY,
# and the weekly TREE read) and K9W (writes: LAUNCH, ATTACHED, CLEANUP). What K9_INTERFACE_NOTE.md revision 2 (sha256
# ab5159be...596c), section 10.4, leaves to the binder, checked before the owner is asked:
#   - the operation is one of the frozen list (K9_OPERATIONS.json, bc796cb7...) of the right kind (READ for K9R, WRITE for K9W);
#   - attempt_key = sha256(canonical([epoch, day, phase, operation])) (actb03_lib.attempt_key), recomputed;
#   - the window is exactly the row of the named grid (G18 or G19, section 5; the grid file is pinned by hash beside this
#     binder), the gate is the window, and the window has at least 180 sendable seconds under A2 section 3, the container
#     rule and the quiet bands (rules 1-4); run_not_after is the grid's (a RESULT's is its launch's);
#   - the window lies in the eve or the morning of D (K9R DESIGN deviation 9: K9R refuses these windows only on the host,
#     after the claim, so the binder refuses them first);
#   - the TREE rows (parent_rows) and boot (evidence_boot_id_sha256) of every daily request are the cited TREE receipt's,
#     by $from (PLAN_SOURCES), and the week's constants are the ones that TREE read signed; the runner hash is the one
#     K4-E0 delivered (the TREE request cites the E0 receipt; every daily request cites a complete TREE read, which read
#     the runner file and found the signed hash);
#   - for K9W `bind`: the owner order's exact bytes are the order of the grid's cutoff_at and phase windows for D;
#   - a SPARE is bound as the spare of its PRIMARY (same request but for slot, window and run_not_after), and is sent only if
#     the PRIMARY never was (the existing spare gate);
#   - a fixed Portuguese owner text per K9 operation (HOSTOPS02_TEXT_PT), so that the 22-29 sheets of an eve differ.
K9R_OPERATION = 'GO_READONLY_HOSTOPS02_K9_PHASE_READ_01'
K9W_OPERATION = 'GO_WRITE_HOSTOPS02_K9_PHASE_STEP_01'
K9_PROGRAMS = {K9R_OPERATION: 'READ', K9W_OPERATION: 'WRITE'}          # the program and the kind of the K9 operations it runs
K4E0_OPERATION = 'GO_WRITE_HOSTOPS02_K4_E0_01'
K4E0_OUTCOME = 'EPOCH_ROOTS_CREATED_RUNNER_DELIVERED_READ_BACK'
K9_EPOCH = 'R2D2-V2-SHADOW-2026-10-05'
K9_DAYS = ('2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09')          # Monday 05/10 has no K9 list (NOTE 5.5)
K9_NOTE_SHA256 = 'ab5159bea34b3239379e87c2500d383f0777cc6186618435ba0ea9f61e3d596c'
K9_OPERATIONS_SHA256 = 'bc796cb7d6d8ab29e314ad29c726f33f16f3b83dfcede7771ec2b2cdae0e7d08'
# K9_OPERATIONS.json, written out: its canonical bytes must hash to K9_OPERATIONS_SHA256 (checked at every use).
K9_OPERATIONS = {'k9_interface_note_sha256': K9_NOTE_SHA256, 'schema': 'ACTB03_K9_OPERATIONS_V1', 'synthetic': False, 'phases': {
    'capture': {'capture_cleanup': 'WRITE', 'capture_launch': 'WRITE', 'capture_result': 'READ'},
    'causal_list': {'collect_launch': 'WRITE', 'collect_result': 'READ', 'commit_launch': 'WRITE', 'commit_result': 'READ', 'publish_launch': 'WRITE',
                    'publish_result': 'READ', 'readiness_probe': 'READ', 'readiness_recheck': 'READ'},
    'components': {'components_launch': 'WRITE', 'components_result': 'READ'},
    'policy_readonly': {'policy_read': 'READ'},
    'risk': {'acquire_launch': 'WRITE', 'acquire_result': 'READ', 'bind': 'WRITE', 'execute_launch': 'WRITE', 'execute_result': 'READ', 'preflight': 'WRITE',
             'stage': 'WRITE'},
    'sources': {'sources_launch': 'WRITE', 'sources_result': 'READ'}}}
# The two grids of the note (section 5; aux/grid9.json, made by aux/grid9.py and checked by aux/check9.py: GRID9_PASS),
# a byte copy beside this file, pinned here.
K9_GRID_FILE = 'K9_GRID9.json'
K9_GRID_SHA256 = 'a6c509ff1e722f677f99368f11dd4c37e231e5693ad8b7bdcbc29bf29828892c'
K9_GRIDS = ('G18', 'G19')
K9_SLOTS = ('PRIMARY', 'SPARE')
K9_TREE_OUTCOME = 'K9_TREE_AS_REQUIRED_ALL_OBSERVED'
K9_ROOT = '/var/lib/c3po/r2d2-v2-k9-20261005'          # N-8 (codex-n8-placement-20261004.txt d30f7f90...): K9R's and K4-E0's compiled placement
K9_RUNNER_PATH = K9_ROOT + '/tools/k9_runner-%s.py'
K9R_CHAINS = (('days', 'DAYS'), ('source_root', 'SOURCE_ROOT'), ('secrets', 'SECRETS'), ('tools', 'TOOLS'), ('claims', 'CLAIMS'))
# A2 section 3 and the note's rules 1-4 (aux/check9.py, written out): a send starts only in these seconds of the hour; the
# container rule (K9W steps and the probe: never 06:58:40-07:25:59, 12:58:40-13:25:59, 18:58:40-19:25:59 BRT); the quiet
# bands of the scheduled workflows (00:15:00-00:45:59, 02:15:00-02:45:59 BRT); at least 180 such seconds from the window
# start to its end minus the watchdog (80 s).
K9_SEND_SECONDS = ((0, 220), (480, 520), (1560, 2020), (2280, 3600))
K9_CONTAINER_BANDS = tuple(((hour - 1) * 3600 + 58 * 60 + 40, hour * 3600 + 26 * 60) for hour in (7, 13, 19))
K9_QUIET_BANDS = ((15 * 60, 46 * 60), (2 * 3600 + 15 * 60, 2 * 3600 + 46 * 60))
K9_CONTAINER_MODES = ('PROBE', 'LAUNCH', 'ATTACHED', 'CLEANUP')
K9_MIN_SENDABLE_SECONDS = 180
K9_WATCHDOG_SECONDS = 80
# The packaged risk order (R/r2d2_v2_risk_host_executor.py:_validate at dd4ec4bb): schema, scope and the three actions.
K9_RISK_ORDER_SCHEMA = 'R2D2_V2_RISK_HOST_ORDER_V1'
K9_RISK_PHASES = ['preflight', 'acquire', 'execute']
K9_RISK_ACTIONS = ['READ_PROVIDERS', 'READ_DATABASE', 'WRITE_PRIVATE_RISK_ARTIFACTS']
# The week's constants known when revision 4 was written (the coordinator's message of 2026-10-04 ~22:05Z): the runner,
# by command from W/fable-k9runner-20261004/k9_runner.py (revision 2: 40,618 bytes); the risk source pins; the disk floor (Codex,
# #429 5984327121); the placement (Codex N-8, W/codex-n8-placement-20261004.txt d30f7f90...: K9R's and K9W's compiled
# K9_PLACEMENT). Every K9R and K9W request carries them in `constants`, and K4-E0 delivers that runner.
K9_RUNNER_SHA256 = '563a4797ab2a7ef4c02a1c1937061a2644420b69bdcc2dca842cd1efd7fb7690'          # runner revision 2, 40,618 bytes (by command 2026-10-05T00:56Z; rev 1 was b5950b99...)
K9_RISK_SOURCE_PINS_SHA256 = 'faaa35a7905076231f1847616c600968193c69ce064b6bd1db9cdbd6b77852bb'
K9_STEP_TABLE_SHA256 = 'e9c96ce99a56610af3131e6f224240d8ecc5fca9cff69df82eeb94e489ac5561'          # K9W's (sealed 165330a6..., unchanged in rev 2 92203431...)
K9_DISK_FLOOR_BYTES = 214748364800
# ---------------------------------------------------------------- PLACEMENT PLUG (one place). Codex decision 6 (#429 5985748037;
# W/codex-six-design-decisions-20261004.txt 4b169599...): the source root under the root-only chain, no open root anywhere for
# K9 / K4-E0 binds (only K3-K9's September reads and the TREE's lstat of them use the data volume's open root). The binder
# compares the PATHS of `constants.placement` (each program compares its whole compiled object, and every request of the week
# carries the TREE read's object); the other members (`decision`, the open-root members) are left to the programs. Every chain
# of `parent_rows` whose path is not on the data volume must have open_root null and rows of gid 0 without setgid.
K9_DATA_VOLUME = '/mnt/day-d-data'
K9_PLACEMENT_PATHS = {'k9_root': K9_ROOT, 'source_root': '/var/lib/c3po/r2d2-v2-source-20261005', 'days': K9_ROOT + '/days', 'tools': K9_ROOT + '/tools',
                      'claims': K9_ROOT + '/claims', 'secrets': K9_ROOT + '/secrets', 'emitter': K9_ROOT + '/secrets/emitter',
                      'provider_env_file': K9_ROOT + '/secrets/provider.env', 'risk_db_env_file': K9_ROOT + '/secrets/risk-db.env',
                      'emitter_password': K9_ROOT + '/secrets/emitter/password'}
# ---------------------------------------------------------------- end of the PLACEMENT PLUG
K4E0_OPERATION_DAYS = ('2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08')          # A2 row E0: Mon 05/10 to Thu 08/10, 17:38-20:30 BRT
K4E0_BAND = ('20:38:00', '23:30:00')          # in UTC of that day
K3K9_OPERATION = 'GO_WRITE_HOSTOPS02_K3K9_SECRETS_01'
K9_PREREQUISITES = (K4E0_OPERATION, K3K9_OPERATION)
K9_POLICY_ROW_SOURCES = (EPOCH_READBACK_OPERATION, ACTIVATE_OPERATION, RELEASE_OPERATION)          # K9R CONTRACT 2: the K11 POST / activate
# receipts (and K10's, which created the release directory); a chain may be the parts of a $concat of their rows


# ---------------------------------------------------------------- K9W: the binding of its SEALED bytes (the one K9W block)
# W/fable-k9w-20261004/k9_phase_step, SHA256SUMS 165330a6c86ac0dfd0dc09f77176d35e7973e4da65e2a1cef699e9edfe4b8d77 (by command,
# 2026-10-04T23:46Z; every file checks), op.py read: PLAN_KEYS = mode epoch day k9_phase k9_operation slot attempt_key
# run_not_after constants parent_rows evidence_boot_id_sha256 bind; `bind` (bind step only) = {namespace, cutoff_at,
# phase_windows, owner_order_text, owner_order_sha256}, the order as ASCII text of its canonical bytes; run_not_after for
# LAUNCH only (window end + the step's ceiling; capture 14:03:00Z of D); constants: the sixteen of K9R, step_table_sha256 =
# its K9W_STEP_TABLE_SHA256; its window rules (k9w_window_of, in perform after the read-only checks, DESIGN 8 item 2) are
# refused here first, including RUN_NOT_AFTER_TOO_CLOSE at the latest start (launch timeout run_not_after - now - 5 s, at
# least 90 s, inside a 60 s program: 155 s left at the latest start). A new K9W seal: compare this block again.
K9W_SEAL_SHA256 = '922034314242dce519a716babe4ca03e5bba38463f09eb1f3f568c88e8d02344'          # revision 2 (decision 6); rev 1 was 165330a6...
K9W_STEP_TABLE_SHA256 = 'e9c96ce99a56610af3131e6f224240d8ecc5fca9cff69df82eeb94e489ac5561'
K9W_PLUG = {
    'status': 'MATCHED_TO_THE_SEALED_K9W_165330a6_AND_REV2_92203431',
    # plan member names (K9R's names: the core reserves `phase` in every plan, so the K9 phase is k9_phase)
    'members': {'mode': 'mode', 'epoch': 'epoch', 'day': 'day', 'phase': 'k9_phase', 'operation': 'k9_operation', 'slot': 'slot',
                'attempt_key': 'attempt_key', 'run_not_after': 'run_not_after', 'constants': 'constants', 'parent_rows': 'parent_rows',
                'boot': 'evidence_boot_id_sha256'},
    'modes': ('LAUNCH', 'ATTACHED', 'CLEANUP'),
    'run_not_after_modes': ('LAUNCH',),
    'constants_shared_with_the_tree_read': None,          # None: the whole object (K9W DESIGN 8 item 9: one object serves both programs)
    'bind_member': 'bind',
    'bind_keys': ('namespace', 'cutoff_at', 'phase_windows', 'owner_order_text', 'owner_order_sha256'),
    'risk_namespace_prefixes': ('R2D2-V2-DIAG-R4-',),          # K9W_RISK_NAMESPACE (N-1)
    'before_open_ends_by': '13:30:00',          # window_class BEFORE_OPEN ends by 13:30Z of D; IN_SESSION starts at or after it
    'in_session_operations': ('capture_launch', 'capture_cleanup'),
    'cleanup_starts_after': ('capture_cleanup', '14:03:00'),          # K9W_CAPTURE_RUN_NOT_AFTER
    'latest_run_not_after': {'commit_launch': '03:50:00'},          # the step table's `latest` (publish: implied by the class, DESIGN 8 item 8)
    'ceiling_seconds': {'collect_launch': 900, 'commit_launch': 600, 'publish_launch': 600, 'components_launch': 2400, 'sources_launch': 4500,
                        'acquire_launch': 3600, 'execute_launch': 1200},          # K9W_STEPS ceilings (capture: its fixed 14:03:00Z)
    'seconds_left_at_the_latest_start': 155,          # K9W_MIN_TIMEOUT_SECONDS 90 + K9W_LAUNCH_MARGIN_SECONDS 5 + the core's 60 s
}


def k9w_view(plan):
    """K9W's plan in the binder's own words (K9W_PLUG['members']); every member must exist."""
    return {name: plan[key] for name, key in K9W_PLUG['members'].items()}


def k9w_bind_members(plan, operation):
    """bind: the member `bind` with exactly its keys; any other K9W operation: null."""
    value = plan.get(K9W_PLUG['bind_member'])
    if operation != 'bind':
        need(value is None, 'K9_BIND_MEMBERS_OUTSIDE_BIND')
        return None
    need(type(value) is dict and set(value) == set(K9W_PLUG['bind_keys']) and type(value['owner_order_text']) is str, 'K9_BIND_ORDER_NOT_THE_GRIDS')
    return value


def k9w_window_rules(view, start, end, run_not_after, latest_start=None):
    """K9W's window rules (k9w_window_of: on the host, after its read-only checks), applied before the owner is asked."""
    day = view['day']

    def utc_of_d(hms):
        return datetime.fromisoformat(day + 'T' + hms + '+00:00')
    opening = utc_of_d(K9W_PLUG['before_open_ends_by'])
    if view['operation'] in K9W_PLUG['in_session_operations']:
        need(start >= opening, 'K9_WINDOW_NOT_OF_THE_STEP_CLASS')
    else:
        need(end <= opening, 'K9_WINDOW_NOT_OF_THE_STEP_CLASS')
    cleanup, after = K9W_PLUG['cleanup_starts_after']
    need(view['operation'] != cleanup or start >= utc_of_d(after), 'K9_CLEANUP_BEFORE_CAPTURE_RUN_NOT_AFTER')
    latest = K9W_PLUG['latest_run_not_after'].get(view['operation'])
    need(latest is None or (run_not_after is not None and run_not_after <= utc_of_d(latest)), 'K9_RUN_NOT_AFTER_AFTER_THE_STEP_LIMIT')
    ceiling = K9W_PLUG['ceiling_seconds'].get(view['operation'])
    need(ceiling is None or (run_not_after is not None and run_not_after == end + timedelta(seconds=ceiling)), 'K9_RUN_NOT_AFTER_NOT_WINDOW_END_PLUS_CEILING')
    need(run_not_after is None or latest_start is None
         or (run_not_after - latest_start).total_seconds() >= K9W_PLUG['seconds_left_at_the_latest_start'], 'K9_RUN_NOT_AFTER_TOO_CLOSE_TO_THE_LATEST_START')


K9W_NETWORK_PT = {'PROVIDER': 'do provedor', 'DATABASE': 'interna do banco', 'DATABASE_AND_PROVIDER': 'do banco com saída para o provedor', 'NONE': 'nenhuma'}
# ---------------------------------------------------------------- end of the K9W block


def k9r_view(plan):
    """K9R's plan (k9_phase_read DESIGN.md section 6) in the binder's own words."""
    return {'mode': plan['mode'], 'epoch': plan['epoch'], 'day': plan['day'], 'phase': plan['k9_phase'], 'operation': plan['k9_operation'],
            'slot': plan['slot'], 'attempt_key': plan['attempt_key'], 'run_not_after': plan['run_not_after'], 'constants': plan['constants'],
            'parent_rows': plan['parent_rows'], 'boot': plan['evidence_boot_id_sha256']}


def k9_view(operation, plan):
    return k9r_view(plan) if operation == K9R_OPERATION else k9w_view(plan)


def k9_operation_list():
    """{K9 operation: (phase, READ|WRITE)} of the frozen list, after its bytes are proved to be the frozen ones."""
    need(sha(canonical(K9_OPERATIONS)) == K9_OPERATIONS_SHA256, 'K9_OPERATION_LIST_NOT_THE_FROZEN_ONE')
    return {operation: (phase, kind) for phase, operations in K9_OPERATIONS['phases'].items() for operation, kind in operations.items()}


def k9_grid():
    """The two grids of the note, from the pinned copy beside this file."""
    raw = read_file(Path(__file__).resolve().with_name(K9_GRID_FILE), 1024 * 1024, 'K9_GRID_MISSING')
    need(sha(raw) == K9_GRID_SHA256, 'K9_GRID_NOT_THE_NOTES')
    grid = strict_json(raw, 'K9_GRID_NOT_THE_NOTES')
    need(type(grid) is dict and sorted(grid) == list(K9_GRIDS), 'K9_GRID_NOT_THE_NOTES')
    return grid


def k9_attempt_key(epoch, day, phase, operation):
    """actb03_lib.attempt_key: sha256 of the canonical list [epoch, day, phase, operation] (no slot: PRIMARY and SPARE share it)."""
    return sha(json.dumps([epoch, day, phase, operation], separators=(',', ':'), ensure_ascii=True).encode('ascii'))


def k9_iso(text):
    """A grid instant (YYYY-MM-DDTHH:MM:SSZ) as K9R signs an instant: datetime.isoformat() of the UTC instant (+00:00)."""
    return parse_utc(text, 'K9_GRID_NOT_THE_NOTES').isoformat()


def k9_rows_of_the_day(grid, name, day):
    found = [entry for entry in grid[name] if type(entry) is dict and entry.get('day') == day]
    need(len(found) == 1 and type(found[0].get('rows')) is list, 'K9_NO_GRID_ROW')
    return found[0]


def k9_grid_row(grid, name, day, operation, slot):
    """The one row of that grid, day, operation and slot (readiness_recheck is a PRIMARY of the S track)."""
    entry = k9_rows_of_the_day(grid, name, day)
    rows = [row for row in entry['rows'] if type(row) is dict and row.get('operation') == operation and row.get('slot') == slot]
    need(len(rows) == 1, 'K9_NO_GRID_ROW')
    return rows[0], entry


def k9_launch_of(entry, row):
    """A RESULT row's launch: its predecessor, in the same track."""
    rows = [item for item in entry['rows'] if item.get('operation') == row.get('pred') and item.get('track') == row.get('track') and item.get('mode') == 'LAUNCH']
    need(len(rows) == 1 and type(rows[0].get('run_not_after')) is str, 'K9_NO_GRID_ROW')
    return rows[0]


def k9_sendable(moment, container):
    """One second at which a K9 send may start (A2 section 3; the note's rules 1-3), Brasília time (UTC-3)."""
    local = moment - timedelta(hours=3)
    second = local.hour * 3600 + local.minute * 60 + local.second
    return (any(low <= second % 3600 < high for low, high in K9_SEND_SECONDS)
            and not (container and any(low <= second < high for low, high in K9_CONTAINER_BANDS))
            and not any(low <= second < high for low, high in K9_QUIET_BANDS))


def k9_sendable_seconds(start, last, container):
    count, moment = 0, start
    while moment <= last:
        count += 1 if k9_sendable(moment, container) else 0
        moment += timedelta(seconds=1)
    return count


def k9_day_window(day, mode, start, end, run_not_after):
    """K9R perform's window rules (DESIGN 7.2, deviation 9), refused here first, for every K9 request of D: the window in
    the eve or the morning of D, [20:00Z of D-1, 15:00Z of D]; a probe ends by 04:00Z of D; a policy read starts on D; a
    run_not_after in the same bounds; a result starts at or after it; a detached run stays in its launch's UTC day."""
    midnight = datetime.fromisoformat(day + 'T00:00:00+00:00')
    low, high = midnight - timedelta(hours=4), midnight + timedelta(hours=15)
    need(low <= start and end <= high, 'K9_WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    need(mode != 'PROBE' or end <= midnight + timedelta(hours=4), 'K9_WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    need(mode != 'POLICY' or start >= midnight, 'K9_WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    if run_not_after is not None:
        need(low <= run_not_after <= high, 'K9_RUN_NOT_AFTER_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
        need(mode != 'RESULT' or start >= run_not_after, 'K9_RESULT_WINDOW_BEFORE_RUN_NOT_AFTER')
        need(mode != 'LAUNCH' or (run_not_after.date() == start.date() and run_not_after > end), 'K9_DETACHED_RUN_LEAVES_THE_UTC_DAY_OF_ITS_LAUNCH')


def k9_e0_runner(ctx, constants):
    """The K4-E0 receipt the request cites, if any: complete, of this epoch, and the runner it delivered (read back inside
    its run) is the content-addressed runner whose hash the request's constants sign."""
    found = cited(ctx, K4E0_OPERATION)
    if not found:
        return None
    need(len(found) == 1, 'K9_E0_RECEIPT_NOT_ONE')
    role, receipt = found[0]
    need(complete_role(ctx, role) and receipt.get('outcome') == K4E0_OUTCOME and at(receipt, '/delivered/epoch') == K9_EPOCH, 'K9_E0_RECEIPT_NOT_COMPLETE')
    delivered = at(receipt, '/delivered/runner/sha256')
    need(is_hash(delivered) and delivered == at(receipt, '/effects/runner/sha256') == constants.get('runner_sha256')
         and at(receipt, '/delivered/runner/path') == K9_RUNNER_PATH % delivered and at(receipt, '/delivered/runner/bytes_equal_the_signed_bytes') is True,
         'K9_RUNNER_NOT_THE_ONE_E0_DELIVERED')
    return {'role': role, 'receipt_sha256': receipt['metadata_sha256'], 'runner_sha256': delivered}


def k9_tree_read(ctx, view, operation):
    """The one cited K9R TREE receipt of a daily request: complete in mode TREE, of the plan's boot; the rows of the five
    chains are its observed rows (also a PLAN_SOURCES row each); the week's constants are the ones it read under; it read
    the runner file and found the signed hash."""
    found = cited(ctx, K9R_OPERATION)
    need(len(found) == 1, 'K9_TREE_RECEIPT_NOT_CITED')
    role, receipt = found[0]
    need(complete_role(ctx, role) and receipt.get('mode') == 'TREE' and at(receipt, '/effects/mode') == 'TREE' and receipt.get('outcome') == K9_TREE_OUTCOME,
         'K9_TREE_RECEIPT_NOT_THE_COMPLETE_TREE_READ')
    need(is_hash(receipt.get('boot_id_sha256')) and receipt.get('boot_id_sha256') == view['boot'], 'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    shared = K9W_PLUG['constants_shared_with_the_tree_read'] if operation == K9W_OPERATION else None
    signed = at(receipt, '/effects/constants')
    if shared is None:
        need(type(signed) is dict and canonical(signed) == canonical(view['constants']), 'K9_CONSTANTS_NOT_THE_TREE_READS')
    else:
        need(type(signed) is dict and all(canonical(signed.get(key)) == canonical(view['constants'].get(key)) for key in shared), 'K9_CONSTANTS_NOT_THE_TREE_READS')
    need(at(receipt, '/items/runner_file/status') == 'COMPLETE' and at(receipt, '/items/runner_file/bytes_equal_signed') is True,
         'K9_TREE_READ_DID_NOT_FIND_THE_SIGNED_RUNNER')
    rows = view['parent_rows']
    need(type(rows) is dict and sorted(rows) == sorted(name for name, _ in K9R_CHAINS), 'PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT')
    for name, key in K9R_CHAINS:
        observed = at(receipt, '/items/directory:%s/observed_rows' % key)
        need(type(rows[name]) is dict and type(observed) is list and canonical(rows[name].get('rows')) == canonical(observed),
             'PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT')
    return {'role': role, 'receipt_sha256': receipt['metadata_sha256'], 'boot_id_sha256': receipt['boot_id_sha256'],
            'runner_sha256': view['constants'].get('runner_sha256')}


def k9_policy_rows(ctx, plan):
    """K9R POLICY (CONTRACT 2): the rows of the policy and release directories are copied by $from (or the parts of a $concat)
    from cited K11 (POST), K6a or K10 receipts of the plan's boot, never typed."""
    sources, operations = {}, {entry['role']: entry['operation'] for entry in ctx['entries']}
    for key in ('policy', 'release'):
        pointer = '/policy_read/%s/directory/rows' % key
        # one copy, or the parts of a {"$concat": [...]} (each part recorded under the member's pointer)
        copies = [item for item in ctx['copied'] if item.get('plan_pointer') == pointer]
        need(copies and all('evidence_role' in item and operations.get(item['evidence_role']) in K9_POLICY_ROW_SOURCES
                            and complete_role(ctx, item['evidence_role'])
                            and at(ctx['receipts'][item['evidence_role']], '/effects/evidence_boot_id_sha256') == plan['evidence_boot_id_sha256']
                            for item in copies), 'K9_POLICY_ROWS_NOT_COPIED_FROM_A_CITED_RECEIPT')
        for item in copies:
            if item.get('receipt_transformation') == 'CREATED_DIRECTORY_CHAIN_V1':
                need(canonical(created_directory_chain_provenance(ctx, item)) == canonical(pointer_value(plan, pointer)),
                     'K9_POLICY_ROWS_NOT_COPIED_FROM_A_CITED_RECEIPT')
        sources[key] = [{'role': item['evidence_role'], 'receipt_pointer': item['receipt_pointer']} for item in copies]
    return sources


def k9_risk_order(entry, day, namespace):
    """bind (NOTE 3.3, 5.3-5.4, F13): the order whose exact bytes the owner signs, from the grid: cutoff_at = the start of the
    sources_result window; phase windows = preflight [its start, its end + 60 s], acquire and execute [their start, their
    run_not_after]. Canonical JSON bytes, instants as isoformat (+00:00)."""
    rows = {row['operation']: row for row in entry['rows'] if row.get('track') == 'POST'}
    need(all(name in rows for name in ('sources_result', 'preflight', 'acquire_launch', 'execute_launch')), 'K9_NO_GRID_ROW')
    cutoff = k9_iso(rows['sources_result']['not_before'])
    preflight_end = parse_utc(rows['preflight']['not_after'], 'K9_GRID_NOT_THE_NOTES') + timedelta(seconds=60)
    windows = {'preflight': {'not_before': k9_iso(rows['preflight']['not_before']), 'not_after': preflight_end.isoformat()},
               'acquire': {'not_before': k9_iso(rows['acquire_launch']['not_before']), 'not_after': k9_iso(rows['acquire_launch']['run_not_after'])},
               'execute': {'not_before': k9_iso(rows['execute_launch']['not_before']), 'not_after': k9_iso(rows['execute_launch']['run_not_after'])}}
    order = {'schema': K9_RISK_ORDER_SCHEMA, 'scope': {'namespace': namespace, 'session_date': day, 'cutoff_at': cutoff, 'phases': list(K9_RISK_PHASES)},
             'actions': list(K9_RISK_ACTIONS)}
    return order, canonical(order), cutoff, windows


def k9_bind_order(plan, view, entry):
    """K9W bind: the order's exact bytes (ASCII text in the plan) are the grid's order for D, with the signed namespace; its
    sha256 as signed; cutoff_at and phase_windows the grid's."""
    members = k9w_bind_members(plan, view['operation'])
    if members is None:
        return None
    namespace = members['namespace']
    need(type(namespace) is str and namespace in [prefix + view['day'] for prefix in K9W_PLUG['risk_namespace_prefixes']], 'K9_BIND_NAMESPACE_NOT_ACCEPTED')
    try:
        raw = members['owner_order_text'].encode('ascii')
    except UnicodeEncodeError:
        raise Refused('K9_BIND_ORDER_NOT_THE_GRIDS')
    expected, expected_raw, cutoff, windows = k9_risk_order(entry, view['day'], namespace)
    need(raw == expected_raw and members['owner_order_sha256'] == sha(raw), 'K9_BIND_ORDER_NOT_THE_GRIDS')
    need(members['cutoff_at'] == cutoff and canonical(members['phase_windows']) == canonical(windows), 'K9_BIND_ORDER_NOT_THE_GRIDS')
    return {'owner_order_sha256': sha(raw), 'owner_order_bytes': len(raw), 'namespace': namespace, 'session_date': view['day'], 'cutoff_at': cutoff,
            'phase_windows': windows}


def k9_compiled_constants(constants):
    """The week's constants that are known (above): the runner (also K4-E0's), the risk source pins, the step table, the floor,
    the placement."""
    need(constants.get('runner_sha256') == K9_RUNNER_SHA256, 'K9_RUNNER_NOT_THE_REVIEWED_ONE')
    need(constants.get('risk_source_pins_sha256') == K9_RISK_SOURCE_PINS_SHA256 and constants.get('disk_floor_bytes') == K9_DISK_FLOOR_BYTES
         and constants.get('step_table_sha256') == K9_STEP_TABLE_SHA256 and type(constants.get('placement')) is dict
         and all(constants['placement'].get(key) == value for key, value in K9_PLACEMENT_PATHS.items())
         and constants['placement'].get('k9_open_root') is None, 'K9_CONSTANTS_NOT_THE_COMPILED_ONES')


def k9_on_the_data_volume(path):
    return type(path) is str and (path == K9_DATA_VOLUME or path.startswith(K9_DATA_VOLUME + '/'))


def k9_root_controlled(rows):
    """N-8: a chain of the K9 tree, every row of group 0 and without the setgid bit (the owner and the write bits are the core's)."""
    need(type(rows) is list and rows and all(type(row) is dict and row.get('gid') == 0 and type(row.get('mode')) is int and not row['mode'] & stat.S_ISGID
                                             for row in rows), 'K9_CHAIN_NOT_ROOT_CONTROLLED')


def k9_prerequisite_window(ctx, days, band):
    """K4-E0 and K3-K9 (no grid): a UTC day of the band of A2, at least 180 sendable seconds (no container is started)."""
    window = ctx['window']
    day = window['start'].date().isoformat()
    need(day in days and datetime.fromisoformat(day + 'T' + band[0] + '+00:00') <= window['start']
         and window['end'] <= datetime.fromisoformat(day + 'T' + band[1] + '+00:00'), 'K9_PREREQUISITE_WINDOW_NOT_IN_ITS_BAND')
    sendable = k9_sendable_seconds(window['gate_start'], window['gate_end'] - timedelta(seconds=ctx['watchdog']), False)
    need(sendable >= K9_MIN_SENDABLE_SECONDS, 'K9_SENDABLE_SECONDS_BELOW_180')
    return sendable


def k4e0_rules(ctx):
    """K4 mode E0 (CONTRACT 4): the rows of /, /mnt, /mnt/day-d-data and of /, /var, /var/lib and the boot from one cited
    complete precheck (PLAN_SOURCES); the K9 chain root-controlled; the runner's bytes from the runner file (an input, never
    typed), its hash the week's runner and its path the content-addressed one; the window in A2's E0 band."""
    plan, m = ctx['plan'], ctx['rt']['source']
    # K4-E0 PLUG: matched to its revision 4 (sealed 63c75348..., decision 6): plan keys parent, runner, evidence_boot_id_sha256;
    # its compiled SOURCE_ROOT and K9_ROOT must be the placement's (revision 2, 394f1b27..., is refused here).
    need(getattr(m, 'SOURCE_ROOT', K9_PLACEMENT_PATHS['source_root']) == K9_PLACEMENT_PATHS['source_root']
         and getattr(m, 'K9_ROOT', K9_ROOT) == K9_ROOT, 'K9_PROGRAM_NOT_OF_THIS_PLACEMENT')

    prechecks = cited(ctx, PRECHECK_OPERATION)
    need(len(prechecks) == 1 and complete_role(ctx, prechecks[0][0]), 'K4E0_EVIDENCE_NOT_ONE_COMPLETE_PRECHECK')
    runner = plan['runner']
    need(runner['sha256'] == K9_RUNNER_SHA256 == sha(ctx['inputs']['runner']), 'K9_RUNNER_NOT_THE_REVIEWED_ONE')
    need(runner['path'] == K9_RUNNER_PATH % runner['sha256'], 'K4E0_RUNNER_PATH_NOT_CONTENT_ADDRESSED')
    k9_root_controlled(plan['parent'])          # revision 4: one chain, /, /var, /var/lib, for both roots
    sendable = k9_prerequisite_window(ctx, K4E0_OPERATION_DAYS, bootstrap_prerequisite_band(ctx))
    return {'k9_prerequisite': {'program': 'K4E0', 'runner_sha256': runner['sha256'], 'runner_bytes': runner['bytes'], 'precheck_role': prechecks[0][0],
                                'sendable_seconds': sendable}, 'dispatch_gates': []}


# ---------------------------------------------------------------- K3-K9 PLUG: K3-K9 is being revised (2026-10-04) to sign the
# identity rows of the September source files taken from the K9R TREE read; neither the revised plan nor the TREE member
# holding those rows existed when this was written. What the binder assumes is here and nowhere else.
K3K9_PLUG = {'status': 'PROVISIONAL_UNTIL_K3K9_IS_SEALED',
             'secrets_chain': 'secrets_chain', 'data_volume_chain': 'data_volume_chain', 'source_rows': 'source_rows',
             'worker': 'worker_container_id', 'boot': 'evidence_boot_id_sha256',
             # the TREE read K3-K9 cites may be taken before K3-K9 writes the secrets: then its only findings are the absent secret files
             'tree_findings_allowed': ('SECRET_FILE_ABSENT',)}


def k3k9_rules(ctx):
    """K3-K9 (DESIGN 3): one cited K4-E0 receipt (complete), one K11 POST readback (complete) and one K9R TREE read (mode TREE;
    complete, or with no finding but absent secret files), all of the plan's boot; the secrets chain is the TREE read's rows
    of the secrets directory (root-controlled), the data volume chain copied from it ($from, ending at the volume); the
    September rows copied by $from from the TREE receipt, the worker's ID and boot from the same complete POLICY receipt, after TREE; the window in A2's band."""
    if cited(ctx,BOOTSTRAP_OPERATION):return bootstrap_k3k9_rules(ctx)
    plan, names = ctx['plan'], K3K9_PLUG
    boot = plan[names['boot']]
    e0, posts = cited(ctx, K4E0_OPERATION), cited(ctx, EPOCH_READBACK_OPERATION)
    trees=[row for row in cited(ctx,K9R_OPERATION) if row[1].get('mode')=='TREE']
    need(len(e0) == 1 and len(posts) == 1 and len(trees) == 1, 'K3K9_EVIDENCE_NOT_E0_POST_AND_TREE')
    (e0_role, e0_receipt), (post_role, post), (tree_role, tree) = e0[0], posts[0], trees[0]
    need(complete_role(ctx, e0_role) and e0_receipt.get('outcome') == K4E0_OUTCOME and complete_role(ctx, post_role) and post.get('mode') == 'POST',
         'K3K9_EVIDENCE_NOT_COMPLETE')
    findings = tree.get('findings') if type(tree.get('findings')) is list else [None]
    need(tree.get('mode') == 'TREE' and at(tree, '/effects/mode') == 'TREE' and (complete_role(ctx, tree_role) or (
        tree.get('outcome') == 'OBSERVED_ALL_EXPECTATIONS_NOT_MET' and set(findings) <= set(names['tree_findings_allowed'])
        and at(tree, '/items/directory:SECRETS/status') == 'COMPLETE')), 'K3K9_TREE_READ_NOT_ACCEPTABLE')
    need(all(value == boot for value in (at(e0_receipt, '/effects/evidence_boot_id_sha256'), at(post, '/effects/evidence_boot_id_sha256'),
                                         tree.get('boot_id_sha256'))), 'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    secrets, volume = plan[names['secrets_chain']], plan[names['data_volume_chain']]
    need(canonical(secrets) == canonical(at(tree, '/items/directory:SECRETS/observed_rows')) and type(volume) is list and volume
         and volume[-1].get('path') == K9_DATA_VOLUME, 'PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT')
    k9_root_controlled(secrets)
    for member, role, code in ((names['source_rows'], tree_role, 'K3K9_SOURCE_ROWS_NOT_COPIED_FROM_THE_TREE_READ'),
                               (names['data_volume_chain'], tree_role, 'K3K9_SOURCE_ROWS_NOT_COPIED_FROM_THE_TREE_READ')):
        copies = [item for item in ctx['copied'] if item.get('plan_pointer') == '/' + member or item.get('plan_pointer', '').startswith('/' + member + '/')]
        need(copies and all(item.get('evidence_role') == role for item in copies), code)
    identity=policy_worker_identity(ctx)
    policy=ctx['receipts'][identity['evidence_role']]
    try:
        ordered=datetime.fromisoformat(at(tree,'/clock/utc_end'))<=datetime.fromisoformat(at(policy,'/clock/utc_start'))
    except (ValueError,TypeError):ordered=False
    need(ordered,'POLICY_IDENTITY_NOT_AFTER_TREE')
    sendable = k9_prerequisite_window(ctx, K4E0_OPERATION_DAYS, K4E0_BAND)
    return {'k9_prerequisite': {'program': 'K3K9', 'e0_role': e0_role, 'post_role': post_role, 'tree_role': tree_role,
                                'policy_role':identity['evidence_role'],'tree_complete': complete_role(ctx, tree_role), 'sendable_seconds': sendable}, 'dispatch_gates': []}
# ---------------------------------------------------------------- end of the K3-K9 PLUG


def k9_rules(ctx):
    """K9_INTERFACE_NOTE.md section 10.4 (see the head of this section), for K9R and K9W. Returns the sheet member rules."""
    operation, plan, params, m, window = ctx['operation'], ctx['plan'], ctx['params'], ctx['rt']['source'], ctx['window']
    operations = k9_operation_list()
    # the sealed program speaks of this interface (where its source names it)
    need(all(getattr(m, name, value) == value for name, value in (('K9_NOTE_SHA256', K9_NOTE_SHA256), ('K9_OPERATIONS_SHA256', K9_OPERATIONS_SHA256),
                                                                 ('K9_EPOCH', K9_EPOCH), ('K9W_NOTE_SHA256', K9_NOTE_SHA256),
                                                                 ('K9W_OPERATIONS_SHA256', K9_OPERATIONS_SHA256), ('K9W_EPOCH', K9_EPOCH),
                                                                 ('K9W_STEP_TABLE_SHA256', K9_STEP_TABLE_SHA256)))
         and tuple(getattr(m, 'K9_DAYS', K9_DAYS)) == tuple(getattr(m, 'K9W_DAYS', K9_DAYS)) == K9_DAYS, 'K9_PROGRAM_NOT_OF_THIS_INTERFACE')
    need(ctx['watchdog'] == K9_WATCHDOG_SECONDS, 'K9_WATCHDOG_NOT_THE_GRIDS')
    need((window['gate_start'], window['gate_end']) == (window['start'], window['end']), 'K9_GATE_IS_THE_GRID_WINDOW')
    view = k9_view(operation, plan)
    need(view['epoch'] == K9_EPOCH and type(view['constants']) is dict and view['constants'].get('k9_interface_note_sha256') == K9_NOTE_SHA256,
         'K9_CONSTANTS_NOT_OF_THIS_INTERFACE')
    k9_compiled_constants(view['constants'])
    e0 = k9_e0_runner(ctx, view['constants'])
    common = {'program': 'K9R' if operation == K9R_OPERATION else 'K9W', 'note_sha256': K9_NOTE_SHA256, 'operation_list_sha256': K9_OPERATIONS_SHA256,
              'mode': view['mode'], 'runner_sha256': view['constants'].get('runner_sha256'), 'e0': e0}
    if view['mode'] == 'TREE':
        # the weekly prerequisite read (NOTE 4.1, 6.2): no grid row; it signs the runner E0 delivered
        need(operation == K9R_OPERATION and 'k9_grid' not in params and 'spare_of' not in params, 'K9_TREE_PLAN_INVALID')
        need(e0 is not None, 'K9_TREE_WITHOUT_THE_E0_RECEIPT')
        sendable = k9_sendable_seconds(window['start'], window['end'] - timedelta(seconds=ctx['watchdog']), False)
        need(sendable >= K9_MIN_SENDABLE_SECONDS, 'K9_SENDABLE_SECONDS_BELOW_180')
        return {'k9': dict(common, text_key='TREE', sendable_seconds=sendable, container_rule=False), 'dispatch_gates': []}
    need(view['mode'] in (('RESULT', 'PROBE', 'POLICY') if operation == K9R_OPERATION else K9W_PLUG['modes']), 'K9_MODE_NOT_OF_THIS_PROGRAM')
    need(type(view['day']) is str and view['day'] in K9_DAYS, 'K9_DAY_NOT_A_SESSION_WITH_A_K9_LIST')
    need(type(view['operation']) is str and operations.get(view['operation']) == (view['phase'], K9_PROGRAMS[operation]), 'K9_OPERATION_NOT_OF_THIS_PROGRAM')
    need(view['slot'] in K9_SLOTS, 'K9_SLOT_INVALID')
    need(view['attempt_key'] == k9_attempt_key(K9_EPOCH, view['day'], view['phase'], view['operation']), 'K9_ATTEMPT_KEY_NOT_RECOMPUTED')
    need((view['slot'] == 'SPARE') == ('spare_of' in params), 'K9_SPARE_WITHOUT_ITS_PRIMARY')
    name = params.get('k9_grid')
    need(type(name) is str and name in K9_GRIDS, 'K9_GRID_NOT_NAMED')
    row, entry = k9_grid_row(k9_grid(), name, view['day'], view['operation'], view['slot'])
    k9_dated_reserve(name, view['day'], row)
    need((row.get('kind'), row.get('phase'), row.get('mode')) == (K9_PROGRAMS[operation], view['phase'], view['mode']), 'K9_GRID_ROW_NOT_OF_THIS_MODE')
    if view['mode'] == 'RESULT':
        launch = k9_launch_of(entry, row)
        expected = k9_iso(launch['run_not_after'])
    elif operation == K9W_OPERATION and view['mode'] in K9W_PLUG['run_not_after_modes']:
        launch, expected = None, k9_iso(row['run_not_after'])
    else:
        launch, expected = None, None
    need(view['run_not_after'] == expected, 'K9_RUN_NOT_AFTER_NOT_THE_GRIDS')
    # the programs' own window rules (applied by them only on the host, after the claim) first, then the grid's row
    k9_day_window(view['day'], view['mode'], window['start'], window['end'], None if expected is None else datetime.fromisoformat(expected))
    if operation == K9W_OPERATION:
        k9w_window_rules(view, window['start'], window['end'], None if expected is None else datetime.fromisoformat(expected),
                         window['gate_end'] - timedelta(seconds=ctx['watchdog']))
    container = view['mode'] in K9_CONTAINER_MODES
    sendable = k9_sendable_seconds(window['start'], window['end'] - timedelta(seconds=ctx['watchdog']), container)
    need(sendable >= K9_MIN_SENDABLE_SECONDS, 'K9_SENDABLE_SECONDS_BELOW_180')
    need((zulu(window['start']), zulu(window['end'])) == (row['not_before'], row['not_after']), 'K9_WINDOW_NOT_THE_GRIDS')
    tree = k9_tree_read(ctx, view, operation)
    for chain, _ in K9R_CHAINS:          # decision 6: every chain off the data volume (with its placement: all five) root-controlled
        if not k9_on_the_data_volume(K9_PLACEMENT_PATHS[chain]):
            need(view['parent_rows'][chain].get('open_root') is None, 'K9_CHAIN_NOT_ROOT_CONTROLLED')
            k9_root_controlled(view['parent_rows'][chain]['rows'])
    policy = k9_policy_rows(ctx, plan) if view['mode'] == 'POLICY' else None
    order = k9_bind_order(plan, view, entry) if operation == K9W_OPERATION else None
    return {'k9': dict(common, text_key=view['operation'], operation=view['operation'], phase=view['phase'], slot=view['slot'], day=view['day'],
                       eve=entry.get('eve'), grid=name, grid_sha256=K9_GRID_SHA256, track=row.get('track'), window_not_before=row['not_before'],
                       window_not_after=row['not_after'], run_not_after=expected, launch=None if launch is None else launch['operation'],
                       attempt_key=view['attempt_key'], sendable_seconds=sendable, container_rule=container, tree=tree, policy_rows=policy,
                       risk_order=order),
            'dispatch_gates': []}


def k9_spare_of_its_primary(ctx, primary):
    """A K9 SPARE (spare_rules): the PRIMARY's request but for slot, window and run_not_after; the PRIMARY is the PRIMARY
    slot of the same grid, operation and day (the attempt key, which has no slot, is therefore the same)."""
    try:
        theirs = strict_json(primary['files']['REQUEST.BOUND.json'], 'K9_SPARE_NOT_OF_ITS_PRIMARY')['plan']
        rules = primary['sheet']['hostops02']['rules']['k9']
        mine_view, their_view = k9_view(ctx['operation'], ctx['plan']), k9_view(ctx['operation'], theirs)
        varying = {'window', K9W_PLUG['members']['slot'], K9W_PLUG['members']['run_not_after']} if ctx['operation'] == K9W_OPERATION else {'window', 'slot', 'run_not_after'}
        same = canonical({key: value for key, value in theirs.items() if key not in varying}) == canonical(
            {key: value for key, value in ctx['plan'].items() if key not in varying})
        ok = (same and (their_view['slot'], mine_view['slot']) == ('PRIMARY', 'SPARE') and rules.get('grid') == ctx['params'].get('k9_grid')
              and rules.get('operation') == mine_view['operation'])
    except (KeyError, TypeError, AttributeError):
        ok = False
    need(ok, 'K9_SPARE_NOT_OF_ITS_PRIMARY')


RULES_OF.update({K9R_OPERATION: k9_rules, K9W_OPERATION: k9_rules, K4E0_OPERATION: k4e0_rules, K3K9_OPERATION: k3k9_rules})
# Where each bound value of a daily K9 request comes from (K9R CONTRACT 2): the rows of the five chains and the boot, from
# the cited TREE receipt (a K9R receipt), whether typed or copied by $from. A TREE request carries null there (no row).
PLAN_SOURCES[K9R_OPERATION] = tuple(('/parent_rows/%s/rows' % name, K9R_OPERATION, '/items/directory:%s/observed_rows' % key) for name, key in K9R_CHAINS) + (
    ('/evidence_boot_id_sha256', K9R_OPERATION, '/boot_id_sha256'),)
PLAN_SOURCES[K4E0_OPERATION] = (('/parent', PRECHECK_OPERATION, '/items/chains/VAR_LIB/rows'),          # K4-E0 revision 4 (sealed 63c75348...)
                                 ('/evidence_boot_id_sha256', PRECHECK_OPERATION, BOOT_POINTER))
PLAN_SOURCES[K9W_OPERATION] = tuple(('/%s/%s/rows' % (K9W_PLUG['members']['parent_rows'], name), K9R_OPERATION, '/items/directory:%s/observed_rows' % key)
                                    for name, key in K9R_CHAINS) + (('/' + K9W_PLUG['members']['boot'], K9R_OPERATION, '/boot_id_sha256'),)


def usable_minutes(start, end):
    """How many of the minutes that begin or are under way between start and end are not minutes to avoid."""
    moment, count = start.replace(second=0), 0
    while moment <= end:
        if moment >= start - timedelta(seconds=59) and not any(low <= moment.minute <= high for low, high in MINUTES_TO_AVOID):
            count += 1
        moment += timedelta(minutes=1)
    return count


def minutes_allowed(start, end):
    """True when the gate leaves at least MIN_USABLE_MINUTES minutes that are not minutes to avoid: the dispatcher's
    prepare, the publication of the intent and the resume all happen outside them (check refuses a dispatch inside them)."""
    return usable_minutes(start, end) >= MIN_USABLE_MINUTES


def in_a_minute_to_avoid(moment):
    return any(low <= moment.minute <= high for low, high in MINUTES_TO_AVOID)


# ---- the spare (A9', M1', M3'): a second bound set over the same payload, used only if the primary was never sent
def primary_claim(sheet, go_sha256, now=None):
    """(the primary's claim root is at its signed identity, what is in it). The rule of K10 (CONTRACT 6, step 15;
    binding/predispatch.py role spare): the claim .go-<sha256 of the primary's GO>.claim, which the dispatcher creates at ITS
    PREPARE, before the publication and before any spawn, means "prepared". Here ANY entry of the primary's claim root counts
    as prepared (an attempt directory or an intent whose claim file was removed included). Returns (found, prepared, state):
    state EMPTY; PREPARED_NEVER_SENT_PAST_ITS_LATEST_START (exactly the claim and <label>-once holding only intent.json, and
    `now` past the primary's latest start: its resume is refused before spawn.claim, so it can never be sent); OTHER."""
    identity = sheet['claim_root_identity']
    try:
        found = claim_identity(Path(identity['path'])) == identity
    except Refused:
        found = False
    if not found:
        return False, None, None
    root = Path(identity['path'])
    try:
        entries = sorted(os.listdir(str(root)))
    except OSError:
        return True, True, 'OTHER'
    if not entries:
        return True, False, 'EMPTY'
    attempt = root / (sheet['label'] + '-once')
    try:
        inside = sorted(os.listdir(str(attempt))) if attempt.is_dir() and not attempt.is_symlink() else None
    except OSError:
        inside = None
    latest = parse_utc(sheet['window']['latest_start'])
    if (entries == sorted(['.go-' + go_sha256 + '.claim', sheet['label'] + '-once']) and inside == ['intent.json']
            and now is not None and now > latest):
        return True, True, 'PREPARED_NEVER_SENT_PAST_ITS_LATEST_START'
    return True, True, 'OTHER'


def spare_allowed(operation, state):
    """Whether a spare may still replace its primary: the primary's root empty, or (K2a, K6a) prepared and provably never
    sent. Anything else (sent, uncertain, refused on the host, an unexpected content) is never replaced by a spare."""
    return state == 'EMPTY' or (state == 'PREPARED_NEVER_SENT_PAST_ITS_LATEST_START' and operation in SPARE_AFTER_A_PREPARED_PRIMARY)


def spare_registry(primary_bound):
    """The one spare a primary may have, recorded beside the primary's directory (never inside a bound set): created with
    the spare's prepare, exclusively, so that a second spare of the same primary is refused, and read by the spare's gate."""
    return Path(primary_bound).parent / (Path(primary_bound).name + '.SPARE.json')


def spare_rules(ctx):
    item = ctx['params']['spare_of']
    need(type(item) is dict and set(item) == {'bound'} and type(item['bound']) is str, 'PARAMETERS_INVALID')
    path = Path(item['bound'])
    try:
        primary = signed_state(path if path.is_absolute() else ctx['base'] / path)
    except Refused:
        raise Refused('SPARE_PRIMARY_NOT_A_SIGNED_SET')
    sheet = primary['sheet']
    need(sheet['operation'] == ctx['operation'] and sheet['mode'] == ctx['mode'] and sheet.get('family') == ctx['seal']
         and sheet['host_binding_sha256'] == ctx['host'] and sheet['source_sha256'] == ctx['source_sha256'] and sheet['label'] != ctx['params']['label']
         and type(sheet.get('hostops02')) is dict and sheet['hostops02'].get('spare_of') is None, 'SPARE_PRIMARY_NOT_OF_THIS_OPERATION')
    if ctx['operation'] in K9_PROGRAMS:
        # rev 4: a K9 SPARE is its own grid row (another window and slot), so its effects differ from the PRIMARY's in those
        # members only: k9_spare_of_its_primary compares everything else (NOTE 5.7 rules 3 and 4)
        k9_spare_of_its_primary(ctx, primary)
    else:
        need(primary['files'].get('EFFECTS.json') == pretty(ctx['effects']), 'SPARE_EFFECTS_NOT_THE_PRIMARYS')
    need(ctx['window']['gate_start'] >= primary['window']['gate_end'], 'SPARE_WINDOW_NOT_AFTER_THE_PRIMARY')
    need(not os.path.lexists(str(spare_registry(primary['bound']))), 'SPARE_ALREADY_BOUND_FOR_THIS_PRIMARY')
    go_sha = sha(primary['raws'][2])
    found, claimed, state = primary_claim(sheet, go_sha, ctx['now'])
    need(found, 'SPARE_PRIMARY_CLAIM_ROOT_NOT_FOUND')
    need(spare_allowed(ctx['operation'], state), 'SPARE_PRIMARY_ALREADY_PREPARED')
    return {'label': sheet['label'], 'bound': str(primary['bound']), 'prepare_json_sha256': sha(primary['sheet_raw']), 'request_sha256': sheet['request_sha256'],
            'go_sha256': go_sha, 'claim_root_identity': sheet['claim_root_identity'], 'claim_name': '.go-' + go_sha + '.claim',
            'gate_not_after': sheet['window']['gate_not_after'], 'latest_start': sheet['window']['latest_start'],
            'registry': str(spare_registry(primary['bound'])),
            'replaces_a_prepared_primary_past_its_latest_start': ctx['operation'] in SPARE_AFTER_A_PREPARED_PRIMARY}


def hostops02_prepare(ctx):
    """Everything a HOSTOPS02 contract asks of the binder before the owner is asked, on top of the core profile's checks:
    the operation's own rules, the input files, the spare, the minutes to avoid. Returns the sheet member `hostops02`."""
    operation, plan = ctx['operation'], ctx['plan']
    required_inputs(ctx['used'], input_members(operation, plan))
    compared = {'override'} if operation == ACTIVATE_OPERATION else set()          # K6a's override: compared with the derived bytes, not carried
    need(set(ctx['inputs']) - compared == {item['input'] for item in ctx['used']}, 'BIND_INPUT_NOT_USED')
    if HOSTOPS02[operation]['minutes']:
        need(minutes_allowed(ctx['window']['gate_start'], ctx['window']['gate_end'] - timedelta(seconds=ctx['watchdog'])), 'GATE_WINDOW_ONLY_IN_MINUTES_TO_AVOID')
    try:
        rules = RULES_OF[operation](ctx)
    except (KeyError, TypeError, IndexError, AttributeError, ValueError) as error:
        if isinstance(error, Refused):
            raise
        raise Refused('HOSTOPS02_RULE_INPUT_MALFORMED')
    spare = spare_rules(ctx) if 'spare_of' in ctx['params'] else None
    linux_job = linux_job_of(ctx) if 'linux_job' in ctx['params'] else None
    need(linux_job is not None or ctx['mode'] == REHEARSAL or operation not in (CATALOG_OPERATION, ACTIVATE_OPERATION) + K9_PREREQUISITES,
         'LINUX_JOB_RECORD_REQUIRED')          # rev 4: K4-E0 and K3-K9 (CONTRACT 1 of each: the Linux-root job before any GO)
    rules['linux_job'] = linux_job
    # A1 section 8: before each write, the co-auditor's written review that cites the hash of the BOUND request and of the
    # final payload of that write (both exist only after the signature), or his statement that the review of the unbound
    # bytes suffices for that operation. A waiver recorded by the owner replaces it.
    review_gate = ['CODEX_REVIEW_OF_THE_BOUND_SET'] if ctx['review']['kind'] == 'CODEX_REVIEWED' and ctx['request']['writes_allowed'] else []
    gates = list(rules.pop('dispatch_gates')) + review_gate + (['SPARE_PRIMARY_NEVER_PREPARED'] if spare else [])
    return {'core': ctx['core'], 'rules': rules, 'bind_inputs': {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in sorted(ctx['inputs'].items())},
            'plan_values_from_input_files': ctx['used'], 'spare_of': spare, 'dispatch_gates': gates,
            'minutes_to_avoid': [list(item) for item in MINUTES_TO_AVOID] if HOSTOPS02[operation]['minutes'] else [],
            'parameters_directory': str(ctx['base'])}


# ---- dispatch gates: evaluated by `check --gates FILE`, minutes before the dispatcher's prepare (and, for K10, its resume)
def load_gates(path, operation):
    raw = read_file(Path(path), 65536, 'GATES_FILE_INVALID')
    gates = strict_json(raw, 'GATES_FILE_INVALID')
    # No "reboot_pending_order": a pending reboot always fails the A9 gate. Leaving it pending and initialising the catalog
    # anyway is not in the weekend authority (A1 6.2): it is the owner's own act, with Codex's written reading, and a new
    # sheet he signs; never a file named at dispatch.
    allowed = {'schema', 'rehearsal', 'grid_read', 'm0', 'install', 'readback_post', 'codex_review'}
    need(type(gates) is dict and gates.get('schema') == GATES_SCHEMA and set(gates) <= allowed
         and all(type(value) is dict for key, value in gates.items() if key != 'schema'), 'GATES_FILE_INVALID')
    return gates, sha(raw), Path(path).resolve().parent


def gate_receipt(state, gates, key, operation, base, seals, failed, label):
    """One cited set (or, in a rehearsal, receipt file) of a gate, judged as a cited receipt is judged at prepare."""
    item = gates.get(key)
    if item is None or 'family' not in item:
        failed.append(label + (':NOT_GIVEN' if item is None else ':FAMILY_NOT_GIVEN'))
        return None, None, None
    sheet = state['sheet']
    try:
        blobs = {}
        entries, receipts, facts = load_evidence([dict(item, role='GATE', operation=operation, accept_not_complete=True)], base, sheet['mode'], sheet['host_binding_sha256'],
                                                 None, None, seals, blobs)
    except Refused as error:
        failed.append(label + ':' + str(error))
        return None, None, None
    return receipts['GATE'], facts[0], blobs['GATE']


def reload_cited(state, seals, family):
    """The receipts the bound request cites, read again from the paths of its PARAMETERS.json and judged again: their
    hashes must be the ones the request carries."""
    sheet, params = state['sheet'], strict_json(state['files']['PARAMETERS.json'], 'BOUND_CHANGED')
    request = strict_json(state['files']['REQUEST.BOUND.json'], 'BOUND_CHANGED')
    blobs = {}
    try:
        entries, receipts, facts = load_evidence(params['evidence'], Path(sheet['hostops02']['parameters_directory']), sheet['mode'],
                                                 sheet['host_binding_sha256'], family, sheet['family'], seals, blobs)
    except Refused:
        raise Refused('CITED_RECEIPTS_NOT_FOUND_AGAIN')
    need(entries == request['evidence'], 'CITED_RECEIPTS_NOT_FOUND_AGAIN')
    return entries, receipts, blobs


def evaluate_gates(state, gates, gates_base, seals, step, now, family):
    """The dispatch gates the sheet names, each with the constant names of what failed (empty: the gate allows)."""
    sheet, failed, facts = state['sheet'], [], {}
    request = strict_json(state['files']['REQUEST.BOUND.json'], 'BOUND_CHANGED')
    plan, operation = request['plan'], sheet['operation']
    required = sheet['hostops02']['dispatch_gates']
    if 'K2A_REHEARSAL_RECEIPT_OF_THESE_BYTES' in required:
        receipt, fact, blob = gate_receipt(state, gates, 'rehearsal', CATALOG_OPERATION, gates_base, seals, failed, 'K2A_REHEARSAL_RECEIPT')
        if receipt is not None:
            checks = k2a_rehearsal_checks(receipt, fact, sheet['family'], plan)
            failed.extend('K2A_REHEARSAL_RECEIPT:' + name for name, ok in sorted(checks.items()) if not ok)
            facts['rehearsal_receipt_sha256'] = fact['receipt_sha256']
            signed = (sheet['hostops02']['rules'].get('rehearsal_receipt') or {}).get('receipt_sha256')
            if signed is not None and signed != fact['receipt_sha256']:
                failed.append('K2A_REHEARSAL_RECEIPT:NOT_THE_ONE_THE_OWNER_WAS_SHOWN')
    if 'K2A_GRID_READ_PIN_NO_REBOOT' in required:
        receipt, fact, blob = gate_receipt(state, gates, 'grid_read', W1_OPERATION, gates_base, seals, failed, 'K2A_GRID_READ')
        if receipt is not None:
            sections = at(receipt, '/observation/sections') or {}
            pin = at(sections, '/data_volume/root/pin')
            boot, end = at(sections, '/runtime/boot/boot_epoch_utc'), at(sections, '/clock/utc_end')
            observed = sheet['hostops02']['rules'].get('precheck_observed_at')
            try:
                age = (now - datetime.fromisoformat(end)).total_seconds()
                same_boot = type(boot) is int and boot + BOOT_MARGIN_SECONDS <= datetime.fromisoformat(observed).timestamp() <= datetime.fromisoformat(end).timestamp()
            except (TypeError, ValueError):
                age, same_boot = None, False
            checks = {'COMPLETE_READ': fact['complete'] is True and all(at(sections, '/%s/status' % name) == 'COMPLETE'
                                                                      for name in ('runtime', 'data_volume', 'security_controller', 'clock')),
                      'PIN_PRESENT_REGULAR_ROOT_OWNED': type(pin) is dict and pin.get('exists') is True and (pin.get('type'), pin.get('uid'), pin.get('gid')) == ('file', 0, 0),
                      'NO_REBOOT_PENDING': at(sections, '/security_controller/reboot_pending') is False,
                      'SAME_BOOT_AS_THE_EVIDENCE': same_boot,
                      'TAKEN_MINUTES_BEFORE_THE_DISPATCH': age is not None and -GRID_READ_CLOCK_SKEW_SECONDS <= age <= GRID_READ_MAX_AGE_SECONDS}
            failed.extend('K2A_GRID_READ:' + name for name, ok in sorted(checks.items()) if not ok)
            facts['grid_read_receipt_sha256'] = fact['receipt_sha256']
    if 'K10_M0_PREDISPATCH_DISPATCH_ALLOWED' in required:
        receipt, fact, blob = gate_receipt(state, gates, 'm0', W1_OPERATION, gates_base, seals, failed, 'K10_M0')
        if receipt is not None and blob['source'] != 'bound':
            failed.append('K10_M0:NOT_A_BOUND_SET')
        elif receipt is not None:
            need(family is not None, 'GATES_NEED_THE_FAMILY')
            entries, receipts, cited_blobs = reload_cited(state, seals, family)
            precheck = [entry['role'] for entry in entries if entry['operation'] == PRECHECK_OPERATION][0]
            tool, tool_sha = binding_tool(family, 'predispatch.py')
            need(tool_sha == sheet['hostops02']['rules']['sunday_gate']['tool_sha256'], 'BINDING_TOOL_NOT_THE_ONE_OF_THE_PREPARE')
            spare = sheet['hostops02'].get('spare_of')
            blobs = {'request': state['files']['REQUEST.BOUND.json'], 'evidence': cited_blobs[precheck]['receipt'], 'm0-request': blob['request'],
                     'm0-receipt': blob['receipt'], 'm0-exit': blob['exit']}
            claim, readable = None, True
            if spare:
                try:
                    primary = signed_state(Path(spare['bound']))
                    blobs['primary-go'] = primary['raws'][2]
                    claim = primary_claim(primary['sheet'], spare['go_sha256'])[1]
                except Refused as error:
                    readable = False
                    failed.append('K10_M0:PRIMARY_SET_UNREADABLE:' + str(error))
            if readable:
                ctx = {'rt': state['rt'], 'source_sha256': sheet['source_sha256']}
                names, count = predispatch_checks(ctx, tool, step, 'spare' if spare else 'primary', blobs, now, claim)
                failed.extend('K10_M0:' + name for name in names)
                facts.update(m0_receipt_sha256=fact['receipt_sha256'], predispatch_checks=count, predispatch_step=step)
    if 'K11_POST_AFTER_THE_COMPLETE_INSTALL' in required:
        receipt, fact, blob = gate_receipt(state, gates, 'install', RELEASE_OPERATION, gates_base, seals, failed, 'K11_INSTALL')
        if receipt is not None:
            checks = {'COMPLETE': fact['complete'] is True and receipt.get('outcome') == RELEASE_INSTALLED_OUTCOME,
                      'THE_SIGNED_BYTES_ARE_INSTALLED': (at(receipt, '/installed/sha256'), at(receipt, '/installed/bytes')) == (plan['release']['sha256'], plan['release']['bytes'])}
            failed.extend('K11_INSTALL:' + name for name, ok in sorted(checks.items()) if not ok)
            facts['install_receipt_sha256'] = fact['receipt_sha256']
    if 'K6A_AFTER_THE_COMPLETE_POST_READBACK' in required:
        receipt, fact, blob = gate_receipt(state, gates, 'readback_post', EPOCH_READBACK_OPERATION, gates_base, seals, failed, 'K6A_READBACK_POST')
        if receipt is not None:
            live = plan['live_parent'][-1]['path'].rstrip('/') + '/' + plan['directory_name']
            checks = {'COMPLETE_POST': fact['complete'] is True and receipt.get('outcome') == POST_OUTCOME and receipt.get('gates_first_session_readback') is True,
                      'NO_VERIFY_CONTAINER_LEFT': at(receipt, '/items/containers/verify_container_present') is False,
                      'NO_WORKER_SERVICE_LEFTOVER': at(receipt, '/items/containers/worker_service_leftovers') == 0,
                      'SAME_RELEASE_POLICY_AND_LIVE_DIRECTORY': (at(receipt, '/effects/release/sha256'), at(receipt, '/effects/policy/sha256'),
                                                                 at(receipt, '/effects/live/path')) == (plan['release']['sha256'], plan['policy']['sha256'], live),
                      'SAME_BOOT': at(receipt, '/effects/evidence_boot_id_sha256') == plan['evidence_boot_id_sha256']}
            failed.extend('K6A_READBACK_POST:' + name for name, ok in sorted(checks.items()) if not ok)
            facts['readback_post_receipt_sha256'] = fact['receipt_sha256']
    if 'CODEX_REVIEW_OF_THE_BOUND_SET' in required:
        codex_review_gate(state, gates, gates_base, failed, facts)
    if 'SPARE_PRIMARY_NEVER_PREPARED' in required:
        spare = sheet['hostops02']['spare_of']
        try:
            primary = signed_state(Path(spare['bound']))
        except Refused as error:
            failed.append('SPARE:PRIMARY_SET_UNREADABLE:' + str(error))
        else:
            found, claimed, primary_phase = primary_claim(primary['sheet'], spare['go_sha256'], now)
            if not found or sha(primary['raws'][2]) != spare['go_sha256']:
                failed.append('SPARE:PRIMARY_CLAIM_ROOT_NOT_FOUND')
            elif not spare_allowed(operation, primary_phase):
                failed.append('SPARE:PRIMARY_WAS_PREPARED_ITS_CLAIM_EXISTS')
            facts['primary_claim_root'] = primary_phase
            try:
                registry = strict_json(read_file(spare_registry(primary['bound']), 65536, 'SPARE_REGISTRY_UNREADABLE'), 'SPARE_REGISTRY_UNREADABLE')
            except Refused:
                registry = None
            if not (type(registry) is dict and registry.get('schema') == SPARE_REGISTRY_SCHEMA and registry.get('primary_go_sha256') == spare['go_sha256']
                    and registry.get('spare_bound') == str(state['bound']) and registry.get('spare_prepare_json_sha256') == sha(state['sheet_raw'])):
                failed.append('SPARE:NOT_THE_REGISTERED_SPARE_OF_ITS_PRIMARY')
    return {'required': required, 'evaluated': True, 'failed': failed, 'facts': facts, 'step': step}


def codex_review_gate(state, gates, gates_base, failed, facts):
    """A1 section 8, at dispatch: "parecer escrito do Codex que cite o hash do pedido vinculado e do payload final daquela
    escrita; o parecer sobre o candidato não vinculado só basta se o próprio Codex escrever que basta para aquela operação".
    The gates file names the document: {"document_file": ..., "form": "BOUND_SET"} must carry, as text, this set's request
    hash and final payload hash; {"form": "CANDIDATE_REVIEW_SUFFICES"} must carry the operation's name, its seal and its
    payload (source or unbound final) — the statement that it suffices is read by the operator, the binder records the form."""
    sheet, item = state['sheet'], gates.get('codex_review')
    if item is None:
        failed.append('CODEX_REVIEW:NOT_GIVEN')
        return
    if not (type(item) is dict and set(item) == {'document_file', 'form'} and type(item['document_file']) is str
            and item['form'] in ('BOUND_SET', 'CANDIDATE_REVIEW_SUFFICES')):
        failed.append('CODEX_REVIEW:INVALID')
        return
    path = Path(item['document_file'])
    try:
        raw = read_file(path if path.is_absolute() else gates_base / path, 1024 * 1024, 'CODEX_REVIEW_DOCUMENT_UNREADABLE')
    except Refused:
        failed.append('CODEX_REVIEW:UNREADABLE')
        return
    if item['form'] == 'BOUND_SET':
        ok = sheet['request_sha256'].encode('ascii') in raw and sha(state['payload']).encode('ascii') in raw
    else:
        assembly = sheet['hostops02']['core']['assembly']
        ok = (sheet['operation'].encode('ascii') in raw and sheet['family']['sha256sums_sha256'].encode('ascii') in raw
              and (sheet['source_sha256'].encode('ascii') in raw or assembly['final_payload_sha256'].encode('ascii') in raw))
    if not ok:
        failed.append('CODEX_REVIEW:DOES_NOT_NAME_' + ('THIS_REQUEST_AND_FINAL_PAYLOAD' if item['form'] == 'BOUND_SET' else 'THESE_BYTES'))
    facts['codex_review'] = {'form': item['form'], 'document_sha256': sha(raw)}


# ---- what the owner reads for a HOSTOPS02 request
HOSTOPS02_TEXT_PT = {
    CATALOG_OPERATION: (
        'inicialização do catálogo do journal de barras, operação 4b (GRAVAÇÃO; inicia um contêiner)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR E INICIA UM CONTÊINER. Ela roda uma vez o comando do README do supervisor (linhas 336 a 339 da '
        'release dd4ec4bb), palavra por palavra: um contêiner da imagem de ID assinado, sem rede, raiz somente leitura, sem capacidades, '
        'removido pelo próprio motor ao terminar, com o script fixado na entrada padrão. O contêiner cria maintenance.lock e epoch.json na '
        'pasta do journal que é ligada a ele.\n'
        'Antes do contêiner o programa só lê: as pastas assinadas, linha por linha a partir de "/", a imagem pelo ID e a lista de contêineres. '
        'Depois dele lê de novo a pasta e a lista de contêineres e confere o catálogo byte a byte.',
        'O que NÃO é feito: nada é removido, sobrescrito, renomeado, nem tem dono ou permissão trocados; nenhuma segunda execução numa pasta que '
        'já tenha algo; nenhum docker exec, shell, systemctl ou pull; nenhuma rede, token, manifesto, pasta de estado ou pasta de configuração '
        'dentro do contêiner; nenhuma opção que o README não escreva. Um tempo esgotado para o cliente docker, não o contêiner; nada desta '
        'família remove um contêiner que sobre.'),
    RELEASE_OPERATION: (
        'instalação da release da época, sem ativação (GRAVAÇÃO)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR. Ela cria uma pasta privada na raiz do volume de dados e, nela, o arquivo da release com exatamente '
        'os bytes cujo sha256 e tamanho o pedido assina, e relê esses bytes dentro da própria execução.\n'
        'Nenhum processo é iniciado: nenhum docker, nenhum systemctl, nenhum contêiner criado ou recriado, nada ativado. A release não é '
        'verificada pela aplicação aqui: isso é da releitura da época (K11).',
        'O que NÃO é feito: nada que exista é sobrescrito, renomeado, tem dono ou permissão trocados ou é removido (só o temporário desta '
        'execução, depois de provada a identidade dele); nenhum processo, docker, systemctl, shell ou rede; nenhuma ativação; nenhum '
        'contêiner recriado; nenhuma segunda tentativa.'),
    EPOCH_READBACK_OPERATION: (
        'releitura da época K11 (NÃO GRAVA; INICIA UM CONTÊINER)',
        'Esta consulta NÃO GRAVA NADA no servidor, mas INICIA UM CONTÊINER de verificação (detalhe abaixo). O programa lê: o boot, as pastas '
        'assinadas, a imagem, o contêiner do trabalhador e o seu ambiente (só verdadeiro ou falso, nunca os valores), a versão do deploy, o '
        'pino, as unidades listadas, o marcador de reinício, e faz um teste de um instante da trava de deploy.',
        'O que NÃO é feito: nenhum arquivo aberto para escrita, mkdir, chmod, chown, renomeação ou remoção; nenhum docker exec, compose up, '
        'pull ou shell; nenhuma rede para o contêiner; nenhuma montagem em que o contêiner possa escrever; nenhum systemctl além de show; '
        'nenhum daemon-reload; nenhuma espera e nenhuma segunda tentativa.'),
    ACTIVATE_OPERATION: (
        'ativação: política, override do compose e UMA recriação do r2d2-worker (GRAVAÇÃO)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR E RECRIA O CONTÊINER DO TRABALHADOR. Sob a trava de deploy ela cria uma pasta privada com dois '
        'arquivos (a política assinada e o override do compose com quatro valores) e roda uma única vez o docker compose up do serviço '
        'r2d2-worker com esse override, recriando só esse serviço.\n'
        'Nenhum valor lido de contêiner, da renderização ou do .env é impresso, gravado ou posto em argumento; do .env e do compose.yml '
        'nenhum byte, hash ou tamanho sai da execução.',
        'O que NÃO é feito: nenhum docker exec, shell, systemctl, pull ou build; nenhuma segunda recriação; o .env e o compose.yml não são '
        'alterados; nenhum arquivo é sobrescrito, renomeado, tem dono ou permissão trocados ou é removido (só os temporários desta execução); '
        'nenhuma unidade do systemd é ativada. O que é substituído: o contêiner antigo do trabalhador, que o docker compose remove ao recriar.\n'
        'Consequência que fica depois da execução: todo comando compose posterior deste projeto precisa nomear os mesmos dois arquivos (o '
        'compose.yml do deploy e este override); senão os quatro valores somem do trabalhador. Um deploy, que nomeia um arquivo só, faz '
        'exatamente isso. O override e a política ficam numa pasta que o trabalhador pode escrever: compará-los com os hashes do recibo antes '
        'de se apoiar neles.'),
}
OUTCOME_TEXT_PT = {
    (CATALOG_OPERATION, 'REAL'): (
        'Se o resultado for RECUSADO: nada foi criado e nenhum contêiner iniciado; a assinatura está gasta e a pasta continua utilizável com um '
        'pedido novo. Se for PARCIAL, vale o veredito da pasta no recibo: NOT_TO_BE_USED_AGAIN quer dizer uma pasta nova (provisão) e um pedido '
        'novo, duas assinaturas; CATALOG_VERIFIED_WITH_FINDINGS quer dizer catálogo verificado, mas o passo seguinte depende de uma leitura escrita '
        'sua e do Codex; UNTOUCHED_NO_CONTAINER_STARTED quer dizer pasta do journal intacta, mas a pasta de configuração do cliente docker da '
        'unidade não está vazia: toda execução seguinte destes bytes, inclusive a reserva, recusa até ela ser esvaziada, o que é uma remoção com '
        'autorização e bytes próprios. Se não houver recibo: a pasta é tratada como não utilizável de novo (sem recibo não se distingue uma '
        'execução que não começou de uma que começou), e uma leitura registra o que ficou. Nenhuma segunda execução nesta pasta.'),
    (CATALOG_OPERATION, 'REHEARSAL'): (
        'Se o resultado for RECUSADO: nada foi criado. Se for PARCIAL, ou se não houver recibo: é um achado do ensaio; a pasta real do journal não '
        'foi usada; as pastas descartáveis que existirem ficam; outro ensaio precisa de outro nome descartável; sem o recibo completo deste ensaio '
        'o catálogo real não é enviado. O recibo deste ensaio nunca é o recibo da operação 4b.'),
    (RELEASE_OPERATION, None): (
        'Se o resultado for RECUSADO: nada desta execução existe no servidor e, pela ordem assinada, a época não começa. Se for PARCIAL: algo desta '
        'execução existe; enquanto a decisão D-6 não for respondida por escrito por você e pelo Codex, vale a leitura estrita: a época não '
        'começa. Sem recibo: o estado é lido por uma consulta separada; nunca um segundo envio.'),
    (EPOCH_READBACK_OPERATION, 'PRE'): (
        'O resultado pode voltar PARCIAL (uma observação falhou ou o servidor não está como assinado): é resultado válido, não falha, e é um achado '
        'a corrigir antes de segunda; sem um PRE completo no perfil FULL nem a instalação nem a ativação de segunda são vinculadas. RECUSADO: nada '
        'foi observado e a assinatura está gasta. Sem recibo: um contêiner desta consulta pode ter sobrado, e só você o remove, por nome. Um recibo '
        'PRE nunca é a releitura da ordem (linha 7).'),
    (EPOCH_READBACK_OPERATION, 'POST'): (
        'Só o resultado completo (EPOCH_READBACK_POST_ALL_OBSERVED_ALL_EXPECTATIONS_MET) é a releitura da ordem (linha 7) e libera a ativação '
        '(M3). Se for PARCIAL ou RECUSADO, ou se não houver recibo: a ativação não é enviada e, pela ordem, a época não começa. Para uma releitura '
        'sem recibo, a ordem admite a ativação só depois de uma leitura que mostre nenhum contêiner hostops02-k11-*: essa exceção só você pode '
        'invocar, com outra leitura.'),
    (ACTIVATE_OPERATION, None): (
        'Se o resultado for RECUSADO: nada mudou e, pela ordem, a época não começa (salvo recusa local antes do envio, que não gasta nada). Se o '
        'trabalhador NÃO foi recriado (PARCIAL, com a pasta e os arquivos criados): a ativação não aconteceu e, pela ordem, a época não começa. Se '
        'o trabalhador foi recriado sem verificação completa, se o resultado for incerto ou se não houver recibo: o trabalhador pode estar parado '
        '(em seis dos oito estados intermediários de uma recriação nenhum trabalhador roda); você é avisado na hora; o estado é estabelecido por '
        'uma leitura, nunca por um segundo envio; se a época começa assim é a decisão em aberto D2, sua e do Codex. Depois de qualquer envio desta '
        'ativação, nenhum outro pedido de ativação (principal ou reserva) é usado.'),
}
GATE_TEXT_PT = {
    'K2A_REHEARSAL_RECEIPT_OF_THESE_BYTES': 'o recibo do ensaio destes mesmos bytes, do mesmo boot, com REHEARSAL_CATALOG_READY_VERIFIED, a mesma imagem, o '
                                            'mesmo script e o mesmo caminho no contêiner, e a pasta do cliente docker contada vazia depois das leituras '
                                            'e depois da execução;',
    'K2A_GRID_READ_PIN_NO_REBOOT': 'uma leitura W1 completa deste boot, de no máximo 60 minutos antes, mostrando o pino presente (arquivo de root:root) e '
                                   'nenhum reinício pendente (com reinício pendente este pedido não é enviado: seguir assim seria ato seu, com '
                                   'leitura escrita do Codex e outra folha);',
    'K10_M0_PREDISPATCH_DISPATCH_ALLOWED': 'a leitura M0 de segunda (W1, do mesmo dia, de no máximo uma hora), lida pela ferramenta binding/predispatch.py do '
                                           'pacote selado, que tem de responder DISPATCH_ALLOWED antes do prepare do dispatcher e de novo antes do envio;',
    'K11_POST_AFTER_THE_COMPLETE_INSTALL': 'o recibo KNOWN_COMPLETE da instalação da release (M1 ou M1\') com estes mesmos bytes;',
    'K6A_AFTER_THE_COMPLETE_POST_READBACK': 'o recibo KNOWN_COMPLETE da releitura M2 (K11 POST) do mesmo boot, com a mesma release, a mesma política e a mesma '
                                            'pasta, sem contêiner de verificação e sem sobra temporária do trabalhador;',
    'CODEX_REVIEW_OF_THE_BOUND_SET': 'um parecer escrito do Codex que cite o hash deste pedido e o do payload final (os dois só existem depois da sua '
                                     'assinatura), ou um escrito dele dizendo que o parecer sobre estes bytes não vinculados basta para esta operação;',
    'SPARE_PRIMARY_NEVER_PREPARED': 'que o pedido principal nunca foi enviado (ver o parágrafo da reserva).',
}
INPUT_NAMES_PT = {'release': 'release', 'policy': 'política', 'override': 'override do compose'}

# ---- rev 4: what the owner reads for a K9 request: one fixed text per K9 operation (NOTE 10.4), so that the 22 to 29 sheets
# of an eve can be told apart; the title shown is this one plus the session, the slot and the grid (k9_title_pt).
K9_LAUNCH_PT = {
    'collect_launch': 'a coleta do registro de símbolos e do contrato diário de 20 sessões da sessão D (provedor)',
    'commit_launch': 'o compromisso da lista causal no banco (compromisso, evento de auditoria e confirmação, pelo emissor empacotado)',
    'publish_launch': 'a publicação da lista causal (relay em arquivo, envelope privado na raiz das fontes e releitura verificada)',
    'components_launch': 'os componentes da lista confirmada (registro comprometido, 61 sessões diárias e resultados trimestrais)',
    'sources_launch': 'as fontes do risco (instantâneo oficial pelo papel restrito; fundamentos, notas e posições institucionais por nome)',
    'acquire_launch': 'a fase acquire do executor de risco empacotado',
    'execute_launch': 'a fase execute do executor de risco empacotado (risk.json e os demais arquivos de saída do risco)',
    'capture_launch': 'a captura das 10:00 de Nova York (snapshot e fita de cotações da sessão D)'}
K9R_RESULT_NEVER_PT = ('O que NÃO é feito: nada é gravado nem removido (o contêiner parado fica para o passo seguinte do K9W remover); nenhum '
                       'contêiner é iniciado; nenhuma lista de contêineres; nenhum valor de ambiente, segredo ou símbolo sai da execução. '
                       'FAILED ou UNCERTAIN encerra a fase do dia: nada é repetido (ORD:33).')
K9R_PROBE_PT = ('O programa K9R confere a pasta de segredos e os metadados do arquivo de ambiente do provedor (sem abrir) e roda UM contêiner '
                'anexado da imagem de ID assinado: rede bridge, raiz só de leitura, sem montagem, sem capacidades, removido pelo motor e encerrado '
                'em até 36 s, com o trecho fixado na entrada padrão. O trecho faz duas chamadas ao provedor (lista de símbolos e barras do fim do '
                'dia da sessão anterior) e aplica a regra 95/100 da época 28. Responde READY ou NOT_READY.')
K9W_NEVER_PT = ('O que NÃO é feito: nenhum docker exec, kill, stop ou pull; nenhuma remoção com -f ou -v; um contêiner anterior ainda em execução '
                'nunca é removido (o passo para como UNCERTAIN_PREVIOUS_RUNNING e você é avisado); nenhuma segunda tentativa. Se faltar algo de que o '
                'passo depende (passos anteriores COMPLETOS, destinos ausentes, símbolos, plano de risco, janela), o envio só remove o contêiner '
                'parado anterior e recusa (modo só-remoção). Espaço abaixo do piso, arquivos de segredo ou executor fora do exigido: recusa sem efeito.')
K9W_HEAD_PT = ('ESTA OPERAÇÃO GRAVA NO SERVIDOR. O programa K9W confere antes, só lendo, a árvore K9, o espaço livre contra o piso e o que o passo '
               'exige; depois cria a reivindicação exclusiva de uso único (claims/<attempt_key>.claim) e grava o plano do passo (days/<D>/plans/%s.json). ')
K9_TEXT_PT = {
    K9R_OPERATION: dict({
        'readiness_probe': ('K9 readiness_probe: sondagem de prontidão do provedor (NÃO GRAVA; INICIA UM CONTÊINER)', K9R_PROBE_PT,
                            'O que NÃO é feito: nenhum arquivo gravado, nenhuma pasta criada, nenhum banco de dados, nenhum contêiner removido, '
                            'nenhuma segunda tentativa. NOT_READY não é falha: a coleta PRIMÁRIA não é enviada e a re-sondagem (readiness_recheck) '
                            'roda uma hora depois.'),
        'readiness_recheck': ('K9 readiness_recheck: re-sondagem de prontidão, só depois de um NOT_READY (NÃO GRAVA; INICIA UM CONTÊINER)',
                              'A mesma sondagem, uma hora depois, enviada só se a sondagem anterior respondeu NOT_READY. ' + K9R_PROBE_PT,
                              'O que NÃO é feito: nenhum arquivo gravado, nenhuma pasta criada, nenhum banco de dados, nenhum contêiner removido, '
                              'nenhuma segunda tentativa. READY: roda a trilha RESERVA da lista causal. Dois NOT_READY: não há lista para D, a '
                              'sessão não tem admissão nem entradas novas, e você é avisado no mesmo dia.'),
        'policy_read': ('K9 policy_read: releitura da política e do trabalhador (SÓ LEITURA; NÃO INICIA CONTÊINER)',
                        'O programa K9R lê no servidor o arquivo da política instalado pela ativação e o arquivo da release, confere os hashes '
                        'assinados e a validade da política no instante da leitura, e lê o estado do contêiner r2d2-worker e cinco nomes do '
                        'ambiente dele, só como verdadeiro ou falso.',
                        'O que NÃO é feito: nenhum conteúdo da política, da release ou do ambiente sai da execução; nada é gravado, removido ou '
                        'iniciado; nenhuma segunda tentativa.'),
        'TREE': ('K9 TREE: leitura semanal da árvore K9 (SÓ LEITURA; NÃO INICIA CONTÊINER)',
                 'O programa K9R lê, a partir de "/" e sem seguir links, as pastas da árvore K9 em ' + K9_ROOT + ' e a raiz das fontes, com '
                 'dono, permissões e identidade de cada componente; os metadados (sem abrir) dos três arquivos de segredo; o hash do arquivo do '
                 'executor k9 entregue pela E0; o espaço livre contra o piso assinado; e o boot. As linhas e o boot que ela registrar são '
                 'assinados em todas as folhas K9 da semana: um reinício do servidor exige nova leitura e novas folhas.',
                 'O que NÃO é feito: nenhum segredo é aberto ou medido; nada é gravado, removido ou iniciado; nenhuma segunda tentativa.')},
        **{result: ('K9 %s: leitura do resultado de %s (SÓ LEITURA; NÃO INICIA CONTÊINER)' % (result, launch),
                    'O programa K9R lê o resultado de %s, que é %s: o registro de lançamento deste dia, o contêiner registrado pelo ID (estado e '
                    'código de saída, nunca o ambiente), o marcador de início e o recibo do passo (%s) e confere de novo, no servidor, o hash dos '
                    'arquivos que o recibo nomeia. Responde COMPLETE, FAILED ou UNCERTAIN.'
                    % (launch, K9_LAUNCH_PT[launch], 'do executor de risco empacotado, no spool' if launch in ('acquire_launch', 'execute_launch')
                       else 'do executor k9'), K9R_RESULT_NEVER_PT)
           for result, launch in (('collect_result', 'collect_launch'), ('commit_result', 'commit_launch'), ('publish_result', 'publish_launch'),
                                  ('components_result', 'components_launch'), ('sources_result', 'sources_launch'),
                                  ('acquire_result', 'acquire_launch'), ('execute_result', 'execute_launch'), ('capture_result', 'capture_launch'))}),
    K9W_OPERATION: {
        'collect_launch': ('K9 collect_launch: lança a coleta das entradas da lista causal (GRAVAÇÃO; CONTÊINER DESTACADO)',
                           K9W_HEAD_PT % 'collect_launch' + 'Cria a pasta do dia days/<D> (privada) e lança UM contêiner destacado da imagem de ID '
                           'assinado, rede do provedor, que roda o executor k9 fixado por hash: ' + K9_LAUNCH_PT['collect_launch'] + '. Grava o '
                           'registro de lançamento. O contêiner termina sozinho até o fim da execução desta folha e fica parado até o passo '
                           'seguinte removê-lo.', K9W_NEVER_PT),
        'commit_launch': ('K9 commit_launch: lança o compromisso da lista causal (GRAVAÇÃO; BANCO; CONTÊINER DESTACADO)',
                          K9W_HEAD_PT % 'commit_launch' + 'Remove o contêiner parado de collect_launch (só se exited e com a chave dele) e lança UM '
                          'contêiner destacado, rede interna do banco, com a senha do papel emissor montada só para leitura: '
                          + K9_LAUNCH_PT['commit_launch'] + '; o compromisso confirmado fica em causal/commitment.private.json. As linhas do banco '
                          'são só acrescentadas.', K9W_NEVER_PT),
        'publish_launch': ('K9 publish_launch: lança a publicação da lista causal (GRAVAÇÃO; BANCO; CONTÊINER DESTACADO)',
                           K9W_HEAD_PT % 'publish_launch' + 'Remove o contêiner parado de commit_launch e lança UM contêiner destacado, rede interna '
                           'do banco: ' + K9_LAUNCH_PT['publish_launch'] + '; grava control/symbols.txt.', K9W_NEVER_PT),
        'components_launch': ('K9 components_launch: lança os componentes da lista confirmada (GRAVAÇÃO; CONTÊINER DESTACADO)',
                              K9W_HEAD_PT % 'components_launch' + 'Remove o contêiner parado de publish_launch e lança UM contêiner destacado, rede '
                              'do provedor: ' + K9_LAUNCH_PT['components_launch'] + ', em components/<D>/ da raiz das fontes.', K9W_NEVER_PT),
        'sources_launch': ('K9 sources_launch: lança as fontes do risco (GRAVAÇÃO; BANCO E PROVEDOR; CONTÊINER DESTACADO)',
                           K9W_HEAD_PT % 'sources_launch' + 'Remove o contêiner parado de components_launch e lança UM contêiner destacado, com '
                           'banco (papel restrito de leitura) e provedor: ' + K9_LAUNCH_PT['sources_launch'] + ', gravado em risk/plan do dia.',
                           K9W_NEVER_PT),
        'bind': ('K9 bind: grava os documentos de risco do dia, com a ordem assinada nesta folha (GRAVAÇÃO; CONTÊINER ANEXADO SEM REDE)',
                 K9W_HEAD_PT % 'bind' + 'Roda UM contêiner anexado, sem rede, por até 35 s: o executor k9 grava em risk/plan do dia OWNER_ORDER.json '
                 'com exatamente os bytes da ordem desta folha, SOURCE_PINS.json, list.private.json, HOST_PLAN.json e GO.json (o GO de risco da '
                 'Fable, que cita o hash deste pedido), e cria risk/spool. Não copia nada.', K9W_NEVER_PT),
        'preflight': ('K9 preflight: fase preflight do executor de risco empacotado (GRAVAÇÃO; CONTÊINER ANEXADO SEM REDE)',
                      K9W_HEAD_PT % 'preflight' + 'Roda UM contêiner anexado, sem rede, por até 35 s: a fase preflight do executor de risco '
                      'empacotado, com o plano, o GO e os pinos do bind; ela grava o próprio recibo no spool.', K9W_NEVER_PT),
        'acquire_launch': ('K9 acquire_launch: lança a fase acquire do risco (GRAVAÇÃO; BANCO E PROVEDOR; CONTÊINER DESTACADO)',
                           K9W_HEAD_PT % 'acquire_launch' + 'Remove o contêiner parado de sources_launch e lança UM contêiner destacado, com banco '
                           'e provedor: ' + K9_LAUNCH_PT['acquire_launch'] + ', por até 60 min, a partir do recibo do preflight.', K9W_NEVER_PT),
        'execute_launch': ('K9 execute_launch: lança a fase execute do risco (GRAVAÇÃO; CONTÊINER DESTACADO SEM REDE)',
                           K9W_HEAD_PT % 'execute_launch' + 'Remove o contêiner parado de acquire_launch e lança UM contêiner destacado, sem rede: '
                           + K9_LAUNCH_PT['execute_launch'] + ', por até 20 min, a partir do recibo do acquire.', K9W_NEVER_PT),
        'stage': ('K9 stage: entrega o risk.json do dia à raiz das fontes (GRAVAÇÃO; CONTÊINER ANEXADO SEM REDE)',
                  K9W_HEAD_PT % 'stage' + 'Remove o contêiner parado de execute_launch e roda UM contêiner anexado, sem rede, por até 18 s, com a pasta do dia '
                  'só de leitura (menos a pasta de recibos): confere de novo risk.json e o manifesto contra o recibo do execute e os nomes contra a lista, e cria components/<D>/risk.json '
                  '(criação exclusiva) na raiz das fontes.', K9W_NEVER_PT),
        'capture_launch': ('K9 capture_launch: lança a captura das 10:00 de Nova York (GRAVAÇÃO; CONTÊINER DESTACADO)',
                           K9W_HEAD_PT % 'capture_launch' + 'Lança UM contêiner destacado, rede do provedor: ' + K9_LAUNCH_PT['capture_launch']
                           + ', na raiz das fontes, até 11:03 de Brasília. O contêiner fica parado até capture_cleanup removê-lo.', K9W_NEVER_PT),
        'capture_cleanup': ('K9 capture_cleanup: remove o contêiner parado da captura (GRAVAÇÃO: UMA REMOÇÃO)',
                            K9W_HEAD_PT % 'capture_cleanup' + 'Lê o registro de lançamento da captura, inspeciona esse contêiner e o remove com '
                            'docker rm (sem -f, sem -v) só se estiver exited e com a chave da captura; depois confere que ele não existe mais.',
                            'O que NÃO é feito: nenhum contêiner em execução é removido (nada é feito e você é avisado); nenhum outro contêiner '
                            'é tocado; nenhuma segunda tentativa.')}}
HOSTOPS02_TEXT_PT.update(K9_TEXT_PT)
HOSTOPS02_TEXT_PT.update({
    K4E0_OPERATION: (
        'K4 E0: cria a árvore K9 e entrega o executor k9 (GRAVAÇÃO)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR. Uma vez por época: cria em /var/lib/c3po a raiz das fontes e a árvore K9 ' + K9_ROOT + ' (tools, '
        'days, claims, secrets), cada pasta root:root 0700, e em tools o arquivo do executor k9 com exatamente os bytes cujo sha256 e tamanho '
        'o pedido assina (root:root 0600). /var/lib/c3po é criada só se não existir; se existir, tem de ser de root, fechada e sem setgid, e é '
        'usada sem mudança. Tudo é relido dentro da própria execução.',
        'O que NÃO é feito: nada que exista é sobrescrito, renomeado, tem dono ou permissão trocados ou é removido (só o temporário desta '
        'execução); nenhum processo, docker, systemctl, shell ou rede; nenhum segredo; nenhuma ativação; nenhuma segunda tentativa (um '
        'resultado parcial exige nomes novos e um pedido novo).'),
    K3K9_OPERATION: (
        'K3-K9: grava os segredos das fases K9 (GRAVAÇÃO; SEGREDOS EM REPOUSO)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR UMA SEGUNDA CÓPIA DE SEGREDOS. Em ' + K9_ROOT + '/secrets ela cria provider.env (os três tokens do '
        'provedor, copiados em memória do ambiente do trabalhador em execução, cujo ID o pedido assina), risk-db.env (a URL do papel restrito '
        'de leitura do risco, do arquivo de setembro) e emitter/password (a senha do papel emissor, do arquivo de setembro), todos root:root '
        '0600, e confere cada um por releitura de metadados.',
        'O que NÃO é feito: nenhum valor, tamanho ou hash de segredo sai da execução ou entra no recibo; nada que exista é sobrescrito, '
        'renomeado ou removido; os arquivos de setembro e o trabalhador só são lidos; nenhuma ativação; nenhuma segunda tentativa.')})          # a K9 program's entry is a table by K9 operation (TREE: the weekly read)
OUTCOME_TEXT_PT.update({
    (K9R_OPERATION, 'RESULT'): ('O recibo diz phase_result. Só COMPLETE (saída 0) libera o passo seguinte. FAILED ou UNCERTAIN encerra a fase do dia: '
                                'nada é repetido (ORD:33). RECUSADO: nada foi observado e a assinatura está gasta. Sem recibo: vale UNCERTAIN.'),
    (K9R_OPERATION, 'PROBE'): ('READY (saída 0) libera a coleta. NOT_READY (saída 2) leva à re-sondagem; qualquer outro achado vale como não pronto. '
                               'Sem recibo: não pronto; o contêiner da sondagem pode ter ficado no motor por no máximo 36 s.'),
    (K9R_OPERATION, 'POLICY'): ('Só o resultado completo (saída 0) diz que a política, a release e o trabalhador estão como assinados agora; '
                                'qualquer achado segura as operações que dependem deles. Sem recibo: nada se conclui.'),
    (K9R_OPERATION, 'TREE'): ('Só o resultado completo (K9_TREE_AS_REQUIRED_ALL_OBSERVED) permite vincular as folhas K9 da semana com as linhas e o '
                              'boot dele; qualquer achado (por exemplo, espaço abaixo do piso) segura todas elas. Um reinício do servidor invalida '
                              'esta leitura.'),
    (K9W_OPERATION, 'LAUNCH'): ('O envio só lança o contêiner; o resultado da etapa é lido depois, por uma leitura K9R assinada à parte. RECUSADO: '
                                'nada foi lançado (salvo a remoção do contêiner parado anterior, se feita). Qualquer resultado gasta esta '
                                'assinatura: a fase do dia não é repetida (ORD:33).'),
    (K9W_OPERATION, 'ATTACHED'): ('O contêiner roda até o fim dentro do envio e o recibo dele fica no servidor. Qualquer resultado gasta esta '
                                  'assinatura; um resultado que não seja completo encerra a fase do dia (ORD:33).'),
    (K9W_OPERATION, 'CLEANUP'): 'Só remove o contêiner parado da captura; se ele ainda estiver rodando, nada é removido e você é avisado.',
    (K9W_OPERATION, None): 'Qualquer resultado gasta esta assinatura; um resultado que não seja completo encerra a fase do dia (ORD:33).',
    (K4E0_OPERATION, None): ('Se o resultado for RECUSADO: nada foi criado e os mesmos bytes podem ser assinados de novo quando a causa sair. PARCIAL ou '
                             'sem recibo: algo pode existir; não há segunda tentativa com estes bytes nem remoção nesta família: a E0 é refeita '
                             'com nomes novos (pedido e revisão novos) ou as fases K9 não começam.'),
    (K3K9_OPERATION, None): ('Se o resultado for RECUSADO: nada foi criado. PARCIAL ou sem recibo: algum arquivo de segredo pode existir; o estado '
                             'é lido por uma consulta separada (TREE); nunca um segundo envio. Sem os três arquivos, as fases K9 não começam.')})


# ================================================================ rev 4: the other sealed programs of the epoch (one table)
# For each: the fixed owner text (title, body, what is never done), the outcome text, whether it starts a container (the
# A2 container rule), and its own extra rule. The common rule (sealed_program_rules), before the owner is asked: every
# operation its sealed source names in EVIDENCE_OPERATIONS is cited, each such receipt complete (in its signed mode); every
# cited receipt that names a boot names the plan's; the plan's mode is one of the source's; the window has at least 180
# sendable seconds (A2 section 3, the quiet bands, the container rule where it starts one); a write's Linux-job record is
# required in REAL. Their plans are checked by their own validate_plan (authenticate, at prepare). Seals: sealed directories
# read by command on 2026-10-05 (none accepted: ACCEPTED_SEALS.json is not edited; K12 rev 3 will replace rev 2's seals).
SEALED_PROGRAMS = {
    'GO_WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_01': {'key':'BOOTSTRAP_IDENTITY','container':False,'texts':(
        'BOOTSTRAP_IDENTITY: identidade do primeiro arranque e claim único da época (GRAVAÇÃO)',
        'Observa o boot e o ID do trabalhador em execução, confere a imagem, a revisão, a política, a release e as comparações LIVE. Confirma SECRETS vazio e as ausências pelos nomes fixos sob o pai conferido. Cria somente um claim exclusivo 0600 em CLAIMS, independente do GO, com fsync e releitura.',
        'O Python recebe cinco booleanos do ambiente; Docker CLI/daemon processam Config.Env. Não abre conteúdo de segredos nem cria EMITTER. Após criação possível do claim, o uso está consumido: sem remoção ou retry. O claim limita esta execução, sem provar uma única citação do recibo.'),
        'outcome':'Só o resultado completo com identidade observada e claim durável permite o K3 da primeira noite. Parcial, recusa ou incerteza mantém HOLD.'},
    'GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01': {'key':'PROBE','container':True,'seal':'FINAL_HASH_REQUIRED','texts':(
        'PROBE: leitura CALENDAR, IDENT ou LOAD em contêiner sem rede (SÓ LEITURA; INICIA CONTÊINER)',
        'Roda o script fixado na imagem assinada, sem rede e sem segredos. Os binds são somente de leitura; o engine remove os contêineres que esta operação criou. LOAD exige o recibo completo da montagem e a mesma cadeia de evidências.',
        'Não grava arquivos do host, não altera o trabalhador e não emite GO. Resultado parcial ou incerto mantém HOLD.'),
        'outcome':'Só o resultado completo do passo assinado permite o dependente; CALENDAR e IDENT não substituem LOAD.', 'extra':'capacity_probe_rules'},
    'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01': {'key': 'K8', 'container': False, 'seal': '1140de95', 'texts': (
        'K8 E6: entrega os documentos e o payload da véspera ao diretório de capacidade (GRAVAÇÃO)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR. Para a sessão do pedido, cria por criação exclusiva os documentos da véspera e o payload '
        '(contrato e lista causal confirmada, montado no servidor a partir do compromisso do commit) nas pastas existentes do diretório de '
        'capacidade, root:root 0600, e relê cada um. Os hashes e tamanhos estão em EFFECTS.json.',
        'O que NÃO é feito: nada que exista é sobrescrito, renomeado ou removido; nenhum contêiner, docker, systemctl, rede ou banco; '
        'nenhuma ativação; nenhuma segunda tentativa.'),
        'outcome': 'Só o resultado completo entrega a véspera; RECUSADO: nada foi criado; PARCIAL ou sem recibo: o estado é lido à parte, nunca um segundo envio.', 'extra': 'k8_rules'},
    'GO_WRITE_HOSTOPS02_K12_PREFLIGHT_01': {'key': 'K12p', 'container': True, 'seal': '0e086f2a (rev 2; rev 3 a caminho)', 'texts': (
        'K12p: pré-checagem da janela de capacidade no layout de despacho (GRAVAÇÃO; INICIA UM CONTÊINER)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR E INICIA UM CONTÊINER. Roda uma vez o escritor de capacidade em modo de pré-checagem no layout '
        'de despacho, com o pedido de capacidade assinado, os arquivos de configuração e de pinos exigidos root:root 0600 e o volume de '
        'dados só de leitura; grava só o que EFFECTS.json lista.',
        'O que NÃO é feito: nenhuma entrada de capacidade é executada; nada fora do layout listado é gravado; nenhum segredo é lido além de '
        'metadados; nenhuma segunda tentativa.'),
        'outcome': 'Só o resultado completo libera a janela K12; qualquer outro resultado a segura; nunca um segundo envio.', 'extra': 'k12_rules'},
    'GO_WRITE_HOSTOPS02_K12_WINDOW_01': {'key': 'K12w', 'container': True, 'seal': 'ed8fb52e (rev 2; rev 3 a caminho)', 'texts': (
        'K12w: um passo da janela de capacidade (LAUNCH, PERSIST, STOP ou REMOVE) (GRAVAÇÃO; CONTÊINER)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR. Executa um passo da janela de capacidade do dia, no modo assinado: lançar o contêiner do escritor '
        '(LAUNCH), gravar o recibo dele lido dos logs do contêiner encerrado e vinculado (PERSIST), parar (STOP) ou remover contêineres '
        'encerrados (REMOVE), sempre pelo ID e pelas etiquetas assinados.',
        'O que NÃO é feito: nenhum logs em follow, nenhum log bruto publicado, nenhuma remoção com -f ou -v, nenhum contêiner que não seja '
        'o assinado; nenhuma segunda tentativa.'),
        'outcome': 'Qualquer resultado gasta esta assinatura; um resultado que não seja completo encerra a janela do dia.', 'extra': 'k12_rules'},
    'GO_READONLY_HOSTOPS02_K12_COLLECT_01': {'key': 'K12c', 'container': False, 'seal': '388879ba (rev 2; rev 3 a caminho)', 'texts': (
        'K12c: leitura da capacidade (COLLECT ou TREE) (SÓ LEITURA; NÃO INICIA CONTÊINER)',
        'O programa só lê: no modo TREE, as pastas da árvore de capacidade a partir de "/"; no modo COLLECT, o estado do contêiner da janela '
        'pelo ID registrado e os recibos persistidos, com os hashes conferidos.',
        'O que NÃO é feito: nada é gravado, removido ou iniciado; nenhum log bruto ou segredo sai da execução.'),
        'outcome': 'Só o resultado completo vale como leitura da capacidade; PARCIAL é resultado válido e diz o que faltou.', 'extra': 'k12_rules'},
    'GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01': {'key': 'K6b', 'container': True, 'seal': 'f8c88581 (núcleo próprio core-k6b 979e8c83)', 'texts': (
        'K6b: chave de capacidade do trabalhador (GRAVAÇÃO; EDITA O .env; RECRIA O r2d2-worker)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR E RECRIA O CONTÊINER DO TRABALHADOR. No modo assinado, edita no lugar só o bloco final de capacidade '
        'do .env do deploy (por um contêiner da imagem assinada, sem rede, raiz só de leitura, com o arquivo único montado), sob a trava de '
        'deploy, e recria uma vez o serviço r2d2-worker com a mesma lista compose da ativação; depois confere o trabalhador.',
        'O que NÃO é feito: nenhuma outra linha do .env muda; nenhum rollback inferido; a retirada da edição só acontece se o pedido a '
        'autoriza; nenhum docker exec, pull ou build; nenhuma segunda tentativa. Este programa usa uma revisão própria do núcleo (decisão 1 do Codex).'),
        'outcome': 'RECUSADO: nada mudou. PARCIAL ou sem recibo: o trabalhador pode ter sido recriado ou não; o estado é lido à parte, nunca um segundo envio.', 'extra': 'capacity_switch_rules'},
    'GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01': {'key': 'K5', 'container': False, 'seal': 'e2b6e7bc', 'texts': (
        'K5: supervisor (ACTIVATE: habilita o timer; RESET: limpa a falha de uma execução assinada) (GRAVAÇÃO; SYSTEMCTL)',
        'ESTA OPERAÇÃO MUDA O ESTADO DO SYSTEMD. ACTIVATE: systemctl enable --now do timer já instalado e conferido (o enable recarrega o '
        'gerenciador), e relê o estado. RESET: reset-failed só do serviço exato, só se a execução com o InvocationID assinado terminou com '
        'código 78, sem start, reinício ou nova tentativa.',
        'O que NÃO é feito: nenhuma unidade é instalada ou alterada; nenhum start do serviço; nenhum retry; o reload do gerenciador não '
        'prova que o serviço rodou corretamente (decisão 3 do Codex).'),
        'outcome': 'Só o resultado completo do modo assinado vale; qualquer outro resultado é lido à parte, nunca um segundo envio.',
        'extra': 'k5_rules'},
    'GO_READONLY_HOSTOPS02_DB_PRIV_01': {'key': 'DBR_PRIV', 'container': True, 'seal': 'c8fe1390', 'texts': (
        'DBR-PRIV: conferência isolada de privilégios (LEITURA)',
        'Um contêiner anexado lê apenas CONNECT/USAGE/SELECT do papel leitor restrito por funções de catálogo, em transação somente leitura revertida. Não consulta linhas da época nem usa o emissor.',
        'Nenhum GRANT, DDL ou credencial administrativa. O resultado não concede privilégios e só vale como prova no mesmo dia UTC das consultas.'),
        'outcome': 'Só a prova completa dos privilégios permite citar este recibo; falha ou ausência mantém HOLD.'},
    'GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01': {'key': 'DBR', 'container': True, 'seal': 'd239ed75', 'texts': (
        'DBR: três consultas da ORD:28 (LEITURA)',
        'As três consultas fixadas usam os papéis existentes, após recibo completo do programa DBR-PRIV separado, do mesmo boot e dia UTC e anterior à janela.',
        'Nenhum GRANT, DDL ou credencial administrativa. O binder copia hash, instante, resultado e boot do recibo PRIV citado, sem redatação.'),
        'outcome': 'Só o resultado completo vale; sem PRIV completo e conferido as consultas ficam em HOLD.', 'extra': 'dbr_rules'},
    'GO_WRITE_HOSTOPS02_READER_UNITS_01': {'key': 'units', 'container': False, 'seal': 'c90c044c', 'texts': (
        'Unidades do leitor: instala os arquivos de unidade, sem ativação (GRAVAÇÃO)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR. Cria em /etc/systemd/system só os arquivos de unidade do leitor listados em EFFECTS.json, '
        'root:root 0644, renderizados dos modelos fixados, sem substituir nada que exista.',
        'O que NÃO é feito: nenhum daemon-reload, enable, start ou systemctl; a unidade do produtor só é lida; nada é ativado.'),
        'outcome': 'Só o resultado completo instala; RECUSADO: nada foi criado; PARCIAL ou sem recibo: o estado é lido à parte.'},
    'GO_WRITE_HOSTOPS02_K4_FILES_01': {'key': 'K4', 'container': False, 'seal': '765995f6', 'texts': (
        'K4: entrega dos arquivos da época (CHAIN_STATIC, PINS, LAUNCHER ou WRITER) (GRAVAÇÃO)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR. No modo assinado, cria por criação exclusiva os arquivos listados em EFFECTS.json (documentos da '
        'cadeia e configuração estática, pinos, lançador ou escritor), com os hashes e tamanhos assinados, e relê cada um.',
        'O que NÃO é feito: nada que exista é sobrescrito ou removido; nenhum segredo; nenhum processo, contêiner ou ativação.'),
        'outcome': 'Só o resultado completo entrega; RECUSADO: nada foi criado; PARCIAL ou sem recibo: nomes novos e pedido novo.'},
    'GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01': {'key': 'K3', 'container': False, 'seal': 'b094fe28 (núcleo próprio core_k3 4b9736d8)', 'texts': (
        'K3: grava o secret.env do leitor (GRAVAÇÃO; SEGREDO EM REPOUSO)',
        'ESTA OPERAÇÃO GRAVA NO SERVIDOR UMA CÓPIA DE UM SEGREDO. Lê duas vezes, em memória, o valor do ambiente do trabalhador em execução '
        '(ID assinado) e cria o secret.env do leitor root:root 0600 com uma única linha, conferido por releitura de metadados.',
        'O que NÃO é feito: nenhum valor, tamanho ou hash do segredo sai da execução; nada que exista é sobrescrito; nenhuma ativação. Este '
        'programa usa uma revisão própria do núcleo (decisão 5 do Codex).'),
        'outcome': 'RECUSADO: nada foi criado. PARCIAL ou sem recibo: o arquivo pode existir; o estado é lido à parte, nunca um segundo envio.'},
    'GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01': {'key': 'K13', 'container': False, 'seal': '81f5ed12', 'texts': (
        'K13: chave do leitor (ACTIVATE, RESTART ou DEACTIVATE) (GRAVAÇÃO; SYSTEMCTL)',
        'ESTA OPERAÇÃO MUDA O ESTADO DO SYSTEMD. No modo assinado, habilita e inicia, reinicia ou desabilita o serviço e o timer do leitor, '
        'pelos comandos fixos listados em EFFECTS.json, depois de conferir as unidades, o lançador, os pinos e as pastas assinadas.',
        'O que NÃO é feito: nenhum arquivo é apagado; nenhum daemon-reload além do implícito no enable/disable; a vida do leitor é provada '
        'por uma leitura K13r separada.'),
        'outcome': 'O retorno exige a leitura de vida K13r; qualquer resultado gasta esta assinatura.'},
    'GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01': {'key': 'K13r', 'container': False, 'seal': '68ca972c', 'texts': (
        'K13r: leitura de vida do leitor (LIVE ou STOPPED) (SÓ LEITURA; NÃO INICIA CONTÊINER)',
        'O programa só lê o estado do serviço e do timer do leitor e a imagem assinada, e confere o estado esperado no modo assinado.',
        'O que NÃO é feito: nada é gravado, iniciado ou parado.'),
        'outcome': 'Só o resultado completo confirma o estado esperado; PARCIAL é resultado válido e diz o que faltou.'},
}
HOSTOPS02_TEXT_PT.update({operation: item['texts'] for operation, item in SEALED_PROGRAMS.items()})
OUTCOME_TEXT_PT.update({(operation, None): item['outcome'] for operation, item in SEALED_PROGRAMS.items()})


SEALED_PROGRAM_MODE_ENUMS = {
    'GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01': None,
    'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01': None,
    'GO_WRITE_HOSTOPS02_K12_PREFLIGHT_01': None,
    'GO_WRITE_HOSTOPS02_K12_WINDOW_01': ('W_MODES', ('LAUNCH','PERSIST','STOP','REMOVE')),
    'GO_READONLY_HOSTOPS02_K12_COLLECT_01': ('C_MODES', ('COLLECT','TREE')),
    'GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01': ('MODES', ('MOUNT','ENABLE','DISABLE_FAST','DISABLE_FULL')),
    'GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01': ('MODES', ('ACTIVATE','RESET')),
    'GO_READONLY_HOSTOPS02_DB_PRIV_01': ('MODES', ('PRIV',)),
    'GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01': ('MODES', ('QUERIES',)),
    'GO_WRITE_HOSTOPS02_READER_UNITS_01': None,
    'GO_WRITE_HOSTOPS02_K4_FILES_01': ('K4_MODES', ('CHAIN_STATIC','PINS','LAUNCHER','WRITER')),
    'GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01': None,
    'GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01': ('READER_MODES', ('ACTIVATE','RESTART','DEACTIVATE')),
    'GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01': ('LIVENESS_MODES', ('LIVE','STOPPED')),
}


def sealed_program_modes(m, operation=None):
    """Only the registered operation's compiled string enum is operational authority.
    Numeric file/directory permission tuples never supply or obscure an operation's modes.
    The old generic helper remains only for nonoperational callers without a registered source.
    """
    observed_operation = getattr(m, 'OPERATION', None)
    if operation is None and observed_operation in SEALED_PROGRAM_MODE_ENUMS:operation = observed_operation
    if operation is None:
        found = [value for name, value in sorted(vars(m).items()) if (name == 'MODES' or name.endswith('_MODES')) and type(value) in (tuple, dict)]
        return tuple(found[0]) if len(found) == 1 else None
    need(operation in SEALED_PROGRAM_MODE_ENUMS and observed_operation == operation, 'SEALED_PROGRAM_MODE_SOURCE_MISMATCH')
    rule = SEALED_PROGRAM_MODE_ENUMS[operation]
    if rule is None:
        need('mode' not in getattr(m, 'PLAN_KEYS', ()), 'SEALED_PROGRAM_MODE_ENUM_INVALID')
        return None
    attribute, expected = rule;observed = getattr(m, attribute, None)
    need(type(observed) in (tuple,dict) and tuple(observed) == expected
         and all(type(value) is str for value in observed), 'SEALED_PROGRAM_MODE_ENUM_INVALID')
    return tuple(observed)


def receipt_boot(receipt):
    for pointer in ('/effects/evidence_boot_id_sha256', '/boot_id_sha256', BOOT_POINTER):
        value = at(receipt, pointer)
        if is_hash(value):
            return value
    return None


A2_AMENDMENT4_REV3_SHA256 = '1099dbb5e443b8b36eca5be5f6d616fe2e60988e021023de73b23435908789e2'
A2_AMENDMENT4_SESSIONS = ('2026-10-08', '2026-10-09')


def k9_dated_reserve(name, day, row):
    """Rev8: G19 S is a dated exception, never a standing permission."""
    need(not (name == 'G19' and row.get('track') == 'S') or day in A2_AMENDMENT4_SESSIONS,
         'K9_G19_S_OUTSIDE_DATED_AMENDMENT')


def k8_e6_band(ctx):
    """Normal band unchanged. Only observed G19 S commit on 07/10 or 08/10 extends E6."""
    day = ctx['plan'].get('day')
    try:
        eve = datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone.utc) - timedelta(days=1)
    except (TypeError, ValueError):
        raise Refused('K8_SESSION_DAY_INVALID')
    start, normal_end = eve + timedelta(hours=20, minutes=38), eve + timedelta(hours=23, minutes=55)
    end = normal_end
    reserve = False
    if ctx['window']['end'] > normal_end and day in A2_AMENDMENT4_SESSIONS:
        commits = [(role, receipt) for role, receipt in cited(ctx, K9R_OPERATION)
                   if receipt.get('mode') == 'RESULT' and receipt.get('k9_operation') == 'commit_result'
                   and receipt.get('day') == day]
        if len(commits) == 1:
            role, receipt = commits[0]
            try:
                begun_raw, finished_raw = at(receipt, '/clock/utc_start'), at(receipt, '/clock/utc_end')
                begun = datetime.fromisoformat(begun_raw[:-1] + '+00:00' if type(begun_raw) is str and begun_raw.endswith('Z') else begun_raw)
                finished = datetime.fromisoformat(finished_raw[:-1] + '+00:00' if type(finished_raw) is str and finished_raw.endswith('Z') else finished_raw)
                in_g19_s = eve + timedelta(days=1, minutes=26) <= begun <= finished <= eve + timedelta(days=1, minutes=45, seconds=59)
            except (TypeError, ValueError):
                in_g19_s = False
            reserve = (complete_role(ctx, role) and receipt.get('phase_result') == 'COMPLETE'
                       and receipt.get('outcome') == 'K9_PHASE_RESULT_COMPLETE_ALL_OBSERVED'
                       and receipt.get('slot') == 'SPARE' and at(receipt, '/items/launch_record/slot') == 'SPARE'
                       and in_g19_s)
        if reserve:
            end = eve + timedelta(days=1, minutes=59, seconds=59)
    need(start <= ctx['window']['start'] < ctx['window']['end'] <= end, 'K8_E6_WINDOW_OUTSIDE_A2_BAND')
    result = {'a2_e6_band_start': start.isoformat(), 'a2_e6_band_end': end.isoformat(), 'spare_after_2100_authorized': reserve}
    if reserve:
        result['dated_amendment_sha256'] = A2_AMENDMENT4_REV3_SHA256
    return result


K8_VERIFIER_SUMS = '4ed3a3f9b74baf9f5d34a044a0cd13202a0e62b64d32b2aec44edfd5e3a93834'


def k8_listed_bytes(directory, listing_sha=None):
    """Capture checked bytes once; the verifier consumes a private copy, never a mutable caller tree."""
    listing = read_file(directory / 'SHA256SUMS', 65536, 'K8_DOCUMENTS_UNREADABLE')
    need(listing_sha is None or sha(listing) == listing_sha, 'K8_VERIFIER_BYTES_CHANGED')
    files = {'SHA256SUMS': listing}
    try:
        lines = listing.decode('ascii').splitlines()
    except UnicodeError:
        raise Refused('K8_DOCUMENTS_LISTING_INVALID')
    need(1 <= len(lines) <= 64, 'K8_DOCUMENTS_LISTING_INVALID')
    for line in lines:
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.=/:-]+)', line)
        need(match is not None, 'K8_DOCUMENTS_LISTING_INVALID')
        digest, name = match.groups()
        path = PurePosixPath(name)
        need(not path.is_absolute() and str(path) == name and all(part not in ('', '.', '..') for part in path.parts)
             and name not in files, 'K8_DOCUMENTS_LISTING_INVALID')
        raw = read_file(directory / name, 2 * 1024 * 1024, 'K8_DOCUMENTS_UNREADABLE')
        need(sha(raw) == digest, 'K8_DOCUMENTS_BYTES_CHANGED')
        files[name] = raw
    need(sum(map(len, files.values())) <= 8 * 1024 * 1024, 'K8_DOCUMENTS_TOO_LARGE')
    return files


def k8_run_verifier(bundle, documents, chain):
    with tempfile.TemporaryDirectory(prefix='bind-k8-verify-') as scratch:
        root = Path(scratch)
        for area, files in (('bundle', bundle), ('documents', documents), ('chain', chain)):
            for name, raw in files.items():
                target = root / area / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        command = [sys.executable, '-I', '-B', str(root / 'bundle/c3po/deployment/capacity-day/capacity_day_documents.py'),
                   'verify', '--directory', str(root / 'documents'), '--chain-directory', str(root / 'chain')]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': scratch}, timeout=60)
        except (OSError, subprocess.SubprocessError):
            raise Refused('K8_DOCUMENTS_VERIFIER_UNAVAILABLE')
        need(result.returncode == 0 and len(result.stdout) <= 65536, 'K8_DOCUMENTS_NOT_VERIFIED')
        return strict_json(result.stdout, 'K8_DOCUMENTS_NOT_VERIFIED')


def k8_documents(ctx):
    """Re-run the pinned offline day tool against a checked private snapshot and bind its REQUEST bytes to the delivery."""
    plan, m = ctx['plan'], ctx['rt']['source']
    sets = ctx['params'].get('k8_document_sets')
    need(type(sets) is dict and set(sets) == set(plan.get('windows', [])) and sets, 'K8_DOCUMENT_SETS_REQUIRED')
    delivery = m.k8_delivery(plan)
    bundle = k8_listed_bytes(Path(__file__).resolve().parent / 'k8_verifier', K8_VERIFIER_SUMS)
    results = {}
    for window, item in sorted(sets.items()):
        need(type(item) is dict and set(item) == {'directory', 'chain_directory'} and all(type(p) is str for p in item.values()),
             'K8_DOCUMENT_SETS_REQUIRED')
        def resolve(value):
            p = Path(value)
            return p if p.is_absolute() else ctx['base'] / p
        documents = k8_listed_bytes(resolve(item['directory']))
        summary = strict_json(documents.get('SUMMARY.json', b''), 'K8_DOCUMENTS_NOT_VERIFIED')
        roles = summary.get('roles') if type(summary) is dict else None
        need(type(roles) is dict, 'K8_DOCUMENTS_NOT_VERIFIED')
        config_name = roles.get('capacity_config')
        config = strict_json(documents.get(config_name, b''), 'K8_DOCUMENTS_NOT_VERIFIED')
        pins = config.get('document_pins') if type(config) is dict else None
        need(type(pins) is dict and all(role in pins for role in m.K8_CHAIN_ROLES), 'K8_DOCUMENTS_CHAIN_INVALID')
        chain = {}
        for role in m.K8_CHAIN_ROLES:
            pin = pins[role]
            need(type(pin) is dict and set(pin) == {'file','sha256'} and type(pin['file']) is str
                 and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', pin['file']), 'K8_DOCUMENTS_CHAIN_INVALID')
            raw = read_file(resolve(item['chain_directory']) / pin['file'], 1024 * 1024, 'K8_DOCUMENTS_UNREADABLE')
            need(sha(raw) == pin['sha256'], 'K8_DOCUMENTS_CHAIN_INVALID')
            chain[pin['file']] = raw
        checked = k8_run_verifier(bundle, documents, chain)
        need(type(checked) is dict and checked.get('status') == 'VERIFIED' and checked.get('kind') == 'CAPACITY_DAY'
             and checked.get('documentary_authority') == 'VERIFIED' and checked.get('summary') == 'REBUILT_EQUAL'
             and checked.get('day') == plan['day'] and checked.get('window') == window
             and checked.get('sha256sums_sha256') == sha(documents['SHA256SUMS']), 'K8_DOCUMENTS_NOT_VERIFIED')
        for role in ('contract', 'template', 'go_admission_record', 'go_bar_manifest_record', 'publication_bar_manifest',
                     'go_admission', 'go_bar_manifest', 'capacity_config', 'veto_view'):
            key = role + ':' + window if role in ('capacity_config', 'veto_view') else role
            expected = delivery['contract_raw'] if role == 'contract' else delivery['raws'][key]
            need(documents.get(roles.get(role)) == expected, 'K8_DOCUMENTS_NOT_THE_DELIVERY_BYTES')
        request_raw = documents.get(roles.get('request'), b'')
        request = strict_json(request_raw, 'K8_WINDOW_REQUEST_INVALID')
        need(type(request) is dict and request.get('day') == plan['day'] and request.get('window') == window
             and at(request, '/documentary/contract_sha256') == sha(delivery['contract_raw'])
             and request.get('capacity_config_sha256') == sha(delivery['raws']['capacity_config:' + window]),
             'K8_WINDOW_REQUEST_NOT_THE_DELIVERY_CONTRACT')
        results[window] = {'sha256sums_sha256':sha(documents['SHA256SUMS']), 'request_sha256':sha(request_raw),
                           'contract_sha256':sha(delivery['contract_raw']), 'documentary_authority':'VERIFIED',
                           'inputs':'NOT_COMPARED'}
    return {'verifier_listing_sha256':K8_VERIFIER_SUMS, 'windows':results}


def k8_rules(ctx):
    band = k8_e6_band(ctx)
    plan = ctx['plan']
    reads = cited(ctx, K9R_OPERATION)
    trees = [(role, receipt) for role, receipt in reads if receipt.get('mode') == 'TREE']
    need(len(trees) == 1, 'K8_TREE_NOT_ONE_COMPLETE_READ')
    role, tree = trees[0]
    need(complete_role(ctx, role) and tree.get('outcome') == K9_TREE_OUTCOME,
         'K8_TREE_NOT_ONE_COMPLETE_READ')
    need(canonical(plan.get('days_parent')) == canonical(at(tree, '/items/directory:DAYS/observed_rows'))
         and type(plan.get('days_parent')) is list and plan['days_parent']
         and plan.get('evidence_boot_id_sha256') == tree.get('boot_id_sha256'),
         'PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT')
    commits = [(role, receipt) for role, receipt in reads if receipt.get('mode') == 'RESULT'
               and receipt.get('k9_operation') == 'commit_result' and receipt.get('day') == plan['day']]
    need(len(commits) == 1, 'K8_COMMIT_RESULT_NOT_CITED')
    commit_role, commit = commits[0]
    need(complete_role(ctx, commit_role) and commit.get('phase_result') == 'COMPLETE'
         and commit.get('outcome') == 'K9_PHASE_RESULT_COMPLETE_ALL_OBSERVED', 'K8_COMMIT_RESULT_NOT_COMPLETE')
    return dict(band, tree_role=role, commit_result_role=commit_role, day_documents=k8_documents(ctx))


def k5_rules(ctx):
    """K5 RESET: the InvocationID it signs is copied by $from from a cited read-only receipt of the same boot (decision 3)."""
    plan = ctx['plan']
    if plan.get('mode') != 'RESET':
        return {}
    operations = {entry['role']: entry['operation'] for entry in ctx['entries']}
    copies = [item for item in ctx['copied'] if item.get('plan_pointer') == '/invocation_id']
    need(len(copies) == 1 and operations.get(copies[0].get('evidence_role'), '').startswith('GO_READONLY_'), 'K5_INVOCATION_ID_NOT_COPIED_FROM_A_READ')
    return {'invocation_id_from': copies[0]['evidence_role']}


def dbr_rules(ctx):
    """DBR QUERIES: priv_receipt is the cited PRIV receipt of the distinct PRIV program (complete, of the plan's boot), member for member."""
    plan, m = ctx['plan'], ctx['rt']['source']
    need('PRIV' not in (sealed_program_modes(m) or ()), 'DBR_SPLIT_PRIV_PROGRAM_REQUIRED')
    need(plan.get('mode') == 'QUERIES', 'DBR_SPLIT_PRIV_PROGRAM_REQUIRED')
    priv_operation = getattr(m, 'PRIV_OPERATION', None)
    need(priv_operation == 'GO_READONLY_HOSTOPS02_DB_PRIV_01' and priv_operation != ctx['operation'],
         'DBR_SPLIT_PRIV_PROGRAM_REQUIRED')
    return dbr_priv_receipt_members(ctx, priv_operation)


def dbr_priv_receipt_members(ctx, priv_operation):
    """Receipt-member checks; the separately reviewed PRIV operation must be named by the queries source."""
    plan, m = ctx['plan'], ctx['rt']['source']
    privs = [(role, receipt) for role, receipt in cited(ctx, priv_operation) if receipt.get('mode') == 'PRIV' or at(receipt, '/effects/mode') == 'PRIV']
    need(len(privs) == 1, 'DBR_PRIV_RECEIPT_NOT_CITED')
    role, receipt = privs[0]
    priv = plan.get('priv_receipt') if type(plan.get('priv_receipt')) is dict else {}
    need(complete_role(ctx, role) and receipt.get('outcome') == getattr(m, 'PRIV_COMPLETE_OUTCOME', None)
         and priv.get('receipt_sha256') == receipt.get('metadata_sha256') and priv.get('outcome') == receipt.get('outcome')
         and priv.get('mode') == 'PRIV' and priv.get('operation') == priv_operation
         and type(receipt.get('observed_at')) is str and priv.get('observed_at') == receipt['observed_at']
         and priv.get('boot_id_sha256') == plan.get('evidence_boot_id_sha256')
         == receipt_boot(receipt), 'DBR_PRIV_RECEIPT_NOT_THE_CITED_ONE')
    try:
        observed = datetime.fromisoformat(receipt['observed_at'])
        same_day = observed.tzinfo is not None and observed.astimezone(timezone.utc).date() == ctx['window']['start'].astimezone(timezone.utc).date()
    except (KeyError,TypeError,ValueError):same_day=False
    need(same_day, 'DBR_PRIV_NOT_OF_THE_SAME_UTC_DAY')
    return {'priv_receipt_role': role}


CAPACITY_SWITCH_OPERATION = 'GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01'
CAPACITY_PROBE_OPERATION = 'GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01'


def one_complete_mode(ctx, operation, mode, code):
    found = [(role, receipt) for role, receipt in cited(ctx, operation)
             if receipt.get('mode', at(receipt, '/effects/mode')) == mode
             or receipt.get('step', at(receipt, '/effects/step')) == mode
             or (operation == ACTIVATE_OPERATION and mode == 'ACTIVATE')]
    need(len(found) == 1, code)
    role, receipt = found[0]
    need(complete_role(ctx, role) and is_hash(ctx['plan'].get('evidence_boot_id_sha256'))
         and receipt_boot(receipt) == ctx['plan']['evidence_boot_id_sha256'], code)
    return role, receipt


def predecessor_finished_before(ctx, receipt, code):
    raw = at(receipt, '/clock/utc_end')
    try:
        finished = datetime.fromisoformat(raw)
        valid = finished.tzinfo is not None and finished <= ctx['window']['start']
    except (TypeError, ValueError):
        valid = False
    need(valid, code)


def capacity_probe_rules(ctx):
    plan, source = ctx['plan'], ctx['rt']['source']
    step = plan.get('step')
    need(step in ('CALENDAR','IDENT','LOAD'), 'PROBE_STEP_INVALID')
    try:
        source.validate_window({'not_before':ctx['window']['start'].isoformat(),
                                'expires_at':ctx['window']['end'].isoformat()}, step)
    except Exception:
        raise Refused('PROBE_WINDOW_OUTSIDE_SIGNED_BAND') from None
    if step != 'LOAD':return {'step':step}
    role, mount = one_complete_mode(ctx, CAPACITY_SWITCH_OPERATION, 'MOUNT', 'PROBE_MOUNT_NOT_COMPLETE_CITED')
    need(plan.get('load',{}).get('mount_receipt_sha256') == mount.get('metadata_sha256')
         and is_hash(mount.get('metadata_sha256')), 'PROBE_MOUNT_HASH_NOT_CITED')
    predecessor_finished_before(ctx, mount, 'PROBE_MOUNT_NOT_FINISHED_BEFORE_LOAD')
    return {'step':step,'mount_role':role}


def capacity_switch_rules(ctx):
    plan = ctx['plan']
    role, activated = one_complete_mode(ctx, ACTIVATE_OPERATION, 'ACTIVATE', 'K6B_ACTIVATION_NOT_COMPLETE_CITED')
    effects = activated.get('effects',{})
    recreate = effects.get('recreate',{})
    overrides = [row for row in effects.get('files',[]) if row.get('key')=='OVERRIDE']
    need(len(overrides)==1 and plan.get('data_root') == effects.get('data_root')
         and plan.get('worker',{}).get('image_id') == recreate.get('image_id')
         and plan.get('override',{}).get('environment') == recreate.get('environment')
         and type(plan.get('override',{}).get('directory')) is list and bool(plan['override']['directory'])
         and plan['override']['directory'][-1].get('path','')+'/'+plan.get('override',{}).get('name','') == overrides[0].get('path')
         and plan.get('compose',{}).get('project') == recreate.get('project')
         and plan.get('compose',{}).get('env_file') == recreate.get('env_file')
         and plan.get('compose',{}).get('files') == recreate.get('files',[])[:-1],
         'K6B_ACTIVATION_MEMBERS_NOT_THE_CITED_ONES')
    result={'activation_role':role}
    if plan.get('mode')!='ENABLE':return result
    load_role, load = one_complete_mode(ctx, CAPACITY_PROBE_OPERATION, 'LOAD', 'K6B_LOAD_NOT_COMPLETE_CITED')
    need(is_hash(load.get('metadata_sha256')) and plan.get('probe_load_receipt_sha256') == load['metadata_sha256'],
         'K6B_LOAD_HASH_NOT_CITED')
    mount_role, mount = one_complete_mode(ctx, CAPACITY_SWITCH_OPERATION, 'MOUNT', 'K6B_MOUNT_NOT_COMPLETE_CITED')
    need(is_hash(mount.get('metadata_sha256')) and at(load,'/effects/load/mount_receipt/receipt_sha256') == mount['metadata_sha256'],
         'K6B_LOAD_MOUNT_LINK_INVALID')
    predecessor_finished_before(ctx, load, 'K6B_LOAD_NOT_FINISHED_BEFORE_ENABLE')
    try:
        end=datetime.fromisoformat(at(mount,'/clock/utc_end'))
        start=datetime.fromisoformat(at(load,'/clock/utc_start'))
        valid=end.tzinfo is not None and start.tzinfo is not None and end<=start
    except (TypeError,ValueError):valid=False
    need(valid,'K6B_MOUNT_NOT_FINISHED_BEFORE_LOAD')
    return dict(result,load_role=load_role,mount_role=mount_role)


def sealed_metadata_provenance(ctx):
    """Host identities cannot be typed or borrowed from an unproved receipt. Runtime shape checks remain separate."""
    targets = []
    def walk(value, pointer=''):
        if type(value) is dict:
            if {'device','inode'} <= set(value):
                targets.append(pointer)
                return
            for key, child in value.items():
                walk(child, pointer+'/'+str(key).replace('~','~0').replace('/','~1'))
        elif type(value) is list:
            for index, child in enumerate(value):walk(child,pointer+'/'+str(index))
    walk(ctx['plan'])
    checked=[]
    for target in targets:
        matches=[]
        for entry in ctx['copied']:
            pointer=entry.get('plan_pointer')
            role=entry.get('evidence_role')
            if type(pointer) is str and role in ctx['receipts'] and (pointer=='/' or target==pointer or target.startswith(pointer+'/')):
                receipt=ctx['receipts'][role]
                if complete_role(ctx,role) and receipt_boot(receipt)==ctx['plan'].get('evidence_boot_id_sha256'):
                    source=entry.get('receipt_pointer')
                    if type(source) is str:
                        actual=pointer_value(receipt,source)
                        planned=ctx['plan'] if pointer=='/' else pointer_value(ctx['plan'],pointer)
                        if entry.get('receipt_transformation') == 'CREATED_DIRECTORY_CHAIN_V1':
                            actual = created_directory_chain_provenance(ctx, entry)
                        elif entry.get('receipt_transformation') == 'SUPERVISOR_UNIT_RECORD_V1':
                            actual = supervisor_unit_record_provenance(ctx, entry)
                        if actual is not MISSING and canonical(actual)==canonical(planned):matches.append(role)
                    elif type(entry.get('receipt_ledger_row')) is dict:
                        # resolve_hostops02 already validated and copied the cited ledger row's exact member.
                        matches.append(role)
        need(matches,'SEALED_HOST_IDENTITY_NOT_FROM_PROVED_RECEIPT')
        checked.append({'plan_pointer':target,'evidence_role':matches[0]})
    return checked


K12_P = 'GO_WRITE_HOSTOPS02_K12_PREFLIGHT_01'
K12_W = 'GO_WRITE_HOSTOPS02_K12_WINDOW_01'
K12_C = 'GO_READONLY_HOSTOPS02_K12_COLLECT_01'
K8_DELIVERY = 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01'


def k12_document_rules(ctx):
    """Rebuild the carried window REQUEST; require the actual same-day K8 delivery of its named documents."""
    m, plan = ctx['rt']['source'], ctx['plan']
    try:raw, request, derived = m.k12_capacity_request(plan.get('capacity_request'))
    except Exception:raise Refused('K12_CAPACITY_REQUEST_INVALID') from None
    need(ctx.get('inputs', {}).get('k12_request') == raw, 'K12_REQUEST_NOT_THE_BINDER_INPUT_BYTES')
    item = ctx['params'].get('k12_document_set')
    need(type(item) is dict and set(item) == {'directory','chain_directory'} and all(type(p) is str for p in item.values()),
         'K12_DOCUMENT_SET_REQUIRED')
    def resolve(value):
        path = Path(value)
        return path if path.is_absolute() else ctx['base'] / path
    documents = k8_listed_bytes(resolve(item['directory']))
    summary = strict_json(documents.get('SUMMARY.json', b''), 'K12_DOCUMENTS_INVALID')
    roles = summary.get('roles') if type(summary) is dict else None
    need(type(roles) is dict and documents.get(roles.get('request')) == raw, 'K12_REQUEST_NOT_THE_VERIFIED_DOCUMENT_BYTES')
    config = strict_json(documents.get(roles.get('capacity_config'), b''), 'K12_DOCUMENTS_INVALID')
    pins = config.get('document_pins') if type(config) is dict else None
    required = ('CODEX','FABLE','DUDU','ACT_B','B_CODEX','B_FABLE','B_DUDU')
    need(type(pins) is dict and all(role in pins for role in required), 'K12_DOCUMENT_CHAIN_INVALID')
    chain = {}
    for role in required:
        pin = pins[role]
        need(type(pin) is dict and set(pin) == {'file','sha256'} and type(pin['file']) is str
             and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', pin['file']), 'K12_DOCUMENT_CHAIN_INVALID')
        body = read_file(resolve(item['chain_directory']) / pin['file'], 1024 * 1024, 'K12_DOCUMENT_CHAIN_INVALID')
        need(sha(body) == pin['sha256'], 'K12_DOCUMENT_CHAIN_INVALID')
        chain[pin['file']] = body
    verified = k8_run_verifier(k8_listed_bytes(Path(__file__).resolve().parent/'k8_verifier', K8_VERIFIER_SUMS), documents, chain)
    need(type(verified) is dict and verified.get('status') == 'VERIFIED' and verified.get('kind') == 'CAPACITY_DAY'
         and verified.get('summary') == 'REBUILT_EQUAL' and verified.get('documentary_authority') == 'VERIFIED'
         and verified.get('day') == request['day'] and verified.get('window') == request['window']
         and verified.get('sha256sums_sha256') == sha(documents['SHA256SUMS']), 'K12_DOCUMENTS_NOT_VERIFIED')
    deliveries = [(role,r) for role,r in cited(ctx,K8_DELIVERY) if at(r,'/effects/day') == request['day']]
    need(len(deliveries) == 1, 'K12_K8_DELIVERY_NOT_CITED')
    role, delivery = deliveries[0]
    need(complete_role(ctx,role) and delivery.get('outcome') == 'EVE_DAY_DOCUMENTS_AND_PAYLOAD_DELIVERED_READ_BACK'
         and receipt_boot(delivery) == plan.get('evidence_boot_id_sha256'), 'K12_K8_DELIVERY_NOT_COMPLETE')
    predecessor_finished_before(ctx,delivery,'K12_K8_DELIVERY_NOT_FINISHED')
    need(sha(documents.get(roles.get('contract'),b'')) == at(delivery,'/effects/contract/sha256'), 'K12_DOCUMENTS_NOT_THE_K8_DELIVERY')
    files = at(delivery,'/effects/files')
    need(type(files) is list, 'K12_DOCUMENTS_NOT_THE_K8_DELIVERY')
    for doc_role in ('template','go_admission_record','go_bar_manifest_record','publication_bar_manifest','go_admission','go_bar_manifest','capacity_config','veto_view'):
        key = doc_role + ':' + request['window'] if doc_role in ('capacity_config','veto_view') else doc_role
        matches = [row for row in files if type(row) is dict and row.get('key') == key]
        body = documents.get(roles.get(doc_role))
        need(len(matches) == 1 and type(body) is bytes and sha(body) == matches[0].get('sha256')
             and len(body) == matches[0].get('bytes'), 'K12_DOCUMENTS_NOT_THE_K8_DELIVERY')
    return {'request_sha256':sha(raw),'day':request['day'],'window':request['window'],'delivery_role':role,'inputs':'NOT_COMPARED'}


def k12_tree_rules(ctx):
    role, tree = one_complete_mode(ctx,K12_C,'TREE','K12_TREE_NOT_ONE_COMPLETE_READ')
    need(tree.get('outcome') == 'K12_OBSERVED_AS_REQUIRED', 'K12_TREE_NOT_ONE_COMPLETE_READ')
    rows = tree.get('observed_rows')
    parents = ctx['plan'].get('parent_rows')
    need(type(parents) is dict and parents and type(rows) is dict, 'K12_PARENTS_NOT_FROM_TREE')
    need(all(type(value) is list and value and canonical(value) == canonical(rows.get(key)) for key,value in parents.items()),
         'K12_PARENTS_NOT_FROM_TREE')
    predecessor_finished_before(ctx,tree,'K12_TREE_NOT_FINISHED')
    return role


def k12_rules(ctx):
    operation, plan = ctx['operation'],ctx['plan']
    mode = plan.get('mode')
    if operation == K12_C and mode == 'TREE':
        return {'read_only_tree':True}
    tree_role = k12_tree_rules(ctx)
    if mode == 'REMOVE':
        proofs = []
        for row in plan.get('removals',[]):
            matches = [(role,r) for role,r in cited(ctx,K12_C) if r.get('mode') == 'COLLECT'
                and at(r,'/effects/day') == row.get('day') and at(r,'/effects/window_slot') == row.get('window_slot')
                and at(r,'/items/container/id') == row.get('container_id')]
            need(len(matches) == 1, 'K12_REMOVE_CONTAINER_NOT_CITED')
            role, receipt = matches[0]
            need(complete_role(ctx,role) and receipt_boot(receipt) == plan.get('evidence_boot_id_sha256')
                and at(receipt,'/items/container/ours') is True and at(receipt,'/items/container/running') is False
                and at(receipt,'/effects/launch_request_sha256') == row.get('launch_request_sha256')
                and at(receipt,'/effects/capacity_request_sha256') == row.get('capacity_request_sha256'), 'K12_REMOVE_NOT_THE_CITED_CONTAINER')
            predecessor_finished_before(ctx,receipt,'K12_REMOVE_READ_NOT_FINISHED')
            launches = [(launch_role,r) for launch_role,r in cited(ctx,K12_W)
                if r.get('mode') == 'LAUNCH' and r.get('request_sha256') == row.get('launch_request_sha256')]
            need(len(launches) == 1, 'K12_REMOVE_LAUNCH_NOT_CITED')
            launch_role, launch = launches[0]
            create = at(launch,'/effects/create')
            need(complete_role(ctx,launch_role) and launch.get('outcome') == 'K12_WINDOW_STEP_COMPLETE_READ_BACK'
                and receipt_boot(launch) == plan.get('evidence_boot_id_sha256')
                and at(launch,'/effects/capacity_request_sha256') == row.get('capacity_request_sha256')
                and at(launch,'/effects/day') == row.get('day') and at(launch,'/effects/window_slot') == row.get('window_slot')
                and type(create) is list and create.count(row.get('image_id')) == 1, 'K12_REMOVE_IMAGE_NOT_THE_LAUNCH')
            predecessor_finished_before(ctx,launch,'K12_REMOVE_LAUNCH_NOT_FINISHED')
            proofs.append(role)
        need(proofs, 'K12_REMOVE_CONTAINER_NOT_CITED')
        return {'tree_role':tree_role,'container_roles':proofs}
    documents = k12_document_rules(ctx)
    if (operation == K12_W and mode in ('PERSIST','STOP')) or (operation == K12_C and mode == 'COLLECT'):
        candidates = [(role,r) for role,r in cited(ctx,K12_W) if r.get('mode') == 'LAUNCH'
            and r.get('request_sha256') == plan.get('launch_request_sha256')]
        need(len(candidates) == 1, 'K12_LAUNCH_REQUEST_NOT_CITED')
        role, receipt = candidates[0]
        need(complete_role(ctx,role) and receipt.get('outcome') == 'K12_WINDOW_STEP_COMPLETE_READ_BACK'
             and receipt_boot(receipt) == plan.get('evidence_boot_id_sha256')
             and at(receipt,'/effects/capacity_request_sha256') == documents['request_sha256'], 'K12_LAUNCH_NOT_THE_CITED_WINDOW')
        predecessor_finished_before(ctx,receipt,'K12_LAUNCH_NOT_FINISHED')
        documents['launch_role'] = role
    return {'tree_role':tree_role,'documents':documents}



def scalar_receipt_copy(ctx, target, operations):
    value = pointer_value(ctx['plan'],target)
    need(value is not MISSING, 'READER_MEMBER_NOT_PROVED')
    matches=[]
    for entry in ctx.get('copied',[]):
        role=entry.get('evidence_role');pointer=entry.get('plan_pointer');source=entry.get('receipt_pointer')
        receipt=ctx['receipts'].get(role,{})
        if pointer == target and type(source) is str and receipt.get('operation') in operations:
            if complete_role(ctx,role) and receipt_boot(receipt)==ctx['plan'].get('evidence_boot_id_sha256'):
                actual=pointer_value(receipt,source)
                if actual is not MISSING and canonical(actual)==canonical(value):
                    predecessor_finished_before(ctx,receipt,'READER_PREDECESSOR_NOT_FINISHED')
                    matches.append(role)
    need(matches,'READER_MEMBER_NOT_PROVED')
    return {'plan_pointer':target,'evidence_role':matches[0]}


def policy_worker_identity(ctx):
    """Exact ID and boot copies from one complete K9R POLICY receipt; no W1 time estimate or POST ID."""
    policies=[(role,receipt) for role,receipt in cited(ctx,K9R_OPERATION) if receipt.get('mode')=='POLICY']
    need(len(policies)==1,'POLICY_IDENTITY_NOT_ONE_READ')
    role,receipt=policies[0]
    need(complete_role(ctx,role) and receipt.get('operation')==K9R_OPERATION
         and at(receipt,'/effects/mode')=='POLICY' and receipt.get('findings')==[]
         and at(receipt,'/items/worker/running') is True
         and at(receipt,'/items/worker/state')=='running'
         and at(receipt,'/items/worker/image_id_equal_signed') is True
         and at(receipt,'/items/worker/status')=='COMPLETE'
         and at(receipt,'/items/boot/status')=='COMPLETE'
         and at(receipt,'/items/boot/equal_to_the_evidence') is True,'POLICY_IDENTITY_NOT_COMPLETE')
    boot=ctx['plan'].get('evidence_boot_id_sha256');worker=ctx['plan'].get('worker_container_id')
    need(is_hash(boot) and is_hash(worker) and receipt.get('boot_id_sha256')==boot
         and at(receipt,'/effects/evidence_boot_id_sha256')==boot
         and at(receipt,'/items/worker/container_id')==worker,'POLICY_IDENTITY_NOT_THE_PLAN')
    for target,source in [('/worker_container_id','/items/worker/container_id'),('/evidence_boot_id_sha256','/boot_id_sha256')]:
        copies=[row for row in ctx.get('copied',[]) if row.get('plan_pointer')==target]
        need(len(copies)==1 and copies[0].get('evidence_role')==role and copies[0].get('receipt_pointer')==source,
             'POLICY_IDENTITY_NOT_EXACT_COPIES')
    try:
        start=datetime.fromisoformat(at(receipt,'/clock/utc_start'));end=datetime.fromisoformat(at(receipt,'/clock/utc_end'))
        valid=start.utcoffset()==timedelta(0) and end.utcoffset()==timedelta(0) and start<=end
    except (ValueError,TypeError):valid=False
    need(valid,'POLICY_IDENTITY_CLOCK_INVALID')
    predecessor_finished_before(ctx,receipt,'READER_PREDECESSOR_NOT_FINISHED')
    return {'evidence_role':role,'copies':[{'plan_pointer':target,'evidence_role':role} for target in ['/worker_container_id','/evidence_boot_id_sha256']]}


# ---------------------------------------------------------------- first-night bootstrap: a separate operation/rule.
# The daily K9 rules and complete_role retain their original meaning. TREE_PRE is
# partial even when its individually completed rows may supply this operation.
BOOTSTRAP_OPERATION = 'GO_WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_01'
BOOTSTRAP_MODE = 'BOOTSTRAP_IDENTITY'
BOOTSTRAP_SLOT = 'FIRST_NIGHT_20261006'
BOOTSTRAP_DAY = '2026-10-06'
# Candidate amendment: additional prerequisite band only on this UTC day.
BOOTSTRAP_MORNING_BAND = ('11:26:00', '15:30:00')
BOOTSTRAP_RECEIPT_SCHEMA = 'WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_RECEIPT_V1'
BOOTSTRAP_OUTCOME = 'BOOTSTRAP_IDENTITY_AND_EPOCH_CLAIM_VERIFIED'
BOOTSTRAP_ATTEMPT_KEY = sha(canonical([K9_EPOCH, BOOTSTRAP_SLOT]))
BOOTSTRAP_PLAN_KEYS = frozenset(('mode','epoch','slot','attempt_key','constants','parent_rows',
    'data_volume_chain','source_rows','evidence_boot_id_sha256','policy_read'))
BOOTSTRAP_CONSTANT_KEYS = frozenset(('package_sha256','code_revision','release_sha256','policy_sha256',
    'image_id','runner_sha256','disk_floor_bytes','placement'))
BOOTSTRAP_TREE_DIRECTORIES = (('K9_ROOT','k9_root'),('DAYS','days'),('TOOLS','tools'),('CLAIMS','claims'),
    ('SECRETS','secrets'),('EMITTER','emitter'),('SOURCE_ROOT','source_root'))
BOOTSTRAP_TREE_ITEMS = frozenset(('boot','k9_filesystem','runner_file','september_sources','directories_stable',
    'secret:SECRETS/provider.env','secret:SECRETS/risk-db.env','secret:EMITTER/password')) | frozenset(
        'directory:'+key for key,_ in BOOTSTRAP_TREE_DIRECTORIES)
BOOTSTRAP_TREE_COMPONENT_POINTERS = tuple('/items/directory:'+key+'/observed_rows'
    for key,_ in BOOTSTRAP_TREE_DIRECTORIES if key != 'EMITTER') + (
        '/items/september_sources/data_volume_rows','/items/september_sources/components')
BOOTSTRAP_SOURCE_PATHS = tuple(K9_DATA_VOLUME+'/'+path for path in (
    '.r2d2-v2-risk-secrets','.r2d2-v2-risk-secrets/risk-database-url',
    '.c3po-role-executor-20260908-r2','.c3po-role-executor-20260908-r2/secret',
    '.c3po-role-executor-20260908-r2/secret/password'))
BOOTSTRAP_COMPLETE_ITEMS = frozenset(('boot','boot_stable','k9_filesystem','runner_file','september_sources',
    'directories_stable','secret:SECRETS/provider.env','secret:SECRETS/risk-db.env','secret:EMITTER/password',
    'directory:POLICY','directory:RELEASE','policy_file','release_file','worker','worker_environment','image',
    'worker_stable','worker_environment_stable')) | frozenset('directory:'+key for key,_ in BOOTSTRAP_TREE_DIRECTORIES)
BOOTSTRAP_POSTCLAIM_ITEMS = ('worker','worker_environment','image','policy_file','release_file','runner_file',
    'september_sources','k9_filesystem','boot','directory:SECRETS','directory:EMITTER',
    'secret:EMITTER/password','secret:SECRETS/provider.env','secret:SECRETS/risk-db.env','directories_stable')
BOOTSTRAP_COMPLETE_ITEMS |= frozenset(key+'_postclaim' for key in BOOTSTRAP_POSTCLAIM_ITEMS)


def bootstrap_bound_evidence(ctx,role):
    facts=[row for row in ctx['evidence_facts'] if row.get('role')==role]
    blob=ctx.get('blobs',{}).get(role)
    need(len(facts)==1 and facts[0].get('source')=='BOUND_SET'
         and facts[0].get('receipt_host_binding_is_the_one_of_this_set') is True
         and facts[0].get('receipt_payload_is_the_sealed_source_of_that_operation') is True
         and facts[0].get('exit_json_binds_these_bytes') is True and type(facts[0].get('bound_set')) is dict
         and facts[0]['bound_set'].get('stderr_empty') is True
         and facts[0]['bound_set'].get('exit_json_binds_config_request_go_and_output') is True
         and type(blob) is dict and blob.get('source')=='bound','BOOTSTRAP_EVIDENCE_NOT_BOUND')



def bootstrap_source_rows(components):
    """Known schema projection; no arbitrary transform or typed host identity."""
    need(type(components) is list and len(components)==len(BOOTSTRAP_SOURCE_PATHS),'BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID')
    rows=[]
    for index,(item,path) in enumerate(zip(components,BOOTSTRAP_SOURCE_PATHS)):
        need(type(item) is dict and item.get('path')==path and item.get('exists') is True and item.get('is_link') is False
             and item.get('type')==('file' if index in (1,4) else 'dir')
             and (index not in (1,4) or type(item.get('nlink')) is int and item['nlink']==1)
             and type(item.get('mode_octal')) is str and re.fullmatch('[0-7]{4}',item['mode_octal'])
             and all(type(item.get(key)) is int and item[key]>= (1 if key=='inode' else 0)
                     for key in ('device','inode','uid','gid','mtime_ns','ctime_ns')),
             'BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID')
        rows.append({key:item[key] for key in ('path','device','inode','uid','gid','mtime_ns','ctime_ns')})
        rows[-1]['mode']=int(item['mode_octal'],8)
    return rows


def bootstrap_clock(receipt):
    try:
        start=utc_instant(at(receipt,'/clock/utc_start'));end=utc_instant(at(receipt,'/clock/utc_end'))
        valid=start<=end
    except (ValueError,TypeError):valid=False
    need(valid,'BOOTSTRAP_PREDECESSOR_CLOCK_INVALID')
    return start,end


def bootstrap_prerequisite_band(ctx):
    """Only the additional06/10 morning band; all other windows face the legacy band."""
    start,end=ctx['window']['start'],ctx['window']['end']
    if start.date().isoformat()==BOOTSTRAP_DAY and (
            utc_instant(BOOTSTRAP_DAY+'T'+BOOTSTRAP_MORNING_BAND[0]+'+00:00')<=start<end
            <=utc_instant(BOOTSTRAP_DAY+'T'+BOOTSTRAP_MORNING_BAND[1]+'+00:00')):
        return BOOTSTRAP_MORNING_BAND
    return K4E0_BAND


def bootstrap_first_night(ctx, exact=False):
    start,end=ctx['window']['start'],ctx['window']['end']
    lower=utc_instant(BOOTSTRAP_DAY+'T12:26:00+00:00')
    upper=utc_instant(BOOTSTRAP_DAY+'T12:31:00+00:00')
    if exact:
        valid=start==lower and end==upper and ctx['window']['gate_start']==lower and ctx['window']['gate_end']==upper
    else:
        valid=start.date().isoformat()==BOOTSTRAP_DAY and (
            upper<=start<end<=utc_instant(BOOTSTRAP_DAY+'T'+BOOTSTRAP_MORNING_BAND[1]+'+00:00')
            or utc_instant(BOOTSTRAP_DAY+'T'+K4E0_BAND[0]+'+00:00')<=start<end<=utc_instant(BOOTSTRAP_DAY+'T'+K4E0_BAND[1]+'+00:00'))
    need(valid,'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')


def bootstrap_exact_copy(ctx,target,role,source):
    copies=[row for row in ctx.get('copied',[]) if row.get('plan_pointer')==target]
    value=pointer_value(ctx['plan'],target);actual=pointer_value(ctx['receipts'][role],source)
    need(len(copies)==1 and copies[0].get('evidence_role')==role and copies[0].get('receipt_pointer')==source
         and value is not MISSING and actual is not MISSING and canonical(value)==canonical(actual),
         'BOOTSTRAP_IDENTITY_NOT_EXACT_COPIES')
    return {'plan_pointer':target,'evidence_role':role,'receipt_pointer':source}


def bootstrap_tree_pre(ctx):
    """Only the K9R first-arranque gaps; no claim that the legacy TREE became complete."""
    need(ctx['operation'] in (BOOTSTRAP_OPERATION,K3K9_OPERATION),'BOOTSTRAP_TREE_NOT_ALLOWED_FOR_OPERATION')
    trees=[(role,r) for role,r in cited(ctx,K9R_OPERATION) if r.get('mode')=='TREE']
    need(len(trees)==1 and trees[0][0]=='TREE_PRE','BOOTSTRAP_TREE_PRE_NOT_ONE_PARTIAL_READ')
    role,tree=trees[0];items=tree.get('items');facts=[row for row in ctx['evidence_facts'] if row.get('role')==role]
    need(len(facts)==1 and facts[0].get('complete') is False and facts[0].get('not_complete_accepted_by_parameter') is True
         and tree.get('operation')==K9R_OPERATION and tree.get('status')==RECEIPT_STATUS['KNOWN_PARTIAL']
         and tree.get('outcome')=='PARTIAL_OBSERVED' and at(tree,'/effects/mode')=='TREE'
         and tree.get('findings')==['PARENT_MISSING','SECRET_FILE_ABSENT']
         and tree.get('items_not_complete')==['secret:EMITTER/password']
         and tree.get('items_omitted_by_the_plan')==[] and type(items) is dict and set(items)==BOOTSTRAP_TREE_ITEMS,
         'BOOTSTRAP_TREE_PRE_NOT_ONE_PARTIAL_READ')
    expected_directories={key:K9_PLACEMENT_PATHS[name] for key,name in BOOTSTRAP_TREE_DIRECTORIES}
    expected_files=[K9_PLACEMENT_PATHS[key] for key in ('provider_env_file','risk_db_env_file','emitter_password')]
    need(at(tree,'/effects/reads/directories')==expected_directories
         and at(tree,'/effects/reads/secret_files_lstat_only')==expected_files,
         'BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT')
    exceptions={'directory:EMITTER','secret:SECRETS/provider.env','secret:SECRETS/risk-db.env','secret:EMITTER/password'}
    need(all(type(item) is dict and item.get('status')=='COMPLETE' and item.get('matches') is True
             and item.get('findings')==[] for key,item in items.items() if key not in exceptions),
         'BOOTSTRAP_TREE_PRE_OTHER_ITEMS_NOT_COMPLETE')
    secrets=items['directory:SECRETS'];emitter=items['directory:EMITTER'];password=items['secret:EMITTER/password']
    need(secrets.get('path')==K9_PLACEMENT_PATHS['secrets'] and secrets.get('held') is True
         and secrets.get('root_private') is True and type(secrets.get('entries')) is int and secrets['entries']==0
         and secrets.get('owner_uid')==0 and secrets.get('owner_gid')==0 and secrets.get('mode_octal')=='0700'
         and secrets.get('rows_acceptable_to_the_k9_requests') is True and secrets.get('components_not_root_controlled')==[],
         'BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT')
    need(emitter.get('status')=='COMPLETE' and emitter.get('matches') is False and emitter.get('findings')==['PARENT_MISSING']
         and emitter.get('path')==K9_PLACEMENT_PATHS['emitter'] and emitter.get('held') is False
         and canonical(emitter.get('observed_rows'))==canonical(secrets.get('observed_rows'))
         and password.get('status')=='UNAVAILABLE' and password.get('code')=='DIRECTORY_NOT_HELD'
         and set(password)<= {'status','code','elapsed_ms'},'BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT')
    for name in ('provider.env','risk-db.env'):
        item=items['secret:SECRETS/'+name]
        need(item.get('status')=='COMPLETE' and item.get('matches') is False
             and item.get('findings')==['SECRET_FILE_ABSENT'] and item.get('exists') is False and item.get('name')==name,
             'BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT')
    held={key for key,_ in BOOTSTRAP_TREE_DIRECTORIES if key!='EMITTER'}
    stable=at(tree,'/items/directories_stable/directories')
    need(type(stable) is dict and set(stable)==held and all(value is True for value in stable.values()),
         'BOOTSTRAP_TREE_PRE_OTHER_ITEMS_NOT_COMPLETE')
    boot=ctx['plan'].get('evidence_boot_id_sha256')
    need(is_hash(boot) and tree.get('boot_id_sha256')==boot and at(tree,'/items/boot/boot_id_sha256')==boot,
         'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    for key,name in BOOTSTRAP_TREE_DIRECTORIES:
        if key=='EMITTER':continue
        item=items['directory:'+key];rows=item.get('observed_rows')
        need(item.get('path')==K9_PLACEMENT_PATHS[name] and item.get('held') is True
             and item.get('root_private') is True and type(rows) is list and rows and rows[-1].get('path')==K9_PLACEMENT_PATHS[name],
             'BOOTSTRAP_TREE_PRE_OTHER_ITEMS_NOT_COMPLETE')
        k9_root_controlled(rows)
    bootstrap_bound_evidence(ctx,role)
    bootstrap_clock(tree)
    predecessor_finished_before(ctx,tree,'BOOTSTRAP_PREDECESSOR_NOT_FINISHED')
    return role,tree


def bootstrap_metadata_provenance(ctx,tree_role):
    """The sole partial-receipt exception is a completed component of validated TREE_PRE."""
    need(ctx['operation'] in (BOOTSTRAP_OPERATION,K3K9_OPERATION) and tree_role=='TREE_PRE',
         'BOOTSTRAP_TREE_NOT_ALLOWED_FOR_OPERATION')
    checked_role,_=bootstrap_tree_pre(ctx)
    need(checked_role==tree_role,'BOOTSTRAP_TREE_PRE_NOT_ONE_PARTIAL_READ')
    targets=[]
    def walk(value,pointer=''):
        if type(value) is dict:
            if {'device','inode'}<=set(value):targets.append(pointer);return
            for key,child in value.items():walk(child,pointer+'/'+str(key).replace('~','~0').replace('/','~1'))
        elif type(value) is list:
            for index,child in enumerate(value):walk(child,pointer+'/'+str(index))
    walk(ctx['plan']);checked=[]
    for target in targets:
        matches=[]
        for entry in ctx.get('copied',[]):
            pointer,role,source=entry.get('plan_pointer'),entry.get('evidence_role'),entry.get('receipt_pointer')
            if type(pointer) is not str or role not in ctx['receipts'] or not (target==pointer or target.startswith(pointer+'/')):continue
            receipt=ctx['receipts'][role]
            if receipt_boot(receipt)!=ctx['plan'].get('evidence_boot_id_sha256'):continue
            partial=role==tree_role and not complete_role(ctx,role)
            if not complete_role(ctx,role) and not partial:continue
            if type(source) is str:
                if partial and not any(source==base or source.startswith(base+'/') for base in BOOTSTRAP_TREE_COMPONENT_POINTERS):continue
                actual=pointer_value(receipt,source);planned=pointer_value(ctx['plan'],pointer)
                if entry.get('receipt_transformation') == 'CREATED_DIRECTORY_CHAIN_V1':
                    if partial:continue
                    actual=created_directory_chain_provenance(ctx,entry)
                if entry.get('receipt_transformation')=='BOOTSTRAP_SOURCE_ROWS_V1':
                    if role!=tree_role or source!='/items/september_sources/components' or pointer!='/source_rows':continue
                    actual=bootstrap_source_rows(actual)
                if actual is not MISSING and planned is not MISSING and canonical(actual)==canonical(planned):matches.append(role)
            elif not partial and type(entry.get('receipt_ledger_row')) is dict:matches.append(role)
        need(matches,'BOOTSTRAP_HOST_IDENTITY_NOT_FROM_COMPLETE_COMPONENT')
        checked.append({'plan_pointer':target,'evidence_role':matches[0],'tree_pre_is_complete':False} if matches[0]==tree_role
                       else {'plan_pointer':target,'evidence_role':matches[0]})
    return checked


def bootstrap_tree_plan_rows(ctx,role,all_parents=False):
    plan,tree=ctx['plan'],ctx['receipts'][role]
    members=[]
    if all_parents:
        parents=plan.get('parent_rows')
        need(type(parents) is dict and set(parents)=={name for name,_ in K9R_CHAINS},'BOOTSTRAP_TREE_ROWS_NOT_EXACT_COPIES')
        for name,key in K9R_CHAINS:
            spec=parents[name];target='/parent_rows/'+name+'/rows';source='/items/directory:'+key+'/observed_rows'
            need(type(spec) is dict and spec.get('path')==K9_PLACEMENT_PATHS[name] and spec.get('open_root') is None,
                 'BOOTSTRAP_TREE_ROWS_NOT_EXACT_COPIES')
            bootstrap_exact_copy(ctx,target,role,source);members.append(target)
    else:
        need(canonical(plan.get('secrets_chain'))==canonical(at(tree,'/items/directory:SECRETS/observed_rows')),
             'BOOTSTRAP_TREE_ROWS_NOT_EXACT_COPIES')
        bootstrap_exact_copy(ctx,'/secrets_chain',role,'/items/directory:SECRETS/observed_rows');members.append('/secrets_chain')
    volume=plan.get('data_volume_chain')
    need(type(volume) is list and volume and volume[-1].get('path')==K9_DATA_VOLUME,
         'BOOTSTRAP_TREE_ROWS_NOT_EXACT_COPIES')
    bootstrap_exact_copy(ctx,'/data_volume_chain',role,'/items/september_sources/data_volume_rows')
    copies=[row for row in ctx.get('copied',[]) if row.get('plan_pointer')=='/source_rows' or row.get('plan_pointer','').startswith('/source_rows/')]
    need(len(copies)==1 and copies[0].get('plan_pointer')=='/source_rows' and copies[0].get('evidence_role')==role
         and copies[0].get('receipt_pointer')=='/items/september_sources/components'
         and copies[0].get('receipt_transformation')=='BOOTSTRAP_SOURCE_ROWS_V1'
         and canonical(plan.get('source_rows'))==canonical(bootstrap_source_rows(at(tree,'/items/september_sources/components'))),
         'BOOTSTRAP_TREE_ROWS_NOT_EXACT_COPIES')
    return members+['/data_volume_chain','/source_rows']


def bootstrap_predecessors(ctx,tree):
    e0,posts=cited(ctx,K4E0_OPERATION),cited(ctx,EPOCH_READBACK_OPERATION)
    need(len(e0)==len(posts)==1,'BOOTSTRAP_PREDECESSORS_NOT_COMPLETE')
    (e0_role,e0_receipt),(post_role,post)=e0[0],posts[0]
    need(complete_role(ctx,e0_role) and e0_receipt.get('outcome')==K4E0_OUTCOME
         and complete_role(ctx,post_role) and post.get('mode')=='POST' and post.get('outcome')==POST_OUTCOME,
         'BOOTSTRAP_PREDECESSORS_NOT_COMPLETE')
    boot=ctx['plan'].get('evidence_boot_id_sha256')
    need(all(receipt_boot(r)==boot for r in (e0_receipt,post,tree))
         and all(receipt_boot(r) in (None,boot) for r in ctx['receipts'].values()),'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    tree_start,_=bootstrap_clock(tree)
    for role,receipt in ((e0_role,e0_receipt),(post_role,post)):
        bootstrap_bound_evidence(ctx,role)
        _,end=bootstrap_clock(receipt)
        need(end<=tree_start,'BOOTSTRAP_PREDECESSOR_NOT_FINISHED')
    return {'e0_role':e0_role,'post_role':post_role}


def bootstrap_program_rules(ctx):
    """No call to the common all-complete rule and no dependency on a future bootstrap receipt."""
    plan,m=ctx['plan'],ctx['rt']['source']
    need(ctx['operation']==BOOTSTRAP_OPERATION and plan.get('mode')==BOOTSTRAP_MODE
         and plan.get('epoch')==K9_EPOCH and plan.get('slot')==BOOTSTRAP_SLOT
         and plan.get('attempt_key')==BOOTSTRAP_ATTEMPT_KEY and getattr(m,'PLAN_KEYS',None)==BOOTSTRAP_PLAN_KEYS
         and getattr(m,'RECEIPT_SCHEMA',None)==BOOTSTRAP_RECEIPT_SCHEMA,'BOOTSTRAP_PROGRAM_CONTRACT_MISMATCH')
    need(not cited(ctx,BOOTSTRAP_OPERATION),'BOOTSTRAP_PREPARE_CANNOT_CITE_BOOTSTRAP')
    constants=plan.get('constants')
    need(type(constants) is dict and set(constants)==BOOTSTRAP_CONSTANT_KEYS
         and constants.get('package_sha256')=='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
         and constants.get('code_revision')=='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
         and constants.get('runner_sha256')==K9_RUNNER_SHA256 and constants.get('disk_floor_bytes')==K9_DISK_FLOOR_BYTES
         and type(constants.get('placement')) is dict and all(constants['placement'].get(key)==value for key,value in K9_PLACEMENT_PATHS.items())
         and constants['placement'].get('k9_open_root') is None,'BOOTSTRAP_PROGRAM_CONTRACT_MISMATCH')
    bootstrap_first_night(ctx,exact=True)
    role,tree=bootstrap_tree_pre(ctx);predecessors=bootstrap_predecessors(ctx,tree)
    bootstrap_tree_plan_rows(ctx,role,all_parents=True)
    bootstrap_exact_copy(ctx,'/evidence_boot_id_sha256',role,'/boot_id_sha256')
    policy=k9_policy_rows(ctx,plan)
    provenance=bootstrap_metadata_provenance(ctx,role)
    sendable=k9_sendable_seconds(ctx['window']['gate_start'],ctx['window']['gate_end']-timedelta(seconds=ctx['watchdog']),False)
    need(sendable>=K9_MIN_SENDABLE_SECONDS,'K9_SENDABLE_SECONDS_BELOW_180')
    need(ctx['mode']==REHEARSAL or 'linux_job' in ctx['params'],'LINUX_JOB_RECORD_REQUIRED')
    return {'bootstrap_identity':dict(predecessors,tree_role=role,tree_complete=False,mode=BOOTSTRAP_MODE,
        attempt_key=BOOTSTRAP_ATTEMPT_KEY,host_identity_provenance=provenance,policy_rows=policy,
        sendable_seconds=sendable,claim_limits='BOOTSTRAP_EXECUTION_ONLY_NOT_RECEIPT_CITATION'), 'dispatch_gates':[]}


def bootstrap_complete_identity(ctx,copies=True):
    """One actual observed worker/boot plus its own positive absence and durable claim proof."""
    found=cited(ctx,BOOTSTRAP_OPERATION)
    need(ctx['operation'] in (K3K9_OPERATION,'GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01') and len(found)==1,
         'BOOTSTRAP_IDENTITY_NOT_ONE_COMPLETE_READ')
    role,receipt=found[0];items=receipt.get('items');claim=receipt.get('claim');boot=ctx['plan'].get('evidence_boot_id_sha256')
    need(complete_role(ctx,role) and receipt.get('schema')==BOOTSTRAP_RECEIPT_SCHEMA
         and receipt.get('operation')==BOOTSTRAP_OPERATION and receipt.get('mode')==BOOTSTRAP_MODE
         and receipt.get('status')==RECEIPT_STATUS['KNOWN_COMPLETE'] and receipt.get('outcome')==BOOTSTRAP_OUTCOME
         and receipt.get('epoch')==K9_EPOCH and receipt.get('slot')==BOOTSTRAP_SLOT
         and receipt.get('attempt_key')==BOOTSTRAP_ATTEMPT_KEY and receipt.get('findings')==[]
         and receipt.get('items_not_complete')==[] and receipt.get('expectations_met') is True
         and receipt.get('dependents_hold') is False and receipt.get('secret_contents_opened') is False
         and receipt.get('phase_reached')=='CLAIM' and receipt.get('nothing_changed_by_this_run') is False
         and type(items) is dict and set(items)==BOOTSTRAP_COMPLETE_ITEMS
         and all(type(item) is dict and item.get('status')=='COMPLETE' and item.get('matches') is True
                 and item.get('findings')==[] for item in items.values()),'BOOTSTRAP_IDENTITY_NOT_ONE_COMPLETE_READ')
    bootstrap_bound_evidence(ctx,role)
    worker=at(receipt,'/items/worker/container_id')
    need(is_hash(boot) and is_hash(worker) and receipt.get('boot_id_sha256')==boot
         and at(receipt,'/effects/evidence_boot_id_sha256')==boot
         and at(receipt,'/items/boot/equal_to_the_evidence') is True and at(receipt,'/items/boot_stable/equal_to_first') is True
         and at(receipt,'/items/worker/running') is True and at(receipt,'/items/worker/state')=='running'
         and at(receipt,'/items/worker/image_id_equal_signed') is True
         and canonical(items['worker'])==canonical(items['worker_stable'])
         and canonical(items['worker_environment'])==canonical(items['worker_environment_stable'])
         and canonical(items['worker'])==canonical(items['worker_postclaim'])
         and canonical(items['worker_environment'])==canonical(items['worker_environment_postclaim'])
         and at(receipt,'/items/boot_postclaim/equal_to_first') is True
         and all(at(receipt,'/items/'+key+'/'+field) is True for key in ('image','image_postclaim')
                 for field in ('id_equal_signed','revision_equal_signed')),
         'BOOTSTRAP_IDENTITY_NOT_OBSERVED_SAME_BOOT')
    for suffix in ('','_postclaim'):
        secrets=items['directory:SECRETS'+suffix];emitter=items['directory:EMITTER'+suffix];password=items['secret:EMITTER/password'+suffix]
        need(secrets.get('path')==K9_PLACEMENT_PATHS['secrets'] and secrets.get('held') is True and secrets.get('pinned') is True
             and secrets.get('root_private') is True and type(secrets.get('entries')) is int and secrets['entries']==0
             and type(secrets.get('observed_rows')) is list and bool(secrets['observed_rows'])
             and emitter.get('path')==K9_PLACEMENT_PATHS['emitter'] and emitter.get('exists') is False
             and emitter.get('held') is False and emitter.get('absence_confirmed') is True
             and emitter.get('parent_item')=='directory:SECRETS' and emitter.get('code')=='ABSENT_FROM_HELD_SECRETS'
             and emitter.get('errno')==2 and password.get('path')==K9_PLACEMENT_PATHS['emitter_password']
             and password.get('exists') is False and password.get('parent_absent_confirmed') is True
             and password.get('code')=='ABSENT_PARENT_CONFIRMED' and password.get('parent_item')=='directory:EMITTER',
             'BOOTSTRAP_ABSENCE_NOT_POSITIVELY_CONFIRMED')
        k9_root_controlled(secrets['observed_rows'])
        for name,pathkey in (('provider.env','provider_env_file'),('risk-db.env','risk_db_env_file')):
            item=items['secret:SECRETS/'+name+suffix]
            need(item.get('path')==K9_PLACEMENT_PATHS[pathkey] and item.get('exists') is False and item.get('absence_confirmed') is True
                 and item.get('errno')==2 and item.get('code')=='ABSENT_ENTRY_CONFIRMED' and item.get('parent_item')=='directory:SECRETS'
                 and item.get('name')==name,'BOOTSTRAP_ABSENCE_NOT_POSITIVELY_CONFIRMED')
    stable_keys={key for key,_ in BOOTSTRAP_TREE_DIRECTORIES if key!='EMITTER'}|{'POLICY','RELEASE'}
    need(all(type(at(receipt,'/items/'+key+'/directories')) is dict
             and set(at(receipt,'/items/'+key+'/directories'))==stable_keys
             and all(value is True for value in at(receipt,'/items/'+key+'/directories').values())
             for key in ('directories_stable','directories_stable_postclaim')),
         'BOOTSTRAP_ABSENCE_NOT_POSITIVELY_CONFIRMED')
    expected_name='bootstrap-'+BOOTSTRAP_ATTEMPT_KEY+'.claim'
    need(type(claim) is dict and claim.get('state')=='VERIFIED' and claim.get('key')==BOOTSTRAP_ATTEMPT_KEY
         and claim.get('name')==expected_name and claim.get('path')==K9_PLACEMENT_PATHS['claims']+'/'+expected_name
         and claim.get('code') is None and claim.get('errno') is None
         and all(claim.get(key) is True for key in ('possible_creation','created_by_this_run','usage_consumed','file_fsync',
                                                   'directory_fsync','readback_verified','parent_stable')),
         'BOOTSTRAP_CLAIM_NOT_DURABLE_COMPLETE')
    metadata=claim.get('metadata')
    need(type(metadata) is dict and metadata.get('type')=='file' and metadata.get('uid')==metadata.get('gid')==0
         and metadata.get('mode_octal')=='0600' and type(metadata.get('links')) is int and metadata['links']==1
         and type(metadata.get('device')) is int and type(metadata.get('inode')) is int and metadata['inode']>0,
         'BOOTSTRAP_CLAIM_NOT_DURABLE_COMPLETE')
    content={'schema':'HOSTOPS02_BOOTSTRAP_EPOCH_CLAIM_V1','epoch':K9_EPOCH,'slot':BOOTSTRAP_SLOT,'attempt_key':BOOTSTRAP_ATTEMPT_KEY,
        'request_sha256':receipt.get('request_sha256'),'go_sha256':receipt.get('go_sha256'),'payload_sha256':receipt.get('payload_sha256'),
        'boot_id_sha256':boot,'worker_container_id':worker}
    need(all(is_hash(content[key]) for key in ('request_sha256','go_sha256','payload_sha256'))
         and claim.get('content_sha256')==sha(canonical(content)),'BOOTSTRAP_CLAIM_NOT_DURABLE_COMPLETE')
    need(all(receipt_boot(r) in (None,boot) for r in ctx['receipts'].values()),'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    start,end=bootstrap_clock(receipt)
    need(utc_instant(BOOTSTRAP_DAY+'T12:26:00+00:00')<=start<=end<=utc_instant(BOOTSTRAP_DAY+'T12:31:00+00:00'),
         'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')
    predecessor_finished_before(ctx,receipt,'BOOTSTRAP_PREDECESSOR_NOT_FINISHED')
    identity={'evidence_role':role,'container_id':worker,'boot_id_sha256':boot,'copies':[]}
    if copies:
        need(ctx['plan'].get('worker_container_id')==worker,'BOOTSTRAP_IDENTITY_NOT_OBSERVED_SAME_BOOT')
        identity['copies']=[bootstrap_exact_copy(ctx,target,role,source) for target,source in (
            ('/worker_container_id','/items/worker/container_id'),('/evidence_boot_id_sha256','/boot_id_sha256'))]
    return identity


def bootstrap_k3k9_rules(ctx):
    """The new first-night identity path; k3k9_rules keeps the legacy POLICY path intact."""
    bootstrap_first_night(ctx)
    identity=bootstrap_complete_identity(ctx)
    role,tree=bootstrap_tree_pre(ctx);predecessors=bootstrap_predecessors(ctx,tree)
    bootstrap_tree_plan_rows(ctx,role)
    bootstrap_metadata_provenance(ctx,role)
    bootstrap=ctx['receipts'][identity['evidence_role']]
    _,tree_end=bootstrap_clock(tree);bootstrap_start,_=bootstrap_clock(bootstrap)
    need(tree_end<=bootstrap_start and canonical(at(tree,'/items/directory:SECRETS/observed_rows'))
         ==canonical(at(bootstrap,'/items/directory:SECRETS/observed_rows')),'BOOTSTRAP_TREE_PRE_NOT_CORROBORATED')
    sendable=k9_prerequisite_window(ctx,(BOOTSTRAP_DAY,),bootstrap_prerequisite_band(ctx))
    return {'k9_prerequisite':dict(predecessors,program='K3K9',tree_role=role,tree_complete=False,
        bootstrap_role=identity['evidence_role'],identity_source='BOOTSTRAP_IDENTITY_OBSERVED',sendable_seconds=sendable,
        claim_limits='BOOTSTRAP_EXECUTION_ONLY_NOT_RECEIPT_CITATION'), 'dispatch_gates':[]}


def bootstrap_k3env_identity(ctx):
    """K3 effects are equality-checked signed values; the identity observation remains bootstrap's."""
    bootstrap_first_night(ctx)
    identity=bootstrap_complete_identity(ctx,copies=False);bootstrap=ctx['receipts'][identity['evidence_role']]
    found=cited(ctx,K3K9_OPERATION)
    need(len(found)==1,'BOOTSTRAP_K3_CHAIN_NOT_COMPLETE')
    role,receipt=found[0]
    need(complete_role(ctx,role) and receipt.get('status')==RECEIPT_STATUS['KNOWN_COMPLETE']
         and receipt.get('outcome')=='K9_SECRETS_PLACED_METADATA_VERIFIED' and receipt.get('readback')=='COMPLETE'
         and at(receipt,'/worker/one_container_with_the_name') is True
         and at(receipt,'/worker/id_equal_signed') is True and at(receipt,'/worker/running') is True
         and at(receipt,'/worker/read_twice_equal') is True and at(receipt,'/process/dumpable_disabled') is True
         and at(receipt,'/secrets_directory/pinned') is True and at(receipt,'/secrets_directory/empty') is True
         and receipt.get('directory_readbacks')=={'secrets_directory':None,'emitter_directory':None},
         'BOOTSTRAP_K3_CHAIN_NOT_COMPLETE')
    files=receipt.get('files')
    need(type(files) is dict and set(files)=={'provider_env','risk_db_env','emitter_password'}
         and all(type(row) is dict and row.get('state')=='PLACED_VERIFIED' and row.get('code') is None
                 and all(row.get(key) is True for key in ('created','fsync_file','fsync_directory','regular','uid_0','gid_0',
                     'mode_0600','single_link','on_the_device_of_the_directory','readback_same_inode','readback_metadata_as_created'))
                 for row in files.values()),'BOOTSTRAP_K3_CHAIN_NOT_COMPLETE')
    worker,boot=identity['container_id'],identity['boot_id_sha256']
    need(at(receipt,'/effects/values/provider_env/container_id')==worker
         and at(receipt,'/effects/evidence_boot_id_sha256')==boot,'BOOTSTRAP_K3_CHAIN_NOT_SAME_IDENTITY')
    blob=ctx.get('blobs',{}).get(role)
    facts=[row for row in ctx['evidence_facts'] if row.get('role')==role]
    need(type(blob) is dict and blob.get('source')=='bound' and type(blob.get('request')) is bytes
         and type(blob.get('sheet')) is dict and len(facts)==1 and facts[0].get('source')=='BOUND_SET'
         and type(facts[0].get('bound_set')) is dict and facts[0]['bound_set'].get('stderr_empty') is True
         and facts[0]['bound_set'].get('exit_json_binds_config_request_go_and_output') is True,
         'BOOTSTRAP_K3_CHAIN_NOT_BOUND')
    request=strict_json(blob['request'],'BOOTSTRAP_K3_CHAIN_NOT_BOUND');sheet=blob['sheet']
    need(type(request) is dict and request.get('operation')==K3K9_OPERATION
         and receipt.get('request_sha256')==sha(blob['request']) and sheet.get('operation')==K3K9_OPERATION
         and sheet.get('mode')==ctx['mode'] and at(request,'/plan/worker_container_id')==worker
         and at(request,'/plan/evidence_boot_id_sha256')==boot
         and at(sheet,'/hostops02/rules/k9_prerequisite/identity_source')=='BOOTSTRAP_IDENTITY_OBSERVED',
         'BOOTSTRAP_K3_CHAIN_NOT_BOUND')
    entries=request.get('evidence')
    links=[entry for entry in entries if type(entry) is dict and entry.get('operation')==BOOTSTRAP_OPERATION] if type(entries) is list else []
    need(len(links)==1 and is_hash(bootstrap.get('metadata_sha256')) and links[0].get('receipt_sha256')==bootstrap['metadata_sha256'],
         'BOOTSTRAP_K3_CHAIN_NOT_LINKED')
    bootstrap_role=links[0].get('role');copies=sheet.get('plan_values_copied_from_receipts')
    need(type(copies) is list and at(sheet,'/hostops02/rules/k9_prerequisite/bootstrap_role')==bootstrap_role
         and all(len([row for row in copies if row.get('plan_pointer')==target])==1
                 and any(row.get('plan_pointer')==target and row.get('evidence_role')==bootstrap_role and row.get('receipt_pointer')==source
                         for row in copies) for target,source in (
                 ('/worker_container_id','/items/worker/container_id'),('/evidence_boot_id_sha256','/boot_id_sha256'))),
         'BOOTSTRAP_K3_CHAIN_NOT_LINKED')
    start,end=bootstrap_clock(receipt);_,bootstrap_end=bootstrap_clock(bootstrap)
    try:request_start=parse_utc(request.get('not_before'),code='BOOTSTRAP_K3_CHAIN_NOT_LINKED');request_end=parse_utc(request.get('not_after'),code='BOOTSTRAP_K3_CHAIN_NOT_LINKED')
    except (ValueError,TypeError):raise Refused('BOOTSTRAP_K3_CHAIN_NOT_LINKED')
    need(bootstrap_end<=request_start<=start<=end<=request_end
         and request_start.date().isoformat()==BOOTSTRAP_DAY
         and request_end<=utc_instant(BOOTSTRAP_DAY+'T23:30:00+00:00'),'BOOTSTRAP_K3_CHAIN_NOT_LINKED')
    predecessor_finished_before(ctx,receipt,'BOOTSTRAP_PREDECESSOR_NOT_FINISHED')
    result=[bootstrap_exact_copy(ctx,target,role,source) for target,source in (
        ('/worker_container_id','/effects/values/provider_env/container_id'),
        ('/evidence_boot_id_sha256','/effects/evidence_boot_id_sha256'))]
    return {'copies':result,'identity_observed_role':identity['evidence_role'],'k3_role':role,
            'k3_effects_are_independent_observation':False}


def reader_install_rules(ctx):
    operation,plan=ctx['operation'],ctx['plan']
    k4='GO_WRITE_HOSTOPS02_K4_FILES_01';units='GO_WRITE_HOSTOPS02_READER_UNITS_01'
    switch='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01'
    precheck=PRECHECK_OPERATION
    if operation == k4:
        mode=plan.get('mode');delivery=plan.get('delivery',{})
        kind={'CHAIN_STATIC':'static_config','LAUNCHER':'launcher'}.get(mode)
        if kind:
            raw=ctx['rt']['source'].signed_bytes(delivery.get(kind),2097152,'K4_INPUT_BYTES_INVALID')
            need(ctx.get('inputs',{}).get('k4_'+kind)==raw,'K4_INPUT_NOT_THE_BINDER_BYTES')
        if mode == 'PINS':
            names=('producer_unit_sha256','reader_unit_sha256')
            copies=[scalar_receipt_copy(ctx,'/delivery/'+name,(units,)) for name in names]
            need(delivery.get('values',{}).get('C3PO_R2D2_V2_SHADOW_SOURCE_DIR') == '/c3po-source',
                 'READER_SOURCE_TARGET_NOT_APPROVED')
            for name in ('C3PO_R2D2_V2_CAPACITY_CONFIG_SHA','C3PO_READER_LAUNCHER_SHA256'):
                copies.append(scalar_receipt_copy(ctx,'/delivery/values/'+name,(k4,)))
            return {'copies':copies}
        return {'file_inputs': [kind] if kind else [],'compiled_writer':mode=='WRITER'}
    if operation == 'GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01':
        if cited(ctx,BOOTSTRAP_OPERATION):return bootstrap_k3env_identity(ctx)
        return {'copies':policy_worker_identity(ctx)['copies']}
    if operation == switch and plan.get('mode') != 'DEACTIVATE':
        fields=('/image_id','/release/sha256')
        result=[scalar_receipt_copy(ctx,fields[0],(ACTIVATE_OPERATION,EPOCH_READBACK_OPERATION)),
                scalar_receipt_copy(ctx,fields[1],(RELEASE_OPERATION,EPOCH_READBACK_OPERATION))]
        files=plan.get('files')
        need(type(files) is dict and files,'READER_FILES_NOT_PROVED')
        for name in sorted(files):
            result.append(scalar_receipt_copy(ctx,'/files/'+name,(k4,units)))
        return {'copies':result}
    if operation == 'GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01':
        need(plan.get('source_target') == '/c3po-source','READER_SOURCE_TARGET_NOT_APPROVED')
        return {'copies':[scalar_receipt_copy(ctx,'/image_id',(switch,))]}
    if operation == units:
        for unit in plan['units']:
            expect=unit['expect']
            need(expect == 'ABSENT' or (type(expect) is dict and type(expect.get('links')) is int
                                       and expect['links'] == 1), 'READER_UNIT_PRESENT_LINKS_NOT_ONE')
        if plan.get('acknowledged_leftovers'):
            return {'copies':[scalar_receipt_copy(ctx,'/acknowledged_leftovers',(precheck,))]}
    return {'mode':plan.get('mode')}


for _reader_operation in ('GO_WRITE_HOSTOPS02_READER_UNITS_01','GO_WRITE_HOSTOPS02_K4_FILES_01',
    'GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01','GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01',
    'GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01'):
    SEALED_PROGRAMS[_reader_operation]['extra']='reader_install_rules'


def sealed_program_rules(ctx):
    """The common rule of the programs of SEALED_PROGRAMS, then the program's own extra rule."""
    operation, plan, m, window = ctx['operation'], ctx['plan'], ctx['rt']['source'], ctx['window']
    item = SEALED_PROGRAMS[operation]
    required = tuple(getattr(m, 'EVIDENCE_OPERATIONS', ()))
    for needed in required:
        roles = [role for role, _ in cited(ctx, needed)]
        need(roles, 'SEALED_PROGRAM_EVIDENCE_NOT_CITED')
        need(all(complete_role(ctx, role) for role in roles), 'SEALED_PROGRAM_EVIDENCE_NOT_COMPLETE')
    boot = plan.get('evidence_boot_id_sha256')
    if boot is not None:
        need(all(receipt_boot(receipt) in (None, boot) for receipt in ctx['receipts'].values()), 'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    # Required predecessor evidence must prove its boot, not merely omit a conflicting one.
    for needed in required:
        predecessors = [receipt for _, receipt in cited(ctx, needed)]
        need(is_hash(boot) and all(receipt_boot(receipt) == boot for receipt in predecessors),
             'SEALED_PROGRAM_EVIDENCE_BOOT_UNKNOWN')
    modes = sealed_program_modes(m, operation)
    if 'mode' in plan:
        need(modes is not None and plan['mode'] in modes, 'SEALED_PROGRAM_MODE_INVALID')
    sendable = k9_sendable_seconds(window['gate_start'], window['gate_end'] - timedelta(seconds=ctx['watchdog']), item['container'])
    need(sendable >= K9_MIN_SENDABLE_SECONDS, 'K9_SENDABLE_SECONDS_BELOW_180')
    need(ctx['mode'] == REHEARSAL or not ctx['request']['writes_allowed'] or 'linux_job' in ctx['params'], 'LINUX_JOB_RECORD_REQUIRED')
    provenance = sealed_metadata_provenance(ctx)
    extra = globals()[item['extra']](ctx) if item.get('extra') else {}
    return {'sealed_program': {'program': item['key'], 'mode': plan.get('mode'), 'evidence_required': list(required),
                               'sendable_seconds': sendable, 'container_rule': item['container'], 'host_identity_provenance': provenance, 'extra': extra}, 'dispatch_gates': []}


RULES_OF.update({operation: sealed_program_rules for operation in SEALED_PROGRAMS})
RULES_OF[BOOTSTRAP_OPERATION]=bootstrap_program_rules


def sealed_program_effects_lines(operation, effects, plan):
    """The owner's list for these programs: the mode, then every object the effects name with a path (and its mode, owner and
    expectation when given), then their booleans; the rest is in EFFECTS.json. Device and inode numbers are never printed."""
    lines = ['- programa %s%s' % (SEALED_PROGRAMS[operation]['key'], '' if effects.get('mode') is None else ', modo %s' % effects['mode'])]

    def walk(value, label):
        if type(value) is dict:
            if type(value.get('path')) is str:
                parts = [value['path']] + ['%s %s' % (key, value[key]) for key in ('mode_octal', 'expect', 'require', 'required', 'sha256', 'bytes')
                                          if type(value.get(key)) in (str, int)]
                lines.append('- %s: %s' % (label, ', '.join(parts)))
            for key, item in sorted(value.items()):
                if key not in ('rows', 'parent', 'chain') and type(item) in (dict, list):
                    walk(item, key if label == 'efeitos' else label + '.' + key)
        elif type(value) is list:
            for index, item in enumerate(value[:40]):
                walk(item, label)
    walk(effects, 'efeitos')
    flags = ['%s=%s' % (key, str(value).lower()) for key, value in sorted(effects.items()) if type(value) is bool]
    if flags:
        lines.append('- ' + '; '.join(flags))
    lines.append('- os efeitos completos, calculados pelo programa a partir do pedido, estão em EFFECTS.json')
    return [line if line.isprintable() else line.encode('ascii', 'replace').decode('ascii') for line in lines]


def k9_rows_pt(chain):
    return 'identidades assinadas (%d linhas)' % len(chain) if type(chain) is list else 'linhas não assinadas'


def k9_effects_lines(operation, effects, plan):
    """The owner's list for a K9 request. K9R: from its effects_of(plan) (what it reads, what it starts, nothing written).
    K9W (PLUG): from the plan and the note's step table. Device and inode numbers are never printed."""
    view = k9_view(operation, plan)
    lines = []
    if operation == K9R_OPERATION:
        reads, mode = effects['reads'], effects['mode']
        lines.append('- programa K9R, modo %s%s' % (mode, '' if mode == 'TREE' else '; operação K9 %s da fase %s; sessão %s; vaga %s'
                                                     % (effects['k9_operation'], effects['k9_phase'], effects['day'], effects['slot'])))
        if mode != 'TREE':
            lines.append('- chave de uso único (attempt_key): %s' % effects['attempt_key'])
        if mode == 'RESULT':
            lines.append('- lê o registro %s, o contêiner %s pelo ID registrado (estado e código de saída), os recibos em %s e confere de novo os arquivos '
                         'que o recibo nomeia (%s)' % (reads['launch_record'], reads['container_name'], reads['receipt_directory'], reads['outputs_hashed_again']))
            lines.append('- fim da execução do lançamento que esta leitura colhe: %s' % brt(utc_instant(reads['run_not_after'])))
        elif mode == 'PROBE':
            command = ' '.join(reads['command'])
            lines.append('- O ÚNICO comando que cria algo: docker run --rm -i --pull never --init --user 0:0 --network %s --read-only --cap-drop ALL '
                         '--security-opt no-new-privileges --env-file %s --env C3PO_R2D2_V2_PRODUCERS_ENABLED=true --name %s <ID da imagem assinado> %s: '
                         'UM contêiner anexado, sem montagem, encerrado em até %d s; na entrada padrão, o trecho fixado (sha256 %s)'
                         % (reads['network'], reads['env_file'], reads['container_name'], command, reads['timeout_seconds'], reads['snippet_sha256']))
            lines.append('- o arquivo de ambiente é lido pelo cliente docker no servidor; o programa só o confere por lstat (nunca o abre)')
        elif mode == 'POLICY':
            lines.append('- lê os arquivos %s e %s, o contêiner %s (estado e imagem) e cinco nomes do ambiente dele (só verdadeiro ou falso); pastas: '
                         'da política, %s; da release, %s' % (reads['policy_file'], reads['release_file'], reads['worker']['container'],
                                                             k9_rows_pt(plan['policy_read']['policy']['directory']['rows']),
                                                             k9_rows_pt(plan['policy_read']['release']['directory']['rows'])))
        else:
            lines.append('- lê as pastas %s a partir de "/" (linhas no recibo), os metadados de %s por lstat (nunca abertos), o arquivo %s (hash) e o espaço '
                         'livre contra o piso de %d bytes' % (', '.join(sorted(reads['directories'].values())), ', '.join(reads['secret_files_lstat_only']),
                                                              reads['runner_file'], reads['disk_floor_bytes']))
        if effects['parent_rows'] is not None:
            lines.append('- pastas assinadas (da leitura TREE do mesmo boot): ' + '; '.join(
                '%s %s' % (name, k9_rows_pt(plan['parent_rows'][name]['rows'])) for name, _ in K9R_CHAINS))
        lines.append('- grava %d arquivo(s); cria %d reivindicação(ões); remove %d contêiner(es); inicia %d contêiner(es); ativação: nenhuma'
                     % (effects['writes'], effects['claims'], effects['containers_removed'], effects['containers_run']))
    else:          # K9W: from its own effects_of(plan) (sealed 165330a6...)
        step = effects['step']
        row = step['row']
        lines.append('- programa K9W, modo %s; operação K9 %s da fase %s; sessão %s; vaga %s' % (view['mode'], view['operation'], view['phase'], view['day'], view['slot']))
        lines.append('- reivindicação de uso único %s (criada depois das conferências só de leitura, antes de qualquer outro efeito)' % step['claim_file'])
        if step['directories_created']:
            lines.append('- pastas criadas (root:root 0700; têm de estar ausentes): ' + ', '.join(step['directories_created']))
        if step['step_plan_file']:
            lines.append('- arquivo do plano do passo %s (root:root 0600, criação exclusiva)' % step['step_plan_file'])
        if step['launch_record_file']:
            lines.append('- registro de lançamento %s (root:root 0600, criação exclusiva, depois do start)' % step['launch_record_file'])
        if step['container_name']:
            words = ' '.join('<sha256 deste pedido>' if word == '1' * 64 else '<sha256 do plano do passo>' if word == '2' * 64 else '<ID da imagem assinado>'
                             if word == view['constants']['image_id'] else word for word in step['argv'])
            lines.append('- contêiner %s (%s), rede %s; montagens: %s; arquivos de ambiente: %s'
                         % (step['container_name'], {'LAUNCH': 'destacado, docker create + docker start, sem --rm',
                                                     'ATTACHED': 'anexado, removido pelo motor'}.get(view['mode'], view['mode']),
                            K9W_NETWORK_PT.get(row['network'], row['network']),
                            '; '.join('%s em %s (%s)' % (item['source'], item['target'], 'leitura' if item['read_only'] else 'leitura e escrita')
                                      for item in step['mounts']) or 'nenhuma', ', '.join(step['env_files']) or 'nenhum'))
            lines.append('- comando: docker ' + words)
        if step['removes_the_container_of']:
            lines.append('- remove o contêiner parado %s (docker rm <ID do registro %s>, sem -f e sem -v) só se estiver exited, com a chave e a imagem dele'
                         % (step['removal_container_name'], step['removal_record_file']))
        if view['run_not_after'] is not None:
            lines.append('- o contêiner termina sozinho até %s (limite dentro dele: run_not_after menos o instante do create menos 5 s, no mínimo 90 s)'
                         % brt(utc_instant(view['run_not_after'])))
        if effects.get('bind') is not None:
            lines.append('- documentos de risco: ordem OWNER_ORDER.json de sha256 %s; cutoff_at %s' % (effects['bind']['owner_order_sha256'], effects['bind']['cutoff_at']))
        lines.append('- no máximo: %d reivindicação, %d contêiner criado, %d contêiner(es) removido(s), %d arquivo(s) e %d pasta(s) criados; ativação: nenhuma'
                     % (effects['claims'], effects['containers_created'], effects['containers_removed_at_most'], effects['files_created_at_most'],
                        effects['directories_created_at_most']))
    return lines


def k9_title_pt(title, k9):
    """The fixed title of the K9 operation, with what tells this sheet from the others of the eve."""
    if k9['mode'] == 'TREE':
        return title
    return '%s - sessão %s, vaga %s, grade %s' % (title, k9['day'], {'PRIMARY': 'PRIMÁRIA', 'SPARE': 'RESERVA'}[k9['slot']], k9['grid'])


def k9_question_lines(k9):
    """What the binder checked for a K9 request, in the owner's words, from the sheet member `k9` alone."""
    lines = ['Interface K9: nota sha256 %s; lista fechada das operações (K9_OPERATIONS.json) sha256 %s.' % (k9['note_sha256'], k9['operation_list_sha256'])]
    if k9['mode'] == 'TREE':
        e0 = k9['e0']
        lines += ['Executor k9 entregue pela E0 (recibo sha256 %s): sha256 %s, igual à constante runner_sha256 deste pedido; esta leitura confere o '
                  'arquivo no servidor.' % (e0['receipt_sha256'], e0['runner_sha256'])]
    else:
        lines += ['Grade %s da nota K9 (sha256 %s), sessão %s (véspera %s), trilha %s: janela %s a %s (horário de Brasília). O binder conferiu que a janela '
                  'deste pedido é exatamente essa linha da grade.' % (k9['grid'], k9['grid_sha256'], k9['day'], k9['eve'], k9['track'],
                                                                      brt(parse_utc(k9['window_not_before'])), brt(parse_utc(k9['window_not_after'])))]
        lines += ['Chave de uso único: %s, recalculada pelo binder (época, sessão, fase, operação; a PRIMÁRIA e a RESERVA têm a mesma).' % k9['attempt_key']]
        if k9['run_not_after'] is not None:
            lines += [('Fim da execução de %s, que esta leitura colhe: %s; a janela começa depois dele.' % (k9['launch'], brt(utc_instant(k9['run_not_after']))))
                      if k9['launch'] else 'O contêiner deste lançamento termina sozinho até %s.' % brt(utc_instant(k9['run_not_after']))]
        tree = k9['tree']
        lines += ['Leitura TREE em que este pedido se apoia: recibo sha256 %s, completo, do mesmo boot; as linhas das cinco pastas, o boot e as '
                  'constantes da semana deste pedido são os dela, e ela leu o arquivo do executor k9 (sha256 %s) com o hash assinado.'
                  % (tree['receipt_sha256'], tree['runner_sha256'])]
        if k9['e0'] is not None:
            lines += ['Executor k9 conferido também com o recibo da E0 citado (sha256 %s).' % k9['e0']['receipt_sha256']]
        if k9['policy_rows'] is not None:
            lines += ['As linhas das pastas da política e da release foram copiadas dos recibos citados (%s), do mesmo boot.'
                      % ', '.join(sorted({item['role'] for items in k9['policy_rows'].values() for item in items}))]
        order = k9['risk_order']
        if order is not None:
            windows = order['phase_windows']
            lines += ['Ordem de risco (OWNER_ORDER.json) assinada aqui byte a byte: sha256 %s, %d bytes; namespace %s, sessão %s, cutoff_at %s (início '
                      'da janela de sources_result da grade); janelas: preflight %s a %s, acquire %s a %s, execute %s a %s.'
                      % (order['owner_order_sha256'], order['owner_order_bytes'], order['namespace'], order['session_date'], order['cutoff_at'],
                         windows['preflight']['not_before'], windows['preflight']['not_after'], windows['acquire']['not_before'],
                         windows['acquire']['not_after'], windows['execute']['not_before'], windows['execute']['not_after'])]
    lines += ['Segundos em que o envio pode começar dentro da janela (A2 seção 3%s; faixas de silêncio 00:15-00:45 e 02:15-02:45): %d (mínimo 180).'
              % ('; regra dos contêineres' if k9['container_rule'] else '', k9['sendable_seconds'])]
    if k9['program'] == 'K9R':
        lines += ['Uso único desta leitura: o claim do dispatcher (spawn.claim) e a regra da RESERVA; o K9R não grava reivindicação no servidor.']
    else:
        lines += ['Uso único: o K9W cria no servidor, antes de qualquer efeito, a reivindicação exclusiva da chave acima; a PRIMÁRIA e a RESERVA '
                  'têm a mesma chave, e no máximo uma roda.']
    return lines


def hostops02_effects_lines(sheet, effects, plan):
    """The owner's list, from the operation's own effects_of(plan) and the signed plan: every path created with its mode
    and whether it is expected absent or present, every command that changes state. Device and inode numbers are never
    printed: a signed chain is shown as "identidades assinadas (N linhas)"."""
    def folder(value):
        need(value == 'ABSENT', 'EFFECTS_NOT_LISTABLE_FOR_THE_OWNER')
        return 'será criada; tem de estar ausente'

    def rows(chain):
        return 'identidades assinadas (%d linhas)' % len(chain)
    operation, lines = sheet['operation'], []
    try:
        if operation == CATALOG_OPERATION:
            real, root, container, creates = effects['mode'] == 'REAL', effects['journal_root'], effects['container'], effects['creates']
            lines.append('- modo da operação: ' + ('REAL (a pasta real do journal: o catálogo a liga para sempre à época %s)' % effects['epoch'] if real else
                                                   'REHEARSAL (ensaio no servidor de produção: a pasta real do journal não é usada; duas pastas '
                                                   'descartáveis são criadas em /var/lib e ficam; um contêiner da imagem de produção roda; época de '
                                                   'diagnóstico %s)' % effects['epoch']))
            if real:
                lines.append('- pasta %s: já existe (criada pela provisão), tem de estar vazia, root:root, modo 0700, %s: é usada, não é criada'
                             % (root['path'], rows(plan['journal_chain'])))
            else:
                for path in creates['by_this_process']:
                    lines.append('- pasta %s, root:root, modo 0700 (tem de estar ausente; será criada por esta execução e fica depois dela)' % path)
                lines.append('- pasta real do journal %s: só lida (tem de estar vazia), nunca dada ao docker, %s'
                             % (effects['real_journal_root_read_only']['path'], rows(plan['reference_chain'])))
            for path in creates['by_the_container']:
                lines.append('- arquivo %s, root:root, modo %s (tem de estar ausente: a pasta tem de estar vazia; será criado pelo contêiner)'
                             % (path, creates['file_mode_octal']))
            unit = effects['docker_config']
            lines.append('- pasta de configuração do cliente docker da unidade %s: tem de existir vazia, %s; %s'
                         % (unit['path'], rows(plan['docker_config_chain']), 'o docker roda com ela (DOCKER_CONFIG)' if unit['given_to_docker'] else
                            'só é lida; nenhum comando docker deste ensaio roda com ela'))
            argv = ' '.join(['docker'] + [('<ID da imagem assinado>' if word == container['image_id'] else word) for word in container['docker_arguments']])
            lines.append('- comando que muda estado: %s, com DOCKER_CONFIG=%s: UM contêiner, no máximo %d s, o script fixado (sha256 %s, %d bytes) na '
                         'entrada padrão' % (argv, container['docker_config_variable'], container['time_limit_seconds'], container['standard_input']['sha256'],
                                             container['standard_input']['bytes']))
            lines.append('- só leituras do docker, com a mesma configuração: docker image inspect pelo ID e docker ps -a antes; docker ps -a depois')
            lines.append('- a imagem (o ID assinado está em EFFECTS.json) tem de carregar a revisão %s, conferida com a leitura da pré-checagem citada'
                         % container['image_revision'])
        elif operation == RELEASE_OPERATION:
            directory, created, release = effects['directory'], effects['file'], effects['release']
            lines.append('- pasta %s, root:root, modo %s (%s)' % (directory['path'], directory['mode_octal'], folder(directory['expect'])))
            lines.append('- arquivo %s, root:root, modo %s, um link: os bytes da release de sha256 %s (%d bytes) (ausente, na pasta nova; será criado; nunca substitui nada)'
                         % (created['path'], created['mode_octal'], created['sha256'], created['bytes']))
            lines.append('- arquivo temporário .hostops-<16 primeiros hex do GO>-0.partial (root:root, modo 0600) na mesma pasta: criado, ligado ao nome final '
                         'e removido por esta execução depois de provada a identidade dele')
            lines.append('- exige, sem tocar: o pino %s, arquivo regular de root:root' % effects['maintenance_pin']['path'])
            lines.append('- pasta-mãe %s, %s; o volume tem de ser ponto de montagem' % (effects['parent']['path'], rows(plan['parent'])))
            lines.append('- a release diz de si: época %s, primeira sessão %s, revisão %s, pacote %s, aprovada em %s'
                         % (release['epoch'], release['first_session'], release['code_revision'], release['implementation_package_sha'], release['approved_at']))
            lines.append('- caminho da release dentro do trabalhador (informado, não conferido aqui): %s' % effects['release_file_in_the_worker'])
            lines.append('- comandos que mudam estado: nenhum processo; só as chamadas de criação (mkdir, criação exclusiva, escrita, link e remoção do '
                         'próprio temporário) e fsync')
        elif operation == ACTIVATE_OPERATION:
            directory, recreate = effects['directory'], effects['recreate']
            lines.append('- pasta %s, root:root, modo %s (%s)' % (directory['path'], directory['mode_octal'], folder(directory['expect'])))
            for item in effects['files']:
                lines.append('- arquivo %s, root:root, modo %s: %s de sha256 %s (%d bytes) (ausente, na pasta nova; será criado; nunca substitui nada)'
                             % (item['path'], item['mode_octal'], {'POLICY': 'a política assinada', 'OVERRIDE': 'o override do compose'}[item['key']],
                                item['sha256'], item['bytes']))
            lines.append('- arquivos temporários .hostops-<16 primeiros hex do GO>-0.partial e -1.partial (root:root, modo 0600) na mesma pasta: criados, '
                         'ligados aos nomes finais e removidos por esta execução depois de provada a identidade deles')
            files = ' '.join('-f ' + name for name in recreate['files'])
            lines.append('- comando que muda estado: docker compose --project-name %s --env-file %s %s up -d --no-deps --no-build --pull never '
                         '--force-recreate %s (C3PO_BUILD_SHA=%s): recria UM serviço, o contêiner %s, uma vez, sob a trava de deploy %s (espera até %d s)'
                         % (recreate['project'], recreate['env_file'], files, recreate['service'], recreate['build_sha'], recreate['container'],
                            recreate['lock'], recreate['lock_wait_seconds']))
            lines.append('- os quatro valores que o trabalhador passa a carregar: '
                         + '; '.join('%s=%s' % (name, value) for name, value in sorted(recreate['environment'].items())))
            lines.append('- montagem do trabalhador exigida na renderização: %s em %s; imagem: o ID assinado (em EFFECTS.json)'
                         % (recreate['worker_mount']['source'], recreate['worker_mount']['target']))
            lines.append('- só lidos e comparados, nunca escritos: a release instalada %s (sha256 %s, %d bytes), a versão do deploy (tem de dizer %s), o .env '
                         'e o compose.yml do deploy (nenhum byte deles sai), o pino %s e a ausência do marcador %s'
                         % (effects['release']['path'], effects['release']['sha256'], effects['release']['bytes'], effects['required']['deploy_version'],
                            effects['required']['maintenance_pin'], effects['required']['reboot_pending_marker_absent']))
            lines.append('- pastas assinadas: pasta-mãe da pasta nova, %s; pasta-mãe da release, %s; árvore do deploy, %s; pasta da trava, %s'
                         % (rows(plan['live_parent']), rows(plan['release']['parent']), rows(plan['deploy_directory']), rows(plan['lock']['directory'])))
        elif operation == EPOCH_READBACK_OPERATION:
            verify, release = effects['verify'], effects['release']
            modes = {'FULL': 'o ensaio completo de segunda (o único PRE em que M1 e M3 se apoiam)', 'REDUCED': 'perfil reduzido: um diagnóstico, nunca o ensaio'}
            lines.append('- modo: ' + ('PRE %s, %s' % (effects['dry_run'], modes[effects['dry_run']]) if effects['mode'] == 'PRE' else
                                       'POST, a releitura da primeira sessão (o arquivo instalado é lido e verificado)'))
            mounts = ''.join(' --mount type=bind,source=%s,target=%s,readonly' % (bind['source'], bind['target']) for bind in verify['binds'])
            lines.append('- O ÚNICO comando que cria algo: docker run --rm -i --pull never --init --user 0:0 --network none --read-only --cap-drop ALL '
                         '--security-opt no-new-privileges --name hostops02-k11-<16 primeiros hex do GO>%s <ID da imagem assinado> python -I -B -: UM '
                         'contêiner de verificação, sem rede, raiz e montagens só de leitura, que termina sozinho em até %d s e é removido pelo motor; '
                         'na entrada padrão, o trecho fixado (sha256 %s)%s'
                         % (mounts, verify['alarm_seconds'], verify['snippet_sha256'],
                            ' e os bytes assinados da release, da política e do override' if effects['mode'] == 'PRE' else ' e os bytes assinados da política'))
            if effects['render'] is not None:
                lines.append('- duas renderizações do compose em memória (docker compose ... config --format json; a segunda com o override de sha256 %s na '
                             'entrada padrão), comparadas entre si; nenhum compose up' % effects['render']['override_sha256'])
            lines.append('- leituras: docker image inspect, docker ps -a e docker container inspect do trabalhador; systemctl show de %d unidade(s); '
                         'um teste de um instante da trava de deploy %s' % (len(effects['units']), effects['deploy']['lock']))
            lines.append('- release: sha256 %s (%d bytes), em %s (%s)' % (release['sha256'], release['bytes'], release['path'],
                                                                          {'DIRECTORY_ABSENT': 'a pasta tem de estar ausente', 'INSTALLED': 'tem de estar instalada'}.get(
                                                                              release['expected_on_the_host'], release['expected_on_the_host'])))
            if effects['policy'] is not None:
                lines.append('- política: sha256 %s (%d bytes), conferida nos instantes (horário de Brasília) %s'
                             % (effects['policy']['sha256'], effects['policy']['bytes'],
                                ', '.join(brt(utc_instant(item)) for item in effects['policy']['valid_at'])))
            for label, chain in (('pasta-mãe da release', plan['release']['parent']), ('pasta-mãe da pasta ao vivo', (plan['live'] or {}).get('parent')),
                                 ('árvore do deploy', plan['deploy']['tree']), ('pasta da trava', plan['deploy']['lock_directory']),
                                 ('pasta da sonda da montagem', (plan['bind_probe'] or {}).get('directory'))):
                if type(chain) is dict:
                    lines.append('- %s %s: %s' % (label, chain['path'], rows(chain['rows']) if chain['rows'] is not None else 'linhas não assinadas: só observadas'))
            lines.append('- se esta consulta deixar um contêiner (hostops02-k11-<16 primeiros hex do GO>, também em estado created), ele só é removido por você, '
                         'por esse nome exato, antes da leitura M0 de segunda')
        elif operation in K9_PROGRAMS:          # rev 4
            lines += k9_effects_lines(operation, effects, plan)
        elif operation in SEALED_PROGRAMS:          # rev 4
            lines += sealed_program_effects_lines(operation, effects, plan)
        elif operation == K4E0_OPERATION:          # rev 4
            for key, item in sorted(effects['directories'].items()):
                lines.append('- pasta %s, root:root, modo %s (%s), com %d entrada(s) depois' % (item['path'], item['mode_octal'], folder(item['expect']),
                                                                                             item['entries_after']))
            lines.append('- %s: criada root:root 0700 só se não existir; se existir, só conferida e usada' % effects['c3po_directory']['path'])
            runner = effects['runner']
            lines.append('- arquivo %s, root:root, modo %s, um link: o executor k9 de sha256 %s (%d bytes) (ausente; será criado)'
                         % (runner['path'], runner['mode_octal'], runner['sha256'], runner['bytes']))
            lines.append('- cadeia assinada /, /var, /var/lib: %s (sem raiz aberta; nada no volume de dados)' % rows(plan['parent']))
            lines.append('- comandos que mudam estado: nenhum processo; só mkdir, criação exclusiva, escrita, link e remoção do próprio temporário, e fsync')
        elif operation == K3K9_OPERATION:          # rev 4
            for item in [effects['creates']['directory']] + effects['creates']['files']:
                lines.append('- %s %s, root:root, modo %s (ausente; será criado)' % ('pasta' if item in [effects['creates']['directory']] else 'arquivo',
                                                                                 item['path'], item['mode_octal']))
            lines.append('- tokens do provedor lidos do contêiner %s de ID assinado; URL e senha lidas dos arquivos %s e %s'
                         % (effects['values']['provider_env']['from_container'], effects['values']['risk_db_env']['from_file'],
                            effects['values']['emitter_password']['from_file']))
            lines.append('- pasta dos segredos, %s; volume de dados, %s; linhas dos arquivos de setembro: sha256 %s'
                         % (rows(plan['secrets_chain']), rows(plan['data_volume_chain']), effects['values']['source_rows_sha256']))
    except (KeyError, TypeError, IndexError, AttributeError, ValueError):
        raise Refused('EFFECTS_NOT_LISTABLE_FOR_THE_OWNER')
    need(lines and all(type(line) is str and line.isprintable() for line in lines), 'EFFECTS_NOT_LISTABLE_FOR_THE_OWNER')
    return lines


def input_carriage_pt(operation, plan, name):
    """What the request does with an input file, in the owner's words: its bytes travel in the request, only its hash and
    size do, or (K6a's override) it is compared and not carried."""
    forms = {form for pointer, (input_name, form) in input_members(operation, plan).items() if input_name == name}
    if 'b64' in forms:
        return 'os bytes vão no pedido'
    if operation == ACTIVATE_OPERATION and name == 'override':
        return 'não vai no pedido: o binder conferiu que é byte a byte o override que esta operação deriva e escreve'
    return 'no pedido vão só o hash e o tamanho'


def review_line_pt(review):
    """The review line of every HOSTOPS02 question (K11 included): the co-auditor's review, or the owner's own waiver,
    recorded on its own before this request; the signature over this sheet is never the waiver."""
    if review['kind'] == 'CODEX_REVIEWED':
        return 'Revisão prévia do Codex sobre estes bytes: FEITA (documento sha256 %s).' % review['document_sha256']
    return ('Revisão prévia do Codex sobre estes bytes: DISPENSADA por decisão sua registrada à parte (registro sha256 %s, resposta sua de %s). '
            'Esta assinatura não é a dispensa.' % (review['document_sha256'], brt(parse_utc(review['owner_waiver_signed_at_utc']))))


def spare_paragraph_pt(operation, spare):
    if operation in SPARE_AFTER_A_PREPARED_PRIMARY:
        rule = ('Antes do envio o binder confere, por comando, que o principal nunca foi enviado: a raiz de uso único dele está vazia, ou ele foi '
                'só preparado (o arquivo de reivindicação %s e a tentativa só com intent.json, sem spawn.claim) e o último início dele já passou, '
                'quando o dispatcher não o envia mais. Qualquer outro estado (enviado, recusado no servidor, incerto) impede esta reserva.'
                % spare['claim_name'])
    else:
        rule = ('Antes do envio o binder confere, por comando, que a raiz de uso único do principal está vazia (nem o arquivo de reivindicação %s '
                'nem tentativa). Limite conhecido, da regra do contrato desta operação: esse arquivo nasce no prepare do dispatcher do principal, '
                'antes da publicação e de qualquer envio; um principal preparado e nunca enviado também impede o uso desta reserva.' % spare['claim_name'])
    return ('Este é o pedido RESERVA do pedido %s (pedido sha256 %s, GO sha256 %s). Ele só é usado se o principal nunca tiver sido enviado; '
            'reserva não é segunda tentativa, e um principal tem uma reserva só. %s' % (spare['label'], spare['request_sha256'], spare['go_sha256'], rule))


def hostops02_question(sheet, sheet_sha256, effects, plan):
    w, b, h = sheet['window'], sheet['window']['brt'], sheet['hostops02']
    operation = sheet['operation']
    k9 = h['rules']['k9'] if operation in K9_PROGRAMS else None          # rev 4: a K9 request's text is the one of its K9 operation
    if k9 is not None:
        title, body, never = HOSTOPS02_TEXT_PT[operation][k9['text_key']]
        title = k9_title_pt(title, k9)
    else:
        title, body, never = HOSTOPS02_TEXT_PT[operation]
        program = h['rules'].get('sealed_program')
        if program is not None and program['mode'] is not None:          # rev 4: the signed mode in the title
            title = '%s - modo %s' % (title, program['mode'])
    lines = []
    if sheet['mode'] == REHEARSAL:
        lines += ['*** ENSAIO - NÃO MOSTRAR AO DONO - nenhuma assinatura é pedida; transporte falso (.invalid) ***', '']
    lines += ['PEDIDO DE ASSINATURA - ' + title, '']
    if sheet['writes_allowed']:
        lines += ['Preciso da sua assinatura para UMA execução, no servidor de produção, de uma operação que GRAVA.', '']
    elif (k9 is not None and k9['mode'] != 'PROBE') or (operation in SEALED_PROGRAMS and not SEALED_PROGRAMS[operation]['container']):
        lines += ['Preciso da sua assinatura para uma única consulta ao servidor de produção, só de leitura, que não inicia contêiner.', '']
    else:
        lines += ['Preciso da sua assinatura para uma única consulta ao servidor de produção, que não grava nada mas inicia um contêiner.', '']
    if sheet.get('purpose_pt'):
        lines += ['Finalidade: ' + sheet['purpose_pt'], '']
    lines += body.split('\n') + ['']
    lines += ['O que esta execução faz (calculado pelo programa da família a partir do pedido; EFFECTS.json):']
    lines += hostops02_effects_lines(sheet, effects, plan) + ['']
    lines += never.split('\n') + ['']
    if h['bind_inputs']:
        lines += ['Arquivos de entrada lidos pelo binder no preparo (nada foi digitado):']
        lines += ['- %s: sha256 %s (%d bytes); %s' % (INPUT_NAMES_PT.get(name, name), item['sha256'], item['bytes'], input_carriage_pt(operation, plan, name))
                  for name, item in sorted(h['bind_inputs'].items())] + ['']
    rules = h['rules']
    if operation != RELEASE_OPERATION:
        job = rules.get('linux_job')
        lines += ['Job Linux destes bytes: ' + ('não registrado neste pedido.' if job is None else
                                               'APROVADO segundo o registro de sha256 %s, que nomeia o selo e o programa destes bytes e o selo do '
                                               'núcleo (o binder confere só que os hashes estão no texto).' % job['document_sha256'])]
        if rules.get('release_tree'):
            lines += ['Conferido com a árvore da release: o script é o do README (sha256 %s), o comando docker é o do README palavra por palavra '
                      'e, no modo REAL, a época é a do código.' % rules['release_tree']['readme_sha256']]
        if operation == CATALOG_OPERATION and plan.get('mode') == 'REAL':
            rehearsal = rules.get('rehearsal_receipt')
            if rehearsal:
                lines += ['Ensaio destes mesmos bytes (A6): recibo sha256 %s, resultado %s, conferido no preparo (mesmos bytes, boot, imagem, script e '
                          'caminho; pasta do cliente docker vazia); é conferido de novo antes do envio.' % (rehearsal['receipt_sha256'], rehearsal['outcome'])]
            else:
                lines += ['Ensaio destes mesmos bytes (A6): ainda sem recibo neste preparo. O contrato (seção 5, passo 1) o põe antes da assinatura; '
                          'aqui ele é portão do envio: sem o recibo completo do ensaio, este pedido não é enviado.']
        if operation == EPOCH_READBACK_OPERATION:
            tests = rules['siblings_tests']
            if tests['record']:
                lines += ['Testes das operações irmãs (contrato, seção 8, passo 3): registro sha256 %s, que nomeia os selos aceitos das três irmãs e '
                          'o desta operação.' % tests['record']['document_sha256']]
            elif tests['stale_recorded_seals']:
                lines += ['Atenção: o registro selado das operações irmãs nomeia selos anteriores de %s; os testes das irmãs (contrato, seção 8, '
                          'passo 3) não foram registrados de novo neste pedido.' % ', '.join(tests['stale_recorded_seals'])]
            worker = rules['worker_and_image_compared_with']
            lines += ['Trabalhador, imagem e montagem do volume de dados: ' + ('conferidos com a leitura W1 citada (%s).' % ', '.join(worker) if worker else
                                                                             'não conferidos com uma leitura (nenhuma leitura W1 citada); o ID da '
                                                                             'imagem e a revisão são os da leitura citada.')]
        if k9 is not None:          # rev 4
            lines += k9_question_lines(k9)
        program = rules.get('sealed_program')
        if program is not None:          # rev 4: the other sealed programs
            lines += ['Conferido pelo binder: %s; modo %s; segundos em que o envio pode começar dentro do portão (A2 seção 3%s; faixas de silêncio): %d (mínimo 180).'
                      % ('recibos exigidos pelo programa citados e completos (%s)' % ', '.join(program['evidence_required']) if program['evidence_required']
                         else 'nenhum recibo exigido pelo programa', program['mode'] or 'único', '; regra dos contêineres' if program['container_rule'] else '',
                         program['sendable_seconds'])]
            if program['extra'].get('invocation_id_from'):
                lines += ['O InvocationID assinado foi copiado do recibo de leitura citado (%s), do mesmo boot.' % program['extra']['invocation_id_from']]
            if program['extra'].get('priv_receipt_role'):
                lines += ['O recibo PRIV citado (%s) é o que o pedido assina: completo, do mesmo boot.' % program['extra']['priv_receipt_role']]
        prerequisite = rules.get('k9_prerequisite')
        if prerequisite is not None:          # rev 4: K4-E0, K3-K9
            if prerequisite['program'] == 'K4E0':
                lines += ['Executor k9: sha256 %s (%d bytes), lido pelo binder do arquivo do executor e igual à constante runner_sha256 da semana; as '
                          'linhas e o boot vêm da pré-checagem citada (%s).' % (prerequisite['runner_sha256'], prerequisite['runner_bytes'], prerequisite['precheck_role'])]
            else:
                lines += ['A pasta dos segredos e o volume de dados são as linhas da leitura TREE citada (%s, %s); as linhas dos arquivos de setembro '
                          'foram copiadas dela; o ID do trabalhador, da releitura POST citada (%s); a E0 citada (%s); tudo do mesmo boot.'
                          % (prerequisite['tree_role'], 'completa' if prerequisite['tree_complete'] else 'só com os arquivos de segredo ausentes',
                             prerequisite['post_role'], prerequisite['e0_role'])]
            lines += ['Segundos em que o envio pode começar dentro do portão (A2 seção 3; faixas de silêncio): %d (mínimo 180).' % prerequisite['sendable_seconds']]
        lines += ['']
    if operation == RELEASE_OPERATION:
        proof = rules['linux_proof']
        lines += ['Prova do job Linux (binding/linux_proof.py): ' + ('ACEITA (junit root sha256 %s, junit user sha256 %s).' % (
            proof['root_junit_sha256'], proof['user_junit_sha256']) if proof else 'não exigida neste ensaio.')]
        gate = rules['sunday_gate']
        lines += ['Portão de domingo (binding/predispatch.py sobre a leitura W1 citada): %d verificações; %s.' % (
            gate['checks'], 'nenhuma falhou' if not gate['failed'] else 'falhou só a que falha por construção antes do dia (M0 do mesmo dia)')]
        if rules.get('host_evidence_reason_pt'):
            lines += ['Recibos de provisão citados: %d (o contrato nomeia dois, A3 e A4). Motivo dado pelo operador: %s'
                      % (rules['provisions_cited'], rules['host_evidence_reason_pt'])]
        if not rules['host_evidence_complete']:
            lines += ['Atenção: entre os recibos da execução real das chamadas de criação (provisão e instalação de unidades do HOSTOPS01) há pelo menos um que '
                      'NÃO está completo. Eles seriam as primeiras execuções dessas chamadas por esta família como root com o /usr/bin/python3 do servidor: '
                      'fecham U-K10-4 para essas chamadas e U-K10-3 no sistema de arquivos raiz; estreitam U-K10-1 (as mesmas duas chamadas no volume de '
                      'dados só acontecem na segunda) e não o fecham.']
        lines += ['']
    lines += [review_line_pt(sheet['review']), '']
    if sheet.get('evidence'):
        lines += ['Recibos em que este pedido se apoia:']
        for item in sheet['evidence']:
            lines += ['- %s: %s, recibo sha256 %s, resultado %s (%s)' % (
                item['role'], item['operation'], item['receipt_sha256'], item['outcome'] or item['receipt_status'],
                'completo' if item['complete'] else 'NÃO COMPLETO, aceito por parâmetro: confira antes de assinar')]
        lines += ['']
    spare = h['spare_of']
    if spare:
        lines += [spare_paragraph_pt(operation, spare), '']
    if h['dispatch_gates']:
        lines += ['Antes do envio, a Fable confere por comando (bind_once.py check --gates, nos blocos de envio), e sem isso não há envio:']
        lines += ['- ' + GATE_TEXT_PT[name] for name in h['dispatch_gates']] + ['']
    lines += ['Janela (horário de Brasília): de %s até %s.' % (b['not_before'], b['not_after'])]
    if (w['gate_not_before'], w['gate_not_after']) != (w['not_before'], w['not_after']):
        lines += ['Dentro dela, a execução só pode acontecer de %s até %s.' % (b['gate_not_before'], b['gate_not_after'])]
    lines += ['O envio precisa começar até %s; depois disso esta assinatura não serve mais.' % b['latest_start']]
    if h['minutes_to_avoid']:
        lines += ['O envio evita os minutos :05 a :07, :10 a :25 e :35 a :37 de cada hora (a conferência do binder não deixa enviar neles).']
    lines += ['']
    lines += ['Uso único: a assinatura vale para uma única execução, sem segunda tentativa com ela, qualquer que seja o resultado.']
    lines += [OUTCOME_TEXT_PT.get((operation, plan.get('mode'))) or OUTCOME_TEXT_PT[(operation, None)], '']
    lines += ['Modelo de assinatura: %s.' % SIGNATURE_MODELS[sheet['signature_model']], '']
    core = h['core']
    lines += ['O que a assinatura cobre (identificadores):',
              '- operação: ' + operation,
              '- pedido (REQUEST.BOUND.json) sha256: ' + sheet['request_sha256'],
              '- programa enviado ao servidor (fonte) sha256: ' + sheet['source_sha256'],
              '- escopo assinado (scope) sha256: ' + sheet['scope_sha256'],
              '- efeitos (EFFECTS.json) sha256: ' + sheet['effects_sha256'],
              '- critério de sucesso: ' + sheet['success_criterion'],
              '- selo da operação (SHA256SUMS) sha256: ' + sheet['family']['sha256sums_sha256'] + ' (' + sheet['family']['family'] + ', revisão '
              + sheet['family']['revision'] + ')',
              '- núcleo congelado (CORE_SHA256SUMS) sha256: %s, geração %s; montagem conferida pelo próprio núcleo: %s'
              % (core['core_sha256sums_sha256'], core['generation_sha256'], core['assembly_check']['answer']),
              '- vínculo do servidor (host binding) sha256: ' + sheet['host_binding_sha256'],
              '- comando fixo de transporte (command pin) sha256: ' + sheet['command_sha256'],
              '- raiz local de uso único: ' + sheet['claim_root_identity']['path'] + ' (identidade assinada, em PREPARE.json)',
              '- folha de assinatura (PREPARE.json) sha256: ' + sheet_sha256, '']
    if sheet['mode'] == REHEARSAL:
        lines += ['*** ENSAIO: não há resposta do dono; nada aqui é assinatura. ***']
    else:
        lines += ['Se estiver de acordo, responda exatamente: ' + REAL_ANSWER]
    return ('\n'.join(lines) + '\n').encode('utf-8')


# ---------------------------------------------------------------- documents (pure constructions)
def bind_request(profile, template, m, params, window, host, evidence_entries, plan_values):
    request = json.loads(json.dumps(template['request']))
    nb, na = zulu(window['start']), zulu(window['end'])
    if profile == 'core':
        need(set(request) == set(m.REQUEST_KEYS) and type(request.get('plan')) is dict and request.get('date') is None, 'TEMPLATE_INVALID')
        need(type(plan_values) is dict and set(plan_values) == set(m.PLAN_KEYS), 'PLAN_KEYS_MISMATCH')
        plan = request['plan']
        need(plan.get('status') == 'UNBOUND' and plan.get('host_binding_sha256') is None
             and plan.get('window') == {'expires_at': None, 'not_before': None}, 'TEMPLATE_INVALID')
        plan.update(plan_values)
        plan.update(status='BOUND', host_binding_sha256=host, window={'not_before': nb, 'expires_at': na})
        request.update(status='BOUND', date=window['start'].date().isoformat(), not_before=nb, not_after=na, host_binding_sha256=host,
                       evidence=evidence_entries)
        need(set(request) == set(m.REQUEST_KEYS), 'TEMPLATE_INVALID')
    else:
        collection = request.get('collection')
        need(type(collection) is dict and collection.get('status') == 'UNBOUND' and collection.get('host_binding_sha256') is None
             and collection.get('window') == {'expires_at': None, 'not_before': None} and request.get('dates') == list(m.DATES), 'TEMPLATE_INVALID')
        keys = set(request), set(collection)
        collection.update(status='BOUND', host_binding_sha256=host, window={'not_before': nb, 'expires_at': na})
        if 'candidates' in collection:
            collection['candidates'] = json.loads(json.dumps(params['candidates']))
        request.update(status='BOUND', host_binding_sha256=host, not_before=nb, not_after=na)
        need((set(request), set(collection)) == keys, 'TEMPLATE_INVALID')
    raw = canonical(request)
    need(raw == m.canonical(request) and len(raw) <= 65536, 'REQUEST_NOT_CANONICAL_OR_TOO_LARGE')
    return request, raw


def owner_evidence(profile, mode, signed_at, sheet_sha256, checked_channel=None):
    channel, answer = (REAL_CHANNEL, REAL_ANSWER) if mode == REAL else (REHEARSAL_CHANNEL, REHEARSAL_ANSWER)
    if checked_channel is not None:
        need(mode == REAL, 'CAPTURE_REAL_ONLY')
        channel = checked_channel
    if profile == 'core':
        owner = REAL_OWNER if mode == REAL else REHEARSAL_OWNER
        return '%s answered "%s" (%s) at %s over sheet PREPARE.json sha256:%s' % (owner, answer, channel, signed_at, sheet_sha256)
    return {'channel': channel, 'owner_answer_verbatim': answer, 'signed_at_utc': signed_at, 'prepare_sheet_sha256': sheet_sha256}


def bind_authority(profile, template, m, owner, host, window, request_sha256, evidence, effects):
    authority = json.loads(json.dumps(template['authority']))
    keys = set(authority)
    authority.update(owner=owner, status='SIGNED', decision='APPROVED', execution_authorized=True, host_binding_sha256=host,
                     request_sha256=request_sha256, owner_evidence=evidence, not_before=zulu(window['start']), not_after=zulu(window['end']))
    if profile == 'core':
        authority['effects'] = effects
        need(set(authority) == keys == set(m.AUTHORITY_KEYS), 'TEMPLATE_INVALID')
    else:
        need(set(authority) == keys | {'owner_evidence'}, 'TEMPLATE_INVALID')
    return authority, canonical(authority)


def bind_go(profile, template, m, owner, host, window, request_sha256, authority_sha256, identity, evidence, binding, effects, scope, success):
    go = json.loads(json.dumps(template['go']))
    keys = set(go)
    go.update(owner=owner, status='SIGNED', action='GO', execution_authorized=True, host_binding_sha256=host, request_sha256=request_sha256,
              authority_sha256=authority_sha256, claim_root_identity=identity, not_before=zulu(window['gate_start']),
              not_after=zulu(window['gate_end']), transport_binding=binding)
    if profile == 'core':
        need(go.get('scope_statement') == scope == m.SCOPE_STATEMENT, 'TEMPLATE_INVALID')
        go.update(effects=effects, success_criterion=success)
        need(set(go) == keys == set(m.GO_KEYS), 'TEMPLATE_INVALID')
    else:
        go.update(owner_evidence=evidence, scope=scope)
        need(set(go) == keys | {'owner_evidence', 'scope'}, 'TEMPLATE_INVALID')
    return go, canonical(go)


def contract_decisions(contract, header):
    lines = contract.splitlines()
    need(lines.count(header) == 1, 'CONTRACT_DECISIONS_NOT_FOUND')
    decisions, current = {}, None
    for line in lines[lines.index(header) + 1:]:
        match = re.fullmatch(r'(\d{1,2})\. (.+)', line)
        if match:
            current = int(match.group(1))
            need(current == len(decisions) + 1, 'CONTRACT_DECISIONS_NOT_FOUND')
            decisions[current] = [match.group(2).strip()]
        elif line.startswith('   ') and current is not None:
            decisions[current].append(line.strip())
        else:
            break
    return {number: ' '.join(parts) for number, parts in decisions.items()}


def collection_scope(m, rule, contract, contract_sha256, sums_sha256, source_sha256, date):
    """The scope sentence of a collection-profile GO: a fixed frame around text QUOTED from the sealed contract and from the
    source's own SIDE_EFFECTS, so that the sentence asserts nothing those bytes do not."""
    decisions = contract_decisions(contract, rule['decisions_header'])
    need(all(number in decisions for number in rule['decisions']), 'CONTRACT_DECISIONS_NOT_FOUND')
    effects = m.SIDE_EFFECTS
    need(type(effects) is list and len(effects) >= rule['minimum_side_effects'] and all(type(item) is str and item for item in effects)
         and m.SCOPE.get('side_effects') == effects, 'SIDE_EFFECTS_NOT_FOUND')
    text = (
        '%s (operation %s): one single-use run as root inside the signed window on UTC %s, limited to the commands, paths, '
        'candidates and limits of the signed request (scope sha256 %s; source sha256 %s; candidate manifest SHA256SUMS sha256 %s; '
        'CONTRACT.txt sha256 %s). writes_allowed and activation_allowed are false in the request, the authority and this GO. '
        'Decisions of CONTRACT.txt accepted by this signature, quoted from it: %s Side effects declared in the signed scope '
        '(SCOPE.side_effects, %d items), quoted from the source: %s A refusal of this run is identified by exit.json only '
        '(config, request and GO hashes): the launcher is the reviewed file of the earlier operation, so the stdout of a refused '
        'run is byte for byte that of a refused run of that operation. The receipt is evidence for review only: not readiness, '
        'not installation authority and not activation authority. KNOWN_PARTIAL is a valid outcome, not a failure. No retry: '
        'any remote result spends this GO, and nothing is run again for it once spawn.claim exists.'
    ) % (rule['title'], m.OPERATION, date, m.SCOPE_SHA256, source_sha256, sums_sha256, contract_sha256,
         ' '.join('[decision %d] %s' % (number, decisions[number].rstrip('.') + '.') for number in rule['decisions']),
         len(effects), ' '.join('[side effect %d] %s' % (index, item.rstrip('.') + '.') for index, item in enumerate(effects, 1)))
    need(all(32 <= ord(character) < 127 for character in text) and len(text) <= 24000, 'SCOPE_SENTENCE_INVALID')
    return text


def bind_config(template, rt, mode, owner, host, window, fields, identity, attempt, bound, names, hashes, authorization_ref):
    config = json.loads(json.dumps(template['config']))
    keys = set(config)
    watchdog = config['watchdog_seconds']
    latest = window['gate_end'] - timedelta(seconds=watchdog)
    config.update(status='BOUND', decision='GO', owner=owner, authorization_ref=authorization_ref, target=fields['target'],
                  host_binding_sha256=host, ssh_key=fields['ssh_key'], known_hosts=fields['known_hosts'], local_root_identity=identity,
                  attempt_directory=attempt, not_before=zulu(window['gate_start']), not_after=zulu(window['gate_end']), latest_start=zulu(latest))
    try:
        config['command_sha256'] = rt['transport'].command_pin(rt['dispatch'].command(config))
    except ValueError:
        raise Refused('DISPATCHER_REFUSES_THE_COMMAND')
    for key in BLOBS:
        config[key] = {'path': str(Path(bound) / names[key]), 'sha256': hashes[key]}
    need(set(config) == keys and config['remote_command'] == fields['remote_command'] == REMOTE_COMMAND, 'TEMPLATE_INVALID')
    return config


def transport_binding(config):
    return {key: config[key] for key in ('target', 'remote_command', 'command_sha256', 'runtime_sha256')}


# ---------------------------------------------------------------- the family's own checks, offline
class Untouchable:
    """A host object that fails on any use: nothing may be observed before the first gate call."""

    def __getattr__(self, name):
        raise AssertionError('HOST_TOUCHED_BEFORE_THE_GATE')


class Dry(Exception):
    pass


def family_code(error):
    text = str(error)
    return text if isinstance(error, ValueError) and re.fullmatch(CODE, text) else 'UNEXPECTED_' + type(error).__name__


def authenticate(rt, profile, raws, clock, uid=lambda: 0):
    """The source's own authenticate() on the bytes, then its collector with a gate that raises: the private exception
    must surface, because nothing may be touched before the first gate call. Returns 'ACCEPTED' or the family's code."""
    m, source = rt['source'], rt['source_bytes']
    pins = m.Pins(payload=sha(source), request=sha(raws[0]), authority=sha(raws[1]), go=sha(raws[2]))
    try:
        value, _ = m.authenticate(raws[0], raws[1], raws[2], pins=pins, payload_bytes=source, clock=lambda: clock,
                                  monotonic=lambda: 0.0, executor_uid=uid)
    except ValueError as error:
        return family_code(error)

    def gate():
        raise Dry()
    try:
        if profile == 'core':
            bound = m.digests(raws[0], raws[1], raws[2], source)
            bound['host_binding_sha256'] = value['host_binding_sha256']
            m.perform(value, gate, Untouchable(), bound, lambda: clock, lambda: 0.0, m.Effects())
        else:
            m.collect(value, gate, host=Untouchable())
    except Dry:
        return 'ACCEPTED'
    except BaseException as error:
        return 'DRY_GATE_NOT_FIRST_' + type(error).__name__
    return 'DRY_GATE_NOT_REACHED'


class OsProxy:
    """The os module as the dispatcher sees it during a dry run: every creating call raises DryStop instead."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def open(self, path, flags, mode=0o777, *, dir_fd=None):
        if flags & (self._real.O_CREAT | self._real.O_WRONLY | self._real.O_RDWR | self._real.O_TRUNC | self._real.O_APPEND):
            raise DryStop()
        return self._real.open(path, flags, mode) if dir_fd is None else self._real.open(path, flags, mode, dir_fd=dir_fd)

    def mkdir(self, *args, **kwargs):
        raise DryStop()

    def write(self, *args, **kwargs):
        raise DryStop()


def never_transport(*args, **kwargs):
    raise AssertionError('TRANSPORT_MUST_NOT_RUN')


def dry_dispatch(rt, config_path, config_sha256, clock, memory, ssh_paths):
    """The family's own dispatch_once.execute(phase='prepare') with two substitutions and nothing else changed:
    (1) its os module raises DryStop at the first creating call, which is the exclusive creation of the claim;
    (2) its read() answers from `memory` for documents that are not on disk yet, and for the key and known-hosts files it
        checks by lstat what read() would demand and returns nothing: the binder never opens those two files.
    Returns 'ACCEPTED_UP_TO_THE_CLAIM' or the dispatcher's refusal code."""
    d = rt['dispatch']
    original_read, original_os = d.read, d.os

    def read(path, pin, limit=2 * 1024 * 1024, private=True):
        if path in memory:
            d.need(type(pin) is str and re.fullmatch(HEX64, pin) and pin != '0' * 64, 'LOCAL_PIN_UNBOUND')
            d.need(0 < len(memory[path]) <= limit, 'LOCAL_FILE')
            d.need(sha(memory[path]) == pin, 'LOCAL_PIN')
            return memory[path]
        if path in ssh_paths:
            d.need(type(pin) is str and re.fullmatch(HEX64, pin) and pin != '0' * 64, 'LOCAL_PIN_UNBOUND')
            try:
                lstat_reference({'path': path})
            except Refused:
                d.need(False, 'LOCAL_FILE')
            return b''
        return original_read(path, pin, limit, private)
    d.read, d.os = read, OsProxy(original_os)
    try:
        d.execute(config_path, config_sha256, phase='prepare', clock=lambda: clock, monotonic=lambda: 0.0, transport=never_transport)
    except DryStop:
        return 'ACCEPTED_UP_TO_THE_CLAIM'
    except Exception as error:
        return family_code(error)
    finally:
        d.read, d.os = original_read, original_os
    return 'RETURNED_WITHOUT_REACHING_THE_CLAIM'


def proofs(rt, profile, raws, payload, config, config_raw, config_path, window, memory, ssh_paths, template_go_raw):
    """Acceptance and refusal, by the family's own code, of the bound bytes and of unsigned and expired variants."""
    start, end = window['gate_start'], window['gate_end']
    latest = end - timedelta(seconds=config['watchdog_seconds'])
    second = timedelta(seconds=1)
    result = {}

    def expect(name, got, wanted):
        result[name] = got
        need(got in wanted, 'PROOF_FAILED_' + name.upper())
    # the source alone
    expect('source_accepts_at_not_before', authenticate(rt, profile, raws, start), ('ACCEPTED',))
    expect('source_accepts_at_latest_start', authenticate(rt, profile, raws, latest), ('ACCEPTED',))
    expect('source_refuses_before_the_window', authenticate(rt, profile, raws, start - second), ('OUTSIDE_GO_WINDOW',))
    expect('source_refuses_at_not_after', authenticate(rt, profile, raws, end), ('OUTSIDE_GO_WINDOW',))
    expect('source_refuses_this_user', authenticate(rt, profile, raws, start, uid=os.geteuid), ('REQUEST_OR_EXECUTOR_UNBOUND',))
    request, authority, go = (json.loads(raw) for raw in raws)
    unsigned_authority = canonical(dict(authority, status='UNSIGNED_NOT_AUTHORITY'))
    unsigned_go = canonical(dict(go, status='UNSIGNED_NOT_GO'))
    rechained_go = canonical(dict(go, authority_sha256=sha(unsigned_authority)))
    expect('source_refuses_unsigned_authority', authenticate(rt, profile, [raws[0], unsigned_authority, rechained_go], start), ('AUTHORITY_UNBOUND',))
    expect('source_refuses_unsigned_go', authenticate(rt, profile, [raws[0], raws[1], unsigned_go], start), ('GO_UNBOUND',))
    # the dispatcher, up to the claim
    def dispatch(clock, overrides=None, changed=None):
        held = dict(memory)
        variant, raw = config, config_raw
        if overrides:
            variant = dict(config)
            for key, blob in overrides.items():
                held[config[key]['path']] = blob
                variant[key] = {'path': config[key]['path'], 'sha256': sha(blob)}
        if changed:
            variant = dict(variant, **changed)
        if variant is not config:
            raw = pretty(variant)
        held[config_path] = raw
        if not overrides and not changed and config_path not in memory:
            del held[config_path]              # the bound config is read from disk through the dispatcher's own read()
        return dry_dispatch(rt, config_path, sha(raw), clock, held, ssh_paths)
    expect('dispatcher_accepts_at_not_before', dispatch(start), ('ACCEPTED_UP_TO_THE_CLAIM',))
    expect('dispatcher_accepts_at_latest_start', dispatch(latest), ('ACCEPTED_UP_TO_THE_CLAIM',))
    expect('dispatcher_refuses_before_the_window', dispatch(start - second), ('DISPATCH_WINDOW',))
    expect('dispatcher_refuses_after_latest_start', dispatch(latest + second), ('WINDOW_WITH_WATCHDOG',))
    expect('dispatcher_refuses_at_not_after', dispatch(end), ('DISPATCH_WINDOW',))
    expect('dispatcher_refuses_unsigned_go', dispatch(start, {'go': unsigned_go}), ('GO_UNSIGNED',))
    expect('dispatcher_refuses_the_template_go', dispatch(start, {'go': template_go_raw}), ('GO_UNSIGNED',))
    expect('dispatcher_refuses_unsigned_authority', dispatch(start, {'authority': unsigned_authority, 'go': rechained_go}), ('AUTHORITY_UNSIGNED',))
    expect('dispatcher_refuses_unbound_config', dispatch(start, None, {'status': 'UNBOUND', 'decision': 'UNBOUND'}), ('DISPATCH_UNBOUND',))
    expect('dispatcher_refuses_another_payload', dispatch(start, {'payload': payload + b'\n'}), ('FINAL_BUNDLE_BYTES',))
    return result


def run_payload_locally(payload):
    """The final bytes under an isolated interpreter as this (non-root) user: they must compile and refuse before
    anything is observed. This is not a dispatch: no transport, no host."""
    need(os.geteuid() != 0, 'BIND_AS_ROOT')
    python = '/usr/bin/python3' if os.path.exists('/usr/bin/python3') else sys.executable
    try:
        done = subprocess.run([python, '-I', '-B', '-'], input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': tempfile.gettempdir()}, timeout=60)
    except (OSError, subprocess.SubprocessError):
        raise Refused('PAYLOAD_LOCAL_RUN_FAILED')
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        answer = {}
    if type(answer) is not dict:
        answer = {}
    code = answer.get('code')
    need(done.returncode == 1 and done.stderr == b'' and answer.get('status') == 'REFUSED' and code == 'REQUEST_OR_EXECUTOR_UNBOUND',
         'PAYLOAD_LOCAL_RUN_UNEXPECTED')
    return {'interpreter': python, 'returncode': done.returncode, 'stderr_empty': True, 'status': 'REFUSED', 'code': code}


# ---------------------------------------------------------------- the question shown to the owner
def effects_lines(effects):
    """What a write creates, as the family's own effects_of() states it: one line per path, with its mode and whether the
    request expects it absent (created) or present (only compared). A write whose effects this function cannot list is
    not put to the owner."""
    def expectation(value):
        return 'será criado' if value == 'ABSENT' else 'o pedido o assina como já existente: só é conferido'
    lines = []
    rows = [('diretório', row.get('path') if type(row) is dict else None, row) for row in effects['creates']] if type(effects.get('creates')) is list else []
    if type(effects.get('units')) is list and type(effects.get('directory')) is str:
        rows += [('arquivo', effects['directory'] + '/' + row['destination_name'] if type(row) is dict and type(row.get('destination_name')) is str else None, row)
                 for row in effects['units']]
    for kind, name, row in rows:
        need(type(name) is str and name.isprintable() and type(row.get('mode_octal')) is str and re.fullmatch('0[0-7]{3}', row['mode_octal'])
             and row.get('expect') in ('ABSENT', 'PRESENT'), 'EFFECTS_NOT_LISTABLE_FOR_THE_OWNER')
        lines.append('- %s %s, modo %s (%s)' % (kind, name, row['mode_octal'], expectation(row['expect'])))
    tag = effects.get('retention_tag')
    if type(tag) is dict:
        need(type(tag.get('reference')) is str and tag['reference'].isprintable() and tag.get('expect') in ('ABSENT', 'PRESENT'), 'EFFECTS_NOT_LISTABLE_FOR_THE_OWNER')
        lines.append('- etiqueta de imagem %s sobre o ID de imagem assinado (%s)' % (tag['reference'], expectation(tag['expect'])))
    need(lines, 'EFFECTS_NOT_LISTABLE_FOR_THE_OWNER')
    return lines


def question_text(sheet, sheet_sha256, effects=None, plan=None):
    if sheet.get('hostops02') is not None:
        return hostops02_question(sheet, sheet_sha256, effects, plan)
    w, b = sheet['window'], sheet['window']['brt']
    title, body = OWNER_TEXT_PT.get(sheet['operation'], (None, None))
    if title is None:
        title, body = 'operação ' + sheet['operation'], sheet['owner_summary_pt']
    lines = []
    if sheet['mode'] == REHEARSAL:
        lines += ['*** ENSAIO - NÃO MOSTRAR AO DONO - nenhuma assinatura é pedida; transporte falso (.invalid) ***', '']
    lines += ['PEDIDO DE ASSINATURA - ' + title, '']
    if sheet['writes_allowed']:
        lines += ['Preciso da sua assinatura para UMA execução, no servidor de produção, de uma operação que GRAVA.', '']
    else:
        lines += ['Preciso da sua assinatura para uma única consulta, só de leitura, ao servidor de produção.', '']
    if sheet.get('purpose_pt'):
        lines += ['Finalidade: ' + sheet['purpose_pt'], '']
    lines += body.split('\n') + ['']
    if sheet['writes_allowed']:
        lines += ['O que esta execução cria (lista dos efeitos, calculada pelo programa da família a partir do pedido):'] + effects_lines(effects) + ['']
        review = sheet['review']
        if review['kind'] == 'CODEX_REVIEWED':
            lines += ['Revisão prévia do Codex sobre estes bytes: FEITA, segundo o registro de sha256 %s.' % review['document_sha256'], '']
        else:
            lines += ['Revisão prévia do Codex sobre estes bytes: DISPENSADA por decisão sua para esta operação, segundo o documento de sha256 %s. '
                      'Ao assinar você confirma essa dispensa.' % review['document_sha256'], '']
    if sheet.get('candidates') is not None:
        counts = '; '.join('%s: %d' % (key, sheet['candidates'][key]) for key in sorted(sheet['candidates']))
        lines += ['Candidatos assinados no pedido (só as contagens; os nomes estão em REQUEST.BOUND.json): %s.' % counts, '']
    if sheet.get('evidence'):
        lines += ['Recibos em que este pedido se apoia:']
        for item in sheet['evidence']:
            lines += ['- %s: %s, recibo sha256 %s, resultado %s (%s)' % (
                item['role'], item['operation'], item['receipt_sha256'], item['outcome'],
                'completo' if item['complete'] else 'NÃO COMPLETO, aceito por parâmetro: confira antes de assinar')]
        lines += ['']
    lines += ['Janela (horário de Brasília): de %s até %s.' % (b['not_before'], b['not_after'])]
    if (w['gate_not_before'], w['gate_not_after']) != (w['not_before'], w['not_after']):
        lines += ['Dentro dela, a execução só pode acontecer de %s até %s.' % (b['gate_not_before'], b['gate_not_after'])]
    lines += ['O envio precisa começar até %s; depois disso esta assinatura não serve mais.' % b['latest_start'], '']
    if sheet['writes_allowed']:
        lines += ['Uso único: a assinatura vale para uma única execução. Não há segunda tentativa com ela, qualquer que seja o '
                  'resultado; se a execução não terminar com o critério de sucesso, o estado do servidor será lido por uma consulta '
                  'separada, com outra assinatura.', '']
    else:
        lines += ['Uso único: a assinatura vale para uma única execução. O resultado pode voltar como "parcial" (alguma informação '
                  'não pôde ser lida): isso não é falha, vale o que foi lido, e não haverá segunda tentativa com esta assinatura.', '']
    lines += ['Modelo de assinatura: %s.' % SIGNATURE_MODELS[sheet['signature_model']], '']
    lines += ['O que a assinatura cobre (identificadores):',
              '- operação: ' + sheet['operation'],
              '- pedido (REQUEST.BOUND.json) sha256: ' + sheet['request_sha256'],
              '- programa enviado ao servidor (fonte) sha256: ' + sheet['source_sha256'],
              '- escopo assinado (scope) sha256: ' + sheet['scope_sha256'],
              '- texto formal do escopo do GO (GO_SCOPE.txt) sha256: ' + sheet['go_scope_sha256']]
    if sheet['profile'] == 'core':
        lines += ['- efeitos (EFFECTS.json) sha256: ' + sheet['effects_sha256'],
                  '- critério de sucesso: ' + sheet['success_criterion']]
    lines += ['- selo do candidato (SHA256SUMS) sha256: ' + sheet['family']['sha256sums_sha256'] + ' (' + sheet['family']['family']
              + ', revisão ' + sheet['family']['revision'] + ')',
              '- vínculo do servidor (host binding) sha256: ' + sheet['host_binding_sha256'],
              '- comando fixo de transporte (command pin) sha256: ' + sheet['command_sha256'],
              '- raiz local de uso único: ' + sheet['claim_root_identity']['path'] + ' (device %d, inode %d)'
              % (sheet['claim_root_identity']['device'], sheet['claim_root_identity']['inode']),
              '- folha de assinatura (PREPARE.json) sha256: ' + sheet_sha256, '']
    if sheet['mode'] == REHEARSAL:
        lines += ['*** ENSAIO: não há resposta do dono; nada aqui é assinatura. ***']
    else:
        lines += ['Se estiver de acordo, responda exatamente: ' + REAL_ANSWER]
    return ('\n'.join(lines) + '\n').encode('utf-8')


# ---------------------------------------------------------------- prepare
def names_for(owner, label):
    tag = label.upper().replace('-', '_')
    return {'authority': '%s_%s_AUTHORITY.json' % (owner, tag), 'go': '%s_%s_GO.json' % (owner, tag), 'request': 'REQUEST.BOUND.json',
            'payload': 'FINAL_PAYLOAD.BOUND.py'}


def claim_identity(root):
    info = private_directory(root, 'CLAIM_ROOT_NOT_PRIVATE')
    return {'path': str(root), 'device': info.st_dev, 'inode': info.st_ino}


def assemble(profile, template, rt, mode, owner, host, window, fields, identity, bound, names, request_raw, evidence, effects, scope,
             success, authorization_ref, label):
    """AUTHORITY, GO, final payload and dispatch configuration, as bytes. Pure: the same inputs give the same bytes."""
    m = rt['source']
    request_sha = sha(request_raw)
    _, authority_raw = bind_authority(profile, template, m, owner, host, window, request_sha, evidence, effects)
    hashes = {'source': sha(rt['source_bytes']), 'request': request_sha, 'authority': sha(authority_raw), 'go': '0' * 64, 'payload': '0' * 64}
    all_names = dict(names, source=rt['source_name'])
    attempt = str(Path(identity['path']) / (label + '-once'))
    config = bind_config(template, rt, mode, owner, host, window, fields, identity, attempt, bound, all_names, hashes, authorization_ref('0' * 64))
    _, go_raw = bind_go(profile, template, m, owner, host, window, request_sha, sha(authority_raw), identity, evidence,
                        transport_binding(config), effects, scope, success)
    try:
        payload = rt['launcher'].build(rt['source_bytes'], request_raw, authority_raw, go_raw, expected_payload_sha256=hashes['source'],
                                       expected_request_sha256=request_sha, expected_authority_sha256=sha(authority_raw),
                                       expected_go_sha256=sha(go_raw))
    except ValueError:
        raise Refused('LAUNCHER_REFUSES_TO_BUILD')
    need(type(payload) is bytes and 0 < len(payload) <= 2 * 1024 * 1024, 'FINAL_PAYLOAD_TOO_LARGE')
    config['go']['sha256'], config['payload']['sha256'] = sha(go_raw), sha(payload)
    config['authorization_ref'] = authorization_ref(sha(go_raw))
    config_raw = pretty(config)
    need(len(config_raw) <= 65536, 'CONFIG_TOO_LARGE')
    return {'authority': authority_raw, 'go': go_raw, 'payload': payload, 'config': config, 'config_raw': config_raw}


def prepare(family_directory, operation, params_path, reference_path, out, mode, github_context_path=None, *, now=utc_now):
    need(os.geteuid() != 0, 'BIND_AS_ROOT')
    need(mode in (REAL, REHEARSAL), 'MODE_INVALID')
    identity_of_binder, seals = binder_identity()
    family = verify_family(family_directory)
    seal = accepted_seal(seals, family['sums_sha256'])
    op = select_operation(family, operation)
    rt = load_runtime(op['files'], op['source_name'], op['directory'])
    m = rt['source']
    profile = profile_of(m)
    facts = dispatcher_facts(rt, op['files'])
    template = template_chain(op, rt, facts)
    hostops02 = 'core' in seal
    need(not hostops02 or (operation in HOSTOPS02 and profile == 'core'), 'HOSTOPS02_OPERATION_WITHOUT_BINDING_RULES')
    core = hostops02_core(family, seal, op, rt) if hostops02 else None
    params, params_sha, params_raw, window = load_parameters(Path(params_path), operation, profile, template, hostops02_extra_keys(operation, seal), hostops02)
    owner = REAL_OWNER if mode == REAL else REHEARSAL_OWNER
    out = Path(out)
    need(out.is_absolute() and not os.path.lexists(str(out)) and out.parent.is_dir(), 'OUT_EXISTS_OR_PARENT_MISSING')
    out = out.parent.resolve() / out.name
    mode_guard(mode, out, owner)
    fields, reference, host, executed_command = load_reference(Path(reference_path), mode, True)
    mode_guard(mode, out, owner, fields)
    watchdog = template['config']['watchdog_seconds']
    latest = window['gate_end'] - timedelta(seconds=watchdog)
    need(window['gate_start'] <= latest, 'WINDOW_SHORTER_THAN_WATCHDOG')
    moment = now()
    need(moment <= latest, 'WINDOW_ALREADY_UNUSABLE')
    need(window['start'].date().isoformat() in facts['dates'], 'DATE_NOT_IN_FAMILY_SCOPE')

    capture_context_raw = capture_context_file(github_context_path, params) if mode == REAL else None
    copied, evidence_facts, section12, checked, review = [], [], None, [], None
    inputs, used, blobs = {}, [], {}
    base = Path(params_path).resolve().parent
    identity = hostops02_identity(family, op, seal, template, mode, moment, operation) if hostops02 else None
    if profile == 'core':
        need('gate_not_before' in params or (window['end'] - window['start']).total_seconds() <= m.MAX_GATE_SPAN_SECONDS, 'GATE_SPAN_OVER_FAMILY_CAP')
        need((window['gate_end'] - window['gate_start']).total_seconds() <= m.MAX_GATE_SPAN_SECONDS, 'GATE_SPAN_OVER_FAMILY_CAP')
        foreign = None if hostops02 else (seals, HOSTOPS01_MAY_CITE.get(operation, ()))
        entries, receipts, evidence_facts = load_evidence(params['evidence'], base, mode, host, family, seal, *((seals, blobs) if hostops02 else (None, None)),
                                                          foreign=foreign)
        need(type(params['plan']) is dict, 'PARAMETERS_INVALID')
        plan_source = params['plan']
        if hostops02:
            inputs = load_inputs(params, base, HOSTOPS02[operation]['inputs'])
            plan_source = resolve_hostops02(params['plan'], {'inputs': inputs, 'used': used, 'copied': copied, 'receipts': receipts, 'source': m,
                                                             'operations': {entry['role']: entry['operation'] for entry in entries},
                                                             'evidence_facts':evidence_facts, 'blobs':blobs,
                                                             'operation':operation, 'plan_mode':params['plan'].get('mode'), 'window':window})
        plan_values = resolve_references(plan_source, receipts, copied)
        request, request_raw = bind_request(profile, template, m, params, window, host, entries, plan_values)
        section12 = None if hostops02 else presign_rules(request['plan'], entries, receipts)          # HOSTOPS01 contract section 12 only
        checked = plan_sources(operation, request['plan'], entries, receipts)
        if not hostops02:
            cited_4b = catalog_citation_rules(operation, mode, request['plan'], entries, receipts, evidence_facts)
            if cited_4b is not None:          # only a request that cites the K2a set: the others are bound as before
                checked += cited_4b.pop('checked')
                section12.update(cited_4b)
        if 'review' in params:
            review = load_review(params['review'], base, identity)
        try:
            effects = json.loads(canonical(m.effects_of(request['plan'])))
            success = m.success_of(request['plan'])
        except Exception:
            raise Refused('FAMILY_REFUSES_THE_PLAN')
        need(type(success) is str and re.fullmatch(CODE, success), 'FAMILY_REFUSES_THE_PLAN')
        if hostops02:
            hostops02_effects_lines({'operation': operation}, effects, request['plan'])          # listed for the owner before anything is created
        elif template['request'].get('writes_allowed'):
            effects_lines(effects)          # a write whose effects cannot be listed for the owner is refused before anything is created
        scope = m.SCOPE_STATEMENT
    else:
        need('gate_not_before' not in params, 'GATE_NOT_SUPPORTED_BY_THIS_PROFILE')
        rule = COLLECTION_SCOPE_RULES.get(operation)
        need(rule is not None, 'SCOPE_RULES_UNKNOWN_FOR_OPERATION')
        need((window['end'] - window['start']).total_seconds() <= rule['max_window_seconds'], 'WINDOW_OVER_THE_READ_CAP')
        request, request_raw = bind_request(profile, template, m, params, window, host, None, None)
        effects, success = None, None
        try:
            contract = family['files']['CONTRACT.txt'].decode('ascii')
        except UnicodeDecodeError:
            raise Refused('CONTRACT_DECISIONS_NOT_FOUND')
        scope = collection_scope(m, rule, contract, op['contract_sha256'], family['sums_sha256'], template['source_sha256'],
                                 window['start'].date().isoformat())

    names = names_for(owner, params['label'])
    root = out / CLAIM_ROOT
    provisional = owner_evidence(profile, mode, zulu(moment.replace(microsecond=0)), '0' * 64)

    def reference_text(go_sha):
        return 'PROVISIONAL sha256:' + go_sha

    def build(identity):
        return assemble(profile, template, rt, mode, owner, host, window, fields, identity, out, names, request_raw, provisional, effects,
                        scope, success, reference_text, params['label'])
    # ---- everything the family's source demands, in memory, before anything is created
    draft = build({'path': str(root), 'device': 1, 'inode': 1})
    need(executed_command is None or draft['config']['command_sha256'] == executed_command, 'COMMAND_PIN_NOT_THE_EXECUTED_ONE')
    for name, clock in (('at not_before', window['gate_start']), ('at latest_start', latest)):
        answer = authenticate(rt, profile, [request_raw, draft['authority'], draft['go']], clock)
        need(answer == 'ACCEPTED', 'FAMILY_REFUSES_THE_REQUEST_' + answer)
    h02 = None
    if hostops02:          # the rules of the operation's contract, on a plan the family's own authenticate() accepted
        h02 = hostops02_prepare({'operation': operation, 'mode': mode, 'plan': request['plan'], 'request': request, 'request_raw': request_raw,
                                 'entries': entries, 'receipts': receipts, 'evidence_facts': evidence_facts, 'blobs': blobs, 'params': params,
                                 'inputs': inputs, 'used': used, 'rt': rt, 'family': family, 'op': op, 'seal': seal, 'seals': seals, 'host': host,
                                 'now': moment, 'window': window, 'watchdog': watchdog, 'effects': effects, 'base': base,
                                 'source_sha256': template['source_sha256'], 'core': core, 'review': review, 'identity': identity,
                                 'copied': copied})          # rev 4: which plan members were copied from which cited receipt (K9 POLICY rows)

    # ---- creation: directory, claim root, runtime, templates, request
    make_directory(out)
    make_directory(root)
    make_directory(out / 'templates')
    written = {}
    for name in op['runtime_names']:
        written[name] = put(out, name, op['files'][name])
    for name in TEMPLATE_NAMES:
        written['templates/' + name] = put(out / 'templates', name, op['files'][name])
    written['REQUEST.BOUND.json'] = put(out, 'REQUEST.BOUND.json', request_raw)
    written['PARAMETERS.json'] = put(out, 'PARAMETERS.json', params_raw)
    if capture_context_raw is not None:
        written[CAPTURE_OWNER_CONTEXT_NAME] = put(out, CAPTURE_OWNER_CONTEXT_NAME, capture_context_raw)
    written['GO_SCOPE.txt'] = put(out, 'GO_SCOPE.txt', (scope + '\n').encode('ascii'))
    if profile == 'core':
        written['EFFECTS.json'] = put(out, 'EFFECTS.json', pretty(effects))
    identity = claim_identity(root)
    # ---- the family's dispatcher, on provisional documents held in memory, against the real claim root and runtime files
    rt = load_runtime({name: op['files'][name] for name in op['runtime_names']}, op['source_name'], out)
    draft = build(identity)
    config = draft['config']
    memory = {config['request']['path']: request_raw, config['authority']['path']: draft['authority'], config['go']['path']: draft['go'],
              config['payload']['path']: draft['payload'], str(out / 'DISPATCH.BOUND.json'): draft['config_raw']}
    ssh_paths = (fields['ssh_key']['path'], fields['known_hosts']['path'])
    proved = proofs(rt, profile, [request_raw, draft['authority'], draft['go']], draft['payload'], config, draft['config_raw'],
                    str(out / 'DISPATCH.BOUND.json'), window, memory, ssh_paths, op['files']['GO.UNBOUND.json'])

    sheet = {
        'schema': SHEET_SCHEMA, 'mode': mode, 'status': 'AWAITING_OWNER_SIGNATURE', 'binder': identity_of_binder, 'family': seal,
        'contract_sha256': op['contract_sha256'], 'operation': operation, 'phase': m.PHASE, 'profile': profile, 'label': params['label'],
        'writes_allowed': bool(template['request'].get('writes_allowed')), 'owner': owner, 'signature_model': params['signature_model'],
        'review': review,
        'source_name': op['source_name'], 'source_sha256': template['source_sha256'],
        'runtime_sha256': {name: sha(op['files'][name]) for name in op['runtime_names']}, 'scope_sha256': m.SCOPE_SHA256,
        'request_sha256': sha(request_raw), 'request_bytes': len(request_raw), 'parameters_sha256': params_sha,
        'go_scope_sha256': sha((scope + '\n').encode('ascii')), 'effects_sha256': written.get('EFFECTS.json'), 'success_criterion': success,
        'evidence': evidence_facts, 'plan_values_copied_from_receipts': copied, 'plan_values_equal_to_the_cited_receipts': checked,
        'contract_section_12_checks': section12, 'window': window_of_sheet(window, watchdog),
        'host_binding_sha256': host, 'command_sha256': config['command_sha256'], 'transport_reference': reference,
        'claim_root_identity': identity, 'attempt_directory': config['attempt_directory'],
        'authority_name': names['authority'], 'go_name': names['go'], 'files_sha256': written,
        'dispatcher': facts, 'provisional_proofs': proved, 'prepared_at_utc': zulu(moment.replace(microsecond=0)),
        'owner_signs_over': ['request_sha256', 'source_sha256', 'scope_sha256', 'go_scope_sha256', 'effects_sha256', 'success_criterion',
                             'window', 'host_binding_sha256', 'command_sha256', 'claim_root_identity', 'family', 'runtime_sha256',
                             'signature_model', 'review', 'evidence'],
    }
    if profile == 'collection' and 'candidates' in request['collection']:
        sheet['candidates'] = {key: len(value) for key, value in sorted(request['collection']['candidates'].items())}
    for key in ('purpose_pt', 'owner_summary_pt'):
        if key in params:
            sheet[key] = params[key]
    if hostops02:
        sheet['hostops02'] = h02
        sheet['owner_signs_over'] = sheet['owner_signs_over'] + ['hostops02']
    sheet_raw = pretty(sheet)
    digest = put(out, 'PREPARE.json', sheet_raw)
    question = question_text(sheet, digest, effects, request['plan'] if profile == 'core' else None)
    put(out, 'OWNER_QUESTION.txt', question)
    if h02 is not None and h02['spare_of'] is not None:          # the one spare of that primary, beside the primary's directory
        registry = Path(h02['spare_of']['registry'])
        put(registry.parent, registry.name, pretty({'schema': SPARE_REGISTRY_SCHEMA, 'primary_bound': h02['spare_of']['bound'],
                                                    'primary_go_sha256': h02['spare_of']['go_sha256'], 'spare_bound': str(out),
                                                    'spare_label': params['label'], 'spare_prepare_json_sha256': digest}))
    return {'status': 'PREPARED_AWAITING_OWNER_SIGNATURE', 'mode': mode, 'bound': str(out), 'prepare_json_sha256': digest,
            'owner_question_file': str(out / 'OWNER_QUESTION.txt'), 'owner_question_sha256': sha(question),
            'owner_question_pt': question.decode('utf-8'), 'sheet': sheet}


# ---------------------------------------------------------------- an existing bound directory
def open_bound(bound, signed):
    """Reads a bound directory and proves it is the one prepare (and, when signed, sign) wrote."""
    bound = Path(bound)
    need(bound.is_absolute() and bound.is_dir() and not bound.is_symlink(), 'BOUND_NOT_FOUND')
    bound = bound.resolve()
    private_directory(bound, 'BOUND_NOT_PRIVATE')
    sheet_raw = read_file(bound / 'PREPARE.json', 1024 * 1024, 'BOUND_NOT_PREPARED', private=True)
    sheet = strict_json(sheet_raw, 'BOUND_NOT_PREPARED')
    need(type(sheet) is dict and sheet.get('schema') == SHEET_SCHEMA and type(sheet.get('files_sha256')) is dict
         and type(sheet.get('label')) is str and re.fullmatch(LABEL, sheet['label']), 'BOUND_NOT_PREPARED')
    mode_guard(sheet.get('mode'), bound, sheet.get('owner'))
    expected = set(sheet['files_sha256']) | {'PREPARE.json', 'OWNER_QUESTION.txt'}
    private_directory(bound / 'templates', 'BOUND_NOT_PRIVATE')
    names = names_for(sheet['owner'], sheet['label'])
    signed_names = {names['authority'], names['go'], names['payload'], 'DISPATCH.BOUND.json', 'CLAIM_ROOT_IDENTITY.json', 'SHA256SUMS'}
    if sheet['mode'] == REAL:
        need(CAPTURE_OWNER_CONTEXT_NAME in expected, 'CAPTURE_GITHUB_CONTEXT_REQUIRED')
        signed_names.add(CAPTURE_OWNER_READBACK_NAME)
    present, proofs_present = set(), []
    for path in bound.rglob('*'):
        relative = path.relative_to(bound)
        if relative.parts[0] == CLAIM_ROOT:
            continue
        if path.is_symlink() or not path.is_dir():
            if len(relative.parts) == 1 and re.fullmatch(PROOF_NAME, relative.name):
                proofs_present.append(relative.name)
            else:
                present.add(str(relative))
        else:
            # No directory but its own: a bytecode cache beside the runtime files could be executed in their place.
            need(str(relative) in BOUND_DIRECTORIES, 'BOUND_SET_HOLDS_A_DIRECTORY_THAT_IS_NOT_ITS_OWN')
    if signed:
        need(present == expected | signed_names, 'BOUND_FILE_SET_NOT_SIGNED')
    else:
        need(present == expected and not proofs_present, 'BOUND_FILE_SET_OR_ALREADY_SIGNED')
    files = {}
    for name in sorted(present):
        files[name] = read_file(bound / name, 8 * 1024 * 1024, 'BOUND_CHANGED', private=True)
    need(all(sha(files[name]) == digest for name, digest in sheet['files_sha256'].items()), 'BOUND_CHANGED')
    effects = strict_json(files['EFFECTS.json'], 'BOUND_CHANGED') if 'EFFECTS.json' in files else None
    bound_request = strict_json(files.get('REQUEST.BOUND.json', b''), 'BOUND_CHANGED')
    try:
        question = question_text(sheet, sha(sheet_raw), effects, bound_request.get('plan') if type(bound_request) is dict else None)
    except (Refused, KeyError, TypeError, ValueError, AttributeError):          # a sheet edited into a shape no prepare writes
        raise Refused('OWNER_QUESTION_CHANGED')
    need(files['OWNER_QUESTION.txt'] == question, 'OWNER_QUESTION_CHANGED')
    if signed:
        listed = {}
        for line in files['SHA256SUMS'].decode('ascii', 'replace').splitlines():
            match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_./-]+)', line)
            need(match and match.group(2) not in listed, 'BOUND_SUMS_INVALID')
            listed[match.group(2)] = match.group(1)
        need(listed == {name: sha(raw) for name, raw in files.items() if name != 'SHA256SUMS'}, 'BOUND_SUMS_INVALID')
    runtime = {name: files[name] for name in sheet.get('runtime_sha256', {})}
    need(set(runtime) == set(sheet['runtime_sha256']) and sheet.get('source_name') in runtime, 'BOUND_CHANGED')
    rt = load_runtime(runtime, sheet['source_name'], bound)
    profile = profile_of(rt['source'])
    need(profile == sheet.get('profile') and rt['source'].OPERATION == sheet.get('operation'), 'BOUND_CHANGED')
    op_files = dict(runtime)
    for name in TEMPLATE_NAMES:
        op_files[name] = files['templates/' + name]
    facts = dispatcher_facts(rt, op_files)
    template = {key: strict_json(op_files[name], 'BOUND_CHANGED') for key, name in zip(('request', 'authority', 'go', 'config', 'proof'), TEMPLATE_NAMES)}
    template['source_sha256'] = sha(rt['source_bytes'])
    w = sheet['window']
    window = {'start': parse_utc(w['not_before']), 'end': parse_utc(w['not_after']), 'gate_start': parse_utc(w['gate_not_before']),
              'gate_end': parse_utc(w['gate_not_after'])}
    # What the owner is shown is derived again from what is bound: the window in Brasília time, its span, its date and
    # the latest start from the four UTC instants; the other displayed members from the files of the set.
    watchdog = template['config'].get('watchdog_seconds')
    need(type(watchdog) is int and w == window_of_sheet(window, watchdog), 'SHEET_WINDOW_NOT_DERIVED_FROM_ITS_UTC_FIELDS')
    params = strict_json(files['PARAMETERS.json'], 'BOUND_CHANGED')
    request = strict_json(files['REQUEST.BOUND.json'], 'BOUND_CHANGED')
    need(type(params) is dict and type(request) is dict and type(template['request']) is dict, 'BOUND_CHANGED')
    candidates = request['collection'].get('candidates') if profile == 'collection' and type(request.get('collection')) is dict else None
    derived = {'writes_allowed': bool(template['request'].get('writes_allowed')), 'label': params.get('label'), 'signature_model': params.get('signature_model'),
               'purpose_pt': params.get('purpose_pt'), 'owner_summary_pt': params.get('owner_summary_pt'),
               'parameters_sha256': sha(files['PARAMETERS.json']), 'request_sha256': sha(files['REQUEST.BOUND.json']),
               'source_sha256': sha(rt['source_bytes']), 'scope_sha256': rt['source'].SCOPE_SHA256, 'go_scope_sha256': sha(files['GO_SCOPE.txt']),
               'effects_sha256': sha(files['EFFECTS.json']) if profile == 'core' and 'EFFECTS.json' in files else None,
               'candidates': {key: len(value) for key, value in candidates.items()} if type(candidates) is dict else None}
    need(all(sheet.get(key) == value for key, value in derived.items()), 'SHEET_FIELD_NOT_DERIVED_FROM_THE_BOUND_FILES')
    review, declared = sheet.get('review'), params.get('review')
    # a review (or the owner's waiver) is on the sheet of every write and of every HOSTOPS02 request (K11 starts a container)
    reviewed = derived['writes_allowed'] or 'hostops02' in sheet
    need(type(sheet.get('signature_model')) is str and sheet['signature_model'] in SIGNATURE_MODELS and (review is not None) == reviewed
         and (review is None or (type(review) is dict and type(declared) is dict and review.get('kind') == declared.get('kind'))),
         'SHEET_FIELD_NOT_DERIVED_FROM_THE_BOUND_FILES')
    if profile == 'collection':
        rule = COLLECTION_SCOPE_RULES.get(sheet['operation'])
        need(rule is not None, 'SCOPE_RULES_UNKNOWN_FOR_OPERATION')
        need((window['end'] - window['start']).total_seconds() <= rule['max_window_seconds'], 'WINDOW_OVER_THE_READ_CAP')
    if 'hostops02' in sheet:
        # a HOSTOPS02 sheet belongs to a seal with a core, and the input files it shows are the ones the bound request carries
        h02 = sheet['hostops02']
        need(type(sheet.get('family')) is dict and 'core' in sheet['family'] and type(h02) is dict and type(request.get('plan')) is dict
             and h02.get('bind_inputs') == bind_inputs_in_request(sheet['operation'], request['plan'], effects), 'SHEET_FIELD_NOT_DERIVED_FROM_THE_BOUND_FILES')
    else:
        need(type(sheet.get('family')) is not dict or 'core' not in sheet['family'], 'SHEET_FIELD_NOT_DERIVED_FROM_THE_BOUND_FILES')
    return {'bound': bound, 'sheet': sheet, 'sheet_raw': sheet_raw, 'files': files, 'rt': rt, 'profile': profile, 'facts': facts,
            'template': template, 'window': window, 'names': names, 'proofs_present': sorted(proofs_present), 'op_files': op_files}


def rebuild(state, fields, evidence, sheet_sha256):
    """The deterministic construction of the signed documents from the sheet, the bound request and the owner evidence."""
    sheet, rt, profile = state['sheet'], state['rt'], state['profile']
    files = state['files']
    scope = files['GO_SCOPE.txt'].decode('ascii')[:-1]
    effects = json.loads(files['EFFECTS.json']) if profile == 'core' else None
    signed_at = evidence['signed_at_utc'] if type(evidence) is dict else re.search(r' at (\S+) over sheet ', evidence).group(1)
    go_name = state['names']['go']

    def reference_text(go_sha):
        return ('sha256:%s (%s, owner answer recorded at %s, over sheet PREPARE.json sha256:%s)' % (go_sha, go_name, signed_at, sheet_sha256)
                if sheet['mode'] == REAL else
                'REHEARSAL sha256:%s (%s, no owner answer, synthetic time %s, sheet PREPARE.json sha256:%s)' % (go_sha, go_name, signed_at, sheet_sha256))
    # Paths are those of the directory the set was bound in (the claim root is tied to it): a copy elsewhere still verifies.
    original = Path(sheet['claim_root_identity']['path']).parent
    return assemble(profile, state['template'], rt, sheet['mode'], sheet['owner'], sheet['host_binding_sha256'], state['window'], fields,
                    sheet['claim_root_identity'], original, state['names'], files['REQUEST.BOUND.json'], evidence, effects, scope,
                    sheet['success_criterion'], reference_text, sheet['label'])


def reference_of(sheet, enforce_age=False):
    recorded = sheet.get('transport_reference')
    need(type(recorded) is dict and type(recorded.get('path')) is str and is_hash(recorded.get('sha256')), 'BOUND_CHANGED')
    fields, facts, host, executed = load_reference(Path(recorded['path']), sheet['mode'], enforce_age)
    need(facts['sha256'] == recorded['sha256'], 'TRANSPORT_REFERENCE_PIN')
    need(host == sheet['host_binding_sha256'], 'HOST_BINDING_NOT_REPRODUCED')
    return fields, facts, executed


def claim_root_state(state):
    root = state['bound'] / CLAIM_ROOT
    identity = claim_identity(root)
    need(identity == state['sheet']['claim_root_identity'], 'BOUND_SET_RELOCATED_OR_CLAIM_ROOT_CHANGED')
    return root, identity, sorted(os.listdir(str(root)))


# ---------------------------------------------------------------- sign
def sign(bound, sheet_sha256, signed_at, owner_answer, owner_api_proof=None, *, now=utc_now):
    need(os.geteuid() != 0, 'BIND_AS_ROOT')
    need(is_hash(sheet_sha256), 'SHEET_SHA256_INVALID')
    signed = parse_utc(signed_at, 'SIGNED_AT_NOT_UTC_SECONDS')
    state = open_bound(bound, signed=False)
    sheet = state['sheet']
    # The answer is given verbatim by the caller and only the literal word is a signature. A rehearsal has no owner
    # answer: its marker is the only value accepted there, so that a rehearsal can never record the owner's word.
    need(type(owner_answer) is str and owner_answer == (REAL_ANSWER if sheet['mode'] == REAL else REHEARSAL_ANSWER), 'OWNER_ANSWER_IS_NOT_THE_SIGNATURE')
    # The owner answered a question that quoted this hash. Any other sheet, or this one edited, is not what was signed.
    need(sha(state['sheet_raw']) == sheet_sha256, 'SHEET_IS_NOT_THE_ONE_THE_OWNER_SAW')
    identity_of_binder, _ = binder_identity()
    need(identity_of_binder == sheet.get('binder'), 'BINDER_CHANGED_SINCE_PREPARE')
    need(sha(state['files']['REQUEST.BOUND.json']) == sheet['request_sha256'] and sha(state['rt']['source_bytes']) == sheet['source_sha256']
         and sha(state['files']['GO_SCOPE.txt']) == sheet['go_scope_sha256'], 'BOUND_CHANGED')
    root, identity, entries = claim_root_state(state)
    need(not entries, 'CLAIM_ROOT_CHANGED_OR_USED')
    fields, reference, executed = reference_of(sheet)
    mode_guard(sheet['mode'], state['bound'], sheet['owner'], fields)
    window = state['window']
    watchdog = state['template']['config']['watchdog_seconds']
    latest = window['gate_end'] - timedelta(seconds=watchdog)
    moment = now()
    need(parse_utc(sheet['prepared_at_utc']) <= signed, 'SIGNATURE_BEFORE_THE_SHEET_EXISTED')
    need(signed <= moment, 'SIGNATURE_IN_THE_FUTURE')
    need(signed <= latest and moment <= latest, 'WINDOW_ALREADY_UNUSABLE')
    owner_packet = None
    channel = None
    if sheet['mode'] == REAL:
        need(type(owner_api_proof) is str, 'CAPTURE_OWNER_API_PROOF_REQUIRED')
        owner_packet = read_file(Path(owner_api_proof), 65536, 'CAPTURE_OWNER_API_PACKET_INVALID', private=True)
        record, channel = capture_signature_packet(state, owner_packet)
        need(signed == parse_utc(record['answered_at_utc']) and parse_utc(record['observed_at']) <= moment,
             'CAPTURE_OWNER_SIGNED_AT_NOT_THE_RESPONSE')
    evidence = owner_evidence(state['profile'], sheet['mode'], zulu(signed), sheet_sha256, channel)
    final = rebuild(state, fields, evidence, sheet_sha256)
    config = final['config']
    need(config['command_sha256'] == sheet['command_sha256'] and (executed is None or executed == config['command_sha256']),
         'COMMAND_PIN_NOT_THE_EXECUTED_ONE')
    need(zulu(latest) == sheet['window']['latest_start'] == config['latest_start'], 'BOUND_CHANGED')
    raws = [state['files']['REQUEST.BOUND.json'], final['authority'], final['go']]
    names = state['names']
    config_path = str(state['bound'] / 'DISPATCH.BOUND.json')
    memory = {config['authority']['path']: final['authority'], config['go']['path']: final['go'], config['payload']['path']: final['payload'],
              config_path: final['config_raw']}
    ssh_paths = (fields['ssh_key']['path'], fields['known_hosts']['path'])
    # ---- the final bytes, in memory, through the family's source and dispatcher before anything is written
    proofs(state['rt'], state['profile'], raws, final['payload'], config, final['config_raw'], config_path, window, memory, ssh_paths,
           state['op_files']['GO.UNBOUND.json'])
    # ---- exclusive writes
    if owner_packet is not None:
        put(state['bound'], CAPTURE_OWNER_READBACK_NAME, owner_packet)
    put(state['bound'], names['authority'], final['authority'])
    put(state['bound'], names['go'], final['go'])
    put(state['bound'], names['payload'], final['payload'])
    put(state['bound'], 'DISPATCH.BOUND.json', final['config_raw'])
    put(state['bound'], 'CLAIM_ROOT_IDENTITY.json', pretty(identity))
    sums = {}
    for path in sorted(state['bound'].rglob('*')):
        relative = path.relative_to(state['bound'])
        if relative.parts[0] != CLAIM_ROOT and not path.is_dir():
            sums[str(relative)] = sha(read_file(path, 8 * 1024 * 1024, 'WRITTEN_SET_CHECK', private=True))
    put(state['bound'], 'SHA256SUMS', ''.join('%s  %s\n' % (sums[name], name) for name in sorted(sums)).encode('ascii'))
    # ---- the written set, read from disk by the dispatcher's own read()
    need(dry_dispatch(state['rt'], config_path, sha(final['config_raw']), window['gate_start'], {}, ssh_paths) == 'ACCEPTED_UP_TO_THE_CLAIM',
         'WRITTEN_SET_CHECK')
    return {'status': 'BOUND_NOT_DISPATCHED', 'mode': sheet['mode'], 'operation': sheet['operation'], 'bound': str(state['bound']),
            'prepare_json_sha256': sheet_sha256, 'signed_at_utc': zulu(signed), 'request_sha256': sheet['request_sha256'],
            'authority_sha256': sha(final['authority']), 'go_sha256': sha(final['go']), 'payload_sha256': sha(final['payload']),
            'payload_bytes': len(final['payload']), 'config_sha256': sha(final['config_raw']), 'source_sha256': sheet['source_sha256'],
            'command_sha256': config['command_sha256'], 'host_binding_sha256': sheet['host_binding_sha256'],
            'window': sheet['window'], 'attempt_directory': config['attempt_directory'], 'authority_name': names['authority'],
            'go_name': names['go'], 'connection_files': reference['connection_files'],
            'owner_answer_verbatim': owner_answer,
            'prepare_command': dispatch_command(state['bound'], sha(final['config_raw']), 'prepare'),
            'next': 'run check; then the dispatcher prepare by hand, as block 6 of the runbook writes it (exit 2 and AWAITING_PUBLICATION_NO_SPAWN are '
                    'the success of that step)'}


def dispatch_command(bound, config_sha256, phase, proof=None):
    """The family's dispatcher as the runbook runs it. The pycache prefix is a placeholder on purpose: the dispatcher imports
    its three siblings by name, and this interpreter would execute a cached bytecode file of matching time and size in
    place of the pinned source (-B only stops writing). A fresh, empty, private directory as prefix leaves it no cache."""
    command = ['/usr/bin/python3', '-B', '-X', 'pycache_prefix=' + PYCACHE_PLACEHOLDER, str(Path(bound) / 'dispatch_once.py'),
               '--config', str(Path(bound) / 'DISPATCH.BOUND.json'), '--config-sha256', config_sha256, '--phase', phase]
    if proof is not None:
        command += ['--publication-proof', proof[0], '--publication-proof-sha256', proof[1]]
    return command


# ---------------------------------------------------------------- check
def signed_state(bound):
    """A signed set, with its documents proved to be the deterministic construction from the sheet and their own evidence."""
    state = open_bound(bound, signed=True)
    sheet, files, names = state['sheet'], state['files'], state['names']
    authority = strict_json(files[names['authority']], 'BOUND_CHANGED')
    evidence = authority.get('owner_evidence') if type(authority) is dict else None
    if state['profile'] == 'core':
        match = re.fullmatch(r'(\S+) answered "([^"]+)" \((.+)\) at (\S+) over sheet PREPARE\.json sha256:([0-9a-f]{64})', evidence if type(evidence) is str else '')
        need(match, 'OWNER_EVIDENCE_INVALID')
        owner, answer, channel, signed_at, sheet_sha256 = match.groups()
    else:
        need(type(evidence) is dict and set(evidence) == {'channel', 'owner_answer_verbatim', 'signed_at_utc', 'prepare_sheet_sha256'}, 'OWNER_EVIDENCE_INVALID')
        owner, answer, channel, signed_at, sheet_sha256 = (authority.get('owner'), evidence['owner_answer_verbatim'], evidence['channel'],
                                                           evidence['signed_at_utc'], evidence['prepare_sheet_sha256'])
    if sheet['mode'] == REAL:
        record, expected_channel = capture_signature_packet(state, files[CAPTURE_OWNER_READBACK_NAME])
        need(record['answered_at_utc'] == signed_at, 'CAPTURE_OWNER_SIGNED_AT_NOT_THE_RESPONSE')
        wanted = (REAL_OWNER, REAL_ANSWER, expected_channel)
    else:
        wanted = (REHEARSAL_OWNER, REHEARSAL_ANSWER, REHEARSAL_CHANNEL)
    need((owner, answer, channel) == wanted and sheet_sha256 == sha(state['sheet_raw']), 'OWNER_EVIDENCE_INVALID')
    signed = parse_utc(signed_at, 'OWNER_EVIDENCE_INVALID')
    need(parse_utc(sheet['prepared_at_utc']) <= signed, 'OWNER_EVIDENCE_INVALID')
    config = strict_json(files['DISPATCH.BOUND.json'], 'BOUND_CHANGED')
    need(type(config) is dict and all(key in config for key in ('target', 'remote_command', 'ssh_key', 'known_hosts')), 'BOUND_CHANGED')
    fields = {key: config[key] for key in ('target', 'remote_command', 'ssh_key', 'known_hosts')}
    need(type(fields['target']) is str and all(type(fields[key]) is dict and set(fields[key]) == {'path', 'sha256'} for key in ('ssh_key', 'known_hosts')),
         'BOUND_CHANGED')
    mode_guard(sheet['mode'], state['bound'], sheet['owner'], fields)
    need(host_binding(fields['target'], fields['known_hosts']['sha256']) == sheet['host_binding_sha256'], 'HOST_BINDING_NOT_REPRODUCED')
    final = rebuild(state, fields, evidence, sheet_sha256)
    need(final['authority'] == files[names['authority']] and final['go'] == files[names['go']] and final['payload'] == files[names['payload']]
         and final['config_raw'] == files['DISPATCH.BOUND.json'], 'NOT_THE_DETERMINISTIC_CONSTRUCTION')
    need(final['config']['command_sha256'] == sheet['command_sha256'], 'NOT_THE_DETERMINISTIC_CONSTRUCTION')
    state.update(config=final['config'], config_raw=final['config_raw'], fields=fields, signed_at=zulu(signed),
                 raws=[files['REQUEST.BOUND.json'], final['authority'], final['go']], payload=final['payload'])
    return state


def attempt_state(state, root=None):
    """What the dispatcher has left under a claim root of this set (names only): its own, unless another is given."""
    root = state['bound'] / CLAIM_ROOT if root is None else Path(root)
    private_directory(root, 'CLAIM_ROOT_NOT_PRIVATE')
    attempt = root / (state['sheet']['label'] + '-once')
    claim = root / ('.go-' + sha(state['raws'][2]) + '.claim')
    names = sorted(os.listdir(str(attempt))) if attempt.is_dir() and not attempt.is_symlink() else None
    if names is None:
        phase = 'NOT_PREPARED' if not os.path.lexists(str(claim)) else 'CLAIMED_WITHOUT_ATTEMPT_DIRECTORY'
    elif 'exit.json' in names:
        phase = 'FINISHED'
    elif 'spawn.claim' in names:
        phase = 'SPAWN_CLAIMED_NO_RESULT'
    elif names == ['intent.json']:
        phase = 'PREPARED_AWAITING_PUBLICATION'
    else:
        phase = 'UNEXPECTED_ATTEMPT_CONTENT'
    return attempt, claim, names, phase


def check(bound, family_directory=None, gates_path=None, step='prepare', *, now=utc_now):
    need(os.geteuid() != 0, 'BIND_AS_ROOT')
    state = signed_state(bound)
    sheet, files, names = state['sheet'], state['files'], state['names']
    identity_of_binder, seals = binder_identity()
    root, identity, entries = claim_root_state(state)
    need(strict_json(files['CLAIM_ROOT_IDENTITY.json'], 'BOUND_CHANGED') == identity, 'BOUND_CHANGED')
    h02 = sheet.get('hostops02')
    required = h02['dispatch_gates'] if h02 is not None else []
    need(gates_path is None or required, 'GATES_NOT_DEFINED_FOR_THIS_SET')
    need(step in ('prepare', 'resume') and (step == 'prepare' or h02 is not None), 'STEP_RESUME_NOT_FOR_THIS_OPERATION')
    family_checked, family = False, None
    if family_directory is not None:
        family = verify_family(family_directory)
        need(accepted_seal(seals, family['sums_sha256']) == sheet['family'], 'FAMILY_IS_NOT_THE_ONE_BOUND')
        op = select_operation(family, sheet['operation'])
        need(all(op['files'][name] == state['op_files'][name] for name in state['op_files']) and op['contract_sha256'] == sheet['contract_sha256'],
             'FAMILY_IS_NOT_THE_ONE_BOUND')
        family_rt = load_runtime(op['files'], op['source_name'], op['directory'])
        template_chain(op, family_rt, state['facts'])
        if h02 is not None:          # the frozen core beside the family, and the core's own check of the build, again
            core = hostops02_core(family, sheet['family'], op, family_rt)
            need((core['core_sha256sums_sha256'], core['generation_sha256'], core['assembly']) == (
                h02['core']['core_sha256sums_sha256'], h02['core']['generation_sha256'], h02['core']['assembly']), 'FAMILY_IS_NOT_THE_ONE_BOUND')
        if state['profile'] == 'collection':
            scope = collection_scope(state['rt']['source'], COLLECTION_SCOPE_RULES[sheet['operation']], family['files']['CONTRACT.txt'].decode('ascii'),
                                     op['contract_sha256'], family['sums_sha256'], sheet['source_sha256'], sheet['window']['date_utc'])
            need((scope + '\n').encode('ascii') == files['GO_SCOPE.txt'], 'FAMILY_IS_NOT_THE_ONE_BOUND')
        family_checked = True
    config, window = state['config'], state['window']
    ssh_paths = (state['fields']['ssh_key']['path'], state['fields']['known_hosts']['path'])
    proved = proofs(state['rt'], state['profile'], state['raws'], state['payload'], config, state['config_raw'],
                    str(state['bound'] / 'DISPATCH.BOUND.json'), window, {}, ssh_paths, state['op_files']['GO.UNBOUND.json'])
    local = run_payload_locally(state['payload'])
    attempt, claim, attempt_names, phase = attempt_state(state)
    moment = now()
    latest = parse_utc(config['latest_start'])
    if moment < window['gate_start']:
        by_clock = 'VALID_WINDOW_NOT_YET_OPEN'
    elif moment <= latest:
        by_clock = 'VALID_WINDOW_OPEN'
    else:
        by_clock = 'VALID_BUT_PAST_LATEST_START_THE_DISPATCHER_WILL_REFUSE'
    # The dry runs above stop before the exclusive creation of the claim: once a claim exists they still say "accepted up
    # to the claim", and the real prepare would fail at that creation. The verdict says so.
    verdict = {'NOT_PREPARED': by_clock, 'PREPARED_AWAITING_PUBLICATION': 'VALID_ALREADY_PREPARED', 'SPAWN_CLAIMED_NO_RESULT': 'VALID_GO_SPENT',
               'FINISHED': 'VALID_GO_SPENT'}.get(phase, 'VALID_BUT_THE_CLAIM_ROOT_IS_NOT_AS_THE_DISPATCHER_LEAVES_IT')
    extra = {}
    if h02 is not None:
        # The dispatch gates of the operation's contract (and of a spare): they must hold minutes before the dispatch. The
        # sealed bytes do not look at them; this verdict does. A gate that needs evidence and was given none has failed.
        gates, gates_sha, gates_base = ({}, None, None) if gates_path is None else load_gates(gates_path, sheet['operation'])
        if required and (gates_path is not None or required == ['SPARE_PRIMARY_NEVER_PREPARED']):
            evaluated = evaluate_gates(state, gates, gates_base, seals, step, moment, family)
        else:
            evaluated = {'required': required, 'evaluated': False, 'failed': ['GATES_FILE_NOT_GIVEN'] if required else [], 'facts': {}, 'step': step}
        evaluated['gates_file_sha256'] = gates_sha
        allowed = not evaluated['failed']
        # A minute to avoid is not a dispatch verdict (K2a CONTRACT 5 step 6, K11 CONTRACT 8 step 7): the dispatcher's
        # prepare and the resume both wait for the next usable minute.
        avoid = in_a_minute_to_avoid(moment) if h02['minutes_to_avoid'] else None
        if step == 'resume':
            if phase == 'PREPARED_AWAITING_PUBLICATION':
                ok = allowed and not avoid and window['gate_start'] <= moment <= latest
                verdict = 'VALID_RESUME_ALLOWED_BY_THE_GATES' if ok else 'VALID_BUT_RESUME_GATES_NOT_MET'
            elif phase == 'NOT_PREPARED':
                verdict = 'VALID_BUT_NOTHING_TO_RESUME'
        elif phase == 'NOT_PREPARED' and verdict in ('VALID_WINDOW_OPEN', 'VALID_WINDOW_NOT_YET_OPEN') and not allowed:
            verdict = 'VALID_BUT_DISPATCH_GATES_NOT_MET'
        elif verdict == 'VALID_WINDOW_OPEN' and avoid:
            verdict = 'VALID_BUT_NOW_IS_A_MINUTE_TO_AVOID'
        extra = {'dispatch_gates': evaluated, 'dispatch_allowed_by_the_gates': allowed, 'now_is_a_minute_to_avoid': avoid}
    return {'status': 'CHECKED', 'verdict': verdict, 'window_verdict': by_clock, 'a_new_dispatcher_prepare_would_reach_the_claim_and': (
                'CREATE_IT' if phase == 'NOT_PREPARED' and by_clock == 'VALID_WINDOW_OPEN' else 'BE_REFUSED'), **extra,
            'mode': sheet['mode'], 'operation': sheet['operation'], 'bound': str(state['bound']),
            'prepare_json_sha256': sha(state['sheet_raw']), 'request_sha256': sheet['request_sha256'], 'authority_sha256': sha(state['raws'][1]),
            'go_sha256': sha(state['raws'][2]), 'payload_sha256': sha(state['payload']), 'config_sha256': sha(state['config_raw']),
            'signed_at_utc': state['signed_at'], 'window': sheet['window'], 'now_utc': zulu(moment.replace(microsecond=0)),
            'documents_are_the_deterministic_construction': True, 'family_seal_and_templates_rechecked': family_checked,
            'binder_unchanged_since_prepare': identity_of_binder == sheet['binder'], 'proofs': proved,
            'final_payload_run_locally_as_this_user': local, 'attempt_phase': phase,
            'prepare_command': dispatch_command(state['bound'], sha(state['config_raw']), 'prepare'),
            'wrote_nothing': True}


# ---------------------------------------------------------------- publication proof
def publish_proof(bound, comment_id, created_at, name='PUBLICATION.PROOF.json', *, now=utc_now):
    need(os.geteuid() != 0, 'BIND_AS_ROOT')
    need(type(name) is str and re.fullmatch(PROOF_NAME, name), 'PROOF_NAME_INVALID')
    published = parse_utc(created_at, 'CREATED_AT_NOT_UTC_SECONDS')
    state = signed_state(bound)
    sheet, config, d, m = state['sheet'], state['config'], state['rt']['dispatch'], state['rt']['source']
    if sheet['mode'] == REAL:
        need(type(comment_id) is str and re.fullmatch(COMMENT_ID, comment_id), 'COMMENT_ID_INVALID')
    else:
        need(comment_id == REHEARSAL_PUBLICATION, 'REHEARSAL_SET_WITH_A_REAL_PUBLICATION')
    claim_root_state(state)
    attempt, claim, names, phase = attempt_state(state)
    need(phase == 'PREPARED_AWAITING_PUBLICATION', 'ATTEMPT_NOT_AWAITING_PUBLICATION')
    config_sha, go_sha = sha(state['config_raw']), sha(state['raws'][2])
    facts = state['facts']
    claim_raw = canonical({'schema': facts['claim_schema'], 'go_sha256': go_sha, 'config_sha256': config_sha})
    try:
        need(d.read(str(claim), sha(claim_raw)) == claim_raw, 'CLAIM_IS_NOT_OF_THIS_CONFIG')
        intent_raw = read_file(attempt / 'intent.json', 65536, 'INTENT_UNREADABLE', private=True)
        need(d.read(str(attempt / 'intent.json'), sha(intent_raw), 65536) == intent_raw, 'INTENT_UNREADABLE')
    except ValueError:
        raise Refused('CLAIM_IS_NOT_OF_THIS_CONFIG')
    intent = strict_json(intent_raw, 'INTENT_DOES_NOT_BIND_THIS_SET')
    expected = {'schema': facts['intent_schema'], 'config_sha256': config_sha, 'payload_sha256': sha(state['payload']),
                'request_sha256': sheet['request_sha256'], 'go_sha256': go_sha, 'started_at': intent.get('started_at') if type(intent) is dict else None,
                'attempts': 1, 'retry': False}
    need(intent == expected and type(intent['started_at']) is str, 'INTENT_DOES_NOT_BIND_THIS_SET')
    try:
        started = m.instant(intent['started_at'])
    except ValueError:
        raise Refused('INTENT_DOES_NOT_BIND_THIS_SET')
    moment = now()
    need(state['window']['gate_start'] <= started, 'INTENT_DOES_NOT_BIND_THIS_SET')
    need(started <= published, 'PUBLISHED_BEFORE_THE_INTENT')
    need(published <= moment, 'PUBLISHED_IN_THE_FUTURE')
    need(moment <= parse_utc(config['latest_start']), 'WINDOW_ALREADY_UNUSABLE')
    proof = {'schema': facts['publication_schema'], 'status': 'PUBLISHED', 'owner': sheet['owner'], 'publication_ref': comment_id,
             'go_sha256': go_sha, 'config_sha256': config_sha, 'intent_sha256': sha(intent_raw), 'published_at': published.isoformat()}
    need(set(proof) == set(state['template']['proof']), 'TEMPLATE_INVALID')
    raw = canonical(proof)
    digest = put(state['bound'], name, raw)
    path = str(state['bound'] / name)
    try:
        need(d.read(path, digest, 65536) == raw, 'WRITTEN_FILE_READ_BACK')
    except ValueError:
        raise Refused('WRITTEN_FILE_READ_BACK')
    return {'status': 'PROOF_WRITTEN_NOT_DISPATCHED', 'mode': sheet['mode'], 'operation': sheet['operation'], 'publication_proof_path': path,
            'publication_proof_sha256': digest, 'config_sha256': config_sha, 'go_sha256': go_sha, 'intent_sha256': sha(intent_raw),
            'intent_started_at': intent['started_at'], 'published_at': proof['published_at'], 'publication_ref': comment_id,
            'latest_start': config['latest_start'],
            'resume_command': dispatch_command(state['bound'], config_sha, 'resume', (path, digest)),
            'next': 'resume runs ONCE and is the only step that contacts the host; this binder never runs it'}


# ---------------------------------------------------------------- status of a finished attempt
def safe_codes(value, pattern):
    return [item for item in value if type(item) is str and re.fullmatch(pattern, item)] if type(value) is list else None


def status(bound, show_findings=False):
    """Read-only. Statuses, constant codes, counts and hashes: never a value the receipt observed on the host. The findings
    of a collection receipt are constant codes too, but they say what the host is like: only their number is printed unless
    show_findings is asked for."""
    need(os.geteuid() != 0, 'BIND_AS_ROOT')
    return attempt_report(signed_state(bound), show_findings)[0]


def attempt_report(state, show_findings=False):
    """The report of `status` and, when the attempt ended with a result of the transport, the stored standard output.
    Which claim root is read: the set's own; for a relocated copy that does not itself hold a finished attempt, the ORIGINAL
    root named on the sheet when it still exists with the signed identity, because the family's dispatcher run from a copy
    reads its blobs and claims at the original paths; when the original is gone, the copy's own content is reported with
    no statement about what was consumed."""
    sheet, config, m = state['sheet'], state['config'], state['rt']['source']
    identity = sheet['claim_root_identity']
    need(type(identity) is dict and type(identity.get('path')) is str and clean_absolute(identity['path']), 'BOUND_CHANGED')
    relocated = claim_identity(state['bound'] / CLAIM_ROOT) != identity
    attempt, claim, names, phase = attempt_state(state)
    root_read = 'OF_THIS_DIRECTORY'
    if relocated and phase == 'FINISHED':
        root_read = 'OF_THIS_COPY_WHICH_HOLDS_A_FINISHED_ATTEMPT'
    elif relocated:
        try:
            original_found = claim_identity(Path(identity['path'])) == identity
        except Refused:
            original_found = False
        if original_found:
            attempt, claim, names, phase = attempt_state(state, Path(identity['path']))
            root_read = 'ORIGINAL_NAMED_ON_THE_SHEET'
        else:
            root_read = 'OF_THIS_COPY_THE_ORIGINAL_WAS_NOT_FOUND'
    report = {'status': phase, 'verified': False, 'mode': sheet['mode'], 'operation': sheet['operation'], 'config_sha256': sha(state['config_raw']),
              'request_sha256': sheet['request_sha256'], 'go_sha256': sha(state['raws'][2]), 'payload_sha256': sha(state['payload']),
              'attempt_files': names, 'claim_exists': os.path.lexists(str(claim)), 'go_spent': bool(names) and 'spawn.claim' in names,
              'retry_allowed': False, 'bound_set_is_a_relocated_copy': relocated, 'claim_root_read': root_read,
              'publication_proofs': state['proofs_present']}
    if phase != 'FINISHED':
        if root_read == 'OF_THIS_COPY_THE_ORIGINAL_WAS_NOT_FOUND':
            report.update(status='RELOCATED_COPY_STATE_NOT_KNOWN', attempt_phase_in_this_copy=phase, claim_exists=None, go_spent=None,
                          verdict_pt='Este diretório é uma cópia e a raiz de uso único original, a que o GO assinou, não foi encontrada: o que a '
                                     'cópia mostra não diz o que já foi consumido. Nunca despachar a partir de uma cópia.')
            return report, None
        if phase == 'PREPARED_AWAITING_PUBLICATION' and state['proofs_present']:
            report['status'] = phase = 'PREPARED_PROOF_WRITTEN_RESUME_NOT_RUN'
        report['verdict_pt'] = {
            'NOT_PREPARED': 'O prepare do dispatcher ainda não rodou para este conjunto: nada foi consumido.',
            'PREPARED_AWAITING_PUBLICATION': 'Prepare feito (claim e intent.json existem); falta publicar o intent, gravar a prova e rodar o resume.',
            'PREPARED_PROOF_WRITTEN_RESUME_NOT_RUN': 'Prepare feito e prova de publicação gravada; o resume ainda não rodou.',
            'SPAWN_CLAIMED_NO_RESULT': 'spawn.claim existe sem exit.json: a única tentativa foi consumida e o resultado é desconhecido. Nunca repetir o resume.',
        }.get(phase, 'Conteúdo inesperado sob a raiz de uso único: parar e relatar, sem mexer em nada.')
        if root_read == 'ORIGINAL_NAMED_ON_THE_SHEET':
            report['verdict_pt'] += ' (Lido na raiz de uso único ORIGINAL, a que a folha nomeia: este diretório é uma cópia.)'
        return report, None
    need(names == ['exit.json', 'intent.json', 'spawn.claim', 'stderr.private', 'stdout.private.json'], 'ATTEMPT_FILE_SET')
    exit_raw = read_file(attempt / 'exit.json', 65536, 'EXIT_JSON_UNREADABLE', private=True)
    out = read_file(attempt / 'stdout.private.json', 4 * 1024 * 1024, 'STDOUT_UNREADABLE', private=True, allow_empty=True)
    err = read_file(attempt / 'stderr.private', 4 * 1024 * 1024, 'STDERR_UNREADABLE', private=True, allow_empty=True)
    result = strict_json(exit_raw, 'EXIT_JSON_INVALID')
    need(type(result) is dict and exit_raw == canonical(result), 'EXIT_JSON_INVALID')
    state['attempt_raw'] = {'exit': exit_raw}          # for a rule that cites this set; never printed
    need(result.get('config_sha256') == report['config_sha256'] and result.get('request_sha256') == report['request_sha256']
         and result.get('go_sha256') == report['go_sha256'], 'EXIT_JSON_DOES_NOT_BIND_THIS_SET')
    need(result.get('stdout_sha256') == sha(out) and result.get('stderr_sha256') == sha(err), 'EXIT_JSON_DOES_NOT_MATCH_THE_STORED_OUTPUT')
    transport_status = result.get('status')
    report.update(status=transport_status if type(transport_status) is str and re.fullmatch(CODE, transport_status) else 'UNKNOWN',
                  code=result.get('code') if type(result.get('code')) is str and re.fullmatch(CODE, result['code']) else None,
                  returncode=result.get('returncode') if type(result.get('returncode')) is int else None,
                  finished_at=result.get('finished_at') if type(result.get('finished_at')) is str and len(result['finished_at']) <= 40 else None,
                  exit_json_sha256=sha(exit_raw), stdout_sha256=sha(out), stdout_bytes=len(out), stderr_sha256=sha(err), stderr_empty=err == b'')
    receipt = None
    if len(out) <= 65536 + 1:
        try:
            receipt = strict_json(out, 'RECEIPT_INVALID')
        except Refused:
            receipt = None
    if transport_status not in RECEIPT_STATUS:
        refusal = receipt.get('code') if type(receipt) is dict else None
        report['remote_code'] = refusal if type(refusal) is str and re.fullmatch(CODE, refusal) else None
        report['verdict_pt'] = ('%s: não há recibo em que se apoiar. A assinatura está gasta; uma nova tentativa exige novo pedido e nova '
                                'assinatura. Nunca repetir o resume.' % report['status'])
        return report, None
    need(type(receipt) is dict, 'RECEIPT_INVALID')
    body = dict(receipt)
    claimed = body.pop('metadata_sha256', None)
    bindings = {'schema': receipt.get('schema') == m.RECEIPT_SCHEMA,
                'request_sha256': receipt.get('request_sha256') == report['request_sha256'],
                'authority_sha256': receipt.get('authority_sha256') == sha(state['raws'][1]),
                'go_sha256': receipt.get('go_sha256') == report['go_sha256'],
                'payload_sha256': receipt.get('payload_sha256') == sheet['source_sha256'],
                'host_binding_sha256': receipt.get('host_binding_sha256') == sheet['host_binding_sha256'],
                'status_pairs_with_transport_status': receipt.get('status') == RECEIPT_STATUS[transport_status],
                'metadata_sha256': is_hash(claimed) and sha(canonical(body)) == claimed}
    report.update(receipt_status=RECEIPT_STATUS[transport_status] if bindings['status_pairs_with_transport_status'] else None,
                  receipt_bindings=bindings, metadata_sha256=claimed if is_hash(claimed) else None)
    if state['profile'] == 'core':
        outcome = receipt.get('outcome')
        go = json.loads(state['raws'][2])
        counts = receipt.get('mutating_calls')
        report.update(outcome=outcome if type(outcome) is str and re.fullmatch(CODE, outcome) else None,
                      remote_code=receipt.get('code') if type(receipt.get('code')) is str and re.fullmatch(CODE, receipt['code']) else None,
                      success_criterion=go['success_criterion'], success_criterion_met=outcome == go['success_criterion'],
                      size_reductions=safe_codes(receipt.get('size_reductions'), CODE),
                      mutating_calls={key: value for key, value in counts.items() if type(value) is int and re.fullmatch('[a-z_]{1,40}', key)}
                      if type(counts) is dict else None)
    else:
        observation = receipt.get('observation') if type(receipt.get('observation')) is dict else {}
        sections = observation.get('sections') if type(observation.get('sections')) is dict else {}
        report.update(observation_status=observation.get('status') if type(observation.get('status')) is str and re.fullmatch(CODE, observation['status']) else None,
                      section_status={name: (sections[name].get('status') if type(sections[name]) is dict and type(sections[name].get('status')) is str
                                             and re.fullmatch(CODE, sections[name]['status']) else None)
                                      for name in sorted(sections) if re.fullmatch('[a-z_]{1,40}', name)},
                      size_reductions=safe_codes(observation.get('size_reductions'), CODE),
                      problems=safe_codes(observation.get('problems'), '[a-z_]{1,40}:' + CODE),
                      findings_count=len(observation['findings']) if type(observation.get('findings')) is list else None,
                      problems_truncated=observation.get('problems_truncated') is True, findings_truncated=observation.get('findings_truncated') is True,
                      commands_started=observation.get('commands_started') if type(observation.get('commands_started')) is int else None)
        if show_findings:
            report['findings'] = safe_codes(observation.get('findings'), '[a-z_]{1,40}:' + CODE)
    report['verified'] = all(bindings.values()) and report['stderr_empty']
    if not report['verified']:
        report['verdict_pt'] = 'RECIBO NÃO VERIFICADO: pelo menos um vínculo falhou; não se apoiar nele. Nunca repetir o resume.'
    elif transport_status == 'KNOWN_COMPLETE':
        report['verdict_pt'] = ('KNOWN_COMPLETE verificado: esquema, vínculos de hash e selo do recibo conferem. Evidência para revisão; '
                                'não é prontidão nem autoridade de instalação ou ativação.')
    else:
        report['verdict_pt'] = ('KNOWN_PARTIAL verificado: esquema, vínculos de hash e selo conferem. Parcial é resultado válido, não falha: '
                                'vale o que foi lido ou feito, e os códigos dizem o que faltou. A assinatura está gasta.')
    return report, out


# ---------------------------------------------------------------- a sealed copy of the HOSTOPS02 tier (K10 CONTRACT 6, step 1)
def sums_listing(raw, code):
    listed = {}
    try:
        lines = raw.decode('ascii').splitlines()
    except UnicodeDecodeError:
        raise Refused(code)
    for line in lines:
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_./-]+)', line)
        need(match and match.group(2) not in listed and '..' not in match.group(2).split('/') and not match.group(2).startswith('/'), code)
        listed[match.group(2)] = match.group(1)
    need(listed, code)
    return listed


def sealed_copy(out, sources):
    """"Bind and dispatch from a copy that holds only the files SHA256SUMS lists, SHA256SUMS itself and ../core": for every
    accepted seal of the HOSTOPS02 kind, the operation directory found under one of the source roots (a subdirectory whose
    SHA256SUMS is that seal) and the core it names (a subdirectory core/ whose CORE_SHA256SUMS is that seal's core), copied
    file by file, each file taken from the first source root that holds it WITH THE SEALED HASH. Nothing outside the
    lists is copied; a listed file that no source holds with its hash is a refusal. The copy is written with exclusive
    creations (0600 files, 0700 directories); the sources are only read."""
    need(os.geteuid() != 0, 'BIND_AS_ROOT')
    _, seals = binder_identity()
    out = Path(out)
    need(out.is_absolute() and not os.path.lexists(str(out)) and out.parent.is_dir(), 'OUT_EXISTS_OR_PARENT_MISSING')
    roots = [Path(item).resolve() for item in sources]
    need(roots and all(root.is_dir() for root in roots), 'SEALED_COPY_SOURCE_NOT_FOUND')
    kinds = [item for item in seals if 'core' in item]
    # one core per core directory name (rev 4: a seal may name its own, e.g. core-k6b; seals that name none share "core")
    cores = {}
    for item in kinds:
        cores.setdefault(core_directory_of(item), set()).add(item['core']['sha256sums_sha256'])
    need(kinds and all(len(found) == 1 for found in cores.values()), 'SEALED_COPY_SOURCE_NOT_FOUND')
    wanted = {name: ('CORE_SHA256SUMS', found.pop()) for name, found in sorted(cores.items())}
    for item in kinds:
        found = {name.name for root in roots for name in sorted(root.iterdir()) if name.is_dir() and not name.is_symlink()
                 and (name / 'SHA256SUMS').is_file() and sha((name / 'SHA256SUMS').read_bytes()) == item['sha256sums_sha256']}
        need(len(found) == 1 and not found & set(cores), 'SEALED_COPY_SOURCE_NOT_FOUND')
        wanted[found.pop()] = ('SHA256SUMS', item['sha256sums_sha256'])
    # A source root whose directory of one of these names carries another seal is a superseded working directory (the seal
    # was replaced after it): nothing is taken from it, not even a file of the same hash, and the copy is refused, so that
    # the copy can never be rebuilt from the bytes of a seal that is no longer accepted.
    for root in roots:
        for name, (sums_name, seal_sha) in wanted.items():
            sums = root / name / sums_name
            need(not sums.exists() or (sums.is_file() and not sums.is_symlink() and sha(sums.read_bytes()) == seal_sha), 'SEALED_COPY_SOURCE_HOLDS_A_SUPERSEDED_SEAL')
    plan = {}
    for name, (sums_name, seal_sha) in sorted(wanted.items()):
        sums_raw = None
        for root in roots:
            candidate = root / name / sums_name
            if candidate.is_file() and not candidate.is_symlink() and sha(candidate.read_bytes()) == seal_sha:
                sums_raw = candidate.read_bytes()
                break
        need(sums_raw is not None, 'SEALED_COPY_SOURCE_NOT_FOUND')
        files = {sums_name: (sums_raw, None)}
        for relative, digest in sorted(sums_listing(sums_raw, 'SEALED_COPY_SOURCE_NOT_FOUND').items()):
            for index, root in enumerate(roots):
                try:
                    raw = read_file(root / name / relative, 8 * 1024 * 1024, 'SEALED_COPY_FILE_NOT_FOUND')
                except Refused:
                    continue
                if sha(raw) == digest:
                    files[relative] = (raw, index)
                    break
            need(relative in files, 'SEALED_COPY_FILE_NOT_FOUND')
        plan[name] = (sums_name, seal_sha, files)
    make_directory(out)
    report = {}
    for name, (sums_name, seal_sha, files) in sorted(plan.items()):
        for relative, (raw, index) in sorted(files.items()):
            directory = out / name
            for part in PurePosixPath(relative).parts[:-1]:
                if not directory.is_dir():
                    make_directory(directory)
                directory = directory / part
            if not directory.is_dir():
                make_directory(directory)
            put(directory, PurePosixPath(relative).name, raw)
        report[name] = {'seal_file': sums_name, 'seal_sha256': seal_sha, 'files': len(files) - 1,
                        'files_taken_from_a_later_source': sorted(relative for relative, (raw, index) in files.items() if index)}
    return {'status': 'SEALED_COPY_WRITTEN', 'out': str(out), 'sources': [str(root) for root in roots], 'directories': report}


# ---------------------------------------------------------------- rehearsal transport reference
def rehearsal_reference(out):
    need(os.geteuid() != 0, 'BIND_AS_ROOT')
    out = Path(out)
    need(out.is_absolute() and out.name.startswith(REHEARSAL_PREFIX), 'REHEARSAL_DIRECTORY_NAME')
    need(not os.path.lexists(str(out)) and out.parent.is_dir(), 'OUT_EXISTS_OR_PARENT_MISSING')
    out = out.parent.resolve() / out.name
    make_directory(out)
    key = {'path': str(out / 'NOT_A_KEY'), 'sha256': put(out, 'NOT_A_KEY', REHEARSAL_KEY)}
    hosts = {'path': str(out / 'NOT_KNOWN_HOSTS'), 'sha256': put(out, 'NOT_KNOWN_HOSTS', REHEARSAL_HOSTS)}
    reference = {'schema': REHEARSAL_REFERENCE_SCHEMA, 'rehearsal': True, 'target': REHEARSAL_TARGET, 'remote_command': REMOTE_COMMAND,
                 'ssh_key': key, 'known_hosts': hosts,
                 'note': 'Fake transport for rehearsals. The target is in the reserved .invalid domain and the two files are not keys.'}
    digest = put(out, 'REHEARSAL_TRANSPORT_REFERENCE.json', pretty(reference))
    return {'status': 'REHEARSAL_REFERENCE_WRITTEN', 'reference': str(out / 'REHEARSAL_TRANSPORT_REFERENCE.json'), 'sha256': digest}



# Capture-only candidate, separate from the delivered Mac rev8.
CAPTURE_OWNER_RESPONSE_SHA256 = '9a3a6605176215b22be0613f7e0be1f8b0093ca147ca2bf63e0f16e7a962c814'
CAPTURE_OPS = ('policy_read', 'capture_launch', 'capture_result', 'capture_cleanup')
CAPTURE_OWNER_CONTEXT_NAME = 'CAPTURE.GITHUB.CONTEXT.json'
CAPTURE_OWNER_READBACK_NAME = 'OWNER_API.READBACK.json'


def capture_context_file(path, params):
    need(type(path) is str, 'CAPTURE_GITHUB_CONTEXT_REQUIRED')
    raw = read_file(Path(path), 4096, 'CAPTURE_GITHUB_CONTEXT_INVALID', private=True)
    capture_context_value(raw, params)
    return raw


def capture_context_value(raw, params):
    value = strict_json(raw, 'CAPTURE_GITHUB_CONTEXT_INVALID')
    need(type(value) is dict and set(value) == {'schema', 'session', 'run_id', 'run_attempt', 'nonce', 'k9_operation'},
         'CAPTURE_GITHUB_CONTEXT_INVALID')
    plan = params.get('plan')
    need(type(plan) is dict and plan.get('day') == value.get('session') == '2026-10-08'
         and plan.get('k9_operation') == value.get('k9_operation') and value.get('k9_operation') in CAPTURE_OPS
         and plan.get('slot') == 'PRIMARY' and params.get('signature_model') == 'PRE', 'CAPTURE_ONLY_SCOPE')
    need(value.get('schema') == 'CAPTURE_GITHUB_CONTEXT_V2'
         and type(value.get('run_id')) is str and re.fullmatch(r'[1-9][0-9]{5,19}', value['run_id'])
         and type(value.get('run_attempt')) is int and value['run_attempt'] == 1
         and type(value.get('nonce')) is str and re.fullmatch(r'[0-9a-f]{32}', value['nonce']),
         'CAPTURE_GITHUB_CONTEXT_INVALID')
    return value


def capture_request_fields(state):
    need(state['sheet']['mode'] == REAL, 'CAPTURE_REAL_ONLY')
    params = strict_json(state['files']['PARAMETERS.json'], 'CAPTURE_GITHUB_CONTEXT_INVALID')
    c = capture_context_value(state['files'].get(CAPTURE_OWNER_CONTEXT_NAME, b''), params)
    need(state['sheet'].get('signature_model') == 'PRE', 'CAPTURE_ONLY_SCOPE')
    return {'schema':'CAPTURE_OWNER_REQUEST_V2', 'verdict':'AWAITING_OWNER_SIGNATURE',
        'session':c['session'], 'run_id':c['run_id'], 'run_attempt':c['run_attempt'],
        'nonce':c['nonce'], 'sheet_sha256':sha(state['sheet_raw']),
        'request_sha256':state['sheet']['request_sha256'], 'k9_operation':c['k9_operation'],
        'not_before':state['sheet']['window']['gate_not_before'],
        'not_after':state['sheet']['window']['gate_not_after'],
        'owner_question_sha256':sha(state['files']['OWNER_QUESTION.txt']),
        'owner_deadline_utc':'2026-10-08T12:30:00Z', 'answer_schema':'CAPTURE_OWNER_ANSWER_V2',
        'response_channel':'AskUserQuestion via Fable', 'recorded_by':'FABLE'}


def capture_fable_question(state):
    # Private exact question. Public request names only hashes and context, never this text.
    return state['files']['OWNER_QUESTION.txt'] + b'\nCONTEXTO DESTA UNICA FOLHA:\n' + canonical(capture_request_fields(state))


def capture_question_body(state):
    fields = capture_request_fields(state)
    fields['asked_question_sha256'] = sha(capture_fable_question(state))
    return canonical(fields).decode()


def capture_signature_packet(state, raw):
    need(state['sheet']['mode'] == REAL, 'CAPTURE_REAL_ONLY')
    packet = strict_json(raw, 'CAPTURE_OWNER_API_PACKET_INVALID')
    need(type(packet) is dict and set(packet) == {'question_first','question_readback','first','readback','observed_at'},
         'CAPTURE_OWNER_API_PACKET_INVALID')
    q = packet['question_first']
    need(type(q) is dict and q == packet['question_readback'] and type(q.get('id')) is int and q['id'] > 0
         and q.get('issue_url') == 'https://api.github.com/repos/duduvcastro/c3po-chief-of-staff-intelligence/issues/429'
         and q.get('url') == 'https://api.github.com/repos/duduvcastro/c3po-chief-of-staff-intelligence/issues/comments/' + str(q['id'])
         and q.get('created_at') == q.get('updated_at') and q.get('body') == capture_question_body(state),
         'CAPTURE_OWNER_QUESTION_READBACK')
    helper_raw = read_file(Path(__file__).resolve().with_name('capture_owner_response.py'), 32768,
                           'CAPTURE_OWNER_HELPER_INVALID')
    need(sha(helper_raw) == CAPTURE_OWNER_RESPONSE_SHA256, 'CAPTURE_OWNER_HELPER_INVALID')
    namespace = {'__name__':'capture_owner_response_checked', '__builtins__':__builtins__}
    exec(compile(helper_raw, 'capture_owner_response_checked', 'exec'), namespace)
    c = strict_json(state['files'][CAPTURE_OWNER_CONTEXT_NAME], 'CAPTURE_GITHUB_CONTEXT_INVALID')
    context = {key:c[key] for key in ('session','run_id','run_attempt','nonce')}
    context.update(sheet_sha256=sha(state['sheet_raw']), question_created_at=q['created_at'],
        question_body_sha256=sha(q['body'].encode()), asked_question_sha256=sha(capture_fable_question(state)), prepared_at_utc=state['sheet']['prepared_at_utc'],
        not_before='2026-10-08T11:50:00Z', not_after='2026-10-08T12:30:00Z')
    try:
        record = namespace['validate_owner_response'](packet['first'],packet['readback'],context,packet['observed_at'])
    except ValueError as error:
        raise Refused(str(error))
    channel = REAL_CHANNEL + ' comment:' + str(record['comment_id']) + ' packet-sha256:' + sha(raw)
    return record, channel


def capture_owner_request(bound):
    state = open_bound(bound, signed=False)
    body = capture_question_body(state)
    return {'status':'OWNER_REQUEST_NOT_SIGNED','body':body,'body_sha256':sha(body.encode())}


# ---------------------------------------------------------------- command line
def main(argv=None):
    parser = argparse.ArgumentParser(description='Generic binder of the once families. Never dispatches.', allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    first = commands.add_parser('prepare', allow_abbrev=False)
    first.add_argument('--family', required=True, help='sealed family directory (SHA256SUMS at its root)')
    first.add_argument('--operation', required=True, help='operation name, e.g. GO_READONLY_W1PREFLIGHT_01')
    first.add_argument('--params', required=True, help='JSON file with the request parameters of that operation')
    first.add_argument('--reference', required=True, help='REAL: DISPATCH.BOUND.json of an executed bound set; REHEARSAL: the fake reference')
    first.add_argument('--out', required=True, help='output directory; must not exist')
    first.add_argument('--mode', required=True, choices=('real', 'rehearsal'))
    first.add_argument('--github-context', help='REAL capture-only immutable per-sheet job/session/nonce context')
    second = commands.add_parser('sign', allow_abbrev=False)
    second.add_argument('--bound', required=True)
    second.add_argument('--sheet-sha256', required=True, help='prepare_json_sha256 exactly as quoted to the owner; must equal sha256 of PREPARE.json')
    second.add_argument('--signed-at', required=True, help='UTC second of the owner answer, YYYY-MM-DDTHH:MM:SSZ')
    second.add_argument('--owner-answer', required=True, help="the owner's answer, verbatim; only the literal signature word is accepted")
    second.add_argument('--owner-api-proof', help='REAL capture-only exact API question/answer and readback packet')
    third = commands.add_parser('check', allow_abbrev=False)
    third.add_argument('--bound', required=True)
    third.add_argument('--family', help='the sealed family directory, to re-derive the scope sentence and compare the templates')
    third.add_argument('--gates', help='HOSTOPS02 only: the JSON file naming the evidence of the dispatch gates the sheet lists')
    third.add_argument('--step', choices=('prepare', 'resume'), default='prepare', help='HOSTOPS02 K10 only: resume evaluates the gate before the resume')
    fourth = commands.add_parser('publish-proof', allow_abbrev=False)
    fourth.add_argument('--bound', required=True)
    fourth.add_argument('--comment-id', required=True, help='numeric id of the channel comment that publishes the intent hash')
    fourth.add_argument('--created-at', required=True, help='created_at of that comment, YYYY-MM-DDTHH:MM:SSZ')
    fourth.add_argument('--name', default='PUBLICATION.PROOF.json')
    fifth = commands.add_parser('status', allow_abbrev=False)
    fifth.add_argument('--bound', required=True)
    fifth.add_argument('--show-findings', action='store_true', help='also print the finding codes of a collection receipt (they describe the host)')
    sixth = commands.add_parser('rehearsal-reference', allow_abbrev=False)
    sixth.add_argument('--out', required=True)
    seventh = commands.add_parser('sealed-copy', allow_abbrev=False)
    seventh.add_argument('--out', required=True, help='directory to create: the core and every accepted HOSTOPS02 operation directory, sealed files only')
    seventh.add_argument('--source', required=True, action='append', help='a root holding core/ and the operation directories; repeat for fallbacks')
    own = commands.add_parser('owner-request', allow_abbrev=False)
    own.add_argument('--bound', required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    del WROTE[:]
    code = 0
    try:
        if args.command == 'prepare':
            result = prepare(args.family, args.operation, args.params, args.reference, args.out, args.mode.upper(), args.github_context)
        elif args.command == 'sign':
            result = sign(args.bound, args.sheet_sha256, args.signed_at, args.owner_answer, args.owner_api_proof)
        elif args.command == 'owner-request':
            result = capture_owner_request(args.bound)
        elif args.command == 'check':
            result = check(args.bound, args.family, args.gates, args.step)
            code = 0 if result['verdict'] in ('VALID_WINDOW_OPEN', 'VALID_WINDOW_NOT_YET_OPEN', 'VALID_RESUME_ALLOWED_BY_THE_GATES') else 1
        elif args.command == 'publish-proof':
            result = publish_proof(args.bound, args.comment_id, args.created_at, args.name)
        elif args.command == 'status':
            result = status(args.bound, args.show_findings)
            code = 0 if result['verified'] else 1
        elif args.command == 'sealed-copy':
            result = sealed_copy(args.out, args.source)
        else:
            result = rehearsal_reference(args.out)
    except Refused as error:
        result, code = {'status': 'REFUSED', 'code': str(error)}, 2
    except BaseException as error:                 # never a traceback: an exception text can carry a path
        if isinstance(error, (SystemExit, KeyboardInterrupt)):
            raise
        result, code = {'status': 'REFUSED', 'code': 'UNEXPECTED_' + type(error).__name__}, 2
    if code == 2:
        result['created_by_this_run'] = [Path(item).name for item in WROTE]
        result['note'] = ('Nothing was written by this run.' if not WROTE else
                          'This run had already created the items listed: stop, change nothing, do not run it again on that directory, report.')
    sys.stdout.write(json.dumps(result, sort_keys=True, indent=1, ensure_ascii=False) + '\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
