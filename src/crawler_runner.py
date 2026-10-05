from __future__ import annotations

import asyncio
import sys

from core.run import run_all
from database.repository import JobRepository

sys.stdout.reconfigure(encoding='utf-8')


async def async_main() -> None:
    repository = JobRepository()
    await run_all(repository)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n[!] Đã dừng chương trình do người dùng bấm Ctrl+C.")
    except Exception as exc:
        print(f"\n[X] Đã xảy ra lỗi: {exc}")


if __name__ == "__main__":
    main()