"""Fable-only installation preparation and read-only measurement entry.

No timer enable/start, no fallback, no sign or repair command. Stdlib verifies
the entire own source manifest before importing any adapter.
"""
import argparse
import sys
from pathlib import Path


def stable_stat(info):
    """Content/identity metadata; a read-induced atime change is harmless."""
    return tuple(getattr(info,name) for name in ("st_dev","st_ino","st_mode","st_nlink","st_uid","st_gid",
                  "st_size","st_mtime_ns","st_ctime_ns"))


def acceptance_input(raw, manifest_raw, *, clock, channel=None, fixture=False):
    """Read pinned private inputs; originals come from the elected channel.

    This assembler never creates a review, signature, root or timer. Fixture
    injection is an explicit library-only parameter, unavailable in the CLI.
    """
    from common import canonical,digest,fields,need,sha,strict
    from runtime import physical,measure
    from channel import GitHub429
    from acceptance import build
    value=strict(raw)
    fields(value,('schema','inputs','channel'),'ACCEPT_INPUT_FIELDS')
    need(canonical(value)==raw and value['schema']=='SERVER_ACCEPTANCE_INPUT_V2','ACCEPT_INPUT_SCHEMA')
    roles=('spec','measurement','prepared','definition')
    need(set(value['inputs'])==set(roles),'ACCEPT_INPUT_SET')
    originals={}
    for role in roles:
        ref=value['inputs'][role];fields(ref,('path','sha256'),'ACCEPT_INPUT_REFERENCE')
        body,ident=physical(ref['path'])
        need(ident['mode'] in (0o400,0o444) and digest(body)==sha(ref['sha256']),'ACCEPT_INPUT_PIN')
        originals[role]=body
    spec=strict(originals['spec']);measurement=strict(originals['measurement'])
    need(spec['mode']==('FIXTURE' if fixture else 'REAL') and measure(spec)==measurement,'ACCEPT_INPUT_RUNTIME')
    class ReadGuard:
        value={'measurement':measurement}
        def recheck(self):
            need(measure(spec)==measurement,'ACCEPT_INPUT_CHANGED_RUNTIME')
            return digest(originals['measurement'])
    guard=ReadGuard();feed=value['channel']
    if channel is None:
        fields(feed,('token_path','token_sha256','collection_since_UTC'),'ACCEPT_INPUT_CHANNEL')
        registry=strict(physical(spec['files']['registry']['path'])[0])
        need(feed=={k:registry['channel'][k] for k in feed},'ACCEPT_INPUT_CHANNEL_NOT_ELECTED')
        channel=GitHub429(guard,feed['token_path'],feed['token_sha256'],since=feed['collection_since_UTC'])
    return build(originals['spec'],originals['measurement'],originals['prepared'],manifest_raw,
                 originals['definition'],channel=channel,clock=clock,fixture=fixture)


def unit_packet(raw, manifest_pin, *, fixture=False):
    """Exact unit bytes as private data, requiring a later installation act."""
    import base64
    from common import canonical,digest,fields,need,sha,strict
    from runtime import physical
    from installation import units
    value=strict(raw)
    fields(value,('schema','acceptance','source_root','executor_user'),'UNIT_INPUT_FIELDS')
    need(canonical(value)==raw and value['schema']=='SERVER_UNIT_INPUT_V2','UNIT_INPUT_SCHEMA')
    ref=value['acceptance'];fields(ref,('path','sha256'),'UNIT_INPUT_REFERENCE')
    body,ident=physical(ref['path'])
    need(digest(body)==sha(ref['sha256']) and ident['mode']==(0o400 if fixture else 0o444)
         and (fixture or ident['uid']==0),'UNIT_INPUT_ACCEPTANCE_PIN')
    parts=units(body,manifest_pin,source_root=value['source_root'],acceptance_path=ref['path'],
                executor_user=value['executor_user'],fixture=fixture)
    return {'schema':'SERVER_FINITE_UNIT_PACKET_V2','acceptance_sha256':digest(body),'manifest_sha256':manifest_pin,
            'mode':'FIXTURE' if fixture else 'REAL','units':[
                {'name':name,'bytes':len(data),'sha256':digest(data),'body_b64':base64.b64encode(data).decode('ascii')}
                for name,data in sorted(parts.items())], 'timers_installed':0,'operational_GO':False}


def verified_source(pin):
    import hashlib,json,os,stat
    root=Path(__file__).absolute().parent
    for path in (root,*root.parents):
        if stat.S_ISLNK(path.lstat().st_mode):raise ValueError('BOOTSTRAP_LINK')
    mp=root/'MANIFEST.json';info=mp.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o444:raise ValueError('BOOTSTRAP_MANIFEST')
    raw=mp.read_bytes()
    if stable_stat(info)!=stable_stat(mp.lstat()):raise ValueError('BOOTSTRAP_MANIFEST_CHANGED')
    if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('BOOTSTRAP_MANIFEST_PIN')
    records=json.loads(raw)['files'];names=set()
    for entry in records:
        name=entry['name']
        if name in names or '/' in name or name in ('.','..'):raise ValueError('BOOTSTRAP_MEMBER')
        names.add(name);path=root/name;before=path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or stat.S_IMODE(before.st_mode)!=0o444:raise ValueError('BOOTSTRAP_PERMISSION')
        data=path.read_bytes()
        if stable_stat(before)!=stable_stat(path.lstat()) or len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('BOOTSTRAP_SOURCE_PIN')
    if Path(__file__).name not in names:raise ValueError('BOOTSTRAP_ENTRY_NOT_ELECTED')
    sys.path.insert(0,str(root))
    return root


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('prepare','measure','accept','units'))
    p.add_argument('--manifest-sha256',required=True);p.add_argument('--input',required=True);p.add_argument('--input-sha256',required=True)
    a=p.parse_args()
    # -I -S invocation; this one bootstrap source is independently pinned in
    # the installation question/act, just as the service entry is in its unit.
    source=verified_source(a.manifest_sha256)
    from common import canonical,digest,need,sha,strict
    from runtime import physical,measure
    from installation import prepare
    from datetime import datetime,timezone
    raw,_=physical(a.input);need(digest(raw)==sha(a.input_sha256),'INSTALL_INPUT_PIN')
    clock=lambda:datetime.now(timezone.utc).isoformat()
    if a.command=='prepare':result=prepare(raw,clock=clock)
    elif a.command=='measure':
        result=measure(strict(raw));need(result['mode']=='REAL','MEASURE_FIXTURE_NOT_REAL')
    elif a.command=='accept':
        result=strict(acceptance_input(raw,(source/'MANIFEST.json').read_bytes(),clock=clock))
    else:result=unit_packet(raw,a.manifest_sha256)
    # PRIVATE stdout; never public issue text, argv secret or exception log.
    print(canonical(result).decode(),end='');return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('{"schema":"SERVER_INSTALLATION_HOLD_V2","verdict":"HOLD","operational_GO":false}')
        raise SystemExit(2)
