"""Explicit measurement only. Never calls prepare, never turns its output into acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import types


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    home = Path(__file__).resolve().parent
    helper = (home / 'runtime_identity.py').read_bytes()
    module = types.ModuleType('runtime_identity')
    module.__file__ = str(home / 'runtime_identity.py')
    sys.modules['runtime_identity'] = module
    exec(compile(helper, module.__file__, 'exec'), module.__dict__)
    module.need(module.sha(module.read_regular(home/'bind_once.py')) == module.BINDER_SHA256,
                'RUNTIME_BINDER_BYTES')
    module.need(module.sha(module.read_regular(home/'ACCEPTED_SEALS.json')) == module.ACCEPTED_SHA256,
                'RUNTIME_ACCEPTANCE_BYTES')
    observed = module.observe(home.parents[1], (home / 'runtime_identity.py',))
    observed['runtime_guard_sha256'] = hashlib.sha256(helper).hexdigest()
    observed['measurement_is_not_acceptance'] = True
    destination = Path(args.output)
    with destination.open('xb') as out:
        out.write((json.dumps(observed, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps({'status': 'MEASURED_NOT_ACCEPTED',
                      'identity_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                      'host_proof': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
