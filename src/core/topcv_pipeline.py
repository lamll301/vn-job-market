from __future__ import annotations

from typing import AsyncIterator
from urllib.parse import quote

from core.http_client import AsyncHttpClient
from core.interfaces import DetailEnricher, ListFetcher
from core.pipeline import CrawlPipeline
from models.job import Job
from parsers.topcv import TopCVParser
from config import TOPCV_BASE_URL, TOPCV_SEARCHES


TOPCV_SEARCH_PATH = "/tim-viec-lam"

TOPCV_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.topcv.vn/",
}


def _build_search_url(keyword: str) -> str:
    """Build TopCV's SEO search path from config keyword."""
    keyword = (keyword or "").strip().strip("/")

    if not keyword:
        return f"{TOPCV_BASE_URL}{TOPCV_SEARCH_PATH}"

    # Keep the config value human-readable and safe for a URL path.
    slug = "-".join(part for part in keyword.replace("_", "-").split() if part)
    slug = quote(slug, safe="-")
    return f"{TOPCV_BASE_URL}{TOPCV_SEARCH_PATH}-{slug}"


def _build_search_params(search: dict) -> dict:
    """Convert TOPCV_SEARCHES entry into TopCV query parameters."""
    params = dict(search.get("params") or {})

    locations = search.get("locations") or []
    if isinstance(locations, str):
        locations = [locations]

    category_family = search.get("category_family")
    if category_family:
        params["category_family"] = category_family

    if locations:
        params["locations"] = ",".join(str(location) for location in locations)

    return params


class TopCVListFetcher(ListFetcher):
    """
    Producer: pages through a TopCV search configured in config.TOPCV_SEARCHES.

    A config entry has this shape:

        TOPCV_SEARCHES = {
            "it": {
                "keyword": "software-engineering",
                "locations": ["l9"],
                "category_family": "r257~b258_...",
                "params": {
                    "type_keyword": 1,
                    "disable_auto_detect_type_keyword": 1,
                    "sba": 1,
                    "saturday_status": 0,
                },
            }
        }

    The fetcher does not hard-code keyword, location, category or filter
    values. Adding another search only requires editing config.py.
    """

    source = "topcv"

    def __init__(
        self,
        http_client: AsyncHttpClient,
        search_url: str,
        search_params: dict | None = None,
        max_pages: int = 50,
        start_page: int = 1,
    ):
        self.http_client = http_client
        self.search_url = search_url
        self.search_params = dict(search_params or {})
        self.max_pages = max_pages
        self.start_page = max(1, start_page)
        self.parser = TopCVParser(base_url=TOPCV_BASE_URL)

    async def fetch_pages(self) -> AsyncIterator[list[Job]]:
        seen_ids: set[str] = set()

        for page in range(self.start_page, self.max_pages + 1):
            params = {
                **self.search_params,
                "page": page,
            }

            response = await self.http_client.get(
                self.search_url,
                params=params,
            )

            jobs = self.parser.parse(response.text)
            new_on_page = [
                job for job in jobs if job.source_id not in seen_ids
            ]

            print(
                f"    [topcv] page {page}: "
                f"{len(jobs)} jobs, {len(new_on_page)} new"
            )

            if not jobs or not new_on_page:
                return

            seen_ids.update(job.source_id for job in new_on_page)
            yield new_on_page


class TopCVDetailEnricher(DetailEnricher):
    """
    Consumer: fetches the TopCV detail page and enriches the listing Job.
    """

    def __init__(self, http_client: AsyncHttpClient):
        self.http_client = http_client
        self.parser = TopCVParser(base_url=TOPCV_BASE_URL)

    async def enrich(self, job: Job) -> Job:
        response = await self.http_client.get(job.url)
        detail = self.parser.parse_detail(response.text)

        job.description = detail.get("description") or job.description
        job.requirements = detail.get("requirements") or job.requirements
        job.benefits = detail.get("benefits") or job.benefits
        job.contact = detail.get("contact") or job.contact

        job.salary = detail.get("salary") or job.salary
        job.location = detail.get("location") or job.location
        job.address = detail.get("address") or job.address

        job.posted_at = detail.get("posted_at") or job.posted_at
        job.expired_at = detail.get("expired_at") or job.expired_at

        job.specifications = {
            **(job.specifications or {}),
            **(detail.get("specifications") or {}),
        }

        # job.raw_data = {
        #     **(job.raw_data or {}),
        #     **(detail.get("raw_data") or {}),
        # }

        return job


def build_pipeline(
    search_key: str,
    http_client: AsyncHttpClient,
    repository,
    concurrency: int = 4,
    max_pages: int = 50,
    start_page: int = 1,
) -> CrawlPipeline:
    """
    Factory giống CareerLink/VietnamWorks nhưng lấy toàn bộ filter từ
    config.TOPCV_SEARCHES[search_key].

    Ví dụ:
        build_pipeline(
            search_key="it",
            http_client=http_client,
            repository=repository,
            concurrency=4,
        )
    """
    if search_key not in TOPCV_SEARCHES:
        raise KeyError(
            f"TOPCV search '{search_key}' not found in config.TOPCV_SEARCHES"
        )

    search = TOPCV_SEARCHES[search_key]
    search_url = search.get("search_url") or _build_search_url(search.get("keyword", ""))
    search_params = _build_search_params(search)

    print(f"    [topcv] search='{search_key}'")
    print(f"    [topcv] url={search_url}")
    print(f"    [topcv] params={search_params}")

    list_fetcher = TopCVListFetcher(
        http_client=http_client,
        search_url=search_url,
        search_params=search_params,
        max_pages=max_pages,
        start_page=start_page,
    )

    detail_enricher = TopCVDetailEnricher(http_client=http_client)

    return CrawlPipeline(
        list_fetcher=list_fetcher,
        detail_enricher=detail_enricher,
        repository=repository,
        concurrency=concurrency,
    )
