"""Synthetic real day-tool output; rule tests isolate checker, plus actual checker on its dependency-equipped Python."""
import base64
import copy
import json
import sys
from pathlib import Path
import pytest
import helpers as h
from calendar_fixture_selection import fixture_root
from test_programs import programs, program_seals, DIRECTORIES, OWN_CORE, PROGRAMS
b = h.b
K8_DOCUMENTS = b.k8_documents
ROOT = h.BIND.parent / 'test-inputs'
OP = 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01'


def context(programs, root=ROOT):
    ROOT=root
    fixture=json.loads((ROOT/'k8-document-fixtures.json').read_bytes())
    raws=fixture['days']['2026-10-06']['files']
    def blob(raw):
        raw=base64.b64decode(raw)
        return {'content_b64':base64.b64encode(raw).decode(),'sha256':b.sha(raw),'bytes':len(raw)}
    plan={'day':'2026-10-06','windows':fixture['windows'],'contract':blob(raws['contract']),
          'files':{key:blob(raw) for key,raw in raws.items() if key!='contract'}}
    sets={w:{'directory':str((ROOT/'documents'/('out-2026-10-06-'+w)).resolve()),
             'chain_directory':str((ROOT/'documents/chain').resolve())} for w in fixture['windows']}
    return {'plan':plan,'rt':{'source':programs.modules[OP][2]['source']},
            'params':{'k8_document_sets':sets},'base':ROOT}


def checker(bundle,documents,chain):
    summary=b.strict_json(documents['SUMMARY.json'],'TEST')
    return {'status':'VERIFIED','kind':'CAPACITY_DAY','documentary_authority':'VERIFIED',
            'summary':'REBUILT_EQUAL','day':summary['day'],'window':summary['window'],
            'sha256sums_sha256':b.sha(documents['SHA256SUMS'])}


def test_each_window_matches_actual_contract_and_delivery_bytes(programs,monkeypatch):
    monkeypatch.setattr(b,'k8_run_verifier',checker)
    result=K8_DOCUMENTS(context(programs))
    assert len(result['windows'])==3
    assert len({row['contract_sha256'] for row in result['windows'].values()})==1


@pytest.mark.parametrize('case',['absent','missing_window','not_checked','other_day','other_listing','other_contract'])
def test_unverified_or_unbound_window_refused(programs,monkeypatch,case):
    ctx=context(programs)
    if case=='absent':ctx['params']={};code='K8_DOCUMENT_SETS_REQUIRED'
    elif case=='missing_window':ctx['params']['k8_document_sets'].pop('primary');code='K8_DOCUMENT_SETS_REQUIRED'
    elif case=='other_contract':
        # Well-shaped contract with same causal scope: changing owner_sha preserves K8's layout validation,
        # but it no longer equals the contract verified in the day-tool set.
        raw=json.loads(base64.b64decode(ctx['plan']['contract']['content_b64']))
        raw['owner_sha']='b1'*32
        raw=b.canonical(raw)
        ctx['plan']['contract']={'content_b64':base64.b64encode(raw).decode(),'sha256':b.sha(raw),'bytes':len(raw)}
        code='K8_DOCUMENTS_NOT_THE_DELIVERY_BYTES'
    else:code='K8_DOCUMENTS_NOT_VERIFIED'
    def altered(bundle,docs,chain):
        out=checker(bundle,docs,chain)
        if case=='not_checked':out['documentary_authority']='NOT_CHECKED'
        if case=='other_day':out['day']='2026-10-07'
        if case=='other_listing':out['sha256sums_sha256']='b1'*32
        return out
    monkeypatch.setattr(b,'k8_run_verifier',altered)
    with h.refused(code):K8_DOCUMENTS(ctx)


def test_actual_pinned_tool_reverifies_all_windows(programs):
    result=K8_DOCUMENTS(context(programs, fixture_root()))
    assert all(row['documentary_authority']=='VERIFIED' for row in result['windows'].values())


def test_actual_pinned_tool_refuses_k8_documents_from_other_calendar(programs):
    with h.refused('K8_DOCUMENTS_NOT_VERIFIED'):
        K8_DOCUMENTS(context(programs, fixture_root(other=True)))


def test_checker_bytes_must_equal_compiled_listing(tmp_path):
    (tmp_path/'SHA256SUMS').write_text('b1'*32+'  checker.py\n')
    with h.refused('K8_VERIFIER_BYTES_CHANGED'):b.k8_listed_bytes(tmp_path,b.K8_VERIFIER_SUMS)


def test_mutated_input_file_is_rejected_before_checker(tmp_path):
    (tmp_path/'SHA256SUMS').write_text(b.sha(b'original')+'  REQUEST.json\n')
    (tmp_path/'REQUEST.json').write_bytes(b'changed')
    with h.refused('K8_DOCUMENTS_BYTES_CHANGED'):b.k8_listed_bytes(tmp_path)


def mutate_set(ctx,tmp_path,window,role,transform):
    import shutil
    src=Path(ctx['params']['k8_document_sets'][window]['directory'])
    dst=tmp_path/'set';shutil.copytree(src,dst)
    summary=json.loads((dst/'SUMMARY.json').read_bytes())
    file=dst/summary['roles'][role];file.write_bytes(transform(file.read_bytes()))
    lines=[]
    for line in (dst/'SHA256SUMS').read_text().splitlines():
        _,name=line.split('  ',1);lines.append(b.sha((dst/name).read_bytes())+'  '+name+'\n')
    (dst/'SHA256SUMS').write_text(''.join(lines));ctx['params']['k8_document_sets'][window]['directory']=str(dst)


@pytest.mark.parametrize('bad_json',[True,False])
def test_window_request_contract_cannot_drift(programs,monkeypatch,tmp_path,bad_json):
    ctx=context(programs);monkeypatch.setattr(b,'k8_run_verifier',checker)
    def change(raw):
        if bad_json:return b'{'
        obj=json.loads(raw);obj['documentary']['contract_sha256']='b1'*32;return b.canonical(obj)
    mutate_set(ctx,tmp_path,'primary','request',change)
    with h.refused('K8_WINDOW_REQUEST_INVALID' if bad_json else 'K8_WINDOW_REQUEST_NOT_THE_DELIVERY_CONTRACT'):
        K8_DOCUMENTS(ctx)


@pytest.mark.parametrize('bad_listing',['invalid','0'*64+'  ../escape\n'])
def test_listing_cannot_escape_or_be_malformed(tmp_path,bad_listing):
    (tmp_path/'SHA256SUMS').write_text(bad_listing)
    with h.refused('K8_DOCUMENTS_LISTING_INVALID'):b.k8_listed_bytes(tmp_path)


def test_unreadable_set_refuses(tmp_path):
    with h.refused('K8_DOCUMENTS_UNREADABLE'):b.k8_listed_bytes(tmp_path)


def test_total_document_bytes_bounded(tmp_path):
    raw=b'x'*(2*1024*1024)
    lines=[]
    for index in range(5):
        name='part%d'%index;(tmp_path/name).write_bytes(raw);lines.append(b.sha(raw)+'  '+name+'\n')
    (tmp_path/'SHA256SUMS').write_text(''.join(lines))
    with h.refused('K8_DOCUMENTS_TOO_LARGE'):b.k8_listed_bytes(tmp_path)


def test_verifier_unavailable_refuses(monkeypatch):
    def unavailable(*args,**kwargs):raise OSError()
    monkeypatch.setattr(b.subprocess,'run',unavailable)
    with h.refused('K8_DOCUMENTS_VERIFIER_UNAVAILABLE'):b.k8_run_verifier({}, {}, {})


def test_verifier_failure_refuses(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(b.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout=b'{}'))
    with h.refused('K8_DOCUMENTS_NOT_VERIFIED'):b.k8_run_verifier({}, {}, {})


def test_signed_chain_changed_refuses(programs,tmp_path,monkeypatch):
    import shutil
    ctx=context(programs);monkeypatch.setattr(b,'k8_run_verifier',checker)
    chain=tmp_path/'chain';shutil.copytree(ROOT/'documents/chain',chain)
    file=next(chain.iterdir());file.write_bytes(file.read_bytes()+b'\n')
    for item in ctx['params']['k8_document_sets'].values():item['chain_directory']=str(chain)
    with h.refused('K8_DOCUMENTS_CHAIN_INVALID'):K8_DOCUMENTS(ctx)
