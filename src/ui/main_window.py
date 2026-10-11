import os
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

import customtkinter as ctk

from ui.components.crawl_progress_dialog import (
    CrawlProgressTheme,
    CrawlResult,
    CrawlSession,
)
from ui.components.pagination import PaginationBar, PaginationTheme
from ui.views.job_detail_view import JobDetailTheme, JobDetailView
from ui.views.job_table_view import JobTableTheme, JobTableView


class MainWindow:
    # ============================================================
    # Window
    # ============================================================

    WINDOW_WIDTH = 1280
    WINDOW_HEIGHT = 720

    MIN_WINDOW_WIDTH = 1000
    MIN_WINDOW_HEIGHT = 620

    # ============================================================
    # Layout
    # ============================================================

    LEFT_RATIO = 0.60
    RIGHT_RATIO = 0.40

    PAGE_SIZE = 20

    SEARCH_BORDER = "#D1D5DB"   # viền ô search lúc bình thường
    FILTER_ACTIVE = "#1D4ED8"   # xanh dương đậm khi cột đang lọc / sort
    HOVER_BG = "#F3F4F6"

    # ============================================================
    # Colors
    # ============================================================

    BG = "#F5F6F8"
    WHITE = "#FFFFFF"

    BORDER = "#E5E7EB"
    BORDER_LIGHT = "#EEF0F2"

    TEXT_PRIMARY = "#111827"
    TEXT_SECONDARY = "#6B7280"
    TEXT_MUTED = "#9CA3AF"

    PRIMARY = "#2563EB"
    PRIMARY_HOVER = "#1D4ED8"

    TAG_BG = "#EFF6FF"
    TAG_TEXT = "#2563EB"

    SELECTED = "#DBEAFE"

    JD_BG = "#F9FAFB"

    SALARY_COLOR = "#16A34A"

    # Crawl: logic + dialog tiến độ nằm ở components/crawl_progress_dialog.py
    CANCEL_COLOR = "#B91C1C"

    _crawl = None               # CrawlSession đang chạy (None = rảnh)
    _backup_running = False     # đang chạy mongodump
    _toast = None
    _toast_after_id = None

    # ============================================================
    # Constructor
    # ============================================================

    def __init__(self, root, repository):
        self.root = root
        self.repository = repository

        self.jobs = []
        self.filtered_jobs = []

        self.is_loading = True
        self.load_error = None

        self._configure_window()
        self._configure_styles()
        self._build_ui()

        self.load_jobs()

    # ============================================================
    # Window
    # ============================================================

    def _configure_window(self):
        self.root.title("Vietnam Job Market")
        self.root.iconbitmap("assets/sunflower_10761.ico")
        self.root.resizable(True, True)

        self.root.minsize(
            self.MIN_WINDOW_WIDTH,
            self.MIN_WINDOW_HEIGHT
        )

        self.root.geometry(
            f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}"
        )

        self._center_window()

        self.root.configure(
            fg_color=self.BG
        )

    def _center_window(self):
        self.root.update_idletasks()

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        x = max(
            0,
            (screen_width - self.WINDOW_WIDTH) // 2
        )

        y = max(
            0,
            ((screen_height - self.WINDOW_HEIGHT) // 2) - 40
        )

        self.root.geometry(
            f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}"
            f"+{x}+{y}"
        )

    # ============================================================
    # ttk Styles
    # ============================================================

    def _configure_styles(self):
        # Style của Treeview / Scrollbar nằm ở views/job_table_view.py
        try:
            ttk.Style().theme_use("clam")
        except tk.TclError:
            pass

    # ============================================================
    # Main UI
    # ============================================================

    def _build_ui(self):
        self.main_frame = ctk.CTkFrame(
            self.root,
            fg_color=self.BG,
            corner_radius=0
        )

        self.main_frame.pack(
            fill="both",
            expand=True,
            padx=14,
            pady=14
        )

        # --------------------------------------------------------
        # Single row containing the two main columns
        # (Toolbar now lives inside the Left panel, not here)
        # --------------------------------------------------------

        self.main_frame.grid_rowconfigure(
            0,
            weight=1
        )

        self.main_frame.grid_columnconfigure(
            0,
            weight=1
        )

        self._build_content()

    # ============================================================
    # Content — 60 / 40 split between Left and Right panels
    # ============================================================

    def _build_content(self):
        self.content = ctk.CTkFrame(
            self.main_frame,
            fg_color=self.BG,
            corner_radius=0
        )

        self.content.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        # --------------------------------------------------------
        # 60 / 40 split
        #
        # weight 60 : 40 + cùng uniform group -> tỉ lệ cố định,
        # không bị minsize hay nội dung bên trong làm lệch.
        # --------------------------------------------------------

        self.content.grid_columnconfigure(
            0,
            weight=round(self.LEFT_RATIO * 100),
            uniform="split"
        )

        self.content.grid_columnconfigure(
            1,
            weight=round(self.RIGHT_RATIO * 100),
            uniform="split"
        )

        self.content.grid_rowconfigure(
            0,
            weight=1
        )

        self._build_left_panel()
        self._build_right_panel()

    # ============================================================
    # Left Panel (~60%)
    #
    # Row 0 = Toolbar (Crawl / Backup / Search)
    # Row 1 = Data table
    # Row 2 = Pagination
    # ============================================================

    def _build_left_panel(self):
        self.left_panel = ctk.CTkFrame(
            self.content,
            fg_color=self.BG,
            corner_radius=0
        )

        self.left_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 5)
        )

        self.left_panel.grid_rowconfigure(
            0,
            weight=0
        )

        self.left_panel.grid_rowconfigure(
            1,
            weight=1
        )

        self.left_panel.grid_columnconfigure(
            0,
            weight=1
        )

        self._build_toolbar()
        self._build_table_card()

    # ============================================================
    # Toolbar (now inside the Left panel)
    # ============================================================

    def _build_toolbar(self):
        self.toolbar = ctk.CTkFrame(
            self.left_panel,
            fg_color=self.WHITE,
            corner_radius=10,
            border_width=1,
            border_color=self.BORDER
        )

        self.toolbar.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 10)
        )

        # --------------------------------------------------------
        # Toolbar columns
        #
        # 0 = Crawl
        # 1 = Backup
        # 2 = expandable space
        # 3 = Search
        #
        # Crawl, Backup and Search all stay together inside the
        # Left panel. Nothing from the toolbar is ever placed in
        # the Right panel.
        # --------------------------------------------------------

        self.toolbar.grid_columnconfigure(
            0,
            weight=0
        )

        self.toolbar.grid_columnconfigure(
            1,
            weight=0
        )

        self.toolbar.grid_columnconfigure(
            2,
            weight=1
        )

        self.toolbar.grid_columnconfigure(
            3,
            weight=0
        )

        # --------------------------------------------------------
        # Crawl
        # --------------------------------------------------------

        self.crawl_button = ctk.CTkButton(
            self.toolbar,
            text="Crawl",
            width=80,
            height=36,
            corner_radius=7,
            fg_color=self.PRIMARY,
            hover_color=self.PRIMARY_HOVER,
            text_color=self.WHITE,
            font=("Segoe UI Semibold", 10),
            command=self.on_crawl
        )

        self.crawl_button.grid(
            row=0,
            column=0,
            padx=(10, 5),
            pady=9
        )

        # --------------------------------------------------------
        # Backup
        # --------------------------------------------------------

        self.backup_button = ctk.CTkButton(
            self.toolbar,
            text="Backup",
            width=80,
            height=36,
            corner_radius=7,
            fg_color="#1F2937",
            hover_color="#374151",
            text_color="#FFFFFF",
            border_width=0,
            font=("Segoe UI Semibold", 10),
            command=self.on_backup
        )

        self.backup_button.grid(
            row=0,
            column=1,
            padx=(0, 5),
            pady=9
        )

        # --------------------------------------------------------
        # Search
        # --------------------------------------------------------

        self.search_entry = ctk.CTkEntry(
            self.toolbar,
            width=200,
            height=36,
            corner_radius=7,
            border_width=1,
            border_color=self.BORDER,
            fg_color=self.WHITE,
            text_color=self.TEXT_PRIMARY,
            placeholder_text="Search...",
            placeholder_text_color=self.TEXT_MUTED,
            font=("Segoe UI", 10)
        )

        self.search_entry.configure(border_color=self.SEARCH_BORDER)

        # Focus -> viền xanh dương, rời focus -> trả về xám nhẹ
        self.search_entry.bind(
            "<FocusIn>",
            lambda e: self.search_entry.configure(
                border_color=self.PRIMARY
            ),
            add="+"
        )
        self.search_entry.bind(
            "<FocusOut>",
            lambda e: self.search_entry.configure(
                border_color=self.SEARCH_BORDER
            ),
            add="+"
        )

        self.search_entry.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(10, 10),
            pady=9
        )

        self.search_entry.bind(
            "<KeyRelease>",
            self.on_search
        )

    # ============================================================
    # Table card (data table + pagination), below the toolbar
    # ============================================================

    def _build_table_card(self):
        self.table_card = ctk.CTkFrame(
            self.left_panel,
            fg_color=self.WHITE,
            corner_radius=10,
            border_width=1,
            border_color=self.BORDER
        )

        self.table_card.grid(
            row=1,
            column=0,
            sticky="nsew"
        )

        # --------------------------------------------------------
        # Row 0 = table
        # Row 1 = pagination
        # --------------------------------------------------------

        self.table_card.grid_rowconfigure(
            0,
            weight=1
        )

        self.table_card.grid_rowconfigure(
            1,
            weight=0
        )

        self.table_card.grid_columnconfigure(
            0,
            weight=1
        )

        self._build_table()
        self._build_pagination()

    # ============================================================
    # Table
    # ============================================================

    def _build_table(self):
        # Treeview + filter/sort header + menu chuột phải + overlay trạng thái
        # nằm ở views/job_table_view.py
        self.table = JobTableView(
            self.table_card,
            theme=JobTableTheme(
                white=self.WHITE,
                border=self.BORDER,
                text_primary=self.TEXT_PRIMARY,
                text_secondary=self.TEXT_SECONDARY,
                text_muted=self.TEXT_MUTED,
                primary=self.PRIMARY,
                hover_bg=self.HOVER_BG,
                selected=self.SELECTED,
                active=self.FILTER_ACTIVE
            ),
            get_jobs=lambda: self.jobs,
            on_select=self._on_job_selected,
            on_filter_change=self.on_search,
            on_clear_filters=self.clear_search_and_filters
        )

        self.table.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=7,
            pady=(7, 0)
        )

    def _update_state_overlay(self):
        self.table.update_state(
            loading=self.is_loading,
            error=self.load_error,
            total=len(self.jobs),
            shown=len(self.filtered_jobs)
        )


    # ============================================================
    # Pagination — thanh phân trang nằm ở components/pagination.py
    # ============================================================

    def _build_pagination(self):
        self.pagination = PaginationBar(
            self.table_card,
            theme=PaginationTheme(
                white=self.WHITE,
                border=self.BORDER,
                text_primary=self.TEXT_PRIMARY,
                text_secondary=self.TEXT_SECONDARY,
                hover_bg=self.HOVER_BG
            ),
            page_size=self.PAGE_SIZE,
            on_change=self.refresh_table
        )

        self.pagination.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=7,
            pady=(5, 7)
        )

    # ============================================================
    # Right Panel (~40%) — khung chi tiết JD nằm ở views/job_detail_view.py
    # ============================================================

    def _build_right_panel(self):
        self.detail_view = JobDetailView(
            self.content,
            theme=JobDetailTheme(
                white=self.WHITE,
                jd_bg=self.JD_BG,
                border=self.BORDER,
                border_light=self.BORDER_LIGHT,
                text_primary=self.TEXT_PRIMARY,
                text_secondary=self.TEXT_SECONDARY,
                text_muted=self.TEXT_MUTED,
                primary=self.PRIMARY,
                primary_hover=self.PRIMARY_HOVER,
                tag_bg=self.TAG_BG,
                tag_text=self.TAG_TEXT,
                salary_color=self.SALARY_COLOR
            )
        )

        self.detail_view.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(5, 0)
        )

    # ============================================================
    # Real Data (MongoDB)
    # ============================================================

    def load_jobs(self):
        """Đọc DB ở thread riêng để giao diện không bị đơ."""

        self.is_loading = True
        self.load_error = None
        self._update_state_overlay()

        def worker():
            try:
                docs = self.repository.get_all()
                jobs = [self._to_view_model(doc) for doc in docs]
            except Exception as exc:
                message = str(exc)
                self.root.after(
                    0,
                    lambda: self._on_load_failed(message)
                )
                return

            self.root.after(0, lambda: self._set_jobs(jobs))

        threading.Thread(target=worker, daemon=True).start()

    def _set_jobs(self, jobs):
        self.is_loading = False
        self.load_error = None

        self.jobs = jobs
        self.filtered_jobs = list(jobs)
        self.pagination.reset()

        self.table.prune_filters()
        self.on_search()

    def _on_load_failed(self, message):
        print(f"[X] Lỗi đọc DB: {message}")

        self.is_loading = False
        self.load_error = message

        self._update_state_overlay()

    @staticmethod
    def _fmt_date(value):
        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y")
        return "—"

    def _to_view_model(self, doc):
        """Chuyển document Mongo (từ dataclass Job) sang dict mà UI dùng."""

        return {
            # iid của Treeview phải duy nhất -> ghép source + source_id
            "id": f"{doc.get('source', '')}:{doc.get('source_id', '')}",
            "title": doc.get("title") or "",
            "company": doc.get("company") or "",
            "location": doc.get("location") or "",
            "source": doc.get("source") or "",
            "posted_at": self._fmt_date(doc.get("posted_at")),
            "expire_date": self._fmt_date(doc.get("expired_at")),
            "description": doc.get("description") or "",
            "requirements": doc.get("requirements") or "",
            "address": doc.get("address") or "",
            "salary": doc.get("salary") or "",
            "benefits": doc.get("benefits") or "",
            "contact": doc.get("contact") or "",
            "specifications": doc.get("specifications") or {},
            "url": doc.get("url") or "",
            "posted_at_raw": doc.get("posted_at"),
            "expired_at_raw": doc.get("expired_at")
        }

    # ============================================================
    # Refresh Table
    # ============================================================

    def refresh_table(self):
        self.table.set_rows(
            self.pagination.paginate(self.filtered_jobs)
        )

        self._update_state_overlay()

    # ============================================================
    # Job Selection
    # ============================================================

    def _on_job_selected(self, job):
        """Bảng chọn một job (None = bảng rỗng) -> cập nhật khung chi tiết."""
        if job:
            self.detail_view.show_job(job)
        else:
            self.detail_view.clear()

    # ============================================================
    # Search & filters (logic lọc / sort nằm trong JobTableView)
    # ============================================================

    def _matches_filters(self, job, keyword):
        if not self.table.matches_filters(job):
            return False

        if not keyword:
            return True

        return any(
            keyword in job[key].lower()
            for key in ("title", "company", "location", "source")
        )

    def clear_search_and_filters(self):
        """Reset ô Search + mọi filter ở header rồi nạp lại danh sách."""
        self.search_entry.delete(0, "end")
        self.table.clear_filters()

        self.on_search()

    def on_search(self, event=None):
        keyword = (
            self.search_entry
            .get()
            .strip()
            .lower()
        )

        self.filtered_jobs = self.table.sort_jobs([
            job
            for job in self.jobs
            if self._matches_filters(job, keyword)
        ])

        self.pagination.reset()

        self.refresh_table()

    # ============================================================
    # Actions
    # ============================================================

    def on_crawl(self):
        if self._crawl is not None or self._backup_running:
            return  # đang crawl/backup rồi, không cho chạy chồng

        try:
            from core.run import run_all
        except Exception as exc:
            self._show_toast(f"[X] Không nạp được module crawl: {exc}", "error")
            return

        self.table.close_popups()

        self._set_actions_enabled(False)

        self._crawl = CrawlSession(
            self.root,
            job_factory=lambda: run_all(self.repository),
            on_finished=self._on_crawl_finished,
            theme=CrawlProgressTheme(
                white=self.WHITE,
                border=self.BORDER,
                primary=self.PRIMARY,
                text_primary=self.TEXT_PRIMARY,
                text_secondary=self.TEXT_SECONDARY,
                text_muted=self.TEXT_MUTED,
                cancel=self.CANCEL_COLOR,
            ),
        )
        self._crawl.start()

    def _set_actions_enabled(self, enabled):
        state = "normal" if enabled else "disabled"

        self.crawl_button.configure(
            state=state,
            text="Crawl" if enabled else "Crawling..."
        )

        self.backup_button.configure(state=state)

    # --- kết thúc crawl ----------------------------------------------

    def _on_crawl_finished(self, result: CrawlResult):
        self._crawl = None
        self._set_actions_enabled(True)

        if result.error:
            print(f"[X] Lỗi khi crawl: {result.error}")
            self._show_toast(
                f"[X] Crawl gặp lỗi: {result.error}",
                "error"
            )
        elif result.cancelled:
            self._show_toast(
                "[STOP] Đã dừng crawl theo yêu cầu "
                f"(đã lưu {result.saved} tin mới)",
                "warning"
            )
        elif result.stop:
            self._show_toast(f"[STOP] {result.stop}", "warning")
        else:
            self._show_toast(
                f"[OK] Đã cào xong {result.listed} tin tuyển dụng "
                f"({result.new} tin mới)",
                "success"
            )

        # Nạp lại bảng (kể cả khi lỗi/dừng: có thể đã lưu được một phần)
        self.load_jobs()

    # --- toast ----------------------------------------------------------

    def _show_toast(self, message, kind="success"):
        self._hide_toast()

        colors = {
            "success": "#166534",
            "warning": "#92400E",
            "error": "#991B1B",
        }

        toast = ctk.CTkFrame(
            self.root,
            fg_color=colors.get(kind, colors["success"]),
            corner_radius=10
        )

        label = ctk.CTkLabel(
            toast,
            text=message,
            text_color="#FFFFFF",
            font=("Segoe UI Semibold", 11),
            wraplength=420,
            justify="left"
        )

        label.pack(padx=16, pady=10)

        # Click vào toast để tắt ngay
        for widget in (toast, label):
            widget.bind("<Button-1>", lambda e: self._hide_toast())

        toast.place(relx=1.0, rely=1.0, x=-24, y=-24, anchor="se")
        toast.lift()

        self._toast = toast
        self._toast_after_id = self.root.after(
            8000 if kind == "error" else 5000,
            self._hide_toast
        )

    def _hide_toast(self):
        if self._toast_after_id is not None:
            self.root.after_cancel(self._toast_after_id)
            self._toast_after_id = None

        if self._toast is not None:
            self._toast.destroy()
            self._toast = None

    # --- backup ---------------------------------------------------------

    def on_backup(self):
        if self._backup_running or self._crawl is not None:
            return  # đang backup/crawl rồi, không cho chạy chồng

        try:
            from database.backup import backup_database
        except Exception as exc:
            self._show_toast(f"[X] Không nạp được module backup: {exc}", "error")
            return

        self.table.close_popups()

        self._backup_running = True
        self._set_backup_busy(True)

        # mongodump có thể chạy vài giây -> đưa sang thread riêng để UI không đơ
        def worker():
            path, error = None, None

            try:
                path = backup_database()
            except FileNotFoundError:
                error = (
                    "Không tìm thấy mongodump. "
                    "Hãy cài MongoDB Database Tools và thêm vào PATH."
                )
            except subprocess.CalledProcessError as exc:
                # Không dùng str(exc): nó chứa cả MONGODB_URI (có mật khẩu)
                error = (
                    f"mongodump thất bại (mã lỗi {exc.returncode}). "
                    "Kiểm tra lại kết nối / MONGODB_URI."
                )
            except Exception as exc:
                error = str(exc)

            self.root.after(0, lambda: self._on_backup_finished(path, error))

        threading.Thread(target=worker, daemon=True).start()

    def _set_backup_busy(self, busy):
        self.backup_button.configure(
            state="disabled" if busy else "normal",
            text="Backup..." if busy else "Backup"
        )

        # Backup xong mới cho crawl, tránh vừa ghi vừa sao lưu
        self.crawl_button.configure(
            state="disabled" if busy else "normal"
        )

    def _on_backup_finished(self, path, error):
        self._backup_running = False
        self._set_backup_busy(False)

        if error:
            print(f"[X] Backup thất bại: {error}")
            self._show_toast(f"[X] Backup thất bại: {error}", "error")
            return

        location = os.path.abspath(path) if path else "thư mục backups"

        print(f"[OK] Backup xong: {location}")
        self._show_toast(f"[OK] Đã backup xong:\n{location}", "success")