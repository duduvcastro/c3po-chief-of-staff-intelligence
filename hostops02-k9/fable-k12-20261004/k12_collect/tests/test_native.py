"""K12r with the real system calls of its own Native on a private temporary tree that stands in for '/' (tests/oslevel.py;
the data volume on a device of its own by tests/native_support.py). TREE starts no process at all; COLLECT's one
inspect is answered by the emulated engine (tests/native_k12.py). Proves read-only opens by dir_fd without following a
link, secret.env never opened, the persisted receipt and the manifest read and hashed on the host, nothing changed.
Linux, O_NOATIME and real uid 0 only on the Linux-root job (NOT RUN)."""
import json
import os
import stat

import pytest

import family as f
import k12emu as e
import k12r
import native_k12 as n
import native_support

K=k12r.K()
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL

@pytest.fixture
def tree(tmp_path):return n.build_tree(tmp_path)

def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out

def run(root,docs,host):
    before=snapshot(root)
    with native_support.Volume(root) as record:receipt=docs.run(n.with_engine(K.m.Native,host))
    assert snapshot(root)==before and e.SECRET_URL not in json.dumps(receipt) and e.MANIFEST_SHA not in json.dumps(receipt)
    opens=[entry for entry in record.calls if entry['call']=='open'];assert opens and all(entry['flags']&os.O_NOFOLLOW and not entry['flags']&WRITE for entry in opens)
    assert not [entry for entry in opens if entry['path'].endswith('secret.env')] and not record.of('mkdir','link','unlink','umask')
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens)
    return receipt,record

def test_native_tree_reads_the_rows_the_binder_copies(tree):
    host=e.world(K);docs=f.Docs(K,k12r.fields(host,'TREE'),now=e.at(k12r.MOMENTS['TREE']));receipt,record=run(tree,docs,host)
    assert (receipt['status'],receipt['findings'])==('METADATA_ONLY_REQUIRES_REVIEW',[]),receipt['findings']
    for name,path in (('config',e.CONFIG),('manifests',e.MANIFESTS),('journal',e.JOURNAL),('data',e.RELEASE),('receipts',e.RECEIPTS)):
        assert receipt['observed_rows'][name]==n.rows(tree,path),name
    assert host.commands==[] and receipt['boot_id_sha256']==f.BOOT_SHA

def test_native_tree_finds_a_secret_file_open_to_the_group(tree):
    os.chmod(tree/'etc/c3po-reader/secret.env',0o640);host=e.world(K);docs=f.Docs(K,k12r.fields(host,'TREE'),now=e.at(k12r.MOMENTS['TREE']))
    receipt,_=run(tree,docs,host);assert receipt['findings']==['FILE_NOT_ROOT_PRIVATE:secret.env']

def test_native_collect_reads_the_receipt_and_the_manifest_on_the_host(tree):
    host=e.world(K);item=k12r.published(K,host)
    for path in (e.RECEIPTS+'/k12-2026-10-06-w1.writer.json',e.MANIFESTS+'/2026-10-06.json'):
        n.write(tree/path.lstrip('/'),bytes(host.tree.get(path).content))
    docs=f.Docs(K,dict(k12r.fields(host,'COLLECT'),parent_rows=n.chains(tree,['manifests','receipts','data'])),now=e.at(k12r.MOMENTS['COLLECT']))
    receipt,record=run(tree,docs,host)
    assert (receipt['status'],receipt['window_verdict'],receipt['manifest_sha256_equals_the_line'])==('METADATA_ONLY_REQUIRES_REVIEW','VERIFIED',True),receipt['window_reason']
    reads=[entry['path'] for entry in record.calls if entry['call']=='open' and not entry['flags']&os.O_DIRECTORY]
    assert '/var/lib/c3po-reader/capacity-receipts/k12-2026-10-06-w1.writer.json' in reads and '/etc/c3po-bar/manifests/2026-10-06.json' in reads
    assert '/mnt/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json' in reads and not [path for path in reads if path.startswith('/mnt/') and 'r2d2-v2-release-20261005/' not in path]
    os.chmod(tree/'etc/c3po-bar/manifests/2026-10-06.json',0o644);receipt,_=run(tree,docs,host)
    assert (receipt['window_verdict'],receipt['window_reason'])==('UNCERTAIN','MANIFEST_NOT_AS_THE_LINE_SAYS')
    (tree/'etc/c3po-bar/manifests/2026-10-06.json').unlink();os.symlink('/etc/passwd',str(tree/'etc/c3po-bar/manifests/2026-10-06.json'))
    receipt,record=run(tree,docs,host);assert receipt['items']['manifest']['type']=='symlink' and not [entry for entry in record.calls if 'passwd' in str(entry.get('path'))]
