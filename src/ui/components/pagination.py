"""Thanh phân trang ‹ Page [n] of N ›.

MainWindow chỉ cần:

    self.pagination = PaginationBar(
        parent, theme=PaginationTheme(...), page_size=20,
        on_change=self.refresh_table
    )
    self.pagination.grid(...)

    page_items = self.pagination.paginate(all_items)   # trong refresh_table
    self.pagination.reset()                            # khi dữ liệu / bộ lọc đổi

Bấm ‹ / › hoặc nhập số trang rồi Enter -> PaginationBar đổi trang và gọi
on_change(); MainWindow gọi lại paginate() để lấy dữ liệu trang mới.
"""

from dataclasses import dataclass

import customtkinter as ctk


@dataclass(frozen=True)
class PaginationTheme:
    """Màu dùng cho thanh phân trang (truyền từ MainWindow vào)."""

    white: str
    border: str
    text_primary: str
    text_secondary: str
    hover_bg: str


class PaginationBar(ctk.CTkFrame):
    def __init__(self, parent, *, theme, page_size, on_change):
        super().__init__(
            parent,
            fg_color=theme.white,
            corner_radius=0,
            height=50
        )

        self.theme = theme
        self.page_size = page_size
        self._on_change = on_change

        self._page = 1
        self._total_pages = 1

        self._build()
        self._sync()

    # ------------------------------------------------------------------
    # API công khai
    # ------------------------------------------------------------------

    @property
    def page(self):
        return self._page

    @property
    def total_pages(self):
        return self._total_pages

    def reset(self):
        """Về trang 1 (không gọi on_change; caller tự refresh)."""
        self._page = 1

    def paginate(self, items):
        """Cập nhật tổng số trang theo `items`, kẹp trang hiện tại vào
        [1, total_pages], làm mới UI và trả về các phần tử của trang đó."""
        self._total_pages = max(
            1,
            (len(items) + self.page_size - 1) // self.page_size
        )

        self._page = min(self._page, self._total_pages)

        start = (self._page - 1) * self.page_size

        self._sync()

        return items[start:start + self.page_size]

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build(self):
        t = self.theme

        # col 0 / col 4 giãn ra để cụm giữa luôn nằm chính giữa
        for column, weight in enumerate((1, 0, 0, 0, 1)):
            self.grid_columnconfigure(column, weight=weight)

        self.previous_button = self._make_button(
            "‹", self.previous_page
        )
        self.previous_button.grid(
            row=0, column=0, sticky="e", padx=(0, 4), pady=6
        )

        ctk.CTkLabel(
            self,
            text="Page",
            text_color=t.text_secondary,
            font=("Segoe UI", 9)
        ).grid(row=0, column=1, padx=(8, 4), pady=6)

        self.page_entry = ctk.CTkEntry(
            self,
            width=50,
            height=30,
            corner_radius=6,
            border_width=1,
            border_color=t.border,
            fg_color=t.white,
            text_color=t.text_primary,
            justify="center",
            font=("Segoe UI", 9)
        )
        self.page_entry.grid(row=0, column=2, padx=4, pady=6)

        self.page_of_label = ctk.CTkLabel(
            self,
            text="of 1",
            text_color=t.text_secondary,
            font=("Segoe UI", 9)
        )
        self.page_of_label.grid(row=0, column=3, padx=(4, 8), pady=6)

        self.page_entry.bind("<Return>", self.go_to_page)
        self.page_entry.bind("<FocusOut>", self.go_to_page)

        self.next_button = self._make_button("›", self.next_page)
        self.next_button.grid(
            row=0, column=4, sticky="w", padx=(4, 0), pady=6
        )

    def _make_button(self, text, command):
        t = self.theme

        return ctk.CTkButton(
            self,
            text=text,
            width=34,
            height=30,
            corner_radius=6,
            fg_color=t.white,
            hover_color=t.hover_bg,
            text_color=t.text_primary,
            border_width=1,
            border_color=t.border,
            font=("Segoe UI", 15),
            command=command
        )

    def _set_entry(self, value):
        self.page_entry.delete(0, "end")
        self.page_entry.insert(0, str(value))

    def _sync(self):
        """Đồng bộ ô nhập, nhãn 'of N' và trạng thái 2 nút với state."""
        self._set_entry(self._page)

        self.page_of_label.configure(text=f"of {self._total_pages}")

        self.previous_button.configure(
            state="normal" if self._page > 1 else "disabled"
        )
        self.next_button.configure(
            state="normal" if self._page < self._total_pages else "disabled"
        )

    # ------------------------------------------------------------------
    # Điều hướng
    # ------------------------------------------------------------------

    def _go(self, page):
        self._page = page
        self._on_change()

    def previous_page(self):
        if self._page > 1:
            self._go(self._page - 1)

    def next_page(self):
        if self._page < self._total_pages:
            self._go(self._page + 1)

    def go_to_page(self, event=None):
        value = self.page_entry.get().strip()

        try:
            page = int(value)
        except ValueError:                  # rỗng hoặc không phải số
            self._set_entry(self._page)
            return

        # Giới hạn page trong khoảng 1 -> total_pages
        page = max(1, min(page, self._total_pages))

        if page == self._page:
            self._set_entry(self._page)
            return

        self._go(page)
