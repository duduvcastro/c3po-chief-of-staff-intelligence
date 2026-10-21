"""The decisor's verdicts of ONE night for the R2D2 lab, ENCRYPTED to the lab's key (owner's order of 2026-10-20).

From Monday 26/10 the R2D2 measurement mode (virtual, GitHub Actions in the PRIVATE lab repository) takes entries only in
the names the decisor marks ``COMPRA_PERMITIDA`` for the night before the session, and measures the same day without the
gate side by side. This repository is PUBLIC and anyone can download its workflow artifacts, so the verdict list (it names
symbols) never leaves the host in clear: ``export`` reads the night's verdicts (read-only), builds the canonical
plaintext and returns only an envelope encrypted to the lab's X25519 public key — an ephemeral X25519 key agreement,
HKDF-SHA256 (info binding both public keys) and AES-256-GCM, with the clear header as associated data. In clear: the
night, the decision run's clock and identity, the thresholds' hash, the counts (no symbol), the plaintext's sha256 (the
plaintext carries a random ``blinding`` so that hash cannot be confirmed by guessing a list) and the key material. The
private key exists only as the lab's secret; nothing here can decrypt.

The night N is a NYSE (XNYS) session: the session the decisor's verdicts are FOR (``valuation_decisions.session_date``,
the last completed session at the run's clock — never a civil date). Its verdicts are the US records (NASDAQ, NYSE) of
the LATEST decision run for N published by the cutoff ``min(now, open of the session after N)`` — what an entry on the
next session could have read before the open; a run published after that open is never exported for N. Refused (a code,
no symbol, nothing encrypted): N not a session, N not closed yet, no decision recorded for N (by the cutoff), any stored
record of N whose identity does not verify, a run whose records disagree on their clock/generation/thresholds, and a
night that is not COMPLETE — the generation in force at the cutoff is not the one the selected run decided (a canonical
retry activated a later generation that was not decided again, or the run decided an older one).

    python -m app.valuation_decision --export-verdicts --night 2026-10-23 --recipient-public-key <base64 X25519>
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import secrets
from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import valuation_official as official
from .valuation_decision import DECISION_SCHEMA, DECISOR_VERSION, MODE_SHADOW, VERDICTS
from .valuation_official import CalendarUnavailable, generation_at, session_date_of

EXPORT_SCHEMA = "VALUATION_DECISOR_VERDICTS_V1"
ENVELOPE_SCHEMA = "VALUATION_DECISOR_VERDICTS_ENVELOPE_V1"
REFUSAL_SCHEMA = "VALUATION_DECISOR_VERDICTS_REFUSAL_V1"
ALGORITHM = "X25519-HKDF-SHA256-AES-256-GCM"
HKDF_INFO = b"c3po valuation decisor verdicts v1"
US_MARKETS: tuple[str, ...] = ("NASDAQ", "NYSE")
NIGHT_CALENDAR_MARKET = "NYSE"  # XNYS: NASDAQ and NYSE share it (valuation_official.CALENDARS)
LAST_COMPLETED = "last-completed"
READ_ONLY_PGOPTION = "-c default_transaction_read_only=on"
NIGHT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
# the envelope's keys, EXACTLY: a key it grows is reviewed here (and in the workflow's runner check) before it can reach
# a public artifact — no field may carry the plaintext
ENVELOPE_KEYS = frozenset({"schema", "algorithm", "night", "decision_instant", "decision_run_id", "generation_id", "decisor_version", "thresholds_sha256",
                           "counts", "plaintext_sha256", "recipient_public_key", "ephemeral_public_key", "nonce", "ciphertext"})
COUNT_KEYS = frozenset({"rows", "by_market", "by_verdict", "by_verdict_without_events"})
PLAINTEXT_KEYS = frozenset({"schema", "night", "decision_instant", "thresholds_sha256", "decisor_version", "blinding", "rows"})
ROW_KEYS = frozenset({"symbol", "market", "verdict", "reasons", "verdict_without_events"})
# refusal codes: the ONLY reason a refusal prints (stdout, one JSON line) — never a symbol
REFUSALS = ("NIGHT_INVALID", "NOT_A_SESSION", "CALENDAR_UNAVAILABLE", "NIGHT_NOT_CLOSED", "NO_DECISIONS", "DECISIONS_ONLY_AFTER_NEXT_OPEN",
            "UNVERIFIED_DECISIONS", "RUN_INCONSISTENT", "GENERATION_NOT_DECIDED", "KEY_INVALID")


class ExportRefused(Exception):
    """The night cannot be exported: ``code`` is one of ``REFUSALS`` (printed), ``detail`` carries no symbol."""

    def __init__(self, code: str, detail: str) -> None:
        assert code in REFUSALS
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def canonical_bytes(value: Any) -> bytes:
    """The canonical JSON bytes (the encoding ``valuation_official.canonical_sha256`` hashes)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: Any, *, size: int | None = None, name: str) -> bytes:
    if not isinstance(text, str):
        raise ValueError(f"{name} is not base64 text")
    try:
        raw = base64.b64decode(text.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as error:
        raise ValueError(f"{name} is not base64") from error
    if size is not None and len(raw) != size:
        raise ValueError(f"{name} is {len(raw)} bytes, not {size}")
    return raw


def public_key(text: str) -> X25519PublicKey:
    """A base64 raw X25519 public key (32 bytes) — ``KEY_INVALID`` otherwise."""
    try:
        return X25519PublicKey.from_public_bytes(_unb64(text, size=32, name="the recipient public key"))
    except ValueError as error:
        raise ExportRefused("KEY_INVALID", str(error)) from error


def _raw(key: X25519PublicKey) -> bytes:
    return key.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)


def _key(shared: bytes, ephemeral: bytes, recipient: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=HKDF_INFO + ephemeral + recipient).derive(shared)


def force_read_only_session(environ: MutableMapping[str, str] | None = None) -> str:
    """``-c default_transaction_read_only=on`` last in ``PGOPTIONS`` (libpq reads it at connect time): every transaction
    of this process is read-only in PostgreSQL itself — the export cannot write, not just does not."""
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    current = env.get("PGOPTIONS", "").replace(READ_ONLY_PGOPTION, " ").split()
    env["PGOPTIONS"] = " ".join([*current, READ_ONLY_PGOPTION])
    return env["PGOPTIONS"]


# ------------------------------------------------------------------ the night's verdicts (read-only)


def resolve_night(night: str, *, now: datetime) -> str:
    if night == LAST_COMPLETED:
        try:
            return session_date_of(NIGHT_CALENDAR_MARKET, now)
        except CalendarUnavailable as error:
            raise ExportRefused("CALENDAR_UNAVAILABLE", "the NYSE calendar cannot name the last completed session") from error
    if not NIGHT_PATTERN.fullmatch(night):
        raise ExportRefused("NIGHT_INVALID", f"--night must be YYYY-MM-DD or {LAST_COMPLETED}")
    return night


def _next_open(night: str) -> datetime:
    """The open of the NYSE session after ``night`` (``NOT_A_SESSION`` when ``night`` is not one)."""
    try:
        calendar = official._calendar(NIGHT_CALENDAR_MARKET)
        if not calendar.is_session(night):
            raise ExportRefused("NOT_A_SESSION", f"{night} is not a NYSE session")
        return _utc(calendar.session_open(calendar.next_session(night)).to_pydatetime())
    except ExportRefused:
        raise
    except Exception as error:  # the calendar is out of range or broken: nothing is exported on a guess
        raise ExportRefused("CALENDAR_UNAVAILABLE", f"the NYSE calendar cannot answer for {night} ({type(error).__name__})") from error


def counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The aggregate the envelope carries in clear: no symbol, every verdict and market listed (zeros included)."""
    return {
        "rows": len(rows),
        "by_market": {market: sum(1 for row in rows if row["market"] == market) for market in US_MARKETS},
        "by_verdict": {verdict: sum(1 for row in rows if row["verdict"] == verdict) for verdict in VERDICTS},
        "by_verdict_without_events": {verdict: sum(1 for row in rows if row["verdict_without_events"] == verdict) for verdict in VERDICTS},
    }


def night_verdicts(database: Any, night: str, *, now: datetime | None = None) -> dict[str, Any]:
    """The verdicts of night ``night`` (see the module docstring), as ``{"document": <plaintext>, "header": <clear
    identity>}``. Read-only: ``database.valuation_decisions_of_session`` and the generation in force at the cutoff."""
    clock = _utc(now) if now is not None else datetime.now(timezone.utc)
    night = resolve_night(night, now=clock)
    next_open = _next_open(night)
    try:
        closed = session_date_of(NIGHT_CALENDAR_MARKET, clock)
    except CalendarUnavailable as error:
        raise ExportRefused("CALENDAR_UNAVAILABLE", "the NYSE calendar cannot name the last completed session") from error
    if night > closed:
        raise ExportRefused("NIGHT_NOT_CLOSED", f"the {night} session has not closed: its night is not complete")
    cutoff = min(clock, next_open)
    records, unverified = database.valuation_decisions_of_session(list(US_MARKETS), night)
    if unverified:
        raise ExportRefused("UNVERIFIED_DECISIONS", f"{unverified} stored decision(s) of {night} do not verify: nothing is exported")
    if not records:
        raise ExportRefused("NO_DECISIONS", f"no decision recorded for {night}")
    eligible = [record for record in records if _utc(record["published_at"]) <= cutoff]
    if not eligible:
        raise ExportRefused("DECISIONS_ONLY_AFTER_NEXT_OPEN", f"every decision for {night} was published after {cutoff.isoformat()}")
    runs: dict[str, tuple[datetime, datetime]] = {}
    for record in eligible:
        key = (_utc(record["published_at"]), _utc(record["prediction_instant"]))
        held = runs.get(str(record["run_id"]))
        runs[str(record["run_id"])] = key if held is None or key > held else held
    run_id = max(runs, key=lambda name: (runs[name], name))
    chosen = [record for record in eligible if str(record["run_id"]) == run_id]
    identity = {(str(record["prediction_instant"]), str(record["generation_id"]), str(record["thresholds_sha256"]), str(record["decisor_version"]),
                 record.get("schema"), record.get("mode")) for record in chosen}
    if len(identity) != 1:
        raise ExportRefused("RUN_INCONSISTENT", f"the records of run {run_id} disagree on their clock, generation, thresholds or version")
    instant, generation_id, thresholds, version, schema, mode = next(iter(identity))
    if schema != DECISION_SCHEMA or mode != MODE_SHADOW or SHA256_PATTERN.fullmatch(thresholds) is None:
        raise ExportRefused("RUN_INCONSISTENT", f"run {run_id} is not a {DECISION_SCHEMA} shadow run with a thresholds hash")
    in_force = generation_at(database, cutoff)
    if not in_force or str(in_force.get("generation_id")) != generation_id:
        raise ExportRefused("GENERATION_NOT_DECIDED", f"the generation in force at {cutoff.isoformat()} is not the one run {run_id} decided: "
                                                      f"the night {night} is not complete")
    rows: list[dict[str, Any]] = []
    for record in sorted(chosen, key=lambda item: (str(item["market"]), str(item["symbol"]))):
        checks = record.get("checks") if isinstance(record.get("checks"), Mapping) else {}
        counterfactual = (checks or {}).get("counterfactual")
        without = counterfactual.get("verdict_without_events") if isinstance(counterfactual, Mapping) else None
        if record["verdict"] not in VERDICTS or without not in VERDICTS:
            raise ExportRefused("RUN_INCONSISTENT", f"a record of run {run_id} carries no valid verdict or counterfactual")
        rows.append({"symbol": str(record["symbol"]), "market": str(record["market"]), "verdict": str(record["verdict"]),
                     "reasons": [str(code) for code in record["reason_codes"]], "verdict_without_events": str(without)})
    decision_instant = _utc(instant).isoformat()
    document = {"schema": EXPORT_SCHEMA, "night": night, "decision_instant": decision_instant, "thresholds_sha256": thresholds,
                "decisor_version": version, "blinding": secrets.token_hex(16), "rows": rows}
    header = {"night": night, "decision_instant": decision_instant, "decision_run_id": run_id, "generation_id": generation_id,
              "decisor_version": version, "thresholds_sha256": thresholds, "counts": counts(rows)}
    return {"document": document, "header": header}


# ------------------------------------------------------------------ the envelope


def encrypt(plaintext: bytes, recipient_public_key: str, header: Mapping[str, Any]) -> dict[str, Any]:
    """The envelope of ``plaintext`` for ``recipient_public_key`` (base64 raw X25519): a fresh ephemeral key per envelope,
    HKDF-SHA256 over the shared secret (info = ``HKDF_INFO`` + ephemeral + recipient public keys), AES-256-GCM with a
    random 96-bit nonce and the canonical clear header (every key but ``ciphertext``) as associated data."""
    recipient = public_key(recipient_public_key)
    ephemeral = X25519PrivateKey.generate()
    ephemeral_raw, recipient_raw = _raw(ephemeral.public_key()), _raw(recipient)
    key = _key(ephemeral.exchange(recipient), ephemeral_raw, recipient_raw)
    nonce = secrets.token_bytes(12)
    clear = {**dict(header), "schema": ENVELOPE_SCHEMA, "algorithm": ALGORITHM, "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
             "recipient_public_key": _b64(recipient_raw), "ephemeral_public_key": _b64(ephemeral_raw), "nonce": _b64(nonce)}
    envelope = {**clear, "ciphertext": _b64(AESGCM(key).encrypt(nonce, plaintext, canonical_bytes(clear)))}
    check_envelope(envelope)
    return envelope


def check_envelope(envelope: Any) -> None:
    """The exact shape of an envelope (``ValueError`` otherwise): exactly ``ENVELOPE_KEYS``, exactly ``COUNT_KEYS`` with
    every market and verdict, typed clear fields, 32-byte keys, a 12-byte nonce, a ciphertext with its 16-byte tag."""
    if not isinstance(envelope, Mapping) or set(envelope) != ENVELOPE_KEYS:
        raise ValueError("the envelope's keys are not exactly the envelope's")
    if envelope["schema"] != ENVELOPE_SCHEMA or envelope["algorithm"] != ALGORITHM:
        raise ValueError("unexpected envelope schema or algorithm")
    if not isinstance(envelope["night"], str) or NIGHT_PATTERN.fullmatch(envelope["night"]) is None:
        raise ValueError("the night is not YYYY-MM-DD")
    for name in ("plaintext_sha256", "thresholds_sha256"):
        if not isinstance(envelope[name], str) or SHA256_PATTERN.fullmatch(envelope[name]) is None:
            raise ValueError(f"{name} is not a sha256")
    for name in ("decision_instant", "decision_run_id", "generation_id", "decisor_version"):
        if not isinstance(envelope[name], str) or not envelope[name]:
            raise ValueError(f"{name} is not text")
    _utc(envelope["decision_instant"])
    for name in ("recipient_public_key", "ephemeral_public_key"):
        _unb64(envelope[name], size=32, name=name)
    _unb64(envelope["nonce"], size=12, name="nonce")
    if len(_unb64(envelope["ciphertext"], name="ciphertext")) < 16:
        raise ValueError("the ciphertext is shorter than its tag")
    tally = envelope["counts"]
    if not isinstance(tally, Mapping) or set(tally) != COUNT_KEYS or not isinstance(tally["rows"], int):
        raise ValueError("the counts' keys are not exactly the counts'")
    for name, keys in (("by_market", US_MARKETS), ("by_verdict", VERDICTS), ("by_verdict_without_events", VERDICTS)):
        block = tally[name]
        if not isinstance(block, Mapping) or set(block) != set(keys) or not all(isinstance(value, int) and value >= 0 for value in block.values()):
            raise ValueError(f"counts.{name} is not exactly {', '.join(keys)}")
        if sum(block.values()) != tally["rows"]:
            raise ValueError(f"counts.{name} does not add up to counts.rows")


def decrypt(envelope: Mapping[str, Any], private_key: str) -> dict[str, Any]:
    """The plaintext document of ``envelope`` (the lab's side; here for the tests): the shape checked, the key the
    envelope names is the private key's, AES-GCM authenticates the ciphertext AND the clear header, the plaintext's sha256
    and the counts recompute, and the night is the header's."""
    check_envelope(envelope)
    secret = X25519PrivateKey.from_private_bytes(_unb64(private_key, size=32, name="the private key"))
    recipient_raw = _raw(secret.public_key())
    if _unb64(envelope["recipient_public_key"], size=32, name="recipient_public_key") != recipient_raw:
        raise ValueError("the envelope is for another key")
    ephemeral_raw = _unb64(envelope["ephemeral_public_key"], size=32, name="ephemeral_public_key")
    key = _key(secret.exchange(X25519PublicKey.from_public_bytes(ephemeral_raw)), ephemeral_raw, recipient_raw)
    clear = {name: value for name, value in envelope.items() if name != "ciphertext"}
    plaintext = AESGCM(key).decrypt(_unb64(envelope["nonce"], size=12, name="nonce"), _unb64(envelope["ciphertext"], name="ciphertext"),
                                    canonical_bytes(clear))
    if hashlib.sha256(plaintext).hexdigest() != envelope["plaintext_sha256"]:
        raise ValueError("plaintext_sha256 does not recompute")
    document = json.loads(plaintext.decode("utf-8"))
    if not isinstance(document, dict) or set(document) != PLAINTEXT_KEYS or document["schema"] != EXPORT_SCHEMA:
        raise ValueError("unexpected plaintext shape")
    if document["night"] != envelope["night"] or document["decision_instant"] != envelope["decision_instant"]:
        raise ValueError("the plaintext is of another night or run")
    if any(not isinstance(row, dict) or set(row) != ROW_KEYS for row in document["rows"]) or counts(document["rows"]) != dict(envelope["counts"]):
        raise ValueError("the rows do not match the counts")
    return document


def export(database: Any, night: str, recipient_public_key: str, *, now: datetime | None = None) -> dict[str, Any]:
    """The encrypted envelope of the night's verdicts — the ONLY thing the CLI prints. The key is checked first: a bad
    key reads nothing."""
    public_key(recipient_public_key)
    verdicts = night_verdicts(database, night, now=now)
    return encrypt(canonical_bytes(verdicts["document"]), recipient_public_key, verdicts["header"])


def refusal(error: ExportRefused, night: str) -> dict[str, Any]:
    """What a refusal prints: its code and the requested night — never the detail (the runner prints the code only)."""
    return {"schema": REFUSAL_SCHEMA, "night": night, "refused": error.code}
