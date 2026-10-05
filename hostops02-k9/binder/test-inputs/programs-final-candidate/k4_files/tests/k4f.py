"""Fixtures of K4 modes CHAIN_STATIC, PINS and LAUNCHER: the emulated host after the provisioning of 2026-10-03 (the
reader's configuration directory and the capacity tree, all root:root 0700), the request plans built from it exactly
as a binder would copy them from read-only receipts, and SYNTHETIC bytes for everything that does not exist yet: the
static capacity config (its chain pins are the real ones, compiled into the source; every other hash is the SHA-256
of a label), the launcher (comment lines that say so), the two unit texts (the real mount and journal lines, nothing
else). Nothing here is authoritative."""
import base64
import json
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
EPOCH='R2D2-V2-SHADOW-2026-10-05'
READER='/etc/c3po-reader'
CAPACITY='/var/lib/c3po-capacity'
DOCUMENTS=CAPACITY+'/documents'
CONFIG=CAPACITY+'/config'
LAUNCHER_DIRECTORY=READER+'/launcher'
LAUNCHER_FILE=LAUNCHER_DIRECTORY+'/reader_launcher.py'
UNITS='/etc/systemd/system'
PINS=READER+'/pins.env'
STATIC=CONFIG+'/week.static.capacity.json'
def writer_path(m):return CONFIG+'/manifest_writer-'+m.K4_WRITER[0]+'.py'
JOURNAL_HOST='/var/lib/c3po-bar/journal'
JOURNAL='/c3po-bar-journal'
SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
SOURCE_TARGET='/c3po-source'
RELEASE='fc2f64ea252f9996ba62cd8bb10411ea0cbc3a351c15b8612de88390ccbdcaa1'
PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
SESSIONS=['2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09']
LAUNCHER=b''.join(b'# SYNTHETIC TEST BYTES %03d: NOT THE READER LAUNCHER, never delivered anywhere\n'%index for index in range(60))

def b64(raw):return base64.b64encode(raw).decode('ascii')
def label(text):return f.sha(text.encode())
def K():return f.load(DIRECTORY)
def member(raw):return {'content_b64':b64(raw),'sha256':f.sha(raw),'bytes':len(raw)}

def chain_names(m):return [(label_,name,digest) for label_,name,digest,_,_ in m.K4_CHAIN_DOCUMENTS]

def static_config(m,**changes):
    """A static config in the documents tool's shape, canonical bytes. Its seven chain pins are the compiled ones."""
    pins={label_:{'file':name,'sha256':digest} for label_,name,digest in chain_names(m)}
    pins['TEMPLATE']={'file':'session=2026-10-05.template.md','sha256':label('template')}
    config={'schema':'R2D2_CAPACITY_BOOTSTRAP_V3','r2d2_v2_capacity_veto_mode':'DISPATCH_AND_DERIVATION_ONLY',
            'identity':{'epoch':EPOCH,'namespace':EPOCH,'first_session':'2026-10-05','authorized_sessions':list(SESSIONS),
                        'document_order_sha':label('document order'),'runtime_order_sha':label('runtime order')},
            'calendar_pin_sha':label('calendar pin'),'release_sha':RELEASE,'package_sha':PACKAGE,
            'roots':{name:{'path':'/c3po-capacity/'+name,'identity':label('identity '+name)} for name in ('documents','payload','go')},
            'document_pins':pins,'veto_views':{'2026-10-05':{'file':'session=2026-10-05.view-primary.md','sha256':label('view')}},
            'restore_revocation':None}
    config.update(changes)
    return f.canonical(config)

def producer_unit(journal=JOURNAL,source=JOURNAL_HOST):
    return ('[Service]\nExecStart=/usr/bin/docker run --rm --init --restart no --name c3po-massive --pull never \\\n'
            '  --mount type=bind,source=%s,target=%s \\\n'
            '  --mount type=bind,source=/var/lib/c3po-bar/supervisor,target=/var/lib/c3po-bar/supervisor \\\n'
            '  --mount type=bind,source=/etc/c3po-bar,target=/etc/c3po-bar,readonly \\\n'
            '  sha256:%s \\\n'
            '  python -B -m app.r2d2_v2_massive_supervisor --journal-root %s --manifest-directory /etc/c3po-bar/manifests '
            '--token-file /etc/c3po-bar/token --state-root /var/lib/c3po-bar/supervisor\n'%(source,journal,'1'*64,journal)).encode()

def reader_unit(journal=JOURNAL,source=JOURNAL_HOST,capacity=CAPACITY,launcher=LAUNCHER_DIRECTORY,source_root=SOURCE_ROOT,source_target=SOURCE_TARGET):
    return ('[Service]\nExecStart=/usr/bin/docker run --rm --init --restart no --name c3po-reader --pull never \\\n'
            '  --env-file /etc/c3po-reader/secret.env \\\n'
            '  --mount type=bind,source=/mnt/day-d-data,target=/app/day-d-data,readonly \\\n'
            '  --mount type=bind,source=%s,target=%s,readonly \\\n'
            '  --mount type=bind,source=%s,target=%s,readonly \\\n'
            '  --mount type=bind,source=%s,target=/c3po-capacity,readonly \\\n'
            '  --mount type=bind,source=%s,target=/c3po-reader,readonly \\\n'
            '  sha256:%s \\\n'
            '  python -I -B /c3po-reader/reader_launcher.py\n'%(source,journal,source_root,source_target,capacity,launcher,'1'*64)).encode()

def provisioned(host):
    """What the provisioning of 2026-10-03 left (E2): the reader's directories and the capacity tree, root:root 0700."""
    for path in (READER,READER+'/docker-cli','/var/lib/c3po-reader','/var/lib/c3po-reader/capacity-receipts',CAPACITY,DOCUMENTS,CONFIG,
                 CAPACITY+'/payload',CAPACITY+'/go','/var/lib/c3po-bar',JOURNAL_HOST):host.tree.add(path,mode=0o700)
    host.tree.add('/var/lib/c3po',mode=0o700);host.tree.add(SOURCE_ROOT,mode=0o700)      # K4 E0 (placement of decision 6)
    return host

def delivered_before_pins(host,m,config=None,launcher=LAUNCHER,producer=None,reader=None):
    """What B5, A8 and B2 leave before B6: the static config, the launcher, the two units."""
    host.tree.add(STATIC,kind='file',mode=0o600,content=config if config is not None else static_config(m))
    host.tree.add(LAUNCHER_DIRECTORY,mode=0o700);host.tree.add(LAUNCHER_FILE,kind='file',mode=0o600,content=launcher)
    host.tree.add(UNITS+'/c3po-massive.service',kind='file',mode=0o644,content=producer if producer is not None else producer_unit())
    host.tree.add(UNITS+'/c3po-reader.service',kind='file',mode=0o644,content=reader if reader is not None else reader_unit())
    return host

def pins_values(m,config=None,launcher=LAUNCHER,**changes):
    values={'C3PO_BUILD_SHA':REVISION,'C3PO_R2D2_V2_SHADOW_RELEASE_FILE':'/app/day-d-data/r2d2-v2-release-20261005/release.json',
            'C3PO_R2D2_V2_SHADOW_RELEASE_SHA':RELEASE,'C3PO_R2D2_V2_SHADOW_SOURCE_DIR':SOURCE_TARGET,
            'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR':'/app/day-d-data/provider=eodhd/microstructure/raw','C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR':JOURNAL,
            'C3PO_R2D2_V2_CAPACITY_REQUIRED':'true','C3PO_R2D2_V2_CAPACITY_VETO_MODE':'DISPATCH_AND_DERIVATION_ONLY',
            'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE':'/c3po-capacity/config/week.static.capacity.json',
            'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA':f.sha(config if config is not None else static_config(m)),
            'C3PO_R2D2_V2_SHADOW_POLL_SECONDS':'1.0','C3PO_READER_LAUNCHER_SHA256':f.sha(launcher)}
    values.update(changes);return values

def render(values,m):return ''.join(name+'='+values[name]+'\n' for name in m.PINS_NAMES).encode()

def fields(host,mode,m,config=None,launcher=LAUNCHER):
    if mode=='CHAIN_STATIC':
        delivery={'documents_parent':hostemu.rows(host,DOCUMENTS),'config_parent':hostemu.rows(host,CONFIG),
                  'static_config':member(config if config is not None else static_config(m))}
    elif mode=='PINS':
        values=pins_values(m);raw=render(values,m)
        delivery={'reader_parent':hostemu.rows(host,READER),'config_parent':hostemu.rows(host,CONFIG),'unit_parent':hostemu.rows(host,UNITS),
                  'source_chain':hostemu.rows(host,SOURCE_ROOT),'journal_chain':hostemu.rows(host,JOURNAL_HOST),
                  'values':values,'sha256':f.sha(raw),'bytes':len(raw),
                  'producer_unit_sha256':f.sha(bytes(host.tree.get(UNITS+'/c3po-massive.service').content)),
                  'reader_unit_sha256':f.sha(bytes(host.tree.get(UNITS+'/c3po-reader.service').content))}
    elif mode=='WRITER':
        delivery={'config_parent':hostemu.rows(host,CONFIG),'writer_sha256':m.K4_WRITER[0]}
    else:
        delivery={'reader_parent':hostemu.rows(host,READER),'launcher':member(launcher)}
    return {'mode':mode,'delivery':delivery,'evidence_boot_id_sha256':f.BOOT_SHA}

def world(mode,k=None):
    k=k or K();host=provisioned(f.world(k))
    if mode=='PINS':delivered_before_pins(host,k.m)
    return k,host

def case(now=None,mode='CHAIN_STATIC',**options):
    """(docs, host): a bound fixture that completes on the emulated host of that mode."""
    k,host=world(mode);return f.Docs(k,fields(host,mode,k.m),now=now,**options),host

def state_of(host):
    """Everything a run could change on the emulated host."""
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)
