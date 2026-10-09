"""Offline candidate: authenticated original -> the image's exact veto-view ABI.

No provider, installer, pin publisher, clock renewal, file/network/DB operation or
default verifier is supplied. REAL needs an independently pinned verifier and
actual source/authority originals. FIXTURE output is DRAFT, never ISSUED.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types
from typing import Callable
from zoneinfo import ZoneInfo


SPEC_SCHEMA = "R2D2_IMAGE_VETO_EMITTER_SPEC_V3"
DOCUMENT_SCHEMA = "R2D2_DOCUMENTARY_EVIDENCE_V1"
BEGIN = "<!-- R2D2-EVIDENCE-V1:BEGIN -->"
END = "<!-- R2D2-EVIDENCE-V1:END -->"
MAX_ORIGINAL_BYTES = 1024 * 1024
_LOADED_VERIFIERS = {}
SHA = re.compile(r"(?!0{64}\Z)[0-9a-f]{64}\Z")
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
NEW_YORK = ZoneInfo("America/New_York")


class Refused(ValueError):
    """Only a constant code is exposed, never source bytes or callback details."""


def need(ok, code):
    if not ok:
        raise Refused(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def instant(value):
    need(type(value) is str and len(value) <= 40, "VETO_TIME_FORMAT")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        need(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, "VETO_TIME_UTC")
        return parsed.astimezone(timezone.utc)
    except Refused:
        raise
    except (ValueError, TypeError, AttributeError):
        raise Refused("VETO_TIME_FORMAT") from None


def now_utc(clock):
    need(callable(clock), "VETO_CLOCK_UNBOUND")
    try:
        value = clock()
        need(type(value) is datetime and value.tzinfo is not None
             and value.utcoffset().total_seconds() == 0, "VETO_CLOCK_UTC")
        return value.astimezone(timezone.utc)
    except Refused:
        raise
    except Exception:
        raise Refused("VETO_CLOCK_UNAVAILABLE") from None


def real_clock():
    """The only supported clock in REAL, never a scheduler-supplied timestamp."""
    return datetime.now(timezone.utc)


def read_spec(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_ORIGINAL_BYTES, "VETO_SPEC_BYTES")
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "VETO_SPEC_DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        spec = json.loads(raw, object_pairs_hook=pairs)
        need(type(spec) is dict and set(spec) == {
            "schema", "mode", "context", "source", "verifier", "authority_sha256",
            "view_opens_at", "required_pins", "maximum_age_seconds",
            "consumer_config_template_sha256", "consumer_document_pins"}, "VETO_SPEC_FIELDS")
        need(canonical(spec) + b"\n" == raw, "VETO_SPEC_CANONICAL")
        need(spec["schema"] == SPEC_SCHEMA and spec["mode"] in {"REAL", "FIXTURE"}, "VETO_SPEC_SCHEMA")
        ctx = spec["context"]
        need(type(ctx) is dict and set(ctx) == {"epoch", "first_session", "day", "order_sha"}, "VETO_CONTEXT_FIELDS")
        need(type(ctx["epoch"]) is str and IDENTITY.fullmatch(ctx["epoch"]) is not None
             and ctx["epoch"] not in {"r2d2-v2-03", "R2D2-V2-SHADOW-2026-10-05"}, "VETO_EPOCH")
        for key in ("first_session", "day"):
            need(type(ctx[key]) is str and date.fromisoformat(ctx[key]).isoformat() == ctx[key], "VETO_DAY")
        need(ctx["first_session"] <= ctx["day"] and SHA.fullmatch(ctx["order_sha"] or "") is not None, "VETO_CONTEXT")
        for key in ("source", "verifier"):
            binding = spec[key]
            fields = {"identity", "implementation_sha256"} | ({"observation_format"} if key == "source" else set())
            need(type(binding) is dict and set(binding) == fields, "VETO_BINDING_FIELDS")
            need(type(binding["identity"]) is str and IDENTITY.fullmatch(binding["identity"]) is not None
                 and type(binding["implementation_sha256"]) is str
                 and SHA.fullmatch(binding["implementation_sha256"]) is not None, "VETO_BINDING_PIN")
            if key == "source":
                need(type(binding["observation_format"]) is str
                     and IDENTITY.fullmatch(binding["observation_format"]) is not None, "VETO_SOURCE_FORMAT")
        need(type(spec["authority_sha256"]) is str and SHA.fullmatch(spec["authority_sha256"]) is not None, "VETO_AUTHORITY_PIN")
        instant(spec["view_opens_at"])
        pins = spec["required_pins"]
        need(type(pins) is list and pins and pins == sorted(set(pins))
             and all(type(pin) is str and SHA.fullmatch(pin) is not None for pin in pins), "VETO_REQUIRED_PINS")
        minimum = {ctx["order_sha"], spec["authority_sha256"],
                   spec["source"]["implementation_sha256"], spec["verifier"]["implementation_sha256"]}
        need(minimum <= set(pins), "VETO_REQUIRED_SCOPE")
        documents = spec['consumer_document_pins']
        need(type(spec['consumer_config_template_sha256']) is str
             and SHA.fullmatch(spec['consumer_config_template_sha256']) is not None
             and type(documents) is list and documents and documents == sorted(set(documents))
             and all(type(pin) is str and SHA.fullmatch(pin) is not None for pin in documents)
             and set(documents) | {spec['consumer_config_template_sha256']} <= set(pins), 'VETO_CONSUMER_REVOCATION_SCOPE')
        need(type(spec["maximum_age_seconds"]) is int and 0 < spec["maximum_age_seconds"] <= 10, "VETO_MAX_AGE")
        return spec
    except Refused:
        raise
    except Exception:
        raise Refused("VETO_SPEC_INVALID") from None


@dataclass(frozen=True)
class VerifiedObservation:
    """Produced only by the pinned external verifier, never by this module."""
    mode: str
    source_identity: str
    source_implementation_sha256: str
    observation_format: str
    original_sha256: str
    authority_sha256: str
    authority_valid_from: str
    authority_valid_until: str
    authority_required_pins: tuple
    permitted_output_role: str
    authenticity_verified: bool
    authority_verified: bool
    revocation_checked: bool
    epoch: str
    first_session: str
    day: str
    order_sha: str
    view_opens_at: str
    status: str
    observed_at: str
    valid_until: str
    owner_veto: bool
    revoked_shas: tuple


@dataclass(frozen=True)
class VerifierBinding:
    identity: str
    implementation_sha256: str
    mode: str
    verify_original: Callable


@dataclass(frozen=True)
class LoadedVerifier:
    """Created by load_verifier from measured source bytes, never from a callable."""
    identity: str
    implementation_sha256: str
    mode: str
    verify_original: Callable
    path: str
    ancestors: tuple
    file_identity: tuple
    module: object


def _directory_identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))


def _file_identity(info):
    return _directory_identity(info) + (info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_program(path, ancestors, mode):
    need(type(path) is str and Path(path).is_absolute() and str(Path(path)) == path
         and '..' not in Path(path).parts and '\x00' not in path, 'VETO_VERIFIER_PATH')
    parent = str(Path(path).parent)
    expected = ['/'] + [str(Path(*Path(parent).parts[:i])) for i in range(2, len(Path(parent).parts)+1)]
    need(type(ancestors) is tuple and len(ancestors) == len(expected), 'VETO_VERIFIER_ROOT_PIN')
    held=[]; fd=None
    try:
        for i,(item,name) in enumerate(zip(ancestors, expected)):
            need(type(item) is tuple and len(item) == 2 and item[0] == name
                 and type(item[1]) is tuple and len(item[1]) == 5
                 and all(type(value) is int for value in item[1]), 'VETO_VERIFIER_ROOT_PIN')
            held.append(os.open('/' if i==0 else Path(name).name,
                os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW, **({} if i==0 else {'dir_fd':held[-1]})))
            info=os.fstat(held[-1]);named=os.lstat(name)
            need(stat.S_ISDIR(named.st_mode) and not stat.S_ISLNK(named.st_mode)
                 and _directory_identity(info)==_directory_identity(named)==item[1], 'VETO_VERIFIER_ROOT_CHANGED')
        parent_info=os.fstat(held[-1])
        need(mode=='FIXTURE' or (parent_info.st_uid==0 and not(stat.S_IMODE(parent_info.st_mode)&0o022)),
             'VETO_VERIFIER_ROOT_POLICY')
        fd = os.open(Path(path).name, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=held[-1])
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and 0 < before.st_size <= MAX_ORIGINAL_BYTES and not (stat.S_IMODE(before.st_mode) & 0o022)
             and (mode == 'FIXTURE' or before.st_uid == 0), 'VETO_VERIFIER_FILE_POLICY')
        raw = os.read(fd, MAX_ORIGINAL_BYTES+1)
        after = os.fstat(fd); named = os.stat(Path(path).name,dir_fd=held[-1],follow_symlinks=False)
        need(_file_identity(before) == _file_identity(after) == _file_identity(named)
             and len(raw) == before.st_size, 'VETO_VERIFIER_FILE_CHANGED')
        for directory,(name,pin) in zip(held,ancestors):
            named=os.lstat(name)
            need(stat.S_ISDIR(named.st_mode) and not stat.S_ISLNK(named.st_mode)
                 and _directory_identity(os.fstat(directory))==_directory_identity(named)==pin,
                 'VETO_VERIFIER_ROOT_CHANGED')
        return raw, _file_identity(before)
    except OSError:
        raise Refused('VETO_VERIFIER_FILE_UNAVAILABLE') from None
    finally:
        if fd is not None:os.close(fd)
        for directory in reversed(held):os.close(directory)


def load_verifier(path, *, ancestors, identity, implementation_sha256, mode, context=None):
    """Compile the exact FD-read pin, not a path loader that can reopen changed bytes.

    The authority must independently approve this program AND its dependency/
    context bindings. A pin cannot attest arbitrary program semantics by itself.
    This loading call belongs inside the externally bounded, approved process.
    """
    need(mode in {'REAL','FIXTURE'} and type(identity) is str and IDENTITY.fullmatch(identity)
         and type(implementation_sha256) is str and SHA.fullmatch(implementation_sha256), 'VETO_VERIFIER_LOAD_BINDING')
    raw, info = _read_program(path, ancestors, mode)
    need(digest(raw) == implementation_sha256, 'VETO_VERIFIER_IMPLEMENTATION_HASH')
    module = types.ModuleType('_pinned_veto_verifier'); module.__file__ = path
    try:
        exec(compile(raw, path, 'exec'), module.__dict__)
        need(module.VERIFIER_MODE == mode, 'VETO_VERIFIER_LOADED_MODE')
        if context is not None:
            need(type(module.bind_context) is types.FunctionType
                 and module.bind_context.__globals__ is module.__dict__, 'VETO_VERIFIER_FACTORY')
            accepted = module.bind_context(context)
            need(accepted is None, 'VETO_VERIFIER_FACTORY_RESULT')
        function = module.verify_original
        need(type(function) is types.FunctionType and function.__globals__ is module.__dict__, 'VETO_VERIFIER_ENTRYPOINT')
    except Refused:
        raise
    except Exception:
        raise Refused('VETO_VERIFIER_LOAD_REJECTED') from None
    raw2, info2 = _read_program(path, ancestors, mode)
    need(raw2 == raw and info2 == info, 'VETO_VERIFIER_FILE_CHANGED')
    loaded=LoadedVerifier(identity, implementation_sha256, module.VERIFIER_MODE, function, path, ancestors, info, module)
    _LOADED_VERIFIERS[id(loaded)]=(loaded,module,function)
    return loaded


def _check_loaded(verifier):
    registered=_LOADED_VERIFIERS.get(id(verifier))
    need(type(verifier) is LoadedVerifier and type(verifier.module) is types.ModuleType
         and registered is not None and registered[0] is verifier and registered[1] is verifier.module
         and registered[2] is verifier.verify_original
         and type(verifier.verify_original) is types.FunctionType
         and verifier.verify_original is verifier.module.verify_original
         and verifier.verify_original.__globals__ is verifier.module.__dict__, 'VETO_REAL_VERIFIER_NOT_LOADED')
    raw, info = _read_program(verifier.path, verifier.ancestors, verifier.mode)
    need(digest(raw) == verifier.implementation_sha256 and info == verifier.file_identity
         and verifier.module.VERIFIER_MODE == verifier.mode, 'VETO_VERIFIER_IMPLEMENTATION_CHANGED')


def _consumer_template(raw, spec):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_ORIGINAL_BYTES
         and digest(raw) == spec['consumer_config_template_sha256'], 'VETO_CONSUMER_TEMPLATE_HASH')
    def pairs(items):
        out={}
        for key, value in items:need(key not in out,'VETO_CONSUMER_DUPLICATE');out[key]=value
        return out
    try:
        body=json.loads(raw,object_pairs_hook=pairs)
        need(type(body) is dict and body.get('schema')=='R2D2_CAPACITY_BOOTSTRAP_V3'
             and set(body)=={'schema','identity','calendar_pin_sha','release_sha','package_sha','roots','document_pins','veto_views','restore_revocation','r2d2_v2_capacity_veto_mode'}
             and type(body['document_pins']) is dict and {'CODEX','FABLE','DUDU','ACT_B','B_CODEX','B_FABLE','B_DUDU','TEMPLATE'}<=set(body['document_pins']), 'VETO_CONSUMER_DOCUMENT_FIELDS')
        pins=[]
        for item in body['document_pins'].values():
            need(type(item) is dict and set(item)=={'file','sha256'} and type(item['sha256']) is str
                 and SHA.fullmatch(item['sha256']), 'VETO_CONSUMER_DOCUMENT_PIN')
            pins.append(item['sha256'])
        need(sorted(set(pins)) == spec['consumer_document_pins']
             and set(pins) <= set(spec['required_pins']), 'VETO_CONSUMER_REVOCATION_SCOPE')
    except Refused:raise
    except Exception:raise Refused('VETO_CONSUMER_TEMPLATE_INVALID') from None


@dataclass(frozen=True)
class Emission:
    mode: str
    view_raw: bytes
    view_sha256: str
    observation_sha256: str
    authority_sha256: str
    spec_sha256: str
    operational_GO: bool = False


def validate_observation(row, spec, original_sha, now, derivation_rule_sha):
    need(type(row) is VerifiedObservation, "VETO_VERIFIER_RESULT")
    need(row.mode == spec["mode"], "VETO_VERIFIER_MODE")
    source, ctx = spec["source"], spec["context"]
    need(row.source_identity == source["identity"]
         and row.source_implementation_sha256 == source["implementation_sha256"]
         and row.observation_format == source["observation_format"], "VETO_SOURCE_IDENTITY")
    need(row.original_sha256 == original_sha and row.authority_sha256 == spec["authority_sha256"], "VETO_ORIGINAL_BINDING")
    need(row.authenticity_verified is True and row.authority_verified is True
         and row.revocation_checked is True, "VETO_EXTERNAL_VERIFICATION")
    need(type(row.authority_required_pins) is tuple
         and row.authority_required_pins == tuple(sorted(set(spec["required_pins"])|{derivation_rule_sha})), "VETO_REVOCATION_SCOPE")
    need(row.permitted_output_role == "FABLE", "VETO_ROLE_NOT_AUTHORIZED")
    need(all(getattr(row, key) == ctx[key] for key in ("epoch", "first_session", "day", "order_sha")), "VETO_OBSERVATION_CONTEXT")
    need(row.status == "VERIFIED", "VETO_STATUS_UNKNOWN")
    observed, until, opens = map(instant, (row.observed_at, row.valid_until, row.view_opens_at))
    need(opens == instant(spec["view_opens_at"]) and observed == opens, "VETO_VIEW_INSTANT")
    need(0 < (until-observed).total_seconds() <= 5, "VETO_UNIFIED_VALIDITY_INTERVAL")
    authority_from, authority_until = map(instant, (row.authority_valid_from, row.authority_valid_until))
    need(authority_from <= observed < until <= authority_until, "VETO_AUTHORITY_INTERVAL")
    need(observed <= now < until and (now-observed).total_seconds() <= spec["maximum_age_seconds"], "VETO_STALE_OR_FUTURE")
    need(now.astimezone(NEW_YORK).date().isoformat() == ctx["day"], "VETO_DAY_NOT_TODAY")
    need(type(row.owner_veto) is bool and row.owner_veto is False, "VETO_OWNER_VETOED")
    need(type(row.revoked_shas) is tuple and len(row.revoked_shas) == len(set(row.revoked_shas))
         and all(type(pin) is str and SHA.fullmatch(pin) is not None for pin in row.revoked_shas), "VETO_REVOCATION_FIELDS")
    need(not set(row.revoked_shas).intersection(set(spec["required_pins"])|{derivation_rule_sha}), "VETO_AUTHORITY_REVOKED")


def emit_view(spec_raw, observation_raw, authority_raw, observation_sha256, *, spec_sha256, verifier, clock,
              consumer_template_raw, derivation_rule_raw, derivation_rule_sha):
    """Validate an actual original and return bytes only; never publish or renew it.

    `observation_sha256` must come from the authorized original/pin provider, not
    a scheduler's fabricated expected observation. Runtime must independently pin
    the spec, this source, callback implementation, authority and provider before
    calling. Callback failure, absence or false verification always refuses.
    """
    need(type(spec_raw) is bytes and type(spec_sha256) is str and SHA.fullmatch(spec_sha256) is not None
         and digest(spec_raw) == spec_sha256, "VETO_SPEC_HASH")
    spec = read_spec(spec_raw)
    # An imported Python object graph is not a boundary against hostile callbacks.
    # REAL requires a separately installed/supervised runtime, absent from this candidate.
    need(spec["mode"]=="FIXTURE", "VETO_REAL_PROCESS_AUTHORITY_UNAVAILABLE")
    check_derivation_rule(derivation_rule_raw,derivation_rule_sha,spec)
    _consumer_template(consumer_template_raw, spec)
    need(type(observation_raw) is bytes and 0 < len(observation_raw) <= MAX_ORIGINAL_BYTES, "VETO_ORIGINAL_ABSENT")
    need(type(observation_sha256) is str and SHA.fullmatch(observation_sha256) is not None
         and digest(observation_raw) == observation_sha256, "VETO_ORIGINAL_HASH")
    need(type(authority_raw) is bytes and 0 < len(authority_raw) <= MAX_ORIGINAL_BYTES
         and digest(authority_raw) == spec["authority_sha256"], "VETO_AUTHORITY_HASH")
    if spec['mode'] == 'REAL':
        need(clock is real_clock, 'VETO_REAL_CLOCK_REQUIRED')
        _check_loaded(verifier)
    else:
        need(type(verifier) in {VerifierBinding, LoadedVerifier} and callable(verifier.verify_original), "VETO_VERIFIER_UNBOUND")
        if type(verifier) is LoadedVerifier:_check_loaded(verifier)
    need(verifier.identity == spec["verifier"]["identity"]
         and verifier.implementation_sha256 == spec["verifier"]["implementation_sha256"], "VETO_VERIFIER_IDENTITY")
    need(verifier.mode == spec["mode"], "VETO_VERIFIER_MODE")
    before = now_utc(clock)
    try:
        row = verifier.verify_original(observation_raw, authority_raw, spec_raw, before, derivation_rule_raw, derivation_rule_sha)
    except Exception:
        raise Refused("VETO_VERIFIER_REJECTED") from None
    try:
        validate_observation(row, spec, observation_sha256, before,derivation_rule_sha)
        after = now_utc(clock)
        if type(verifier) is LoadedVerifier:_check_loaded(verifier)
        need(after >= before, "VETO_CLOCK_ROLLBACK")
        validate_observation(row, spec, observation_sha256, after,derivation_rule_sha)
        body = {"status": row.status, "role": "FABLE", "epoch": row.epoch,
                "day": row.day, "order_sha": row.order_sha,
                "observed_at": row.observed_at, "valid_until": row.valid_until,
                "owner_veto": row.owner_veto, "revoked_shas": list(row.revoked_shas),
                "evidence_sha": observation_sha256}
        doc = {"schema": DOCUMENT_SCHEMA, "kind": "VETO_VIEW",
               "state": "ISSUED" if spec["mode"] == "REAL" else "DRAFT", "body": body}
        raw = BEGIN.encode() + b"\n```json\n" + canonical(doc) + b"\n```\n" + END.encode() + b"\n"
        return Emission(spec["mode"], raw, digest(raw), observation_sha256,
                        digest(authority_raw), digest(spec_raw))
    except Refused:
        raise
    except Exception:
        raise Refused("VETO_OBSERVATION_INVALID") from None


DERIVATION_SCHEMA='R2D2_IMAGE_VETO_DERIVATION_RULE_V1'
def check_derivation_rule(raw,expected_sha,spec):
    need(type(raw)is bytes and 0<len(raw)<=MAX_ORIGINAL_BYTES and type(expected_sha)is str
         and SHA.fullmatch(expected_sha)and digest(raw)==expected_sha,'VETO_DERIVATION_RULE_PIN')
    def pairs(items):
        out={}
        for k,x in items:need(k not in out,'VETO_DERIVATION_DUPLICATE');out[k]=x
        return out
    try:rule=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in()).throw(ValueError()))
    except Exception:raise Refused('VETO_DERIVATION_RULE_JSON')from None
    need(type(rule)is dict and set(rule)=={'schema','purpose','spec_base','observe_not_before','observe_not_after'}
         and canonical(rule)+b'\n'==raw and rule['schema']==DERIVATION_SCHEMA
         and rule['purpose']=='IMAGE_ADMISSION_MONDAY','VETO_DERIVATION_RULE_FIELDS')
    base=rule['spec_base'];actual=dict(spec);actual.pop('view_opens_at')
    need(type(base)is dict and base==actual,'VETO_DERIVATION_STATIC_MISMATCH')
    c=spec['context'];need(c['epoch']=='R2D2-V2-SHADOW-2026-10-12'
         and c['first_session']==c['day']=='2026-10-12','VETO_DERIVATION_MONDAY_CONTEXT')
    need(spec['maximum_age_seconds']<=5,'VETO_UNIFIED_MAXIMUM_AGE')
    before,opens,after=map(instant,(rule['observe_not_before'],spec['view_opens_at'],rule['observe_not_after']))
    need(before<=opens<after,'VETO_DERIVATION_OBSERVATION_WINDOW')
    need(before.astimezone(NEW_YORK).date().isoformat()=='2026-10-12'
         and (after-timedelta(microseconds=1)).astimezone(NEW_YORK).date().isoformat()=='2026-10-12','VETO_DERIVATION_FACTUAL_WINDOW')
    return rule
