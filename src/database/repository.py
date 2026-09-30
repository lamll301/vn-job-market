from dataclasses import asdict

from database.connection import db
from models.job import Job


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

    def save(self, job: Job):
        document = asdict(job)
        document.pop("created_at", None)

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