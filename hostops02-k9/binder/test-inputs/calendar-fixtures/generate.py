"""Offline SYNTHETIC supplements; real pinned day tool, never operational documents.

The historical signed-chain helper is unavailable. Reuse the published synthetic
chain, templates and sessions byte for byte; replace only the unsigned epoch's
calendar_pin_receipt via the real tool API, then regenerate every downstream byte.
Run once per exact exchange_calendars version. Tests never run this generator.
"""
import argparse
import base64
import copy
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

TOOL_SHA = '888a48e6654aff90e2f305b410ea6c5614485e5ac778354ba721b790bfead183'
CONFIG_SHA = '91619929a513074f2eee01a6bcd78342305e0066e61ac79f2afd087c2e035897'
HISTORICAL_HELPER_SHA = '70ef5cf4bb08b1895d4bf4af4be47ea67a021fe23d9fa874111cbf3241def92e'
PINS = {'4.2.8': '31654118a9d5ed9b04f81a434b773514dc06b79bfd499a299ea6d3a7d802e72d',
        '4.13.2': '46777dde9fb7a2289d67e95467351380d8c22c8994ca21adf8cb618a7a67db8c'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=1, sort_keys=True) + '\n', encoding='ascii')


def hashes(root):
    return {str(path.relative_to(root)): sha(path.read_bytes())
            for path in sorted(root.rglob('*')) if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, runtime, target = args.source.resolve(), args.runtime.resolve(), args.output.resolve()
    version = importlib.metadata.version('exchange_calendars')
    assert version in PINS, 'exact supported calendar dependency required'
    assert target.name == version and not target.exists(), 'new version-specific output only'
    tool_path = runtime / 'c3po/deployment/capacity-day/capacity_day_documents.py'
    assert sha(tool_path.read_bytes()) == TOOL_SHA
    assert sha((runtime / 'c3po/backend/app/config.py').read_bytes()) == CONFIG_SHA
    # Every listed runtime file must equal the published verifier bundle. The one
    # missing dependency is the explicitly hashed config supplied by the runner.
    runtime_manifest = (source.parent / 'bind/k8_verifier/SHA256SUMS').read_bytes()
    for line in runtime_manifest.decode('ascii').splitlines():
        digest, name = line.split('  ', 1)
        assert sha((runtime / name).read_bytes()) == digest, name
    original = hashes(source)
    spec = importlib.util.spec_from_file_location('synthetic_calendar_day_tool', tool_path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    receipt = tool.calendar_receipt(tool.app())
    assert receipt['calendar_version'] == version and receipt['calendar_pin_sha'] == PINS[version]
    target.mkdir(parents=True)
    logs = target / 'generation-logs'
    logs.mkdir()
    provenance = {'schema': 'BINDER_SYNTHETIC_CALENDAR_FIXTURE_PROVENANCE_V1', 'synthetic': True,
                  'scope': 'OFFLINE_TEST_ONLY_NO_REAL_OWNER_AUTHORITY_NO_HOST_OR_LINUX_PASS',
                  'method': 'REAL_CALENDAR_RECEIPT_API_THEN_REAL_DAY_AND_VERIFY_CLI',
                  'historical_helper': {'available': False, 'used': False,
                                        'expected_sha256': HISTORICAL_HELPER_SHA},
                  'original_generator_sha256': sha((source / 'programs-final-candidate/k8_eve/tests/make_fixtures.py').read_bytes()),
                  'generator_sha256': sha(Path(__file__).read_bytes()),
                  'tool_sha256': TOOL_SHA, 'runtime_manifest_sha256': sha(runtime_manifest),
                  'config_dependency_sha256': CONFIG_SHA,
                  'python': {'executable': sys.executable, 'version': sys.version},
                  'dependencies': {name: importlib.metadata.version(name) for name in ('exchange_calendars', 'numpy', 'pandas')},
                  'calendar_pin_receipt': receipt, 'epoch_inputs': {}, 'copied_inputs': {}, 'commands': []}

    def command(label, arguments, status):
        argv = [sys.executable, '-I', '-B', str(tool_path)] + [str(arg) for arg in arguments]
        completed = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        out, err = logs / (label + '.stdout.txt'), logs / (label + '.stderr.txt')
        out.write_bytes(completed.stdout)
        err.write_bytes(completed.stderr)
        row = {'argv': argv, 'returncode': completed.returncode,
               'stdout': str(out.relative_to(target)), 'stdout_sha256': sha(completed.stdout),
               'stderr': str(err.relative_to(target)), 'stderr_sha256': sha(completed.stderr)}
        provenance['commands'].append(row)
        assert completed.returncode == 0, row
        result = json.loads(completed.stdout)
        row['result'] = result
        assert result['status'] == status and result['documentary_authority'] == 'VERIFIED', row
        return result

    for kind in ('documents', 'k12-documents'):
        src, dst = source / kind, target / kind
        dst.mkdir()
        for path in sorted(src.iterdir()):
            if path.name.startswith('out-') or path.name == 'epoch.json':
                continue
            if path.is_dir():
                shutil.copytree(path, dst / path.name)
            else:
                shutil.copyfile(path, dst / path.name)
        for name, digest in hashes(dst).items():
            assert digest == sha((src / name).read_bytes()), name
            provenance['copied_inputs'][kind + '/' + name] = digest
        raw = (src / 'epoch.json').read_bytes()
        epoch = json.loads(raw)
        rebuilt = copy.deepcopy(epoch)
        rebuilt['calendar_pin_receipt'] = receipt
        assert {key: value for key, value in epoch.items() if key != 'calendar_pin_receipt'} == {
            key: value for key, value in rebuilt.items() if key != 'calendar_pin_receipt'}
        write_json(dst / 'epoch.json', rebuilt)
        provenance['epoch_inputs'][kind] = {'original_sha256': sha(raw), 'new_sha256': sha((dst / 'epoch.json').read_bytes()),
                                           'only_mutable_unsigned_field': 'calendar_pin_receipt',
                                           'original_receipt': epoch['calendar_pin_receipt'], 'new_receipt': receipt}
        days = ('2026-10-06', '2026-10-07', '2026-10-08') if kind == 'documents' else ('2026-10-06',)
        windows = ('primary', 'contingency_1', 'contingency_2') if kind == 'documents' else ('primary',)
        for day in days:
            for window in windows:
                label = kind + '-' + day + '-' + window
                output = dst / (('out-' + day + '-' + window) if kind == 'documents' else 'out-primary')
                result = command(label + '-day', ['day', '--epoch-inputs', dst / 'epoch.json',
                    '--session-inputs', dst / (day + '.json'), '--window', window, '--output-directory', output,
                    '--chain-directory', dst / 'chain'], 'WRITTEN')
                assert result['list'] == ('EMPTY' if day == '2026-10-08' else 'NOT_EMPTY')
                command(label + '-verify', ['verify', '--directory', output, '--chain-directory', dst / 'chain'], 'VERIFIED')
    fixture = json.loads((source / 'k8-document-fixtures.json').read_bytes())
    fixture['generation_provenance'] = {'synthetic': True, 'calendar_version': version,
                                       'provenance_file': 'PROVENANCE.json', 'historical_helper_used': False}
    for day, item in fixture['days'].items():
        roles = {}
        for window in fixture['windows']:
            output = target / 'documents' / ('out-' + day + '-' + window)
            summary = json.loads((output / 'SUMMARY.json').read_bytes())
            for role, name in summary['roles'].items():
                if role in ('request', 'dispatch_go'):
                    continue
                key = role + ':' + window if role in ('capacity_config', 'veto_view') else role
                value = {'path': name, 'b64': base64.b64encode((output / name).read_bytes()).decode('ascii')}
                if key in roles:
                    assert roles[key] == value, (key, 'shared day-role bytes differ')
                roles[key] = value
        item['files'] = {key: value['b64'] for key, value in sorted(roles.items())}
        item['paths'] = {key: value['path'] for key, value in sorted(roles.items())}
    write_json(target / 'k8-document-fixtures.json', fixture)
    assert hashes(source) == original, 'original test-inputs changed'
    provenance['output_files_sha256'] = hashes(target)
    write_json(target / 'PROVENANCE.json', provenance)
    listing = ''.join(digest + '  ' + name + '\n' for name, digest in hashes(target).items())
    (target / 'SHA256SUMS').write_text(listing, encoding='ascii')
    print(json.dumps({'version': version, 'manifest_sha256': sha(listing.encode('ascii')),
                      'calendar_pin_sha256': receipt['calendar_pin_sha'], 'commands_verified': len(provenance['commands'])}, sort_keys=True))


if __name__ == '__main__':
    main()
