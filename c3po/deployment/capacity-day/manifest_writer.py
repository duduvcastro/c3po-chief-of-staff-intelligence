"""Capacity-day manifest writer: admission commit and the dated bar manifest, in one process.

Deployment script. It is NOT part of the pinned implementation package: it lives in
c3po/deployment, is pinned by SHA-256 in each authorisation, and only imports and calls
the packaged code of the deployed image. Run it from a read-only bind mount or on
standard input:

    python -I -B - <arguments> < manifest_writer.py

Offline candidate: nothing here was installed or run on a host or in a container.

One invocation, for one session date:

  publish (default)  pre-flight, then (with --prepare-first, when the day's binding is not
                     committed yet) prepare-capacity-day through the packaged code, then the
                     exclusive publication of <manifest-directory>/<day>.json: the canonical
                     JSON of DailyCapacityBinding.bar_manifest() of the committed binding.
  --verify-only      compares the existing file with the committed binding. Never writes,
                     never repairs.
  --preflight        builds the same context and validates everything that needs neither the
                     clock nor the veto view. Never waits, prepares, writes or reads the view.

The file is created by private temporary + fsync + link() + unlink, mode 0600, and is never
overwritten, truncated or deleted. The temporary is created (empty) before anything is
committed, so a directory that cannot take a new file refuses with nothing committed. The
one write that needs no bar_manifest GO is the removal of the second name left by a
publication interrupted between link() and unlink(), and only after the bytes under the
final name were found equal to the manifest of the committed binding.

The list of symbols is written only to that file. Standard output carries exactly one JSON
line with counts, hashes, clocks and constant codes. A refusal code always holds an
underscore, which no symbol can. The database URL is read by the packaged settings and is
never printed, never an argument, and never part of an error text that reaches output.

Authority. This script issues no GO. The day's bar_manifest GO is checked by the packaged
documentary authority (Act B chain, the day's template, GO and publication records, the
pinned veto view): before the commit against the plan in the day's payload file, and again
immediately before link() against the plan frozen in the committed binding.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
from types import SimpleNamespace
from typing import Any, Callable, Iterator
import warnings

# Where the image keeps the application. The only path this script adds to sys.path
# (python -I leaves the script directory and the environment out of it).
APPLICATION_ROOT = '/app'

RECEIPT_SCHEMA = 'R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1'
PHASE, ADMISSION = 'bar_manifest', 'admission'
MAX_MANIFEST_BYTES = 65536                   # the supervisor's own bound
MAX_SYMBOLS = 550                            # the producer's own bound
CUTOFF_BEFORE_OPEN = timedelta(minutes=10)   # 09:20 New York on a regular day
MAX_WAIT_SECONDS = 900                       # longest parking before --view-opens-at
VIEW_GRACE_SECONDS = 5.0                     # a view emitted in-window may lag this much
# States of a view file that is still being delivered; retried only inside the grace.
VIEW_NOT_YET = frozenset({'VETO_HASH_MISMATCH', 'ROOT_FILE_POLICY', 'ROOT_FILE_CHANGED'})
EXIT_OK, EXIT_UNVERIFIED, EXIT_REFUSED = 0, 1, 3
GO_MODES = ('INDIVIDUAL', 'DELEGATED_ACT_B')  # --require-go-mode
GO_FIELDS = frozenset({'decision', 'epoch', 'first_session', 'day', 'phase', 'proposal_sha', 'signed_order_sha',
                       'template_sha', 'mode', 'not_before', 'not_after', 'automatic_retry', 'authority_receipts'})
# A code always holds an underscore; the symbol grammar ([A-Z0-9][A-Z0-9.-]{0,19}) has none.
_CODE = re.compile(r'[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_EPOCH = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z')   # the producer's epoch grammar
_TEMPORARY = r'\.%s\.[0-9a-f]{16}\.tmp\Z'
_APP: SimpleNamespace | None = None


class Refused(ValueError):
    """One constant code; never input, a path or a symbol."""


def need(condition: Any, code: str) -> None:
    if not condition:
        raise Refused(code)


def packaged() -> SimpleNamespace:
    """The deployed image's own code, imported once from APPLICATION_ROOT and nowhere else."""
    global _APP
    if _APP is None:
        if APPLICATION_ROOT not in sys.path:
            sys.path.insert(0, APPLICATION_ROOT)
        store = importlib.import_module('app.r2d2_v2_store')
        origin = os.path.dirname(os.path.dirname(os.path.realpath(str(store.__file__))))
        need(origin == os.path.realpath(APPLICATION_ROOT), 'MANIFEST_APPLICATION_ROOT')
        from app.r2d2_v2_calendar import NEW_YORK
        from app.r2d2_v2_capacity_authority import validate_contract
        from app.r2d2_v2_capacity_bound import DailyCapacityBinding
        from app.r2d2_v2_epoch_assembler import digest as go_digest, is_sha, stamp, validate_go
        from app.r2d2_v2_massive_supervisor import private_bytes
        from app.r2d2_v2_minute_bars import _SYMBOL
        from app.r2d2_v2_sources import _load_json, _open_directory
        _APP = SimpleNamespace(
            NEW_YORK=NEW_YORK, validate_contract=validate_contract, DailyCapacityBinding=DailyCapacityBinding,
            go_digest=go_digest, is_sha=is_sha, stamp=stamp, validate_go=validate_go, private_bytes=private_bytes,
            symbol=_SYMBOL, load_json=_load_json, open_directory=_open_directory, canonical=store.canonical,
            utc=store.utc)
    return _APP


@dataclass
class Context:
    """Everything the writer consumes, already bound to the verified release."""
    release: Any                                    # verified Release
    calendar: Any                                   # ShadowCalendar
    read_state: Callable[[], dict | None]           # store.read(epoch); verifies the state hash
    verify_binding: Callable[[dict], bool]          # Act B chain for a binding document
    verify_go: Callable[[dict, dict], bool]         # documentary GO + publication + veto view
    verify_chain: Callable[[str], None]             # Act A/B chain for the day; raises a code
    check_go: Callable[[dict, dict], None]          # (GO, plan): every document behind a GO, without the view
    read_go: Callable[[str, str], dict]             # (day, phase) -> the 13-field GO
    read_payload: Callable[[str], dict]             # day -> {'contract', 'causal'}
    view_pinned: Callable[[str], bool]              # the capacity config pins a view for the day
    veto_bounds: Callable[[str], tuple[datetime, datetime]]   # pinned view: observed_at, valid_until
    prepare: Callable[[str], dict] | None = None    # only with --prepare-first
    pins: dict = field(default_factory=dict)        # non-secret identifiers echoed in the receipt
    protected: tuple = ()                           # configured roots the manifest directory must not touch


def _code(error: BaseException) -> str | None:
    if (isinstance(error, ValueError) and len(error.args) == 1 and type(error.args[0]) is str
            and _CODE.match(error.args[0])):
        return error.args[0]
    return None


def refusal(error: BaseException) -> tuple[str, int]:
    """Constant codes only. Anything that is not a reviewed code is UNVERIFIED."""
    code = _code(error)
    if code is not None:
        return code, EXIT_REFUSED
    if isinstance(error, ImportError):
        return 'MANIFEST_APPLICATION_UNAVAILABLE', EXIT_UNVERIFIED
    if type(error).__module__.split('.')[0] == 'psycopg':
        return 'MANIFEST_DATABASE_UNAVAILABLE', EXIT_UNVERIFIED
    if isinstance(error, OSError):
        return 'MANIFEST_FILE_UNAVAILABLE', EXIT_UNVERIFIED
    return 'MANIFEST_UNVERIFIED', EXIT_UNVERIFIED


def _coded(function: Callable[[], Any], code: str, missing: str | None = None) -> Any:
    """Run a read or a structural check; anything that is not already a code becomes `code`."""
    try:
        return function()
    except FileNotFoundError:
        raise Refused(missing or code) from None
    except OSError:
        raise
    except Exception as error:
        if _code(error) is not None:
            raise
        raise Refused(code) from None


def _structure_only(_go: dict, _plan: dict) -> bool:
    """Stand-in for the authority in static_go ONLY. No gate uses it."""
    return True


def static_go(go: Any, plan: Any, *, day: str, phase: str) -> tuple[datetime, datetime]:
    """Is this GO well formed for the day's plan? The packaged validator, without clock or authority.

    The clock is placed at the GO's own not_before and the authority is replaced by a
    stand-in, so the answer covers the 13 fields, day, phase, plan hash, order and template
    hashes, the phase window and the notice. The result is discarded: nothing is prepared,
    written or published on it (see _gate). Returns the GO window.
    """
    app = packaged()
    need(type(go) is dict and set(go) == GO_FIELDS, 'MANIFEST_GO_FIELDS')

    def check() -> tuple[datetime, datetime]:
        proposal = plan['proposal']
        need(proposal['phase'] == phase and proposal['daily']['day'] == day, 'MANIFEST_PLAN_DAY_PHASE')
        app.validate_go(go, plan, now=app.stamp(go['not_before']), authority_verifier=_structure_only)
        return app.utc(go['not_before']), app.utc(go['not_after'])

    return _coded(check, 'MANIFEST_GO_INVALID')


def go_records(authority: Any, go: dict) -> None:
    """Pinned documentary records behind one GO, without the veto view.

    Each condition is a necessary one of the packaged verify_go, so this can refuse early
    with a precise code but can never accept what verify_go would refuse.
    """
    app = packaged()

    def check() -> None:
        phase, receipts = go['phase'], go['authority_receipts']
        template, record = authority.record('TEMPLATE'), authority.record('GO:' + phase)
        need(record['go_sha'] == app.go_digest(go) and record['decision'] == 'GO'
             and record['template_sha'] == go['template_sha'] == template['sha'], 'MANIFEST_GO_RECORD')
        if go['mode'] == 'DELEGATED_ACT_B':
            publication = authority.record('PUBLICATION:' + phase)
            need(receipts['publication_receipt_sha'] == authority.pins['PUBLICATION:' + phase]['sha256']
                 and publication['published_at'] == record['published_at'] == receipts['published_at'],
                 'MANIFEST_GO_RECORD')

    _coded(check, 'MANIFEST_GO_RECORD', missing='MANIFEST_GO_RECORD_MISSING')


def _no_view(now: datetime) -> dict:
    """Stand-in for the veto view in static_documents ONLY. No gate uses it."""
    return {'status': 'VERIFIED', 'observed_at': now.isoformat(),
            'valid_until': (now + timedelta(seconds=10)).isoformat(), 'owner_veto': False, 'revoked_shas': []}


def static_documents(authority: Any, go: dict, plan: dict) -> None:
    """Would the documents behind this GO pass the packaged verify_go? Without clock or view.

    The packaged verify_go itself, on a copy of the authority whose veto view is a stand-in
    open at the GO's own not_before. It covers what needs neither the clock nor the real
    view: the Act A and Act B chains, the order hash, the template's membership and scope,
    the GO record's scope, role and binding, the publication record and the notice. The
    result is discarded: nothing is prepared, written or published on it (see _gate, which
    asks the real authority with the real view).
    """
    blind = copy.copy(authority)
    blind.revocation_reader = _no_view
    need(blind.verify_go(go, plan, packaged().stamp(go['not_before'])) is True, 'MANIFEST_GO_DOCUMENTS')


def manifest_bytes(manifest: Any, *, day: str, epoch: str) -> bytes:
    """Every check the producer applies after the claim, applied before publishing.

    A manifest that passes the supervisor but fails the producer costs all five claims of
    the day, so the producer's grammar is enforced here in full.
    """
    app = packaged()
    need(type(manifest) is dict and set(manifest) == {'epoch', 'session', 'symbols', 'owner_uid'}, 'MANIFEST_FIELDS')
    need(type(manifest['owner_uid']) is int and manifest['owner_uid'] == os.geteuid(), 'MANIFEST_OWNER')
    need(type(manifest['epoch']) is str and _EPOCH.match(manifest['epoch']) and manifest['epoch'] == epoch,
         'MANIFEST_EPOCH')
    need(manifest['session'] == day, 'MANIFEST_SESSION')
    symbols = manifest['symbols']
    need(type(symbols) is list, 'MANIFEST_SYMBOLS')
    need(len(symbols) > 0, 'MANIFEST_SYMBOLS_EMPTY')
    need(len(symbols) <= MAX_SYMBOLS and all(type(s) is str and app.symbol.fullmatch(s) for s in symbols)
         and len(set(symbols)) == len(symbols), 'MANIFEST_SYMBOLS')
    data = app.canonical(manifest)               # sorted keys, compact, ASCII, no trailing newline
    need(0 < len(data) <= MAX_MANIFEST_BYTES and app.load_json(data) == manifest, 'MANIFEST_ENCODING')
    return data


def _persisted(row: dict | None, day: str) -> dict | None:
    """The binding committed by prepare-capacity-day, or None when it is missing."""
    if row is None:
        return None
    state = row['state']
    prepared = state.get('daily_capacity', {}).get(day)
    opened = state.get('sessions', {}).get(day, {}).get('capacity_binding')
    need(opened is None or opened == prepared, 'MANIFEST_BINDING_DIVERGED')
    return prepared


def _restore(ctx: Context, persisted: dict) -> Any:
    return packaged().DailyCapacityBinding.restore(persisted, release=ctx.release, calendar=ctx.calendar,
                                                   authority_verifier=ctx.verify_binding)


def _manifest(ctx: Context, binding: Any, row: dict, day: str, clock: Callable[[], datetime]) -> tuple[bytes, int]:
    manifest = binding.bar_manifest(owner_uid=os.geteuid(), state=row['state'], current_day=day, now=clock(),
                                    calendar=ctx.calendar)
    return manifest_bytes(manifest, day=day, epoch=ctx.release.epoch), len(manifest['symbols'])


def _payload_contract(ctx: Context, day: str) -> dict:
    """The contract of the day's payload file, validated by the packaged contract check."""
    payload = ctx.read_payload(day)
    need(type(payload) is dict and set(payload) == {'contract', 'causal'}, 'CAPACITY_INPUT_FIELDS')
    return packaged().validate_contract(payload['contract'], release=ctx.release, day=day, causal=payload['causal'],
                                        calendar=ctx.calendar)


def _park(opens_at: datetime | None, *, clock, sleep, monotonic, maximum: int) -> float:
    """Sleep until the declared instant. The view file is not read here."""
    began = clock()
    if opens_at is None or began >= opens_at:
        return 0.0
    need((opens_at - began).total_seconds() <= maximum, 'MANIFEST_VETO_WINDOW_NOT_OPEN')
    started = monotonic()
    while True:
        remaining = (opens_at - clock()).total_seconds()
        if remaining <= 0:
            return (clock() - began).total_seconds()
        need(monotonic() - started <= maximum + 1.0, 'MANIFEST_WAIT_CLOCK')
        sleep(min(0.25, max(0.001, remaining)))


def _view(ctx: Context, day: str, opens_at: datetime | None, *, clock, sleep, monotonic) -> tuple[datetime, datetime]:
    """Read the pinned view, only now. A view emitted in-window may arrive a few seconds late."""
    started = monotonic()
    while True:
        try:
            observed, until = ctx.veto_bounds(day)
            break
        except FileNotFoundError:
            code = 'MANIFEST_VETO_VIEW_ABSENT'
        except ValueError as error:
            code = _code(error)
            if code not in VIEW_NOT_YET:
                raise
        need(opens_at is not None and (clock() - opens_at).total_seconds() < VIEW_GRACE_SECONDS
             and monotonic() - started <= VIEW_GRACE_SECONDS + 1.0, code)
        sleep(0.05)
    need(opens_at is None or observed == opens_at, 'MANIFEST_VIEW_ARGUMENT_MISMATCH')
    now = clock()
    need(observed <= now, 'MANIFEST_VETO_WINDOW_NOT_OPEN')
    need(now < until, 'MANIFEST_VETO_WINDOW_MISSED')
    return observed, until


def _gate(ctx: Context, go: dict, plan: dict, *, clock, cutoff: datetime) -> dict:
    """The code-level GO: packaged validator with the real authority, inside window and cutoff."""
    app = packaged()
    now = clock()
    need(now < cutoff, 'MANIFEST_CUTOFF_PASSED')
    result = app.validate_go(go, plan, now=now, authority_verifier=ctx.verify_go)
    after = clock()
    need(now <= after and app.utc(go['not_before']) <= after < app.utc(go['not_after']), 'GO_WINDOW_AFTER_AUTHORITY')
    need(after < cutoff, 'MANIFEST_CUTOFF_PASSED')
    return result


def _outside(target: Path, protected: tuple) -> None:
    """The manifest directory is no configured root, holds none and lies inside none."""
    here = os.path.normpath(str(target))
    for root in protected:
        if root and os.path.isabs(str(root)):
            there = os.path.normpath(str(root))
            need(os.path.commonpath([here, there]) not in (here, there), 'MANIFEST_DIRECTORY_OVERLAP')


def _writable(directory: int) -> None:
    """Could this process create a file here? Asked without writing, before anything is committed."""
    need(os.access('.', os.W_OK | os.X_OK, dir_fd=directory), 'MANIFEST_DIRECTORY_NOT_WRITABLE')
    volume = os.fstatvfs(directory)
    blocks = volume.f_bfree if os.geteuid() == 0 else volume.f_bavail
    need(not volume.f_flag & os.ST_RDONLY and (volume.f_blocks == 0 or blocks > 0)
         and (volume.f_files == 0 or volume.f_ffree > 0), 'MANIFEST_DIRECTORY_NOT_WRITABLE')


def _temporaries(directory: int, name: str) -> tuple[int, list[str]]:
    """Leftover temporaries, read only: (foreign ones, second names of the published inode)."""
    try:
        final = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        final = None
    stale, second = 0, []
    for entry in sorted(os.listdir(directory)):
        if re.match(_TEMPORARY % re.escape(name), entry) is None:
            continue
        info = os.stat(entry, dir_fd=directory, follow_symlinks=False)
        if (final is not None and stat.S_ISREG(info.st_mode)
                and (info.st_dev, info.st_ino) == (final.st_dev, final.st_ino)):
            second.append(entry)
        else:
            stale += 1
    return stale, second


def _repair(directory: int, name: str, second: list[str], data: bytes) -> int:
    """Complete an interrupted publication, and nothing else.

    The extra name is removed only when the file under the final name is a private regular
    file of this uid with exactly two links, the other one being that temporary, and its
    bytes ARE the manifest of the committed binding. Any other two-link file is left exactly
    as it is and refused: removing a name would turn a file the supervisor refuses into one
    it accepts.
    """
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = os.fstat(fd)
        need(len(second) == 1 and stat.S_ISREG(info.st_mode) and info.st_nlink == 2
             and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600,
             'MANIFEST_PUBLICATION_INTERRUPTED')
        other = os.stat(second[0], dir_fd=directory, follow_symlinks=False)
        need((other.st_dev, other.st_ino) == (info.st_dev, info.st_ino), 'MANIFEST_PUBLICATION_INTERRUPTED')
        raw = b''
        while len(raw) <= len(data):
            chunk = os.read(fd, len(data) + 1 - len(raw))
            if not chunk:
                break
            raw += chunk
        need(raw == data, 'MANIFEST_CONFLICT')
    finally:
        os.close(fd)
    os.unlink(second[0], dir_fd=directory)          # changes no content: the link count goes from 2 to 1
    os.fsync(directory)
    return 1


def _existing(target: Path, directory: int, name: str) -> bytes | None:
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None
    try:
        return packaged().private_bytes(target / name, MAX_MANIFEST_BYTES)   # the supervisor's own reader
    except Exception:
        raise Refused('MANIFEST_EXISTING_UNVERIFIED') from None


@contextmanager
def _reserved(directory: int, name: str) -> Iterator[tuple[str, int]]:
    """The private temporary, created exclusively and empty BEFORE anything is committed.

    A directory that cannot take a new file fails here, with no binding committed by this
    run. Whatever happens next, the temporary name is removed on the way out.
    """
    temporary = '.' + name + '.' + secrets.token_hex(8) + '.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        try:
            os.fchmod(fd, 0o600)
            yield temporary, fd
        finally:
            os.close(fd)
    finally:
        os.unlink(temporary, dir_fd=directory)
        os.fsync(directory)


def _publish(directory: int, name: str, temporary: str, fd: int, data: bytes, *,
             before_link: Callable[[], Any], linked: Callable[[], None]) -> bool:
    """Exclusive, all-or-nothing publication from the reserved temporary. False: another writer won the name."""
    view = memoryview(data)
    while view:
        count = os.write(fd, view)
        need(count > 0, 'MANIFEST_WRITE_FAILED')
        view = view[count:]
    os.fsync(fd)
    info = os.fstat(fd)
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
         and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == len(data), 'MANIFEST_WRITE_FAILED')
    before_link()                                   # authority is rechecked after the last slow step
    try:
        os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
    except FileExistsError:
        return False
    linked()
    return True


def _verified(receipt: dict, directory: int, name: str, *, day: str, existing: bytes, data: bytes, binding: Any,
              count: int, status: str) -> int:
    """The private file equals the manifest of the committed binding: record it."""
    need(existing == data, 'MANIFEST_CONFLICT')
    readback = packaged().load_json(existing)       # the supervisor's parse and its two checks
    need(readback.get('session') == day and readback.get('owner_uid') == os.geteuid(), 'MANIFEST_READBACK_FAILED')
    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
    need(info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.geteuid(),
         'MANIFEST_READBACK_FAILED')
    if status == 'ALREADY_PUBLISHED_VERIFIED':
        # A publish run that did not create the name itself: the run that did may have died
        # before its directory fsync. Changes nothing; --verify-only never comes here.
        os.fsync(directory)
    receipt.update(binding_sha256=binding.sha, symbol_count=count, manifest_sha256=hashlib.sha256(data).hexdigest())
    receipt['file'] = {'uid': info.st_uid, 'gid': info.st_gid, 'mode': '%04o' % stat.S_IMODE(info.st_mode),
                       'nlink': info.st_nlink, 'device': info.st_dev, 'inode': info.st_ino,
                       'size_within_limit': 0 < info.st_size <= MAX_MANIFEST_BYTES}
    receipt['status'] = status
    return EXIT_OK


def _window(go: dict) -> dict:
    return {'not_before': go['not_before'], 'not_after': go['not_after']}


def _preflight(ctx: Context, receipt: dict, *, day: str, directory: Path | None, expect_sha: str | None,
               view_opens_at: datetime | None, today: bool, now: datetime, cutoff: datetime,
               require_go_mode: str | None) -> int:
    """Context only: no wait, no prepare, no write, no veto view."""
    row = ctx.read_state()
    persisted = _persisted(row, day)
    need(expect_sha is None or persisted is None or persisted.get('sha') == expect_sha,
         'MANIFEST_BINDING_SHA_MISMATCH')
    ctx.verify_chain(day)
    need(ctx.view_pinned(day), 'CAPACITY_VETO_DAY_UNBOUND')
    checks = {'state_row_present': row is not None, 'binding_committed': persisted is not None,
              'act_b_chain_verified': True, 'veto_view_pinned': True, 'day_is_today': today,
              'before_cutoff': now < cutoff, 'directory_checked': False}
    plans = {}
    if persisted is None:
        need(ctx.prepare is not None, 'MANIFEST_PREPARE_MISSING')
        contract = _payload_contract(ctx, day)
        checks['payload_contract_valid'] = True
        plans[ADMISSION] = contract['assembler_plan']
    else:
        contract = _restore(ctx, persisted).document['contract']
        checks['binding_restored'] = True
    plans[PHASE] = contract['consumer_plans'][PHASE]
    windows, files = {}, {}
    for phase, plan in sorted(plans.items()):
        files[phase] = ctx.read_go(day, phase)
        before, after = static_go(files[phase], plan, day=day, phase=phase)
        need(view_opens_at is None or before <= view_opens_at < after, 'MANIFEST_GO_WINDOW_VIEW')
        windows[phase] = _window(files[phase])
    need(require_go_mode is None or files[PHASE]['mode'] == require_go_mode, 'MANIFEST_GO_MODE')
    for phase, file in files.items():
        ctx.check_go(file, plans[phase])
    need(view_opens_at is None or view_opens_at < cutoff, 'MANIFEST_CUTOFF_PASSED')
    checks['go_files_valid'] = sorted(windows)
    if directory is not None:
        target = Path(directory)
        need(target.is_absolute(), 'MANIFEST_DIRECTORY_INVALID')
        _outside(target, ctx.protected)
        handle = packaged().open_directory(target)   # private leaf, no symbolic link in any component
        try:
            need(os.fstat(handle).st_uid == os.geteuid(), 'MANIFEST_DIRECTORY_OWNER')
            _writable(handle)                        # asked, not tried: this mode writes nothing
            stale, second = _temporaries(handle, day + '.json')
            present = bool(second) or _existing(target, handle, day + '.json') is not None
            checks.update(directory_checked=True, directory_writable=True, stale_temporaries=stale,
                          publication_interrupted=bool(second), manifest_present=present)
        finally:
            os.close(handle)
    receipt.update(checks=checks, windows=windows, status='PREFLIGHT_OK')
    return EXIT_OK


def run(ctx: Context, receipt: dict, *, day: str, directory: Path | None = None, verify_only: bool = False,
        preflight: bool = False, expect_sha: str | None = None, view_opens_at: datetime | None = None,
        max_wait: int = 0, require_go_mode: str | None = None, clock: Callable[[], datetime],
        sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic) -> int:
    app = packaged()
    receipt.update(epoch=ctx.release.epoch, owner_uid=os.geteuid(), **ctx.pins)
    parsed = date.fromisoformat(day)
    need(ctx.calendar.is_session(parsed), 'MANIFEST_DAY_NOT_SESSION')
    cutoff = ctx.calendar.details(parsed)['open'] - CUTOFF_BEFORE_OPEN
    receipt['cutoff_at'] = cutoff.isoformat()
    now = clock()
    today = now.astimezone(app.NEW_YORK).date() == parsed
    if preflight:
        return _preflight(ctx, receipt, day=day, directory=directory, expect_sha=expect_sha,
                          view_opens_at=view_opens_at, today=today, now=now, cutoff=cutoff,
                          require_go_mode=require_go_mode)

    # ---- pre-flight: everything below runs before prepare, and most of it before the wait ----
    need(directory is not None and Path(directory).is_absolute(), 'MANIFEST_DIRECTORY_INVALID')
    target, name = Path(directory), day + '.json'
    _outside(target, ctx.protected)
    if not verify_only:
        need(today, 'MANIFEST_DAY_NOT_TODAY')
        # From the cutoff on, a publishing run does nothing at all: no repair, no publication.
        need(now < cutoff and (view_opens_at is None or view_opens_at < cutoff), 'MANIFEST_CUTOFF_PASSED')
    row = ctx.read_state()
    persisted = _persisted(row, day)
    need(expect_sha is None or persisted is None or persisted.get('sha') == expect_sha,
         'MANIFEST_BINDING_SHA_MISMATCH')
    handle = app.open_directory(target)             # private leaf, no symbolic link in any component
    try:
        need(os.fstat(handle).st_uid == os.geteuid(), 'MANIFEST_DIRECTORY_OWNER')
        if not verify_only:
            _writable(handle)                       # before the wait, and long before the commit
        stale, second = _temporaries(handle, name)  # read only
        receipt.update(stale_temporaries=stale, repaired_temporaries=0)
        # Only the publication of a committed binding is completed (below, once its bytes are
        # known), and never by a readback.
        need(not second or (persisted is not None and not verify_only),
             'MANIFEST_PUBLICATION_INTERRUPTED' if persisted is not None or verify_only
             else 'MANIFEST_EXISTING_WITHOUT_BINDING')
        existing = None if second else _existing(target, handle, name)

        if verify_only:
            need(persisted is not None, 'MANIFEST_PREPARE_MISSING')
            binding = _restore(ctx, persisted)
            data, count = _manifest(ctx, binding, row, day, clock)
            if existing is None:
                receipt.update(status='ABSENT', code='MANIFEST_ABSENT')
                return EXIT_REFUSED
            return _verified(receipt, handle, name, day=day, existing=existing, data=data, binding=binding,
                             count=count, status='MATCH_VERIFIED')

        windows, files = [], []
        if persisted is None:
            need(ctx.prepare is not None, 'MANIFEST_PREPARE_MISSING')
            # A manifest can only come from a committed binding: a file without one is foreign.
            need(existing is None, 'MANIFEST_EXISTING_WITHOUT_BINDING')
            contract = _payload_contract(ctx, day)
            files.append((ctx.read_go(day, ADMISSION), contract['assembler_plan']))
            windows.append(static_go(files[0][0], files[0][1], day=day, phase=ADMISSION))
        else:
            receipt['prepare_status'] = 'PRECOMMITTED'
            binding = _restore(ctx, persisted)
            data, count = _manifest(ctx, binding, row, day, clock)
            if second:
                # The one write that needs no bar_manifest GO, and only now: the binding is
                # restored and _repair compares the file's bytes with its manifest first.
                receipt['repaired_temporaries'] = _repair(handle, name, second, data)
                existing = _existing(target, handle, name)
            if existing is not None:                # nothing to publish: no GO, no view, no wait
                return _verified(receipt, handle, name, day=day, existing=existing, data=data, binding=binding,
                                 count=count, status='ALREADY_PUBLISHED_VERIFIED')
            contract = binding.document['contract']
        plan = contract['consumer_plans'][PHASE]
        go = ctx.read_go(day, PHASE)
        windows.append(static_go(go, plan, day=day, phase=PHASE))
        need(require_go_mode is None or go['mode'] == require_go_mode, 'MANIFEST_GO_MODE')
        ctx.verify_chain(day)
        need(ctx.view_pinned(day), 'CAPACITY_VETO_DAY_UNBOUND')
        for file, proposal in files + [(go, plan)]:
            ctx.check_go(file, proposal)
        need(view_opens_at is None or all(before <= view_opens_at < after for before, after in windows),
             'MANIFEST_GO_WINDOW_VIEW')

        # ---- the veto view: park on the declared instant, then read the pinned file ----
        receipt['waited_seconds'] = round(_park(view_opens_at, clock=clock, sleep=sleep, monotonic=monotonic,
                                                maximum=max_wait), 3)
        observed, until = _view(ctx, day, view_opens_at, clock=clock, sleep=sleep, monotonic=monotonic)
        receipt['view'] = {'observed_at': observed.isoformat(), 'valid_until': until.isoformat()}
        need(all(before <= observed and until <= after for before, after in windows), 'MANIFEST_GO_WINDOW_VIEW')

        # ---- first gate: the bar_manifest GO, in full, before anything is committed ----
        checked = _gate(ctx, go, plan, clock=clock, cutoff=cutoff)
        receipt.update(go_sha256=checked['go_sha'], go_mode=go['mode'], template_sha256=go['template_sha'],
                       window=_window(go))

        def linked() -> None:
            # The name exists from here on. Until the readback it is not reported as verified.
            receipt.update(status='PUBLISHED_UNVERIFIED', published_at=clock().isoformat())

        # The temporary exists before prepare: a directory that refuses a new file stops the
        # run here, with nothing committed.
        with _reserved(handle, name) as (temporary, fd):
            if persisted is None:
                # From this line on the binding may be committed, whatever prepare returns or raises.
                receipt['prepare_status'] = 'ATTEMPTED'
                prepared = ctx.prepare(day)         # prepare-capacity-day, through the packaged code
                need(type(prepared) is dict and prepared.get('status') in ('COMMITTED', 'ALREADY_COMMITTED')
                     and app.is_sha(prepared.get('sha')), 'MANIFEST_PREPARE_FAILED')
                receipt['prepare_status'] = prepared['status']
                row = ctx.read_state()
                persisted = _persisted(row, day)
                need(persisted is not None and persisted.get('sha') == prepared['sha'],
                     'MANIFEST_PREPARE_UNCONFIRMED')
                binding = _restore(ctx, persisted)
                receipt['binding_sha256'] = binding.sha
                need(expect_sha is None or binding.sha == expect_sha, 'MANIFEST_BINDING_SHA_MISMATCH')
                need(binding.document['contract'] == contract, 'MANIFEST_CONTRACT_DIVERGED')
                plan = binding.document['contract']['consumer_plans'][PHASE]
                data, count = _manifest(ctx, binding, row, day, clock)
            receipt.update(binding_sha256=binding.sha, symbol_count=count,
                           manifest_sha256=hashlib.sha256(data).hexdigest())
            won = _publish(handle, name, temporary, fd, data, linked=linked,
                           before_link=lambda: _gate(ctx, go, plan, clock=clock, cutoff=cutoff))
        existing = _existing(target, handle, name)
        need(existing is not None, 'MANIFEST_READBACK_FAILED')
        return _verified(receipt, handle, name, day=day, existing=existing, data=data, binding=binding, count=count,
                         status='PUBLISHED_VERIFIED' if won else 'ALREADY_PUBLISHED_VERIFIED')
    finally:
        os.close(handle)


def _instant(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise Refused('MANIFEST_ARGUMENTS_INVALID') from None
    need(parsed is None or parsed.utcoffset() is not None, 'MANIFEST_ARGUMENTS_INVALID')
    return None if parsed is None else parsed.astimezone(timezone.utc)


def _session_day(day: Any) -> str | None:
    try:
        return day if type(day) is str and date.fromisoformat(day).isoformat() == day else None
    except ValueError:
        return None


def execute(build: Callable[[], Context], *, day: Any, directory: Any = None, prepare_first: bool = False,
            verify_only: bool = False, preflight: bool = False, expect_sha: Any = None, view_opens_at: Any = None,
            max_wait: Any = 0, require_go_mode: Any = None, clock: Callable[[], datetime],
            sleep: Callable[[float], None] = time.sleep,
            monotonic: Callable[[], float] = time.monotonic) -> tuple[dict, int]:
    """One receipt and one exit code. The arguments are checked before anything is built."""
    mode = 'PREFLIGHT' if preflight else 'VERIFY_ONLY' if verify_only else 'PUBLISH'
    receipt: dict = {'schema': RECEIPT_SCHEMA, 'status': 'REFUSED', 'code': None, 'session': _session_day(day),
                     'mode': mode}
    try:
        need(receipt['session'] is not None, 'MANIFEST_DAY_INVALID')
        need(not (preflight and verify_only), 'MANIFEST_ARGUMENTS_INVALID')
        need(type(max_wait) is int and 0 <= max_wait <= MAX_WAIT_SECONDS, 'MANIFEST_ARGUMENTS_INVALID')
        need(expect_sha is None or (type(expect_sha) is str and _SHA.match(expect_sha)), 'MANIFEST_ARGUMENTS_INVALID')
        need(require_go_mode is None or require_go_mode in GO_MODES, 'MANIFEST_ARGUMENTS_INVALID')
        opens = _instant(view_opens_at)
        # --verify-only is a readback: it never prepares, never waits and reads no GO.
        need(not verify_only or (not prepare_first and opens is None and max_wait == 0 and require_go_mode is None),
             'MANIFEST_ARGUMENTS_INVALID')
        need(preflight or directory is not None, 'MANIFEST_ARGUMENTS_INVALID')
        code = run(build(), receipt, day=day, directory=directory, verify_only=verify_only, preflight=preflight,
                   expect_sha=expect_sha, view_opens_at=opens, max_wait=max_wait, require_go_mode=require_go_mode,
                   clock=clock, sleep=sleep, monotonic=monotonic)
    except Exception as error:
        receipt['code'], code = refusal(error)
        if receipt.get('status') != 'PUBLISHED_UNVERIFIED':
            # After link() the name exists: never report success, never undo, never call it a refusal.
            receipt['status'] = 'REFUSED' if code == EXIT_REFUSED else 'UNVERIFIED'
    return receipt, code


def context(settings: Any, *, now: datetime, prepare_first: bool, clock: Callable[[], datetime]) -> Context:
    """Wire the deployed settings. Nothing is opened, read or connected while OFF."""
    need(getattr(settings, 'r2d2_v2_shadow_enabled', False), 'MANIFEST_SHADOW_OFF')
    need(getattr(settings, 'r2d2_v2_capacity_required', False), 'MANIFEST_CAPACITY_REQUIRED')
    need(bool(getattr(settings, 'database_url', '')), 'PERSISTENT_DATABASE_REQUIRED')
    app = packaged()
    from app.r2d2_v2_document_format import parse_document
    if prepare_first:
        # The collector the worker builds for --prepare-capacity-day: release, capacity config,
        # sources and the journal catalog. It needs the reader's mounts and environment.
        from app.r2d2_v2_capacity_bound import CapacityBoundCollector
        from app.r2d2_v2_capacity_wiring import prepare_capacity_day
        from app.r2d2_v2_shadow_worker import build_collector
        collector = build_collector(settings, now=now)
        need(isinstance(collector, CapacityBoundCollector), 'CAPACITY_CONFIG_REQUIRED')
        authority = collector.capacity_loader.authority
        config, release, calendar, store = authority.config, collector.release, collector.calendar, collector.store
        prepare = lambda day: prepare_capacity_day(store, collector, day)
    else:
        from app.database import Database
        from app.r2d2_v2_calendar import ShadowCalendar
        from app.r2d2_v2_capacity_bootstrap import CapacityConfig
        from app.r2d2_v2_shadow import Release
        from app.r2d2_v2_shadow_worker import _release_bytes
        from app.r2d2_v2_store import PostgresShadowStore
        calendar = ShadowCalendar()
        release = Release.verify(_release_bytes(str(settings.r2d2_v2_shadow_release_file)),
                                 settings.r2d2_v2_shadow_release_sha, now=now, build_sha=settings.build_sha,
                                 calendar=calendar)
        config = CapacityConfig(settings)
        config.release(release)
        authority, store, prepare = config.authority, PostgresShadowStore(Database(settings).connection), None

    def verify_chain(day: str) -> None:
        _coded(lambda: authority.act_b(clock(), epoch=release.epoch, first=release.first_session.isoformat(),
                                       day=day), 'MANIFEST_CHAIN_UNVERIFIED')

    def check_go(go: dict, plan: dict) -> None:
        go_records(authority, go)                   # precise codes first
        static_documents(authority, go, plan)       # then everything verify_go asks, minus the view

    # Every directory the settings and the capacity config name. The manifest directory must
    # be none of them, hold none of them and lie inside none of them.
    restore = config.body.get('restore_revocation')
    protected = [os.path.dirname(str(getattr(settings, 'r2d2_v2_capacity_config_file', '') or '')),
                 os.path.dirname(str(getattr(settings, 'r2d2_v2_shadow_release_file', '') or '')),
                 *(str(getattr(settings, name, '') or '') for name in (
                     'r2d2_v2_massive_journal_dir', 'r2d2_v2_shadow_source_dir', 'r2d2_microstructure_raw_dir')),
                 *(pin['path'] for pin in config.body['roots'].values()),
                 *([restore['root']['path']] if type(restore) is dict else [])]

    def read_go(day: str, phase: str) -> dict:
        def load() -> dict:
            body = config.roots['go'].json('session=' + day + '.' + phase + '.json')
            need(type(body) is dict and set(body) == {'go'}, 'MANIFEST_GO_FIELDS')
            return body['go']
        return _coded(load, 'MANIFEST_GO_INVALID', missing='MANIFEST_GO_MISSING')

    def read_payload(day: str) -> dict:
        return _coded(lambda: config.roots['payload'].json('session=' + day + '.json'),
                      'MANIFEST_PAYLOAD_INVALID', missing='MANIFEST_PAYLOAD_MISSING')

    def view_pinned(day: str) -> bool:
        config.verify()
        return type(config.body['veto_views'].get(day)) is dict

    def veto_bounds(day: str) -> tuple[datetime, datetime]:
        config.verify()
        pin = config.body['veto_views'].get(day)
        need(type(pin) is dict, 'CAPACITY_VETO_DAY_UNBOUND')
        raw = config.roots['documents'].read(pin['file'])
        need(hashlib.sha256(raw).hexdigest() == pin['sha256'], 'VETO_HASH_MISMATCH')
        body = parse_document(raw)['body']
        return app.utc(body['observed_at']), app.utc(body['valid_until'])

    return Context(release=release, calendar=calendar, read_state=lambda: store.read(release.epoch),
                   verify_binding=lambda document: authority.verify_binding(document, clock()),
                   verify_go=lambda go, plan: authority.verify_go(go, plan, clock()),
                   verify_chain=verify_chain, check_go=check_go, read_go=read_go, read_payload=read_payload,
                   view_pinned=view_pinned, veto_bounds=veto_bounds, prepare=prepare, protected=tuple(protected),
                   pins={'release_sha256': release.receipt_sha, 'capacity_config_sha256': config.sha,
                         'package_sha256': release.implementation_package_sha, 'build_sha': settings.build_sha,
                         'capacity_veto_mode': config.veto_mode,
                         'massive_bars_enabled': bool(getattr(settings, 'r2d2_v2_massive_bars_enabled', False))})


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):                  # one JSON line, never argparse's own text
        raise Refused('MANIFEST_ARGUMENTS_INVALID')


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main(argv: list[str] | None = None, *, clock: Callable[[], datetime] = _utcnow,
         sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic) -> int:
    receipt: dict = {'schema': RECEIPT_SCHEMA, 'status': 'REFUSED', 'code': 'MANIFEST_ARGUMENTS_INVALID',
                     'session': None, 'mode': None}
    code = EXIT_REFUSED
    try:
        # No help action: -h is a wrong argument like any other, one JSON line and exit 3.
        parser = _Parser(prog='manifest_writer', allow_abbrev=False, add_help=False)
        parser.add_argument('--day', required=True, help='Session date, YYYY-MM-DD (New York)')
        parser.add_argument('--manifest-directory', type=Path, help='Required unless --preflight')
        parser.add_argument('--prepare-first', action='store_true',
                            help='Commit the capacity binding in this process when it is not committed yet')
        parser.add_argument('--verify-only', action='store_true', help='Compare the file with the binding; never write')
        parser.add_argument('--preflight', action='store_true',
                            help='Context and static validation only; never waits, prepares, writes or reads the view')
        parser.add_argument('--expect-binding-sha', help='SHA of an already accepted prepare-capacity-day')
        parser.add_argument('--view-opens-at', help='observed_at of the pinned veto view, ISO 8601 with offset')
        parser.add_argument('--max-wait-seconds', type=int, default=0,
                            help='Longest parking before --view-opens-at (0-%d)' % MAX_WAIT_SECONDS)
        parser.add_argument('--require-go-mode', choices=GO_MODES,
                            help='Refuse a bar_manifest GO of another mode, before the wait')
        args = parser.parse_args(argv)

        def build() -> Context:
            packaged()
            from app.config import get_settings
            return context(get_settings(), now=clock(), prepare_first=args.prepare_first, clock=clock)

        receipt, code = execute(build, day=args.day, directory=args.manifest_directory,
                                prepare_first=args.prepare_first, verify_only=args.verify_only,
                                preflight=args.preflight, expect_sha=args.expect_binding_sha,
                                view_opens_at=args.view_opens_at, max_wait=args.max_wait_seconds,
                                require_go_mode=args.require_go_mode, clock=clock, sleep=sleep,
                                monotonic=monotonic)
    except Refused:
        pass                                        # the argument refusal prepared above
    sys.stdout.write(json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
    sys.stdout.flush()
    return code


if __name__ == '__main__':
    # Nothing but the receipt line may reach the output: library log records and warnings
    # could carry a connection string or a file name.
    logging.disable(logging.CRITICAL)
    warnings.simplefilter('ignore')
    raise SystemExit(main())
