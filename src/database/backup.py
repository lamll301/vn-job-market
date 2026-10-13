import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Protocol, Sequence

from config import (
    MONGODB_URI,
    MONGODB_DATABASE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from notifications.telegram import TelegramDestination

BACKUP_ROOT = Path("backups")


class BackupDestination(Protocol):
    name: str

    def upload(self, path: Path, caption: str = "") -> None: ...


def build_destinations() -> list[BackupDestination]:
    """Chỉ bật destination nào đã được cấu hình trong .env."""
    destinations: list[BackupDestination] = []
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        destinations.append(TelegramDestination(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID))
    return destinations


def _run_mongodump(out_dir: Path) -> None:
    subprocess.run(
        [
            "mongodump",
            f"--uri={MONGODB_URI}",
            f"--db={MONGODB_DATABASE}",
            f"--out={out_dir}",
        ],
        check=True,
    )


def _archive(folder: Path) -> Path:
    """Nén folder thành .zip cạnh nó rồi xóa folder gốc."""
    archive = Path(shutil.make_archive(str(folder), "zip", root_dir=folder))
    shutil.rmtree(folder)
    return archive


def _upload_all(
    destinations: Sequence[BackupDestination], archive: Path, caption: str
) -> list[str]:
    """Trả về tên các destination upload thất bại."""
    failed: list[str] = []
    for destination in destinations:
        try:
            destination.upload(archive, caption)
            print(f"[OK] Đã gửi backup tới {destination.name}")
        except Exception as exc:
            failed.append(destination.name)
            print(f"[!] Gửi tới {destination.name} thất bại: {exc}")
    return failed


def backup_database(
    destinations: Sequence[BackupDestination] = (), strict: bool = False
) -> Path:
    """strict=True: báo lỗi nếu không có destination hoặc upload thất bại
    (dùng khi chạy CI, nơi file local không được giữ lại)."""
    if strict and not destinations:
        raise RuntimeError("Chưa cấu hình nơi lưu backup (Telegram), bản backup sẽ mất khi runner kết thúc")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    _run_mongodump(backup_dir)
    archive = _archive(backup_dir)
    print(f"Database backup completed: {archive}")

    caption = f"Backup {MONGODB_DATABASE} - {timestamp}"
    failed = _upload_all(destinations, archive, caption)
    if strict and failed:
        raise RuntimeError(f"Upload thất bại: {', '.join(failed)}")
    return archive