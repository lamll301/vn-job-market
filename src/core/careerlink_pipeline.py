from __future__ import annotations

from typing import AsyncIterator, Iterable

from core.http_client import AsyncHttpClient
from core.interfaces import DetailEnricher, ListFetcher
from core.pipeline import CrawlPipeline
from models.job import Job
from parsers.careerlink import CareerLinkParser
from config import CAREERLINK_BASE_URL, CAREERLINK_SEARCHES

SEARCH_PATH = "/vieclam/tim-kiem-viec-lam"

CAREERLINK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


class CareerLinkListFetcher(ListFetcher):
    """
    Producer: pages through CareerLink's listing endpoint and yields
    parsed job stubs, one page at a time. See parsers/careerlink.py for
    the actual HTML parsing (CareerLinkParser.parse) -- this class only
    owns the paging/HTTP concerns.
    """

    source = "careerlink"

    def __init__(
        self,
        http_client: AsyncHttpClient,
        category_ids: Iterable[int],
        province_codes: Iterable[str],
        base_url: str = CAREERLINK_BASE_URL,
        search_path: str = SEARCH_PATH,
        max_pages: int = 50,
    ):
        self.http_client = http_client
        self.category_ids = list(category_ids)
        self.province_codes = list(province_codes)
        self.base_url = base_url
        self.search_path = search_path
        self.max_pages = max_pages
        self.parser = CareerLinkParser(base_url=base_url)

    async def fetch_pages(self) -> AsyncIterator[list[Job]]:
        seen_ids: set[str] = set()
        page = 1

        while page <= self.max_pages:
            url = f"{self.base_url}{self.search_path}"
            params = {
                "category_ids": ",".join(str(c) for c in self.category_ids),
                "province_codes": ",".join(self.province_codes),
                "page": page,
            }

            response = await self.http_client.get(url, params=params)
            jobs = self.parser.parse(response.text)
            print(f"    [careerlink] page {page}: {len(jobs)} jobs")

            if not jobs:
                return

            new_on_page = [j for j in jobs if j.source_id not in seen_ids]
            if not new_on_page:
                # Same jobs came back as last page -> stop (last page
                # reached, or the page param isn't advancing as expected).
                return
            seen_ids.update(j.source_id for j in new_on_page)

            yield new_on_page
            page += 1


class CareerLinkDetailEnricher(DetailEnricher):
    """
    Consumer: fetches a job's detail page and fills in description,
    requirements, benefits, contact, and exact posted/expiry dates.
    See parsers/careerlink.py (CareerLinkParser.parse_detail) for the
    actual HTML/JSON-LD parsing.
    """

    def __init__(self, http_client: AsyncHttpClient, base_url: str = CAREERLINK_BASE_URL):
        self.http_client = http_client
        self.parser = CareerLinkParser(base_url=base_url)

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
        job.specifications = detail.get("specifications") or job.specifications

        # job.raw_data = {
        #     **job.raw_data,
        #     "tags": detail.get("tags"),
        #     "job_type": detail.get("job_type"),
        #     "career_level": detail.get("career_level"),
        #     "education": detail.get("education"),
        #     "experience": detail.get("experience"),
        #     "company_url": detail.get("company_url"),
        #     "company_size": detail.get("company_size"),
        # }
        return job


def build_pipeline(
    search_key: str,
    http_client: AsyncHttpClient,
    repository,
    concurrency: int = 4,
) -> CrawlPipeline:
    """Factory: build a ready-to-run CrawlPipeline for one named entry
    in config.CAREERLINK_SEARCHES."""
    search = CAREERLINK_SEARCHES[search_key]

    list_fetcher = CareerLinkListFetcher(
        http_client=http_client,
        category_ids=search["category_ids"],
        province_codes=search["province_codes"],
    )
    detail_enricher = CareerLinkDetailEnricher(http_client=http_client)

    return CrawlPipeline(
        list_fetcher=list_fetcher,
        detail_enricher=detail_enricher,
        repository=repository,
        concurrency=concurrency,
    )
