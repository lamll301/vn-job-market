"""Lớp phủ trạng thái (đang tải / chưa có dữ liệu / lỗi / không có kết quả).

Phủ lên toàn bộ parent (hoặc chỉ phần body, chừa lại `top_offset` px phía trên
để giữ hàng tiêu đề của bảng). Chỉ lo phần hiển thị: việc chọn thông điệp nào
là của caller.

    overlay = StateOverlay(parent, theme=StateOverlayTheme(...),
                           action_text="Xóa bộ lọc", on_action=callback)
    overlay.show("Đang tải...", loading=True)
    overlay.show("Không có kết quả", show_action=True, top_offset=26)
    overlay.hide()
"""

import tkinter as tk
from dataclasses import dataclass

import customtkinter as ctk


@dataclass(frozen=True)
class StateOverlayTheme:
    """Màu dùng cho lớp phủ (truyền từ MainWindow vào)."""

    white: str
    text_secondary: str
    border: str
    primary: str
    action_bg: str
    action_hover: str
    action_text: str


class StateOverlay(ctk.CTkFrame):
    def __init__(self, parent, *, theme, action_text, on_action):
        super().__init__(
            parent,
            fg_color=theme.white,
            corner_radius=0
        )

        inner = ctk.CTkFrame(
            self,
            fg_color=theme.white,
            corner_radius=0
        )

        inner.place(
            relx=0.5,
            rely=0.45,
            anchor="center"
        )

        self._label = ctk.CTkLabel(
            inner,
            text="",
            text_color=theme.text_secondary,
            font=("Segoe UI", 11),
            justify="center",
            wraplength=420
        )

        self._label.pack()

        self._progress = ctk.CTkProgressBar(
            inner,
            mode="indeterminate",
            width=220,
            height=6,
            fg_color=theme.border,
            progress_color=theme.primary
        )

        # Nút hành động (vd. "Xóa tìm kiếm & bộ lọc" ở trạng thái không có kết quả)
        self._action = ctk.CTkButton(
            inner,
            text=action_text,
            width=170,
            height=32,
            corner_radius=7,
            fg_color=theme.action_bg,
            hover_color=theme.action_hover,
            text_color=theme.action_text,
            font=("Segoe UI", 10),
            command=on_action
        )

    def show(self, message, *, loading=False, show_action=False,
             top_offset=0):
        """Hiện lớp phủ.

        loading    : hiện thanh tiến trình chạy liên tục.
        show_action: hiện nút hành động dưới thông điệp.
        top_offset : chừa lại bao nhiêu px phía trên (vd. chiều cao header).
        """
        self._label.configure(text=message)

        if loading:
            self._progress.pack(pady=(12, 0))
            self._progress.start()
        else:
            self._progress.stop()
            self._progress.pack_forget()

        if show_action:
            self._action.pack(pady=(14, 0))
        else:
            self._action.pack_forget()

        # CTkFrame.place() cấm truyền height -> gọi place gốc của tkinter
        # (relheight=1 + height âm = cao bằng khung trừ phần chừa lại).
        tk.Place.place_configure(
            self,
            x=0,
            y=top_offset,
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
            height=-top_offset
        )

    def hide(self):
        self._progress.stop()
        self.place_forget()
