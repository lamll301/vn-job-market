"""Toàn bộ logic lọc theo cột của bảng việc làm (Text / Date / Checklist).

MainWindow chỉ cần dùng FilterManager (xem cuối file); các popup và hàm
tiện ích bên trên là chi tiết bên trong.
"""

import calendar
import re
import tkinter as tk
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from tkinter import ttk


# ====================================================================
# Hàm thuần (không phụ thuộc Tk): chuẩn hóa chữ, gộp biến thể
# ====================================================================


def normalize_text(text):
    """'  Hà   Nội ' -> 'ha noi' (bỏ dấu, chữ thường, gọn khoảng trắng)."""
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)

    stripped = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )

    return " ".join(stripped.casefold().split())


def split_locations(value):
    """'Hà Nội, Hồ Chí Minh' -> ['Hà Nội', 'Hồ Chí Minh']."""
    return [
        part.strip()
        for part in re.split(r"[,;/|]", value or "")
        if part.strip()
    ]


def matches_query(display, query):
    """Gõ 'Hà' -> khớp đúng dấu; gõ 'ha' (không dấu) -> khớp mọi dấu."""
    if not query:
        return True

    has_accent = (
        normalize_text(query) != " ".join(query.casefold().split())
    )

    if has_accent:
        return query.casefold() in display.casefold()

    return normalize_text(query) in normalize_text(display)


def pick_label(variants):
    """Chọn nhãn đẹp nhất trong các biến thể: có dấu > viết hoa đúng
    kiểu ('Hà Nội') > xuất hiện nhiều nhất."""

    def score(item):
        variant, count = item
        has_accent = (
            normalize_text(variant)
            != " ".join(variant.casefold().split())
        )
        return (has_accent, variant == variant.title(), count)

    return max(variants.items(), key=score)[0]


def group_variants(values, by_count):
    """Gộp các biến thể cùng chuỗi chuẩn hóa thành 1 dòng:
    'Hà Nội' / 'Ha Noi' / 'HA NOI' -> key 'ha noi', nhãn 'Hà Nội'."""
    groups = {}  # key chuẩn hóa -> Counter(các biến thể gốc trong DB)

    for value in values:
        key = normalize_text(value)

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

    return [(key, pick_label(groups[key])) for key in keys]


# ====================================================================
# Đo kích thước header / cột của ttk.Treeview
# ====================================================================


def measure_header_height(tree, default):
    """Chiều cao hàng tiêu đề: quét y đến khi hết vùng 'heading'."""
    for y in range(2, 80):
        if tree.identify_region(5, y) != "heading":
            return y if y >= 12 else default

    return default


def column_left(tree, key):
    """Toạ độ x (trong tree) của mép trái cột `key`."""
    left = 0

    for name in tree["columns"]:
        if name == key:
            break
        left += int(tree.column(name, "width"))

    return left


# ====================================================================
# Màu dùng cho icon lọc và các popup
# ====================================================================


@dataclass(frozen=True)
class FilterTheme:
    """Màu dùng cho icon lọc và các popup (truyền từ MainWindow vào)."""

    white: str
    border: str
    text_primary: str
    text_secondary: str
    text_muted: str
    hover_bg: str
    active: str          # màu nhấn: cột đang lọc, nút Áp dụng, ngày đang chọn


# ====================================================================
# Lớp nền chung của popup lọc
# ====================================================================


class FilterPopup:
    """Khung chung của popup lọc: cửa sổ không viền nằm ngay dưới header cột.

    Lớp con cài đặt:
        build(body)       dựng nội dung
        apply()           nút "Áp dụng" / phím Enter
        focus_initial()   (tuỳ chọn) widget nhận focus khi mở

    Popup không biết gì về MainWindow, chỉ gọi lại:
        on_change(rule)   đặt bộ lọc của cột (rule=None -> bỏ lọc) rồi làm mới bảng
        on_close()        nhờ FilterManager đóng popup này
        anchor()          -> (x, y) toạ độ màn hình của góc dưới-trái ô header
    """

    def __init__(self, *, root, theme, key, rule, anchor, on_change, on_close):
        self.root = root
        self.theme = theme
        self.key = key
        self.rule = rule

        self._anchor = anchor
        self._on_change = on_change
        self._on_close = on_close

        self.window = None
        self._origin = None

    # --- vòng đời --------------------------------------------------------

    def show(self):
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=self.theme.border, padx=1, pady=1)

        body = tk.Frame(window, bg=self.theme.white)
        body.pack(fill="both", expand=True)

        self.window = window

        self.build(body)
        self.place()

        window.after(20, self._focus)

    def close(self):
        if self.window is not None:
            self.window.destroy()
            self.window = None

    # --- cho lớp con ---------------------------------------------------

    def build(self, body):
        raise NotImplementedError

    def apply(self):
        raise NotImplementedError

    def focus_initial(self):
        pass

    def discard_pending(self):
        """Huỷ thao tác đang chờ (vd. lọc debounce) trước khi xoá lọc."""

    def clear(self):
        """Nút "Xóa lọc"."""
        self.discard_pending()
        self._on_close()
        self._on_change(None)

    # --- vị trí ----------------------------------------------------------

    def place(self):
        window = self.window
        window.update_idletasks()

        x, y = self._anchor()

        # Không để popup tràn ra ngoài màn hình
        x = max(0, min(x, window.winfo_screenwidth() - window.winfo_reqwidth() - 8))

        window.geometry(f"+{x}+{y}")
        self._origin = (x, y)

    def refit(self):
        """Ép popup co/giãn lại theo nội dung hiện tại.

        Bỏ kích thước cũ (geometry("")) để Toplevel không giữ chiều cao
        lúc đang mở lịch; chỉ giữ lại vị trí, và đẩy lên nếu tràn đáy
        màn hình."""
        if self.window is None or not self._origin:
            return

        window = self.window
        x, y = self._origin

        window.geometry("")
        window.update_idletasks()

        overflow = y + window.winfo_reqheight() - (
            window.winfo_screenheight() - 48
        )

        if overflow > 0:
            y = max(0, y - overflow)

        window.geometry(f"+{x}+{y}")

    # --- tiện ích dùng chung ---------------------------------------------

    def _focus(self):
        if self.window is None:
            return

        try:
            self.focus_initial()
        except tk.TclError:
            pass

    def _build_buttons(self, parent):
        """Hàng nút [Xóa lọc] [Áp dụng] dùng chung cho mọi popup."""
        t = self.theme

        button_row = tk.Frame(parent, bg=t.white)
        button_row.pack(fill="x", padx=8, pady=8)

        apply_button = tk.Button(
            button_row,
            text="Áp dụng",
            command=self.apply,
            bg=t.active,
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
            command=self.clear,
            bg=t.white,
            fg=t.text_secondary,
            activebackground=t.hover_bg,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=t.border,
            padx=14,
            pady=3,
            font=("Segoe UI", 9),
            cursor="hand2"
        )

        apply_button.pack(side="right")
        clear_button.pack(side="right", padx=(0, 6))

        return apply_button


# ====================================================================
# Popup lọc theo từ khóa (Job Title / Company)
# ====================================================================


TEXT_CONDITIONS = {
    "contains": "Chứa",
    "startswith": "Bắt đầu bằng",
    "endswith": "Kết thúc bằng",
}


def text_matches(value, condition, needle):
    """`needle` đã được normalize_text."""
    value = normalize_text(value)

    if condition == "startswith":
        return value.startswith(needle)

    if condition == "endswith":
        return value.endswith(needle)

    return needle in value


class TextFilterPopup(FilterPopup):
    """Lọc theo từ khóa (Job Title / Company).

    rule: None | (điều kiện, text người dùng gõ, text đã chuẩn hóa)
    """

    DEBOUNCE_MS = 250

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._query = None
        self._condition = None
        self._entry = None
        self._after_id = None

    def build(self, body):
        t = self.theme
        rule = self.rule

        tk.Label(
            body,
            text="Điều kiện",
            bg=t.white,
            fg=t.text_secondary,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=8, pady=(8, 2))

        self._condition = tk.StringVar(
            value=TEXT_CONDITIONS[rule[0] if rule else "contains"]
        )

        combo = ttk.Combobox(
            body,
            textvariable=self._condition,
            values=list(TEXT_CONDITIONS.values()),
            state="readonly",
            font=("Segoe UI", 10)
        )

        combo.pack(fill="x", padx=8)

        tk.Label(
            body,
            text="Nhập từ khóa tìm kiếm...",
            bg=t.white,
            fg=t.text_secondary,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=8, pady=(8, 2))

        self._query = tk.StringVar(value=rule[1] if rule else "")

        entry = tk.Entry(
            body,
            textvariable=self._query,
            width=32,
            font=("Segoe UI", 10),
            relief="flat",
            bg=t.white,
            fg=t.text_primary,
            insertbackground=t.text_primary,
            highlightthickness=1,
            highlightbackground=t.border,
            highlightcolor=t.active
        )

        entry.pack(fill="x", padx=8, ipady=3)

        self._entry = entry

        self._build_buttons(body)

        # Gõ đến đâu bảng lọc đến đó (debounce để không giật)
        self._query.trace_add("write", lambda *_: self._schedule())
        combo.bind("<<ComboboxSelected>>", lambda e: self._schedule())

        for widget in (entry, combo):
            widget.bind("<Escape>", lambda e: self._on_close())
            widget.bind("<Return>", lambda e: self.apply())

    def focus_initial(self):
        self._entry.focus_force()
        self._entry.select_range(0, "end")

    # --- lọc -------------------------------------------------------------

    def _schedule(self):
        if self._after_id:
            self.root.after_cancel(self._after_id)

        self._after_id = self.root.after(self.DEBOUNCE_MS, self._commit)

    def discard_pending(self):
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None

    def _commit(self):
        self.discard_pending()

        text = self._query.get().strip()
        needle = normalize_text(text)
        label = self._condition.get()

        condition = next(
            (k for k, v in TEXT_CONDITIONS.items() if v == label),
            "contains"
        )

        # Ô trống = không lọc
        self._on_change((condition, text, needle) if needle else None)

    def apply(self):
        self._commit()
        self._on_close()

    def close(self):
        # Đóng khi còn lần gõ chưa kịp lọc -> lọc nốt
        if self._after_id:
            self._commit()

        super().close()


# ====================================================================
# Popup checklist kiểu Excel (Location / Source)
# ====================================================================


class ChecklistFilterPopup(FilterPopup):
    """Popup checklist kiểu Excel (Location / Source).

    options: [(key_chuẩn_hóa, nhãn_hiển_thị)]
    rule   : None (không lọc) | set các key chuẩn hóa được chọn
    """

    def __init__(self, *, options, **kwargs):
        super().__init__(**kwargs)

        self.options = options
        self.checked = (
            {k for k, _ in options}
            if self.rule is None
            else set(self.rule)
        )
        self.visible = []

        self._query = None
        self._listbox = None
        self._apply_button = None
        self._search_entry = None

    def build(self, body):
        t = self.theme

        # Ô tìm kiếm trong popup
        search_row = tk.Frame(body, bg=t.white)
        search_row.pack(fill="x", padx=8, pady=(8, 6))

        tk.Label(
            search_row,
            text="Tìm kiếm",
            bg=t.white,
            fg=t.text_secondary,
            font=("Segoe UI", 9)
        ).pack(side="left", padx=(0, 6))

        self._query = tk.StringVar()

        entry = tk.Entry(
            search_row,
            textvariable=self._query,
            font=("Segoe UI", 10),
            relief="flat",
            bg=t.white,
            fg=t.text_primary,
            insertbackground=t.text_primary,
            highlightthickness=1,
            highlightbackground=t.border,
            highlightcolor=t.active
        )

        entry.pack(side="left", fill="x", expand=True, ipady=3)

        self._search_entry = entry

        # Danh sách checkbox (Listbox: cuộn mượt kể cả khi có hàng trăm mục)
        list_row = tk.Frame(body, bg=t.white)
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
            bg=t.white,
            fg=t.text_primary,
            selectbackground=t.white,
            selectforeground=t.text_primary,
            yscrollcommand=scrollbar.set
        )

        scrollbar.configure(command=listbox.yview)
        scrollbar.pack(side="right", fill="y")
        listbox.pack(side="left", fill="both", expand=True)

        self._listbox = listbox
        self._apply_button = self._build_buttons(body)

        self._query.trace_add("write", lambda *_: self._render())
        listbox.bind("<Button-1>", self._on_click)

        for widget in (entry, listbox):
            widget.bind("<Escape>", lambda e: self._on_close())
            widget.bind("<Return>", lambda e: self.apply())

        self._render()

    def focus_initial(self):
        self._search_entry.focus_force()

    # --- danh sách -----------------------------------------------------

    @staticmethod
    def _box(is_checked):
        return "☑" if is_checked else "☐"

    def _render(self):
        query = self._query.get().strip()

        self.visible = [
            (k, display)
            for k, display in self.options
            if matches_query(display, query)
        ]

        listbox = self._listbox
        top = listbox.yview()[0]

        all_checked = bool(self.visible) and all(
            k in self.checked for k, _ in self.visible
        )

        listbox.delete(0, "end")
        listbox.insert("end", f"{self._box(all_checked)}  Chọn tất cả")

        for k, display in self.visible:
            listbox.insert(
                "end",
                f"{self._box(k in self.checked)}  {display}"
            )

        listbox.yview_moveto(top)

        # Không chọn mục nào thì không cho Áp dụng
        self._apply_button.configure(
            state="normal" if self.checked else "disabled"
        )

    def _on_click(self, event):
        listbox = self._listbox

        index = listbox.nearest(event.y)
        bbox = listbox.bbox(index) if index >= 0 else None

        # Click vào vùng trống bên dưới mục cuối thì bỏ qua
        if not bbox or event.y > bbox[1] + bbox[3]:
            return "break"

        visible_keys = {k for k, _ in self.visible}

        if index == 0:
            # "Chọn tất cả" tác động lên các mục đang hiển thị (đã lọc)
            if visible_keys <= self.checked:
                self.checked -= visible_keys
            else:
                self.checked |= visible_keys
        else:
            k = self.visible[index - 1][0]
            self.checked ^= {k}

        self._render()

        return "break"

    # --- áp dụng ---------------------------------------------------------

    def apply(self):
        if not self.checked:
            return

        all_keys = {k for k, _ in self.options}
        checked = self.checked & all_keys

        self._on_close()

        # Chọn đủ tất cả = không lọc
        self._on_change(None if checked == all_keys else checked)


# ====================================================================
# Popup lọc theo khoảng ngày (Posted At / Expire Date)
# ====================================================================


# Cột ngày hết hạn thường nằm ở tương lai -> thêm mốc "tới" trong chọn nhanh
UPCOMING_COLUMNS = ("expire_date",)


def parse_date(text):
    """'04/10/2026' -> date; để trống -> None; sai định dạng -> ValueError."""
    text = (text or "").strip()

    if not text:
        return None

    return datetime.strptime(text, "%d/%m/%Y").date()


def format_date(value):
    return value.strftime("%d/%m/%Y") if value else ""


def date_in_range(value, start, end):
    """Mốc `value` (datetime) có nằm trong [start, end] (tính theo ngày)?"""
    if not isinstance(value, datetime):
        return False  # job không có ngày thì loại khi đang lọc

    day = value.date()

    return (start is None or day >= start) and (end is None or day <= end)


def date_presets(key):
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

    if key in UPCOMING_COLUMNS:
        presets[4:4] = [
            ("7 ngày tới", today, today + timedelta(days=6)),
            ("30 ngày tới", today, today + timedelta(days=29)),
        ]

    return presets


def build_calendar(parent, theme, shown, selected, on_pick):
    """Lịch tháng gọn: ‹ Tháng m/yyyy › + lưới ngày (T2 -> CN)."""
    frame = tk.Frame(
        parent,
        bg=theme.white,
        highlightthickness=1,
        highlightbackground=theme.border
    )

    state = {"year": shown.year, "month": shown.month}

    header = tk.Frame(frame, bg=theme.white)
    header.pack(fill="x", padx=4, pady=4)

    title = tk.Label(
        header,
        bg=theme.white,
        fg=theme.text_primary,
        font=("Segoe UI Semibold", 10)
    )

    grid = tk.Frame(frame, bg=theme.white)
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
                bg=theme.white,
                fg=theme.text_muted,
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
                    bg, fg = theme.active, "#FFFFFF"
                elif value == today:
                    bg, fg = "#DBEAFE", theme.text_primary
                else:
                    bg, fg = theme.white, theme.text_primary

                tk.Button(
                    grid,
                    text=str(day),
                    width=3,
                    relief="flat",
                    bd=0,
                    bg=bg,
                    fg=fg,
                    activebackground=theme.hover_bg,
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
            bg=theme.white,
            fg=theme.text_secondary,
            activebackground=theme.hover_bg,
            font=("Segoe UI", 10),
            cursor="hand2",
            command=lambda d=delta: shift(d)
        ).pack(side=side)

    title.pack(side="left", expand=True, fill="x")

    render()

    return frame


class DateFilterPopup(FilterPopup):
    """Lọc theo khoảng ngày (Posted At / Expire Date).

    rule: None | (từ ngày | None, đến ngày | None)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        rule = self.rule

        self._vars = {
            "from": tk.StringVar(value=format_date(rule[0]) if rule else ""),
            "to": tk.StringVar(value=format_date(rule[1]) if rule else ""),
        }
        self._holders = {}
        self._error = None
        self._first_entry = None

    def build(self, body):
        t = self.theme

        # --- Chọn nhanh ---
        tk.Label(
            body,
            text="Chọn nhanh",
            bg=t.white,
            fg=t.text_secondary,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=8, pady=(8, 2))

        preset_frame = tk.Frame(body, bg=t.white)
        preset_frame.pack(fill="x", padx=6)

        for index, (label, start, end) in enumerate(date_presets(self.key)):
            tk.Button(
                preset_frame,
                text=label,
                command=lambda s=start, e=end: self._apply_preset(s, e),
                bg=t.white,
                fg=t.text_primary,
                activebackground=t.hover_bg,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=t.border,
                padx=8,
                pady=3,
                font=("Segoe UI", 9),
                cursor="hand2"
            ).grid(row=index // 3, column=index % 3, sticky="ew", padx=2, pady=2)

        for col in range(3):
            preset_frame.grid_columnconfigure(col, weight=1, uniform="preset")

        tk.Frame(body, height=1, bg=t.border).pack(fill="x", padx=8, pady=8)

        # --- Từ ngày / Đến ngày ---
        entries = []

        for name, label in (("from", "Từ ngày"), ("to", "Đến ngày")):
            tk.Label(
                body,
                text=f"{label} (dd/mm/yyyy)",
                bg=t.white,
                fg=t.text_secondary,
                font=("Segoe UI", 9)
            ).pack(anchor="w", padx=8, pady=(0, 2))

            row = tk.Frame(body, bg=t.white)
            row.pack(fill="x", padx=8, pady=(0, 6))

            entry = tk.Entry(
                row,
                textvariable=self._vars[name],
                width=14,
                font=("Segoe UI", 10),
                relief="flat",
                bg=t.white,
                fg=t.text_primary,
                insertbackground=t.text_primary,
                highlightthickness=1,
                highlightbackground=t.border,
                highlightcolor=t.active
            )

            entry.pack(side="left", ipady=3)
            entries.append(entry)

            tk.Button(
                row,
                text="▦",
                command=lambda n=name: self._toggle_calendar(n),
                bg=t.white,
                fg=t.active,
                activebackground=t.hover_bg,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=t.border,
                padx=6,
                font=("Segoe UI Symbol", 10),
                cursor="hand2"
            ).pack(side="left", padx=(6, 0))

            holder = tk.Frame(body, bg=t.white)
            holder.pack(fill="x", padx=8)
            self._holders[name] = holder

        self._error = tk.Label(
            body,
            text="",
            bg=t.white,
            fg="#DC2626",
            font=("Segoe UI", 9)
        )

        self._error.pack(anchor="w", padx=8)

        self._build_buttons(body)

        for entry in entries:
            entry.bind("<Escape>", lambda e: self._on_close())
            entry.bind("<Return>", lambda e: self.apply())

        self._first_entry = entries[0]

    def focus_initial(self):
        self._first_entry.focus_force()

    # --- lịch ----------------------------------------------------------

    @staticmethod
    def _clear_holder(holder):
        """Xóa lịch và thu khung chứa về cỡ tối thiểu.

        Tk giữ nguyên cỡ cũ của một frame khi mọi widget con bị xóa,
        nên phải đặt lại width/height thì khoảng trống mới biến mất."""
        for child in holder.winfo_children():
            child.destroy()

        holder.configure(width=1, height=1)

    def _toggle_calendar(self, which):
        for name, holder in self._holders.items():
            was_open = bool(holder.winfo_children())

            self._clear_holder(holder)

            if name != which or was_open:
                continue

            try:
                current = parse_date(self._vars[name].get())
            except ValueError:
                current = None

            build_calendar(
                holder,
                self.theme,
                shown=current or date.today(),
                selected=current,
                on_pick=lambda d, n=name: self._pick_date(n, d)
            ).pack(anchor="w", pady=(0, 6))

        self.refit()

    def _pick_date(self, which, picked):
        self._vars[which].set(format_date(picked))
        self._error.configure(text="")

        self._clear_holder(self._holders[which])

        self.refit()

    # --- áp dụng ---------------------------------------------------------

    def _apply_preset(self, start, end):
        self._vars["from"].set(format_date(start))
        self._vars["to"].set(format_date(end))

        self.apply()

    def apply(self):
        try:
            start = parse_date(self._vars["from"].get())
            end = parse_date(self._vars["to"].get())
        except ValueError:
            self._error.configure(text="Ngày không hợp lệ, nhập dd/mm/yyyy")
            return

        if start and end and start > end:
            self._error.configure(text="'Từ ngày' phải trước 'Đến ngày'")
            return

        self._on_close()

        # Cả hai trống = không lọc
        self._on_change((start, end) if (start or end) else None)


# ====================================================================
# FilterManager: icon header + trạng thái + popup + matches()
# ====================================================================


class FilterManager:
    """Quản lý lọc theo cột của một ttk.Treeview.

    Gồm: icon lọc trên header, popup (text / date / checklist), trạng thái
    bộ lọc của từng cột và hàm `matches(job)` để MainWindow lọc danh sách.

    columns            mọi cột có icon lọc
    text_columns       lọc theo từ khóa (popup Text)
    checklist_columns  lọc theo danh sách chọn (popup Checklist)
    date_columns       {cột: khoá datetime gốc trong job} (popup Date)
    sort_columns       cột mà click vào heading là để sort (không mở popup lọc)
    multi_value_columns  cột chứa nhiều giá trị ('Hà Nội, HCM') -> tách ra
                       và xếp theo số lượng trong checklist
    get_jobs           callable trả về list job hiện có (để dựng checklist)
    on_change          callable không tham số, gọi sau khi bộ lọc đổi
    """

    ICON_IDLE = "▾"
    ICON_ACTIVE = "●"   # lọc đang bật (khác ▲▼ của sort)

    def __init__(
        self,
        root,
        tree,
        *,
        columns,
        text_columns,
        checklist_columns,
        date_columns,
        sort_columns,
        get_jobs,
        on_change,
        theme,
        icon_width,
        default_header_height,
        multi_value_columns=("location",)
    ):
        self.root = root
        self.tree = tree
        self.columns = tuple(columns)
        self.text_columns = tuple(text_columns)
        self.checklist_columns = tuple(checklist_columns)
        self.date_columns = dict(date_columns)
        self.sort_columns = tuple(sort_columns)
        self.multi_value_columns = tuple(multi_value_columns)

        self._get_jobs = get_jobs
        self._on_change = on_change
        self.theme = theme
        self.icon_width = icon_width
        self.default_header_height = default_header_height

        # None = không lọc. Checklist: set các key chuẩn hóa được chọn.
        # Text: (điều kiện, text gõ, text chuẩn hóa)
        # Date: (từ ngày | None, đến ngày | None)
        self.rules = {key: None for key in self.columns}

        self.icons = {}
        self._popup = None

        self._build_icons()

    # ------------------------------------------------------------------
    # Icon trên header
    # ------------------------------------------------------------------

    def _build_icons(self):
        t = self.theme

        for key in self.columns:
            icon = tk.Label(
                self.tree,
                text=self.ICON_IDLE,
                bg=t.white,
                fg=t.text_muted,
                font=("Segoe UI Symbol", 9),
                cursor="hand2"
            )

            icon.bind(
                "<Button-1>",
                lambda e, k=key: self.toggle_popup(k)
            )
            icon.bind(
                "<Enter>",
                lambda e, w=icon: w.configure(bg=t.hover_bg)
            )
            icon.bind(
                "<Leave>",
                lambda e, w=icon: w.configure(bg=t.white)
            )

            self.icons[key] = icon

    def has_icon(self, key):
        return key in self.icons

    def position_icons(self):
        """Đặt icon sát mép phải của cột (gọi lại khi kéo cột / resize)."""
        header_h = measure_header_height(
            self.tree, self.default_header_height
        )

        for key, icon in self.icons.items():
            right = column_left(self.tree, key) + int(
                self.tree.column(key, "width")
            )

            icon.place(
                x=right - self.icon_width - 2,
                y=1,
                width=self.icon_width,
                height=header_h - 2
            )

    def _update_icons(self):
        for key, icon in self.icons.items():
            if self.rules[key] is None:
                icon.configure(text=self.ICON_IDLE, fg=self.theme.text_muted)
            else:
                icon.configure(text=self.ICON_ACTIVE, fg=self.theme.active)

    # ------------------------------------------------------------------
    # Popup
    # ------------------------------------------------------------------

    def toggle_popup(self, key):
        if self._popup and self._popup.key == key:
            self.close_popup()
        else:
            self.open_popup(key)

    def open_popup(self, key):
        self.close_popup()

        def anchor():
            return (
                self.tree.winfo_rootx() + column_left(self.tree, key),
                self.tree.winfo_rooty() + measure_header_height(
                    self.tree, self.default_header_height
                ),
            )

        common = dict(
            root=self.root,
            theme=self.theme,
            key=key,
            rule=self.rules[key],
            anchor=anchor,
            on_change=lambda rule, k=key: self._set_rule(k, rule),
            on_close=self.close_popup,
        )

        if key in self.text_columns:
            popup = TextFilterPopup(**common)
        elif key in self.date_columns:
            popup = DateFilterPopup(**common)
        else:
            popup = ChecklistFilterPopup(
                options=self._options(key),
                **common
            )

        self._popup = popup
        popup.show()

    def close_popup(self):
        popup, self._popup = self._popup, None

        if popup:
            popup.close()

    def on_root_click(self, event):
        """Click ra ngoài popup -> đóng."""
        if not self._popup:
            return

        widget = event.widget

        if widget in self.icons.values():
            return  # icon tự toggle

        if widget is self.tree and self.tree.identify_region(
            event.x, event.y
        ) == "heading":
            column = self.tree.identify_column(event.x)  # '#3'
            index = int(column[1:]) - 1 if column else -1
            names = self.tree["columns"]

            if (
                0 <= index < len(names)
                and names[index] in self.columns
                and names[index] not in self.sort_columns
            ):
                return  # heading Location / Source vẫn tự toggle popup lọc

        self.close_popup()

    def on_root_configure(self, event):
        """Di chuyển / resize cửa sổ chính -> đóng popup."""
        if event.widget is self.root:
            self.close_popup()

    # ------------------------------------------------------------------
    # Trạng thái bộ lọc
    # ------------------------------------------------------------------

    def _set_rule(self, key, rule):
        self.rules[key] = rule

        self._update_icons()
        self._on_change()

    def clear(self):
        """Bỏ mọi bộ lọc (không làm mới bảng - người gọi tự làm)."""
        self.close_popup()

        self.rules = {key: None for key in self.columns}

        self._update_icons()

    def prune(self):
        """Sau khi nạp lại dữ liệu: bỏ các lựa chọn không còn tồn tại."""
        for key in self.checklist_columns:
            selected = self.rules[key]

            if selected is None:
                continue

            valid = {k for k, _ in self._options(key)}
            self.rules[key] = (selected & valid) or None

        self._update_icons()

    # ------------------------------------------------------------------
    # Dữ liệu cho checklist + kiểm tra khớp
    # ------------------------------------------------------------------

    def _options(self, key):
        """Danh sách [(key_chuẩn_hóa, nhãn_hiển_thị)] cho popup của cột."""
        jobs = self._get_jobs()

        if key in self.multi_value_columns:
            # Nhiều job nhất đứng đầu (Hà Nội, Hồ Chí Minh, ...)
            values = [
                name
                for job in jobs
                for name in split_locations(job[key])
            ]
            return group_variants(values, by_count=True)

        values = [job[key] for job in jobs if job[key]]
        return group_variants(values, by_count=False)

    def _values(self, job, key):
        if key in self.multi_value_columns:
            return split_locations(job[key])

        return [job[key]]

    def matches(self, job):
        """Job có thỏa mọi bộ lọc theo cột đang bật không?"""
        for key, raw_key in self.date_columns.items():
            rule = self.rules[key]

            if rule is not None and not date_in_range(
                job.get(raw_key), *rule
            ):
                return False

        for key in self.text_columns:
            rule = self.rules[key]

            if rule is not None:
                condition, _, needle = rule

                if not text_matches(job[key], condition, needle):
                    return False

        for key in self.checklist_columns:
            selected = self.rules[key]

            if selected is None:
                continue

            names = {
                normalize_text(name) for name in self._values(job, key)
            }

            if not names & selected:
                return False

        return True
