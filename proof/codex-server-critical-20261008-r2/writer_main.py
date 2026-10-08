"""Standalone writer entry for the newly elected K12 V2 image/argv.

No provider, SQL, dynamic script, signature or container activation. Reads only
the exact mounted runtime acceptance and retained causal bodies; one exclusive
private publication is independently re-read before its wire receipt.
"""
import argparse
import sys
from pathlib import Path


def run(guard,*,clock=None):
    from common import PinnedDirectory,context,digest,instant,need,sha,strict
    from runtime import physical
    from manifest_writer import publish
    from datetime import datetime,timezone
    entry=guard.value['writer_registry'];spec=guard.value['spec'];role=spec['files']['writer_configuration']
    raw,_=physical(role['path']);need(digest(raw)==sha(role['sha256']),'WRITER_CONFIGURATION_PIN')
    config=strict(raw);need(context(config['context'])==guard.context and config['producer_sha256']==guard.value['source_pins']['manifest_writer.py'],
                          'WRITER_CONTEXT_SOURCE')
    parent_spec=spec['files']['writer_parent_request'];parent_raw,_=physical(parent_spec['path'])
    parent=strict(parent_raw)
    need(digest(parent_raw)==sha(parent_spec['sha256'])==sha(entry['parent_request_sha256'])
         and parent['schema']=='SERVER_FAMILY_REQUEST_V2' and parent['context']==guard.context
         and parent['operation']=='F4_K12_LAUNCH' and parent['payload']['configuration_sha256']==digest(raw),
         'WRITER_PARENT_REQUEST')
    began,end=instant(entry['start_UTC']),instant(entry['end_UTC'])
    need(type(entry['budget_seconds']) is int and 0<entry['budget_seconds']<=120
         and parent['start_UTC']==entry['start_UTC'] and parent['end_UTC']==entry['end_UTC']
         and parent['budget_seconds']==entry['budget_seconds'],
         'WRITER_WINDOW_AUTHORITY')
    current=clock or (lambda:datetime.now(timezone.utc))
    def recheck():
        now=instant(current());guard.recheck()
        need(began<=now<end and (now-began).total_seconds()<=entry['budget_seconds'],'WRITER_WINDOW')
    recheck()
    capacity=PinnedDirectory(spec['roots']['capacity'],expected=guard.value['measurement']['roots']['capacity'][-1]['identity'])
    bars=PinnedDirectory(spec['roots']['bars'],expected=guard.value['measurement']['roots']['bars'][-1]['identity'])
    try:
        # This claim is never removed or reused after a failed publication.
        name='writer-'+guard.context['session']+'.claim.json'
        recheck();bars.create(name,__import__('common').canonical({'schema':'SERVER_WRITER_CLAIM_V2','mode':guard.mode,
            'context':guard.context,'parent_request_sha256':entry['parent_request_sha256'],'configuration_sha256':digest(raw)}))
        recheck();return publish(config,capacity,bars,recheck=recheck)
    finally:capacity.close();bars.close()


def verified_source(pin):
    import hashlib,json,os,stat
    root=Path(__file__).absolute().parent
    for path in (root,*root.parents):
        if stat.S_ISLNK(path.lstat().st_mode):raise ValueError('BOOTSTRAP_LINK')
    mp=root/'MANIFEST.json';info=mp.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o444:raise ValueError('BOOTSTRAP_MANIFEST')
    raw=mp.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('BOOTSTRAP_MANIFEST_PIN')
    records=json.loads(raw)['files'];names=set()
    for entry in records:
        name=entry['name']
        if name in names or '/' in name or name in ('.','..'):raise ValueError('BOOTSTRAP_MEMBER')
        names.add(name);path=root/name;before=path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or stat.S_IMODE(before.st_mode)!=0o444:raise ValueError('BOOTSTRAP_PERMISSION')
        data=path.read_bytes()
        if before!=path.lstat() or len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('BOOTSTRAP_SOURCE_PIN')
    if Path(__file__).name not in names:raise ValueError('BOOTSTRAP_ENTRY_NOT_ELECTED')
    sys.path.insert(0,str(root))
    return root


def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--acceptance',required=True);p.add_argument('--acceptance-sha256',required=True);a=p.parse_args()
    verified_source(a.manifest_sha256)
    from runtime import RuntimeGuard
    guard=RuntimeGuard(a.acceptance,a.acceptance_sha256)
    sys.stdout.buffer.write(run(guard));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        # Invalid/uncertain output is NOT a published writer wire receipt.
        print('{"schema":"SERVER_K12_WRITER_HOLD_V2","status":"HOLD","operational_GO":false}')
        raise SystemExit(2)
