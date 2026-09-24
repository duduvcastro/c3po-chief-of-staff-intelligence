import time
from typing import Any

import httpx


class MarketDataRequestError(RuntimeError):
    pass


class JsonHttpClient:
    def __init__(self, *, timeout: float, max_retries: int, client: httpx.Client | None = None) -> None:
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.client = client

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                if self.client:
                    response = self.client.get(url, params=params, headers=headers, timeout=self.timeout)
                else:
                    response = httpx.get(url, params=params, headers=headers, timeout=self.timeout, follow_redirects=True)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.25 * (2 ** attempt))
        raise MarketDataRequestError(str(last_error) if last_error else "Market data request failed")

    def get_text(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> str:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                if self.client:
                    response = self.client.get(url, params=params, headers=headers, timeout=self.timeout)
                else:
                    response = httpx.get(url, params=params, headers=headers, timeout=self.timeout, follow_redirects=True)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.25 * (2 ** attempt))
        raise MarketDataRequestError(str(last_error) if last_error else "Market data request failed")


class DeadlineJsonHttpClient(JsonHttpClient):
    """Bound the complete response, including headers and slow-drip bodies."""
    def __init__(self, *, timeout: float = 3.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(timeout=timeout, max_retries=0)
        self.transport = transport

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        import asyncio

        async def fetch():
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport, follow_redirects=True) as client:
                async with asyncio.timeout(self.timeout):
                    response = await client.get(url, params=params, headers=headers)
                    response.raise_for_status()
                    return response.json()
        try:
            return asyncio.run(fetch())
        except (TimeoutError, httpx.HTTPError, ValueError) as exc:
            # Never propagate URLs or credentials through the service logger.
            raise MarketDataRequestError(type(exc).__name__) from None
