from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Database
from app.portfolio_accounting import replay


def row(**updates):
    return dict(dict(request_id=str(uuid4()),symbol='AMZN',market='NASDAQ',kind='buy',effective_date='2025-01-02',quantity='10',total='100',fees='0'),**updates)


def test_concurrent_retry_does_not_duplicate_and_conflict_is_rejected():
    db=Database(Settings())
    e=row()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _:db.write_portfolio_event(e),range(8)))
    assert len(db.list_portfolio_events())==1
    with pytest.raises(ValueError): db.write_portfolio_event(dict(e,total='200'))


def test_void_cannot_break_later_sale_and_remove_watchlist_preserves_history():
    db=Database(Settings());buy=row();sell=row(kind='sell',quantity='5',effective_date='2025-02-02')
    db.add_realtime_portfolio('AMZN','Amazon','NASDAQ')
    db.write_portfolio_event(buy);db.write_portfolio_event(sell)
    with pytest.raises(ValueError):db.void_portfolio_event(buy['request_id'])
    assert len(db.list_portfolio_events())==2
    db.delete_realtime_portfolio('AMZN')
    assert len(db.list_portfolio_events())==2
    db.void_portfolio_event(sell['request_id'])
    assert replay(db.list_portfolio_events())['AMZN'].quantity==10
    with pytest.raises(ValueError):db.write_portfolio_event(sell)


def test_backdated_sale_replays_whole_ledger_before_commit():
    db=Database(Settings());db.write_portfolio_event(row())
    db.write_portfolio_event(row(kind='sell',effective_date='2025-03-01',quantity='8'))
    with pytest.raises(ValueError):db.write_portfolio_event(row(kind='sell',effective_date='2025-02-01',quantity='5'))
    assert replay(db.list_portfolio_events())['AMZN'].quantity==2


@pytest.fixture
def account_api(monkeypatch):
    from app import main
    db=Database(Settings())
    db.add_realtime_portfolio('AMZN','Amazon','NASDAQ')
    monkeypatch.setattr(main,'database',db)
    monkeypatch.setattr(main.settings,'auth_required',False)
    return main,db,TestClient(main.app)


def test_http_validation_and_persistence(account_api):
    main,db,client=account_api
    payload=row();payload.pop('market')
    response=client.post('/api/v1/realtime/portfolio/events',json=payload)
    assert response.status_code==201
    assert client.post('/api/v1/realtime/portfolio/events',json=payload).status_code==201
    assert len(db.list_portfolio_events())==1
    assert client.post('/api/v1/realtime/portfolio/events',json=dict(payload,quantity='NaN')).status_code==422
    assert client.post('/api/v1/realtime/portfolio/events',json=dict(payload,effective_date='2099-01-01')).status_code==422
    assert client.post('/api/v1/realtime/portfolio/events',json=dict(payload,symbol='MISSING')).status_code==422
    assert client.post(f"/api/v1/realtime/portfolio/events/{payload['request_id']}/void").status_code==200
    assert not db.list_portfolio_events()


def test_member_can_read_but_cannot_write_or_void(account_api,monkeypatch):
    main,db,client=account_api
    monkeypatch.setattr(main.settings,'auth_required',True)
    monkeypatch.setattr(main.auth_service,'authenticate',lambda _:dict(role='member',permissions=['realtime'],capabilities=['read','delete']))
    monkeypatch.setattr(main.portfolio_account,'snapshot',lambda:dict(events=[],summary=None,periods=[],fx=None))
    payload=row();payload.pop('market')
    assert client.get('/api/v1/realtime/portfolio/account').status_code==200
    assert client.post('/api/v1/realtime/portfolio/events',json=payload).status_code==403
    assert client.post(f"/api/v1/realtime/portfolio/events/{payload['request_id']}/void").status_code==403
    monkeypatch.setattr(main.auth_service,'authenticate',lambda _:dict(role='owner',permissions=['realtime']))
    assert client.post('/api/v1/realtime/portfolio/events',json=payload).status_code==201
