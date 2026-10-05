"""Replaces the synthetic `bound` fixture of the W1 candidate's own test file by a set produced by bind_once.py.

The candidate's fixture returns (root, request, authority, go, config, save_docs, pin, put). Here the four documents are
the bytes the binder wrote (REHEARSAL mode, fake transport, window NOW .. NOW + 5 min as in the candidate's fixture), `pin`
is the binder's own DISPATCH.BOUND.json, and `root` is the claim root. save_docs and put are the candidate's own code:
they are only used by the tests that mutate a document on purpose, and then start from the binder's documents.
BIND_TEST_W1_FAMILY names the sealed (pristine) family the binder binds from; BIND_TEST_FIXTURE_COUNTER, when set, names a
file that receives one byte per fixture built, so that the caller can prove the substitution was in effect."""
from datetime import timedelta
import json
import os
from pathlib import Path

import bind_once as b


def bound(tmp_path, module):
    p, l, SOURCE, NOW = module.p, module.l, module.SOURCE, module.NOW
    base = Path(str(tmp_path)).resolve()
    family = Path(os.environ['BIND_TEST_W1_FAMILY'])
    reference = b.rehearsal_reference(base / 'rehearsal-transport')['reference']
    parameters = {'schema': b.PARAMETERS_SCHEMA, 'operation': p.OPERATION, 'label': 'attempt', 'signature_model': 'IND', 'not_before': b.zulu(NOW),
                  'not_after': b.zulu(NOW + timedelta(minutes=5)), 'candidates': {'release_directories': [], 'capacity_roots': []}}
    (base / 'PARAMETERS.json').write_text(json.dumps(parameters))
    prepared = b.prepare(family, p.OPERATION, base / 'PARAMETERS.json', reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    signed = b.sign(base / 'rehearsal-bound', prepared['prepare_json_sha256'], b.zulu(NOW), b.REHEARSAL_ANSWER, now=lambda: NOW)
    set_ = base / 'rehearsal-bound'
    root = set_ / b.CLAIM_ROOT
    extra = base / 'extra'
    extra.mkdir(mode=0o700)

    def put(name, raw):
        path = extra / name
        path.write_bytes(raw)
        path.chmod(0o600)
        return {'path': str(path), 'sha256': p.sha(raw)}
    request = json.loads((set_ / 'REQUEST.BOUND.json').read_bytes())
    authority = json.loads((set_ / signed['authority_name']).read_bytes())
    go = json.loads((set_ / signed['go_name']).read_bytes())
    config_raw = (set_ / 'DISPATCH.BOUND.json').read_bytes()
    config = json.loads(config_raw)
    assert p.canonical(request) == (set_ / 'REQUEST.BOUND.json').read_bytes() and p.canonical(go) == (set_ / signed['go_name']).read_bytes()

    def save_docs():          # the candidate's own save_docs, verbatim in its logic
        authority['request_sha256'] = p.sha(p.canonical(request))
        go.update(request_sha256=authority['request_sha256'], authority_sha256=p.sha(p.canonical(authority)),
                  payload_sha256=p.sha(SOURCE), claim_root_identity=config['local_root_identity'],
                  transport_binding={k: config[k] for k in ('target', 'remote_command', 'command_sha256', 'runtime_sha256')})
        payload = l.build(SOURCE, p.canonical(request), p.canonical(authority), p.canonical(go),
                          expected_payload_sha256=p.sha(SOURCE), expected_request_sha256=p.sha(p.canonical(request)),
                          expected_authority_sha256=p.sha(p.canonical(authority)), expected_go_sha256=p.sha(p.canonical(go)))
        for key, raw in [('source', SOURCE), ('request', p.canonical(request)), ('authority', p.canonical(authority)), ('go', p.canonical(go)), ('payload', payload)]:
            config[key] = put(key, raw)
        return put('config', p.canonical(config))
    pin = {'path': str(set_ / 'DISPATCH.BOUND.json'), 'sha256': p.sha(config_raw)}
    if os.environ.get('BIND_TEST_FIXTURE_COUNTER'):
        with open(os.environ['BIND_TEST_FIXTURE_COUNTER'], 'ab') as counter:
            counter.write(b'.')
    return root, request, authority, go, config, save_docs, pin, put
