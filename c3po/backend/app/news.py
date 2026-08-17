from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import html
import re
from threading import Lock
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx

from .schemas import NewsItem, NewsResponse, NewsSourceGroup


SOURCE_CONFIG: tuple[dict[str, Any], ...] = (
    {
        "code": "globo",
        "name": "Globo.com",
        "homepage_url": "https://g1.globo.com/",
        "feeds": (
            "https://g1.globo.com/dynamo/rss2.xml",
            "https://g1.globo.com/dynamo/economia/rss2.xml",
            "https://g1.globo.com/dynamo/politica/rss2.xml",
        ),
    },
    {
        "code": "uol",
        "name": "UOL",
        "homepage_url": "https://www.uol.com.br/",
        "feeds": (
            "https://www.uol.com.br/rss.xml",
            "https://rss.uol.com.br/feed/noticias.xml",
            "https://rss.uol.com.br/feed/economia.xml",
        ),
    },
    {
        "code": "bloomberg",
        "name": "Bloomberg",
        "homepage_url": "https://www.bloomberg.com/",
        "feeds": (
            "https://feeds.bloomberg.com/markets/news.rss",
            "https://feeds.bloomberg.com/economics/news.rss",
            "https://feeds.bloomberg.com/politics/news.rss",
        ),
    },
    {
        "code": "cnbc",
        "name": "CNBC",
        "homepage_url": "https://www.cnbc.com/",
        "feeds": (
            "https://www.cnbc.com/id/100003114/device/rss/rss.html",
            "https://www.cnbc.com/id/10001147/device/rss/rss.html",
            "https://www.cnbc.com/id/100727362/device/rss/rss.html",
        ),
    },
)

RELEVANCE_TERMS = {
    "market": 11,
    "markets": 11,
    "mercado": 11,
    "economia": 10,
    "economy": 10,
    "business": 9,
    "negocios": 9,
    "bolsa": 9,
    "stocks": 9,
    "acoes": 9,
    "juros": 9,
    "interest rate": 9,
    "inflacao": 9,
    "inflation": 9,
    "banco central": 8,
    "central bank": 8,
    "fed": 8,
    "copom": 8,
    "dolar": 7,
    "dollar": 7,
    "pib": 7,
    "gdp": 7,
    "governo": 6,
    "government": 6,
    "politica": 6,
    "politics": 6,
    "eleicao": 6,
    "election": 6,
    "energia": 6,
    "energy": 6,
    "petroleo": 6,
    "oil": 6,
    "tecnologia": 5,
    "technology": 5,
    "ai": 5,
    "inteligencia artificial": 5,
    "tarifa": 5,
    "tariff": 5,
    "guerra": 5,
    "war": 5,
}

NOISE_TERMS = (
    "futebol",
    "campeonato",
    "celebridade",
    "novela",
    "reality show",
    "horoscopo",
    "loteria",
    "concurso publico",
    "promocao",
    "cupom",
)

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
NON_WORD_RE = re.compile(r"[^a-z0-9]+")


class NewsService:
    def __init__(
        self,
        http: httpx.Client | Any | None = None,
        *,
        cache_seconds: int = 300,
        now_provider: Any | None = None,
    ) -> None:
        self.http = http or httpx.Client(
            timeout=9,
            follow_redirects=True,
            headers={"User-Agent": "C3PO-Chief-of-Staff/1.0 (+private news dashboard)"},
        )
        self.cache_seconds = max(60, cache_seconds)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._cache: tuple[datetime, NewsResponse] | None = None
        self._lock = Lock()

    def snapshot(self, *, refresh: bool = False) -> NewsResponse:
        now = self._now()
        with self._lock:
            if not refresh and self._cache and now - self._cache[0] < timedelta(seconds=self.cache_seconds):
                return self._cache[1].model_copy(deep=True)

        with ThreadPoolExecutor(max_workers=len(SOURCE_CONFIG)) as executor:
            futures = {executor.submit(self._source_group, config, now): config for config in SOURCE_CONFIG}
            groups_by_code: dict[str, NewsSourceGroup] = {}
            for future in as_completed(futures):
                config = futures[future]
                try:
                    group = future.result()
                except Exception as exc:  # A broken outlet must not hide the other sources.
                    group = NewsSourceGroup(
                        code=config["code"],
                        name=config["name"],
                        homepage_url=config["homepage_url"],
                        status="unavailable",
                        fetched_at=None,
                        items=[],
                        errors=[self._friendly_error(exc)],
                    )
                groups_by_code[group.code] = group

        groups = [groups_by_code[config["code"]] for config in SOURCE_CONFIG]
        response = NewsResponse(
            generated_at=now,
            refresh_seconds=self.cache_seconds,
            source_count=sum(1 for group in groups if group.items),
            item_count=sum(len(group.items) for group in groups),
            groups=groups,
        )
        with self._lock:
            self._cache = (now, response.model_copy(deep=True))
        return response

    def _source_group(self, config: dict[str, Any], now: datetime) -> NewsSourceGroup:
        candidates: list[NewsItem] = []
        errors: list[str] = []
        feeds = tuple(config["feeds"])
        with ThreadPoolExecutor(max_workers=len(feeds)) as executor:
            futures = {executor.submit(self._fetch_feed, url, config["name"], now): url for url in feeds}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    candidates.extend(future.result())
                except Exception as exc:
                    errors.append(f"{urlparse(url).netloc}: {self._friendly_error(exc)}")

        deduplicated: dict[str, NewsItem] = {}
        for item in candidates:
            key = self._normal_key(item.title)
            existing = deduplicated.get(key)
            if existing is None or item.score > existing.score:
                deduplicated[key] = item
        ordered = sorted(
            deduplicated.values(),
            key=lambda item: (item.score, item.published_at or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )[:5]
        for rank, item in enumerate(ordered, start=1):
            item.rank = rank

        if ordered and errors:
            status = "partial"
        elif ordered:
            status = "fresh"
        else:
            status = "unavailable"
        return NewsSourceGroup(
            code=config["code"],
            name=config["name"],
            homepage_url=config["homepage_url"],
            status=status,
            fetched_at=now if ordered else None,
            items=ordered,
            errors=errors or ([] if ordered else ["Nenhuma notícia válida encontrada."]),
        )

    def _fetch_feed(self, url: str, source: str, now: datetime) -> list[NewsItem]:
        response = self.http.get(url)
        response.raise_for_status()
        return self._parse_feed(response.content, source, now)

    def _parse_feed(self, payload: bytes, source: str, now: datetime) -> list[NewsItem]:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as original_error:
            root = None
            for encoding in ("iso-8859-1", "cp1252"):
                try:
                    root = ET.fromstring(payload.decode(encoding))
                    break
                except (UnicodeDecodeError, ET.ParseError):
                    continue
            if root is None:
                raise original_error
        entries = [element for element in root.iter() if self._local_name(element.tag) in {"item", "entry"}]
        items: list[NewsItem] = []
        for entry in entries:
            title = self._child_text(entry, ("title",))
            link = self._entry_link(entry)
            description = self._child_text(entry, ("description", "summary", "content", "encoded"))
            if not title:
                title = description
            if not title or not link:
                continue
            published_raw = self._child_text(entry, ("pubDate", "published", "updated", "date"))
            published_at = self._parse_date(published_raw)
            clean_title = self._clean_text(title, limit=240)
            clean_summary = self._clean_text(description, limit=300)
            score = self._score(clean_title, clean_summary, published_at, now)
            items.append(
                NewsItem(
                    rank=0,
                    source=source,
                    title=clean_title,
                    summary=clean_summary,
                    url=link.strip(),
                    published_at=published_at,
                    score=score,
                )
            )
        return items

    def _score(self, title: str, summary: str, published_at: datetime | None, now: datetime) -> float:
        text = self._fold(f"{title} {summary}")
        score = 0.0
        if published_at:
            age_hours = (now - published_at).total_seconds() / 3600
            if age_hours < -0.25:
                score -= 120
            elif age_hours <= 2:
                score += 50
            elif age_hours <= 6:
                score += 42
            elif age_hours <= 12:
                score += 34
            elif age_hours <= 24:
                score += 25
            elif age_hours <= 48:
                score += 12
            elif age_hours <= 96:
                score += 2
            else:
                score -= min(40, age_hours / 24)
        for term, weight in RELEVANCE_TERMS.items():
            if self._contains_term(text, term):
                score += weight
        if any(self._contains_term(text, term) for term in NOISE_TERMS):
            score -= 28
        if len(title) >= 35:
            score += 2
        return round(score, 2)

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def _child_text(self, entry: ET.Element, names: tuple[str, ...]) -> str:
        wanted = {name.casefold() for name in names}
        for child in entry.iter():
            if child is entry or self._local_name(child.tag).casefold() not in wanted:
                continue
            value = "".join(child.itertext()).strip()
            if value:
                return value
        return ""

    def _entry_link(self, entry: ET.Element) -> str:
        for child in entry.iter():
            if self._local_name(child.tag).casefold() != "link":
                continue
            href = str(child.attrib.get("href") or "").strip()
            if href:
                return href
            value = "".join(child.itertext()).strip()
            if value:
                return value
        return ""

    @staticmethod
    def _parse_date(value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _clean_text(value: str, *, limit: int) -> str:
        cleaned = html.unescape(TAG_RE.sub(" ", value or ""))
        cleaned = SPACE_RE.sub(" ", cleaned).strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 1].rstrip(" ,.;:") + "…"

    @staticmethod
    def _fold(value: str) -> str:
        import unicodedata

        normalized = unicodedata.normalize("NFKD", value.casefold())
        return "".join(character for character in normalized if not unicodedata.combining(character))

    def _normal_key(self, title: str) -> str:
        return NON_WORD_RE.sub("", self._fold(title))[:180]

    def _now(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return "tempo limite excedido"
        if isinstance(exc, httpx.HTTPStatusError):
            return f"HTTP {exc.response.status_code}"
        if isinstance(exc, ET.ParseError):
            return "RSS inválido"
        return str(exc)[:160] or exc.__class__.__name__
