from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_proxy_configs_enforce_https_and_security_headers() -> None:
    caddy = (ROOT / "Caddyfile").read_text(encoding="utf-8")
    nginx = (ROOT / "c3po" / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    for config in (caddy, nginx):
        assert "Strict-Transport-Security" in config
        assert "Content-Security-Policy" in config
        assert "frame-ancestors 'none'" in config
    assert "CF-Visitor" in caddy
    assert "redir @cloudflare_http https://{host}{uri} 308" in caddy
    assert "$http_cf_visitor" in nginx
    assert "return 308 https://$host$request_uri" in nginx
