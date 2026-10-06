"""Fixtures of the reader units: the emulated host after E1 (journal root), A9 (the real catalogue in it) and E3 (the
producer unit installed), and the request plan built from it exactly as a binder would copy it from read-only
receipts. The producer bytes are the render of the e3 request (tests/unit_texts.py, copied by command); every other
number is synthetic. Nothing here is authoritative."""
import json
from pathlib import Path

import family as f
import hostemu
import unit_texts

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
UNITS='/etc/systemd/system'
JOURNAL='/var/lib/c3po-bar/journal'
DATA=hostemu.DATA
PRODUCER_PATH=UNITS+'/c3po-massive.service'
NAMES=[('READER_SERVICE','c3po-reader.service'),('READER_TIMER','c3po-reader.timer'),('READER_ALERT','c3po-reader-alert.service')]
EPOCH_FILE=b'{"schema":"MASSIVE_SESSION_ROOT_V1","synthetic":true}'

def K():return f.load(DIRECTORY)

def producer_bytes():
    raw=unit_texts.PRODUCER_TEMPLATE
    for name,value in unit_texts.PRODUCER_VALUES.items():raw=raw.replace(('@%s@'%name).encode('ascii'),value.encode('ascii'))
    assert f.sha(raw)==unit_texts.PRODUCER_RENDER_SHA256
    return raw

def prepared(host):
    """E1's directories (placement A), A9's two catalogue files in the journal root, E3's producer unit."""
    hostemu.provision_supervisor(host)
    host.tree.add(JOURNAL+'/epoch.json',kind='file',mode=0o600,content=EPOCH_FILE)
    host.tree.add(JOURNAL+'/maintenance.lock',kind='file',mode=0o600,content=b'')
    host.tree.add(PRODUCER_PATH,kind='file',mode=0o644,content=producer_bytes())
    return host

def renders(k=None):return (k or K()).m.rendered_units()

def unit_rows(k=None,expect=None):
    """The three signed unit rows; expect maps a key to a signed identity {device, inode, links} (default ABSENT)."""
    done=renders(k);expect=expect or {}
    return [{'key':key,'destination_name':name,'expect':expect.get(key,'ABSENT'),'rendered_sha256':f.sha(done[key]),'rendered_bytes':len(done[key])}
            for key,name in NAMES]

def fields(host,k=None,expect=None,leftovers=()):
    return {'unit_rows':hostemu.rows(host,UNITS),'journal_rows':hostemu.rows(host,JOURNAL),'data_rows':hostemu.rows(host,DATA),
            'units':unit_rows(k,expect),'acknowledged_leftovers':[dict(item) for item in leftovers],'evidence_boot_id_sha256':f.BOOT_SHA}

def world(k=None):return prepared(f.world(k or K()))

def case(now=None,**options):
    """(docs, host): a bound fixture that completes on a fresh emulated host."""
    k=K();host=world(k)
    return f.Docs(k,fields(host,k),now=now,**options),host

def state_of(host):
    """Everything a run could change on the emulated host."""
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)

def installed(host,key,k=None):
    """Put one unit in place as a completed earlier run would have left it; returns its signed identity."""
    name=dict(NAMES)[key];node=host.tree.add(UNITS+'/'+name,kind='file',mode=0o644,content=renders(k)[key])
    return {'device':node.dev,'inode':node.ino,'links':node.nlink}
