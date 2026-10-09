"""Pure candidate: authorized static template + freshly reverified veto -> config bytes.

No host/file/environment writes, installer, publisher, timer, GO issuer, real
authority verifier or runtime measurement adapter is provided. FIXTURE remains
nonoperational because its exact veto evidence is DRAFT.
"""
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Callable
import veto_emitter as veto
import consumer_codec
import hot_runtime as hot
import copy


SPEC_SCHEMA = 'R2D2_IMAGE_CAPACITY_CONFIG_FINALIZER_SPEC_V3'
CONFIG_SCHEMA = 'R2D2_CAPACITY_BOOTSTRAP_V3'
MODE = 'DISPATCH_AND_DERIVATION_ONLY'
EPOCH = 'R2D2-V2-SHADOW-2026-10-12'
FIRST = '2026-10-12'
SESSIONS = ['2026-10-%02d' % day for day in range(12, 17)]
EMITTER_SHA256 = 'b3ea98c4e35d749946f95b32b7dbf8e726779c70fa9f5e5001572a3f24045817'
MAX_BYTES = 1024 * 1024
SHA40 = re.compile(r'[0-9a-f]{40}\Z')
IDENTITY_FIELDS = {'epoch', 'namespace', 'first_session', 'authorized_sessions', 'document_order_sha', 'runtime_order_sha'}
CONFIG_FIELDS = {'schema', 'identity', 'calendar_pin_sha', 'release_sha', 'package_sha', 'roots', 'document_pins', 'veto_views', 'restore_revocation', 'r2d2_v2_capacity_veto_mode'}
DOCUMENT_LABELS = {'CODEX', 'FABLE', 'DUDU', 'ACT_B', 'B_CODEX', 'B_FABLE', 'B_DUDU', 'TEMPLATE'}


class Refused(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Refused(code)


def is_sha(value):
    return type(value) is str and veto.SHA.fullmatch(value) is not None


def filename(value):
    return type(value) is str and 0 < len(value) <= 255 and value not in {'.', '..'} and not any(c in value for c in '/\\\x00\r\n')


def absolute_path(value):
    return type(value) is str and 1 < len(value) <= 4096 and value.startswith('/') and not any(c in value for c in '\\\x00\r\n') and '..' not in value.split('/') and str(PurePosixPath(value)) == value


def parse(raw, code):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, code + '_BYTES')
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, code + '_DUPLICATE')
            out[key] = value
        return out
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
        need(type(value) is dict and veto.canonical(value) + b'\n' == raw, code + '_CANONICAL')
        return value
    except Refused:
        raise
    except Exception:
        raise Refused(code + '_INVALID') from None


def pin(raw, expected, code):
    need(type(raw) is bytes and is_sha(expected) and veto.digest(raw) == expected, code)


def parse_machine_order(raw):
    """Original machine-order ABI: canonical ASCII JSON without an appended LF.

    Raw bytes are pinned separately before this parser. The structured digest
    uses the same no-LF canonical serialization as DocumentAuthority.digest.
    Do not rewrite an original to satisfy this contract.
    """
    code = 'CONFIG_MACHINE_ORDER'
    need(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, code + '_BYTES')
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, code + '_DUPLICATE')
            out[key] = value
        return out
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode('ascii')
        need(type(value) is dict and encoded == raw, code + '_CANONICAL')
        return value
    except Refused:
        raise
    except Exception:
        raise Refused(code + '_INVALID') from None


def check_template(template):
    need(set(template) == CONFIG_FIELDS, 'CONFIG_TEMPLATE_FIELDS')
    need(template['schema'] == CONFIG_SCHEMA and template['r2d2_v2_capacity_veto_mode'] == MODE,
         'CONFIG_TEMPLATE_MODE')
    need(template['restore_revocation'] is None and template['veto_views'] == {}, 'CONFIG_TEMPLATE_DYNAMIC_FIELDS')
    identity = template['identity']
    need(type(identity) is dict and set(identity) == IDENTITY_FIELDS, 'CONFIG_IDENTITY_FIELDS')
    need(identity['epoch'] == identity['namespace'] == EPOCH and identity['first_session'] == FIRST
         and identity['authorized_sessions'] == SESSIONS, 'CONFIG_EPOCH04_IDENTITY')
    need(is_sha(identity['document_order_sha']) and identity['document_order_sha'] != '0f' + '0' * 62
         and is_sha(identity['runtime_order_sha']), 'CONFIG_UNSIGNED_ORDER')
    need(all(is_sha(template[key]) for key in ('calendar_pin_sha', 'release_sha', 'package_sha')), 'CONFIG_TEMPLATE_PIN')
    roots = template['roots']
    need(type(roots) is dict and set(roots) == {'documents', 'payload', 'go'}, 'CONFIG_ROOTS_FIELDS')
    for root in roots.values():
        need(type(root) is dict and set(root) == {'path', 'identity'} and absolute_path(root['path'])
             and is_sha(root['identity']), 'CONFIG_ROOT_PIN')
    pins = template['document_pins']
    need(type(pins) is dict and DOCUMENT_LABELS <= set(pins), 'CONFIG_DOCUMENT_LABELS')
    for label, item in pins.items():
        need(type(label) is str and veto.IDENTITY.fullmatch(label) is not None
             and type(item) is dict and set(item) == {'file', 'sha256'} and filename(item['file'])
             and is_sha(item['sha256']), 'CONFIG_DOCUMENT_PIN')
    need(len({p['file'] for p in pins.values()}) == len(pins), 'CONFIG_DOCUMENT_FILE_COLLISION')


def check_spec(spec, template, veto_spec):
    fields = {'schema', 'mode', 'template_sha256', 'veto_spec_sha256', 'emitter_implementation_sha256',
              'authority_sha256', 'verifier', 'build_sha', 'runtime_authority_sha256',
              'settings_file', 'veto_file', 'day', 'required_pins',
              'act_b_order_sha', 'act_b_original_sha256', 'machine_order_original_sha256'}
    need(set(spec) == fields and spec['schema'] == SPEC_SCHEMA and spec['mode'] in {'FIXTURE', 'REAL'}, 'CONFIG_SPEC_FIELDS')
    need(spec['day'] == FIRST and spec['mode'] == veto_spec['mode'], 'CONFIG_SPEC_SCOPE')
    need(spec['emitter_implementation_sha256'] == EMITTER_SHA256, 'CONFIG_EMITTER_PIN')
    need(is_sha(spec['authority_sha256']) and is_sha(spec['runtime_authority_sha256'])
         and type(spec['build_sha']) is str and SHA40.fullmatch(spec['build_sha']) is not None, 'CONFIG_RUNTIME_PIN')
    binding = spec['verifier']
    need(type(binding) is dict and set(binding) == {'identity', 'implementation_sha256'}
         and type(binding['identity']) is str and veto.IDENTITY.fullmatch(binding['identity']) is not None
         and is_sha(binding['implementation_sha256']), 'CONFIG_VERIFIER_PIN')
    need(absolute_path(spec['settings_file']) and filename(spec['veto_file']), 'CONFIG_PATH_METADATA')
    files = {p['file'] for p in template['document_pins'].values()}
    need(spec['veto_file'] not in files, 'CONFIG_VETO_FILE_COLLISION')
    veto_path = PurePosixPath(template['roots']['documents']['path']) / spec['veto_file']
    need(str(veto_path) != spec['settings_file'], 'CONFIG_OUTPUT_FILE_COLLISION')
    ctx, ident = veto_spec['context'], template['identity']
    need(all(is_sha(spec[k]) for k in ('act_b_order_sha','act_b_original_sha256','machine_order_original_sha256')),
         'CONFIG_ACT_B_ORDER_PIN')
    need(spec['act_b_original_sha256'] == template['document_pins']['ACT_B']['sha256'], 'CONFIG_ACT_B_PIN')
    need(ctx == {'epoch': ident['epoch'], 'first_session': ident['first_session'], 'day': spec['day'],
                 'order_sha': spec['act_b_order_sha']}, 'CONFIG_VETO_MACHINE_ORDER_CONTEXT')
    pins = spec['required_pins']
    minimum = {spec['template_sha256'], spec['veto_spec_sha256'], spec['emitter_implementation_sha256'],
               spec['authority_sha256'], spec['runtime_authority_sha256'], binding['implementation_sha256'],
               ident['document_order_sha'], ident['runtime_order_sha'], template['calendar_pin_sha'],
               template['release_sha'], template['package_sha'], spec['act_b_order_sha'],
               spec['act_b_original_sha256'],spec['machine_order_original_sha256']} | {p['sha256'] for p in template['document_pins'].values()}
    need(type(pins) is list and pins == sorted(set(pins)) and all(is_sha(value) for value in pins)
         and minimum <= set(pins)
         # A document cannot contain its own digest. The config authority checks
         # the veto-spec pin separately; all other static pins are in its view.
         and (set(pins) - {spec['veto_spec_sha256']}) <= set(veto_spec['required_pins']), 'CONFIG_REQUIRED_REVOCATION_SCOPE')


@dataclass(frozen=True)
class VerifiedConfigAuthority:
    """External verifier result; no implementation or independent proof supplied."""
    mode: str
    spec_sha256: str
    template_sha256: str
    authority_sha256: str
    build_sha: str
    runtime_authority_sha256: str
    act_b_order_sha: str
    act_b_original_sha256: str
    machine_order_original_sha256: str
    required_pins: tuple
    checked_at: str
    valid_from: str
    valid_until: str
    permitted_settings_file: str
    permitted_veto_file: str
    identity_verified: bool
    static_pins_verified: bool
    document_authority_verified: bool
    act_b_machine_order_verified: bool
    runtime_snapshot_verified: bool
    output_rule_authorized: bool
    revocation_checked: bool
    revoked_shas: tuple


@dataclass(frozen=True)
class ConfigVerifierBinding:
    identity: str
    implementation_sha256: str
    mode: str
    verify_current: Callable


@dataclass(frozen=True)
class FinalizedConfig:
    mode: str
    config_raw: bytes
    config_sha256: str
    settings: dict
    veto_raw: bytes
    veto_sha256: str
    veto_file: str
    observation_sha256: str
    authority_sha256: str
    spec_sha256: str
    operational_GO: bool = False
    installed: bool = False


def validate_authority(row, spec, spec_sha, now):
    need(type(row) is VerifiedConfigAuthority and row.mode == spec['mode'], 'CONFIG_AUTHORITY_RESULT')
    need(row.spec_sha256 == spec_sha and row.template_sha256 == spec['template_sha256']
         and row.authority_sha256 == spec['authority_sha256'] and row.build_sha == spec['build_sha']
         and row.runtime_authority_sha256 == spec['runtime_authority_sha256']
         and row.act_b_order_sha == spec['act_b_order_sha']
         and row.act_b_original_sha256 == spec['act_b_original_sha256']
         and row.machine_order_original_sha256 == spec['machine_order_original_sha256'], 'CONFIG_AUTHORITY_BINDING')
    need(row.required_pins == tuple(spec['required_pins']) and type(row.required_pins) is tuple, 'CONFIG_AUTHORITY_REVOCATION_SCOPE')
    need(row.permitted_settings_file == spec['settings_file'] and row.permitted_veto_file == spec['veto_file'], 'CONFIG_AUTHORITY_PATH')
    need(veto.instant(row.checked_at) == now, 'CONFIG_AUTHORITY_NOT_CURRENT')
    need(all(getattr(row, key) is True for key in ('identity_verified', 'static_pins_verified', 'document_authority_verified',
             'act_b_machine_order_verified','runtime_snapshot_verified', 'output_rule_authorized', 'revocation_checked')), 'CONFIG_AUTHORITY_UNVERIFIED')
    need(veto.instant(row.valid_from) <= now < veto.instant(row.valid_until), 'CONFIG_AUTHORITY_CLOCK')
    need(type(row.revoked_shas) is tuple and len(row.revoked_shas) == len(set(row.revoked_shas))
         and all(is_sha(value) for value in row.revoked_shas), 'CONFIG_AUTHORITY_REVOCATION_FIELDS')
    need(not set(row.revoked_shas).intersection(set(spec['required_pins']) | {spec_sha}), 'CONFIG_AUTHORITY_REVOKED')


def finalize_config(spec_raw, template_raw, config_authority_raw, *, spec_sha256,
                    emission, veto_spec_raw, veto_authority_raw, observation_raw,
                    act_b_raw, machine_order_raw, veto_verifier, config_verifier, clock,process_session=None):
    """Reverify originals now; copy only the known veto file/hash into a static template.

    External authority must authorize exact static inputs, output rule and paths,
    not an invented future output SHA. The independent caller pins this module,
    byte-exact veto_emitter dependency, both verifier implementations and spec.
    Returned settings are values only, never environment/host changes.
    """
    try:
        pin(spec_raw, spec_sha256, 'CONFIG_SPEC_HASH')
        spec = parse(spec_raw, 'CONFIG_SPEC')
        pin(template_raw, spec.get('template_sha256'), 'CONFIG_TEMPLATE_HASH')
        pin(veto_spec_raw, spec.get('veto_spec_sha256'), 'CONFIG_VETO_SPEC_HASH')
        pin(config_authority_raw, spec.get('authority_sha256'), 'CONFIG_AUTHORITY_HASH')
        template = parse(template_raw, 'CONFIG_TEMPLATE');check_template(template)
        veto_spec = veto.read_spec(veto_spec_raw);check_spec(spec, template, veto_spec)
        if spec['mode']=='REAL':
            hot.require_session(process_session,'config_finalizer')
            need(clock is veto.real_clock,'CONFIG_REAL_CLOCK_REQUIRED')
            verify_runtime_derivation(process_session,spec_raw,template_raw,veto_spec_raw,observation_raw)
        pin(act_b_raw,spec['act_b_original_sha256'],'CONFIG_ACT_B_ORIGINAL_HASH')
        pin(machine_order_raw,spec['machine_order_original_sha256'],'CONFIG_MACHINE_ORDER_ORIGINAL_HASH')
        try:act_b=consumer_codec.normalize_document('ACT_B',act_b_raw)
        except consumer_codec.ShadowIntegrityError:raise Refused('CONFIG_ACT_B_DOCUMENT_INVALID')from None
        machine_order=parse_machine_order(machine_order_raw)
        need(json.dumps(machine_order,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
             ==veto.canonical(machine_order),'CONFIG_MACHINE_ORDER_DIGEST_NAMESPACE')
        machine_sha=veto.digest(veto.canonical(machine_order))
        need(machine_sha==spec['act_b_order_sha']==act_b['order_sha'],'CONFIG_ACT_B_MACHINE_ORDER_HASH')
        ident=template['identity']
        need(act_b['epoch']==machine_order.get('epoch')==ident['epoch']
             and act_b['first_session']==ident['first_session']
             and act_b['authorized_sessions']==machine_order.get('authorized_sessions')==ident['authorized_sessions']
             and act_b['document_order_sha']==ident['document_order_sha']
             and type(machine_order.get('capacity'))is int and machine_order['capacity']==550
             and is_sha(machine_order.get('owner_sha')),'CONFIG_ACT_B_MACHINE_ORDER_SCOPE')
        need(type(emission) is veto.Emission and emission.mode == spec['mode']
             and emission.operational_GO is False and emission.spec_sha256 == spec['veto_spec_sha256'], 'CONFIG_EMISSION_MODE')
        need(type(config_verifier) is ConfigVerifierBinding and callable(config_verifier.verify_current), 'CONFIG_VERIFIER_UNBOUND')
        need(config_verifier.mode == spec['mode'] and config_verifier.identity == spec['verifier']['identity']
             and config_verifier.implementation_sha256 == spec['verifier']['implementation_sha256'], 'CONFIG_VERIFIER_BINDING')
        before = veto.now_utc(clock)
        try:
            current = config_verifier.verify_current(spec_raw, template_raw, config_authority_raw,
                                                     veto_spec_raw, observation_raw, emission.view_raw,
                                                     act_b_raw,machine_order_raw,before)
        except Exception:
            raise Refused('CONFIG_VERIFIER_REJECTED') from None
        validate_authority(current, spec, spec_sha256, before)
        after_authority = veto.now_utc(clock)
        need(after_authority >= before, 'CONFIG_CLOCK_ROLLBACK')
        need(veto.instant(current.valid_from) <= after_authority < veto.instant(current.valid_until), 'CONFIG_AUTHORITY_CLOCK')
        # Fresh verification is required even if an Emission dataclass was supplied.
        fresh = veto.emit_view(veto_spec_raw, observation_raw, veto_authority_raw, emission.observation_sha256,
                               spec_sha256=spec['veto_spec_sha256'], verifier=veto_verifier, clock=clock,
                               consumer_template_raw=template_raw,process_session=process_session)
        need(fresh == emission, 'CONFIG_EMISSION_ORIGINAL_MISMATCH')
        final_check_time = veto.now_utc(clock)
        need(final_check_time >= after_authority, 'CONFIG_CLOCK_ROLLBACK')
        try:
            current = config_verifier.verify_current(spec_raw, template_raw, config_authority_raw,
                                                     veto_spec_raw, observation_raw, fresh.view_raw,
                                                     act_b_raw,machine_order_raw,final_check_time)
        except Exception:
            raise Refused('CONFIG_VERIFIER_REJECTED') from None
        validate_authority(current, spec, spec_sha256, final_check_time)
        body = copy.deepcopy(template)
        body['veto_views'] = {spec['day']: {'file': spec['veto_file'], 'sha256': fresh.view_sha256}}
        raw = veto.canonical(body) + b'\n'
        verify_final_delta(template_raw,raw,day=spec['day'],veto_file=spec['veto_file'],veto_sha256=fresh.view_sha256)
        if spec['mode']=='REAL':hot.require_session(process_session,'config_finalizer')
        after = veto.now_utc(clock)
        need(after >= final_check_time, 'CONFIG_CLOCK_ROLLBACK')
        need(veto.instant(current.valid_from) <= after < veto.instant(current.valid_until), 'CONFIG_AUTHORITY_CLOCK')
        # Check freshness after the final config is serialized; never replace timestamps.
        doc = json.loads(fresh.view_raw.decode().split('```json\n', 1)[1].split('\n```', 1)[0])
        observed, until = map(veto.instant, (doc['body']['observed_at'], doc['body']['valid_until']))
        need(not set(doc['body']['revoked_shas']).intersection(set(spec['required_pins']) | {spec_sha256}), 'CONFIG_VETO_CRITICAL_REVOKED')
        need(veto.instant(current.valid_from) <= observed < until <= veto.instant(current.valid_until), 'CONFIG_AUTHORITY_VETO_INTERVAL')
        need(observed <= after < until and (after-observed).total_seconds() <= veto_spec['maximum_age_seconds'], 'CONFIG_VETO_STALE')
        settings = {'r2d2_v2_capacity_config_file': spec['settings_file'],
                    'r2d2_v2_capacity_config_sha': veto.digest(raw),
                    'r2d2_v2_capacity_veto_mode': MODE,
                    'r2d2_v2_shadow_release_sha': template['release_sha']}
        return FinalizedConfig(spec['mode'], raw, veto.digest(raw), settings, fresh.view_raw,
                               fresh.view_sha256, spec['veto_file'], fresh.observation_sha256,
                               veto.digest(config_authority_raw), spec_sha256)
    except (Refused, veto.Refused):
        raise
    except Exception:
        raise Refused('CONFIG_FINALIZER_INVALID') from None


def verify_runtime_derivation(session,spec_raw,template_raw,veto_spec_raw,observation_raw):
    """The signed registry selects bases; only actual T and actual hashes vary."""
    inputs=session.loaded.inputs
    need(inputs.get('template')==template_raw,'CONFIG_TEMPLATE_REGISTRY')
    base=parse(inputs.get('config_base'),'CONFIG_STATIC_BASE')
    vb=parse(inputs.get('veto_base'),'CONFIG_STATIC_VETO_BASE')
    observation=parse(observation_raw,'CONFIG_REAL_OBSERVATION')
    folder_spec=parse(inputs.get('folder_spec'),'CONFIG_FOLDER_SPEC')
    expected_veto=dict(vb,view_opens_at=observation['observed_at'],
        required_pins=sorted(set(vb['required_pins'])|{veto.digest(inputs.get('folder_spec'))}))
    need(veto.canonical(expected_veto)+b'\n'==veto_spec_raw,'CONFIG_DERIVED_VETO_RULE_CHANGED')
    expected=dict(base,veto_spec_sha256=veto.digest(veto_spec_raw),
        required_pins=sorted(set(base['required_pins'])|set(expected_veto['required_pins'])|{veto.digest(veto_spec_raw)}))
    need(veto.canonical(expected)+b'\n'==spec_raw,'CONFIG_DERIVED_STATIC_RULE_CHANGED')
    need(observation['mode']=='REAL' and observation['source_spec_sha256']==veto.digest(inputs.get('folder_spec'))
        and observation['context']==folder_spec['context'] and observation['root']==folder_spec['root']
        and session.image_at is not None and veto.instant(observation['observed_at'])==session.image_at
        and veto.instant(observation['valid_until'])==session.image_until,'CONFIG_OBSERVATION_PROCESS_BINDING')


def verify_final_delta(template_raw,final_raw,*,day,veto_file,veto_sha256):
    template=parse(template_raw,'CONFIG_DELTA_TEMPLATE');final=parse(final_raw,'CONFIG_DELTA_FINAL')
    check_template(template)
    expected=copy.deepcopy(template);expected['veto_views']={day:{'file':veto_file,'sha256':veto_sha256}}
    need(final.get('document_pins')==template['document_pins'] and final==expected,'CONFIG_UNAUTHORIZED_DELTA')
