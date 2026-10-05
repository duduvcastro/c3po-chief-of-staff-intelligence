"""Select synthetic real-tool documents for the exact observed calendar version.

This only selects test inputs. It changes no verifier or operational calendar gate.
An absent or unexpected dependency fails; matching and cross-version cases both run.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import helpers as h

VERSIONS = ('4.2.8', '4.13.2')
# Pins produced by generate.py with the real pinned day tool on each dependency.
MANIFESTS = {'4.2.8': '01d7e54324eb6e08919c1991eff635f577bf0fa36c6b105daa38eec1f899ca20',
             '4.13.2': 'e2d952c55ec817110d04cf80c99acf9cf649c94639855ea01efffe994357f31a'}


def fixture_root(other=False):
    version = importlib.metadata.version('exchange_calendars')
    assert version in VERSIONS, 'unproved exchange_calendars dependency: ' + version
    selected = next(item for item in VERSIONS if item != version) if other else version
    root = h.BIND.parent / 'test-inputs/calendar-fixtures' / selected
    raw = (root / 'SHA256SUMS').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFESTS[selected], 'calendar fixture listing changed'
    listed = {}
    for line in raw.decode('ascii').splitlines():
        digest, name = line.split('  ', 1)
        assert name not in listed and not Path(name).is_absolute() and all(
            part not in ('', '.', '..') for part in name.split('/')), 'invalid calendar fixture path'
        listed[name] = digest
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, 'calendar fixture changed: ' + name
    present = {str(path.relative_to(root)) for path in root.rglob('*') if path.is_file()}
    assert present == set(listed) | {'SHA256SUMS'}, 'calendar fixture file set changed'
    provenance = json.loads((root / 'PROVENANCE.json').read_bytes())
    assert provenance['synthetic'] is True
    assert provenance['dependencies']['exchange_calendars'] == selected
    assert provenance['calendar_pin_receipt']['calendar_version'] == selected
    return root
