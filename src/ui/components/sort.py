"""Logic sắp xếp theo cột header của bảng việc làm.

MainWindow chỉ cần dùng SortManager: icon ⇅ / ▲ / ▼ trên header, trạng thái
sort (tăng dần -> giảm dần -> mặc định) và sort(jobs).
"""

import re
import tkinter as tk
from dataclasses import dataclass

from .filters import column_left, measure_header_height, normalize_text

USD_TO_VND = 25000                      # chỉ để so sánh lương USD / VND
SALARY_UNITS = {
    "trieu": 1e6, "tr": 1e6, "m": 1e6,
    "nghin": 1e3, "ngan": 1e3, "k": 1e3,
    "ty": 1e9, "ti": 1e9, "b": 1e9,
}


@dataclass(frozen=True)
class SortTheme:
    """Màu dùng cho icon sort (truyền từ MainWindow vào)."""

    white: str
    text_muted: str
    hover_bg: str
    active: str          # màu nhấn: cột đang được sort


def parse_salary(text):
    """'14 triệu - 18 triệu' -> (14e6, 18e6) VND; 'Thương lượng' -> None."""
    text = normalize_text(text)
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
            value *= SALARY_UNITS[unit]
        elif not is_usd and value < 1000:
            value *= 1e6          # '15 - 20' -> hiểu là triệu

        if is_usd:
            value *= USD_TO_VND

        amounts.append(value)

    return (min(amounts), max(amounts))


class SortManager:
    """Quản lý sort theo cột của một ttk.Treeview.

    columns          các cột có icon sort (click heading cũng đổi sort)
    default          (cột, "asc"|"desc") khi chưa ai bấm / sau lần bấm thứ 3
    date_columns     {cột: khoá datetime gốc trong job}; cột ngày sort theo mốc này
    on_change        callable không tham số, gọi sau khi sort đổi (làm mới bảng)
    before_change    callable không tham số, gọi ngay trước khi đổi sort
                     (vd. đóng popup lọc đang mở)
    slots_for        callable(cột) -> số ô icon bên phải đã bị chiếm (icon lọc);
                     icon sort đặt bên trái các ô đó
    """

    IDLE = "⇅"
    ASC = "▲"
    DESC = "▼"

    def __init__(
        self,
        tree,
        *,
        columns,
        default,
        date_columns,
        on_change,
        theme,
        icon_width,
        default_header_height,
        before_change=None,
        slots_for=None
    ):
        self.tree = tree
        self.columns = tuple(columns)
        self.default = default
        self.date_columns = dict(date_columns)

        self._on_change = on_change
        self._before_change = before_change
        self._slots_for = slots_for or (lambda key: 0)
        self.theme = theme
        self.icon_width = icon_width
        self.default_header_height = default_header_height

        # None = mặc định (self.default); ngược lại (cột, "asc"|"desc")
        self.state = None

        self.icons = {}

        self._build_icons()
        self.update_icons()

    # ------------------------------------------------------------------
    # Icon trên header
    # ------------------------------------------------------------------

    def _build_icons(self):
        t = self.theme

        for key in self.columns:
            icon = tk.Label(
                self.tree,
                text=self.IDLE,
                bg=t.white,
                fg=t.text_muted,
                font=("Segoe UI Symbol", 9),
                cursor="hand2"
            )

            icon.bind(
                "<Button-1>",
                lambda e, k=key: self.toggle(k)
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

    def position_icons(self):
        """Đặt icon sát mép phải của cột, bên trái icon lọc (nếu có)."""
        header_h = measure_header_height(
            self.tree, self.default_header_height
        )

        for key, icon in self.icons.items():
            right = column_left(self.tree, key) + int(
                self.tree.column(key, "width")
            )
            slots = self._slots_for(key) + 1

            icon.place(
                x=right - self.icon_width * slots - 2,
                y=1,
                width=self.icon_width,
                height=header_h - 2
            )

    def update_icons(self):
        active_key, direction = self.effective

        for key, icon in self.icons.items():
            if key != active_key:
                icon.configure(text=self.IDLE, fg=self.theme.text_muted)
            else:
                icon.configure(
                    text=self.ASC if direction == "asc" else self.DESC,
                    fg=self.theme.active
                )

    # ------------------------------------------------------------------
    # Trạng thái
    # ------------------------------------------------------------------

    @property
    def effective(self):
        return self.state or self.default

    def toggle(self, key):
        """Tăng dần -> giảm dần -> mặc định."""
        if self._before_change:
            self._before_change()

        state = self.state

        if state is None or state[0] != key:
            self.state = (key, "asc")
        elif state[1] == "asc":
            self.state = (key, "desc")
        else:
            self.state = None

        self.update_icons()
        self._on_change()

    # ------------------------------------------------------------------
    # Sắp xếp
    # ------------------------------------------------------------------

    def _value(self, job, key):
        """Giá trị so sánh của một dòng; None = thiếu dữ liệu (luôn xếp cuối)."""
        if key in self.date_columns:
            value = job.get(self.date_columns[key])

            try:
                return value.timestamp() if value else None
            except (AttributeError, OverflowError, OSError, ValueError):
                return None

        if key == "salary":
            return parse_salary(job.get("salary"))

        return normalize_text(job.get(key)) or None

    def sort(self, jobs):
        key, direction = self.effective

        keyed, missing = [], []

        for job in jobs:
            value = self._value(job, key)
            (missing if value is None else keyed).append((value, job))

        keyed.sort(key=lambda pair: pair[0], reverse=(direction == "desc"))

        # Dòng thiếu dữ liệu luôn nằm dưới cùng, dù tăng hay giảm
        return [job for _, job in keyed] + [job for _, job in missing]
