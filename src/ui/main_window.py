import calendar
import math
import os
import re
import subprocess
import threading
import tkinter as tk
import unicodedata
import webbrowser
from collections import Counter
from datetime import date, datetime, timedelta
from html import escape
from html.parser import HTMLParser
from tkinter import font as tkfont
from tkinter import ttk

import customtkinter as ctk

from ui.components.crawl_progress_dialog import (
    CrawlProgressTheme,
    CrawlResult,
    CrawlSession,
)


class HtmlTextRenderer(HTMLParser):
    """Đổ HTML đơn giản vào tk.Text (không cần thư viện ngoài).

    Hỗ trợ: p, div, br, b/strong, i/em, u, h1-h6, ul/ol/li.
    HTML từ các trang tuyển dụng chủ yếu chỉ dùng vài thẻ cơ bản này.
    """

    BLOCK_TAGS = {
        "p", "div", "section", "article", "blockquote",
        "table", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    }

    STYLE_TAGS = {
        "b": "bold",
        "strong": "bold",
        "i": "italic",
        "em": "italic",
        "u": "underline",
        "h1": "heading",
        "h2": "heading",
        "h3": "heading",
        "h4": "heading",
        "h5": "heading",
        "h6": "heading",
    }

    SKIP_TAGS = {"script", "style"}

    def __init__(self, text_widget):
        super().__init__(convert_charrefs=True)

        self.text = text_widget
        self.styles = []
        self.lists = []
        self.indent_tag = None
        self.at_line_start = True
        self.skip_depth = 0

    # --------------------------------------------------------
    # Public
    # --------------------------------------------------------

    @classmethod
    def render(cls, text_widget, html):
        text_widget.configure(state="normal")
        text_widget.delete("1.0", "end")

        parser = cls(text_widget)
        parser.feed(html)
        parser.close()
        parser.strip_trailing_newline()

        text_widget.configure(state="disabled")
        text_widget.yview_moveto(0)

    def strip_trailing_newline(self):
        if self.text.get("end-2c", "end-1c") == "\n":
            self.text.delete("end-2c", "end-1c")

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------

    def _insert(self, content):
        tags = list(self.styles)

        if self.indent_tag:
            tags.append(self.indent_tag)

        self.text.insert("end", content, tuple(tags))
        self.at_line_start = content.endswith("\n")

    def _break(self):
        """Xuống dòng, nhưng không tạo dòng trống thừa."""
        if not self.at_line_start:
            self._insert("\n")

    def _remove_style(self, style):
        for index in range(len(self.styles) - 1, -1, -1):
            if self.styles[index] == style:
                del self.styles[index]
                return

    # --------------------------------------------------------
    # HTMLParser callbacks
    # --------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if tag == "br":
            self._break()
            return

        if tag in ("ul", "ol"):
            self._break()
            self.lists.append([tag, 0])

        elif tag == "li":
            self._break()

            if not self.lists:
                self.lists.append(["ul", 0])

            current = self.lists[-1]
            current[1] += 1

            marker = (
                f"{current[1]}. "
                if current[0] == "ol"
                else "• "
            )

            self.indent_tag = f"indent{min(len(self.lists), 3)}"
            self._insert(marker)

        elif tag in self.BLOCK_TAGS:
            self._break()

        style = self.STYLE_TAGS.get(tag)

        if style:
            self.styles.append(style)

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return

        style = self.STYLE_TAGS.get(tag)

        if style:
            self._remove_style(style)

        if tag == "li":
            self._break()
            self.indent_tag = None

        elif tag in ("ul", "ol"):
            self._break()

            if self.lists:
                self.lists.pop()

        elif tag in self.BLOCK_TAGS:
            self._break()

    def handle_data(self, data):
        if self.skip_depth:
            return

        data = re.sub(r"\s+", " ", data)

        if self.at_line_start:
            data = data.lstrip()

        if data:
            self._insert(data)


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
    TEXT_CONDITIONS = {
        "contains": "Chứa",
        "startswith": "Bắt đầu bằng",
        "endswith": "Kết thúc bằng",
    }
    # Sort theo header: click lần 1 tăng dần, lần 2 giảm dần, lần 3 về mặc định
    SORT_COLUMNS = ("title", "company", "salary", "posted_at", "expire_date")
    SORT_DEFAULT = ("posted_at", "desc")   # mới đăng nhất lên đầu
    SORT_IDLE = "⇅"
    SORT_ASC = "▲"
    SORT_DESC = "▼"
    USD_TO_VND = 25000                      # chỉ để so sánh lương USD / VND
    SALARY_UNITS = {
        "trieu": 1e6, "tr": 1e6, "m": 1e6,
        "nghin": 1e3, "ngan": 1e3, "k": 1e3,
        "ty": 1e9, "ti": 1e9, "b": 1e9,
    }

    SEARCH_BORDER = "#D1D5DB"   # viền ô search lúc bình thường
    FILTER_ACTIVE = "#1D4ED8"   # xanh dương đậm khi cột đang bị lọc
    HOVER_BG = "#F3F4F6"
    ICON_IDLE = "▾"
    ICON_ACTIVE = "●"   # lọc đang bật (khác ▲▼ của sort)
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

    # ============================================================
    # Detail panel
    # ============================================================

    DETAIL_PAD_X = 18

    # Cỡ chữ nội dung: mặc định (Quyền lợi / Liên hệ) và lớn hơn một chút
    # (Mô tả / Yêu cầu / Thông số).
    HTML_FONT_SIZE = 10
    HTML_FONT_SIZE_LARGE = 14

    # Khoảng cách (trên, dưới) mỗi dòng của "Thông số": thoáng hơn để
    # danh sách dài không bị dính / nhầm dòng.
    SPEC_LINE_GAP = (6, 8)

    META_ICONS = {
        "company": "🏢",
        "location": "📍",
        "address": "🏠",
        "dates": "📅",
    }

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

        self.current_page = 1
        self.selected_job = None

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
    # Pagination
    # ============================================================

    def _build_pagination(self):
        self.pagination = ctk.CTkFrame(
            self.table_card,
            fg_color=self.WHITE,
            corner_radius=0,
            height=50
        )

        self.pagination.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=7,
            pady=(5, 7)
        )

        self.pagination.grid_columnconfigure(
            0,
            weight=1
        )

        self.pagination.grid_columnconfigure(
            1,
            weight=0
        )

        self.pagination.grid_columnconfigure(
            2,
            weight=0
        )

        self.pagination.grid_columnconfigure(
            3,
            weight=0
        )

        self.pagination.grid_columnconfigure(
            4,
            weight=1
        )

        # --------------------------------------------------------
        # Previous
        # --------------------------------------------------------

        self.previous_button = ctk.CTkButton(
            self.pagination,
            text="‹",
            width=34,
            height=30,
            corner_radius=6,
            fg_color=self.WHITE,
            hover_color="#F3F4F6",
            text_color=self.TEXT_PRIMARY,
            border_width=1,
            border_color=self.BORDER,
            font=("Segoe UI", 15),
            command=self.previous_page
        )

        self.previous_button.grid(
            row=0,
            column=0,
            sticky="e",
            padx=(0, 4),
            pady=6
        )

        # --------------------------------------------------------
        # Page
        # --------------------------------------------------------

        self.page_text = ctk.CTkLabel(
            self.pagination,
            text="Page",
            text_color=self.TEXT_SECONDARY,
            font=("Segoe UI", 9)
        )

        self.page_text.grid(
            row=0,
            column=1,
            padx=(8, 4),
            pady=6
        )

        self.page_entry = ctk.CTkEntry(
            self.pagination,
            width=50,
            height=30,
            corner_radius=6,
            border_width=1,
            border_color=self.BORDER,
            fg_color=self.WHITE,
            text_color=self.TEXT_PRIMARY,
            justify="center",
            font=("Segoe UI", 9)
        )

        self.page_entry.grid(
            row=0,
            column=2,
            padx=4,
            pady=6
        )

        self.page_of_label = ctk.CTkLabel(
            self.pagination,
            text="of 1",
            text_color=self.TEXT_SECONDARY,
            font=("Segoe UI", 9)
        )

        self.page_of_label.grid(
            row=0,
            column=3,
            padx=(4, 8),
            pady=6
        )

        self.page_entry.bind(
            "<Return>",
            self.go_to_page
        )

        self.page_entry.bind(
            "<FocusOut>",
            self.go_to_page
        )

        # --------------------------------------------------------
        # Next
        # --------------------------------------------------------

        self.next_button = ctk.CTkButton(
            self.pagination,
            text="›",
            width=34,
            height=30,
            corner_radius=6,
            fg_color=self.WHITE,
            hover_color="#F3F4F6",
            text_color=self.TEXT_PRIMARY,
            border_width=1,
            border_color=self.BORDER,
            font=("Segoe UI", 15),
            command=self.next_page
        )

        self.next_button.grid(
            row=0,
            column=4,
            sticky="w",
            padx=(4, 0),
            pady=6
        )

    # ============================================================
    # Right Panel (~40%)
    #
    # Runs the full height of the window. Pure JD viewer only —
    # no search box, no buttons, no toolbar of any kind here.
    # ============================================================

    def _build_right_panel(self):
        self.right_panel = ctk.CTkFrame(
            self.content,
            fg_color=self.WHITE,
            corner_radius=10,
            border_width=1,
            border_color=self.BORDER
        )

        self.right_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(5, 0)
        )

        self.right_panel.grid_rowconfigure(
            0,
            weight=1
        )

        self.right_panel.grid_columnconfigure(
            0,
            weight=1
        )

        # --------------------------------------------------------
        # Một thanh cuộn duy nhất cho toàn bộ cột chi tiết.
        # Bên trong xếp dọc: Header -> 5 khối nội dung.
        #
        # row 0     = header
        # row 2-3   = Mô tả       row 4-5  = Yêu cầu
        # row 6-7   = Thông số (bullet list)
        # row 8-9   = Quyền lợi   row 10-11 = Liên hệ
        # --------------------------------------------------------

        self.detail_scroll = ctk.CTkScrollableFrame(
            self.right_panel,
            fg_color=self.WHITE,
            corner_radius=0
        )

        self.detail_scroll.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=2,
            pady=6
        )

        self.detail_scroll.grid_columnconfigure(
            0,
            weight=1
        )

        self._wrap_width = 300

        self._build_html_fonts()
        self._build_detail_header()

        self.desc_section = self._build_html_section(
            row=2,
            title="Mô tả công việc",
            font_size=self.HTML_FONT_SIZE_LARGE
        )

        self.req_section = self._build_html_section(
            row=4,
            title="Yêu cầu ứng viên",
            font_size=self.HTML_FONT_SIZE_LARGE
        )

        self.benefits_section = self._build_html_section(
            row=6,
            title="Quyền lợi",
            font_size=self.HTML_FONT_SIZE_LARGE
        )

        self.spec_section = self._build_html_section(
            row=8,
            title="Thông tin khác",
            card=False,
            font_size=self.HTML_FONT_SIZE_LARGE,
            line_gap=self.SPEC_LINE_GAP
        )

        self._build_detail_placeholder()

    # ------------------------------------------------------------
    # Placeholder khi chưa chọn tin nào (căn giữa khung chi tiết)
    # ------------------------------------------------------------

    def _build_detail_placeholder(self):
        self.detail_placeholder = ctk.CTkFrame(
            self.right_panel,
            fg_color=self.WHITE,
            corner_radius=0
        )

        ctk.CTkLabel(
            self.detail_placeholder,
            text="Chọn một tin tuyển dụng bên trái để xem chi tiết",
            text_color=self.TEXT_MUTED,
            font=("Segoe UI", 12),
            justify="center",
            wraplength=280
        ).place(relx=0.5, rely=0.5, anchor="center")

        self._show_detail_placeholder(True)

    def _show_detail_placeholder(self, visible):
        if visible:
            # Chừa 4px quanh viền để không đè lên góc bo của khung.
            # CTkFrame.place() cấm width/height -> dùng place gốc của tk.
            tk.Place.place_configure(
                self.detail_placeholder,
                x=4,
                y=4,
                relx=0,
                rely=0,
                relwidth=1,
                relheight=1,
                width=-8,
                height=-8
            )
            self.detail_placeholder.lift()
        else:
            self.detail_placeholder.place_forget()

    # ============================================================
    # A. Header (title / salary / meta / source + link)
    # ============================================================

    def _build_detail_header(self):
        header = ctk.CTkFrame(
            self.detail_scroll,
            fg_color=self.WHITE,
            corner_radius=0
        )

        header.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=self.DETAIL_PAD_X,
            pady=(10, 0)
        )

        header.grid_columnconfigure(
            0,
            weight=1
        )

        # Dùng tk.Label thay vì CTkLabel: CTkLabel + wraplength cố định
        # hay bị canvas bên trong cắt mất chữ cuối dòng. tk.Label tự
        # wrap theo đúng độ rộng thực tế của nó nên không bị cắt.
        self.jd_title = tk.Label(
            header,
            text="",
            bg=self.WHITE,
            fg=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 22),
            anchor="w",
            justify="left",
            wraplength=self._wrap_width,
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0
        )

        self.jd_title.grid(
            row=0,
            column=0,
            sticky="ew"
        )

        self.jd_title.bind(
            "<Configure>",
            self._on_title_resize
        )

        self.jd_salary = ctk.CTkLabel(
            header,
            text="",
            text_color=self.SALARY_COLOR,
            font=("Segoe UI Semibold", 12),
            anchor="w"
        )

        self.jd_salary.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(6, 0)
        )

        # Mỗi dòng meta = icon + text (company / location / address / dates)
        # Dùng tk.Label (giống jd_title) thay vì CTkLabel: CTkLabel có
        # chiều cao cố định + canvas bên trong nên địa chỉ dài bị cắt mất
        # chữ cuối dòng / dòng cuối. tk.Label tự cao theo số dòng wrap.
        self.jd_meta_rows = {}

        for index, key in enumerate(self.META_ICONS, start=2):
            label = tk.Label(
                header,
                text="",
                bg=self.WHITE,
                fg=self.TEXT_SECONDARY,
                font=("Segoe UI", 12),
                anchor="w",
                justify="left",
                wraplength=self._wrap_width,
                borderwidth=0,
                highlightthickness=0,
                padx=0,
                pady=0
            )

            label.grid(
                row=index,
                column=0,
                sticky="ew",
                pady=(8, 0)
            )

            # Wrap đúng bằng độ rộng label đang có -> không tràn/cắt chữ
            label.bind(
                "<Configure>",
                self._on_meta_resize
            )

            self.jd_meta_rows[key] = label

        source_row = ctk.CTkFrame(
            header,
            fg_color=self.WHITE,
            corner_radius=0
        )

        source_row.grid(
            row=2 + len(self.META_ICONS),
            column=0,
            sticky="w",
            pady=(10, 0)
        )

        self.jd_source = ctk.CTkLabel(
            source_row,
            text="",
            fg_color=self.TAG_BG,
            text_color=self.TAG_TEXT,
            corner_radius=6,
            padx=9,
            pady=4,
            font=("Segoe UI Semibold", 12),
            anchor="w"
        )

        self.jd_source.grid(
            row=0,
            column=0
        )

        self.jd_open_button = ctk.CTkButton(
            source_row,
            text="Mở link gốc ↗",
            width=110,
            height=26,
            corner_radius=6,
            fg_color=self.PRIMARY,
            hover_color=self.PRIMARY_HOVER,
            font=("Segoe UI Semibold", 12),
            command=self.on_open_selected_url,
            state="disabled"
        )

        self.jd_open_button.grid(
            row=0,
            column=1,
            padx=(8, 0)
        )

        separator = ctk.CTkFrame(
            header,
            height=1,
            fg_color=self.BORDER
        )

        separator.grid(
            row=3 + len(self.META_ICONS),
            column=0,
            sticky="ew",
            pady=(14, 0)
        )

    # ============================================================
    # B. Specifications (bullet list, nằm sau Yêu cầu)
    # ============================================================

    def _render_specifications(self, specifications):
        items = []

        if isinstance(specifications, dict):
            items = [
                (str(key), " ".join(str(value).split()))
                for key, value in specifications.items()
                if value not in (None, "")
            ]

        if not items:
            self._set_html_section(self.spec_section, "")
            return

        html = "<ul>" + "".join(
            f"<li><b>{escape(key)}:</b> {escape(value)}</li>"
            for key, value in items
        ) + "</ul>"

        self._set_html_section(self.spec_section, html)

    # ============================================================
    # C/D. HTML sections (Mô tả / Yêu cầu / Quyền lợi / Liên hệ)
    # ============================================================

    def _build_html_fonts(self):
        """Tạo sẵn bộ font cho từng cỡ chữ (thường / đậm / nghiêng / tiêu đề)."""

        family = "Segoe UI"

        self._font_sets = {}

        for size in (self.HTML_FONT_SIZE, self.HTML_FONT_SIZE_LARGE):
            self._font_sets[size] = {
                "body": tkfont.Font(
                    family=family,
                    size=size
                ),
                "bold": tkfont.Font(
                    family=family,
                    size=size,
                    weight="bold"
                ),
                "italic": tkfont.Font(
                    family=family,
                    size=size,
                    slant="italic"
                ),
                "heading": tkfont.Font(
                    family=family,
                    size=size + 1,
                    weight="bold"
                ),
            }

    def _configure_html_tags(self, text, fonts):
        text.tag_configure("bold", font=fonts["bold"])
        text.tag_configure("italic", font=fonts["italic"])
        text.tag_configure("heading", font=fonts["heading"])
        text.tag_configure("underline", underline=True)

        for depth in (1, 2, 3):
            left = 6 + 16 * depth

            text.tag_configure(
                f"indent{depth}",
                lmargin1=left,
                lmargin2=left + 14
            )

    def _build_html_section(
        self,
        row,
        title,
        card=True,
        font_size=None,
        line_gap=None
    ):
        """Heading + tk.Text tự co giãn chiều cao (không có thanh cuộn riêng).

        card=True : nội dung nằm trong khung nền xám nhạt có viền.
        card=False: nội dung hiển thị thẳng trên nền trắng chung của trang.
        font_size : cỡ chữ nội dung (mặc định HTML_FONT_SIZE).
        line_gap  : (spacing1, spacing3) khoảng cách trên/dưới mỗi dòng
                    logic, nếu muốn khác mặc định.
        """

        body_bg = self.JD_BG if card else self.WHITE
        fonts = self._font_sets[font_size or self.HTML_FONT_SIZE]

        if line_gap is None:
            line_gap = (1, 6) if card else (3, 4)

        heading = ctk.CTkLabel(
            self.detail_scroll,
            text=title,
            text_color=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 18),     # chỉnh cỡ chữ của yêu cầu / mô tả công việc / thông tin khác
            anchor="w"
        )

        heading.grid(
            row=row,
            column=0,
            sticky="ew",
            padx=self.DETAIL_PAD_X,
            pady=(14, 6)
        )

        container = ctk.CTkFrame(
            self.detail_scroll,
            fg_color=body_bg,
            corner_radius=8 if card else 0,
            border_width=1 if card else 0,
            border_color=self.BORDER_LIGHT
        )

        container.grid(
            row=row + 1,
            column=0,
            sticky="ew",
            padx=self.DETAIL_PAD_X,
            pady=(0, 6)
        )

        container.grid_columnconfigure(
            0,
            weight=1
        )

        text = tk.Text(
            container,
            wrap="word",
            bg=body_bg,
            fg=self.TEXT_PRIMARY,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=fonts["body"],
            padx=14 if card else 0,
            pady=10 if card else 2,
            spacing1=line_gap[0],
            spacing2=2,
            spacing3=line_gap[1],
            height=1,
            cursor="arrow"
        )

        text.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=1 if card else 0,
            pady=1 if card else 0
        )

        self._configure_html_tags(text, fonts)
        self._bind_auto_height(text)

        text.configure(state="disabled")

        return {
            "heading": heading,
            "container": container,
            "text": text
        }

    def _bind_auto_height(self, text):
        """Đổi chiều rộng -> tính lại số dòng hiển thị -> chỉnh height."""

        last_width = {"value": 0}

        def on_configure(event):
            if event.width != last_width["value"]:
                last_width["value"] = event.width
                self._fit_text_height(text)

        text.bind("<Configure>", on_configure)

    def _fit_text_height(self, text):
        text.update_idletasks()

        # Đếm trực tiếp số dòng hiển thị thực tế (đã tính cả tự động xuống dòng / word wrap)
        result = text.count("1.0", "end-1c", "displaylines")
        lines = result[0] if result else 1

        # Gán số dòng chính xác cho ô Text
        text.configure(
            height=max(1, lines)
        )

    @staticmethod
    def _to_html(content):
        """Nội dung đã là HTML thì giữ nguyên; text thường thì escape + giữ xuống dòng."""

        content = (content or "").strip()

        if not content:
            return ""

        if re.search(r"<[a-zA-Z/][^>]*>", content):
            return content

        return escape(content).replace("\n", "<br>")

    def _set_html_section(self, section, content, placeholder=None):
        html = self._to_html(content) or self._to_html(placeholder)

        if not html:
            section["heading"].grid_remove()
            section["container"].grid_remove()
            return

        section["heading"].grid()
        section["container"].grid()

        HtmlTextRenderer.render(section["text"], html)

        self.root.after_idle(
            self._fit_text_height,
            section["text"]
        )

    # ============================================================
    # Resize (wraplength tự co theo độ rộng thực của widget)
    # ============================================================

    def _on_title_resize(self, event):
        # Wrap đúng bằng độ rộng label đang có -> không bao giờ tràn/cắt chữ.
        width = max(100, event.width)

        if int(self.jd_title.cget("wraplength")) != width:
            self.jd_title.configure(wraplength=width)

    def _on_meta_resize(self, event):
        # Wrap đúng bằng độ rộng thực của từng dòng meta (company, địa chỉ...)
        width = max(100, event.width)
        label = event.widget

        if int(label.cget("wraplength")) != width:
            label.configure(wraplength=width)

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
        self.current_page = 1

        self._prune_filters()
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

        total_pages = max(
            1,
            (
                len(self.filtered_jobs)
                + self.PAGE_SIZE
                - 1
            )
            // self.PAGE_SIZE
        )

        if self.current_page > total_pages:
            self.current_page = total_pages

        start = (
            self.current_page - 1
        ) * self.PAGE_SIZE

        end = start + self.PAGE_SIZE

        page_jobs = self.filtered_jobs[start:end]

        self.page_jobs = page_jobs

        for job in page_jobs:
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

        self.page_entry.delete(0, "end")
        self.page_entry.insert(0, str(self.current_page))

        self.page_of_label.configure(
            text=f"of {total_pages}"
        )

        self.previous_button.configure(
            state=(
                "normal"
                if self.current_page > 1
                else "disabled"
            )
        )

        self.next_button.configure(
            state=(
                "normal"
                if self.current_page < total_pages
                else "disabled"
            )
        )

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

    @staticmethod
    def _fmt_date_range(start, end):
        if not isinstance(start, datetime) and not isinstance(end, datetime):
            return ""

        return (
            f"{MainWindow._fmt_date(start)} - "
            f"{MainWindow._fmt_date(end)}"
        )

    def _set_optional_label(self, label, text):
        if text:
            label.configure(text=text)
            label.grid()
        else:
            label.grid_remove()

    def _set_meta_row(self, key, value):
        label = self.jd_meta_rows[key]

        if value:
            label.configure(
                text=f"{self.META_ICONS[key]}  {value}"
            )
            label.grid()
        else:
            label.grid_remove()

    def _render_header(self, job):
        self.jd_title.configure(
            text=job.get("title") or "(Không có tiêu đề)"
        )

        self._set_optional_label(
            self.jd_salary,
            job.get("salary")
        )

        self._set_meta_row("company", job.get("company"))
        self._set_meta_row("location", job.get("location"))
        self._set_meta_row("address", job.get("address"))
        self._set_meta_row(
            "dates",
            self._fmt_date_range(
                job.get("posted_at_raw"),
                job.get("expired_at_raw")
            )
        )

        self.jd_source.configure(
            text=job.get("source") or "unknown"
        )

        self.jd_open_button.configure(
            state="normal" if job.get("url") else "disabled"
        )

    def _render_sections(self, job):
        self._set_html_section(
            self.desc_section,
            job.get("description"),
            placeholder="(Không có mô tả công việc)"
        )

        self._set_html_section(
            self.req_section,
            job.get("requirements"),
            placeholder="(Không có yêu cầu)"
        )

        # Quyền lợi / Liên hệ: không có dữ liệu thì ẩn luôn cả khối.
        self._set_html_section(
            self.benefits_section,
            job.get("benefits")
        )

    def _scroll_details_to_top(self):
        canvas = getattr(self.detail_scroll, "_parent_canvas", None)

        if canvas is not None:
            canvas.yview_moveto(0)

    def show_job_details(self, job_id):
        job = next(
            (
                item
                for item in self.jobs
                if item["id"] == str(job_id)
            ),
            None
        )

        if not job:
            return

        self.selected_job = job

        self._show_detail_placeholder(False)

        self._render_header(job)
        self._render_specifications(job.get("specifications"))
        self._render_sections(job)
        self._scroll_details_to_top()

    def on_open_selected_url(self):
        url = (
            (self.selected_job or {}).get("url") or ""
        ).strip()

        if url:
            webbrowser.open_new_tab(url)

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
        self.selected_job = None

        self._show_detail_placeholder(True)

        self.jd_title.configure(text="")
        self.jd_source.configure(text="")

        self.jd_salary.grid_remove()

        for label in self.jd_meta_rows.values():
            label.grid_remove()

        self.jd_open_button.configure(state="disabled")

        self._render_specifications(None)

        for section in (
            self.desc_section,
            self.req_section,
            self.benefits_section
        ):
            self._set_html_section(section, "")

    # ============================================================
    # Search
    # ============================================================

    # ------------------------------------------------------------
    # Header filter (popup checklist kiểu Excel cho Location / Source)
    # ------------------------------------------------------------

    def _build_filter_header(self):
        # None = không lọc. Checklist: set các key chuẩn hóa được chọn.
        # Text: (điều kiện, text gõ, text chuẩn hóa)
        # Date: (từ ngày | None, đến ngày | None)
        self.column_filters = {key: None for key in self.FILTER_COLUMNS}
        self.filter_icons = {}
        self._fp = None  # state của popup đang mở
        self._fit_after_id = None

        for key in self.FILTER_COLUMNS:
            self.tree.heading(
                key,
                anchor="w",
                command=lambda k=key: self._on_heading_click(k)
            )

            icon = tk.Label(
                self.tree,
                text=self.ICON_IDLE,
                bg=self.WHITE,
                fg=self.TEXT_MUTED,
                font=("Segoe UI Symbol", 9),
                cursor="hand2"
            )

            icon.bind(
                "<Button-1>",
                lambda e, k=key: self._toggle_filter_popup(k)
            )
            icon.bind(
                "<Enter>",
                lambda e, w=icon: w.configure(bg=self.HOVER_BG)
            )
            icon.bind(
                "<Leave>",
                lambda e, w=icon: w.configure(bg=self.WHITE)
            )

            self.filter_icons[key] = icon

        # Sort: None = mặc định (SORT_DEFAULT); ngược lại (cột, "asc"|"desc")
        self.sort_state = None
        self.sort_icons = {}

        for key in self.SORT_COLUMNS:
            self.tree.heading(
                key,
                anchor="w",
                command=lambda k=key: self._on_heading_click(k)
            )

            icon = tk.Label(
                self.tree,
                text=self.SORT_IDLE,
                bg=self.WHITE,
                fg=self.TEXT_MUTED,
                font=("Segoe UI Symbol", 9),
                cursor="hand2"
            )

            icon.bind(
                "<Button-1>",
                lambda e, k=key: self._toggle_sort(k)
            )
            icon.bind(
                "<Enter>",
                lambda e, w=icon: w.configure(bg=self.HOVER_BG)
            )
            icon.bind(
                "<Leave>",
                lambda e, w=icon: w.configure(bg=self.WHITE)
            )

            self.sort_icons[key] = icon

        # Icon luôn bám theo mép phải của cột khi kéo cột / resize
        for sequence in ("<Configure>", "<B1-Motion>", "<ButtonRelease-1>"):
            self.tree.bind(sequence, self._position_filter_icons, add="+")

        # Cửa sổ hẹp: thu các cột stretch để cột Posted At / Expire Date
        # (và icon lọc của chúng) không bị cắt khỏi khung nhìn
        self.tree.bind("<Configure>", self._schedule_fit_columns, add="+")

        # Click ra ngoài / di chuyển cửa sổ -> đóng popup
        self.root.bind("<Button-1>", self._on_root_click, add="+")
        self.root.bind("<Configure>", self._on_root_configure, add="+")

        self._update_sort_icons()
        self._position_filter_icons()

    def _measure_header_height(self):
        """Chiều cao hàng tiêu đề: quét y đến khi hết vùng 'heading'."""
        for y in range(2, 80):
            if self.tree.identify_region(5, y) != "heading":
                return y if y >= 12 else self.DEFAULT_HEADER_HEIGHT

        return self.DEFAULT_HEADER_HEIGHT

    def _column_left(self, key):
        left = 0

        for name in self.tree["columns"]:
            if name == key:
                break
            left += int(self.tree.column(name, "width"))

        return left

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

        self._position_filter_icons()
        self._schedule_rewrap()

    def _position_filter_icons(self, event=None):
        header_h = self._measure_header_height()

        for key, icon in self.filter_icons.items():
            right = self._column_left(key) + int(
                self.tree.column(key, "width")
            )

            icon.place(
                x=right - self.ICON_WIDTH - 2,
                y=1,
                width=self.ICON_WIDTH,
                height=header_h - 2
            )

        # Icon sort nằm bên trái icon lọc (cột không có lọc thì sát mép phải)
        for key, icon in getattr(self, "sort_icons", {}).items():
            right = self._column_left(key) + int(
                self.tree.column(key, "width")
            )
            slots = 2 if key in self.filter_icons else 1

            icon.place(
                x=right - self.ICON_WIDTH * slots - 2,
                y=1,
                width=self.ICON_WIDTH,
                height=header_h - 2
            )

    # --- Sort theo header ----------------------------------------

    def _on_heading_click(self, key):
        if key in self.SORT_COLUMNS:
            self._toggle_sort(key)
        else:
            self._toggle_filter_popup(key)

    def _effective_sort(self):
        return self.sort_state or self.SORT_DEFAULT

    def _toggle_sort(self, key):
        """Tăng dần -> giảm dần -> mặc định."""
        self._close_filter_popup()

        state = self.sort_state

        if state is None or state[0] != key:
            self.sort_state = (key, "asc")
        elif state[1] == "asc":
            self.sort_state = (key, "desc")
        else:
            self.sort_state = None

        self._update_sort_icons()
        self.on_search()

    def _update_sort_icons(self):
        active_key, direction = self._effective_sort()

        for key, icon in self.sort_icons.items():
            if key != active_key:
                icon.configure(text=self.SORT_IDLE, fg=self.TEXT_MUTED)
            else:
                icon.configure(
                    text=(
                        self.SORT_ASC if direction == "asc"
                        else self.SORT_DESC
                    ),
                    fg=self.FILTER_ACTIVE
                )

    def _sort_value(self, job, key):
        """Giá trị so sánh của một dòng; None = thiếu dữ liệu (luôn xếp cuối)."""
        if key in self.DATE_COLUMNS:
            value = job.get(self.DATE_COLUMNS[key])

            try:
                return value.timestamp() if value else None
            except (AttributeError, OverflowError, OSError, ValueError):
                return None

        if key == "salary":
            return self._parse_salary(job.get("salary"))

        return self._normalize_text(job.get(key)) or None

    def _sort_jobs(self, jobs):
        key, direction = self._effective_sort()

        keyed, missing = [], []

        for job in jobs:
            value = self._sort_value(job, key)
            (missing if value is None else keyed).append((value, job))

        keyed.sort(key=lambda pair: pair[0], reverse=(direction == "desc"))

        # Dòng thiếu dữ liệu luôn nằm dưới cùng, dù tăng hay giảm
        return [job for _, job in keyed] + [job for _, job in missing]

    def _parse_salary(self, text):
        """'14 triệu - 18 triệu' -> (14e6, 18e6) VND; 'Thương lượng' -> None."""
        text = self._normalize_text(text)
        text = re.sub(r"\([^)]*\)", " ", text)         # bỏ phần trong ngoặc
        text = re.sub(r"\d+\s*thang", " ", text)       # '13 tháng lương'

        if not re.search(r"\d", text):
            return None

        is_usd = "usd" in text or "$" in text

        tokens = []

        for number, unit in re.findall(
            r"(\d[\d.,]*)\s*(trieu|tr|nghin|ngan|ty|ti|m|k|b)?(?![a-z])",
            text
        ):
            number = number.rstrip(".,")

            try:
                if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", number):
                    value = float(re.sub(r"[.,]", "", number))
                else:
                    value = float(number.replace(",", "."))
            except ValueError:
                continue

            tokens.append([value, unit or None])

        if not tokens:
            return None

        # '15 - 20 triệu': số không có đơn vị lấy đơn vị của số đứng sau
        carry = None

        for token in reversed(tokens):
            if token[1]:
                carry = token[1]
            else:
                token[1] = carry

        amounts = []

        for value, unit in tokens:
            if unit:
                value *= self.SALARY_UNITS[unit]
            elif not is_usd and value < 1000:
                value *= 1e6          # '15 - 20' -> hiểu là triệu

            if is_usd:
                value *= self.USD_TO_VND

            amounts.append(value)

        return (min(amounts), max(amounts))

    def _update_filter_icons(self):
        for key, icon in self.filter_icons.items():
            if self.column_filters[key] is None:
                icon.configure(text=self.ICON_IDLE, fg=self.TEXT_MUTED)
            else:
                icon.configure(text=self.ICON_ACTIVE, fg=self.FILTER_ACTIVE)

    @staticmethod
    def _split_locations(value):
        """'Hà Nội, Hồ Chí Minh' -> ['Hà Nội', 'Hồ Chí Minh']."""
        return [
            part.strip()
            for part in re.split(r"[,;/|]", value or "")
            if part.strip()
        ]

    @staticmethod
    def _normalize_text(text):
        """'  Hà   Nội ' -> 'ha noi' (bỏ dấu, chữ thường, gọn khoảng trắng)."""
        text = (text or "").replace("đ", "d").replace("Đ", "D")
        decomposed = unicodedata.normalize("NFD", text)

        stripped = "".join(
            ch for ch in decomposed if not unicodedata.combining(ch)
        )

        return " ".join(stripped.casefold().split())

    def _matches_query(self, display, query):
        """Gõ 'Hà' -> khớp đúng dấu; gõ 'ha' (không dấu) -> khớp mọi dấu."""
        if not query:
            return True

        has_accent = (
            self._normalize_text(query) != " ".join(query.casefold().split())
        )

        if has_accent:
            return query.casefold() in display.casefold()

        return self._normalize_text(query) in self._normalize_text(display)

    @staticmethod
    def _pick_label(variants):
        """Chọn nhãn đẹp nhất trong các biến thể: có dấu > viết hoa đúng
        kiểu ('Hà Nội') > xuất hiện nhiều nhất."""

        def score(item):
            variant, count = item
            has_accent = (
                MainWindow._normalize_text(variant)
                != " ".join(variant.casefold().split())
            )
            return (has_accent, variant == variant.title(), count)

        return max(variants.items(), key=score)[0]

    def _group_variants(self, values, by_count):
        """Gộp các biến thể cùng chuỗi chuẩn hóa thành 1 dòng:
        'Hà Nội' / 'Ha Noi' / 'HA NOI' -> key 'ha noi', nhãn 'Hà Nội'."""
        groups = {}  # key chuẩn hóa -> Counter(các biến thể gốc trong DB)

        for value in values:
            key = self._normalize_text(value)

            if key:
                variant = " ".join(value.split())
                groups.setdefault(key, Counter())[variant] += 1

        keys = sorted(
            groups,
            key=(
                (lambda k: (-sum(groups[k].values()), k))
                if by_count
                else (lambda k: k)
            )
        )

        return [(key, self._pick_label(groups[key])) for key in keys]

    def _filter_options(self, key):
        """Danh sách [(key_chuẩn_hóa, nhãn_hiển_thị)] cho popup của cột."""
        if key == "location":
            # Nhiều job nhất đứng đầu (Hà Nội, Hồ Chí Minh, ...)
            values = [
                name
                for job in self.jobs
                for name in self._split_locations(job["location"])
            ]
            return self._group_variants(values, by_count=True)

        values = [job[key] for job in self.jobs if job[key]]
        return self._group_variants(values, by_count=False)

    def _prune_filters(self):
        """Sau khi nạp lại dữ liệu: bỏ các lựa chọn không còn tồn tại."""
        for key in self.CHECKLIST_COLUMNS:
            selected = self.column_filters[key]

            if selected is None:
                continue

            valid = {k for k, _ in self._filter_options(key)}
            self.column_filters[key] = (selected & valid) or None

        self._update_filter_icons()

    # --- popup lọc theo từ khóa (Job Title / Company) -------------

    def _create_popup_window(self):
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=self.BORDER, padx=1, pady=1)

        body = tk.Frame(window, bg=self.WHITE)
        body.pack(fill="both", expand=True)

        return window, body

    def _build_popup_buttons(self, parent):
        """Hàng nút [Xóa lọc] [Áp dụng] dùng chung cho mọi popup."""
        button_row = tk.Frame(parent, bg=self.WHITE)
        button_row.pack(fill="x", padx=8, pady=8)

        apply_button = tk.Button(
            button_row,
            text="Áp dụng",
            command=self._apply_filter_popup,
            bg=self.FILTER_ACTIVE,
            fg="#FFFFFF",
            activebackground="#1E40AF",
            activeforeground="#FFFFFF",
            disabledforeground="#BFDBFE",
            relief="flat",
            bd=0,
            padx=14,
            pady=4,
            font=("Segoe UI Semibold", 9),
            cursor="hand2"
        )

        clear_button = tk.Button(
            button_row,
            text="Xóa lọc",
            command=self._clear_filter_popup,
            bg=self.WHITE,
            fg=self.TEXT_SECONDARY,
            activebackground=self.HOVER_BG,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=self.BORDER,
            padx=14,
            pady=3,
            font=("Segoe UI", 9),
            cursor="hand2"
        )

        apply_button.pack(side="right")
        clear_button.pack(side="right", padx=(0, 6))

        return apply_button

    def _open_text_filter_popup(self, key):
        # rule: None | (điều kiện, text người dùng gõ, text đã chuẩn hóa)
        rule = self.column_filters[key]

        window, body = self._create_popup_window()

        tk.Label(
            body,
            text="Điều kiện",
            bg=self.WHITE,
            fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=8, pady=(8, 2))

        condition = tk.StringVar(
            value=self.TEXT_CONDITIONS[rule[0] if rule else "contains"]
        )

        combo = ttk.Combobox(
            body,
            textvariable=condition,
            values=list(self.TEXT_CONDITIONS.values()),
            state="readonly",
            font=("Segoe UI", 10)
        )

        combo.pack(fill="x", padx=8)

        tk.Label(
            body,
            text="Nhập từ khóa tìm kiếm...",
            bg=self.WHITE,
            fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=8, pady=(8, 2))

        query = tk.StringVar(value=rule[1] if rule else "")

        entry = tk.Entry(
            body,
            textvariable=query,
            width=32,
            font=("Segoe UI", 10),
            relief="flat",
            bg=self.WHITE,
            fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY,
            highlightthickness=1,
            highlightbackground=self.BORDER,
            highlightcolor=self.FILTER_ACTIVE
        )

        entry.pack(fill="x", padx=8, ipady=3)

        self._build_popup_buttons(body)

        self._fp = {
            "type": "text",
            "key": key,
            "window": window,
            "query": query,
            "condition": condition,
            "after_id": None
        }

        # Gõ đến đâu bảng lọc đến đó (debounce để không giật)
        query.trace_add("write", lambda *_: self._schedule_text_filter())
        combo.bind("<<ComboboxSelected>>", lambda e: self._schedule_text_filter())

        for widget in (entry, combo):
            widget.bind("<Escape>", lambda e: self._close_filter_popup())
            widget.bind("<Return>", lambda e: self._apply_filter_popup())

        self._place_filter_popup(window, key)

        window.after(20, lambda: (entry.focus_force(), entry.select_range(0, "end")))

    def _schedule_text_filter(self):
        fp = self._fp

        if not fp or fp.get("type") != "text":
            return

        if fp["after_id"]:
            self.root.after_cancel(fp["after_id"])

        fp["after_id"] = self.root.after(250, self._apply_text_filter)

    def _apply_text_filter(self):
        fp = self._fp

        if not fp or fp.get("type") != "text":
            return

        if fp["after_id"]:
            self.root.after_cancel(fp["after_id"])
            fp["after_id"] = None

        text = fp["query"].get().strip()
        needle = self._normalize_text(text)
        label = fp["condition"].get()

        condition = next(
            (k for k, v in self.TEXT_CONDITIONS.items() if v == label),
            "contains"
        )

        # Ô trống = không lọc
        self.column_filters[fp["key"]] = (
            (condition, text, needle) if needle else None
        )

        self._on_filters_changed()

    def _text_matches(self, value, condition, needle):
        value = self._normalize_text(value)

        if condition == "startswith":
            return value.startswith(needle)

        if condition == "endswith":
            return value.endswith(needle)

        return needle in value

    # --- popup lọc theo khoảng ngày (Posted At / Expire Date) -----

    @staticmethod
    def _parse_date(text):
        """'04/10/2026' -> date; để trống -> None; sai định dạng -> ValueError."""
        text = (text or "").strip()

        if not text:
            return None

        return datetime.strptime(text, "%d/%m/%Y").date()

    @staticmethod
    def _format_date(value):
        return value.strftime("%d/%m/%Y") if value else ""

    @staticmethod
    def _date_in_range(value, start, end):
        """Mốc `value` (datetime) có nằm trong [start, end] (tính theo ngày)?"""
        if not isinstance(value, datetime):
            return False  # job không có ngày thì loại khi đang lọc

        day = value.date()

        return (start is None or day >= start) and (end is None or day <= end)

    def _date_presets(self, key):
        """[(nhãn, từ ngày, đến ngày)] - None/None nghĩa là 'Tất cả'."""
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]

        presets = [
            ("Tất cả", None, None),
            ("Hôm nay", today, today),
            ("7 ngày qua", today - timedelta(days=6), today),
            ("30 ngày qua", today - timedelta(days=29), today),
            (
                "Tháng này",
                today.replace(day=1),
                today.replace(day=last_day)
            ),
        ]

        # Ngày hết hạn thường nằm ở tương lai -> thêm mốc "tới"
        if key == "expire_date":
            presets[4:4] = [
                ("7 ngày tới", today, today + timedelta(days=6)),
                ("30 ngày tới", today, today + timedelta(days=29)),
            ]

        return presets

    def _build_calendar(self, parent, shown, selected, on_pick):
        """Lịch tháng gọn: ‹ Tháng m/yyyy › + lưới ngày (T2 -> CN)."""
        frame = tk.Frame(
            parent,
            bg=self.WHITE,
            highlightthickness=1,
            highlightbackground=self.BORDER
        )

        state = {"year": shown.year, "month": shown.month}

        header = tk.Frame(frame, bg=self.WHITE)
        header.pack(fill="x", padx=4, pady=4)

        title = tk.Label(
            header,
            bg=self.WHITE,
            fg=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 10)
        )

        grid = tk.Frame(frame, bg=self.WHITE)
        grid.pack(padx=4, pady=(0, 4))

        def render():
            for child in grid.winfo_children():
                child.destroy()

            title.configure(text=f"Tháng {state['month']}/{state['year']}")

            for col, name in enumerate(
                ("T2", "T3", "T4", "T5", "T6", "T7", "CN")
            ):
                tk.Label(
                    grid,
                    text=name,
                    width=3,
                    bg=self.WHITE,
                    fg=self.TEXT_MUTED,
                    font=("Segoe UI", 8)
                ).grid(row=0, column=col)

            today = date.today()
            weeks = calendar.monthcalendar(state["year"], state["month"])

            for row, week in enumerate(weeks, start=1):
                for col, day in enumerate(week):
                    if not day:
                        continue

                    value = date(state["year"], state["month"], day)

                    if value == selected:
                        bg, fg = self.FILTER_ACTIVE, "#FFFFFF"
                    elif value == today:
                        bg, fg = "#DBEAFE", self.TEXT_PRIMARY
                    else:
                        bg, fg = self.WHITE, self.TEXT_PRIMARY

                    tk.Button(
                        grid,
                        text=str(day),
                        width=3,
                        relief="flat",
                        bd=0,
                        bg=bg,
                        fg=fg,
                        activebackground=self.HOVER_BG,
                        font=("Segoe UI", 9),
                        cursor="hand2",
                        command=lambda v=value: on_pick(v)
                    ).grid(row=row, column=col, padx=1, pady=1)

        def shift(delta):
            index = state["year"] * 12 + state["month"] - 1 + delta
            state["year"], state["month"] = index // 12, index % 12 + 1
            render()

        for text, delta, side in (("‹", -1, "left"), ("›", 1, "right")):
            tk.Button(
                header,
                text=text,
                width=3,
                relief="flat",
                bd=0,
                bg=self.WHITE,
                fg=self.TEXT_SECONDARY,
                activebackground=self.HOVER_BG,
                font=("Segoe UI", 10),
                cursor="hand2",
                command=lambda d=delta: shift(d)
            ).pack(side=side)

        title.pack(side="left", expand=True, fill="x")

        render()

        return frame

    def _open_date_filter_popup(self, key):
        # rule: None | (từ ngày | None, đến ngày | None)
        rule = self.column_filters[key]

        window, body = self._create_popup_window()

        self._fp = {
            "type": "date",
            "key": key,
            "window": window,
            "vars": {
                "from": tk.StringVar(
                    value=self._format_date(rule[0]) if rule else ""
                ),
                "to": tk.StringVar(
                    value=self._format_date(rule[1]) if rule else ""
                ),
            },
            "holders": {},
            "error": None,
        }

        fp = self._fp

        # --- Chọn nhanh ---
        tk.Label(
            body,
            text="Chọn nhanh",
            bg=self.WHITE,
            fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=8, pady=(8, 2))

        preset_frame = tk.Frame(body, bg=self.WHITE)
        preset_frame.pack(fill="x", padx=6)

        for index, (label, start, end) in enumerate(self._date_presets(key)):
            tk.Button(
                preset_frame,
                text=label,
                command=lambda s=start, e=end: self._apply_date_preset(s, e),
                bg=self.WHITE,
                fg=self.TEXT_PRIMARY,
                activebackground=self.HOVER_BG,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=self.BORDER,
                padx=8,
                pady=3,
                font=("Segoe UI", 9),
                cursor="hand2"
            ).grid(row=index // 3, column=index % 3, sticky="ew", padx=2, pady=2)

        for col in range(3):
            preset_frame.grid_columnconfigure(col, weight=1, uniform="preset")

        tk.Frame(body, height=1, bg=self.BORDER).pack(
            fill="x", padx=8, pady=8
        )

        # --- Từ ngày / Đến ngày ---
        entries = []

        for name, label in (("from", "Từ ngày"), ("to", "Đến ngày")):
            tk.Label(
                body,
                text=f"{label} (dd/mm/yyyy)",
                bg=self.WHITE,
                fg=self.TEXT_SECONDARY,
                font=("Segoe UI", 9)
            ).pack(anchor="w", padx=8, pady=(0, 2))

            row = tk.Frame(body, bg=self.WHITE)
            row.pack(fill="x", padx=8, pady=(0, 6))

            entry = tk.Entry(
                row,
                textvariable=fp["vars"][name],
                width=14,
                font=("Segoe UI", 10),
                relief="flat",
                bg=self.WHITE,
                fg=self.TEXT_PRIMARY,
                insertbackground=self.TEXT_PRIMARY,
                highlightthickness=1,
                highlightbackground=self.BORDER,
                highlightcolor=self.FILTER_ACTIVE
            )

            entry.pack(side="left", ipady=3)
            entries.append(entry)

            tk.Button(
                row,
                text="▦",
                command=lambda n=name: self._toggle_date_calendar(n),
                bg=self.WHITE,
                fg=self.FILTER_ACTIVE,
                activebackground=self.HOVER_BG,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=self.BORDER,
                padx=6,
                font=("Segoe UI Symbol", 10),
                cursor="hand2"
            ).pack(side="left", padx=(6, 0))

            holder = tk.Frame(body, bg=self.WHITE)
            holder.pack(fill="x", padx=8)
            fp["holders"][name] = holder

        fp["error"] = tk.Label(
            body,
            text="",
            bg=self.WHITE,
            fg="#DC2626",
            font=("Segoe UI", 9)
        )

        fp["error"].pack(anchor="w", padx=8)

        self._build_popup_buttons(body)

        for entry in entries:
            entry.bind("<Escape>", lambda e: self._close_filter_popup())
            entry.bind("<Return>", lambda e: self._apply_filter_popup())

        self._place_filter_popup(window, key)

        window.after(20, entries[0].focus_force)

    @staticmethod
    def _clear_calendar_holder(holder):
        """Xóa lịch và thu khung chứa về cỡ tối thiểu.

        Tk giữ nguyên cỡ cũ của một frame khi mọi widget con bị xóa,
        nên phải đặt lại width/height thì khoảng trống mới biến mất."""
        for child in holder.winfo_children():
            child.destroy()

        holder.configure(width=1, height=1)

    def _toggle_date_calendar(self, which):
        fp = self._fp

        for name, holder in fp["holders"].items():
            was_open = bool(holder.winfo_children())

            self._clear_calendar_holder(holder)

            if name != which or was_open:
                continue

            try:
                current = self._parse_date(fp["vars"][name].get())
            except ValueError:
                current = None

            self._build_calendar(
                holder,
                shown=current or date.today(),
                selected=current,
                on_pick=lambda d, n=name: self._pick_date(n, d)
            ).pack(anchor="w", pady=(0, 6))

        self._refit_filter_popup()

    def _pick_date(self, which, picked):
        fp = self._fp

        fp["vars"][which].set(self._format_date(picked))
        fp["error"].configure(text="")

        self._clear_calendar_holder(fp["holders"][which])

        self._refit_filter_popup()

    def _apply_date_preset(self, start, end):
        fp = self._fp

        fp["vars"]["from"].set(self._format_date(start))
        fp["vars"]["to"].set(self._format_date(end))

        self._apply_filter_popup()

    def _apply_date_filter(self):
        fp = self._fp

        try:
            start = self._parse_date(fp["vars"]["from"].get())
            end = self._parse_date(fp["vars"]["to"].get())
        except ValueError:
            fp["error"].configure(text="Ngày không hợp lệ, nhập dd/mm/yyyy")
            return

        if start and end and start > end:
            fp["error"].configure(text="'Từ ngày' phải trước 'Đến ngày'")
            return

        # Cả hai trống = không lọc
        self.column_filters[fp["key"]] = (
            (start, end) if (start or end) else None
        )

        self._close_filter_popup()
        self._on_filters_changed()

    # --- popup ---------------------------------------------------

    def _toggle_filter_popup(self, key):
        if self._fp and self._fp["key"] == key:
            self._close_filter_popup()
        else:
            self._open_filter_popup(key)

    def _open_filter_popup(self, key):
        self._close_filter_popup()

        if key in self.TEXT_COLUMNS:
            self._open_text_filter_popup(key)
            return

        if key in self.DATE_COLUMNS:
            self._open_date_filter_popup(key)
            return

        options = self._filter_options(key)
        selected = self.column_filters[key]
        checked = (
            {k for k, _ in options} if selected is None else set(selected)
        )

        window, body = self._create_popup_window()

        # Ô tìm kiếm trong popup
        search_row = tk.Frame(body, bg=self.WHITE)
        search_row.pack(fill="x", padx=8, pady=(8, 6))

        tk.Label(
            search_row,
            text="Tìm kiếm",
            bg=self.WHITE,
            fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 9)
        ).pack(side="left", padx=(0, 6))

        query = tk.StringVar()

        entry = tk.Entry(
            search_row,
            textvariable=query,
            font=("Segoe UI", 10),
            relief="flat",
            bg=self.WHITE,
            fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY,
            highlightthickness=1,
            highlightbackground=self.BORDER,
            highlightcolor=self.FILTER_ACTIVE
        )

        entry.pack(side="left", fill="x", expand=True, ipady=3)

        # Danh sách checkbox (Listbox: cuộn mượt kể cả khi có hàng trăm mục)
        list_row = tk.Frame(body, bg=self.WHITE)
        list_row.pack(fill="both", expand=True, padx=8)

        scrollbar = ttk.Scrollbar(
            list_row,
            orient="vertical",
            style="Vertical.TScrollbar"
        )

        listbox = tk.Listbox(
            list_row,
            height=10,
            width=30,
            font=("Segoe UI", 10),
            activestyle="none",
            bd=0,
            highlightthickness=0,
            exportselection=False,
            bg=self.WHITE,
            fg=self.TEXT_PRIMARY,
            selectbackground=self.WHITE,
            selectforeground=self.TEXT_PRIMARY,
            yscrollcommand=scrollbar.set
        )

        scrollbar.configure(command=listbox.yview)
        scrollbar.pack(side="right", fill="y")
        listbox.pack(side="left", fill="both", expand=True)

        # Nút hành động
        apply_button = self._build_popup_buttons(body)

        self._fp = {
            "key": key,
            "window": window,
            "options": options,
            "checked": checked,
            "visible": [],
            "query": query,
            "list": listbox,
            "apply": apply_button
        }

        query.trace_add("write", lambda *_: self._render_filter_list())
        listbox.bind("<Button-1>", self._on_filter_list_click)

        for widget in (entry, listbox):
            widget.bind("<Escape>", lambda e: self._close_filter_popup())
            widget.bind("<Return>", lambda e: self._apply_filter_popup())

        self._render_filter_list()
        self._place_filter_popup(window, key)

        window.after(20, entry.focus_force)

    def _place_filter_popup(self, window, key):
        window.update_idletasks()

        x = self.tree.winfo_rootx() + self._column_left(key)
        y = self.tree.winfo_rooty() + self._measure_header_height()

        # Không để popup tràn ra ngoài màn hình
        x = max(0, min(x, window.winfo_screenwidth() - window.winfo_reqwidth() - 8))

        window.geometry(f"+{x}+{y}")

        if self._fp and self._fp.get("window") is window:
            self._fp["origin"] = (x, y)

    def _refit_filter_popup(self):
        """Ép popup co/giãn lại theo nội dung hiện tại.

        Bỏ kích thước cũ (geometry("")) để Toplevel không giữ chiều cao
        lúc đang mở lịch; chỉ giữ lại vị trí, và đẩy lên nếu tràn đáy
        màn hình."""
        fp = self._fp

        if not fp or not fp.get("origin"):
            return

        window = fp["window"]
        x, y = fp["origin"]

        window.geometry("")
        window.update_idletasks()

        overflow = y + window.winfo_reqheight() - (
            window.winfo_screenheight() - 48
        )

        if overflow > 0:
            y = max(0, y - overflow)

        window.geometry(f"+{x}+{y}")

    def _render_filter_list(self):
        fp = self._fp

        if not fp:
            return

        query = fp["query"].get().strip()

        visible = [
            (k, display)
            for k, display in fp["options"]
            if self._matches_query(display, query)
        ]

        fp["visible"] = visible

        listbox = fp["list"]
        top = listbox.yview()[0]

        all_checked = bool(visible) and all(
            k in fp["checked"] for k, _ in visible
        )

        listbox.delete(0, "end")
        listbox.insert("end", f"{self._box(all_checked)}  Chọn tất cả")

        for k, display in visible:
            listbox.insert(
                "end",
                f"{self._box(k in fp['checked'])}  {display}"
            )

        listbox.yview_moveto(top)

        # Không chọn mục nào thì không cho Áp dụng
        fp["apply"].configure(
            state="normal" if fp["checked"] else "disabled"
        )

    @staticmethod
    def _box(is_checked):
        return "☑" if is_checked else "☐"

    def _on_filter_list_click(self, event):
        fp = self._fp
        listbox = fp["list"]

        index = listbox.nearest(event.y)
        bbox = listbox.bbox(index) if index >= 0 else None

        # Click vào vùng trống bên dưới mục cuối thì bỏ qua
        if not bbox or event.y > bbox[1] + bbox[3]:
            return "break"

        visible_keys = {k for k, _ in fp["visible"]}

        if index == 0:
            # "Chọn tất cả" tác động lên các mục đang hiển thị (đã lọc)
            if visible_keys <= fp["checked"]:
                fp["checked"] -= visible_keys
            else:
                fp["checked"] |= visible_keys
        else:
            k = fp["visible"][index - 1][0]
            fp["checked"] ^= {k}

        self._render_filter_list()

        return "break"

    def _apply_filter_popup(self):
        fp = self._fp

        if fp and fp.get("type") == "text":
            self._apply_text_filter()
            self._close_filter_popup()
            return

        if fp and fp.get("type") == "date":
            self._apply_date_filter()
            return

        if not fp or not fp["checked"]:
            return

        all_keys = {k for k, _ in fp["options"]}
        checked = fp["checked"] & all_keys

        # Chọn đủ tất cả = không lọc
        self.column_filters[fp["key"]] = (
            None if checked == all_keys else checked
        )

        self._close_filter_popup()
        self._on_filters_changed()

    def _clear_filter_popup(self):
        if not self._fp:
            return

        self.column_filters[self._fp["key"]] = None

        self._close_filter_popup()
        self._on_filters_changed()

    def _close_filter_popup(self):
        fp = self._fp

        if not fp:
            return

        # Đóng khi còn lần gõ chưa kịp lọc -> lọc nốt
        if fp.get("after_id"):
            self.root.after_cancel(fp["after_id"])
            self._apply_text_filter()

        fp["window"].destroy()
        self._fp = None

    def _on_filters_changed(self):
        self._update_filter_icons()
        self.on_search()

    def _on_root_click(self, event):
        self._close_row_menu()

        if not self._fp:
            return

        widget = event.widget

        if widget in self.filter_icons.values():
            return  # icon tự toggle

        if widget is self.tree and self.tree.identify_region(
            event.x, event.y
        ) == "heading":
            column = self.tree.identify_column(event.x)  # '#3'
            index = int(column[1:]) - 1 if column else -1
            names = self.tree["columns"]

            if (
                0 <= index < len(names)
                and names[index] in self.FILTER_COLUMNS
                and names[index] not in self.SORT_COLUMNS
            ):
                return  # heading Location / Source vẫn tự toggle popup lọc

        self._close_filter_popup()

    def _on_root_configure(self, event):
        if event.widget is self.root:
            self._close_filter_popup()

    def _matches_filters(self, job, keyword):
        for key, raw_key in self.DATE_COLUMNS.items():
            rule = self.column_filters[key]

            if rule is not None and not self._date_in_range(
                job.get(raw_key), *rule
            ):
                return False

        for key in self.TEXT_COLUMNS:
            rule = self.column_filters[key]

            if rule is not None:
                condition, _, needle = rule

                if not self._text_matches(job[key], condition, needle):
                    return False

        selected = self.column_filters["location"]

        if selected is not None:
            names = {
                self._normalize_text(name)
                for name in self._split_locations(job["location"])
            }

            if not names & selected:
                return False

        selected = self.column_filters["source"]

        if (
            selected is not None
            and self._normalize_text(job["source"]) not in selected
        ):
            return False

        if not keyword:
            return True

        return any(
            keyword in job[key].lower()
            for key in ("title", "company", "location", "source")
        )

    def clear_search_and_filters(self):
        """Reset ô Search + mọi filter ở header rồi nạp lại danh sách."""
        self._close_filter_popup()

        self.search_entry.delete(0, "end")
        self.column_filters = {key: None for key in self.FILTER_COLUMNS}

        self._update_filter_icons()
        self.on_search()

    def on_search(self, event=None):
        keyword = (
            self.search_entry
            .get()
            .strip()
            .lower()
        )

        self.filtered_jobs = self._sort_jobs([
            job
            for job in self.jobs
            if self._matches_filters(job, keyword)
        ])

        self.current_page = 1

        self.refresh_table()

    # ============================================================
    # Pagination
    # ============================================================

    def previous_page(self):
        if self.current_page <= 1:
            return

        self.current_page -= 1

        self.refresh_table()

    def next_page(self):
        total_pages = max(
            1,
            (
                len(self.filtered_jobs)
                + self.PAGE_SIZE
                - 1
            )
            // self.PAGE_SIZE
        )

        if self.current_page >= total_pages:
            return

        self.current_page += 1

        self.refresh_table()

    def go_to_page(self, event=None):
        value = self.page_entry.get().strip()

        if not value:
            self.page_entry.delete(0, "end")
            self.page_entry.insert(0, str(self.current_page))
            return

        try:
            page = int(value)
        except ValueError:
            self.page_entry.delete(0, "end")
            self.page_entry.insert(0, str(self.current_page))
            return

        total_pages = max(
            1,
            (
                len(self.filtered_jobs)
                + self.PAGE_SIZE
                - 1
            ) // self.PAGE_SIZE
        )

        # Giới hạn page trong khoảng 1 -> total_pages
        page = max(1, min(page, total_pages))

        if page == self.current_page:
            self.page_entry.delete(0, "end")
            self.page_entry.insert(0, str(self.current_page))
            return

        self.current_page = page
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

        close_filter = getattr(self, "_close_filter_popup", None)

        if close_filter:
            close_filter()

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

        self._close_filter_popup()

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