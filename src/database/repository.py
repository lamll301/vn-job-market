from dataclasses import asdict
from datetime import datetime
from typing import Any, Mapping, Optional

from database.connection import db
from models.job import Job

# Do luồng re-check sở hữu: save() không được $set để crawl lại job
# không làm mất last_rechecked_at hay mở lại job đã đóng.
RECHECK_MANAGED_FIELDS = ("last_rechecked_at", "is_closed")


class JobRepository:
    def __init__(self):
        self.collection = db["jobs"]

        self.collection.create_index(
            [
                ("source", 1),
                ("source_id", 1)
            ],
            unique=True
        )
        # Phục vụ query chọn job cần re-check.
        self.collection.create_index(
            [
                ("source", 1),
                ("posted_at", 1),
                ("last_rechecked_at", 1)
            ]
        )

    def save(self, job: Job):
        document = asdict(job)
        document.pop("created_at", None)
        for name in RECHECK_MANAGED_FIELDS:
            document.pop(name, None)

        self.collection.update_one(
            {
                "source": job.source,
                "source_id": job.source_id
            },
            {
                "$set": document,
                "$setOnInsert": {
                    "created_at": job.created_at
                }
            },
            upsert=True
        )

    def save_many(self, jobs: list[Job]):
        if not jobs:
            return

        for job in jobs:
            self.save(job)

    def get_all(self, limit: int = 0) -> list[dict]:
        cursor = self.collection.find({}).sort("posted_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def find_recheck_candidates(
        self,
        source: str,
        posted_from: datetime,
        posted_to: datetime,
        expiry_after: datetime,
        rechecked_before: datetime,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Job của `source` cần re-check: tuổi nằm trong [posted_from, posted_to]
        (dùng posted_at, thiếu thì dùng created_at), chưa đóng, chưa/sắp hết hạn
        (expired_at > expiry_after) và chưa re-check hoặc lần cuối trước
        `rechecked_before`. Job chưa từng re-check được xếp trước.
        `limit` là None thì không giới hạn số job trả về."""
        age_range = {"$gte": posted_from, "$lte": posted_to}
        query = {
            "source": source,
            "is_closed": {"$ne": True},
            "$and": [
                {"$or": [
                    {"posted_at": age_range},
                    {"posted_at": None, "created_at": age_range},
                ]},
                {"$or": [
                    {"expired_at": None},
                    {"expired_at": {"$gt": expiry_after}},
                ]},
                {"$or": [
                    {"last_rechecked_at": None},
                    {"last_rechecked_at": {"$lte": rechecked_before}},
                ]},
            ],
        }
        cursor = (
            self.collection.find(query)
            .sort([("last_rechecked_at", 1), ("posted_at", 1)])
            .limit(limit or 0)  # pymongo: limit(0) = không giới hạn
        )
        return list(cursor)

    def mark_rechecked(
        self, doc_id: Any, changes: Mapping[str, Any], checked_at: datetime
    ) -> None:
        """Ghi các field thay đổi + last_rechecked_at bằng update_one. Không
        dùng save() vì nó $set toàn bộ document (kể cả crawled_at)."""
        self.collection.update_one(
            {"_id": doc_id},
            {"$set": {**changes, "last_rechecked_at": checked_at}},
        )