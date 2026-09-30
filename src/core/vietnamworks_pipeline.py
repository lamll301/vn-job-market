from __future__ import annotations

import json as json_module
from typing import Any, AsyncIterator, Iterable

from core.http_client import AsyncHttpClient
from core.interfaces import DetailEnricher, ListFetcher
from core.pipeline import CrawlPipeline
from models.job import Job
from parsers.vietnamworks import VietnamWorksParser
from config import VIETNAMWORKS_SEARCH_URL, VIETNAMWORKS_SEARCHES

# VietnamWorks doesn't expose a config constant for this yet -- kept
# local here the same way CareerLink's SEARCH_PATH is (add it to
# config.py instead if you'd rather centralize it there).
VIETNAMWORKS_JOB_INFO_URL = "https://ms.vietnamworks.com/api-gateway/v1.0/tracking/job-info"

VIETNAMWORKS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Accept": "application/json",
    # VietnamWorks is CSR (SPA) -- these endpoints are the internal
    # API the frontend itself calls via XHR/fetch, not a page a browser
    # navigates to directly. CareerLink is SSR, so a plain User-Agent is
    # enough there; here Referer/Origin/X-Requested-With make the
    # request look like it actually came from the site's own JS, which
    # this kind of API-gateway endpoint is more likely to check.
    "Referer": "https://www.vietnamworks.com/",
    "Origin": "https://www.vietnamworks.com",
    "X-Requested-With": "XMLHttpRequest",
}

# Fields requested from the search-listing endpoint. Copied from the old
# synchronous crawler (crawlers/vietnamworks.py, kept for reference only
# -- not used by this pipeline).
RETRIEVE_FIELDS = [
    "address", "benefits", "jobTitle", "salaryMax", "isSalaryVisible",
    "jobLevelVI", "isShowLogo", "salaryMin", "companyLogo", "userId",
    "jobLevel", "jobLevelId", "jobId", "jobUrl", "companyId", "approvedOn",
    "isAnonymous", "alias", "expiredOn", "industries", "industriesV3",
    "workingLocations", "services", "companyName", "salary", "onlineOn",
    "onlineOnText", "simpleServices", "visibilityDisplay",
    "isShowLogoInSearch", "priorityOrder", "skills",
    "profilePublishedSiteMask", "jobDescription", "jobRequirement",
    "prettySalary", "requiredCoverLetter", "languageSelectedVI",
    "languageSelected", "languageSelectedId", "typeWorkingId", "createdOn",
    "isAdrLiteJob", "applicantSignal", "numOfApplications",
    "numberOfRecruits", "exposureStatus",
]


class VietnamWorksListFetcher(ListFetcher):
    """
    Producer: pages through VietnamWorks' search API (POST, JSON body)
    and yields parsed job stubs, one page at a time. See
    parsers/vietnamworks.py (VietnamWorksParser.parse) for the actual
    JSON parsing -- this class only owns the paging/HTTP concerns, mirroring
    core/careerlink_pipeline.py's CareerLinkListFetcher.
    """

    source = "vietnamworks"

    def __init__(
        self,
        http_client: AsyncHttpClient,
        city_ids: Iterable[int] = (),
        job_function_ids: Iterable[int] = (),
        keyword: str = "",
        search_url: str = VIETNAMWORKS_SEARCH_URL,
        hits_per_page: int = 50,
        max_pages: int = 50,
    ):
        self.http_client = http_client
        self.city_ids = list(city_ids)
        self.job_function_ids = list(job_function_ids)
        self.keyword = keyword
        self.search_url = search_url
        self.hits_per_page = hits_per_page
        self.max_pages = max_pages
        self.parser = VietnamWorksParser()

    def _build_filters(self) -> list[dict[str, Any]]:
        # NOTE: the captured network request only ever showed a single
        # city_id / job_function_id, so the multi-value shape below
        # (one dict per id, cityIds comma-joined) is our best-guess
        # extrapolation from that single-value shape, not something
        # confirmed against a real multi-select request. Worth
        # double-checking in devtools with 2+ provinces/job functions
        # picked on the site before relying on it in production.
        filters: list[dict[str, Any]] = []

        if self.job_function_ids:
            filters.append({
                "field": "jobFunction",
                "value": json_module.dumps([
                    {"parentId": job_function_id, "childrenIds": [-1]}
                    for job_function_id in self.job_function_ids
                ]),
            })

        if self.city_ids:
            filters.append({
                "field": "workingLocations.cityId",
                "value": ",".join(str(city_id) for city_id in self.city_ids),
            })
            filters.append({
                "field": "workingLocations.districtId",
                "value": json_module.dumps([
                    {"cityId": city_id, "districtId": [-1]}
                    for city_id in self.city_ids
                ]),
            })

        return filters

    async def fetch_pages(self) -> AsyncIterator[list[Job]]:
        page = 0

        while page < self.max_pages:
            payload = {
                "userId": 0,
                "query": self.keyword,
                "filter": self._build_filters(),
                "hitsPerPage": self.hits_per_page,
                "order": [],
                "page": page,
                "ranges": [],
                "retrieveFields": RETRIEVE_FIELDS,
                "summaryVersion": "",
                "variants": "test",
                "variants_v2": "test",
            }

            response = await self.http_client.post(self.search_url, json=payload)
            data = response.json()
            jobs = self.parser.parse(data)
            print(f"    [vietnamworks] page {page}: {len(jobs)} jobs")

            if not jobs:
                return

            yield jobs

            if len(jobs) < self.hits_per_page:
                # Short page -> this was the last one.
                return
            page += 1


class VietnamWorksDetailEnricher(DetailEnricher):
    """
    Consumer: fetches a job's detail page via the job-info API and fills
    in description, requirements, expiry date, and the `specifications`
    key-value block. See parsers/vietnamworks.py
    (VietnamWorksParser.parse_detail) for the actual JSON parsing.
    """

    def __init__(
        self,
        http_client: AsyncHttpClient,
        job_info_url: str = VIETNAMWORKS_JOB_INFO_URL,
    ):
        self.http_client = http_client
        self.job_info_url = job_info_url
        self.parser = VietnamWorksParser()

    async def enrich(self, job: Job) -> Job:
        response = await self.http_client.get(
            self.job_info_url, params={"jobId": job.source_id}
        )
        payload = response.json()
        detail = self.parser.parse_detail(payload.get("data") or {})

        job.description = detail.get("description") or job.description
        job.requirements = detail.get("requirements") or job.requirements
        job.location = detail.get("location") or job.location
        job.expired_at = detail.get("expired_at") or job.expired_at
        job.specifications = detail.get("specifications") or job.specifications

        return job


def build_pipeline(
    search_key: str,
    http_client: AsyncHttpClient,
    repository,
    keyword: str = "",
    concurrency: int = 4,
) -> CrawlPipeline:
    """Factory: build a ready-to-run CrawlPipeline for one named entry
    in config.VIETNAMWORKS_SEARCHES."""
    search = VIETNAMWORKS_SEARCHES[search_key]

    list_fetcher = VietnamWorksListFetcher(
        http_client=http_client,
        keyword=keyword,
        city_ids=search["city_ids"],
        job_function_ids=search["job_function_ids"],
    )
    detail_enricher = VietnamWorksDetailEnricher(http_client=http_client)

    return CrawlPipeline(
        list_fetcher=list_fetcher,
        detail_enricher=detail_enricher,
        repository=repository,
        concurrency=concurrency,
    )