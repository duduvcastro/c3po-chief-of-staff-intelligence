"""Text pins of C3 against the release it is frozen against (dd4ec4bb) and against the frozen core. Every test here is
named "static": the mutation harness deselects them, so a mutant is never killed merely because a pinned text changed.
The release comparisons run when a tree of the release is at hand (tests/c3.release_tree) and say so when they skip."""
import json
import re

import pytest

import c3
import family as f

def tree():
    found=c3.release_tree()
    if found is None:pytest.skip('no tree of the release at hand (HOSTOPS02_TEST_RELEASE_TREE, work/release, or a checkout above)')
    return found

def test_static_provider_host_and_port_are_the_release_codes_not_a_typed_guess():
    m=c3.K().m;root=tree()
    transport=(root/'c3po/backend/app/r2d2_v2_massive_transport.py').read_text().splitlines()
    assert "socket=connector('wss://socket.massive.com/stocks',open_timeout=10," in transport[98],'line 99 of the transport'
    hosts=set(re.findall(r'wss://([A-Za-z0-9.-]+)(?::([0-9]+))?/',(root/'c3po/backend/app/r2d2_v2_massive_transport.py').read_text()))
    assert hosts=={(m.PROVIDER_HOST,'')},'one endpoint, no explicit port: the wss default 443'
    readme=(root/'c3po/deployment/massive-supervisor/README.md').read_text().splitlines()
    assert readme[579]=='2. A TLS connection to `socket.massive.com:443` succeeds from `@NETWORK@`, without a token.'
    assert m.PROVIDER_PORT==443 and '%s:%d'%(m.PROVIDER_HOST,m.PROVIDER_PORT) in readme[579]
    assert '| `@NETWORK@` | 1 | Docker network of the container, chosen from the host rehearsal. | `bridge` |' in readme[220]
    requirements=(root/'c3po/backend/requirements.txt') if (root/'c3po/backend/requirements.txt').is_file() else None
    if requirements is not None:assert 'websockets>=14,<16' in requirements.read_text().splitlines()

def test_static_the_image_is_built_on_python_with_the_standard_library_the_script_needs():
    root=tree();dockerfile=(root/'c3po/backend/Dockerfile').read_text()
    assert 'FROM python:3.12-alpine3.24@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a' in dockerfile.splitlines()
    assert not re.search(r'^ENTRYPOINT',dockerfile,re.M),'no entrypoint: python -I -B - is the command'

def test_static_build_names_this_core_and_these_two_files():
    k=c3.K();report=k.report;a=f.assembler()
    assert report['core_sha256']==a.core_sha256()=='4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'
    assert report['operation_part_sha256']==f.sha((c3.DIRECTORY/'op.py').read_bytes()) and report['spec_sha256']==f.sha((c3.DIRECTORY/'spec.py').read_bytes())
    assert report['operation']=='GO_READONLY_HOSTOPS02_TLS_PROBE_01' and report['writes_allowed'] is False and report['parts']==['core','runner','docker']
    assert k.m.PROBE_SCRIPT_SHA256=='d625d84f41bdf91396211025afbb80afa0a42e960bc1a19cb9e95428c0619566' and k.m.PROBE_SCRIPT_BYTES==5746

def test_static_unbound_request_carries_no_window_no_day_and_no_value_of_the_host():
    k=c3.K();request=json.loads((k.dir/'REQUEST.UNBOUND.json').read_bytes())
    assert request['date'] is None and request['plan']['window']=={'expires_at':None,'not_before':None}
    assert {key:request['plan'][key] for key in k.m.PLAN_KEYS}=={key:None for key in k.m.PLAN_KEYS}
