from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from bs4 import BeautifulSoup

from models.job import Job


class TopCVParser:
    """
    Parses TopCV pages (server-rendered HTML, same shape as CareerLink).

    - parse(): job-search listing pages
      (e.g. /tim-viec-lam-software-engineering-tai-hai-phong-l9cr257cb258).
      Only a summary card per job is available here, so `description`/
      `requirements` are left as None -- call parse_detail() on each
      job's detail page (the URL already sitting on the Job from parse())
      to fill those in, matching the ListFetcher/DetailEnricher contract
      used across the app (see core/interfaces.py).
    - parse_detail(): a single job's detail page
      (e.g. /viec-lam/<slug>/<id>.html). TopCV embeds a schema.org
      JobPosting JSON-LD block there with the full description /
      requirements / benefits and exact posted/expiry timestamps, so
      parse_detail() reads that first and only falls back to the
      visible HTML for whatever the JSON-LD payload doesn't carry
      (contact info, the job-summary spec table).

    NOTE: TopCV's detail-page HTML was not available when this parser
    was written -- only the listing page and a fetched job-search HTML
    dump were on hand. The `parse()` method below is verified against
    that real listing markup; `parse_detail()` is written defensively
    (JSON-LD first, several CSS-selector fallbacks) but its selectors
    should be double-checked against a real detail page the first time
    this runs, the same way vietnamworks.py's RETRIEVE_FIELDS comment
    flags an untested guess.
    """

    def __init__(self, base_url: str = "https://www.topcv.vn"):
        self.base_url = base_url.rstrip("/")

    def parse(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "html.parser")
        now = datetime.now()

        jobs: list[Job] = []
        for item in soup.select("div.job-item-search-result[data-job-id]"):
            job = self._parse_item(item, now)
            if job is not None:
                jobs.append(job)

        return jobs

    def _parse_item(self, item, now: datetime) -> Optional[Job]:
        source_id = (item.get("data-job-id") or "").strip()
        if not source_id:
            return None

        title_tag = (
            item.select_one("h3.title a span[title]")
            or item.select_one("h3.title a span")
        )
        title = title_tag.get_text(strip=True) if title_tag else ""

        link_tag = item.select_one("h3.title a") or item.select_one(".avatar a")
        url = self._absolute_url(link_tag["href"]) if link_tag and link_tag.get("href") else ""

        company_tag = item.select_one(".company-name")
        company = company_tag.get_text(strip=True) if company_tag else ""

        location = self._parse_location(item)
        salary = self._parse_salary(item)

        return Job(
            source="topcv",
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
            # TopCV's listing card only shows a relative string ("6 ngày
            # trước") plus an *update*-time tooltip ("Cập nhật 15 phút
            # trước") -- neither is an absolute timestamp, so posted_at
            # is left to parse_detail(), which reads the JobPosting
            # JSON-LD's datePosted on the detail page.
            posted_at=None,
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
        city_tag = item.select_one(".address .city-text")
        if not city_tag:
            return None
        text = city_tag.get_text(strip=True)
        return text or None

    @staticmethod
    def _parse_salary(item) -> Optional[str]:
        salary_tag = (
            item.select_one("label.salary span")
            or item.select_one("label.title-salary")
        )
        if not salary_tag:
            return None
        text = salary_tag.get_text(strip=True)
        return text or None

    # ------------------------------------------------------------------
    # Detail page (e.g. /viec-lam/<slug>/<id>.html)
    # ------------------------------------------------------------------

    def parse_detail(self, html: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        job_ld = self._extract_job_ld(soup)

        description_tag = self._find_detail_section(soup, ["Mô tả công việc"])
        requirement_tag = self._find_detail_section(soup, ["Yêu cầu ứng viên"])
        benefit_tag = self._find_detail_section(soup, ["Quyền lợi"])

        specifications = self._detail_specifications(soup)
        specifications.update(self._detail_summary_box(soup))   # + "Kinh nghiệm"
        specifications.update(self._detail_company_info(soup))  # + Quy mô/Địa chỉ công ty
        if job_ld:
            if job_ld.get("industry"):
                specifications["Ngành nghề"] = job_ld["industry"]
            if job_ld.get("skills"):
                specifications["Kỹ năng"] = job_ld["skills"]

        return {
            "description": description_tag.decode_contents().strip() if description_tag else None,
            "requirements": requirement_tag.decode_contents().strip() if requirement_tag else None,
            "benefits": self._benefits_text(benefit_tag),
            "contact": self._detail_contact(soup),
            "salary": self._detail_salary(soup, job_ld),
            "location": self._detail_location(soup, job_ld),
            "address": self._detail_address(soup, job_ld),
            "posted_at": self._parse_ld_datetime(job_ld.get("datePosted")) if job_ld else None,
            "expired_at": self._parse_ld_datetime(job_ld.get("validThrough")) if job_ld else None,
            "specifications": specifications,
        }


    @staticmethod
    def _detail_summary_box(soup) -> dict[str, str]:
        """Box tóm tắt đầu trang (Địa điểm/Kinh nghiệm/Hạn ứng tuyển) --
        chỉ lấy 'Kinh nghiệm', 2 field còn lại đã có ở location/expired_at."""
        result: dict[str, str] = {}
        for item in soup.select(".box-header-job-list-info__item"):
            label_tag = item.select_one(".list-info__content__title")
            value_tag = item.select_one(".list-info__content__desc")
            if not label_tag or not value_tag:
                continue
            label = label_tag.get_text(strip=True)
            if label != "Kinh nghiệm":
                continue
            value = value_tag.get_text(strip=True)
            if value:
                result[label] = value
        return result


    @staticmethod
    def _detail_company_info(soup) -> dict[str, str]:
        """Sidebar thông tin công ty -- Quy mô, Địa chỉ (trụ sở công ty,
        khác với địa điểm làm việc của tin đăng)."""
        result: dict[str, str] = {}
        for item in soup.select(".box-company-info-detail__list--item"):
            label_tag = item.select_one(".box-company-info-detail__list--item-label")
            value_tag = item.select_one(".box-company-info-detail__list--item-value")
            if not label_tag or not value_tag:
                continue
            label = label_tag.get_text(strip=True).rstrip(":")
            value = value_tag.get_text(strip=True)
            if label and value:
                result[f"Công ty - {label}"] = value
        return result
    
    @staticmethod
    def _find_detail_section(soup, title_keywords: list[str]):
        """
        Mỗi block info trên TopCV có dạng:
            <div class="box-job-information-detail-item ...">
                <div class="box-job-information-detail-item__title">
                    <h2 class="box-job-information-detail-item__title--title">TIÊU ĐỀ</h2>
                </div>
                <div class="box-job-information-detail-item__text">...</div>
            </div>
        Tìm đúng block theo tiêu đề (vd "Mô tả công việc", "Yêu cầu ứng viên",
        "Quyền lợi ứng viên") và trả về div `__text` của nó.
        """
        for item in soup.select("div.box-job-information-detail-item"):
            title_tag = item.select_one(".box-job-information-detail-item__title--title")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if any(kw in title for kw in title_keywords):
                return item.select_one(".box-job-information-detail-item__text")
        return None

    @staticmethod
    def _benefits_text(section) -> Optional[str]:
        if not section:
            return None
        items = section.select("li")
        texts = [li.get_text(" ", strip=True) for li in items if li.get_text(strip=True)]
        return "\n".join(texts) if texts else None

    @staticmethod
    def _extract_job_ld(soup) -> Optional[dict[str, Any]]:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(payload, dict) and payload.get("@type") == "JobPosting":
                return payload
            # TopCV sometimes wraps JobPosting inside a @graph list
            # alongside BreadcrumbList (see the breadcrumb JSON-LD in
            # the listing page for the same pattern).
            if isinstance(payload, dict) and isinstance(payload.get("@graph"), list):
                for node in payload["@graph"]:
                    if isinstance(node, dict) and node.get("@type") == "JobPosting":
                        return node
        return None

    @staticmethod
    def _extract_rich_text(soup, selectors: list[str], job_ld, ld_key: str) -> Optional[str]:
        for selector in selectors:
            tag = soup.select_one(selector)
            if tag is not None:
                html = tag.decode_contents().strip()
                if html:
                    return html
        if job_ld and job_ld.get(ld_key):
            text = str(job_ld[ld_key]).strip()
            return text or None
        return None

    @staticmethod
    def _detail_benefits(soup) -> Optional[str]:
        items = soup.select("div.job-welfare li") or soup.select(".job-benefit li")
        texts = [b.get_text(strip=True) for b in items if b.get_text(strip=True)]
        return "\n".join(texts) if texts else None

    @staticmethod
    def _detail_contact(soup) -> Optional[str]:
        parts = []

        name_tag = soup.select_one(".job-recruiter-name") or soup.select_one(".company-contact .name")
        if name_tag:
            text = name_tag.get_text(strip=True)
            if text:
                parts.append(text)

        address_tag = soup.select_one(".job-recruiter-address") or soup.select_one(".company-contact .address")
        if address_tag:
            text = address_tag.get_text(separator=" ", strip=True)
            if text:
                parts.append(text)

        return "\n".join(parts) if parts else None

    @staticmethod
    def _detail_salary(soup, job_ld) -> Optional[str]:
        salary_tag = soup.select_one(".box-header-job__salary--title")
        if salary_tag:
            text = salary_tag.get_text(strip=True)
            if text:
                return text

    @staticmethod
    def _detail_location(soup, job_ld) -> Optional[str]:
        # location = cấp Tỉnh/Thành phố
        if job_ld:
            loc = job_ld.get("jobLocation") or {}
            address = loc.get("address") if isinstance(loc, dict) else None
            if isinstance(address, dict) and address.get("addressRegion"):
                return address["addressRegion"]
        return None

    @staticmethod
    def _detail_address(soup, job_ld) -> Optional[str]:
        # address = số nhà/đường + phường/xã (không gồm tỉnh/thành)
        if job_ld:
            loc = job_ld.get("jobLocation") or {}
            address = loc.get("address") if isinstance(loc, dict) else None
            if isinstance(address, dict):
                parts = [
                    address.get("streetAddress"),
                    address.get("addressLocality"),
                ]
                parts = [p for p in parts if p]
                if parts:
                    return ", ".join(parts)
        return None

    @staticmethod
    def _parse_ld_datetime(value) -> Optional[datetime]:
        # e.g. "2026-09-14" (datePosted) or "2026-10-14T23:59:59+00:00"
        # (validThrough), same shape as CareerLink's JobPosting JSON-LD.
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _detail_specifications(soup) -> dict[str, str]:
        specifications: dict[str, str] = {}

        # Thông tin chung (Cấp bậc, Học vấn, Số lượng tuyển, ...)
        for item in soup.select(".box-job-information-general-info-list__item"):
            label_tag = item.select_one(".box-job-information-general-info-list__item--content-title")
            value_tag = item.select_one(".box-job-information-general-info-list__item--content-desc")
            if not label_tag or not value_tag:
                continue
            label = label_tag.get_text(strip=True)
            value = value_tag.get_text(strip=True)
            if label and value:
                specifications[label] = value

        # Địa điểm và thời gian -- chỉ lấy "Thời gian làm việc"
        # ("Địa điểm làm việc" đã có ở location/address, "Cách thức ứng tuyển"
        # không phải specification nên bỏ qua)
        for item in soup.select(".box-job-information-address-and-time-list__item"):
            label_tag = item.select_one(".box-job-information-address-and-time-list__item--title")
            value_tag = item.select_one(".box-job-information-address-and-time-list__item--content")
            if not label_tag or not value_tag:
                continue
            label = label_tag.get_text(strip=True)
            if label != "Thời gian làm việc":
                continue
            texts = [li.get_text(strip=True) for li in value_tag.select("li") if li.get_text(strip=True)]
            value = "; ".join(texts) if texts else value_tag.get_text(" ", strip=True)
            if value:
                specifications[label] = value

        return specifications