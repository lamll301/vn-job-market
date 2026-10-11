from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Thêm thư mục src vào sys.path để Python nhận diện được các package core, database,...
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent / "src"
sys.path.insert(0, str(src_dir))

sys.stdout.reconfigure(encoding="utf-8")

from core.run import run_all
from database.repository import JobRepository


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