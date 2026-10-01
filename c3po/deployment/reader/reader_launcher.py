"""Day-bounded parent process of the V2 shadow reader. Deployment script.

This file is NOT part of the pinned implementation package and is not in the image.
It is delivered to the host under its own authorisation (its SHA-256 is in the GO
and in the receipt), mounted read-only into a container of the deployed backend
image and run in isolated mode:

    python -I -B /c3po-reader/reader_launcher.py

It imports the packaged calendar, session list and settings of that image, and runs
the UNMODIFIED worker as a child process:

    python -B -m app.r2d2_v2_shadow_worker

Nothing is ever raised into the worker. A phase ends by SIGTERM to the child, which
has the default disposition there, so the kernel ends it and releases every
descriptor and lock it held.

One process serves one authorised session day (times New York, regular session):

  PRE_OPEN  from the start until 90 s before the open: the worker drains what
            accumulated since the previous stop.
  handover  the child is stopped; nothing polls the catalog while the producer
            creates and prepares the session of the day.
  wait      lock-free look at session_date=<day>/ready.json, until it exists or
            until 10 s before the open, whichever comes first; then one second.
  SESSION   the worker again, until the close plus 20 minutes.

Exit status seen by the unit:
  0   STOPPED: end of day, or SIGTERM/SIGINT to this process
  1   FAILED: the child ended by itself with a failure; restart requested
  78  REFUSED: terminal for this start (day, window, flags, settings, pin, arguments)

Standard output carries one JSON object per line (the notices). Standard error
carries only the worker's own status lines, and only when every string in them
passes the grammar below; everything else the child prints is dropped, counted,
and never copied anywhere. No exception text is ever printed.
"""
from datetime import datetime, timedelta, timezone
import errno
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from zoneinfo import ZoneInfo

# Where the deployed image keeps the application. Isolated mode (-I) puts neither
# the working directory nor the script directory on the import path.
APP_ROOT = '/app'
WORKER_MODULE = 'app.r2d2_v2_shadow_worker'

TERMINAL_EXIT = 78
PRE_OPEN_SECONDS = 6 * 3600
HANDOVER_BEFORE_OPEN_SECONDS = 90
READY_DEADLINE_BEFORE_OPEN_SECONDS = 10
READY_SETTLE_SECONDS = 1.0
READY_POLL_SECONDS = 0.25
STOP_AFTER_CLOSE_SECONDS = 20 * 60
CHILD_TERM_GRACE_SECONDS = 20.0
TICK_SECONDS = 0.25
DRAIN_JOIN_SECONDS = 3.0
MAX_LINE_BYTES = 1024 * 1024
# Optional self-pin, a non-secret line of pins.env. Empty or absent: not pinned.
LAUNCHER_PIN_ENV = 'C3PO_READER_LAUNCHER_SHA256'

NEW_YORK = ZoneInfo('America/New_York')
# The exact prefix logging.basicConfig gives the worker's logger.info("V2 status %s", ...)
# when the module runs as __main__ (app/r2d2_v2_shadow_worker.py).
STATUS_PREFIX = 'INFO:__main__:V2 status '
STATUS_SCHEMA = 'R2D2_V2_COLLECTOR_STATUS_V2'
CODE_CLASSES = frozenset(('ShadowIntegrityError', 'SourceUnavailable'))

_HASH = r'[0-9a-f]{40}|[0-9a-f]{64}'
_CLOCK = r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2}))?'
# A constant code carries an underscore; the instrument symbol grammar cannot.
_CODE = r'[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+_?'
_EPOCH = r'R2D2-V2-(?:SHADOW|DIAG)-[A-Za-z0-9_-]{1,80}'
_PLAIN = r'CERTIFIED|DIAGNOSTIC|ELIGIBLE|CONTROL|UNASSIGNED'
_SAFE_VALUE = re.compile('|'.join((_HASH, _CLOCK, _CODE, _EPOCH, _PLAIN)))
_SAFE_KEY = re.compile('|'.join((r'[a-z][a-z0-9_]*', _CLOCK, _CODE, _PLAIN)))
_CLASS_LINE = re.compile(r'((?:[A-Za-z_][A-Za-z0-9_]*\.)*)([A-Za-z_][A-Za-z0-9_]{0,79})(?:: (.*))?')
_FAILURE_CODE = re.compile(r'[A-Z][A-Z0-9_]{0,63}')
_ERRNO = re.compile(r'\[Errno (\d{1,4})\]')


class _Stop:
    requested = False


def _request_stop(signum, frame):
    _Stop.requested = True


def install_signal_handlers():
    """SIGTERM and SIGINT only set a flag; the main loop reads it at every tick."""
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, _request_stop)


def _safe(value):
    """True when no string of a decoded status could be a symbol, a path or free text."""
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, str):
        return _SAFE_VALUE.fullmatch(value) is not None
    if isinstance(value, list):
        return all(_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _SAFE_KEY.fullmatch(key) is not None and _safe(item)
                   for key, item in value.items())
    return False


def safe_status(body):
    try:
        decoded = json.loads(body)
        return isinstance(decoded, dict) and decoded.get('schema') == STATUS_SCHEMA and _safe(decoded)
    except (ValueError, RecursionError):
        return False


class OutputFilter:
    """Decides, line by line, what of the child's output may leave this process."""

    def __init__(self):
        self.forwarded = self.withheld = self.dropped = 0
        self._after_header = False
        self._failure = {}

    def feed(self, line):
        """The line itself when it is a status line that passes the grammar, else None."""
        if line.startswith(STATUS_PREFIX):
            if safe_status(line[len(STATUS_PREFIX):]):
                self.forwarded += 1
                return line
            self.withheld += 1
            return None
        self.dropped += 1
        self._traceback(line)
        return None

    def _traceback(self, line):
        if line.startswith('Traceback (most recent call last):'):
            self._after_header, self._failure = True, {}
            return
        if not self._after_header or not line or line[0].isspace():
            return
        self._after_header = False
        match = _CLASS_LINE.fullmatch(line)
        if match is None:
            return
        name, text = match.group(2), match.group(3) or ''
        failure = {'error': name}
        if name in CODE_CLASSES and '_' in text and _FAILURE_CODE.fullmatch(text) is not None:
            failure['code'] = text
        number = _ERRNO.match(text)
        if number is not None and int(number.group(1)) in errno.errorcode:
            failure['errno'] = errno.errorcode[int(number.group(1))]
        self._failure = failure

    def failure(self):
        """Class name of the last traceback, its constant code or errno name. Never its text."""
        return dict(self._failure)

    def counts(self):
        return {'status_lines': self.forwarded, 'status_withheld': self.withheld, 'dropped_lines': self.dropped}


class WorkerChild:
    """The worker as a child process. Both of its streams end in one filtered pipe."""

    def __init__(self, argv, *, cwd, forward, on_withheld=None):
        self.filter = OutputFilter()
        self._forward, self._on_withheld = forward, on_withheld
        self._closed = False
        self.process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, close_fds=True)
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self):
        stream = self.process.stdout
        while True:
            try:
                raw = stream.readline(MAX_LINE_BYTES + 1)
                if not raw:
                    return
                if not raw.endswith(b'\n') and len(raw) > MAX_LINE_BYTES:
                    self.filter.dropped += 1
                    while raw and not raw.endswith(b'\n'):
                        raw = stream.readline(MAX_LINE_BYTES + 1)
                    continue
            except (OSError, ValueError):
                return  # the pipe is gone
            try:
                before = self.filter.withheld
                line = self.filter.feed(raw.decode('utf-8', 'replace').rstrip('\r\n'))
                if line is not None:
                    self._forward(line)
                elif before == 0 and self.filter.withheld == 1 and self._on_withheld is not None:
                    self._on_withheld()
            except Exception:
                # A failure to write must never stop the drain: a full pipe would stall the child.
                continue

    def poll(self):
        return self.process.poll()

    def stop(self, grace=CHILD_TERM_GRACE_SECONDS):
        """SIGTERM, wait, SIGKILL after the grace. (exit status, ended by this signal, killed)."""
        process = self.process
        if process.poll() is not None:
            return process.returncode, False, False
        process.terminate()
        killed = False
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            process.kill()
            killed = True
            process.wait()
        code = process.returncode
        return code, code == -signal.SIGTERM or (killed and code == -signal.SIGKILL), killed

    def close(self):
        """Idempotent. Never leaves the child running; waits for the last lines."""
        if self._closed:
            return
        self._closed = True
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        self._thread.join(DRAIN_JOIN_SECONDS)
        if not self._thread.is_alive():
            self.process.stdout.close()

    def failure(self):
        return self.filter.failure()

    def counts(self):
        return self.filter.counts()


def ready_marker(journal_dir, day):
    """Lock-free existence check; the catalog lock belongs to the producer and the worker."""
    try:
        info = os.stat(os.path.join(journal_dir, 'session_date=' + day, 'ready.json'), follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode)


def _hex(value, length):
    return value if isinstance(value, str) and re.fullmatch('[0-9a-f]{%d}' % length, value) else None


def _ended(code, killed):
    name = None
    if code is not None and code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = 'UNKNOWN_SIGNAL'
    return {'child_exit': code if code is not None and code >= 0 else None, 'child_signal': name, 'killed': killed}


def supervise(*, utcnow, sleep, notice, spawn, calendar, sessions, settings, stop_requested,
              ready=ready_marker, launcher_sha=None, launcher_pin=''):
    """One authorised day. `spawn(phase)` returns the running child of that phase."""
    now = utcnow()
    day = now.astimezone(NEW_YORK).date()
    key = day.isoformat()

    def say(status, **fields):
        notice({'status': status, 'session': key, 'at': utcnow().isoformat(), **fields})

    def refuse(code):
        say('REFUSED', code=code, restart_allowed=False)
        return TERMINAL_EXIT

    if launcher_pin and launcher_pin != launcher_sha:
        return refuse('READER_LAUNCHER_PIN')
    # Day and window come first: outside them no setting, file or database is read.
    if key not in sessions or not calendar.is_session(day):
        return refuse('READER_SESSION')
    details = calendar.details(day)
    handover = details['open'] - timedelta(seconds=HANDOVER_BEFORE_OPEN_SECONDS)
    ready_deadline = details['open'] - timedelta(seconds=READY_DEADLINE_BEFORE_OPEN_SECONDS)
    stop_at = details['close'] + timedelta(seconds=STOP_AFTER_CLOSE_SECONDS)
    if not details['open'] - timedelta(seconds=PRE_OPEN_SECONDS) <= now < stop_at:
        return refuse('READER_WINDOW')
    try:
        current = settings()
    except Exception:
        return refuse('READER_SETTINGS_INVALID')
    if current.r2d2_v2_shadow_enabled is not True or current.r2d2_v2_massive_bars_enabled is not True:
        return refuse('READER_DISABLED')
    journal = str(current.r2d2_v2_massive_journal_dir)
    if not os.path.isabs(journal):
        return refuse('READER_JOURNAL_DIR')
    pins = {'build_sha': _hex(current.build_sha, 40), 'release_sha': _hex(current.r2d2_v2_shadow_release_sha, 64),
            'capacity_required': current.r2d2_v2_capacity_required is True,
            'capacity_config_sha': _hex(current.r2d2_v2_capacity_config_sha, 64),
            'launcher_sha256': _hex(launcher_sha, 64), 'launcher_pinned': bool(launcher_pin)}

    def run_phase(phase, until):
        """('EXIT', status) when this process must end, ('PHASE_END', fields) at the phase's own end."""
        say('STARTING', phase=phase, until=until.isoformat(), **pins)
        child = spawn(phase)
        try:
            while True:
                if stop_requested():
                    code, _, killed = child.stop()
                    child.close()
                    say('STOPPED', reason='SIGNAL', phase=phase, **_ended(code, killed), **child.counts())
                    return 'EXIT', 0
                code = child.poll()
                if code is None and utcnow() >= until:
                    code, by_parent, killed = child.stop()
                    if by_parent:
                        child.close()
                        return 'PHASE_END', {**_ended(code, killed), **child.counts()}
                if code is not None:
                    # The child ended by itself. Its own exit 0 means it printed OFF.
                    child.close()
                    if code == 0:
                        say('REFUSED', code='READER_DISABLED', phase=phase, restart_allowed=False)
                        return 'EXIT', TERMINAL_EXIT
                    say('FAILED', phase=phase, restart_allowed=True, **_ended(code, False), **child.failure(),
                        **child.counts())
                    return 'EXIT', 1
                sleep(TICK_SECONDS)
        finally:
            child.close()

    if stop_requested():
        say('STOPPED', reason='SIGNAL', phase='START')
        return 0
    if utcnow() < handover:
        outcome, value = run_phase('PRE_OPEN', handover)
        if outcome == 'EXIT':
            return value
        say('HANDOVER', **value)
    started = utcnow()
    observed = ready(journal, key)
    while not observed and utcnow() < ready_deadline:
        if stop_requested():
            say('STOPPED', reason='SIGNAL', phase='READY_WAIT')
            return 0
        sleep(READY_POLL_SECONDS)
        observed = ready(journal, key)
    say('READY_OBSERVED' if observed else 'READY_NOT_OBSERVED',
        waited_seconds=round((utcnow() - started).total_seconds(), 3))
    sleep(READY_SETTLE_SECONDS)
    if stop_requested():
        say('STOPPED', reason='SIGNAL', phase='READY_WAIT')
        return 0
    outcome, value = run_phase('SESSION', stop_at)
    if outcome == 'EXIT':
        return value
    say('STOPPED', reason='END_OF_DAY', phase='SESSION', **value)
    return 0


def own_sha256():
    """SHA-256 of this file as mounted. None when the program arrived on standard input."""
    try:
        with open(__file__, 'rb') as stream:
            return hashlib.sha256(stream.read()).hexdigest()
    except (NameError, OSError):
        return None


def worker_argv():
    return [sys.executable, '-B', '-m', WORKER_MODULE]


def main(argv=None, *, utcnow=None, child_argv=None):
    """`utcnow` and `child_argv` are test seams; the unit passes neither, and no argument."""
    install_signal_handlers()
    lock = threading.Lock()
    utcnow = utcnow or (lambda: datetime.now(timezone.utc))

    def notice(event):
        try:
            with lock:
                print(json.dumps(event, sort_keys=True), flush=True)
        except OSError:
            pass

    def forward(line):
        with lock:
            print(line, file=sys.stderr, flush=True)

    def spawn(phase):
        return WorkerChild(child_argv or worker_argv(), cwd=APP_ROOT, forward=forward,
                           on_withheld=lambda: notice({'status': 'STATUS_WITHHELD', 'phase': phase,
                               'code': 'READER_STATUS_GRAMMAR', 'at': utcnow().isoformat(),
                               'session': utcnow().astimezone(NEW_YORK).date().isoformat()}))

    def settings():
        from app.config import get_settings
        return get_settings()

    if (sys.argv[1:] if argv is None else argv):
        notice({'status': 'REFUSED', 'code': 'READER_ARGUMENTS', 'restart_allowed': False, 'at': utcnow().isoformat()})
        return TERMINAL_EXIT
    try:
        if APP_ROOT not in sys.path:
            sys.path.insert(0, APP_ROOT)
        from app.r2d2_v2_calendar import ShadowCalendar
        from app.r2d2_v2_epoch_assembler import SESSIONS
        return supervise(utcnow=utcnow, sleep=time.sleep, notice=notice, spawn=spawn, calendar=ShadowCalendar(),
            sessions=SESSIONS, settings=settings, stop_requested=lambda: _Stop.requested,
            launcher_sha=own_sha256(), launcher_pin=os.environ.get(LAUNCHER_PIN_ENV, ''))
    except Exception as error:
        # This process's own failure (an import, the calendar, a spawn). Class name only.
        name = type(error).__name__
        event = {'status': 'FAILED', 'phase': 'LAUNCHER', 'error': name, 'restart_allowed': True,
                 'at': utcnow().isoformat()}
        text = error.args[0] if len(error.args) == 1 and type(error.args[0]) is str else ''
        if name in CODE_CLASSES and '_' in text and _FAILURE_CODE.fullmatch(text) is not None:
            event['code'] = text
        if isinstance(error, OSError) and error.errno in errno.errorcode:
            event['errno'] = errno.errorcode[error.errno]
        notice(event)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
