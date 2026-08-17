from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from app.news import SOURCE_CONFIG, NewsService


NOW = datetime(2026, 8, 16, 18, 0, tzinfo=timezone.utc)


def rss_payload() -> bytes:
    stories = [
        ("Mercados reagem à decisão de juros do banco central", "Sun, 16 Aug 2026 17:40:00 GMT"),
        ("Economia cresce e empresas revisam projeções", "Sun, 16 Aug 2026 17:00:00 GMT"),
        ("Dólar recua com novas projeções de inflação", "Sun, 16 Aug 2026 16:00:00 GMT"),
        ("Governo anuncia nova política para energia", "Sun, 16 Aug 2026 15:00:00 GMT"),
        ("Tecnologia e inteligência artificial movimentam ações", "Sun, 16 Aug 2026 14:00:00 GMT"),
        ("Campeonato tem rodada decisiva no futebol", "Sun, 16 Aug 2026 17:55:00 GMT"),
        ("Notícia com horário do futuro", "Mon, 17 Aug 2026 12:00:00 GMT"),
        ("Mercados reagem à decisão de juros do banco central", "Sun, 16 Aug 2026 17:35:00 GMT"),
    ]
    items = "".join(
        f"<item><title>{title}</title><link>https://example.com/{index}</link>"
        f"<description>Resumo sobre mercado, economia e política.</description><pubDate>{published}</pubDate></item>"
        for index, (title, published) in enumerate(stories)
    )
    return f"<?xml version='1.0'?><rss><channel>{items}</channel></rss>".encode()


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeNewsHttp:
    def __init__(self, *, fail_url: str | None = None) -> None:
        self.fail_url = fail_url
        self.calls: list[str] = []
        self.lock = Lock()

    def get(self, url: str) -> FakeResponse:
        with self.lock:
            self.calls.append(url)
        if url == self.fail_url:
            raise RuntimeError("feed unavailable")
        return FakeResponse(rss_payload())


def test_news_snapshot_returns_five_ranked_items_per_source() -> None:
    service = NewsService(http=FakeNewsHttp(), now_provider=lambda: NOW)

    payload = service.snapshot(refresh=True)

    assert payload.source_count == 4
    assert payload.item_count == 20
    assert [group.code for group in payload.groups] == ["globo", "uol", "bloomberg", "cnbc"]
    assert all(group.status == "fresh" for group in payload.groups)
    assert all(len(group.items) == 5 for group in payload.groups)
    assert all([item.rank for item in group.items] == [1, 2, 3, 4, 5] for group in payload.groups)
    assert all("futebol" not in " ".join(item.title for item in group.items).lower() for group in payload.groups)
    assert all("futuro" not in " ".join(item.title for item in group.items).lower() for group in payload.groups)


def test_news_snapshot_keeps_source_available_when_one_feed_fails() -> None:
    failed_url = SOURCE_CONFIG[0]["feeds"][0]
    service = NewsService(http=FakeNewsHttp(fail_url=failed_url), now_provider=lambda: NOW)

    payload = service.snapshot(refresh=True)

    globo = payload.groups[0]
    assert globo.status == "partial"
    assert len(globo.items) == 5
    assert globo.errors
    assert all(group.status == "fresh" for group in payload.groups[1:])


def test_news_snapshot_uses_cache_until_explicit_refresh() -> None:
    http = FakeNewsHttp()
    service = NewsService(http=http, now_provider=lambda: NOW)

    service.snapshot(refresh=True)
    first_call_count = len(http.calls)
    service.snapshot()
    assert len(http.calls) == first_call_count

    service.snapshot(refresh=True)
    assert len(http.calls) == first_call_count * 2
