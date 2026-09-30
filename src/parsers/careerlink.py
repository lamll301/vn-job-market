from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

from bs4 import BeautifulSoup

from models.job import Job


class CareerLinkParser:
    """
    Parses CareerLink pages (server-rendered HTML).

    - parse(): job-search listing pages. Only a summary card per job is
      available here, so `description`/`requirements` are left as None —
      call parse_detail() on each job's detail page to fill those in.
    - parse_detail(): a single job's detail page
      (e.g. /tim-viec-lam/<slug>/<id>). Full description, requirements,
      exact posted/expiry dates and extra metadata (benefits, tags,
      career level, company info) all live here.
    """

    def __init__(self, base_url: str = "https://www.careerlink.vn"):
        self.base_url = base_url.rstrip("/")

    def parse(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "html.parser")
        now = datetime.now()

        jobs: list[Job] = []
        for item in soup.select("ul.list-group > li.job-item"):
            job = self._parse_item(item, now)
            if job is not None:
                jobs.append(job)

        return jobs

    def _parse_item(self, item, now: datetime) -> Optional[Job]:
        link_tag = item.select_one("a.job-link")
        if not link_tag or not link_tag.get("href"):
            return None

        url = self._absolute_url(link_tag["href"])

        title_tag = item.select_one("h5.job-name")
        title = (
            title_tag.get_text(strip=True)
            if title_tag
            else (link_tag.get("title") or "").strip()
        )

        company_tag = item.select_one("a.job-company")
        company = company_tag.get_text(strip=True) if company_tag else ""

        save_btn = item.select_one("button.save-btn[data-job-id]")
        source_id = save_btn["data-job-id"].strip() if save_btn else self._extract_id_from_url(url)
        if not source_id:
            return None

        location = self._parse_location(item)
        salary = self._parse_salary(item)
        position = self._parse_position(item)
        posted_at = self._parse_posted_at(item)

        return Job(
            source="careerlink",
            source_id=str(source_id),
            title=title,
            company=company,
            location=location,
            address=None,
            salary=salary,
            url=url,
            description=None,
            requirements=None,
            benefits=None,
            contact=None,
            posted_at=posted_at,
            expired_at=None,
            crawled_at=now,
            created_at=now,
        )

    def _absolute_url(self, href: str) -> str:
        if href.startswith("http"):
            return href
        return f"{self.base_url}{href}"

    @staticmethod
    def _parse_location(item) -> Optional[str]:
        location_tag = item.select_one("div.job-location")
        if not location_tag:
            return None
        names = [a.get_text(strip=True) for a in location_tag.select("a")]
        names = [n for n in names if n]
        return ", ".join(names) if names else None

    @staticmethod
    def _parse_salary(item) -> Optional[str]:
        salary_tag = item.select_one("span.job-salary")
        if not salary_tag:
            return None
        text = salary_tag.get_text(strip=True)
        return text or None

    @staticmethod
    def _parse_position(item) -> Optional[str]:
        position_tag = item.select_one("a.job-position")
        if not position_tag:
            return None
        text = position_tag.get_text(strip=True)
        return text or None

    @staticmethod
    def _parse_posted_at(item) -> Optional[datetime]:
        # CareerLink renders a hidden unix timestamp and formats it
        # client-side via JS (data-datetime attr on span.cl-datetime).
        dt_tag = item.select_one("span.cl-datetime[data-datetime]")
        if not dt_tag:
            return None
        try:
            return datetime.fromtimestamp(int(dt_tag["data-datetime"]))
        except (ValueError, TypeError, KeyError):
            return None

    @staticmethod
    def _extract_id_from_url(url: str) -> Optional[str]:
        # Job URLs look like: .../ten-viec-lam/3624595?area_code=HP&source=site
        path = url.split("?", 1)[0].rstrip("/")
        tail = path.rsplit("/", 1)[-1]
        return tail if tail.isdigit() else None

    # ------------------------------------------------------------------
    # Detail page (e.g. /tim-viec-lam/nhan-vien-kiem-thu-phan-mem/3622348)
    # ------------------------------------------------------------------

    def parse_detail(self, html: str) -> dict[str, Any]:
        """
        Parse a job detail page and return a dict of fields to merge onto
        an existing Job (from parse()): description, requirements,
        benefits, contact, salary, location, address, posted_at,
        expired_at — plus extras that don't map onto Job's columns (tags,
        career_level, education, experience, job_type, company_url,
        company_size), meant to be stashed in Job.raw_data.

        CareerLink also embeds a schema.org JobPosting JSON-LD block,
        which is used for the exact posted/expiry timestamps since those
        are only shown as relative text ("Hết hạn trong: 19 Ngày") in the
        visible HTML.
        """
        soup = BeautifulSoup(html, "html.parser")
        job_ld = self._extract_job_ld(soup)

        desc_tag = soup.select_one("#section-job-description .rich-text-content")
        requirements_tag = soup.select_one("#section-job-skills .rich-text-content")

        return {
            "description": self._inner_html(desc_tag),
            "requirements": self._inner_html(requirements_tag),
            "benefits": self._detail_benefits(soup),
            "contact": self._detail_contact(soup),
            "salary": self._detail_salary(soup),
            "location": self._detail_location(soup),
            "address": self._detail_address(soup),
            "posted_at": self._parse_ld_datetime(job_ld.get("datePosted")) if job_ld else None,
            "expired_at": self._parse_ld_datetime(job_ld.get("validThrough")) if job_ld else None,
            "specifications": self._detail_specifications(soup),
            # "tags": [t.get_text(strip=True) for t in soup.select(".tags-container a.chip")],
            # "job_type": self._summary_value(soup, "Loại công việc"),
            # "career_level": self._summary_value(soup, "Cấp bậc"),
            # "education": self._summary_value(soup, "Học vấn"),
            # "experience": self._summary_value(soup, "Kinh nghiệm"),
            # "company_url": self._company_website(soup),
            # "company_size": self._company_size(soup),
        }

    @staticmethod
    def _inner_html(tag) -> Optional[str]:
        if not tag:
            return None
        html = tag.decode_contents().strip()
        return html or None

    @staticmethod
    def _extract_job_ld(soup) -> Optional[dict[str, Any]]:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(payload, dict) and payload.get("@type") == "JobPosting":
                return payload
        return None

    @staticmethod
    def _parse_ld_datetime(value) -> Optional[datetime]:
        # e.g. "2026-09-14" (datePosted) or "2026-10-14T23:59:59+00:00" (validThrough)
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _detail_salary(soup) -> Optional[str]:
        salary_tag = soup.select_one("#job-salary span.text-primary")
        return salary_tag.get_text(strip=True) if salary_tag else None

    @staticmethod
    def _detail_location(soup) -> Optional[str]:
        location_tag = soup.select_one("#job-location a")
        return location_tag.get_text(strip=True) if location_tag else None

    @staticmethod
    def _detail_address(soup) -> Optional[str]:
        container = soup.select_one("#job-offices")
        if not container:
            return None
        # Structure: <span><span class="font-weight-bold">VP CHÍNH</span><span> - <address...></span></span>
        spans = [s.get_text(strip=True) for s in container.select("span > span")]
        spans = [s for s in spans if s]
        if not spans:
            return container.get_text(strip=True) or None
        address = spans[-1]
        return re.sub(r"^[\s\-]+", "", address) or None

    @staticmethod
    def _detail_benefits(soup) -> Optional[str]:
        items = soup.select("#section-job-benefits .job-benefit-item span")
        texts = [b.get_text(strip=True) for b in items if b.get_text(strip=True)]
        return "\n".join(texts) if texts else None

    @staticmethod
    def _summary_value(soup, label: str) -> Optional[str]:
        for item in soup.select(".job-summary-item"):
            label_tag = item.select_one(".summary-label")
            if label_tag and label_tag.get_text(strip=True) == label:
                value_tag = item.select_one(".font-weight-bolder")
                if value_tag:
                    text = value_tag.get_text(strip=True)
                    return text or None
        return None

    @staticmethod
    def _company_website(soup) -> Optional[str]:
        link = soup.select_one(".list-company-info a[target='_blank']")
        href = link.get("href") if link else None
        return href.strip() if href else None

    @staticmethod
    def _company_size(soup) -> Optional[str]:
        for item in soup.select(".list-company-info > div"):
            if item.select_one("i.cli-users"):
                span = item.select_one("span")
                if span:
                    text = span.get_text(strip=True)
                    return text or None
        return None

    @staticmethod
    def _detail_contact(soup) -> Optional[str]:
        parts = []

        name_tag = soup.select_one(".contact-person .person-name")
        if name_tag:
            text = name_tag.get_text(strip=True)
            if text:
                parts.append(text)

        note_tag = soup.select_one(".contact-person .rich-text-content")
        if note_tag:
            text = note_tag.get_text(separator=" ", strip=True)
            if text:
                parts.append(text)

        return "\n".join(parts) if parts else None

    @staticmethod
    def _detail_specifications(soup) -> dict[str, str]:
        specifications: dict[str, str] = {}
 
        container = soup.select_one("#section-job-summary")
        if not container:
            return specifications
 
        for item in container.select(".job-summary-item"):
            label_tag = item.select_one(".summary-label")
            value_tag = item.select_one(".font-weight-bolder")
            if not label_tag or not value_tag:
                continue
 
            label = label_tag.get_text(strip=True)
            if not label:
                continue
 
            links = value_tag.select("a")
            if links:
                value = ", ".join(
                    text for a in links if (text := a.get_text(strip=True))
                )
            else:
                value = value_tag.get_text(strip=True)
 
            if value:
                specifications[label] = value
 
        return specifications