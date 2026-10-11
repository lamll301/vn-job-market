from __future__ import annotations

import asyncio
import sys

from core.run import run_recheck
from database.repository import JobRepository

sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    """Entry point cho GitHub Actions: chỉ re-check, không import UI (customtkinter).

    Không bắt exception ở đây để lỗi nghiêm trọng làm workflow fail (exit code != 0)
    và GitHub gửi thông báo. Site không phản hồi đã được RecheckService xử lý gọn.
    """
    asyncio.run(run_recheck(JobRepository()))


if __name__ == "__main__":
    main()
