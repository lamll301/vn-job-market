from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from models.job import Job


class VietnamWorksParser:
    """
    Parses VietnamWorks JSON API responses.

    - parse(): the search-listing API response. Builds job stubs
      (source_id/url/title/company/location/address/salary/...);
      description/requirements/specifications are left empty here and
      filled in by parse_detail() during enrichment, matching the
      ListFetcher / DetailEnricher contract used across the app (see
      core/interfaces.py) -- even though the listing payload actually
      already carries jobDescription/jobRequirement.
    - parse_detail(): the job-info detail API response
      (https://ms.vietnamworks.com/api-gateway/v1.0/tracking/job-info?jobId=...),
      used to fill description, requirements, expiry date and the
      `specifications` key-value block.
    """

    # Detail-payload fields already mapped onto one of Job's own columns
    # -- excluded from `specifications` so they aren't duplicated there.
    _CORE_DETAIL_KEYS = {
        "job_id",
        "job_title",
        "job_description",
        "job_requirement",
        "job_expired_date",
        "job_location_city",
        "company_name",
    }

    # Internal tracking / AB-test fields with no value as a job spec.
    _IGNORED_DETAIL_KEYS = {
        "performance_outcome_at_event",
        "performance_as_of",
        "below_target_type",
    }

    # Friendly Vietnamese labels for known fields. A key that isn't
    # listed here still gets included in `specifications` under its raw
    # JSON key (snake_case as-is) -- so if VietnamWorks adds a new field
    # to this endpoint later (e.g. "headcount_confirmed"), it shows up
    # automatically without touching this code. Only known keys get a
    # nicer label via this map.
    _DETAIL_LABELS = {
        "job_level_name": "Cấp bậc",
        "job_function_name": "Ngành nghề",
        "job_group_function_name": "Lĩnh vực",
        "number_of_years_of_experience_required": "Số năm kinh nghiệm",
        "headcount": "Số lượng tuyển",
        "company_industry": "Ngành công ty",
        "salary_range": "Khoảng lương",
        "is_salary_hidden": "Ẩn lương",
        "job_age_hours": "Đăng cách đây (giờ)",
        "job_level_id": "Mã cấp bậc",
        "job_function_id": "Mã ngành nghề",
        "job_group_function_id": "Mã lĩnh vực",
        "job_location_id": "Mã địa điểm",
        "working_location": "Mã địa điểm làm việc",
        "company_id": "Mã công ty",
        "service_names": "Dịch vụ",
    }

    def parse(self, data: dict) -> list[Job]:
        jobs: list[Job] = []
        now = datetime.now()

        for item in data.get("data", []):
            locations = item.get("workingLocations") or []

            location_names = [
                loc.get("cityNameVI") for loc in locations if loc.get("cityNameVI")
            ]
            location = ", ".join(location_names) or None

            address_names = [
                loc.get("address") for loc in locations if loc.get("address")
            ]
            address = ", ".join(address_names) or None

            jobs.append(
                Job(
                    source="vietnamworks",
                    source_id=str(item["jobId"]),
                    title=item.get("jobTitle", ""),
                    company=item.get("companyName", ""),
                    location=location,
                    address=address,
                    salary=item.get("prettySalary"),
                    url=item.get("jobUrl", ""),
                    description=None,
                    requirements=None,
                    benefits=None,
                    contact=None,
                    posted_at=self._parse_datetime(item.get("approvedOn")),
                    expired_at=self._parse_datetime(item.get("expiredOn")),
                    crawled_at=now,
                    created_at=now,
                    # specifications block only filled at detail stage
                    # (Job's field already defaults to {}).
                )
            )

        return jobs

    def parse_detail(self, data: dict) -> dict[str, Any]:
        """
        `data` is the `"data"` object of the job-info API response
        (see the sample payload: job_id, job_title, job_description,
        job_requirement, job_expired_date, job_location_city, and a
        bunch of extra fields that go straight into `specifications`).
        """
        return {
            "description": data.get("job_description") or None,
            "requirements": data.get("job_requirement") or None,
            "location": data.get("job_location_city") or None,
            "expired_at": self._parse_date(data.get("job_expired_date")),
            "specifications": self._detail_specifications(data),
        }

    @classmethod
    def _detail_specifications(cls, data: dict) -> dict[str, Any]:
        """
        Generic pass over the job-info payload: every key that isn't
        already mapped onto a Job column (_CORE_DETAIL_KEYS) or excluded
        as internal tracking noise (_IGNORED_DETAIL_KEYS) becomes one
        {label: value} entry. Because this loops over `data.items()`
        rather than pulling out named fields one by one, a field added
        to the endpoint later (e.g. "so_luong_tuyen_confirmed") is picked
        up automatically the next time this runs -- no code change
        needed here, only an optional label in _DETAIL_LABELS if you
        want it to look nicer than the raw key.
        """
        specifications: dict[str, Any] = {}

        for key, value in data.items():
            if key in cls._CORE_DETAIL_KEYS or key in cls._IGNORED_DETAIL_KEYS:
                continue

            # "company_industry" is a list of {"id":.., "name":..} dicts
            # -- collapse it into one readable string.
            if key == "company_industry" and isinstance(value, list):
                value = ", ".join(
                    industry.get("name", "")
                    for industry in value
                    if isinstance(industry, dict) and industry.get("name")
                )

            if value in (None, "", [], {}):
                continue

            label = cls._DETAIL_LABELS.get(key, key)
            specifications[label] = value

        return specifications

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        # e.g. "2026-09-26T20:21:32+07:00"
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[datetime]:
        # e.g. "2026-10-25" (date only, no time)
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None