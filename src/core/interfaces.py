from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from models.job import Job


class ListFetcher(ABC):
    """
    Strategy: the 'producer' half of a site's crawler.

    An implementation pages through a site's search/listing results and
    yields ONE PAGE OF JOB STUBS AT A TIME (list[Job], parsed straight
    from the listing page — source_id/url/title/company/... filled in,
    description/requirements/benefits/contact still empty). Yielding
    per-page (rather than per-job) lets CrawlPipeline batch its
    dedup-against-DB check into one query per page instead of one per job.

    `source` must match the value used in Job.source / stored in Mongo,
    so the pipeline's dedup query filters the right documents.
    """

    source: str

    @abstractmethod
    def fetch_pages(self) -> AsyncIterator[list[Job]]:
        ...


class DetailEnricher(ABC):
    """
    Strategy: the 'consumer' half of a site's crawler.

    Given a Job stub (produced by a ListFetcher), fetches its detail page
    and returns the same Job filled in with the fields the listing page
    doesn't have (description, requirements, benefits, contact, exact
    posted/expiry dates, ...).
    """

    @abstractmethod
    async def enrich(self, job: Job) -> Job:
        ...
