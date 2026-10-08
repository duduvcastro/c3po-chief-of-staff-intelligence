"""Fixed F6 service entry. A unit pins this file and the whole source manifest.

No daemon, timer or root is installed by this program. A repeated scheduled
invocation is consumed by the journal, including a refusal or uncertain effect.
"""
import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path


def stable_stat(info):
    """Content/identity metadata; a read-induced atime change is harmless."""
    return tuple(getattr(info,name) for name in ("st_dev","st_ino","st_mode","st_nlink","st_uid","st_gid",
                  "st_size","st_mtime_ns","st_ctime_ns"))


def source_manifest(pin):
    # Standard library only until every package member has been verified.
    root=Path(__file__).absolute().parent
    for p in (root,*root.parents):
        if stat.S_ISLNK(p.lstat().st_mode):raise ValueError('SOURCE_LINK')
    mp=root/'MANIFEST.json';mi=mp.lstat()
    if not stat.S_ISREG(mi.st_mode) or mi.st_nlink!=1 or stat.S_IMODE(mi.st_mode)!=0o444:raise ValueError('SOURCE_MANIFEST_PERMISSION')
    raw=mp.read_bytes()
    if stable_stat(mi)!=stable_stat(mp.lstat()):raise ValueError('SOURCE_MANIFEST_CHANGED')
    if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('SOURCE_MANIFEST_PIN')
    manifest=json.loads(raw)
    names=set()
    for entry in manifest['files']:
        name=entry['name']
        if name in names or '/' in name or name in ('.','..'):raise ValueError('SOURCE_MEMBER')
        names.add(name);p=root/name;before=p.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or stat.S_IMODE(before.st_mode)!=0o444:raise ValueError('SOURCE_PERMISSION')
        data=p.read_bytes();after=p.lstat()
        if stable_stat(before)!=stable_stat(after) or len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('SOURCE_CHANGED')
    if 'service.py' not in names:raise ValueError('SERVICE_NOT_IN_MANIFEST')
    return root


def dependency_tree(guard,deps,manifest):
    from common import need,sha
    from runtime import physical,directory_chain
    root=Path(deps['root']);directory_chain(str(root),guard.mode)
    need(manifest['root']==str(root) and type(manifest['files']) is list and manifest['files'],'H16_DEPENDENCY_MANIFEST')
    expected={}
    for member in manifest['files']:
        name=member['name'];need(type(name) is str and name and not name.startswith('/')
             and '..' not in name.split('/') and name not in expected,'H16_DEPENDENCY_PATH')
        role='dependency:'+name;entry=guard.value['spec']['files'][role]
        need(entry['path']==str(root/name) and entry['sha256']==sha(member['sha256']),'H16_DEPENDENCY_NOT_MEASURED')
        expected[name]=member['sha256']
    observed=set();count=0
    for parent,directories,files in os.walk(root,followlinks=False):
        count+=len(directories)+len(files);need(count<=20000,'H16_DEPENDENCY_LIMIT')
        for name in directories:
            directory_chain(str(Path(parent)/name),guard.mode)
        for name in files:
            path=Path(parent)/name;relative=str(path.relative_to(root))
            need(relative in expected,'H16_DEPENDENCY_EXTRA_FILE')
            raw,ident=physical(path,maximum=128*1024*1024)
            need(ident['mode']&0o022==0 and ident['uid'] in (0,guard.value['measurement']['euid'])
                 and hashlib.sha256(raw).hexdigest()==expected[relative],'H16_DEPENDENCY_PIN')
            observed.add(relative)
    need(observed==set(expected),'H16_DEPENDENCY_MISSING_FILE');guard.recheck()
    return str(root)


def assemble(guard,*,clock,connector=None):
    from common import PinnedDirectory,need,strict
    from channel import GitHub429
    from control import Controller,OPERATIONS
    from families import InputStore,CapacityAdapter,K12Adapter,H16Adapter,ManifestStore
    from journal import Journal,IndependentWitness
    from processes import BoundedProcess,DockerEngine
    from readers import GateReader,AuthorityView
    from observer import Observer
    from reader_artifacts import ArtifactReader
    from reader_checks import DBReader,ReaderHost,CompleteReader
    from retention import NativeRetainer
    roots={}
    try:
        for role,path in guard.value['spec']['roots'].items():
            roots[role]=PinnedDirectory(path,expected=guard.value['measurement']['roots'][role][-1]['identity'])
        entry=guard.value['spec']['files']['registry']
        from runtime import physical
        raw,_=physical(entry['path']);need(__import__('hashlib').sha256(raw).hexdigest()==guard.value['registry_sha256'],'REGISTRY_PIN')
        config=strict(raw);need(config['schema']=='SERVER_NATIVE_REGISTRY_V2' and config['context']==guard.context,'REGISTRY_CONTEXT')
        need(set(config['operations'])==set(guard.value['allowed_operations'])<=OPERATIONS,'REGISTRY_OPERATION_SET')
        pins=config['journal_identities']
        seed=guard.value['journal_election']
        need(seed['context']==guard.context and seed['mode']==guard.mode,'JOURNAL_ELECTION_CONTEXT')
        witness=IndependentWitness(roots['witness'],pins['witness']['events.jsonl'],pins['witness']['lock'],
            election=seed,ledger_root=roots['journal'].identity,independence=config['witness_independence'],mode=guard.mode)
        journal=Journal(roots['journal'],pins['ledger']['events.jsonl'],pins['ledger']['lock'],election=seed,witness=witness)
        since=config['channel']['collection_since_UTC']
        channel=GitHub429(guard,config['channel']['token_path'],config['channel']['token_sha256'],since=since)
        inputs=InputStore(roots['inputs']);runner=BoundedProcess(guard);registry={}
        if any(op.startswith('F4_') for op in config['operations']):engine=DockerEngine(guard,runner)
        for operation in config['operations']:
            if operation.startswith('F3_'):
                adapter=CapacityAdapter(operation,guard,inputs,roots['results'],roots['capacity'],clock=clock)
            elif operation.startswith('F4_'):
                adapter=K12Adapter(operation,guard,inputs,roots['results'],engine,roots['receipts'],ManifestStore(roots['bars'],roots['capacity']),clock=clock)
            elif operation=='F5_H16_READ':
                reader_entry=config['H16'];need(reader_entry==guard.value['reader_registry']['H16_SERVER_READER_V2']['configuration'],'H16_CONFIG_NOT_ELECTED')
                if connector is None:
                    # Imports from an independently measured dependency tree,
                    # never an unreviewed ambient environment or request path.
                    deps=config['dependencies'];need(deps['manifest_role']=='psycopg_dependencies','H16_DRIVER_NOT_ELECTED')
                    manifest_path=guard.value['spec']['files'][deps['manifest_role']]['path']
                    dep_raw,_=physical(manifest_path);dep_manifest=strict(dep_raw)
                    verified=dependency_tree(guard,deps,dep_manifest)
                    sys.path.insert(0,verified)
                    import psycopg
                    need(Path(psycopg.__file__).absolute().is_relative_to(Path(deps['root'])),'H16_DRIVER_ORIGIN')
                    connector=psycopg.connect
                artifacts=ArtifactReader(guard.value['source_pins']['reader_artifacts.py'],roots['receipts'],roots['bars'],roots['capacity'],
                   selectors=reader_entry['artifact_selectors'],capacity_request_name=reader_entry['capacity_request_name'])
                complete=CompleteReader(guard.value['source_pins']['reader_checks.py'],artifacts,
                    DBReader(guard,reader_entry['DBR'],connector),ReaderHost(guard,runner,reader_entry['M6_V']),reader_entry)
                adapter=H16Adapter(operation,guard,inputs,roots['results'],complete,clock=clock)
            else:need(False,'HOLD_ADAPTER_UNAVAILABLE')
            registry[operation]=adapter
        retainer=NativeRetainer(guard,runner,roots['retention'],config['retention'])
        controller=Controller(guard,journal,registry,channel,clock=clock,retainer=retainer)
        upstreams={}
        for name,up in config.get('upstream_journals',{}).items():
            led,wi,out=[roots[up[k]] for k in ('ledger_root_role','witness_root_role','results_root_role')]
            need(led.identity!=roots['journal'].identity,'UPSTREAM_JOURNAL_IS_OWN')
            w=IndependentWitness(wi,up['identities']['witness']['events.jsonl'],up['identities']['witness']['lock'],
                election=up['election'],ledger_root=led.identity,independence=up['witness_independence'],mode=guard.mode)
            upstreams[name]=(Journal(led,up['identities']['ledger']['events.jsonl'],up['identities']['ledger']['lock'],
                                    election=up['election'],witness=w),out)
        gate_config=dict(config['gates'],_own_root_identity=roots['journal'].identity)
        gates=GateReader(guard,roots['results'],roots['receipts'],channel,gate_config,external_journals=upstreams)
        oe=config['authority_observer']
        need(oe['producer_sha256']==guard.value['source_pins']['observer.py'],'OBSERVER_SOURCE_NOT_ELECTED')
        observer=Observer(guard,roots['observer'],oe,clock=clock)
        view=AuthorityView(guard,roots['observer'],oe,clock=clock,observer=observer)
        return controller,gates,view,roots,config
    except BaseException:
        for root in roots.values():root.close()
        raise


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--acceptance',required=True)
    parser.add_argument('--acceptance-sha256',required=True)
    parser.add_argument('--slot',required=True)
    args=parser.parse_args();root=source_manifest(args.manifest_sha256);sys.path.insert(0,str(root))
    from datetime import datetime,timezone
    from common import canonical
    from runtime import RuntimeGuard
    from control import public_projection
    guard=RuntimeGuard(args.acceptance,args.acceptance_sha256)
    clock=lambda:datetime.now(timezone.utc).isoformat()
    controller,gates,view,roots,config=assemble(guard,clock=clock)
    try:
        bundle={'references':guard.value['election']['slots'][args.slot]['references']}
        outcome=controller.invoke(args.slot,bundle,view_reader=view,gate_reader=gates)
        public=public_projection(outcome)
        # One journaled POST; an uncertain publication never repeats effects.
        result=controller.publish(outcome['attempt_key'],public,roots['publication'],config['channel']['author_id'])
        print(canonical({'result':__import__('json').loads(public),'publication':result}).decode(),end='')
        return 0 if outcome['verdict']=='COMPLETE' else 2
    finally:
        for directory in roots.values():directory.close()


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        # No exception text, argv, secret, internal path or hostname in public.
        print('{"schema":"SERVER_SERVICE_HOLD_V2","verdict":"HOLD_RUNTIME","operational_GO":false}')
        raise SystemExit(2)
