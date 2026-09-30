import asyncio
import math
import re
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from tkinter import font as tkfont
from tkinter import ttk

import customtkinter as ctk

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
            yscrollcommand=self.table_scrollbar.set
        )

        # --------------------------------------------------------
        # Headings
        # --------------------------------------------------------

        headings = {
            "title": "Job Title",
            "company": "Company",
            "location": "Location",
            "source": "Source",
            "posted_at": "Posted At",
            "expire_date": "Expire Date"
        }

        for key, text in headings.items():
            self.tree.heading(key, text=text)

        # --------------------------------------------------------
        # Columns
        # --------------------------------------------------------

        self.tree.column(
            "title",
            width=230,
            minwidth=170,
            stretch=True,
            anchor="w"
        )

        self.tree.column(
            "company",
            width=140,
            minwidth=100,
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
            anchor="center"
        )

        self.tree.column(
            "posted_at",
            width=90,
            minwidth=80,
            stretch=False,
            anchor="center"
        )

        self.tree.column(
            "expire_date",
            width=95,
            minwidth=85,
            stretch=False,
            anchor="center"
        )

        # --------------------------------------------------------
        # Events
        # --------------------------------------------------------

        self.tree.bind(
            "<<TreeviewSelect>>",
            self.on_job_selected
        )

        # Double-click a job -> open its original URL in the browser.
        self.tree.bind(
            "<Double-1>",
            self.on_job_double_click
        )

        self._build_state_overlay()

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

    def _show_state(self, message, loading=False):
        self.state_label.configure(text=message)

        if loading:
            self.state_progress.pack(pady=(12, 0))
            self.state_progress.start()
        else:
            self.state_progress.stop()
            self.state_progress.pack_forget()

        self.state_overlay.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1
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
                "Không tìm thấy kết quả phù hợp."
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

        # Specifications: bullet list đơn giản trên nền trắng (không card).
        self.spec_section = self._build_html_section(
            row=6,
            title="Thông tin khác",
            card=False,
            font_size=self.HTML_FONT_SIZE_LARGE,
            line_gap=self.SPEC_LINE_GAP
        )

        self.benefits_section = self._build_html_section(
            row=8,
            title="Quyền lợi"
        )

        self.contact_section = self._build_html_section(
            row=10,
            title="Thông tin liên hệ"
        )

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
            text="Select a job",
            bg=self.WHITE,
            fg=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 20),
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

        header.bind(
            "<Configure>",
            self._on_header_resize
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
        self.jd_meta_rows = {}

        for index, key in enumerate(self.META_ICONS, start=2):
            label = ctk.CTkLabel(
                header,
                text="",
                text_color=self.TEXT_SECONDARY,
                font=("Segoe UI", 12),
                anchor="w",
                justify="left",
                wraplength=self._wrap_width
            )

            label.grid(
                row=index,
                column=0,
                sticky="ew",
                pady=(4, 0)
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

        result = text.count("1.0", "end", "ypixels")
        pixels = result[0] if result else 0

        line_height = tkfont.Font(
            font=text.cget("font")
        ).metrics("linespace")

        text.configure(
            height=max(1, math.ceil(pixels / line_height))
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

    def _on_header_resize(self, event):
        # CTkLabel có padding nội bộ -> chừa dư một chút để không mất ký tự.
        width = max(120, event.width - 16)

        for label in self.jd_meta_rows.values():
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

        for job in page_jobs:
            self.tree.insert(
                "",
                "end",
                iid=job["id"],
                values=(
                    job["title"],
                    job["company"],
                    job["location"],
                    job["source"],
                    job["posted_at"],
                    job["expire_date"]
                )
            )

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

        self._set_html_section(
            self.contact_section,
            job.get("contact")
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

    def on_job_double_click(self, event=None):
        """Open the selected job URL in the default browser."""
        item_id = self.tree.identify_row(event.y) if event else None

        if not item_id:
            selection = self.tree.selection()
            item_id = selection[0] if selection else None

        if not item_id:
            return

        job = next(
            (item for item in self.jobs if item["id"] == str(item_id)),
            None
        )

        if not job:
            return

        url = (job.get("url") or "").strip()
        if url:
            webbrowser.open_new_tab(url)

    def _clear_details(self):
        self.selected_job = None

        self.jd_title.configure(text="Select a job")
        self.jd_source.configure(text="")

        self.jd_salary.grid_remove()

        for label in self.jd_meta_rows.values():
            label.grid_remove()

        self.jd_open_button.configure(state="disabled")

        self._render_specifications(None)

        for section in (
            self.desc_section,
            self.req_section,
            self.benefits_section,
            self.contact_section
        ):
            self._set_html_section(section, "")

    # ============================================================
    # Search
    # ============================================================

    def on_search(self, event=None):
        keyword = (
            self.search_entry
            .get()
            .strip()
            .lower()
        )

        if not keyword:
            self.filtered_jobs = list(
                self.jobs
            )
        else:
            self.filtered_jobs = [
                job
                for job in self.jobs
                if (
                    keyword in job["title"].lower()
                    or keyword in job["company"].lower()
                    or keyword in job["location"].lower()
                    or keyword in job["source"].lower()
                )
            ]

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
        from core.run import run_all

        self.crawl_button.configure(state="disabled", text="Crawling...")

        def worker():
            try:
                asyncio.run(run_all(self.repository))
            except Exception as exc:
                self.root.after(
                    0,
                    lambda exc=exc: print(f"[X] Lỗi khi crawl: {exc}")
                )
            finally:
                self.root.after(0, self._on_crawl_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_crawl_done(self):
        self.crawl_button.configure(state="normal", text="Crawl")
        self.load_jobs()

    def on_backup(self):
        print("Backup clicked")