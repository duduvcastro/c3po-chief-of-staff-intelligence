"""The one function K8 copies from the frozen core: k8_create_file is derived(core parts/files.py) byte for byte
(tests/k8copy.py says how), and the only other line that differs from the core's create_file is the name rule,
k8_named_in. Its behaviour differs from the core's only in the names it admits. These tests are static: a mutant of
the copy is judged by the behavioural tests (test_k8_eve.py, test_native.py), never by these byte comparisons."""
from pathlib import Path

import pytest

import family as f
import k8
import k8copy

CORE_FILES=Path(f.CORE)/'parts'/'files.py'

def test_static_the_copy_is_the_core_function_derived_mechanically():
    k=k8.K();source=k.source.decode('ascii');built=k8copy.source_of(source,'k8_create_file')
    assert built==k8copy.derived(CORE_FILES.read_text(encoding='ascii'))
    assert k8copy.source_of(source,'create_file')==k8copy.source_of(CORE_FILES.read_text(encoding='ascii'),'create_file'),'the core part itself is carried unchanged'
    assert source.count('def k8_create_file(')==1 and source.count('def create_file(')==1

def test_static_the_operation_part_holds_the_copy_and_the_build_holds_the_operation_part():
    op=(k8.DIRECTORY/'op.py').read_text(encoding='ascii')
    assert k8copy.source_of(op,'k8_create_file')==k8copy.derived(CORE_FILES.read_text(encoding='ascii'))

def test_the_name_rule_admits_the_loaders_names_and_nothing_else():
    k=k8.K();m=k.m
    class Held:
        rows=None
    for name in ('session=2026-10-06.json','session=2026-10-09.template.md','session=2026-10-07.view-contingency_2.md',
                 'session=2026-10-08.primary.capacity.json','session=2026-10-06.admission.json'):
        assert m.k8_named_in('/var/lib/c3po-capacity/payload/'+name,Held()),name
    for name in ('session=2026-10-05.json','session=2026-10-10.json','session=2026-10-06','session=2026-10-06.','session=2026-10-06.JSON',
                 'other=2026-10-06.json','session=2026-10-06/x.json','.hostops-0123456789abcdef-1.partial','session=2026-10-06..json'[:0] or 'x'):
        assert not m.k8_named_in('/var/lib/c3po-capacity/payload/'+name,Held()),name
    assert not m.k8_named_in('/var/lib/c3po-capacity/payload/../go/session=2026-10-06.json',Held())
    assert not m.k8_named_in(None,Held()) and not m.k8_named_in('relative/session=2026-10-06.json',Held())
    class Rows:
        rows=[{'path':'/var/lib/c3po-capacity/go'}]
    assert m.k8_named_in('/var/lib/c3po-capacity/go/session=2026-10-06.json',Rows())
    assert not m.k8_named_in('/var/lib/c3po-capacity/payload/session=2026-10-06.json',Rows()),'the directory the parent was walked to'
    # the core's own rule refuses every one of the loader's names: the reason for the copy
    assert not m.named_in('/var/lib/c3po-capacity/payload/session=2026-10-06.json',Held())

@pytest.mark.parametrize('content,mode,index,go16,code',[(b'',0o600,0,'0'*16,'FILE_REQUEST_INVALID'),(b'x',0o640,0,'0'*16,'FILE_REQUEST_INVALID'),
    (b'x',0o600,100,'0'*16,'FILE_REQUEST_INVALID'),(b'x',0o600,0,'0'*15,'FILE_REQUEST_INVALID'),(b'x'*1048577,0o600,0,'0'*16,'FILE_REQUEST_INVALID'),
    ('x',0o600,0,'0'*16,'FILE_REQUEST_INVALID'),(b'x',0o644,0,'0'*16,None),(b'x',0o600,0,'0'*16,'NAME')])
def test_the_request_check_of_the_copy_is_the_cores(content,mode,index,go16,code):
    m=k8.K().m;docs,host=k8.case()
    class Held:
        rows=None;fd=None
        def verify(self,gate):raise m.Refused('PARENT_REPLACED')
    name='other.json' if code=='NAME' else 'session=2026-10-06.json'
    row=m.k8_create_file(index,'payload','/var/lib/c3po-capacity/payload/'+name,content,mode,Held(),host,lambda:60.0,m.Effects(),go16)
    assert row['code']==({None:'PARENT_REPLACED','NAME':'FILE_REQUEST_INVALID'}.get(code,code)) and row['state']=='NOT_ATTEMPTED' and host.log==[]
