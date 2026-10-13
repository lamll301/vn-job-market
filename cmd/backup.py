from __future__ import annotations

import sys
from pathlib import Path

# Thêm thư mục src vào sys.path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent / "src"
sys.path.insert(0, str(src_dir))

sys.stdout.reconfigure(encoding="utf-8")

from database.backup import backup_database, build_destinations


def main() -> None:
  """Entry point cho GitHub Actions: backup rồi gửi Telegram.
  Lỗi thì thoát mã 1 để workflow báo đỏ."""
  try:
    backup_database(build_destinations(), strict=True)
  except Exception as exc:
    print(f"[X] Backup thất bại: {exc}")
    sys.exit(1)


if __name__ == "__main__":
  main()