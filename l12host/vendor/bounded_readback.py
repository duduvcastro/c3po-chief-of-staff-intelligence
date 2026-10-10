"""Bounded transport of a verified native image snapshot; no SQL or DB reader.

The pure producer verifies every retained record using exact selected native
source definitions, then projects explicit paths. The consumer MUST have an
independently approved source-bound verifier of origin, transaction consistency,
complete-chain verification and selection/absence. Selected hashes do not prove
membership in a linear hash chain. FIXTURE is never physical attestation.
"""
from __future__ import annotations
import ast
import base64
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import image_path_adapter as image
from verification_binding import Verifier

WIRE_LIMIT = 4 * 1024 * 1024
ORIGIN_LIMIT = 64 * 1024
PRODUCER_RECORD_LIMIT = 2 * 1024 * 1024
NATIVE_STATE_LIMIT = 8 * 1024 * 1024
PRODUCER_TOTAL_LIMIT = 128 * 1024 * 1024
PRODUCER_COUNT_LIMIT = 1_000_000
STORE_SHA = '9f9887c267af10c5494ec1a4dd2628b05f74f40dd2bae34e340bf81f00575254'
PHASES = {'BEFORE_READER_PROCESS_LAUNCH', 'BEFORE_FIRST_READER',
          'AFTER_FIRST_CYCLE', 'BEFORE_CAPTURE_LAUNCH', 'AFTER_CAPTURE'}
STATE_FIELDS = ('epoch', 'release_sha', 'daily_capacity', 'sessions')
SESSION_FIELDS = ('capacity_admission_blocked', 'capacity_binding', 'universe',
                  'universe_sha', 'causal_list')
RULE_SCHEMA = 'R2D2_IMAGE_BOUNDED_READBACK_RULE_CANDIDATE_V1'
READBACK_SCHEMA = 'R2D2_IMAGE_BOUNDED_READBACK_CANDIDATE_V1'


def need(value, code):
    image.need(value, code)


def _pin(value):
    return type(value) is str and bool(image.SHA.fullmatch(value)) and value != '0' * 64


def _json(raw, limit=WIRE_LIMIT):
    try:
        value = image.strict_json(raw, limit=limit)
        need(type(value) is dict and image.canonical(value) == raw, 'BOUNDED_JSON_CANONICAL')
        return value
    except image.Hold:
        raise
    except (ValueError, TypeError, RecursionError):
        raise image.Hold('BOUNDED_JSON_INVALID') from None


def _native_verifier():
    """Compile only pure definitions; never import/execute an app entrypoint."""
    raw = (Path(__file__).parent / 'sources' / 'r2d2_v2_store.py').read_bytes()
    need(image.sha(raw) == STORE_SHA, 'BOUNDED_NATIVE_SOURCE_PIN')
    names = {'ShadowIntegrityError', 'canonical', 'digest', 'validate_epoch',
             '_namespace', 'verify_journal'}
    parsed = ast.parse(raw)
    nodes = [node for node in parsed.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
             and node.name in names]
    need({node.name for node in nodes} == names, 'BOUNDED_NATIVE_SOURCE_SHAPE')
    namespace = {'json': json, 'sha256': hashlib.sha256, 're': re}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<pinned-pure-store>', 'exec'), namespace)
    return namespace


def _project_state(state, day):
    need(type(state) is dict and type(state.get('daily_capacity', {})) is dict
         and type(state.get('sessions', {})) is dict, 'BOUNDED_STATE_SHAPE')
    present = day in state.get('sessions', {})
    session = state.get('sessions', {}).get(day)
    need(not present or type(session) is dict, 'BOUNDED_SESSION_SHAPE')
    projected = {'epoch': state.get('epoch'), 'release_sha': state.get('release_sha'),
                 'daily_capacity': {}, 'sessions': {}}
    if day in state.get('daily_capacity', {}):
        projected['daily_capacity'][day] = state['daily_capacity'][day]
    if session is not None:
        projected['sessions'][day] = {key: session[key] for key in SESSION_FIELDS if key in session}
    # Preserve exact selected values, no caller aliases or proxy hashes.
    return json.loads(image.canonical(projected))


def build_readback(row, records, *, scope, phase, mode, observed_at,
                   request_sha256, bound_sha256, origin_statement_raw,
                   state_pg_text_bytes):
    """Pure producer for output from actual native read_with_journal.

    Reading PostgreSQL, acquiring originals and attesting origin are the approved
    external producer's duties. These input bytes alone do not attest a DB.
    Complete native chain verification remains a producer cost; no truncation,
    checkpoint reset or modification of retained state/history occurs here.
    """
    scope.validate()
    need(phase in PHASES and mode in {'FIXTURE', 'REAL'}, 'BOUNDED_SCOPE')
    need(_pin(request_sha256) and _pin(bound_sha256), 'BOUNDED_CONTEXT_PIN')
    need(type(origin_statement_raw) is bytes and 0 < len(origin_statement_raw) <= ORIGIN_LIMIT,
         'BOUNDED_ORIGIN_UNAVAILABLE')
    need(type(row) is dict and type(records) is list and len(records) <= PRODUCER_COUNT_LIMIT,
         'BOUNDED_NATIVE_SNAPSHOT_UNAVAILABLE')
    need(type(row.get('version')) is int and 0 <= row['version'] < 2**63
         and _pin(row.get('state_sha')) and _pin(row.get('manifest_sha')),
         'BOUNDED_NATIVE_ANCHOR_INVALID')
    # PostgreSQL jsonb::text length is a separate original measurement. It must
    # be read from the SAME consistent snapshot, not guessed from this Python
    # serializer. The additional canonical ceiling is conservative and bounds
    # the pure verifier workload; neither raises the image's native 8 MiB gate.
    need(type(state_pg_text_bytes) is int and 0 < state_pg_text_bytes <= NATIVE_STATE_LIMIT,
         'BOUNDED_NATIVE_STATE_SIZE')
    state_original_bytes = len(image.canonical(row.get('state')))
    need(0 < state_original_bytes <= NATIVE_STATE_LIMIT, 'BOUNDED_NATIVE_STATE_SIZE')
    hash_chain = hashlib.sha256(b'[')
    byte_count = 2
    selected = {'capacity-prepared:' + scope.day: None, 'universe:' + scope.day: None}
    for position, record in enumerate(records):
        need(type(record) is dict and set(record) == {'epoch','sequence','journal_key','recorded_at',
            'payload','previous_sha','record_sha'} and type(record['journal_key']) is str,
            'BOUNDED_NATIVE_RECORD_SHAPE')
        raw = image.canonical(record)
        need(len(raw) <= PRODUCER_RECORD_LIMIT, 'BOUNDED_NATIVE_RECORD_LIMIT')
        if position:
            hash_chain.update(b','); byte_count += 1
        hash_chain.update(raw); byte_count += len(raw)
        need(byte_count <= PRODUCER_TOTAL_LIMIT, 'BOUNDED_NATIVE_TOTAL_LIMIT')
        if record['journal_key'] in selected:
            selected[record['journal_key']] = json.loads(raw)
    hash_chain.update(b']')
    # Limits precede integral verification, which still checks every original
    # retained record. No selected-hash shortcut or new genesis is accepted.
    native = _native_verifier()
    try:
        native['_namespace'](scope.epoch, row['state'])
        native['verify_journal'](row, records)
    except (native['ShadowIntegrityError'], KeyError, TypeError, AttributeError):
        raise image.Hold('BOUNDED_NATIVE_CHAIN_INVALID') from None
    need(row['state'].get('release_sha') == scope.release_sha256,
         'BOUNDED_NATIVE_SCOPE_MISMATCH')
    projection = _project_state(row['state'], scope.day)
    output = {'schema': READBACK_SCHEMA, 'mode': mode, 'epoch': scope.epoch,
        'session': scope.day, 'scope_sha256': scope.scope_sha256, 'phase': phase,
        'observed_at': image.instant(observed_at).isoformat(),
        'request_sha256': request_sha256, 'bound_sha256': bound_sha256,
        'producer_source_sha256': image.sha(Path(__file__).read_bytes()),
        'native_store_source_sha256': STORE_SHA,
        'origin_statement_base64': base64.b64encode(origin_statement_raw).decode('ascii'),
        'origin_statement_sha256': image.sha(origin_statement_raw),
        'anchor': {'state_sha256': row['state_sha'], 'manifest_sha256': row['manifest_sha'],
                   'version': row['version'], 'journal_head_sha256': row['journal_head'],
                   'journal_count': len(records), 'journal_original_sha256': hash_chain.hexdigest(),
                   'journal_original_bytes': byte_count,
                   'state_pg_text_bytes': state_pg_text_bytes,
                   'state_original_canonical_bytes': state_original_bytes},
        'state_projection': projection, 'state_projection_sha256': image.digest(projection),
        'selected_records': selected}
    raw = image.canonical(output)
    need(len(raw) <= WIRE_LIMIT, 'BOUNDED_WIRE_LIMIT')
    return raw


@dataclass(frozen=True)
class DecodedReadback:
    row: dict
    journal: image.VerifiedBoundedJournal
    observed_at: datetime
    raw_sha256: str


class BoundedReadbackDecoder:
    def __init__(self, rule_raw, rule_sha256, rule_verifier, readback_verifier,
                 *, request_sha256, bound_sha256, read_authority_raw, mode='REAL'):
        need(type(rule_raw) is bytes and _pin(rule_sha256) and image.sha(rule_raw) == rule_sha256,
             'BOUNDED_RULE_PIN')
        need(mode in {'REAL', 'FIXTURE'} and _pin(request_sha256) and _pin(bound_sha256),
             'BOUNDED_CONTEXT_PIN')
        need(type(rule_verifier) is Verifier and type(readback_verifier) is Verifier,
             'BOUNDED_VERIFIER_REQUIRED')
        need(type(read_authority_raw) is bytes and 0 < len(read_authority_raw) <= image.LIMIT,
             'BOUNDED_READ_AUTHORITY_ORIGINAL_REQUIRED')
        self.rule_raw, self.rule_sha256 = rule_raw, rule_sha256
        self.original_rule_sha256 = rule_sha256
        self.rule_verifier, self.readback_verifier = rule_verifier, readback_verifier
        self.request_sha256, self.bound_sha256, self.mode = request_sha256, bound_sha256, mode
        self.context_seal = request_sha256, bound_sha256, mode
        self.read_authority_raw = read_authority_raw
        self.read_authority_sha256 = image.sha(read_authority_raw)
        self._rule()

    def _rule(self):
        rule = _json(self.rule_raw)
        need(image.sha(self.rule_raw) == self.rule_sha256 == self.original_rule_sha256
             and (self.request_sha256,self.bound_sha256,self.mode) == self.context_seal and set(rule) == {
            'schema','mode','epoch','session','native_store_source_sha256','producer_source_sha256',
            'state_fields','session_fields','selected_key_templates','wire_limit','verifiers'},
            'BOUNDED_RULE_SHAPE')
        need(rule['schema'] == RULE_SCHEMA and rule['mode'] == self.mode
             and rule['epoch'] == image.EPOCH and rule['session'] == image.DAY
             and rule['native_store_source_sha256'] == STORE_SHA
             and rule['producer_source_sha256'] == image.sha(Path(__file__).read_bytes())
             and rule['state_fields'] == list(STATE_FIELDS)
             and rule['session_fields'] == list(SESSION_FIELDS)
             and rule['selected_key_templates'] == ['capacity-prepared:D', 'universe:D']
             and type(rule['wire_limit']) is int and rule['wire_limit'] == WIRE_LIMIT,
             'BOUNDED_RULE_UNAPPROVED')
        bindings = rule['verifiers']
        need(type(bindings) is dict and set(bindings) == {'rule', 'readback'}, 'BOUNDED_RULE_VERIFIERS')
        for value in bindings.values():
            need(type(value) is dict and set(value) == {'identity', 'source_sha256'}
                 and type(value['identity']) is str and value['identity'] and _pin(value['source_sha256']),
                 'BOUNDED_RULE_VERIFIERS')
        return rule

    def authorize(self, scope, phase, *, now, plan, task):
        """Approve source/own REQUEST/BOUND before the supplier callback.

        This rule does not grant SQL authority; the enclosing finite core must
        have accepted the read operation's actual authority and runtime first.
        """
        rule = self._rule()
        need(image.sha(self.read_authority_raw) == self.read_authority_sha256
             == scope.finite_authority_sha256 == plan.get('authority_sha256'),
             'BOUNDED_READ_AUTHORITY_ORIGINAL_CHANGED')
        self.rule_verifier.validate(rule['verifiers']['rule'], self.mode)
        self.readback_verifier.validate(rule['verifiers']['readback'], self.mode)
        self.rule_verifier.invoke(rule['verifiers']['rule'], self.mode,
            self.rule_raw, self.rule_sha256, scope, phase, now, plan, task,
            self.request_sha256, self.bound_sha256,self.read_authority_raw)
        self.readback_verifier.validate(rule['verifiers']['readback'], self.mode)
        self._rule()

    def decode(self, raw, scope, phase, *, now, plan, task):
        self.authorize(scope,phase,now=now,plan=plan,task=task)
        rule = self._rule()
        value = _json(raw)
        need(set(value) == {'schema','mode','epoch','session','scope_sha256','phase','observed_at',
            'request_sha256','bound_sha256','producer_source_sha256','native_store_source_sha256',
            'origin_statement_base64','origin_statement_sha256','anchor','state_projection',
            'state_projection_sha256','selected_records'}, 'BOUNDED_READBACK_SHAPE')
        need(value['schema'] == READBACK_SCHEMA and value['mode'] == self.mode
             and value['epoch'] == scope.epoch and value['session'] == scope.day
             and value['scope_sha256'] == scope.scope_sha256 and value['phase'] == phase in PHASES
             and value['request_sha256'] == self.request_sha256
             and value['bound_sha256'] == self.bound_sha256
             and value['producer_source_sha256'] == rule['producer_source_sha256']
             and value['native_store_source_sha256'] == STORE_SHA, 'BOUNDED_READBACK_CONTEXT')
        observed, current = image.instant(value['observed_at']), image.instant(now)
        need(observed <= current and (current-observed).total_seconds() <= 5, 'BOUNDED_READBACK_STALE')
        try:
            need(type(value['origin_statement_base64']) is str, 'BOUNDED_ORIGIN_UNAVAILABLE')
            origin = base64.b64decode(value['origin_statement_base64'], validate=True)
        except (ValueError, TypeError):
            raise image.Hold('BOUNDED_ORIGIN_UNAVAILABLE') from None
        need(0 < len(origin) <= ORIGIN_LIMIT and base64.b64encode(origin).decode('ascii') == value['origin_statement_base64']
             and image.sha(origin) == value['origin_statement_sha256'], 'BOUNDED_ORIGIN_UNAVAILABLE')
        anchor, projection, selected = value['anchor'], value['state_projection'], value['selected_records']
        need(type(anchor) is dict and set(anchor) == {'state_sha256','manifest_sha256','version',
            'journal_head_sha256','journal_count','journal_original_sha256','journal_original_bytes',
            'state_pg_text_bytes','state_original_canonical_bytes'},
            'BOUNDED_ANCHOR_SHAPE')
        need(all(_pin(anchor[k]) for k in ('state_sha256','manifest_sha256','journal_original_sha256'))
             and type(anchor['version']) is int and 0 <= anchor['version'] < 2**63
             and type(anchor['journal_count']) is int and 0 <= anchor['journal_count'] <= PRODUCER_COUNT_LIMIT
             and type(anchor['journal_original_bytes']) is int and 2 <= anchor['journal_original_bytes'] <= PRODUCER_TOTAL_LIMIT,
             'BOUNDED_ANCHOR_INVALID')
        need(all(type(anchor[k]) is int and 0 < anchor[k] <= NATIVE_STATE_LIMIT
                 for k in ('state_pg_text_bytes','state_original_canonical_bytes')),
             'BOUNDED_NATIVE_STATE_SIZE')
        need((_pin(anchor['journal_head_sha256']) if anchor['journal_count'] else anchor['journal_head_sha256'] == ''),
             'BOUNDED_HEAD_INVALID')
        need(type(projection) is dict and set(projection) == set(STATE_FIELDS)
             and projection['epoch'] == scope.epoch and projection['release_sha'] == scope.release_sha256
             and type(projection['daily_capacity']) is dict and set(projection['daily_capacity']) <= {scope.day}
             and type(projection['sessions']) is dict and set(projection['sessions']) <= {scope.day}
             and image.digest(projection) == value['state_projection_sha256'], 'BOUNDED_PROJECTION_CHANGED')
        session = projection['sessions'].get(scope.day)
        need(session is None or (type(session) is dict and set(session) <= set(SESSION_FIELDS)),
             'BOUNDED_SESSION_SHAPE')
        need(type(selected) is dict and set(selected) == {'capacity-prepared:'+scope.day,'universe:'+scope.day},
             'BOUNDED_SELECTION_SHAPE')
        seen = set()
        for key, record in selected.items():
            if record is None:
                continue
            need(type(record) is dict and set(record) == {'epoch','sequence','journal_key','recorded_at',
                 'payload','previous_sha','record_sha'} and record['epoch'] == scope.epoch
                 and record['journal_key'] == key and type(record['sequence']) is int
                 and 1 <= record['sequence'] <= anchor['journal_count'] and record['sequence'] not in seen
                 and type(record['payload']) is dict and record['payload'].get('journal_key') == key
                 and (record['previous_sha'] == '' if record['sequence'] == 1 else _pin(record['previous_sha']))
                 and _pin(record['record_sha'])
                 and image.digest({k:v for k,v in record.items() if k != 'record_sha'}) == record['record_sha'],
                 'BOUNDED_SELECTED_RECORD_INVALID')
            need(record['sequence'] != anchor['journal_count'] or record['record_sha'] == anchor['journal_head_sha256'],
                 'BOUNDED_SELECTED_HEAD_MISMATCH')
            need(image.instant(record['recorded_at']) <= observed, 'BOUNDED_RECORD_FROM_FUTURE')
            seen.add(record['sequence'])
        # Mandatory origin proof of exact whole-chain snapshot, projection and
        # absence. Bytes/None are the protocol; a boolean is never attestation.
        self.readback_verifier.invoke(rule['verifiers']['readback'], self.mode,
            raw, origin, self.rule_raw, scope, phase, current, plan, task,
            self.request_sha256, self.bound_sha256,self.read_authority_raw)
        self._rule()
        # Parse again after callbacks to avoid mutable-data aliases.
        value = _json(raw); anchor = value['anchor']; projection = value['state_projection']
        row = {'state':projection, 'state_sha':anchor['state_sha256'],
               'manifest_sha':anchor['manifest_sha256'], 'version':anchor['version'],
               'journal_head':anchor['journal_head_sha256']}
        selected = {k:v for k,v in value['selected_records'].items() if v is not None}
        journal = image.VerifiedBoundedJournal(value['state_projection_sha256'], anchor['state_sha256'],
            anchor['manifest_sha256'],anchor['journal_head_sha256'], anchor['version'], anchor['journal_count'],scope.day,scope.epoch,
            selected,image.digest(selected),image._BOUNDED_PROOF_TOKEN)
        return DecodedReadback(row,journal,observed,image.sha(raw))
