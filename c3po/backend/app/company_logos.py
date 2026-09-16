"""Bounded, on-demand B3 logo fallback for newly listed Chewie constituents.

Only fixed public image hosts are contacted; never provider credentials or supplied URLs.
Existing curated marks are served statically by the frontend.
"""
from collections import OrderedDict
from hashlib import sha256
import logging
import re
from threading import BoundedSemaphore, Lock
from time import monotonic
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import httpx

MAX_BYTES = 512_000
MAX_ENTRIES = 128
# FMP's generic blue globe (observed for AXIA7), not a company mark.
PLACEHOLDERS = {"ac7d9664ba0d36213e39dc3db8c94115d91aa1bdaced402e30d7858edfd712b6", "53c75b954bb71619d71d7a37fc112ab49f778eb891becaaeabf589fdc968bad1"}
logger = logging.getLogger(__name__)


def validate_logo(data: bytes, url: str) -> str | None:
    if not data or len(data) > MAX_BYTES or sha256(data).hexdigest() in PLACEHOLDERS:
        return None
    if urlsplit(url).path.lower().endswith('/brapi.svg'):
        return None
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        return None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    if root.tag.split('}')[-1] != 'svg':
        return None
    for element in root.iter():
        if element.tag.split('}')[-1].lower() in {'script', 'foreignobject', 'image', 'style', 'a'}:
            return None
        for key, value in element.attrib.items():
            if key.lower().startswith('on') or 'url(' in value.lower():
                return None
            if key.split('}')[-1] == 'href' and not value.startswith('#'):
                return None
    return 'image/svg+xml'


def fetch_logo(url: str) -> bytes:
    # No redirects: even redirects to another public origin need explicit review.
    deadline = monotonic() + 4
    with httpx.stream('GET', url, timeout=httpx.Timeout(3), follow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('logo_not_ok')
        data = bytearray()
        for chunk in response.iter_bytes():
            if monotonic() > deadline:
                raise ValueError('logo_download_deadline')
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError('logo_too_large')
        return bytes(data)


class CompanyLogoService:
    def __init__(self) -> None:
        self._cache: OrderedDict[str, tuple[float, tuple[bytes, str] | None]] = OrderedDict()
        self._lock = Lock()
        self._slots = BoundedSemaphore(4)
        self._flights = [Lock() for _ in range(32)]

    def get(self, symbol: str) -> tuple[bytes, str] | None:
        symbol = symbol.strip().upper().removesuffix('.SA')
        if not re.fullmatch(r'[A-Z][A-Z0-9]{3}[0-9]{1,2}', symbol):
            raise ValueError('invalid_b3_symbol')
        # Single flight per stripe, bounded callers never queue an unbounded backlog.
        flight = self._flights[int(sha256(symbol.encode()).hexdigest(), 16) % 32]
        if not flight.acquire(timeout=0.1):
            return None
        try:
            with self._lock:
                cached = self._cache.get(symbol)
                if cached and cached[0] > monotonic():
                    self._cache.move_to_end(symbol)
                    return cached[1]
            if not self._slots.acquire(blocking=False):
                return None
            try:
                result = None
                for url in (f'https://icons.brapi.dev/icons/{symbol}.svg',
                            f'https://financialmodelingprep.com/image-stock/{symbol}.SA.png'):
                    try:
                        data = fetch_logo(url)
                        media = validate_logo(data, url)
                        if media:
                            result = (data, media)
                            break
                    except (httpx.HTTPError, ValueError):
                        continue
                if result is None:
                    logger.warning('company_logo_unavailable market=B3 symbol=%s', symbol)
                with self._lock:
                    self._cache[symbol] = (monotonic() + (86400 if result else 300), result)
                    self._cache.move_to_end(symbol)
                    while len(self._cache) > MAX_ENTRIES:
                        self._cache.popitem(last=False)
                return result
            finally:
                self._slots.release()
        finally:
            flight.release()
