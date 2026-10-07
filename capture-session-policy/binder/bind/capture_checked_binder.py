"""Linux-only same-process guard, external measurement and approval pins required.

An operator supplying arbitrary hashes does not create owner authority. This tool
is usable only under the separately signed dated workflow authority. It never
measures its own acceptance and never converts a measurement into PASS.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

HELPER = '796ec07043f628b96bfdab20e5103567a70cc62c15f3ee63ce74ea36f6a0e2d6'
BINDER = '9dbff222a3f815573d0cf89686f16a841260831400da40c5055999d7c71af133'
REGISTRY = '78eb4ab25db448d677b5c54bb2f91346c194427fee88028260d1ba2f7be50d72'

def need(ok, code):
    if not ok:
        raise ValueError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path, limit=32*1024*1024, pin=None):
    p = Path(path)
    need(p.is_absolute(), 'CAPTURE_RUNTIME_RELATIVE_PATH')
    for part in (p, *p.parents):
        need(not part.is_symlink(), 'CAPTURE_RUNTIME_LINK')
    fd = os.open(str(p), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        first = os.fstat(stream.fileno())
        need(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and not first.st_mode & 0o022
             and first.st_size <= limit, 'CAPTURE_RUNTIME_FILE')
        raw = stream.read(limit+1)
        last = os.fstat(stream.fileno())
    def identity(s):
        return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns
    need(identity(first) == identity(last) == identity(p.lstat()) and len(raw) == first.st_size,
         'CAPTURE_RUNTIME_FILE_CHANGED')
    if pin is not None:
        need(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) and sha(raw) == pin,
             'CAPTURE_RUNTIME_EXTERNAL_PIN')
    return raw

def strict(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'CAPTURE_RUNTIME_DUPLICATE_FIELD')
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: need(False, 'CAPTURE_RUNTIME_NONFINITE'))

def approval(value, measurement_sha, measured, now, current_run):
    need(value.get('schema') == 'CAPTURE_LINUX_RUNTIME_APPROVAL_V2'
         and value.get('session') == '2026-10-08' and value.get('run_id') == current_run
         and type(value.get('run_attempt')) is int and value['run_attempt'] == 1
         and value.get('verdict') == 'PASS_PHYSICAL_RUNTIME'
         and value.get('measurement_sha256') == measurement_sha
         and value.get('runtime_guard_sha256') == HELPER
         and value.get('binder_sha256') == BINDER and value.get('accepted_seals_sha256') == REGISTRY,
         'CAPTURE_RUNTIME_APPROVAL_SCOPE')
    for field in ('review_body_sha256', 'dated_authority_sha256'):
        need(type(value.get(field)) is str and re.fullmatch('[0-9a-f]{64}', value[field])
             and value[field] != '0'*64, 'CAPTURE_RUNTIME_REVIEW_AUTHORITY_PIN')
    observed = dt.datetime.fromisoformat(value['measured_at_utc'].replace('Z', '+00:00'))
    reviewed = dt.datetime.fromisoformat(value['reviewed_at_utc'].replace('Z', '+00:00'))
    need(observed.tzinfo == reviewed.tzinfo == dt.timezone.utc and observed <= reviewed <= now
         and observed.date().isoformat() == '2026-10-08', 'CAPTURE_RUNTIME_ORDER')
    need(measured.get('runtime_guard_sha256') == HELPER, 'CAPTURE_RUNTIME_MEASUREMENT_GUARD')

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--measurement', required=True)
    parser.add_argument('--measurement-sha256', required=True)
    parser.add_argument('--approval', required=True)
    parser.add_argument('--approval-sha256', required=True)
    parser.add_argument('--check-runtime', action='store_true')
    parser.add_argument('binder_args', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    home = Path(__file__).resolve().parent
    try:
        need(sys.platform == 'linux' and os.geteuid() != 0 and os.environ.get('GITHUB_RUN_ATTEMPT') == '1'
             and re.fullmatch('[1-9][0-9]{5,19}', os.environ.get('GITHUB_RUN_ID', '')), 'CAPTURE_RUNTIME_ACTUAL_JOB')
        now = dt.datetime.now(dt.timezone.utc)
        need(now.date().isoformat() == '2026-10-08', 'CAPTURE_RUNTIME_DATE')
        raw = read(args.measurement, pin=args.measurement_sha256)
        expected = strict(raw)
        accepted = strict(read(args.approval, pin=args.approval_sha256))
        approval(accepted, sha(raw), expected, now, os.environ['GITHUB_RUN_ID'])
        helper = read(str(home/'runtime_identity.py'), pin=HELPER)
        module = types.ModuleType('runtime_identity')
        module.__file__ = str(home/'runtime_identity.py')
        sys.modules['runtime_identity'] = module
        exec(compile(helper, module.__file__, 'exec'), module.__dict__)
        observed = module.observe(home.parents[1], (home/'runtime_identity.py',), expected=expected)
        verdict = module.compare(expected, observed)
        source = read(str(home/'bind_once.py'), pin=BINDER)
        read(str(home/'ACCEPTED_SEALS.json'), pin=REGISTRY)
        if args.check_runtime:
            need(not args.binder_args, 'CAPTURE_RUNTIME_CHECK_ARGUMENTS')
            print(json.dumps(verdict, sort_keys=True))
            return 0
        need(args.binder_args[:1] == ['--'] and len(args.binder_args) > 1, 'CAPTURE_RUNTIME_BINDER_ARGUMENTS')
        sys.argv = [str(home/'bind_once.py')] + args.binder_args[1:]
    except Exception:
        print('{"status":"REFUSED_CAPTURE_RUNTIME","operational_READY":false}')
        return 2
    scope = {'__name__': '__main__', '__file__': str(home/'bind_once.py'), '__package__': None,
             '__builtins__': __builtins__}
    exec(compile(source, str(home/'bind_once.py'), 'exec'), scope)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
