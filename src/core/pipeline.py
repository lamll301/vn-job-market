from __future__ import annotations

import asyncio
from typing import Optional

from core.http_client import SiteUnreachableError
from core.interfaces import DetailEnricher, ListFetcher
from models.job import Job


class CrawlPipeline:
    """
    Generic two-stage crawl pipeline (Producer/Consumer), independent of
    any particular job site. Plug in a site's ListFetcher + DetailEnricher
    (Strategy pattern -- see crawlers/interfaces.py) and this class
    handles:

      1. Paging through listings (list_fetcher.fetch_pages()).
      2. Deduplicating against MongoDB one page at a time -- so detail
         requests are only ever made for genuinely new jobs, in a single
         batched query per page rather than one query per job.
      3. Fanning new jobs out to `concurrency` async workers that call
         detail_enricher.enrich() and persist the result, so one slow or
         timed-out detail page never blocks the rest of the crawl.
      4. Stopping gracefully when the site is unreachable (circuit breaker
         in AsyncHttpClient raises SiteUnreachableError): remaining queued
         jobs are drained without any network calls, and run() re-raises
         SiteUnreachableError so the caller can stop the whole crawl.

    To support a new site (LinkedIn, TopCV, ...), write a ListFetcher +
    DetailEnricher for it (see crawlers/careerlink_pipeline.py for the
    CareerLink example) and reuse this class as-is.

    `repository` just needs to look like the existing JobRepository:
    a `.collection` attribute (a pymongo Collection) for the dedup query,
    and a `.save_many(list[Job])` method to persist enriched jobs.
    """

    def __init__(
        self,
        list_fetcher: ListFetcher,
        detail_enricher: DetailEnricher,
        repository,
        concurrency: int = 4,
        queue_maxsize: int = 200,
    ):
        self.list_fetcher = list_fetcher
        self.detail_enricher = detail_enricher
        self.repository = repository
        self.concurrency = concurrency
        self.queue_maxsize = queue_maxsize

        self.stats = {"listed": 0, "new": 0, "enriched": 0, "failed": 0}
        # Set when the site is unreachable; producer and workers stop making requests.
        self._stop = asyncio.Event()

    async def run(self) -> None:
        queue: asyncio.Queue[Optional[Job]] = asyncio.Queue(maxsize=self.queue_maxsize)

        consumers = [
            asyncio.create_task(self._consume(queue, worker_id=i + 1))
            for i in range(self.concurrency)
        ]

        try:
            await self._produce(queue)
        except Exception as e:
            # Lỗi ở trang danh sách (403, timeout, SiteUnreachableError...)
            # -> coi như site không dùng được, dừng gọn thay vì crash runner.
            print(f"    [{self.list_fetcher.source}] [ERROR] listing failed: {e}")
            self._stop.set()
        finally:
            for _ in consumers:
                await queue.put(None)

        await asyncio.gather(*consumers)

        print(
            f"[{self.list_fetcher.source}] done -> "
            f"listed={self.stats['listed']} new={self.stats['new']} "
            f"enriched={self.stats['enriched']} failed={self.stats['failed']}"
        )

        if self._stop.is_set():
            raise SiteUnreachableError(
                f"[{self.list_fetcher.source}] aborted, site unreachable"
            )

    async def _produce(self, queue: "asyncio.Queue[Optional[Job]]") -> None:
        async for page_jobs in self.list_fetcher.fetch_pages():
            if self._stop.is_set():
                return

            self.stats["listed"] += len(page_jobs)

            new_jobs = self._filter_new(page_jobs)
            self.stats["new"] += len(new_jobs)

            for job in new_jobs:
                if self._stop.is_set():
                    return
                await queue.put(job)

    def _filter_new(self, jobs: list[Job]) -> list[Job]:
        """Batch-dedup one listing page's jobs against MongoDB in a
        single query. A job already in DB is skipped only if it is
        complete; jobs missing description/requirements are crawled again."""
        if not jobs:
            return []

        source_ids = [j.source_id for j in jobs]
        complete_ids: set[str] = set()
        incomplete_count = 0

        for doc in self.repository.collection.find(
            {"source": jobs[0].source, "source_id": {"$in": source_ids}},
            {"source_id": 1, "description": 1, "requirements": 1},
        ):
            if self._is_complete(doc):
                complete_ids.add(doc["source_id"])
            else:
                incomplete_count += 1

        to_crawl = [j for j in jobs if j.source_id not in complete_ids]
        print(
            f"    [{jobs[0].source}] dedup: {len(jobs)} listed, "
            f"{len(complete_ids)} complete in DB, "
            f"{incomplete_count} incomplete (re-crawl), "
            f"{len(to_crawl) - incomplete_count} new"
        )
        return to_crawl

    @staticmethod
    def _is_complete(doc: dict) -> bool:
        """A stored job counts as complete only if both description and
        requirements are non-empty (missing, None and blank all fail)."""
        return all(
            str(doc.get(field) or "").strip()
            for field in ("description", "requirements")
        )

    async def _consume(self, queue: "asyncio.Queue[Optional[Job]]", worker_id: int) -> None:
        while True:
            job = await queue.get()
            if job is None:
                queue.task_done()
                return

            if self._stop.is_set():
                # Site is blocking us: still drain the queue, but make no more requests.
                queue.task_done()
                continue

            try:
                enriched = await self.detail_enricher.enrich(job)
                # pymongo is sync -- run the write off the event loop so
                # it doesn't block other workers' in-flight requests.
                await asyncio.to_thread(self.repository.save_many, [enriched])
                self.stats["enriched"] += 1
                print(f"    [worker {worker_id}] saved {enriched.source_id} - {enriched.title}")
            except SiteUnreachableError:
                self._stop.set()
                print(f"    [worker {worker_id}] [STOP] site không phản hồi, dừng crawl")
            except Exception as e:
                self.stats["failed"] += 1
                print(f"    [worker {worker_id}] [ERROR] {job.source_id} ({job.url}): {e}")
            finally:
                queue.task_done()