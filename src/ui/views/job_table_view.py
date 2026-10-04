"""Khung bảng danh sách việc làm (Treeview) ở cột bên trái của MainWindow.

JobTableView gồm: Treeview + thanh cuộn tự ẩn, ngắt dòng trong ô, icon lọc /
sort trên header, menu chuột phải và lớp phủ trạng thái (loading / rỗng / lỗi).

MainWindow chỉ cần:

    self.table = JobTableView(
        parent, theme=JobTableTheme(...),
        get_jobs=lambda: self.jobs,             # toàn bộ job (cho popup lọc)
        on_select=self._on_job_selected,        # job được chọn (None = bảng rỗng)
        on_filter_change=self.on_search,        # lọc / sort đổi -> nạp lại
        on_clear_filters=self.clear_search_and_filters,
    )
    self.table.grid(...)

    self.table.set_rows(page_jobs)              # đổ dữ liệu một trang
    self.table.update_state(loading=..., error=..., total=..., shown=...)
    self.table.matches_filters(job) / self.table.sort_jobs(jobs)
"""

import math
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk

import customtkinter as ctk

from ui.components.filters import (
    FilterManager,
    FilterTheme,
    measure_header_height,
)
from ui.components.sort import SortManager, SortTheme
from ui.components.state_overlay import StateOverlay, StateOverlayTheme


@dataclass(frozen=True)
class JobTableTheme:
    """Màu dùng cho bảng (truyền từ MainWindow vào)."""

    white: str
    border: str
    text_primary: str
    text_secondary: str
    text_muted: str
    primary: str
    hover_bg: str
    selected: str        # nền dòng đang chọn
    active: str          # màu nhấn: cột đang lọc / sort


@dataclass(frozen=True)
class Column:
    key: str
    heading: str
    width: int
    minwidth: int
    stretch: bool


COLUMNS = (
    Column("title", "Job Title", 300, 170, True),
    Column("company", "Company", 200, 100, True),
    Column("salary", "Salary", 110, 80, True),
    Column("location", "Location", 120, 90, True),
    Column("source", "Source", 95, 80, False),
    Column("posted_at", "Posted At", 110, 105, False),
    Column("expire_date", "Expire Date", 120, 115, False),
)

COLUMN_KEYS = tuple(column.key for column in COLUMNS)


def wrap_text(text, width, font):
    """Ngắt text thành nhiều dòng vừa `width` pixel. Trả về (text, số dòng)."""
    text = (text or "").replace("\n", " ").strip()

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


def cell_text(job, key):
    return job[key] or ("—" if key == "salary" else "")


class JobTableView(ctk.CTkFrame):
    TREE_STYLE = "Jobs.Treeview"

    # Word wrap cho các cột trong bảng (Treeview không hỗ trợ sẵn)
    WRAP_COLUMNS = ("title", "company", "salary", "location")
    CELL_PADDING = 16
    MIN_ROW_HEIGHT = 40
    REWRAP_DELAY_MS = 80
    FIT_DELAY_MS = 100

    # Header lọc: cột ít giá trị -> popup checklist, nhiều giá trị -> gõ từ khóa
    FILTER_COLUMNS = (
        "title", "company", "location", "source", "posted_at", "expire_date"
    )
    CHECKLIST_COLUMNS = ("location", "source")
    TEXT_COLUMNS = ("title", "company")

    # cột ngày -> khoá ngày gốc (datetime) trong view model; lọc theo khoảng
    DATE_COLUMNS = {
        "posted_at": "posted_at_raw",
        "expire_date": "expired_at_raw",
    }

    # Sort theo header: click lần 1 tăng dần, lần 2 giảm dần, lần 3 về mặc định
    SORT_COLUMNS = ("title", "company", "salary", "posted_at", "expire_date")
    SORT_DEFAULT = ("posted_at", "desc")   # mới đăng nhất lên đầu

    ICON_WIDTH = 20
    DEFAULT_HEADER_HEIGHT = 26

    def __init__(
        self,
        parent,
        *,
        theme,
        get_jobs,
        on_select,
        on_filter_change,
        on_clear_filters
    ):
        super().__init__(
            parent,
            fg_color=theme.white,
            corner_radius=0
        )

        self.theme = theme
        self._get_jobs = get_jobs
        self._on_select = on_select
        self._on_filter_change = on_filter_change
        self._on_clear_filters = on_clear_filters

        self._rows = []             # các job đang hiển thị (một trang)
        self._rows_by_id = {}
        self._row_menu = None
        self._wrap_after_id = None
        self._fit_after_id = None

        self._row_font = tkfont.Font(family="Segoe UI", size=10)
        self._row_height = self.MIN_ROW_HEIGHT

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._configure_styles()
        self._build_tree()
        self._build_scrollbar()
        self._build_header_tools()
        self._build_events()
        self._build_state_overlay()

    # ------------------------------------------------------------------
    # API công khai
    # ------------------------------------------------------------------

    def set_rows(self, jobs):
        """Đổ một trang dữ liệu, chọn dòng đầu và báo qua on_select."""
        self._rows = list(jobs)
        self._rows_by_id = {job["id"]: job for job in self._rows}

        for item in self._tree.get_children():
            self._tree.delete(item)

        for job in self._rows:
            self._tree.insert(
                "",
                "end",
                iid=job["id"],
                values=tuple(cell_text(job, key) for key in COLUMN_KEYS)
            )

        self._apply_wrap()

        # Chọn dòng đầu tiên tự động
        rows = self._tree.get_children()

        if rows:
            first_id = rows[0]

            self._tree.selection_set(first_id)
            self._tree.focus(first_id)

            self._on_select(self._rows_by_id[first_id])
        else:
            self._on_select(None)

    def update_state(self, *, loading, error, total, shown):
        """Chọn thông điệp phù hợp: đang tải / lỗi / chưa có dữ liệu /
        không có kết quả; còn lại thì ẩn lớp phủ.

        total: tổng số job đã nạp, shown: số job còn lại sau lọc.
        """
        if loading:
            self._overlay.show("Đang tải dữ liệu...", loading=True)
        elif error and not total:
            self._overlay.show(f"Không tải được dữ liệu.\n{error}")
        elif not total:
            self._overlay.show(
                "Chưa có dữ liệu.\nBấm Crawl để thu thập việc làm."
            )
        elif not shown:
            # Chừa lại hàng tiêu đề (cùng icon lọc) để còn bỏ lọc từng cột.
            self._overlay.show(
                "Không tìm thấy kết quả phù hợp.",
                show_action=True,
                top_offset=self._header_height()
            )
        else:
            self._overlay.hide()

    def matches_filters(self, job):
        return self._filters.matches(job)

    def sort_jobs(self, jobs):
        return self._sort.sort(jobs)

    def prune_filters(self):
        """Bỏ các lựa chọn lọc không còn tồn tại trong dữ liệu mới."""
        self._filters.prune()

    def clear_filters(self):
        self._filters.clear()

    def close_popups(self):
        self._filters.close_popup()

    # ------------------------------------------------------------------
    # Dựng UI
    # ------------------------------------------------------------------

    def _configure_styles(self):
        t = self.theme
        style = ttk.Style()

        style.configure(
            self.TREE_STYLE,
            background=t.white,
            foreground=t.text_primary,
            fieldbackground=t.white,
            borderwidth=0,
            relief="flat",
            rowheight=self.MIN_ROW_HEIGHT,
            font=("Segoe UI", 10)
        )

        style.configure(
            f"{self.TREE_STYLE}.Heading",
            background=t.white,
            foreground=t.text_secondary,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI Semibold", 9)
        )

        style.map(
            self.TREE_STYLE,
            background=[("selected", t.selected)],
            foreground=[("selected", t.text_primary)]
        )

        style.configure(
            "Vertical.TScrollbar",
            background="#D1D5DB",
            troughcolor="#F9FAFB",
            borderwidth=0,
            arrowsize=12
        )

    def _build_tree(self):
        self._tree = ttk.Treeview(
            self,
            columns=COLUMN_KEYS,
            show="headings",
            selectmode="browse",
            style=self.TREE_STYLE
        )

        self._tree.grid(row=0, column=0, sticky="nsew")

        for column in COLUMNS:
            self._tree.heading(column.key, text=column.heading, anchor="w")
            self._tree.column(
                column.key,
                width=column.width,
                minwidth=column.minwidth,
                stretch=column.stretch,
                anchor="w"
            )

        # Re-wrap khi kéo cột hoặc resize cửa sổ
        self._tree.bind("<Configure>", self._schedule_rewrap, add="+")
        self._tree.bind("<ButtonRelease-1>", self._schedule_rewrap, add="+")

    def _build_scrollbar(self):
        self._scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self._tree.yview,
            style="Vertical.TScrollbar"
        )

        self._scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
            padx=(3, 0)
        )

        self._tree.configure(yscrollcommand=self._on_tree_yscroll)

    def _build_header_tools(self):
        """Icon lọc + icon sort trên header và các thao tác click heading."""
        t = self.theme
        root = self.winfo_toplevel()

        # Toàn bộ logic lọc (icon, popup Text/Date/Checklist, trạng thái,
        # kiểm tra khớp) nằm ở ui/components/filters.py
        self._filters = FilterManager(
            root,
            self._tree,
            columns=self.FILTER_COLUMNS,
            text_columns=self.TEXT_COLUMNS,
            checklist_columns=self.CHECKLIST_COLUMNS,
            date_columns=self.DATE_COLUMNS,
            sort_columns=self.SORT_COLUMNS,
            get_jobs=self._get_jobs,
            on_change=self._on_filter_change,
            theme=FilterTheme(
                white=t.white,
                border=t.border,
                text_primary=t.text_primary,
                text_secondary=t.text_secondary,
                text_muted=t.text_muted,
                hover_bg=t.hover_bg,
                active=t.active,
            ),
            icon_width=self.ICON_WIDTH,
            default_header_height=self.DEFAULT_HEADER_HEIGHT,
        )

        # Click heading: cột sort -> đổi sort; cột còn lại -> mở popup lọc
        for key in dict.fromkeys(self.FILTER_COLUMNS + self.SORT_COLUMNS):
            self._tree.heading(
                key,
                anchor="w",
                command=lambda k=key: self._on_heading_click(k)
            )

        # Toàn bộ logic sort (icon, trạng thái, parse lương, sắp xếp)
        # nằm ở ui/components/sort.py
        self._sort = SortManager(
            self._tree,
            columns=self.SORT_COLUMNS,
            default=self.SORT_DEFAULT,
            date_columns=self.DATE_COLUMNS,
            on_change=self._on_filter_change,
            theme=SortTheme(
                white=t.white,
                text_muted=t.text_muted,
                hover_bg=t.hover_bg,
                active=t.active,
            ),
            icon_width=self.ICON_WIDTH,
            default_header_height=self.DEFAULT_HEADER_HEIGHT,
            before_change=self._filters.close_popup,
            # Icon sort nằm bên trái icon lọc (cột không có lọc thì sát mép phải)
            slots_for=lambda key: 1 if self._filters.has_icon(key) else 0,
        )

        # Icon luôn bám theo mép phải của cột khi kéo cột / resize
        for sequence in ("<Configure>", "<B1-Motion>", "<ButtonRelease-1>"):
            self._tree.bind(sequence, self._position_header_icons, add="+")

        # Cửa sổ hẹp: thu các cột stretch để cột Posted At / Expire Date
        # (và icon lọc của chúng) không bị cắt khỏi khung nhìn
        self._tree.bind("<Configure>", self._schedule_fit_columns, add="+")

        # Click ra ngoài / di chuyển cửa sổ -> đóng popup / menu
        root.bind("<Button-1>", self._on_root_click, add="+")
        root.bind("<Configure>", self._filters.on_root_configure, add="+")

        self._position_header_icons()

    def _build_events(self):
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Chuột phải vào dòng -> context menu (mở link gốc / sao chép link)
        right_buttons = ["<Button-3>"]

        # macOS: chuột phải là Button-2 (hoặc Ctrl + click)
        if self.tk.call("tk", "windowingsystem") == "aqua":
            right_buttons += ["<Button-2>", "<Control-Button-1>"]

        for sequence in right_buttons:
            self._tree.bind(sequence, self._on_row_right_click)

        # Cuộn chuột -> đóng menu (click ra ngoài đã xử lý ở _on_root_click)
        root = self.winfo_toplevel()

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            root.bind(sequence, self._close_row_menu, add="+")

    def _build_state_overlay(self):
        t = self.theme

        self._overlay = StateOverlay(
            self,
            theme=StateOverlayTheme(
                white=t.white,
                text_secondary=t.text_secondary,
                border=t.border,
                primary=t.primary,
                action_bg=t.hover_bg,
                action_hover=t.border,
                action_text="#374151",
            ),
            action_text="Xóa tìm kiếm & bộ lọc",
            on_action=self._on_clear_filters
        )

    # ------------------------------------------------------------------
    # Thanh cuộn tự ẩn
    # ------------------------------------------------------------------

    def _on_tree_yscroll(self, first, last):
        """Cập nhật thanh cuộn và ẩn hẳn khi không có gì để cuộn
        (danh sách rỗng hoặc toàn bộ dòng đã vừa khung nhìn)."""
        self._scrollbar.set(first, last)

        needs_scroll = float(first) > 0.0 or float(last) < 1.0
        is_shown = bool(self._scrollbar.winfo_manager())

        if needs_scroll and not is_shown:
            self._scrollbar.grid()
        elif not needs_scroll and is_shown:
            self._scrollbar.grid_remove()

    # ------------------------------------------------------------------
    # Chọn dòng
    # ------------------------------------------------------------------

    def _on_tree_select(self, event=None):
        selection = self._tree.selection()

        if not selection:
            return

        job = self._rows_by_id.get(selection[0])

        if job:
            self._on_select(job)

    # ------------------------------------------------------------------
    # Word wrap (Treeview không hỗ trợ sẵn -> tự ngắt dòng bằng \n)
    # ------------------------------------------------------------------

    def _row_values(self, job):
        wrapped, max_lines = {}, 1

        for key in self.WRAP_COLUMNS:
            width = int(self._tree.column(key, "width")) - self.CELL_PADDING
            wrapped[key], lines = wrap_text(
                cell_text(job, key), width, self._row_font
            )
            max_lines = max(max_lines, lines)

        values = tuple(
            wrapped[key] if key in wrapped else cell_text(job, key)
            for key in COLUMN_KEYS
        )

        return values, max_lines

    def _set_row_height(self, max_lines):
        line_h = self._row_font.metrics("linespace")
        height = max(self.MIN_ROW_HEIGHT, line_h * max_lines + 12)

        if height != self._row_height:
            self._row_height = height
            ttk.Style().configure(self.TREE_STYLE, rowheight=height)

    def _apply_wrap(self):
        self._wrap_after_id = None
        max_lines = 1

        for job in self._rows:
            if not self._tree.exists(job["id"]):
                continue

            values, lines = self._row_values(job)
            self._tree.item(job["id"], values=values)
            max_lines = max(max_lines, lines)

        self._set_row_height(max_lines)

    def _schedule_rewrap(self, event=None):
        # Debounce để không wrap liên tục khi đang kéo
        if self._wrap_after_id:
            self.after_cancel(self._wrap_after_id)

        self._wrap_after_id = self.after(
            self.REWRAP_DELAY_MS, self._apply_wrap
        )

    # ------------------------------------------------------------------
    # Header: vị trí icon, vừa cột, click heading
    # ------------------------------------------------------------------

    def _header_height(self):
        """Chiều cao hàng tiêu đề (dùng cho overlay + icon)."""
        return measure_header_height(self._tree, self.DEFAULT_HEADER_HEIGHT)

    def _position_header_icons(self, event=None):
        self._filters.position_icons()
        self._sort.position_icons()

    def _schedule_fit_columns(self, event=None):
        if self._fit_after_id:
            self.after_cancel(self._fit_after_id)

        self._fit_after_id = self.after(
            self.FIT_DELAY_MS, self._fit_columns
        )

    def _fit_columns(self):
        """Treeview không tự thu nhỏ cột khi khung hẹp lại -> thu các cột
        stretch (không thấp hơn minwidth) cho vừa khung."""
        self._fit_after_id = None

        available = self._tree.winfo_width()

        if available <= 1:
            return

        names = self._tree["columns"]
        widths = {n: int(self._tree.column(n, "width")) for n in names}
        excess = sum(widths.values()) - available

        room = {
            n: widths[n] - int(self._tree.column(n, "minwidth"))
            for n in names
            if str(self._tree.column(n, "stretch")).lower() in ("1", "true")
        }

        room = {n: r for n, r in room.items() if r > 0}
        capacity = sum(room.values())

        if excess <= 0 or capacity <= 0:
            return

        cut = min(excess, capacity)

        for name, available_room in room.items():
            share = math.ceil(cut * available_room / capacity)
            self._tree.column(
                name,
                width=widths[name] - min(share, available_room)
            )

        self._position_header_icons()
        self._schedule_rewrap()

    def _on_heading_click(self, key):
        if key in self._sort.columns:
            self._sort.toggle(key)
        else:
            self._filters.toggle_popup(key)

    def _on_root_click(self, event):
        self._close_row_menu()
        self._filters.on_root_click(event)

    # ------------------------------------------------------------------
    # Context menu (chuột phải vào dòng)
    # ------------------------------------------------------------------

    def _on_row_right_click(self, event):
        self._close_row_menu()

        item_id = self._tree.identify_row(event.y)

        if not item_id:
            return "break"

        # Tự chọn dòng được click chuột phải
        self._tree.selection_set(item_id)
        self._tree.focus(item_id)

        job = self._rows_by_id.get(item_id)
        url = ((job or {}).get("url") or "").strip()
        state = "normal" if url else "disabled"

        t = self.theme

        menu = tk.Menu(
            self.winfo_toplevel(),
            tearoff=0,
            font=("Segoe UI", 10),
            bg=t.white,
            fg=t.text_primary,
            activebackground=t.selected,
            activeforeground=t.text_primary,
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
        menu = self._row_menu

        if menu is None:
            return

        self._row_menu = None

        try:
            menu.unpost()
            menu.destroy()
        except tk.TclError:
            pass

    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
