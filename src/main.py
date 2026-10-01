from __future__ import annotations

import asyncio
import sys
import customtkinter as ctk
from ui.main_window import MainWindow
from database.repository import JobRepository
from core.run import run_all

sys.stdout.reconfigure(encoding='utf-8')

def run_ui() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
 
    root = ctk.CTk()
    MainWindow(root, repository=JobRepository())
    root.mainloop()

async def async_main() -> None:
    repository = JobRepository()
    await run_all(repository)

def run_crawler() -> None:
    """Chạy crawler ở chế độ dòng lệnh (không mở giao diện)."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n[!] Đã dừng chương trình do người dùng bấm Ctrl+C.")
    except Exception as exc:
        print(f"\n[X] Đã xảy ra lỗi: {exc}")

if __name__ == "__main__":
    # run_ui()
    run_crawler()