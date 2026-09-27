import hashlib
import pytest
from app.r2d2_v2_massive_spool import MassiveSpool


def evidence():
    raw=b'[{"ev":"AM"}]'
    return raw, {'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw),'event':{'type':'BAR'}}


def test_reopen_idempotent_exact_bytes(tmp_path):
    raw, receipt=evidence()
    MassiveSpool(tmp_path)(raw,receipt)
    MassiveSpool(tmp_path)(raw,receipt)
    assert [p.read_bytes() for p in (tmp_path/'raw').iterdir()]==[raw]
    assert len(list((tmp_path/'receipts').iterdir()))==1


def test_binding_rejected_before_commit(tmp_path):
    raw, receipt=evidence(); receipt['raw_bytes']+=1
    with pytest.raises(ValueError,match='BINDING'):MassiveSpool(tmp_path)(raw,receipt)
    assert not list((tmp_path/'raw').iterdir())
    assert not list((tmp_path/'receipts').iterdir())


def test_receipt_failure_leaves_only_raw(tmp_path,monkeypatch):
    spool=MassiveSpool(tmp_path); commit=spool._commit
    def fail(directory,data):
        if directory=='receipts':raise OSError('disk full')
        return commit(directory,data)
    monkeypatch.setattr(spool,'_commit',fail)
    with pytest.raises(OSError):spool(*evidence())
    assert len(list((tmp_path/'raw').iterdir()))==1
    assert not list((tmp_path/'receipts').iterdir())
    MassiveSpool(tmp_path)(*evidence())
    assert len(list((tmp_path/'receipts').iterdir()))==1


def test_corrupt_existing_raw_is_not_overwritten(tmp_path):
    raw, receipt=evidence(); spool=MassiveSpool(tmp_path)
    path=tmp_path/'raw'/(receipt['raw_sha256']+'.json'); path.write_bytes(b'bad')
    with pytest.raises(ValueError,match='CONFLICT'):spool(raw,receipt)
    assert path.read_bytes()==b'bad'
    assert not list((tmp_path/'receipts').iterdir())


def test_gap_without_raw(tmp_path):
    MassiveSpool(tmp_path)(None,{'event':{'type':'DATA_GAP'}})
    assert len(list((tmp_path/'receipts').iterdir()))==1
    with pytest.raises(ValueError,match='MISSING_RAW'):
        MassiveSpool(tmp_path)(None,{'event':{'type':'BAR'}})


def test_identical_evidence_reopen_does_not_rewrite(tmp_path,monkeypatch):
    raw,receipt=evidence();MassiveSpool(tmp_path)(raw,receipt)
    def forbidden(*args,**kwargs):
        raise AssertionError('duplicate evidence must not be rewritten')
    monkeypatch.setattr('app.r2d2_v2_massive_spool.secrets.token_hex',forbidden)
    MassiveSpool(tmp_path)(raw,receipt)


def test_existing_raw_symlink_is_refused_before_receipt(tmp_path):
    raw,receipt=evidence();spool=MassiveSpool(tmp_path)
    external=tmp_path/'external';external.write_bytes(raw)
    (tmp_path/'raw'/(receipt['raw_sha256']+'.json')).symlink_to(external)
    with pytest.raises(ValueError,match='CONFLICT'):spool(raw,receipt)
    assert not list((tmp_path/'receipts').iterdir())


@pytest.mark.parametrize('kind', ['fifo', 'oversized', 'symlink'])
def test_competing_destination_is_refused_without_blocking(tmp_path, monkeypatch, kind):
    import os
    raw, receipt = evidence()
    spool = MassiveSpool(tmp_path)
    external = tmp_path / 'external'
    external.write_bytes(raw)
    def race(source, destination, **kwargs):
        destination = tmp_path / 'raw' / destination
        if kind == 'fifo':
            os.mkfifo(destination)
        elif kind == 'symlink':
            destination.symlink_to(external)
        else:
            destination.write_bytes(raw + b'extra')
        raise FileExistsError()
    monkeypatch.setattr('app.r2d2_v2_massive_spool.os.link', race)
    with pytest.raises(ValueError, match='CONTENT_CONFLICT'):
        spool(raw, receipt)
    assert not list((tmp_path / 'receipts').iterdir())
    assert not list((tmp_path / 'raw').glob('.pending-*'))


def test_budget_refuses_before_raw_write(tmp_path):
    raw, receipt = evidence()
    spool = MassiveSpool(tmp_path, max_bytes=len(raw)-1)
    with pytest.raises(ValueError, match='BUDGET_EXHAUSTED'):
        spool(raw, receipt)
    assert not list((tmp_path/'raw').iterdir())
    assert not list((tmp_path/'receipts').iterdir())


def test_budget_retry_does_not_charge_existing_evidence(tmp_path):
    from app.r2d2_v2_sources import canonical
    raw, receipt = evidence()
    cap = len(raw) + len(canonical(receipt))
    spool = MassiveSpool(tmp_path, max_bytes=cap, max_files=2)
    spool(raw, receipt)
    spool(raw, receipt)
    reopened = MassiveSpool(tmp_path, max_bytes=cap, max_files=2)
    reopened(raw, receipt)
    assert reopened.used_bytes == cap and reopened.used_files == 2
    with pytest.raises(ValueError, match='BUDGET_EXHAUSTED'):
        reopened(None, {'event':{'type':'DATA_GAP'}})


def test_budget_counts_orphan_files_after_restart(tmp_path):
    spool = MassiveSpool(tmp_path, max_bytes=32)
    (tmp_path/'raw'/'.pending-orphan').write_bytes(b'x'*32)
    reopened = MassiveSpool(tmp_path, max_bytes=32)
    with pytest.raises(ValueError, match='BUDGET_EXHAUSTED'):
        reopened(*evidence())
    with pytest.raises(ValueError, match='BUDGET_EXHAUSTED'):
        MassiveSpool(tmp_path, max_bytes=31)


def test_budget_receipt_refusal_cannot_commit_receipt(tmp_path):
    raw, receipt = evidence()
    spool = MassiveSpool(tmp_path, max_bytes=len(raw), max_files=1)
    with pytest.raises(ValueError, match='BUDGET_EXHAUSTED'):
        spool(raw, receipt)
    assert len(list((tmp_path/'raw').iterdir())) == 1
    assert not list((tmp_path/'receipts').iterdir())


@pytest.mark.parametrize('location', ['ancestor', 'root', 'raw', 'receipts'])
def test_writer_rejects_symlink_directories_without_external_writes(tmp_path, location):
    import os
    base = tmp_path / 'base'
    root = base / 'spool'
    spool = MassiveSpool(root)
    victim = {'ancestor': base, 'root': root,
              'raw': root / 'raw', 'receipts': root / 'receipts'}[location]
    original = victim.with_name(victim.name + '-original')
    victim.rename(original)
    external = tmp_path / 'external'
    external.mkdir(mode=0o700)
    victim.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match='SPOOL_'):
        spool(*evidence())
    assert list(external.iterdir()) == []


def test_initialization_refuses_ancestor_alias_without_creating_outside(tmp_path):
    external = tmp_path / 'external'
    external.mkdir(mode=0o700)
    alias = tmp_path / 'alias'
    alias.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match='SPOOL_ROOT'):
        MassiveSpool(alias / 'new-spool')
    assert list(external.iterdir()) == []


def test_directory_swap_during_commit_cannot_redirect_write(tmp_path, monkeypatch):
    import os
    spool = MassiveSpool(tmp_path)
    raw, receipt = evidence()
    external = tmp_path / 'external'
    external.mkdir(mode=0o700)
    original_link = os.link
    def swap(source, destination, **kwargs):
        (tmp_path / 'raw').rename(tmp_path / 'raw-original')
        (tmp_path / 'raw').symlink_to(external, target_is_directory=True)
        return original_link(source, destination, **kwargs)
    monkeypatch.setattr('app.r2d2_v2_massive_spool.os.link', swap)
    with pytest.raises(ValueError, match='SPOOL_DIRECTORY'):
        spool(raw, receipt)
    assert list(external.iterdir()) == []
    assert (tmp_path / 'raw-original' / (receipt['raw_sha256'] + '.json')).read_bytes() == raw
    with pytest.raises(ValueError, match='SPOOL_DIRECTORY'):
        spool(raw, receipt)
    assert list((tmp_path / 'receipts').iterdir()) == []


@pytest.mark.parametrize('free', [0, 1024, 1024+len(evidence()[0])-1])
def test_low_disk_refuses_before_any_evidence_write(tmp_path, monkeypatch, free):
 from types import SimpleNamespace
 spool=MassiveSpool(tmp_path,min_free_bytes=1024)
 monkeypatch.setattr('app.r2d2_v2_massive_spool.os.fstatvfs',lambda fd:SimpleNamespace(f_bavail=free,f_frsize=1))
 with pytest.raises(ValueError,match='LOW_DISK'):spool(*evidence())
 assert list((tmp_path/'raw').iterdir())==[]
 assert list((tmp_path/'receipts').iterdir())==[]
 assert spool.used_bytes==0


def test_unreadable_free_space_refuses_closed(tmp_path,monkeypatch):
 spool=MassiveSpool(tmp_path)
 def fail(fd):raise OSError('fixture')
 monkeypatch.setattr('app.r2d2_v2_massive_spool.os.fstatvfs',fail)
 with pytest.raises(ValueError,match='FREE_SPACE_UNVERIFIED'):spool(*evidence())
 assert list((tmp_path/'raw').iterdir())==[]
