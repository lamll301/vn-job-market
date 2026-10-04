from __future__ import annotations

from config import CAREERLINK_SEARCHES, TOPCV_SEARCHES, VIETNAMWORKS_SEARCHES
from core.careerlink_pipeline import CAREERLINK_HEADERS
from core.careerlink_pipeline import build_pipeline as build_careerlink_pipeline
from core.http_client import AsyncHttpClient, SiteUnreachableError
from core.topcv_pipeline import TOPCV_HEADERS
from core.topcv_pipeline import build_pipeline as build_topcv_pipeline
from core.vietnamworks_pipeline import VIETNAMWORKS_HEADERS
from core.vietnamworks_pipeline import build_pipeline as build_vietnamworks_pipeline
from database.repository import JobRepository


async def run_careerlink(repository: JobRepository, concurrency: int = 2) -> None:
    """Chạy tiến trình cào dữ liệu cho CareerLink."""
    print("==================================================")
    print("     Bắt đầu tiến trình cào dữ liệu CareerLink    ")
    print("==================================================")

    async with AsyncHttpClient(
        headers=CAREERLINK_HEADERS,
        concurrency=concurrency,
        base_min_delay=3.0,
        base_max_delay=6.0,
        max_retries=3,
        backoff_base=5.0,
        backoff_cap=60.0,
        max_consecutive_failures=3,
    ) as http_client:
        for search_key in CAREERLINK_SEARCHES:
            print(f"\n---> Đang cào danh mục: '{search_key}'")
            pipeline = build_careerlink_pipeline(
                search_key=search_key,
                http_client=http_client,
                repository=repository,
                concurrency=concurrency,
            )
            try:
                await pipeline.run()
            except SiteUnreachableError:
                print("[STOP] CareerLink không phản hồi, dừng. Chạy lại sau.")
                return

    print("\n[OK] Hoàn thành cào dữ liệu từ CareerLink.")


async def run_vietnamworks(repository: JobRepository, concurrency: int = 4) -> None:
    """Chạy tiến trình cào dữ liệu cho VietnamWorks."""
    print("==================================================")
    print("   Bắt đầu tiến trình cào dữ liệu VietnamWorks    ")
    print("==================================================")

    async with AsyncHttpClient(
        headers=VIETNAMWORKS_HEADERS,
        concurrency=concurrency,
        base_min_delay=1.0,
        base_max_delay=2.5,
        max_retries=4,
        backoff_base=5.0,
        backoff_cap=60.0,
    ) as http_client:
        for search_key in VIETNAMWORKS_SEARCHES:
            print(f"\n---> Đang cào danh mục: '{search_key}'")
            pipeline = build_vietnamworks_pipeline(
                search_key=search_key,
                http_client=http_client,
                repository=repository,
                concurrency=concurrency,
            )
            try:
                await pipeline.run()
            except SiteUnreachableError:
                print("[STOP] VietnamWorks không phản hồi, dừng. Chạy lại sau.")
                return

    print("\n[OK] Hoàn thành cào dữ liệu từ VietnamWorks.")


async def run_topcv(repository: JobRepository, concurrency: int = 4) -> None:
    """Chạy tiến trình cào dữ liệu cho TopCV."""
    print("==================================================")
    print("       Bắt đầu tiến trình cào dữ liệu TopCV       ")
    print("==================================================")

    async with AsyncHttpClient(
        headers=TOPCV_HEADERS,
        concurrency=concurrency,
        base_min_delay=1.5,
        base_max_delay=3.0,
        max_retries=4,
        backoff_base=5.0,
        backoff_cap=60.0,
    ) as http_client:
        for search_key in TOPCV_SEARCHES:
            print(f"\n---> Đang cào danh mục: '{search_key}'")
            pipeline = build_topcv_pipeline(
                search_key=search_key,
                http_client=http_client,
                repository=repository,
                concurrency=concurrency,
            )
            try:
                await pipeline.run()
            except SiteUnreachableError:
                print("[STOP] TopCV không phản hồi, dừng. Chạy lại sau.")
                return

    print("\n[OK] Hoàn thành cào dữ liệu từ TopCV.")


async def run_all(repository: JobRepository) -> None:
    await run_vietnamworks(repository, concurrency=4)
    await run_careerlink(repository, concurrency=2)
    # await run_topcv(repository, concurrency=4)