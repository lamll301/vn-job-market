from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Job:
    source: str
    source_id: str
    title: str
    company: str
    location: Optional[str]
    address: Optional[str]
    salary: Optional[str]
    url: str
    description: Optional[str]
    requirements: Optional[str]
    benefits: Optional[str]
    contact: Optional[str]
    posted_at: Optional[datetime]
    expired_at: Optional[datetime]
    created_at: datetime
    crawled_at: datetime
    # raw_data: dict[str, Any]
    specifications: dict[str, Any] = field(default_factory=dict)
    last_rechecked_at: Optional[datetime] = None
    is_closed: bool = False