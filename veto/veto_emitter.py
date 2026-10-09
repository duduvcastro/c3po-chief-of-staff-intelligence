"""Offline candidate: authenticated original -> the image's exact veto-view ABI.

No provider, installer, pin publisher, clock renewal, file/network/DB operation or
default verifier is supplied. REAL needs an independently pinned verifier and
actual source/authority originals. FIXTURE output is DRAFT, never ISSUED.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Callable
from zoneinfo import ZoneInfo


SPEC_SCHEMA = "R2D2_IMAGE_VETO_EMITTER_SPEC_V1"
DOCUMENT_SCHEMA = "R2D2_DOCUMENTARY_EVIDENCE_V1"
BEGIN = "<!-- R2D2-EVIDENCE-V1:BEGIN -->"
END = "<!-- R2D2-EVIDENCE-V1:END -->"
MAX_ORIGINAL_BYTES = 1024 * 1024
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
            "view_opens_at", "required_pins", "maximum_age_seconds"}, "VETO_SPEC_FIELDS")
        need(canonical(spec) + b"\n" == raw, "VETO_SPEC_CANONICAL")
        need(spec["schema"] == SPEC_SCHEMA and spec["mode"] in {"REAL", "FIXTURE"}, "VETO_SPEC_SCHEMA")
        ctx = spec["context"]
        need(type(ctx) is dict and set(ctx) == {"epoch", "first_session", "day", "order_sha"}, "VETO_CONTEXT_FIELDS")
        need(type(ctx["epoch"]) is str and IDENTITY.fullmatch(ctx["epoch"]) is not None
             and ctx["epoch"] != "r2d2-v2-03", "VETO_EPOCH")
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
class Emission:
    mode: str
    view_raw: bytes
    view_sha256: str
    observation_sha256: str
    authority_sha256: str
    spec_sha256: str
    operational_GO: bool = False


def validate_observation(row, spec, original_sha, now):
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
         and row.authority_required_pins == tuple(spec["required_pins"]), "VETO_REVOCATION_SCOPE")
    need(row.permitted_output_role == "FABLE", "VETO_ROLE_NOT_AUTHORIZED")
    need(all(getattr(row, key) == ctx[key] for key in ("epoch", "first_session", "day", "order_sha")), "VETO_OBSERVATION_CONTEXT")
    need(row.status == "VERIFIED", "VETO_STATUS_UNKNOWN")
    observed, until, opens = map(instant, (row.observed_at, row.valid_until, row.view_opens_at))
    need(opens == instant(spec["view_opens_at"]) and observed == opens, "VETO_VIEW_INSTANT")
    need(0 < (until-observed).total_seconds() <= 10, "VETO_VALIDITY_INTERVAL")
    authority_from, authority_until = map(instant, (row.authority_valid_from, row.authority_valid_until))
    need(authority_from <= observed < until <= authority_until, "VETO_AUTHORITY_INTERVAL")
    need(observed <= now < until and (now-observed).total_seconds() <= spec["maximum_age_seconds"], "VETO_STALE_OR_FUTURE")
    need(now.astimezone(NEW_YORK).date().isoformat() == ctx["day"], "VETO_DAY_NOT_TODAY")
    need(type(row.owner_veto) is bool and row.owner_veto is False, "VETO_OWNER_VETOED")
    need(type(row.revoked_shas) is tuple and len(row.revoked_shas) == len(set(row.revoked_shas))
         and all(type(pin) is str and SHA.fullmatch(pin) is not None for pin in row.revoked_shas), "VETO_REVOCATION_FIELDS")
    need(not set(row.revoked_shas).intersection(spec["required_pins"]), "VETO_AUTHORITY_REVOKED")


def emit_view(spec_raw, observation_raw, authority_raw, observation_sha256, *, spec_sha256, verifier, clock):
    """Validate an actual original and return bytes only; never publish or renew it.

    `observation_sha256` must come from the authorized original/pin provider, not
    a scheduler's fabricated expected observation. Runtime must independently pin
    the spec, this source, callback implementation, authority and provider before
    calling. Callback failure, absence or false verification always refuses.
    """
    need(type(spec_raw) is bytes and type(spec_sha256) is str and SHA.fullmatch(spec_sha256) is not None
         and digest(spec_raw) == spec_sha256, "VETO_SPEC_HASH")
    spec = read_spec(spec_raw)
    need(type(observation_raw) is bytes and 0 < len(observation_raw) <= MAX_ORIGINAL_BYTES, "VETO_ORIGINAL_ABSENT")
    need(type(observation_sha256) is str and SHA.fullmatch(observation_sha256) is not None
         and digest(observation_raw) == observation_sha256, "VETO_ORIGINAL_HASH")
    need(type(authority_raw) is bytes and 0 < len(authority_raw) <= MAX_ORIGINAL_BYTES
         and digest(authority_raw) == spec["authority_sha256"], "VETO_AUTHORITY_HASH")
    need(type(verifier) is VerifierBinding and callable(verifier.verify_original), "VETO_VERIFIER_UNBOUND")
    need(verifier.identity == spec["verifier"]["identity"]
         and verifier.implementation_sha256 == spec["verifier"]["implementation_sha256"], "VETO_VERIFIER_IDENTITY")
    need(verifier.mode == spec["mode"], "VETO_VERIFIER_MODE")
    before = now_utc(clock)
    try:
        row = verifier.verify_original(observation_raw, authority_raw, spec_raw, before)
    except Exception:
        raise Refused("VETO_VERIFIER_REJECTED") from None
    try:
        validate_observation(row, spec, observation_sha256, before)
        after = now_utc(clock)
        need(after >= before, "VETO_CLOCK_ROLLBACK")
        validate_observation(row, spec, observation_sha256, after)
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
