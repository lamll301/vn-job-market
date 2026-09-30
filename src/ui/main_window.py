import asyncio
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

import customtkinter as ctk

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

    LEFT_RATIO = 0.70
    RIGHT_RATIO = 0.30

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
        self.root.title("App")

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
    # Content — 70 / 30 split between Left and Right panels
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
        # 70 / 30 split
        #
        # weight 7 : weight 3 = 70 : 30
        # --------------------------------------------------------

        self.content.grid_columnconfigure(
            0,
            weight=7,
            minsize=620
        )

        self.content.grid_columnconfigure(
            1,
            weight=3,
            minsize=320
        )

        self.content.grid_rowconfigure(
            0,
            weight=1
        )

        self._build_left_panel()
        self._build_right_panel()

    # ============================================================
    # Left Panel (~70%)
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
    # Right Panel (~30%)
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

        # --------------------------------------------------------
        # Responsive rows
        #
        # 0 = header            1 = separator
        # 2 = "Job Description" heading, 3 = Job Description text
        # 4 = "Requirements" heading,    5 = Requirements text
        #
        # Rows 3 and 5 share one uniform group, so both text boxes
        # always get the same height.
        # --------------------------------------------------------

        for row in (0, 1, 2, 4):
            self.right_panel.grid_rowconfigure(
                row,
                weight=0
            )

        for row in (3, 5):
            self.right_panel.grid_rowconfigure(
                row,
                weight=1,
                uniform="jd_sections"
            )

        self.right_panel.grid_columnconfigure(
            0,
            weight=1
        )

        # --------------------------------------------------------
        # JD Header
        # --------------------------------------------------------

        self.jd_header = ctk.CTkFrame(
            self.right_panel,
            fg_color=self.WHITE,
            corner_radius=0
        )

        self.jd_header.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=18,
            pady=(16, 0)
        )

        self.jd_header.grid_columnconfigure(
            0,
            weight=1
        )

        self.jd_title = ctk.CTkLabel(
            self.jd_header,
            text="Select a job",
            text_color=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 17),
            anchor="w",
            justify="left",
            wraplength=300
        )

        self.jd_title.grid(
            row=0,
            column=0,
            sticky="ew"
        )

        self.jd_meta = ctk.CTkLabel(
            self.jd_header,
            text="",
            text_color=self.TEXT_SECONDARY,
            font=("Segoe UI", 10),
            anchor="w",
            justify="left"
        )

        self.jd_meta.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(5, 0)
        )

        self.jd_source = ctk.CTkLabel(
            self.jd_header,
            text="",
            fg_color=self.TAG_BG,
            text_color=self.TAG_TEXT,
            corner_radius=6,
            padx=9,
            pady=4,
            font=("Segoe UI Semibold", 9),
            anchor="w"
        )

        self.jd_source.grid(
            row=2,
            column=0,
            sticky="w",
            pady=(9, 0)
        )

        # --------------------------------------------------------
        # Separator
        # --------------------------------------------------------

        separator = ctk.CTkFrame(
            self.right_panel,
            height=1,
            fg_color=self.BORDER
        )

        separator.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=18,
            pady=(15, 0)
        )

        # --------------------------------------------------------
        # Two text sections
        # --------------------------------------------------------

        self.jd_text = self._build_text_section(
            row=2,
            title="Job Description"
        )

        self.req_text = self._build_text_section(
            row=4,
            title="Requirements",
            last=True
        )

    def _build_text_section(self, row, title, last=False):
        """Heading + read-only text box with its own scrollbar."""

        heading = ctk.CTkLabel(
            self.right_panel,
            text=title,
            text_color=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 11),
            anchor="w"
        )

        heading.grid(
            row=row,
            column=0,
            sticky="ew",
            padx=18,
            pady=(13, 7)
        )

        container = ctk.CTkFrame(
            self.right_panel,
            fg_color=self.JD_BG,
            corner_radius=8,
            border_width=1,
            border_color=self.BORDER_LIGHT
        )

        container.grid(
            row=row + 1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(0, 16 if last else 0)
        )

        container.grid_rowconfigure(
            0,
            weight=1
        )

        container.grid_columnconfigure(
            0,
            weight=1
        )

        text = tk.Text(
            container,
            wrap="word",
            bg=self.JD_BG,
            fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            padx=14,
            pady=12,
            spacing1=2,
            spacing2=2,
            spacing3=6
        )

        text.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        scrollbar = ttk.Scrollbar(
            container,
            orient="vertical",
            command=text.yview,
            style="Vertical.TScrollbar"
        )

        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
            padx=(0, 3),
            pady=3
        )

        text.configure(
            yscrollcommand=scrollbar.set,
            state="disabled"
        )

        return text

    @staticmethod
    def _set_text(widget, content):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")
        widget.yview_moveto(0)

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
            "requirements": doc.get("requirements") or ""
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

        self.jd_title.configure(
            text=job["title"] or "(Không có tiêu đề)"
        )

        self.jd_meta.configure(
            text=(
                f"{job['company']}  •  "
                f"{job['location']}"
            )
        )

        self.jd_source.configure(
            text=job["source"]
        )

        self._set_text(
            self.jd_text,
            job["description"] or "(Không có mô tả công việc)"
        )

        self._set_text(
            self.req_text,
            job["requirements"] or "(Không có yêu cầu)"
        )

    def _clear_details(self):
        self.selected_job = None

        self.jd_title.configure(text="Select a job")
        self.jd_meta.configure(text="")
        self.jd_source.configure(text="")

        self._set_text(self.jd_text, "")
        self._set_text(self.req_text, "")

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