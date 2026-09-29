"""Composition checks with synthetic ACKs; not PostgreSQL provenance proof."""
import pytest
from app import r2d2_v2_massive_retention as r
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_sources import SourceUnavailable


def setup(tmp_path,monkeypatch):
    j=MassiveJournal(tmp_path)
    for i in range(5):j(None,{'event':{'type':'DATA_GAP','session':'2026-09-25','fixture':i}})
    def bound(journal,store,**kwargs):
        p=r._plan_retention_locked(journal,committed_sequence=store,
            retain_from_session=kwargs['retain_from_session'],max_records=kwargs['max_records'])
        return {**p,'ack':{'committed_sequence':store}}
    monkeypatch.setattr(r,'_plan_committed_retention_locked',bound)
    consumers={name:{'store':seq,'epoch':28,'release_sha':'a'*64} for name,seq in [('fast',5),('slow',2)]}
    return j,consumers


def call(j,consumers,required=('fast','slow')):
    return r.plan_consumers_retention(j,consumers,required_consumers=required,now=None,retain_from_session='2026-09-26')


def test_slowest_ack_preserves_predecessor(tmp_path,monkeypatch):
    j,c=setup(tmp_path,monkeypatch);before=j.path.read_bytes();p=call(j,c)
    assert p['committed_sequence']==2 and p['prune_through']==1
    assert set(p['consumer_acks'])=={'fast','slow'}
    assert p['consumer_inventory_authority_verified'] is False
    assert j.path.read_bytes()==before


@pytest.mark.parametrize('required',[(),('fast','fast'),('fast',),('fast','slow','missing')])
def test_inventory_mismatch_refuses(tmp_path,monkeypatch,required):
    j,c=setup(tmp_path,monkeypatch)
    with pytest.raises(SourceUnavailable,match='CONSUMER'):call(j,c,required)


def test_append_between_consumer_snapshots_refuses(tmp_path,monkeypatch):
    j,c=setup(tmp_path,monkeypatch);original=r._plan_committed_retention_locked
    def changing(journal,store,**kwargs):
        p=original(journal,store,**kwargs)
        if store==5:journal(None,{'event':{'type':'DATA_GAP','session':'2026-09-25','fixture':99}})
        return p
    monkeypatch.setattr(r,'_plan_committed_retention_locked',changing)
    with pytest.raises(SourceUnavailable,match='SNAPSHOT_CHANGED'):call(j,c)
