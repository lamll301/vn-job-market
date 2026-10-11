from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Thêm thư mục src vào sys.path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent / "src"
sys.path.insert(0, str(src_dir))

sys.stdout.reconfigure(encoding="utf-8")

from core.run import run_recheck
from database.repository import JobRepository


def main() -> None:
  """Entry point cho GitHub Actions: chỉ re-check, không import UI (customtkinter)."""
  asyncio.run(run_recheck(JobRepository()))


if __name__ == "__main__":
  main()