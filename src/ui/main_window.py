import math
import os
import subprocess
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import font as tkfont
from tkinter import ttk

import customtkinter as ctk

from ui.components.crawl_progress_dialog import (
    CrawlProgressTheme,
    CrawlResult,
    CrawlSession,
)
from ui.components.filters import (
    FilterManager,
    FilterTheme,
    measure_header_height,
)
from ui.components.pagination import PaginationBar, PaginationTheme
from ui.components.sort import SortManager, SortTheme
from ui.views.job_detail_view import JobDetailTheme, JobDetailView


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

    # Word wrap cho các cột trong bảng
    WRAP_COLUMNS = ("title", "company", "salary", "location")
    CELL_PADDING = 16
    MIN_ROW_HEIGHT = 40

    # Header filter (Location / Source)
    FILTER_COLUMNS = (
        "title", "company", "location", "source", "posted_at", "expire_date"
    )
    CHECKLIST_COLUMNS = ("location", "source")  # ít giá trị -> popup checklist
    TEXT_COLUMNS = ("title", "company")         # nhiều giá trị -> gõ từ khóa

    # cột ngày -> khoá ngày gốc (datetime) trong view model; lọc theo khoảng
    DATE_COLUMNS = {
        "posted_at": "posted_at_raw",
        "expire_date": "expired_at_raw",
    }
    # Sort theo header: click lần 1 tăng dần, lần 2 giảm dần, lần 3 về mặc định
    SORT_COLUMNS = ("title", "company", "salary", "posted_at", "expire_date")
    SORT_DEFAULT = ("posted_at", "desc")   # mới đăng nhất lên đầu

    SEARCH_BORDER = "#D1D5DB"   # viền ô search lúc bình thường
    FILTER_ACTIVE = "#1D4ED8"   # xanh dương đậm khi cột đang bị lọc
    HOVER_BG = "#F3F4F6"
    ICON_WIDTH = 20
    DEFAULT_HEADER_HEIGHT = 26

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
        self.root.title("Job Crawler")

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
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # --------------------------------------------------------
        # Treeview
        # --------------------------------------------------------

        style.configure(
            "Jobs.Treeview",
            background=self.WHITE,
            foreground=self.TEXT_PRIMARY,
            fieldbackground=self.WHITE,
            borderwidth=0,
            relief="flat",
            rowheight=40,
            font=("Segoe UI", 10)
        )

        style.configure(
            "Jobs.Treeview.Heading",
            background=self.WHITE,
            foreground=self.TEXT_SECONDARY,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI Semibold", 9)
        )

        style.map(
            "Jobs.Treeview",
            background=[
                ("selected", self.SELECTED)
            ],
            foreground=[
                ("selected", self.TEXT_PRIMARY)
            ]
        )

        # --------------------------------------------------------
        # Scrollbar
        # --------------------------------------------------------

        style.configure(
            "Vertical.TScrollbar",
            background="#D1D5DB",
            troughcolor="#F9FAFB",
            borderwidth=0,
            arrowsize=12
        )

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
        self.table_container = ctk.CTkFrame(
            self.table_card,
            fg_color=self.WHITE,
            corner_radius=0
        )

        self.table_container.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=7,
            pady=(7, 0)
        )

        self.table_container.grid_rowconfigure(
            0,
            weight=1
        )

        self.table_container.grid_columnconfigure(
            0,
            weight=1
        )

        columns = (
            "title",
            "company",
            "salary",
            "location",
            "source",
            "posted_at",
            "expire_date"
        )

        self.tree = ttk.Treeview(
            self.table_container,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Jobs.Treeview"
        )

        self.tree.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        # --------------------------------------------------------
        # Scrollbar
        # --------------------------------------------------------

        self.table_scrollbar = ttk.Scrollbar(
            self.table_container,
            orient="vertical",
            command=self.tree.yview,
            style="Vertical.TScrollbar"
        )

        self.table_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
            padx=(3, 0)
        )

        self.tree.configure(
            yscrollcommand=self._on_tree_yscroll
        )

        # --------------------------------------------------------
        # Headings
        # --------------------------------------------------------

        headings = {
            "title": "Job Title",
            "company": "Company",
            "salary": "Salary",
            "location": "Location",
            "source": "Source",
            "posted_at": "Posted At",
            "expire_date": "Expire Date"
        }

        for key, text in headings.items():
            self.tree.heading(key, text=text, anchor="w")

        # --------------------------------------------------------
        # Columns
        # --------------------------------------------------------

        self.tree.column(
            "title",
            width=300,
            minwidth=170,
            stretch=True,
            anchor="w"
        )

        self.tree.column(
            "company",
            width=200,
            minwidth=100,
            stretch=True,
            anchor="w"
        )

        self.tree.column(
            "salary",
            width=110,
            minwidth=80,
            stretch=True,
            anchor="w"
        )

        self.tree.column(
            "location",
            width=120,
            minwidth=90,
            stretch=True,
            anchor="w"
        )

        self.tree.column(
            "source",
            width=95,
            minwidth=80,
            stretch=False,
            anchor="w"
        )

        self.tree.column(
            "posted_at",
            width=110,
            minwidth=105,
            stretch=False,
            anchor="w"
        )

        self.tree.column(
            "expire_date",
            width=120,
            minwidth=115,
            stretch=False,
            anchor="w"
        )

        # --------------------------------------------------------
        # Word wrap state
        # --------------------------------------------------------

        self._row_font = tkfont.Font(family="Segoe UI", size=10)
        self._row_height = self.MIN_ROW_HEIGHT
        self._wrap_after_id = None
        self.page_jobs = []

        # Re-wrap khi kéo cột hoặc resize cửa sổ
        self.tree.bind("<Configure>", self._schedule_rewrap, add="+")
        self.tree.bind("<ButtonRelease-1>", self._schedule_rewrap, add="+")

        self._build_filter_header()

        # --------------------------------------------------------
        # Events
        # --------------------------------------------------------

        self.tree.bind(
            "<<TreeviewSelect>>",
            self.on_job_selected
        )

        # Chuột phải vào dòng -> context menu (mở link gốc / sao chép link)
        self._build_row_menu()

        self._build_state_overlay()

    def _on_tree_yscroll(self, first, last):
        """Cập nhật thanh cuộn và ẩn hẳn khi không có gì để cuộn
        (danh sách rỗng hoặc toàn bộ dòng đã vừa khung nhìn)."""
        self.table_scrollbar.set(first, last)

        needs_scroll = float(first) > 0.0 or float(last) < 1.0
        is_shown = bool(self.table_scrollbar.winfo_manager())

        if needs_scroll and not is_shown:
            self.table_scrollbar.grid()
        elif not needs_scroll and is_shown:
            self.table_scrollbar.grid_remove()

    # ============================================================
    # Table state overlay (loading / empty / error)
    # ============================================================

    def _build_state_overlay(self):
        self.state_overlay = ctk.CTkFrame(
            self.table_container,
            fg_color=self.WHITE,
            corner_radius=0
        )

        inner = ctk.CTkFrame(
            self.state_overlay,
            fg_color=self.WHITE,
            corner_radius=0
        )

        inner.place(
            relx=0.5,
            rely=0.45,
            anchor="center"
        )

        self.state_label = ctk.CTkLabel(
            inner,
            text="",
            text_color=self.TEXT_SECONDARY,
            font=("Segoe UI", 11),
            justify="center",
            wraplength=420
        )

        self.state_label.pack()

        self.state_progress = ctk.CTkProgressBar(
            inner,
            mode="indeterminate",
            width=220,
            height=6,
            fg_color=self.BORDER,
            progress_color=self.PRIMARY
        )

        # CTA ở empty state "không có kết quả": xóa tìm kiếm + mọi bộ lọc
        self.state_action_button = ctk.CTkButton(
            inner,
            text="Xóa tìm kiếm & bộ lọc",
            width=170,
            height=32,
            corner_radius=7,
            fg_color=self.HOVER_BG,
            hover_color=self.BORDER,
            text_color="#374151",
            font=("Segoe UI", 10),
            command=self.clear_search_and_filters
        )

    def _show_state(self, message, loading=False, keep_header=False,
                    show_clear=False):
        self.state_label.configure(text=message)

        if loading:
            self.state_progress.pack(pady=(12, 0))
            self.state_progress.start()
        else:
            self.state_progress.stop()
            self.state_progress.pack_forget()

        if show_clear:
            self.state_action_button.pack(pady=(14, 0))
        else:
            self.state_action_button.pack_forget()

        if keep_header:
            # Chỉ phủ phần body: chừa lại hàng tiêu đề (cùng icon lọc)
            # để người dùng còn bỏ lọc từng cột được.
            header_h = self._measure_header_height()

            y, height = header_h, -header_h
        else:
            y, height = 0, 0

        # CTkFrame.place() cấm truyền height -> gọi place gốc của tkinter
        # (relheight=1 + height âm = cao bằng khung trừ phần header).
        tk.Place.place_configure(
            self.state_overlay,
            x=0,
            y=y,
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
            height=height
        )

    def _hide_state(self):
        self.state_progress.stop()
        self.state_overlay.place_forget()

    def _update_state_overlay(self):
        if self.is_loading:
            self._show_state(
                "Đang tải dữ liệu...",
                loading=True
            )
        elif self.load_error and not self.jobs:
            self._show_state(
                f"Không tải được dữ liệu.\n{self.load_error}"
            )
        elif not self.jobs:
            self._show_state(
                "Chưa có dữ liệu.\nBấm Crawl để thu thập việc làm."
            )
        elif not self.filtered_jobs:
            self._show_state(
                "Không tìm thấy kết quả phù hợp.",
                keep_header=True,
                show_clear=True
            )
        else:
            self._hide_state()

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

        self.filters.prune()
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

    # ============================================================
    # Word wrap (Treeview không hỗ trợ sẵn -> tự ngắt dòng bằng \n)
    # ============================================================

    def _wrap_text(self, text, width):
        """Ngắt text thành nhiều dòng vừa `width` pixel. Trả về (text, số dòng)."""
        text = (text or "").replace("\n", " ").strip()
        font = self._row_font

        if width <= 0 or font.measure(text) <= width:
            return text, 1

        lines, current = [], ""

        for word in text.split():
            candidate = f"{current} {word}".strip()

            if font.measure(candidate) <= width:
                current = candidate
                continue

            if current:
                lines.append(current)

            # Từ đơn quá dài so với cột -> cắt theo ký tự
            while len(word) > 1 and font.measure(word) > width:
                cut = len(word)
                while cut > 1 and font.measure(word[:cut]) > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]

            current = word

        if current:
            lines.append(current)

        return "\n".join(lines), len(lines)

    def _row_values(self, job):
        wrapped, max_lines = {}, 1

        for key in self.WRAP_COLUMNS:
            width = int(self.tree.column(key, "width")) - self.CELL_PADDING
            text = job[key] or ("—" if key == "salary" else "")
            wrapped[key], lines = self._wrap_text(text, width)
            max_lines = max(max_lines, lines)

        values = (
            wrapped["title"],
            wrapped["company"],
            wrapped["salary"],
            wrapped["location"],
            job["source"],
            job["posted_at"],
            job["expire_date"],
        )

        return values, max_lines

    def _set_row_height(self, max_lines):
        line_h = self._row_font.metrics("linespace")
        height = max(self.MIN_ROW_HEIGHT, line_h * max_lines + 12)

        if height != self._row_height:
            self._row_height = height
            ttk.Style().configure("Jobs.Treeview", rowheight=height)

    def _apply_wrap(self):
        self._wrap_after_id = None
        max_lines = 1

        for job in self.page_jobs:
            if not self.tree.exists(job["id"]):
                continue

            values, lines = self._row_values(job)
            self.tree.item(job["id"], values=values)
            max_lines = max(max_lines, lines)

        self._set_row_height(max_lines)

    def _schedule_rewrap(self, event=None):
        # Debounce để không wrap liên tục khi đang kéo
        if self._wrap_after_id:
            self.root.after_cancel(self._wrap_after_id)

        self._wrap_after_id = self.root.after(80, self._apply_wrap)

    def refresh_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.page_jobs = self.pagination.paginate(self.filtered_jobs)

        for job in self.page_jobs:
            self.tree.insert(
                "",
                "end",
                iid=job["id"],
                values=(
                    job["title"],
                    job["company"],
                    job["salary"] or "—",
                    job["location"],
                    job["source"],
                    job["posted_at"],
                    job["expire_date"]
                )
            )

        self._apply_wrap()

        # Select first item automatically.
        rows = self.tree.get_children()

        if rows:
            first_id = rows[0]

            self.tree.selection_set(first_id)
            self.tree.focus(first_id)

            self.show_job_details(first_id)
        else:
            self._clear_details()

        self._update_state_overlay()

    # ============================================================
    # Job Selection
    # ============================================================

    def on_job_selected(self, event=None):
        selection = self.tree.selection()

        if not selection:
            return

        self.show_job_details(
            selection[0]
        )

    def show_job_details(self, job_id):
        job = self._find_job(job_id)

        if job:
            self.detail_view.show_job(job)


    # ============================================================
    # Context menu (chuột phải vào dòng)
    # ============================================================

    def _build_row_menu(self):
        self._row_menu = None

        right_buttons = ["<Button-3>"]

        # macOS: chuột phải là Button-2 (hoặc Ctrl + click)
        if self.root.tk.call("tk", "windowingsystem") == "aqua":
            right_buttons += ["<Button-2>", "<Control-Button-1>"]

        for sequence in right_buttons:
            self.tree.bind(sequence, self._on_row_right_click)

        # Cuộn chuột -> đóng menu (click ra ngoài đã xử lý ở _on_root_click)
        self.root.bind("<MouseWheel>", self._close_row_menu, add="+")
        self.root.bind("<Button-4>", self._close_row_menu, add="+")
        self.root.bind("<Button-5>", self._close_row_menu, add="+")

    def _find_job(self, job_id):
        return next(
            (item for item in self.jobs if item["id"] == str(job_id)),
            None
        )

    def _on_row_right_click(self, event):
        self._close_row_menu()

        item_id = self.tree.identify_row(event.y)

        if not item_id:
            return "break"

        # Tự chọn dòng được click chuột phải
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)

        job = self._find_job(item_id)
        url = ((job or {}).get("url") or "").strip()
        state = "normal" if url else "disabled"

        menu = tk.Menu(
            self.root,
            tearoff=0,
            font=("Segoe UI", 10),
            bg=self.WHITE,
            fg=self.TEXT_PRIMARY,
            activebackground=self.SELECTED,
            activeforeground=self.TEXT_PRIMARY,
            bd=1,
            relief="solid"
        )

        menu.add_command(
            label="Mở link gốc",
            state=state,
            command=lambda: webbrowser.open_new_tab(url)
        )
        menu.add_command(
            label="Sao chép đường dẫn",
            state=state,
            command=lambda: self._copy_to_clipboard(url)
        )

        self._row_menu = menu

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

        return "break"

    def _close_row_menu(self, event=None):
        menu = getattr(self, "_row_menu", None)

        if menu is None:
            return

        self._row_menu = None

        try:
            menu.unpost()
            menu.destroy()
        except tk.TclError:
            pass

    def _copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()

    def _clear_details(self):
        self.detail_view.clear()


    # ============================================================
    # Search
    # ============================================================

    # ------------------------------------------------------------
    # Header filter (popup checklist kiểu Excel cho Location / Source)
    # ------------------------------------------------------------

    def _build_filter_header(self):
        # Toàn bộ logic lọc (icon, popup Text/Date/Checklist, trạng thái,
        # kiểm tra khớp) nằm ở ui/components/filters.py
        self.filters = FilterManager(
            self.root,
            self.tree,
            columns=self.FILTER_COLUMNS,
            text_columns=self.TEXT_COLUMNS,
            checklist_columns=self.CHECKLIST_COLUMNS,
            date_columns=self.DATE_COLUMNS,
            sort_columns=self.SORT_COLUMNS,
            get_jobs=lambda: self.jobs,
            on_change=self.on_search,
            theme=FilterTheme(
                white=self.WHITE,
                border=self.BORDER,
                text_primary=self.TEXT_PRIMARY,
                text_secondary=self.TEXT_SECONDARY,
                text_muted=self.TEXT_MUTED,
                hover_bg=self.HOVER_BG,
                active=self.FILTER_ACTIVE,
            ),
            icon_width=self.ICON_WIDTH,
            default_header_height=self.DEFAULT_HEADER_HEIGHT,
        )

        self._fit_after_id = None

        # Click heading: cột sort -> đổi sort; cột còn lại -> mở popup lọc
        for key in dict.fromkeys(self.FILTER_COLUMNS + self.SORT_COLUMNS):
            self.tree.heading(
                key,
                anchor="w",
                command=lambda k=key: self._on_heading_click(k)
            )

        # Toàn bộ logic sort (icon, trạng thái, parse lương, sắp xếp)
        # nằm ở ui/components/sort.py
        self.sort = SortManager(
            self.tree,
            columns=self.SORT_COLUMNS,
            default=self.SORT_DEFAULT,
            date_columns=self.DATE_COLUMNS,
            on_change=self.on_search,
            theme=SortTheme(
                white=self.WHITE,
                text_muted=self.TEXT_MUTED,
                hover_bg=self.HOVER_BG,
                active=self.FILTER_ACTIVE,
            ),
            icon_width=self.ICON_WIDTH,
            default_header_height=self.DEFAULT_HEADER_HEIGHT,
            before_change=self.filters.close_popup,
            # Icon sort nằm bên trái icon lọc (cột không có lọc thì sát mép phải)
            slots_for=lambda key: 1 if self.filters.has_icon(key) else 0,
        )

        # Icon luôn bám theo mép phải của cột khi kéo cột / resize
        for sequence in ("<Configure>", "<B1-Motion>", "<ButtonRelease-1>"):
            self.tree.bind(sequence, self._position_header_icons, add="+")

        # Cửa sổ hẹp: thu các cột stretch để cột Posted At / Expire Date
        # (và icon lọc của chúng) không bị cắt khỏi khung nhìn
        self.tree.bind("<Configure>", self._schedule_fit_columns, add="+")

        # Click ra ngoài / di chuyển cửa sổ -> đóng popup
        self.root.bind("<Button-1>", self._on_root_click, add="+")
        self.root.bind("<Configure>", self.filters.on_root_configure, add="+")

        self._position_header_icons()

    def _measure_header_height(self):
        """Chiều cao hàng tiêu đề (dùng cho overlay + icon)."""
        return measure_header_height(self.tree, self.DEFAULT_HEADER_HEIGHT)

    def _schedule_fit_columns(self, event=None):
        if self._fit_after_id:
            self.root.after_cancel(self._fit_after_id)

        self._fit_after_id = self.root.after(100, self._fit_columns)

    def _fit_columns(self):
        """Treeview không tự thu nhỏ cột khi khung hẹp lại -> thu các cột
        stretch (không thấp hơn minwidth) cho vừa khung."""
        self._fit_after_id = None

        available = self.tree.winfo_width()

        if available <= 1:
            return

        names = self.tree["columns"]
        widths = {n: int(self.tree.column(n, "width")) for n in names}
        excess = sum(widths.values()) - available

        room = {
            n: widths[n] - int(self.tree.column(n, "minwidth"))
            for n in names
            if str(self.tree.column(n, "stretch")).lower() in ("1", "true")
        }

        room = {n: r for n, r in room.items() if r > 0}
        capacity = sum(room.values())

        if excess <= 0 or capacity <= 0:
            return

        cut = min(excess, capacity)

        for name, available_room in room.items():
            share = math.ceil(cut * available_room / capacity)
            self.tree.column(name, width=widths[name] - min(share, available_room))

        self._position_header_icons()
        self._schedule_rewrap()

    def _position_header_icons(self, event=None):
        self.filters.position_icons()
        self.sort.position_icons()

    # --- Click heading ---------------------------------------------

    def _on_heading_click(self, key):
        if key in self.sort.columns:
            self.sort.toggle(key)
        else:
            self.filters.toggle_popup(key)

    def _on_root_click(self, event):
        self._close_row_menu()
        self.filters.on_root_click(event)

    def _matches_filters(self, job, keyword):
        if not self.filters.matches(job):
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
        self.filters.clear()

        self.on_search()

    def on_search(self, event=None):
        keyword = (
            self.search_entry
            .get()
            .strip()
            .lower()
        )

        self.filtered_jobs = self.sort.sort([
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

        self.filters.close_popup()

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

        self.filters.close_popup()

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