"""Capacity-day documents for one session day and one dispatch window. Offline; hashes, dates, constants.

Run on the reviewer's machine, never on the host and never inside a container:

    python -I -B capacity_day_documents.py templates --order-file ORDER.json --output-directory OUT
    python -I -B capacity_day_documents.py static-config --static-inputs STATIC.json --day YYYY-MM-DD
                                               --window NAME --view-evidence-sha SHA --output-directory OUT
    python -I -B capacity_day_documents.py day --epoch-inputs EPOCH.json --session-inputs DAY.json
                                               --window NAME --output-directory OUT
                                               (--chain-directory DIR | --draft-without-chain)
    python -I -B capacity_day_documents.py verify --directory OUT [--chain-directory DIR]

The inputs, the files written, who signs them and the refusal codes are in README.documents.md.

It builds what the packaged capacity code reads at prepare-capacity-day and at the bar_manifest gate:
the day's contract (admission plan and the three consumer plans with their ten bindings), GO:admission,
GO:bar_manifest with its publication record, the day's TEMPLATE record, the veto view bytes of the
window, the window's capacity config and a dispatch envelope. Every plan is computed by the packaged
assembler; the records, the view, the contract and the GOs are passed through the packaged validators
before a byte is written. The capacity config is not loaded here (its roots exist only on the host)
and nothing in the repository reads the envelope.

The ordered list of instruments has no input here: the day's list is represented by the two hashes of
its published commitment, and the payload file that carries the list is assembled on the host. The
order and the policy are copied into the contract; beyond their known keys they may hold hashes,
clocks and constants only. Nothing here signs, publishes, dispatches or authorises anything; an output
file has no authority until its hash is pinned by a config whose own hash is named in an authorised
dispatch.

Standard output is one JSON line: a status, constant codes, counts, hashes and clocks.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

# The application root: the backend directory of the checkout this file belongs to. The packaged
# validators are imported from here and from nowhere else (the tool refuses another origin).
APP_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'backend')

EPOCH_INPUTS_SCHEMA = 'R2D2_CAPACITY_DAY_EPOCH_INPUTS_V1'
STATIC_INPUTS_SCHEMA = 'R2D2_CAPACITY_DAY_STATIC_INPUTS_V1'
SESSION_INPUTS_SCHEMA = 'R2D2_CAPACITY_DAY_SESSION_INPUTS_V1'
SUMMARY_SCHEMA = 'R2D2_CAPACITY_DAY_DOCUMENTS_V1'
TEMPLATES_SCHEMA = 'R2D2_CAPACITY_DAY_ACT_B_TEMPLATES_V1'
STATIC_SCHEMA = 'R2D2_CAPACITY_DAY_STATIC_CONFIG_V1'
REQUEST_SCHEMA = 'R2D2_CAPACITY_DAY_ONCE_REQUEST_V1'      # proposed; no code in this repository reads it
DISPATCH_GO_SCHEMA = 'R2D2_CAPACITY_DAY_ONCE_GO_V1'       # proposed; no code in this repository reads it
OPERATION = 'GO_CAPACITY_DAY_03'
CONFIG_SCHEMA = 'R2D2_CAPACITY_BOOTSTRAP_V3'
VETO_MODE = 'DISPATCH_AND_DERIVATION_ONLY'
RULE = 'OPEN_FIRST_THEN_EXISTING_CAUSAL_ORDER_V1_PROPOSED'   # the only rule the packaged contract check accepts
PHASES = ('admission', 'bar_manifest', 'quote_refresh', 'quote_capture')
CHAIN = ('CODEX', 'FABLE', 'DUDU', 'ACT_B', 'B_CODEX', 'B_FABLE', 'B_DUDU')
VIEW_MODES = ('PRE_DELIVERED', 'IN_WINDOW')                  # D4
# The writer's --require-go-mode: named in the dispatch, or left to the packaged rule.
REQUIRE_GO_MODES = ('DELEGATED_ACT_B', 'NOT_REQUIRED')
CUTOFF_BEFORE_OPEN = timedelta(minutes=10)                   # the writer refuses from here on
GO_NOTICE = timedelta(minutes=15)                            # packaged minimum for a delegated GO
GO_NOTICE_LIMIT = timedelta(days=4)                          # a publication older than this is a typing error
MAX_VIEW_SECONDS = 10                                        # packaged maximum life of a veto view
MAX_WAIT_SECONDS = 900                                       # the writer's cap on parking
WATCHDOG_MARGIN_SECONDS = 90
MAX_WINDOWS = 9
MAX_INPUT_BYTES = 1024 * 1024
EXIT_OK, EXIT_UNVERIFIED, EXIT_REFUSED = 0, 1, 3

# What a capacity config is made of. static-config reads these and nothing else; the epoch inputs are
# these plus what exists only later (the policy, Act B, D4, D11 and the dispatch facts).
STATIC_KEYS = {'schema', 'order', 'release_sha', 'package_sha', 'calendar_pin_receipt', 'chain_pins',
               'capacity_roots', 'phase_windows', 'd6_windows', 'view_valid_seconds', 'max_wait_seconds'}
EPOCH_KEYS = STATIC_KEYS | {'policy', 'policy_sha', 'act_b_sha256', 'd11', 'd4_view_mode', 'dispatch'}
RECEIPT_KEYS = ('status', 'epoch', 'calendar_version', 'calendar_pin_sha', 'package_sha', 'document_order_sha')
ORDER_KEYS = ('owner_sha', 'epoch', 'authorized_sessions', 'capacity')
POLICY_KEYS = ('schema', 'mode', 'epoch', 'capacity', 'order_sha', 'release_sha', 'package_sha', 'code_revision',
               'c8_receipt_sha', 'head_go_sha', 'valid_from', 'valid_until')     # read by the packaged policy check
SESSION_KEYS = {'schema', 'day', 'causal_scope', 'bar_manifest_published_at', 'view_evidence_sha'}
D11_KEYS = {'recertification_receipt_sha', 'wind_down_28_receipt_sha', 'input_receipts_sha', 'quote_refresh',
            'quote_capture'}
DISPATCH_KEYS = {'authority_sha256', 'payload_sha256', 'writer_sha256', 'writer_require_go_mode', 'image_id',
                 'build_sha', 'network', 'host_binding_sha256', 'pins_env', 'secret_env_path', 'docker_config',
                 'mounts', 'manifest_directory'}
CONFIG_KEYS = {'schema', 'r2d2_v2_capacity_veto_mode', 'identity', 'calendar_pin_sha', 'release_sha', 'package_sha',
               'roots', 'document_pins', 'veto_views', 'restore_revocation'}
DAY_ROLES = {'template': 'TEMPLATE', 'go_admission_record': 'GO:admission',
             'go_bar_manifest_record': 'GO:bar_manifest', 'publication_bar_manifest': 'PUBLICATION:bar_manifest'}

_CODE = re.compile(r'[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\Z')            # a refusal code always holds an underscore
_WALL = re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d\Z')        # New York wall clock, HH:MM:SS
_INSTANT = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00\Z')
_NAME = re.compile(r'[a-z][a-z0-9_]{0,31}\Z')
_FILE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._=-]{0,127}\Z')
_PATH = re.compile(r'/[A-Za-z0-9._=/-]+\Z')
_NETWORK = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\Z')
_IMAGE = re.compile(r'sha256:([0-9a-f]{64})\Z')
_REVISION = re.compile(r'[0-9a-f]{40}\Z')
_PRINTABLE = re.compile(r'[\x20-\x7e]*\Z')
_KEY = re.compile(r'[a-z][a-z0-9_]{0,63}\Z')
_STAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z')
_HEX = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
# Tripwire, not a proof: the instrument grammar of the capacity code. A string of this shape may only
# be one of the constants below or a date; anything else stops the run before a file is written.
_SYMBOL_SHAPED = re.compile(r'[A-Z0-9][A-Z0-9.-]{0,19}\Z')
_DATE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
CONSTANTS = frozenset(('GO', 'FABLE', 'DUDU', 'CODEX', 'TEMPLATE', 'PUBLICATION', 'VERIFIED', 'LIVE', 'ISSUED',
                       'INDIVIDUAL', 'BOUND', 'UNSIGNED'))


class Refused(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise Refused(code)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# What an empty or failed command leaves behind: the digest of no input and of the empty JSON values.
SENTINELS = frozenset(sha256(raw + end) for raw in (b'', b'[]', b'{}', b'null', b'""') for end in (b'', b'\n'))


_APP = None


def app():
    """The packaged code, imported once from APP_ROOT. No settings, no database, no network."""
    global _APP
    if _APP is None:
        root = os.path.realpath(APP_ROOT)
        if root not in [os.path.realpath(entry) for entry in sys.path if entry]:
            sys.path.insert(0, APP_ROOT)
        from app import r2d2_v2_epoch_assembler as assembler
        from app import r2d2_v2_document_format as fmt
        from app import r2d2_v2_store as store
        from app.r2d2_v2_calendar import NEW_YORK, ShadowCalendar
        from app.r2d2_v2_capacity_authority import calendar_pin, validate_contract
        from app.r2d2_v2_document_authority import DocumentAuthority
        from app.r2d2_v2_earnings_package import implementation_package_sha
        need(os.path.realpath(os.path.dirname(os.path.dirname(assembler.__file__))) == root, 'DOCUMENTS_APP_ROOT')
        _APP = SimpleNamespace(
            EPOCH=assembler.EPOCH, FIRST_SESSION=assembler.FIRST_SESSION, SESSIONS=tuple(assembler.SESSIONS),
            DOCUMENT_ORDER_SHA=assembler.DOCUMENT_ORDER_SHA, RUNTIME_ORDER_SHA=assembler.RUNTIME_ORDER_SHA,
            canonical=assembler.canonical, digest=assembler.digest, is_sha=assembler.is_sha, plan=assembler.plan,
            validate_go=assembler.validate_go, stamp=assembler.stamp, store_canonical=store.canonical,
            store_digest=store.digest, BEGIN=fmt.BEGIN, END=fmt.END, EVIDENCE_SCHEMA=fmt.SCHEMA,
            parse_document=fmt.parse_document, normalize_document=fmt.normalize_document,
            PinnedVetoReader=fmt.PinnedVetoReader, NEW_YORK=NEW_YORK, calendar=ShadowCalendar(),
            calendar_pin=calendar_pin, validate_contract=validate_contract, DocumentAuthority=DocumentAuthority,
            package_sha=implementation_package_sha())
    return _APP


# ---- inputs ------------------------------------------------------------------------------------

def strict_json(raw, code):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, code)
            result[key] = value
        return result

    def refuse(_value):
        raise Refused(code)
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=refuse, parse_float=refuse)
    except Refused:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Refused(code) from None


def read_file(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except OSError:
        raise Refused('DOCUMENTS_INPUT_FILE') from None
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_INPUT_BYTES, 'DOCUMENTS_INPUT_FILE')
        data = b''
        while len(data) <= MAX_INPUT_BYTES:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data += chunk
        need(len(data) <= MAX_INPUT_BYTES, 'DOCUMENTS_INPUT_FILE')
        return data
    finally:
        os.close(fd)


def plain(value, depth=0):
    """Printable ASCII strings, integers, booleans, null, lists and objects: one digest namespace."""
    need(depth < 32, 'DOCUMENTS_INPUT_DEPTH')
    if type(value) is str:
        need(_PRINTABLE.match(value) is not None, 'DOCUMENTS_INPUT_NOT_ASCII')
    elif type(value) is list:
        for item in value:
            plain(item, depth + 1)
    elif type(value) is dict:
        for key, item in value.items():
            plain(key, depth + 1)
            plain(item, depth + 1)
    else:
        need(value is None or type(value) in (int, bool), 'DOCUMENTS_INPUT_TYPE')


def load_inputs(path, keys, schema, label):
    raw = read_file(path)
    body = strict_json(raw, 'DOCUMENTS_INPUT_JSON')
    plain(body)
    need(type(body) is dict and set(body) == set(keys), 'DOCUMENTS_' + label + '_FIELDS')
    need(body['schema'] == schema, 'DOCUMENTS_' + label + '_SCHEMA')
    return body, sha256(raw)


def real_sha(a, value, label):
    """A SHA-256 as lowercase hex that is not what typing or an empty command leaves behind.

    Refused: fewer than five distinct digits, one block repeated (deadbeef..., 0123456789abcdef...) and
    the digests of no input and of the empty JSON values. No check can tell a wrong hash that looks
    real from the right one.
    """
    need(a.is_sha(value) and len(set(value)) >= 5 and value not in SENTINELS
         and not any(value == value[:size] * (64 // size) for size in (1, 2, 4, 8, 16, 32)),
         'DOCUMENTS_INPUT_' + label)
    return value


def distinct(values):
    """Hashes of things that can never be one thing: a value in two slots is a pasting error."""
    need(len(set(values)) == len(values), 'DOCUMENTS_INPUT_HASH_REUSED')


def open_value(a, value):
    if type(value) is dict:
        for key, item in value.items():
            need(_KEY.match(key) is not None, 'DOCUMENTS_FREE_FORM_KEY')
            open_value(a, item)
    else:
        need(value is None or type(value) is bool or (type(value) is str and (value == a.EPOCH or any(
            shape.match(value) is not None for shape in (_HEX, _STAMP, _DATE, _CODE)))), 'DOCUMENTS_FREE_FORM_VALUE')


def closed(a, value, known):
    """The order and the policy are copied into the contract. A key the packaged code does not read
    may hold a hash, a clock, a date, a constant with an underscore, a boolean, null or an object of
    those: no list, no number and no other text."""
    for key, item in value.items():
        if key not in known:
            need(_KEY.match(key) is not None, 'DOCUMENTS_FREE_FORM_KEY')
            open_value(a, item)


def fields(value, keys, label):
    need(type(value) is dict and set(value) == set(keys), 'DOCUMENTS_INPUT_' + label)
    return value


def clean_path(value, label):
    need(type(value) is str and _PATH.match(value) is not None and not value.endswith('/')
         and all(part not in ('', '.', '..') for part in value.split('/')[1:]), 'DOCUMENTS_INPUT_' + label)
    return value


def session_day(a, value):
    need(type(value) is str and value in a.SESSIONS, 'DOCUMENTS_DAY_NOT_AUTHORIZED')
    return value


def wall(a, day, value, label):
    need(type(value) is str and _WALL.match(value) is not None, 'DOCUMENTS_INPUT_' + label)
    naive = datetime.combine(date.fromisoformat(day), time.fromisoformat(value))
    instant = naive.replace(tzinfo=a.NEW_YORK).astimezone(timezone.utc)
    need(instant.astimezone(a.NEW_YORK).replace(tzinfo=None) == naive, 'DOCUMENTS_INPUT_' + label)
    return instant


def check_order(a, order):
    need(type(order) is dict and {'owner_sha', 'epoch', 'authorized_sessions', 'capacity'} <= set(order),
         'DOCUMENTS_INPUT_ORDER')
    real_sha(a, order['owner_sha'], 'ORDER_OWNER_SHA')
    need(order['epoch'] == a.EPOCH and order['authorized_sessions'] == list(a.SESSIONS)
         and type(order['capacity']) is int and order['capacity'] == 550, 'DOCUMENTS_ORDER_SCOPE')
    need(a.digest(order) == a.store_digest(order), 'DOCUMENTS_DIGEST_NAMESPACE')
    closed(a, order, ORDER_KEYS)
    return order


def calendar_receipt(a):
    """The line the calendar-pin script prints, as this interpreter computes it."""
    return {'status': 'CALENDAR_PIN', 'epoch': a.EPOCH, 'calendar_version': a.calendar.version,
            'calendar_pin_sha': a.calendar_pin(a.calendar, identity(a)), 'package_sha': a.package_sha,
            'document_order_sha': a.DOCUMENT_ORDER_SHA}


def check_config_inputs(a, e):
    """What a capacity config is made of. Returns the order and the hashes that name distinct things."""
    order = check_order(a, e['order'])
    for key in ('release_sha', 'package_sha'):
        real_sha(a, e[key], key.upper())
    # The plans are computed by the package of this checkout; another package would validate other bytes.
    need(e['package_sha'] == a.package_sha, 'DOCUMENTS_PACKAGE_MISMATCH')
    # The calendar pin binds the version string of the calendar library, which the package hash does not
    # cover. The whole line printed in the image is the input and every field of it must be the one this
    # interpreter computes. Where the line came from cannot be checked here.
    receipt, local = fields(e['calendar_pin_receipt'], RECEIPT_KEYS, 'CALENDAR_PIN_RECEIPT'), calendar_receipt(a)
    need(all(receipt[key] == local[key] for key in ('status', 'epoch', 'package_sha', 'document_order_sha')),
         'DOCUMENTS_CALENDAR_RECEIPT')
    need(receipt == local, 'DOCUMENTS_CALENDAR_PIN')
    pins = fields(e['chain_pins'], CHAIN, 'CHAIN_PINS')
    for label in CHAIN:
        fields(pins[label], ('file', 'sha256'), 'CHAIN_PINS')
        need(type(pins[label]['file']) is str and _FILE.match(pins[label]['file']) is not None,
             'DOCUMENTS_INPUT_CHAIN_PINS')
        real_sha(a, pins[label]['sha256'], 'CHAIN_PINS')
    need(len({pin['file'] for pin in pins.values()}) == len(CHAIN)
         and len({pin['sha256'] for pin in pins.values()}) == len(CHAIN), 'DOCUMENTS_INPUT_CHAIN_PINS')
    roots = fields(e['capacity_roots'], ('config', 'documents', 'payload', 'go'), 'CAPACITY_ROOTS')
    fields(roots['config'], ('path',), 'CAPACITY_ROOTS')
    for name in ('documents', 'payload', 'go'):
        fields(roots[name], ('path', 'identity'), 'CAPACITY_ROOTS')
        real_sha(a, roots[name]['identity'], 'CAPACITY_ROOT_IDENTITY')
    need(len({clean_path(root['path'], 'CAPACITY_ROOTS') for root in roots.values()}) == 4,
         'DOCUMENTS_INPUT_CAPACITY_ROOTS')
    fields(e['phase_windows'], ('admission', 'bar_manifest'), 'PHASE_WINDOWS')
    windows = e['d6_windows']
    need(type(windows) is list and 1 <= len(windows) <= MAX_WINDOWS, 'DOCUMENTS_INPUT_D6_WINDOWS')
    for window in windows:
        fields(window, ('name', 'start_not_before', 'view_opens_at'), 'D6_WINDOWS')
        need(type(window['name']) is str and _NAME.match(window['name']) is not None, 'DOCUMENTS_INPUT_D6_WINDOWS')
    need(len({window['name'] for window in windows}) == len(windows), 'DOCUMENTS_INPUT_D6_WINDOWS')
    need(type(e['view_valid_seconds']) is int and 1 <= e['view_valid_seconds'] <= MAX_VIEW_SECONDS,
         'DOCUMENTS_INPUT_VIEW_VALID_SECONDS')
    need(type(e['max_wait_seconds']) is int and 1 <= e['max_wait_seconds'] <= MAX_WAIT_SECONDS,
         'DOCUMENTS_INPUT_MAX_WAIT_SECONDS')
    # Not in this list: the order's digest and its owner_sha, because what the order object is has not
    # been defined yet (README.documents.md, "Open decisions").
    things = [e['release_sha'], e['package_sha'], local['calendar_pin_sha'], tool_sha256(),
              *sorted({a.DOCUMENT_ORDER_SHA, a.RUNTIME_ORDER_SHA}), *(pins[label]['sha256'] for label in CHAIN),
              *(roots[name]['identity'] for name in ('documents', 'payload', 'go'))]
    distinct(things)
    return order, things


def check_epoch_inputs(a, e):
    """The epoch inputs of a day. Returns the order, the policy and the hashes that name distinct things."""
    policy = e['policy']
    need(type(policy) is dict and policy.get('schema') == 'R2D2_V2_LIVE_POLICY_V1' and policy.get('mode') == 'LIVE'
         and 'symbols' not in policy, 'DOCUMENTS_POLICY_SCOPE')
    for key in ('policy_sha', 'release_sha', 'package_sha', 'act_b_sha256'):
        real_sha(a, e[key], key.upper())
    need(a.digest(policy) == e['policy_sha'], 'DOCUMENTS_POLICY_HASH')
    need(policy.get('release_sha') == e['release_sha'] and policy.get('package_sha') == e['package_sha'],
         'DOCUMENTS_POLICY_SCOPE')
    for key in ('c8_receipt_sha', 'head_go_sha'):
        real_sha(a, policy.get(key), 'POLICY_' + key.upper())
    closed(a, policy, POLICY_KEYS)
    order, things = check_config_inputs(a, e)
    need(e['chain_pins']['ACT_B']['sha256'] == e['act_b_sha256'], 'DOCUMENTS_ACT_B_HASH')
    d11 = fields(e['d11'], D11_KEYS, 'D11')
    receipts = [real_sha(a, d11[key], key.upper())
                for key in ('recertification_receipt_sha', 'wind_down_28_receipt_sha', 'input_receipts_sha')]
    need(e['d4_view_mode'] in VIEW_MODES, 'DOCUMENTS_INPUT_D4_VIEW_MODE')
    d = e['dispatch']
    check_dispatch(a, d, policy, e['capacity_roots'])
    things = things + [e['policy_sha'], d['authority_sha256'], d['payload_sha256'], d['writer_sha256'],
                       d['host_binding_sha256'], d['pins_env']['sha256'], d['image_id'][len('sha256:'):]]
    # D11 is open: a receipt slot may name what the policy calls its recertification receipts, and
    # nothing else that these inputs already name. Three slots are three documents.
    distinct(things + receipts)
    things = things + [policy['c8_receipt_sha'], policy['head_go_sha']]
    distinct(things)
    return order, policy, things


def check_dispatch(a, d, policy, roots):
    fields(d, DISPATCH_KEYS, 'DISPATCH')
    need(d['writer_require_go_mode'] in REQUIRE_GO_MODES, 'DOCUMENTS_INPUT_DISPATCH_WRITER_REQUIRE_GO_MODE')
    for key in ('authority_sha256', 'payload_sha256', 'writer_sha256', 'host_binding_sha256'):
        real_sha(a, d[key], 'DISPATCH_' + key.upper())
    image = _IMAGE.match(d['image_id']) if type(d['image_id']) is str else None
    need(image is not None, 'DOCUMENTS_INPUT_DISPATCH_IMAGE_ID')
    real_sha(a, image.group(1), 'DISPATCH_IMAGE_ID')
    need(type(d['build_sha']) is str and _REVISION.match(d['build_sha']) is not None
         and d['build_sha'] == policy.get('code_revision'), 'DOCUMENTS_BUILD_REVISION')
    need(type(d['network']) is str and _NETWORK.match(d['network']) is not None
         and d['network'] not in ('host', 'none'), 'DOCUMENTS_INPUT_DISPATCH_NETWORK')
    fields(d['pins_env'], ('path', 'sha256'), 'DISPATCH_PINS_ENV')
    real_sha(a, d['pins_env']['sha256'], 'DISPATCH_PINS_ENV')
    paths = [clean_path(d[key], 'DISPATCH_PATHS') for key in ('secret_env_path', 'docker_config', 'manifest_directory')]
    need(clean_path(d['pins_env']['path'], 'DISPATCH_PINS_ENV') != paths[0], 'DOCUMENTS_INPUT_DISPATCH_PATHS')
    mounts = d['mounts']
    need(type(mounts) is list and 1 <= len(mounts) <= 8, 'DOCUMENTS_INPUT_DISPATCH_MOUNTS')
    for mount in mounts:
        fields(mount, ('source', 'target', 'readonly'), 'DISPATCH_MOUNTS')
        clean_path(mount['source'], 'DISPATCH_MOUNTS')
        clean_path(mount['target'], 'DISPATCH_MOUNTS')
        need(type(mount['readonly']) is bool, 'DOCUMENTS_INPUT_DISPATCH_MOUNTS')
    need(len({mount['target'] for mount in mounts}) == len(mounts), 'DOCUMENTS_INPUT_DISPATCH_MOUNTS')
    # The manifest directory is the only writable bind; every capacity root is under a read-only one.
    need([mount['target'] for mount in mounts if not mount['readonly']] == [d['manifest_directory']],
         'DOCUMENTS_DISPATCH_WRITABLE_MOUNT')
    readonly = [mount['target'] for mount in mounts if mount['readonly']]
    need(all(any(root['path'] == target or root['path'].startswith(target + '/') for target in readonly)
             for root in roots.values()), 'DOCUMENTS_DISPATCH_CAPACITY_MOUNT')


def check_session_inputs(a, e, s, things):
    day = session_day(a, s['day'])
    scope = fields(s['causal_scope'], ('commitment_sha256', 'list_sha256'), 'CAUSAL_SCOPE')
    real_sha(a, scope['commitment_sha256'], 'CAUSAL_COMMITMENT_SHA256')
    if scope['list_sha256'] != a.store_digest([]):             # D12: the digest of an empty list is a real value
        real_sha(a, scope['list_sha256'], 'CAUSAL_LIST_SHA256')
    distinct(things + [scope['commitment_sha256'], scope['list_sha256']])
    need(type(s['bar_manifest_published_at']) is str and _INSTANT.match(s['bar_manifest_published_at']) is not None,
         'DOCUMENTS_INPUT_BAR_MANIFEST_PUBLISHED_AT')
    try:
        a.stamp(s['bar_manifest_published_at'])
    except ValueError:
        raise Refused('DOCUMENTS_INPUT_BAR_MANIFEST_PUBLISHED_AT') from None
    evidence = fields(s['view_evidence_sha'], [window['name'] for window in e['d6_windows']], 'VIEW_EVIDENCE_SHA')
    for value in evidence.values():
        real_sha(a, value, 'VIEW_EVIDENCE_SHA')
    return day


# ---- building ----------------------------------------------------------------------------------

def identity(a):
    return {'epoch': a.EPOCH, 'namespace': a.EPOCH, 'first_session': a.FIRST_SESSION,
            'authorized_sessions': list(a.SESSIONS), 'document_order_sha': a.DOCUMENT_ORDER_SHA,
            'runtime_order_sha': a.RUNTIME_ORDER_SHA}


def template(a, order, day):
    """The contract template of one session: the object whose digest Act B maps to that day."""
    return {'owner_sha': order['owner_sha'], 'epoch': a.EPOCH, 'day': day, 'phases': list(PHASES), 'rule': RULE}


def template_entry(a, order, day):
    """The day's entry of act_b.templates, verbatim; also the body of the day's TEMPLATE record."""
    return {'sha': a.digest(template(a, order, day)), 'epoch': a.EPOCH, 'first_session': a.FIRST_SESSION,
            'authorized_sessions': [day], 'phases': list(PHASES)}


def evidence(a, kind, body, title):
    payload = a.canonical({'schema': a.EVIDENCE_SCHEMA, 'kind': kind, 'state': 'ISSUED', 'body': body}).decode()
    return ('# ' + title + '\n' + a.BEGIN + '\n```json\n' + payload + '\n```\n' + a.END + '\n').encode()


def act_b_templates(a, order):
    entries = [template_entry(a, order, day) for day in a.SESSIONS]
    return {'schema': TEMPLATES_SCHEMA, 'epoch': a.EPOCH, 'first_session': a.FIRST_SESSION, 'cut_rule': RULE,
            'order_sha': a.digest(order), 'template_shas': {entry['authorized_sessions'][0]: entry['sha']
                                                             for entry in entries},
            'templates': entries, 'template_set_sha': a.digest(entries),
            'contract_templates': {day: template(a, order, day) for day in a.SESSIONS}}


def phase_window(a, day, phase, spec, label):
    fields(spec, ('not_before', 'not_after'), label)
    before, after = wall(a, day, spec['not_before'], label), wall(a, day, spec['not_after'], label)
    need(before < after, 'DOCUMENTS_INPUT_' + label)
    return {'epoch': a.EPOCH, 'day': day, 'phase': phase, 'not_before': before.isoformat(),
            'not_after': after.isoformat()}


def view_schedule(a, e, day, windows):
    """Every window of the day in UTC, checked against the two phase windows and the cutoff."""
    opening = a.calendar.details(date.fromisoformat(day))['open']
    cutoff = opening - CUTOFF_BEFORE_OPEN
    need(a.stamp(windows['admission']['not_before']) <= opening, 'DOCUMENTS_ADMISSION_WINDOW_LATE')
    schedule, previous = [], None
    for index, window in enumerate(e['d6_windows']):
        start = wall(a, day, window['start_not_before'], 'D6_WINDOWS')
        observed = wall(a, day, window['view_opens_at'], 'D6_WINDOWS')
        until = observed + timedelta(seconds=e['view_valid_seconds'])
        need(start < observed, 'DOCUMENTS_INPUT_D6_WINDOWS')
        need((observed - start).total_seconds() <= e['max_wait_seconds'], 'DOCUMENTS_WINDOW_WAIT')
        need(previous is None or previous <= start, 'DOCUMENTS_WINDOWS_OVERLAP')
        for phase in ('admission', 'bar_manifest'):
            need(a.stamp(windows[phase]['not_before']) <= observed
                 and until <= a.stamp(windows[phase]['not_after']), 'DOCUMENTS_VIEW_OUTSIDE_PHASE_WINDOW')
        need(until <= cutoff, 'DOCUMENTS_VIEW_AFTER_CUTOFF')
        schedule.append({'name': window['name'], 'index': index, 'start_not_before': start.isoformat(),
                         'view_opens_at': observed.isoformat(), 'view_valid_until': until.isoformat()})
        previous = until
    return schedule, cutoff


def view_document(a, order, day, entry, evidence_sha):
    body = {'status': 'VERIFIED', 'role': 'FABLE', 'epoch': a.EPOCH, 'day': day, 'order_sha': a.digest(order),
            'observed_at': entry['view_opens_at'], 'valid_until': entry['view_valid_until'], 'owner_veto': False,
            'revoked_shas': [], 'evidence_sha': evidence_sha}
    name = 'session=' + day + '.view-' + entry['name'] + '.md'
    return name, evidence(a, 'VETO_VIEW', body, 'VETO_VIEW ' + a.EPOCH + ' ' + day + ' ' + entry['name'])


def capacity_config(a, e, pins, views):
    ident = identity(a)
    return a.canonical({
        'schema': CONFIG_SCHEMA, 'r2d2_v2_capacity_veto_mode': VETO_MODE, 'identity': ident,
        'calendar_pin_sha': a.calendar_pin(a.calendar, ident), 'release_sha': e['release_sha'],
        'package_sha': e['package_sha'],
        'roots': {name: dict(e['capacity_roots'][name]) for name in ('documents', 'payload', 'go')},
        'document_pins': pins, 'veto_views': views, 'restore_revocation': None})


def layout(day, window, view_mode):
    """Role -> relative path. The names are a function of the day, the window and D4 alone."""
    stem = 'session=' + day
    return {'template': 'documents/' + stem + '.template.md',
            'go_admission_record': 'documents/' + stem + '.go-admission.md',
            'publication_bar_manifest': 'documents/' + stem + '.publication-bar_manifest.md',
            'go_bar_manifest_record': 'documents/' + stem + '.go-bar_manifest.md',
            'go_admission': 'go/' + stem + '.admission.json', 'go_bar_manifest': 'go/' + stem + '.bar_manifest.json',
            'contract': 'contract/' + stem + '.contract.json',
            'veto_view': ('documents/' if view_mode == 'PRE_DELIVERED' else 'emitter/') + stem + '.view-' + window
                         + '.md',
            'capacity_config': 'config/' + stem + '.' + window + '.capacity.json',
            'request': 'envelope/' + stem + '.' + window + '.request.json',
            'dispatch_go': 'envelope/' + stem + '.' + window + '.go.json'}


def request_document(a, *, day, window, index, count, view_mode, d, release_sha, package_sha, config_path,
                     config_sha, max_wait, start, observed, until, cutoff, documentary):
    """The dispatch REQUEST. Every argument is an ISO instant, a hash, a path or a constant."""
    argv = ['--day', day, '--manifest-directory', d['manifest_directory'], '--prepare-first',
            '--view-opens-at', observed, '--max-wait-seconds', str(max_wait)]
    if d['writer_require_go_mode'] != 'NOT_REQUIRED':
        argv += ['--require-go-mode', d['writer_require_go_mode']]
    return {'schema': REQUEST_SCHEMA, 'status': 'BOUND', 'operation': OPERATION, 'epoch': a.EPOCH, 'day': day,
            'window': window, 'window_index': index, 'window_count': count,
            'phases': ['admission', 'bar_manifest'], 'mode': 'PREPARE_AND_PUBLISH', 'view_mode': view_mode,
            'image_id': d['image_id'], 'build_sha': d['build_sha'], 'release_sha256': release_sha,
            'package_sha256': package_sha, 'capacity_config_file': config_path,
            'capacity_config_sha256': config_sha, 'network': d['network'], 'mounts': d['mounts'],
            'env_files': {'secret_path': d['secret_env_path'], 'pins': dict(d['pins_env'])},
            'inline_env': {'C3PO_R2D2_V2_SHADOW_ENABLED': 'true', 'C3PO_R2D2_V2_MASSIVE_BARS_ENABLED': 'true',
                           'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE': config_path,
                           'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA': config_sha},
            'docker_config': d['docker_config'], 'writer_sha256': d['writer_sha256'], 'writer_argv': argv,
            'transport_watchdog_seconds': max_wait + WATCHDOG_MARGIN_SECONDS,
            'not_before': start, 'latest_start': observed, 'not_after': until, 'view_opens_at': observed,
            'view_valid_until': until, 'cutoff_at': cutoff, 'documentary': documentary,
            'authority_sha256': d['authority_sha256'], 'host_binding_sha256': d['host_binding_sha256'],
            'executor_uid': 0}


def dispatch_go_document(a, request, request_sha, payload_sha):
    return {'schema': DISPATCH_GO_SCHEMA, 'status': 'UNSIGNED', 'action': 'GO', 'issuer': 'FABLE',
            'operation': OPERATION, 'epoch': a.EPOCH, 'day': request['day'], 'window': request['window'],
            'authority_sha256': request['authority_sha256'], 'request_sha256': request_sha,
            'payload_sha256': payload_sha, 'individual_go_for_admission': True,
            'admission_go_sha256': request['documentary']['admission_go_sha256'],
            'not_before': request['not_before'], 'not_after': request['not_after'],
            'host_binding_sha256': request['host_binding_sha256'], 'retry': False}


def build_day(a, e, s, window_name):
    """Relative path -> bytes for one day and one window, and the index that the summary carries."""
    order, policy, things = check_epoch_inputs(a, e)
    day = check_session_inputs(a, e, s, things)
    names = [window['name'] for window in e['d6_windows']]
    need(window_name in names, 'DOCUMENTS_WINDOW_UNKNOWN')
    tmpl, ident = template(a, order, day), identity(a)
    windows = {phase: phase_window(a, day, phase, e['phase_windows'][phase], 'PHASE_WINDOWS')
               for phase in ('admission', 'bar_manifest')}
    window_sha = {phase: a.digest(windows[phase]) for phase in windows}
    for phase in ('quote_refresh', 'quote_capture'):          # D11: a window, or the digest of one
        spec = e['d11'][phase]
        if type(spec) is dict and set(spec) == {'phase_window_sha'}:
            window_sha[phase] = real_sha(a, spec['phase_window_sha'], 'D11_PHASE_WINDOW_SHA')
            distinct(things + [window_sha[phase]])
        else:
            windows[phase] = phase_window(a, day, phase, spec, 'D11_PHASE_WINDOW')
            window_sha[phase] = a.digest(windows[phase])
    need(len(set(window_sha.values())) == len(PHASES), 'DOCUMENTS_PHASE_WINDOWS_NOT_DISTINCT')
    schedule, cutoff = view_schedule(a, e, day, windows)
    chosen = schedule[names.index(window_name)]
    published = s['bar_manifest_published_at']
    notice = a.stamp(windows['bar_manifest']['not_before']) - a.stamp(published)
    need(GO_NOTICE <= notice <= GO_NOTICE_LIMIT, 'DOCUMENTS_GO_NOTICE')

    causal_scope = {'epoch': a.EPOCH, 'session': day, 'commitment_sha256': s['causal_scope']['commitment_sha256'],
                    'list_sha256': s['causal_scope']['list_sha256']}
    inputs = {'owner_sha': order['owner_sha'], 'order': order, 'policy': policy, 'template': tmpl,
              'causal_scope': causal_scope}
    consumer = {'schema': 'CAPACITY_CONSUMER_INPUT_BINDING_V1', 'authority_inputs_sha': a.store_digest(inputs)}
    bindings = {'signed_epoch_order_sha': a.store_digest(order), 'release_sha': e['release_sha'],
                'policy_sha': e['policy_sha'], 'package_sha': e['package_sha'],
                'calendar_pin_sha': a.calendar_pin(a.calendar, ident),
                'recertification_receipt_sha': e['d11']['recertification_receipt_sha'],
                'wind_down_28_receipt_sha': e['d11']['wind_down_28_receipt_sha'],
                'template_sha': a.store_digest(tmpl), 'input_receipts_sha': e['d11']['input_receipts_sha']}
    plans = {phase: a.plan(ident, day=day, phase=phase, bindings={**bindings, 'phase_window_sha': window_sha[phase]},
                           policy=policy, calendar=a.calendar, consumer_binding=consumer) for phase in PHASES}
    need(all(plan['status'] == 'BOUND_FOR_REVIEW_ONLY' and not plan['missing_bindings'] for plan in plans.values()),
         'DOCUMENTS_PLAN_UNBOUND')
    contract = {**inputs, 'assembler_plan': plans['admission'],
                'consumer_plans': {phase: plans[phase] for phase in PHASES[1:]}}

    files, pins = {}, {label: dict(e['chain_pins'][label]) for label in CHAIN}
    roles = layout(day, window_name, e['d4_view_mode'])

    def put(role, raw, label=None):
        files[roles[role]] = raw
        if label is not None:
            pins[label] = {'file': roles[role].rsplit('/', 1)[1], 'sha256': sha256(raw)}

    def go(phase, mode, receipts):
        return {'decision': 'GO', 'epoch': a.EPOCH, 'first_session': a.FIRST_SESSION, 'day': day, 'phase': phase,
                'proposal_sha': plans[phase]['proposal_sha'], 'signed_order_sha': a.digest(order),
                'template_sha': a.digest(tmpl), 'mode': mode, 'not_before': windows[phase]['not_before'],
                'not_after': windows[phase]['not_after'], 'automatic_retry': False, 'authority_receipts': receipts}

    def record(go_body, **extra):
        return {'go_sha': a.digest(go_body), 'template_sha': go_body['template_sha'], 'decision': 'GO',
                'role': 'FABLE', 'epoch': a.EPOCH, 'first_session': a.FIRST_SESSION, 'day': day,
                'phase': go_body['phase'], **extra}

    title = ' ' + a.EPOCH + ' ' + day
    put('template', evidence(a, 'TEMPLATE', template_entry(a, order, day), 'TEMPLATE' + title), 'TEMPLATE')
    admission = go('admission', 'INDIVIDUAL', {'phase_window': windows['admission']})
    put('go_admission_record', evidence(a, 'GO', record(admission), 'GO admission' + title), 'GO:admission')
    publication = evidence(a, 'PUBLICATION', {
        'role': 'FABLE', 'template_sha': a.digest(tmpl), 'phase': 'bar_manifest', 'day': day,
        'published_at': published, 'epoch': a.EPOCH, 'first_session': a.FIRST_SESSION},
        'PUBLICATION bar_manifest' + title)
    put('publication_bar_manifest', publication, 'PUBLICATION:bar_manifest')
    bar = go('bar_manifest', 'DELEGATED_ACT_B', {
        'phase_window': windows['bar_manifest'], 'signed_act_b_sha': e['act_b_sha256'],
        'publication_receipt_sha': sha256(publication), 'published_at': published})
    put('go_bar_manifest_record', evidence(a, 'GO', record(bar, published_at=published), 'GO bar_manifest' + title),
        'GO:bar_manifest')
    put('go_admission', a.canonical({'go': admission}))
    put('go_bar_manifest', a.canonical({'go': bar}))
    put('contract', a.canonical(contract))
    view_name, view_raw = view_document(a, order, day, chosen, s['view_evidence_sha'][window_name])
    need(roles['veto_view'].rsplit('/', 1)[1] == view_name, 'DOCUMENTS_SELF_CHECK_ROLES')
    put('veto_view', view_raw)
    config_raw = capacity_config(a, e, pins, {day: {'file': view_name, 'sha256': sha256(view_raw)}})
    put('capacity_config', config_raw)

    d = e['dispatch']
    documentary = {
        'act_b_sha256': e['act_b_sha256'], 'template_record_sha256': pins['TEMPLATE']['sha256'],
        'template_sha256': a.digest(tmpl), 'admission_go_sha256': a.digest(admission),
        'admission_go_record_sha256': pins['GO:admission']['sha256'], 'bar_manifest_go_sha256': a.digest(bar),
        'bar_manifest_go_record_sha256': pins['GO:bar_manifest']['sha256'],
        'publication_sha256': pins['PUBLICATION:bar_manifest']['sha256'], 'veto_view_sha256': sha256(view_raw),
        'contract_sha256': sha256(files[roles['contract']]),
        'causal_commitment_sha256': causal_scope['commitment_sha256'], 'causal_list_sha256': causal_scope['list_sha256']}
    body = request_document(
        a, day=day, window=window_name, index=chosen['index'], count=len(schedule), view_mode=e['d4_view_mode'],
        d=d, release_sha=e['release_sha'], package_sha=e['package_sha'],
        config_path=e['capacity_roots']['config']['path'] + '/' + roles['capacity_config'].rsplit('/', 1)[1],
        config_sha=sha256(config_raw), max_wait=e['max_wait_seconds'], start=chosen['start_not_before'],
        observed=chosen['view_opens_at'], until=chosen['view_valid_until'], cutoff=cutoff.isoformat(),
        documentary=documentary)
    request = a.canonical(body)
    put('request', request)
    put('dispatch_go', a.canonical(dispatch_go_document(a, body, sha256(request), d['payload_sha256'])))
    index = {'day': day, 'window': window_name, 'window_index': chosen['index'], 'window_count': len(schedule),
             'view_mode': e['d4_view_mode'], 'roles': roles,
             'list': 'EMPTY' if causal_scope['list_sha256'] == a.store_digest([]) else 'NOT_EMPTY',
             'hashes': {**documentary, 'capacity_config_sha256': sha256(config_raw),
                        'request_sha256': sha256(request), 'dispatch_go_sha256': sha256(files[roles['dispatch_go']]),
                        'order_sha': a.digest(order), 'policy_sha': e['policy_sha'],
                        'proposal_sha': {phase: plans[phase]['proposal_sha'] for phase in PHASES},
                        'phase_window_sha': dict(window_sha)},
             'clocks': {'admission': {key: windows['admission'][key] for key in ('not_before', 'not_after')},
                        'bar_manifest': {key: windows['bar_manifest'][key] for key in ('not_before', 'not_after')},
                        'bar_manifest_published_at': published, 'start_not_before': chosen['start_not_before'],
                        'view_opens_at': chosen['view_opens_at'], 'view_valid_until': chosen['view_valid_until'],
                        'cutoff_at': cutoff.isoformat()}}
    return files, index


# ---- self-check: the packaged validators, before anything is written ----------------------------

class MemoryRoot:
    def __init__(self, files):
        self.files = files

    def read(self, name):
        return self.files[name]


def scan(value):
    """Refuse a string shaped like an instrument unless it is a known constant or a date."""
    if type(value) is str:
        need(_SYMBOL_SHAPED.match(value) is None or value in CONSTANTS or _DATE.match(value) is not None,
             'DOCUMENTS_SYMBOL_SHAPED_VALUE')
    elif type(value) is list:
        for item in value:
            scan(item)
    elif type(value) is dict:
        for key, item in value.items():
            scan(key)
            scan(item)


def self_check(a, files, index, chain=None):
    """The packaged validators and the tool's own comparisons on the bytes of one day and one window.

    Returns what was checked and the index rebuilt from the files, which must equal the given one.
    """
    try:
        return checks(a, files, index, chain)
    except (KeyError, TypeError, AttributeError, IndexError):
        raise Refused('DOCUMENTS_SELF_CHECK_SHAPE') from None


def checks(a, files, index, chain):
    need(type(index) is dict and type(index.get('roles')) is dict, 'DOCUMENTS_SELF_CHECK_ROLES')
    roles, day = index['roles'], session_day(a, index['day'])
    need(all(type(path) is str and path in files for path in roles.values()) and 'request' in roles,
         'DOCUMENTS_SELF_CHECK_ROLES')

    def name(role):
        return roles[role].rsplit('/', 1)[1]

    def json_file(role):
        value = strict_json(files[roles[role]], 'DOCUMENTS_SELF_CHECK_JSON')
        need(type(value) is dict and a.canonical(value) == a.store_canonical(value), 'DOCUMENTS_DIGEST_NAMESPACE')
        need(a.canonical(value) == files[roles[role]], 'DOCUMENTS_SELF_CHECK_CANONICAL')
        return value

    request = json_file('request')
    window, view_mode = request['window'], request['view_mode']
    need(type(window) is str and _NAME.match(window) is not None and view_mode in VIEW_MODES
         and roles == layout(day, window, view_mode), 'DOCUMENTS_SELF_CHECK_ROLES')
    config_raw = files[roles['capacity_config']]
    config = strict_json(config_raw, 'DOCUMENTS_SELF_CHECK_JSON')
    need(type(config) is dict and set(config) == CONFIG_KEYS and config['schema'] == CONFIG_SCHEMA
         and config['r2d2_v2_capacity_veto_mode'] == VETO_MODE and config['restore_revocation'] is None
         and a.canonical(config) == config_raw, 'DOCUMENTS_SELF_CHECK_CONFIG')
    need(config['identity'] == identity(a) and config['package_sha'] == a.package_sha
         and config['calendar_pin_sha'] == a.calendar_pin(a.calendar, config['identity']),
         'DOCUMENTS_SELF_CHECK_CONFIG')
    pins, memory, bodies = config['document_pins'], {}, {}
    need(set(pins) == set(CHAIN) | set(DAY_ROLES.values()) and all(
        type(pin) is dict and set(pin) == {'file', 'sha256'} and type(pin['file']) is str
        and _FILE.match(pin['file']) is not None and a.is_sha(pin['sha256']) for pin in pins.values()),
        'DOCUMENTS_SELF_CHECK_PINS')
    # The roots are host facts: their shape is all that can be checked here.
    need(a.is_sha(config['release_sha']) and set(config['roots']) == {'documents', 'payload', 'go'} and all(
        type(root) is dict and set(root) == {'path', 'identity'} and a.is_sha(root['identity'])
        and type(root['path']) is str and _PATH.match(root['path']) is not None
        for root in config['roots'].values()), 'DOCUMENTS_SELF_CHECK_CONFIG')
    for role, label in DAY_ROLES.items():
        raw = files[roles[role]]
        need(pins[label] == {'file': name(role), 'sha256': sha256(raw)}, 'DOCUMENTS_SELF_CHECK_PINS')
        bodies[label] = a.normalize_document(label, raw)
        scan(a.parse_document(raw))
        memory[name(role)] = raw
    view_raw = files[roles['veto_view']]
    need(config['veto_views'] == {day: {'file': name('veto_view'), 'sha256': sha256(view_raw)}},
         'DOCUMENTS_SELF_CHECK_PINS')
    memory[name('veto_view')] = view_raw
    view = a.parse_document(view_raw)
    scan(view)
    observed, until = a.stamp(view['body']['observed_at']), a.stamp(view['body']['valid_until'])

    contract = json_file('contract')
    gos = {phase: json_file('go_' + phase) for phase in ('admission', 'bar_manifest')}
    dispatch_go = json_file('dispatch_go')
    # Every string of these files is compared with the instrument grammar. The one exemption is the
    # REQUEST's own writer_argv, whose every entry is compared with its expected value below.
    for value in (config, contract, gos, dispatch_go, {key: item for key, item in request.items()
                                                       if key != 'writer_argv'}):
        scan(value)
    need(all(set(body) == {'go'} for body in gos.values()), 'DOCUMENTS_SELF_CHECK_GO_FILE')

    # Necessary conditions of the packaged verify_go that need no chain document: each GO file against
    # its pinned record, the day's TEMPLATE record and, for the delegated phase, its publication record.
    entry, here = bodies['TEMPLATE'], (a.EPOCH, a.FIRST_SESSION)
    need((entry['epoch'], entry['first_session']) == here and entry['authorized_sessions'] == [day]
         and entry['phases'] == list(PHASES) and entry['sha'] == a.digest(contract['template']),
         'DOCUMENTS_SELF_CHECK_RECORDS')
    for phase in ('admission', 'bar_manifest'):
        go, record = gos[phase]['go'], bodies['GO:' + phase]
        need(record['go_sha'] == a.digest(go) and record['template_sha'] == go['template_sha'] == entry['sha']
             and (record['epoch'], record['first_session'], record['day'], record['phase'], record['role'])
             == (*here, day, phase, 'FABLE') and (go['epoch'], go['first_session'], go['day'], go['phase'])
             == (*here, day, phase), 'DOCUMENTS_SELF_CHECK_RECORDS')
    receipts, publication = gos['bar_manifest']['go']['authority_receipts'], bodies['PUBLICATION:bar_manifest']
    need(gos['admission']['go']['mode'] == 'INDIVIDUAL' and gos['bar_manifest']['go']['mode'] == 'DELEGATED_ACT_B'
         and receipts['signed_act_b_sha'] == pins['ACT_B']['sha256']
         and receipts['publication_receipt_sha'] == pins['PUBLICATION:bar_manifest']['sha256']
         and publication['published_at'] == bodies['GO:bar_manifest'].get('published_at') == receipts['published_at']
         and (publication['epoch'], publication['first_session'], publication['day'], publication['phase'],
              publication['template_sha']) == (*here, day, 'bar_manifest', entry['sha'])
         and config['release_sha'] == contract['assembler_plan']['proposal']['bindings']['release_sha'],
         'DOCUMENTS_SELF_CHECK_RECORDS')

    root = MemoryRoot(memory)
    reader = a.PinnedVetoReader(root, file=name('veto_view'), sha256=sha256(view_raw), epoch=a.EPOCH, day=day,
                                order_sha=a.digest(contract['order']))
    reader(observed)                                           # accepted at the instant it opens
    reader(until - timedelta(microseconds=1))                  # and until just before it closes
    for instant in (observed - timedelta(microseconds=1), until):
        try:
            reader(instant)
        except ValueError as error:
            need(str(error) == 'VETO_STALE', 'DOCUMENTS_SELF_CHECK_VIEW')
        else:
            raise Refused('DOCUMENTS_SELF_CHECK_VIEW')

    # The packaged contract check, complete except for its last line: only the host holds the list
    # whose digest is list_sha256. With an empty stand-in it must fail there and nowhere earlier,
    # unless the day's list is itself empty (D12), in which case it must pass and the index says so.
    release = SimpleNamespace(epoch=a.EPOCH, first_session=date.fromisoformat(a.FIRST_SESSION),
                              receipt_sha=config['release_sha'])
    scope = contract['causal_scope']
    stand_in = {'epoch': a.EPOCH, 'session': day, 'symbols': [], 'commitment_sha256': scope['commitment_sha256'],
                'list_sha256': scope['list_sha256']}
    empty = scope['list_sha256'] == a.store_digest([])
    try:
        a.validate_contract(contract, release=release, day=day, causal=stand_in, calendar=a.calendar)
    except ValueError as error:
        if empty or str(error) != 'CAPACITY_CAUSAL_BINDING':
            raise
    else:
        need(empty, 'DOCUMENTS_SELF_CHECK_CONTRACT')
    # The package binds each plan's proposal and its hash and reads nothing else of a plan (schema,
    # execution_authorized, diff, and missing_bindings of a consumer plan). Here every stored plan
    # must be, in full, what the packaged assembler computes from its own bindings.
    plans = {'admission': contract['assembler_plan'], **contract['consumer_plans']}
    need(set(plans) == set(PHASES) and contract['assembler_plan']['proposal']['identity'] == identity(a),
         'DOCUMENTS_SELF_CHECK_PLANS')
    for phase, stored in plans.items():
        fresh = a.plan(identity(a), day=day, phase=phase, bindings=stored['proposal']['bindings'],
                       policy=contract['policy'], calendar=a.calendar,
                       consumer_binding=stored['proposal']['consumer_capacity_binding'])
        need(fresh == stored, 'DOCUMENTS_SELF_CHECK_PLANS')

    if chain is None:
        documentary = 'NOT_CHECKED'

        def verifier(_go, _proposal):
            return True
    else:
        for label in CHAIN:
            pin = pins[label]
            raw = chain(pin['file'])
            need(sha256(raw) == pin['sha256'], 'DOCUMENTS_CHAIN_HASH')
            memory[pin['file']] = raw
        authority = a.DocumentAuthority(root=root, pins=pins, revocation_reader=reader)
        authority.act_b(observed, epoch=a.EPOCH, first=a.FIRST_SESSION, day=day)
        authority.check_binding({'epoch': a.EPOCH, 'day': day, 'contract': contract}, observed)
        documentary = 'VERIFIED'

        def verifier(go, proposal):
            return authority.verify_go(go, proposal, observed)
    for phase in ('admission', 'bar_manifest'):
        a.validate_go(gos[phase]['go'], plans[phase], now=observed, authority_verifier=verifier)

    # The index, rebuilt from the files alone.
    cutoff = a.calendar.details(date.fromisoformat(day))['open'] - CUTOFF_BEFORE_OPEN
    hashes = {
        'act_b_sha256': pins['ACT_B']['sha256'], 'template_record_sha256': pins['TEMPLATE']['sha256'],
        'template_sha256': a.digest(contract['template']), 'admission_go_sha256': a.digest(gos['admission']['go']),
        'admission_go_record_sha256': pins['GO:admission']['sha256'],
        'bar_manifest_go_sha256': a.digest(gos['bar_manifest']['go']),
        'bar_manifest_go_record_sha256': pins['GO:bar_manifest']['sha256'],
        'publication_sha256': pins['PUBLICATION:bar_manifest']['sha256'], 'veto_view_sha256': sha256(view_raw),
        'contract_sha256': sha256(files[roles['contract']]), 'causal_commitment_sha256': scope['commitment_sha256'],
        'causal_list_sha256': scope['list_sha256']}

    # The envelope has no packaged validator. The REQUEST and the dispatch GO must be, field for field,
    # what this tool writes from the documents above and from the host facts the REQUEST itself states
    # (image, network, mounts, the two env files, the authority, payload, writer and host hashes, the
    # window's position and start), which are checked for shape: nothing here can check their truth.
    argv = request['writer_argv']
    need(type(argv) is list and len(argv) in (9, 11) and all(type(item) is str for item in argv)
         and argv[8].isdigit() and 1 <= int(argv[8]) <= MAX_WAIT_SECONDS, 'DOCUMENTS_SELF_CHECK_ENVELOPE')
    start, config_path = a.stamp(request['not_before']), request['capacity_config_file']
    need(type(request['window_index']) is int and type(request['window_count']) is int
         and 0 <= request['window_index'] < request['window_count'] <= MAX_WINDOWS
         and start < observed and (observed - start).total_seconds() <= int(argv[8]) and until <= cutoff
         and type(config_path) is str and config_path.endswith('/' + name('capacity_config')),
         'DOCUMENTS_SELF_CHECK_ENVELOPE')
    d = {'authority_sha256': request['authority_sha256'], 'payload_sha256': dispatch_go['payload_sha256'],
         'writer_sha256': request['writer_sha256'], 'image_id': request['image_id'], 'build_sha': request['build_sha'],
         'writer_require_go_mode': argv[10] if len(argv) == 11 else 'NOT_REQUIRED', 'network': request['network'],
         'host_binding_sha256': request['host_binding_sha256'], 'pins_env': request['env_files']['pins'],
         'secret_env_path': request['env_files']['secret_path'], 'docker_config': request['docker_config'],
         'mounts': request['mounts'], 'manifest_directory': argv[3]}
    try:
        check_dispatch(a, d, contract['policy'], {
            **config['roots'], 'config': {'path': config_path[:-len('/' + name('capacity_config'))]}})
    except Refused:
        raise Refused('DOCUMENTS_SELF_CHECK_ENVELOPE') from None
    need(d['writer_require_go_mode'] in ('NOT_REQUIRED', gos['bar_manifest']['go']['mode'])
         and request == request_document(
             a, day=day, window=window, index=request['window_index'], count=request['window_count'],
             view_mode=view_mode, d=d, release_sha=config['release_sha'], package_sha=config['package_sha'],
             config_path=config_path, config_sha=sha256(config_raw), max_wait=int(argv[8]),
             start=start.isoformat(), observed=view['body']['observed_at'], until=view['body']['valid_until'],
             cutoff=cutoff.isoformat(), documentary=hashes)
         and dispatch_go == dispatch_go_document(a, request, sha256(files[roles['request']]), d['payload_sha256']),
         'DOCUMENTS_SELF_CHECK_ENVELOPE')

    rebuilt = {
        'day': day, 'window': window, 'window_index': request['window_index'],
        'window_count': request['window_count'], 'view_mode': view_mode, 'roles': layout(day, window, view_mode),
        'list': 'EMPTY' if empty else 'NOT_EMPTY',
        'hashes': {**hashes, 'capacity_config_sha256': sha256(config_raw),
                   'request_sha256': sha256(files[roles['request']]),
                   'dispatch_go_sha256': sha256(files[roles['dispatch_go']]),
                   'order_sha': a.digest(contract['order']), 'policy_sha': a.digest(contract['policy']),
                   'proposal_sha': {phase: plans[phase]['proposal_sha'] for phase in PHASES},
                   'phase_window_sha': {phase: plans[phase]['proposal']['bindings']['phase_window_sha']
                                        for phase in PHASES}},
        'clocks': {**{phase: {key: gos[phase]['go'][key] for key in ('not_before', 'not_after')}
                      for phase in ('admission', 'bar_manifest')},
                   'bar_manifest_published_at': receipts['published_at'], 'start_not_before': request['not_before'],
                   'view_opens_at': view['body']['observed_at'], 'view_valid_until': view['body']['valid_until'],
                   'cutoff_at': cutoff.isoformat()}}
    need(all(index.get(key) == value for key, value in rebuilt.items()), 'DOCUMENTS_SELF_CHECK_INDEX')
    checked = {'documents': 'NORMALIZED', 'records': 'CONSISTENT', 'veto_view': 'ACCEPTED_INSIDE_REFUSED_OUTSIDE',
               'contract': 'VALIDATED_WITH_EMPTY_LIST' if empty else 'VALIDATED_UP_TO_LIST_HASH',
               'plans': 'EQUAL_TO_PACKAGED_ASSEMBLER', 'go_admission': 'EVIDENCE_CHECKED',
               'go_bar_manifest': 'EVIDENCE_CHECKED', 'documentary_authority': documentary,
               'capacity_config': 'NOT_LOADED_OFFLINE', 'envelope': 'NO_PACKAGED_VALIDATOR',
               'calendar_pin': 'EQUAL_TO_LOCAL_PROVENANCE_NOT_CHECKED'}
    return checked, rebuilt


# ---- output ------------------------------------------------------------------------------------

def sums(files):
    return ''.join(sha256(files[path]) + '  ' + path + '\n' for path in sorted(files)).encode()


def write_tree(directory, files):
    """Exclusive creation of a new private directory; SHA256SUMS is the last file written."""
    files = {**files, 'SHA256SUMS': sums(files)}
    try:
        os.mkdir(directory, 0o700)
    except FileExistsError:
        raise Refused('DOCUMENTS_OUTPUT_EXISTS') from None
    except FileNotFoundError:                                  # only the last component is created
        raise Refused('DOCUMENTS_OUTPUT_PARENT') from None
    for path in sorted(files, key=lambda item: (item == 'SHA256SUMS', item)):
        target = os.path.join(directory, *path.split('/'))
        os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            view = memoryview(files[path])
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
    return sha256(files['SHA256SUMS']), len(files)


def read_tree(directory):
    listed = {}
    for line in read_file(os.path.join(directory, 'SHA256SUMS')).decode('ascii', 'replace').splitlines():
        digest, separator, path = line.partition('  ')
        need(separator == '  ' and re.match(r'[0-9a-f]{64}\Z', digest) is not None and path not in listed
             and all(part not in ('', '.', '..') for part in path.split('/')), 'DOCUMENTS_SUMS_INVALID')
        listed[path] = digest
    present = set()
    for parent, _folders, names in os.walk(directory):
        present.update(os.path.relpath(os.path.join(parent, entry), directory).replace(os.sep, '/') for entry in names)
    need(present == set(listed) | {'SHA256SUMS'}, 'DOCUMENTS_SUMS_FILE_SET')
    files = {}
    for path in listed:
        try:                                                   # a regular file, never a symbolic link
            files[path] = read_file(os.path.join(directory, *path.split('/')))
        except Refused:
            raise Refused('DOCUMENTS_SUMS_FILE_SET') from None
    need(all(sha256(files[path]) == listed[path] for path in listed), 'DOCUMENTS_SUMS_MISMATCH')
    return files


def read_chain(directory):
    """A reader of the seven signed chain documents, by pinned file name; None when none was supplied."""
    if directory is None:
        return None

    def read(name):
        need(type(name) is str and _FILE.match(name) is not None, 'DOCUMENTS_CHAIN_FILE')
        try:
            return read_file(os.path.join(directory, name))
        except Refused:
            raise Refused('DOCUMENTS_CHAIN_FILE') from None
    return read


def tool_sha256():
    with open(os.path.abspath(__file__), 'rb') as stream:
        return sha256(stream.read())


def summary(a, schema, body):
    return a.canonical({'schema': schema, 'epoch': a.EPOCH, 'tool_sha256': tool_sha256(),
                        'package_sha256': a.package_sha, 'document_order_sha': a.DOCUMENT_ORDER_SHA, **body})


def day_summary(a, index, inputs, checked):
    """SUMMARY.json of a day: all of it but the two input hashes can be rebuilt from the other files."""
    return summary(a, SUMMARY_SCHEMA, {**index, 'inputs': inputs, 'calendar_pin_receipt': calendar_receipt(a),
                                       'self_check': checked})


def command_templates(args):
    a = app()
    raw = read_file(args.order_file)
    order = strict_json(raw, 'DOCUMENTS_INPUT_JSON')
    plain(order)
    body = act_b_templates(a, check_order(a, order))
    scan(body)
    files = {'ACT_B_TEMPLATES.json': a.canonical(body)}
    files['SUMMARY.json'] = summary(a, TEMPLATES_SCHEMA + '_SUMMARY', {
        'inputs': {'order_file_sha256': sha256(raw)}, 'order_sha': body['order_sha'],
        'template_set_sha': body['template_set_sha'], 'act_b_templates_sha256': sha256(files['ACT_B_TEMPLATES.json'])})
    listing, count = write_tree(args.output_directory, files)
    return {'status': 'WRITTEN', 'kind': 'ACT_B_TEMPLATES', 'files': count, 'sha256sums_sha256': listing,
            'template_set_sha': body['template_set_sha'], 'order_sha': body['order_sha']}


def command_day(args):
    a = app()
    e, e_sha = load_inputs(args.epoch_inputs, EPOCH_KEYS, EPOCH_INPUTS_SCHEMA, 'EPOCH')
    s, s_sha = load_inputs(args.session_inputs, SESSION_KEYS, SESSION_INPUTS_SCHEMA, 'SESSION')
    files, index = build_day(a, e, s, args.window)
    checked, rebuilt = self_check(a, files, index, read_chain(args.chain_directory))
    need(rebuilt == index, 'DOCUMENTS_SELF_CHECK_INDEX')
    files['SUMMARY.json'] = day_summary(a, rebuilt, {'epoch_inputs_sha256': e_sha, 'session_inputs_sha256': s_sha},
                                        checked)
    listing, count = write_tree(args.output_directory, files)
    return {'status': 'WRITTEN', 'kind': 'CAPACITY_DAY', 'day': index['day'], 'window': index['window'],
            'files': count, 'sha256sums_sha256': listing,
            'capacity_config_sha256': index['hashes']['capacity_config_sha256'], 'list': index['list'],
            'documentary_authority': checked['documentary_authority']}


def command_static_config(args):
    """The week's static config of a long-running reader: the chain, one TEMPLATE pin and one view pin."""
    a = app()
    e, e_sha = load_inputs(args.static_inputs, STATIC_KEYS, STATIC_INPUTS_SCHEMA, 'STATIC')
    order, _things = check_config_inputs(a, e)
    day = session_day(a, args.day)
    names = [window['name'] for window in e['d6_windows']]
    need(args.window in names, 'DOCUMENTS_WINDOW_UNKNOWN')
    windows = {phase: phase_window(a, day, phase, e['phase_windows'][phase], 'PHASE_WINDOWS')
               for phase in ('admission', 'bar_manifest')}
    schedule, _cutoff = view_schedule(a, e, day, windows)
    view_name, view_raw = view_document(a, order, day, schedule[names.index(args.window)],
                                        real_sha(a, args.view_evidence_sha, 'VIEW_EVIDENCE_SHA'))
    entry = evidence(a, 'TEMPLATE', template_entry(a, order, day), 'TEMPLATE ' + a.EPOCH + ' ' + day)
    pins = {label: dict(e['chain_pins'][label]) for label in CHAIN}
    pins['TEMPLATE'] = {'file': 'session=' + day + '.template.md', 'sha256': sha256(entry)}
    raw = capacity_config(a, e, pins, {day: {'file': view_name, 'sha256': sha256(view_raw)}})
    config = strict_json(raw, 'DOCUMENTS_SELF_CHECK_JSON')
    scan(config)
    need(a.canonical(config) == a.store_canonical(config) == raw, 'DOCUMENTS_DIGEST_NAMESPACE')
    files = {'config/week.static.capacity.json': raw}
    files['SUMMARY.json'] = summary(a, STATIC_SCHEMA, {
        'inputs': {'static_inputs_sha256': e_sha}, 'anchor_day': day, 'anchor_window': args.window,
        'capacity_config_file': e['capacity_roots']['config']['path'] + '/week.static.capacity.json',
        'capacity_config_sha256': sha256(raw), 'template_record_sha256': pins['TEMPLATE']['sha256'],
        'veto_view_sha256': sha256(view_raw), 'calendar_pin_receipt': calendar_receipt(a),
        'calendar_pin': 'EQUAL_TO_LOCAL_PROVENANCE_NOT_CHECKED'})
    listing, count = write_tree(args.output_directory, files)
    return {'status': 'WRITTEN', 'kind': 'STATIC_CONFIG', 'day': day, 'window': args.window, 'files': count,
            'sha256sums_sha256': listing, 'capacity_config_sha256': sha256(raw)}


def command_verify(args):
    a = app()
    files = read_tree(args.directory)
    need('SUMMARY.json' in files, 'DOCUMENTS_SUMS_FILE_SET')
    index = strict_json(files['SUMMARY.json'], 'DOCUMENTS_SELF_CHECK_JSON')
    kinds = {SUMMARY_SCHEMA: 'CAPACITY_DAY', STATIC_SCHEMA: 'STATIC_CONFIG', TEMPLATES_SCHEMA + '_SUMMARY': 'ACT_B_TEMPLATES'}
    need(type(index) is dict and index.get('schema') in kinds and index.get('epoch') == a.EPOCH
         and index.get('package_sha256') == a.package_sha
         and index.get('document_order_sha') == a.DOCUMENT_ORDER_SHA, 'DOCUMENTS_SUMMARY_SCOPE')
    need(index.get('tool_sha256') == tool_sha256(), 'DOCUMENTS_SUMMARY_TOOL')
    listing = sha256(read_file(os.path.join(args.directory, 'SHA256SUMS')))
    if index['schema'] != SUMMARY_SCHEMA:
        # Nothing but the listing can be re-checked without the inputs: say so in the line.
        return {'status': 'VERIFIED', 'kind': kinds[index['schema']], 'files': len(files) + 1,
                'sha256sums_sha256': listing, 'content': 'LISTING_ONLY'}
    inputs, stated = index.get('inputs'), index.get('self_check')
    need(type(index.get('roles')) is dict and type(inputs) is dict and type(stated) is dict
         and set(inputs) == {'epoch_inputs_sha256', 'session_inputs_sha256'}
         and all(a.is_sha(value) for value in inputs.values())
         and stated.get('documentary_authority') in ('VERIFIED', 'NOT_CHECKED'), 'DOCUMENTS_SUMMARY_SCOPE')
    need(all(type(path) is str for path in index['roles'].values())
         and set(index['roles'].values()) == set(files) - {'SUMMARY.json'}, 'DOCUMENTS_SUMS_FILE_SET')
    chain = read_chain(args.chain_directory)
    # A directory that says its GOs were verified over the signed chain is verified over it again.
    need(chain is not None or stated['documentary_authority'] == 'NOT_CHECKED', 'DOCUMENTS_CHAIN_REQUIRED')
    checked, rebuilt = self_check(a, files, index, chain)
    # SUMMARY.json is rebuilt from the other files and this tool. Only the hashes of the two input
    # files (not at hand here) and whether the chain was at hand at the build are taken from it.
    need(files['SUMMARY.json'] == day_summary(a, rebuilt, inputs, {
        **checked, 'documentary_authority': stated['documentary_authority']}), 'DOCUMENTS_SUMMARY_MISMATCH')
    return {'status': 'VERIFIED', 'kind': 'CAPACITY_DAY', 'day': rebuilt['day'], 'window': rebuilt['window'],
            'files': len(files) + 1, 'sha256sums_sha256': listing,
            'capacity_config_sha256': rebuilt['hashes']['capacity_config_sha256'], 'list': rebuilt['list'],
            'documentary_authority': checked['documentary_authority'], 'summary': 'REBUILT_EQUAL',
            'inputs': 'NOT_COMPARED'}


# ---- command line ------------------------------------------------------------------------------

class Parser(argparse.ArgumentParser):
    def error(self, message):                                  # never echo an argument back
        raise Refused('DOCUMENTS_ARGUMENTS_INVALID')


def parse(argv):
    """No help text and no abbreviated option: the output is one JSON line whatever the arguments."""
    parser = Parser(add_help=False, allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)

    def command(name, run):
        one = commands.add_parser(name, add_help=False, allow_abbrev=False)
        one.set_defaults(run=run)
        return one
    one = command('templates', command_templates)              # the five-day template map that Act B signs
    one.add_argument('--order-file', required=True)
    one.add_argument('--output-directory', required=True)
    one = command('static-config', command_static_config)      # the static capacity config of the reader
    one.add_argument('--static-inputs', required=True)
    one.add_argument('--day', required=True)
    one.add_argument('--window', required=True)
    one.add_argument('--view-evidence-sha', required=True)
    one.add_argument('--output-directory', required=True)
    one = command('day', command_day)                          # the documents of one session day and one window
    one.add_argument('--epoch-inputs', required=True)
    one.add_argument('--session-inputs', required=True)
    one.add_argument('--window', required=True)
    one.add_argument('--output-directory', required=True)
    chain = one.add_mutually_exclusive_group(required=True)    # a build without the signed chain is a draft
    chain.add_argument('--chain-directory')
    chain.add_argument('--draft-without-chain', action='store_true')
    one = command('verify', command_verify)                    # re-check a written directory
    one.add_argument('--directory', required=True)
    one.add_argument('--chain-directory')
    return parser.parse_args(argv)


def refusal(error):
    """Constant codes only: no path, no input value and no exception text reaches the output."""
    if (isinstance(error, ValueError) and len(error.args) == 1 and type(error.args[0]) is str
            and _CODE.match(error.args[0])):
        return {'status': 'REFUSED', 'code': error.args[0]}, EXIT_REFUSED
    if isinstance(error, OSError):
        return {'status': 'UNVERIFIED', 'code': 'DOCUMENTS_FILE_UNAVAILABLE'}, EXIT_UNVERIFIED
    return {'status': 'UNVERIFIED', 'code': 'DOCUMENTS_UNVERIFIED'}, EXIT_UNVERIFIED


def main(argv=None):
    try:
        args = parse(argv)
        result, code = args.run(args), EXIT_OK
    except Exception as error:
        result, code = refusal(error)
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
    sys.stdout.flush()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
