from __future__ import annotations

import asyncio
import copy
from collections import Counter
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Mapping

from config import (
    RECHECK_BATCH_SIZE,
    RECHECK_CLOSED_STATUS_CODES,
    RECHECK_EXPIRY_BUFFER_DAYS,
    RECHECK_INTERVAL_DAYS,
    RECHECK_MAX_AGE_DAYS,
    RECHECK_MIN_AGE_DAYS,
    RECHECK_TRACKED_FIELDS,
)
from core.http_client import SiteUnreachableError
from core.interfaces import DetailEnricher
from models.job import Job

if TYPE_CHECKING:
    from database.repository import JobRepository

# Kết quả của 1 lần re-check (dùng làm key thống kê).
UPDATED = "updated"
UNCHANGED = "unchanged"
CLOSED = "closed"
FAILED = "failed"


def _utcnow() -> datetime:
    """pymongo trả datetime naive (UTC) nên so sánh cũng dùng naive UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------
# 1. Policy: chỉ chứa luật "job nào đáng re-check", không biết gì về Mongo
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class FreshnessPolicy:
    min_age_days: int        # < min  -> job mới, bỏ qua
    max_age_days: int        # > max  -> quá cũ, ngừng re-check
    expiry_buffer_days: int  # sắp hết hạn trong N ngày -> ngừng re-check
    interval_days: int       # 1 job được re-check tối đa 1 lần / N ngày

    @classmethod
    def from_config(cls) -> "FreshnessPolicy":
        return cls(
            min_age_days=RECHECK_MIN_AGE_DAYS,
            max_age_days=RECHECK_MAX_AGE_DAYS,
            expiry_buffer_days=RECHECK_EXPIRY_BUFFER_DAYS,
            interval_days=RECHECK_INTERVAL_DAYS,
        )

    def newest_allowed(self, now: datetime) -> datetime:
        return now - timedelta(days=self.min_age_days)

    def oldest_allowed(self, now: datetime) -> datetime:
        return now - timedelta(days=self.max_age_days)

    def expiry_cutoff(self, now: datetime) -> datetime:
        return now + timedelta(days=self.expiry_buffer_days)

    def interval_cutoff(self, now: datetime) -> datetime:
        return now - timedelta(days=self.interval_days)


# --------------------------------------------------------------------------
# 2. Service: điều phối re-check, tái sử dụng DetailEnricher có sẵn
# --------------------------------------------------------------------------
class RecheckService:
    def __init__(
        self,
        repository: JobRepository,
        enrichers: Mapping[str, DetailEnricher],
        policy: FreshnessPolicy | None = None,
        max_jobs: Mapping[str, int | None] | None = None,
        batch_size: int = RECHECK_BATCH_SIZE,
        tracked_fields: Iterable[str] = RECHECK_TRACKED_FIELDS,
        closed_status_codes: Iterable[int] = RECHECK_CLOSED_STATUS_CODES,
    ):
        self.repository = repository
        self.enrichers = dict(enrichers)
        self.policy = policy or FreshnessPolicy.from_config()
        # Trần số job mỗi lần chạy theo từng source; thiếu hoặc None = không giới hạn.
        self.max_jobs = dict(max_jobs or {})
        self.batch_size = batch_size
        self.tracked_fields = tuple(tracked_fields)
        self.closed_status_codes = tuple(closed_status_codes)

    async def run(self) -> Counter:
        total: Counter = Counter()
        for source, enricher in self.enrichers.items():
            total.update(await self._recheck_source(source, enricher))
        return total

    async def _recheck_source(self, source: str, enricher: DetailEnricher) -> Counter:
        stats: Counter = Counter()
        now = _utcnow()

        docs = await asyncio.to_thread(self._find_candidates, source, now)

        for batch in self._chunks(docs, self.batch_size):
            results = await asyncio.gather(
                *(self._recheck_one(doc, enricher, now) for doc in batch),
                return_exceptions=True,
            )
            if self._tally(results, stats):
                print(f"    [recheck:{source}] [STOP] site không phản hồi, dừng source này")
                break

        print(f"[recheck:{source}] done -> {dict(stats)}")
        return stats

    def _find_candidates(self, source: str, now: datetime) -> list[dict]:
        return self.repository.find_recheck_candidates(
            source=source,
            posted_from=self.policy.oldest_allowed(now),
            posted_to=self.policy.newest_allowed(now),
            expiry_after=self.policy.expiry_cutoff(now),
            rechecked_before=self.policy.interval_cutoff(now),
            limit=self.max_jobs.get(source),
        )

    async def _recheck_one(self, doc: dict, enricher: DetailEnricher, now: datetime) -> str:
        job = self._to_job(doc)
        before = self._snapshot(job)

        try:
            enriched = await enricher.enrich(job)
        except SiteUnreachableError:
            raise
        except Exception as exc:
            if self._is_gone(exc):
                await self._save(doc, {"is_closed": True}, now)
                return CLOSED
            # Vẫn đánh dấu thời điểm check để job lỗi dai dẳng không
            # chiếm hết slot đầu hàng đợi ở các lần chạy sau.
            await self._save(doc, {}, now)
            print(f"    [recheck] [ERROR] {job.source_id} ({job.url}): {exc}")
            return FAILED

        changes = self._diff(before, self._snapshot(enriched))
        await self._save(doc, changes, now)
        if changes:
            print(f"    [recheck] updated {job.source_id}: {sorted(changes)}")
        return UPDATED if changes else UNCHANGED

    # ---- helpers ---------------------------------------------------------
    async def _save(self, doc: Mapping[str, Any], changes: Mapping[str, Any], now: datetime) -> None:
        # pymongo là sync -> chạy ngoài event loop (như CrawlPipeline._consume).
        await asyncio.to_thread(self.repository.mark_rechecked, doc["_id"], changes, now)

    @staticmethod
    def _to_job(doc: Mapping[str, Any]) -> Job:
        data = {f.name: doc.get(f.name) for f in fields(Job)}
        data["specifications"] = data["specifications"] or {}
        return Job(**data)

    def _snapshot(self, job: Job) -> dict[str, Any]:
        return {name: copy.deepcopy(getattr(job, name, None)) for name in self.tracked_fields}

    @staticmethod
    def _diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
        return {name: value for name, value in after.items() if before.get(name) != value}

    def _is_gone(self, exc: Exception) -> bool:
        """404/410 ở trang chi tiết -> tin đã bị gỡ."""
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return status in self.closed_status_codes

    @staticmethod
    def _tally(results: list, stats: Counter) -> bool:
        """Cộng dồn kết quả; trả True nếu có SiteUnreachableError."""
        site_down = False
        for result in results:
            if isinstance(result, SiteUnreachableError):
                site_down = True
            elif isinstance(result, BaseException):
                stats[FAILED] += 1
            else:
                stats[result] += 1
        return site_down

    @staticmethod
    def _chunks(items: list, size: int) -> Iterator[list]:
        for start in range(0, len(items), size):
            yield items[start:start + size]