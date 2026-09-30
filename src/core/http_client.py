from __future__ import annotations

import asyncio
import random
from typing import Any, Optional

import httpx


class _RetryableStatus(Exception):
    """Internal signal: response status means 'back off and try again'."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"retryable status {status_code}")


class SiteUnreachableError(Exception):
    """Too many consecutive failures -> site is probably blocking us."""


class AsyncHttpClient:
    """
    Reusable async HTTP transport for any site crawler (CareerLink,
    VietnamWorks, LinkedIn, TopCV, ...). Wraps httpx.AsyncClient with:

      - Concurrency limit: asyncio.Semaphore(concurrency) caps how many
        requests are in flight at once.
      - Adaptive random delay: each request sleeps a random amount in
        [min_delay, max_delay] before firing, to avoid a fixed-interval
        fingerprint. That window widens automatically after a 429/403/timeout
        (site is complaining -> slow everything down) and slowly relaxes
        back toward the base window after clean responses.
      - Exponential backoff retry: on 429 / 403 / 5xx / timeout /
        connection errors, retries with backoff_base * 2**attempt
        (+ jitter), capped at backoff_cap, up to max_retries times.
      - Circuit breaker: after `max_consecutive_failures` requests that
        failed even after all retries, further requests raise
        SiteUnreachableError immediately instead of hammering a site
        that is most likely blocking us.

    Usage (async context manager, so the underlying connection pool is
    always closed):

        async with AsyncHttpClient(headers=MY_HEADERS, concurrency=4) as client:
            response = await client.get(url, params=params)
            response = await client.post(url, json=payload)
    """

    def __init__(
        self,
        headers: Optional[dict] = None,
        concurrency: int = 4,
        base_min_delay: float = 1.0,
        base_max_delay: float = 2.5,
        max_retries: int = 4,
        backoff_base: float = 5.0,
        backoff_cap: float = 60.0,
        timeout: float = 15.0,
        max_consecutive_failures: int = 3,
    ):
        self._client = httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True)
        self._semaphore = asyncio.Semaphore(concurrency)

        self.base_min_delay = base_min_delay
        self.base_max_delay = base_max_delay
        # Grows (up to a cap) after 429/403/timeout so ALL subsequent requests
        # slow down, not just the one that got throttled; decays after successes.
        self._delay_multiplier = 1.0

        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap

        # Circuit breaker: count requests that failed even after all retries.
        self._consecutive_failures = 0
        self.max_consecutive_failures = max_consecutive_failures

    async def get(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        return await self.request("GET", url, params=params)

    async def post(
        self,
        url: str,
        json: Optional[Any] = None,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        return await self.request("POST", url, params=params, json=json)

    async def request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        json: Optional[Any] = None,
    ) -> httpx.Response:
        async with self._semaphore:
            # Check AFTER getting the semaphore, so requests that were
            # already waiting also fail fast once the breaker has tripped.
            self._check_circuit()
            await self._adaptive_delay()
            response = await self._request_with_retry(method, url, params, json)
            self._on_success()
            return response

    async def _adaptive_delay(self) -> None:
        low = self.base_min_delay * self._delay_multiplier
        high = self.base_max_delay * self._delay_multiplier
        await asyncio.sleep(random.uniform(low, high))

    def _on_success(self) -> None:
        self._consecutive_failures = 0
        self._delay_multiplier = max(1.0, self._delay_multiplier * 0.9)

    def _on_throttled(self) -> None:
        self._delay_multiplier = min(6.0, self._delay_multiplier * 1.5)

    def _on_exhausted(self) -> None:
        self._consecutive_failures += 1

    def _check_circuit(self) -> None:
        if self._consecutive_failures >= self.max_consecutive_failures:
            raise SiteUnreachableError(
                f"{self._consecutive_failures} consecutive failures, aborting"
            )

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        params: Optional[dict],
        json: Optional[Any],
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, url, params=params, json=json)
                if response.status_code in (429, 403) or response.status_code >= 500:
                    raise _RetryableStatus(response.status_code)
                response.raise_for_status()
                return response

            except (_RetryableStatus, httpx.TimeoutException, httpx.TransportError) as exc:
                attempt += 1
                status = getattr(exc, "status_code", "network/timeout")
                if status in (429, 403, "network/timeout"):
                    self._on_throttled()

                if attempt > self.max_retries:
                    self._on_exhausted()
                    raise

                wait = min(self.backoff_cap, self.backoff_base * (2 ** (attempt - 1)))
                wait += random.uniform(0, wait * 0.2)  # jitter
                print(
                    f"    [retry] {method} {url} -> {status} "
                    f"(attempt {attempt}/{self.max_retries}), sleeping {wait:.1f}s"
                )
                await asyncio.sleep(wait)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncHttpClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()