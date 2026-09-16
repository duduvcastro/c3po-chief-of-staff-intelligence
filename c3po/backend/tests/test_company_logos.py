import pytest
from app import company_logos as logos

SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'

def test_fallback_and_success_cache(monkeypatch):
    calls = []
    def fetch(url):
        calls.append(url)
        return b'<html>not a logo</html>' if len(calls) == 1 else SVG
    monkeypatch.setattr(logos, 'fetch_logo', fetch)
    service = logos.CompanyLogoService()
    assert service.get('newa3.sa') == (SVG, 'image/svg+xml')
    assert service.get('NEWA3') == (SVG, 'image/svg+xml')
    assert calls == ['https://icons.brapi.dev/icons/NEWA3.svg','https://financialmodelingprep.com/image-stock/NEWA3.SA.png']

def test_failure_expires_and_recovers(monkeypatch):
    now = [0.0]
    calls = []
    monkeypatch.setattr(logos,'monotonic',lambda: now[0])
    def fetch(url):
        calls.append(url)
        return b'bad' if now[0] < 300 else SVG
    monkeypatch.setattr(logos,'fetch_logo',fetch)
    service=logos.CompanyLogoService()
    assert service.get('NEWA3') is None
    assert service.get('NEWA3') is None
    assert len(calls)==2
    now[0]=301
    assert service.get('NEWA3') == (SVG,'image/svg+xml')
    assert len(calls)==3

@pytest.mark.parametrize('symbol',['../ABC3','https://example.com','AAPL.US','ABCDE3','ABC3?x=1'])
def test_invalid_symbols_never_fetch(monkeypatch,symbol):
    monkeypatch.setattr(logos,'fetch_logo',lambda url: pytest.fail('unexpected fetch'))
    with pytest.raises(ValueError): logos.CompanyLogoService().get(symbol)

@pytest.mark.parametrize('data',[b'<html/>',b'<svg><script/></svg>',b'<svg onload="x"/>',b'<svg><image href="https://example.com"/></svg>',b'<!DOCTYPE svg><svg/>',b'<svg><path fill="url(https://example.com)"/></svg>',b'x'*(logos.MAX_BYTES+1)])
def test_invalid_payloads(data):
    assert logos.validate_logo(data,'https://icons.brapi.dev/icons/ABCD3.svg') is None

def test_placeholder_rejected_even_at_ticker_url(monkeypatch):
    monkeypatch.setattr(logos,'PLACEHOLDERS',{logos.sha256(SVG).hexdigest()})
    assert logos.validate_logo(SVG,'https://icons.brapi.dev/icons/ABCD3.svg') is None

def test_cache_bounded(monkeypatch):
    monkeypatch.setattr(logos,'MAX_ENTRIES',2)
    monkeypatch.setattr(logos,'fetch_logo',lambda url: SVG)
    service=logos.CompanyLogoService()
    for symbol in ['AAAA3','BBBB3','CCCC3']: service.get(symbol)
    assert list(service._cache)==['BBBB3','CCCC3']

def test_b3_alphanumeric_issuer(monkeypatch):
    monkeypatch.setattr(logos,'fetch_logo',lambda url: SVG)
    assert logos.CompanyLogoService().get('B3SA3') == (SVG,'image/svg+xml')

def test_logo_route_contract(monkeypatch):
    from app import main
    from app.access_control import required_permissions
    from fastapi.testclient import TestClient
    path='/api/v1/chewie-fundamentals/B3/NEWA3/logo'
    assert required_permissions(path)==('chewie',)
    monkeypatch.setattr(main.company_logos,'get',lambda symbol:(SVG,'image/svg+xml'))
    with TestClient(main.app) as client:
        response=client.get(path)
        assert response.status_code==200
        assert response.content==SVG
        assert response.headers['x-content-type-options']=='nosniff'
        monkeypatch.setattr(main.company_logos,'get',lambda symbol:None)
        response=client.get(path)
        assert response.status_code==404
        assert response.headers['cache-control']=='no-store'
