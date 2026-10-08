"""Only the new metadata regression. Never re-runs the closed eleven tests."""
import ast
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent

def check():
    manifest = json.loads((ROOT / 'MANIFEST.json').read_bytes())
    for row in manifest['files']:
        raw = (ROOT / row['name']).read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    previous = (ROOT / 'PROVA_PREVIOUS_SOURCE.txt').read_bytes()
    current = (ROOT / 'PROVA.py').read_bytes()
    assert previous.count(b'NEW_F5_LINUX_RESULT_V1') == 1
    assert current == previous.replace(b'NEW_F5_LINUX_RESULT_V1', b'NEW_F3_LINUX_RESULT_V1')
    ast.parse(current)
    return {'schema': 'F3_RESULT_METADATA_REVISION_V1', 'checks': 2,
            'source_delta': 'ONLY_RESULT_SCHEMA_F5_TO_F3', 'status': 'PASS_METADATA_ONLY',
            'family': 'F3', 'closed_family_tests_repeated': False,
            'host_operated': False, 'runtime_accepted': False, 'operational_GO': False,
            'manifest_sha256': hashlib.sha256((ROOT / 'MANIFEST.json').read_bytes()).hexdigest()}

if __name__ == '__main__':
    raw = (json.dumps(check(), sort_keys=True, separators=(',', ':')) + '\n').encode()
    if len(sys.argv) == 2:
        pathlib.Path(sys.argv[1]).write_bytes(raw)
    print(raw.decode(), end='')
