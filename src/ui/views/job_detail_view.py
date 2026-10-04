"""Khung hiển thị chi tiết JD (cột bên phải của MainWindow).

MainWindow chỉ cần:

    self.detail_view = JobDetailView(parent, theme=JobDetailTheme(...))
    self.detail_view.grid(...)
    self.detail_view.show_job(job)     # job = view model dict
    self.detail_view.clear()           # về trạng thái "chưa chọn tin"
    self.detail_view.selected_job      # job đang hiển thị (hoặc None)
"""

import re
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from html import escape
from tkinter import font as tkfont

import customtkinter as ctk

from .html_text_renderer import HtmlTextRenderer


@dataclass(frozen=True)
class JobDetailTheme:
    """Màu dùng cho khung chi tiết (truyền từ MainWindow vào)."""

    white: str
    jd_bg: str
    border: str
    border_light: str
    text_primary: str
    text_secondary: str
    text_muted: str
    primary: str
    primary_hover: str
    tag_bg: str
    tag_text: str
    salary_color: str


def _fmt_date(value):
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    return "—"


def _fmt_date_range(start, end):
    if not isinstance(start, datetime) and not isinstance(end, datetime):
        return ""

    return f"{_fmt_date(start)} - {_fmt_date(end)}"


def _to_html(content):
    """Nội dung đã là HTML thì giữ nguyên; text thường thì escape + giữ xuống dòng."""

    content = (content or "").strip()

    if not content:
        return ""

    if re.search(r"<[a-zA-Z/][^>]*>", content):
        return content

    return escape(content).replace("\n", "<br>")


class JobDetailView(ctk.CTkFrame):
    """Pure JD viewer: header + Mô tả / Yêu cầu / Quyền lợi / Thông tin khác."""

    DETAIL_PAD_X = 18

    # Cỡ chữ nội dung (hiện cả hai section đều dùng cỡ lớn).
    HTML_FONT_SIZE = 10
    HTML_FONT_SIZE_LARGE = 14

    # Khoảng cách (trên, dưới) mỗi dòng của "Thông tin khác".
    SPEC_LINE_GAP = (6, 8)

    META_ICONS = {
        "company": "🏢",
        "location": "📍",
        "address": "🏠",
        "dates": "📅",
    }

    def __init__(self, parent, *, theme):
        super().__init__(
            parent,
            fg_color=theme.white,
            corner_radius=10,
            border_width=1,
            border_color=theme.border
        )

        self.theme = theme
        self._selected_job = None
        self._wrap_width = 300

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Một thanh cuộn duy nhất cho toàn bộ cột chi tiết.
        #   row 0 = header
        #   row 2-3 = Mô tả      row 4-5 = Yêu cầu
        #   row 6-7 = Quyền lợi  row 8-9 = Thông tin khác
        self.detail_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=theme.white,
            corner_radius=0
        )

        self.detail_scroll.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=2,
            pady=6
        )

        self.detail_scroll.grid_columnconfigure(0, weight=1)

        self._build_html_fonts()
        self._build_header()

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

        self._build_placeholder()

    # ------------------------------------------------------------------
    # API công khai
    # ------------------------------------------------------------------

    @property
    def selected_job(self):
        return self._selected_job

    def show_job(self, job):
        """Hiển thị một job (view model dict)."""
        self._selected_job = job

        self._show_placeholder(False)

        self._render_header(job)
        self._render_specifications(job.get("specifications"))
        self._render_sections(job)
        self._scroll_to_top()

    def clear(self):
        """Về trạng thái chưa chọn tin nào."""
        self._selected_job = None

        self._show_placeholder(True)

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

    def open_selected_url(self):
        url = (
            (self._selected_job or {}).get("url") or ""
        ).strip()

        if url:
            webbrowser.open_new_tab(url)

    # ------------------------------------------------------------------
    # Placeholder khi chưa chọn tin nào
    # ------------------------------------------------------------------

    def _build_placeholder(self):
        t = self.theme

        self.detail_placeholder = ctk.CTkFrame(
            self,
            fg_color=t.white,
            corner_radius=0
        )

        ctk.CTkLabel(
            self.detail_placeholder,
            text="Chọn một tin tuyển dụng bên trái để xem chi tiết",
            text_color=t.text_muted,
            font=("Segoe UI", 12),
            justify="center",
            wraplength=280
        ).place(relx=0.5, rely=0.5, anchor="center")

        self._show_placeholder(True)

    def _show_placeholder(self, visible):
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

    # ------------------------------------------------------------------
    # A. Header (title / salary / meta / source + link)
    # ------------------------------------------------------------------

    def _build_header(self):
        t = self.theme

        header = ctk.CTkFrame(
            self.detail_scroll,
            fg_color=t.white,
            corner_radius=0
        )

        header.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=self.DETAIL_PAD_X,
            pady=(10, 0)
        )

        header.grid_columnconfigure(0, weight=1)

        # Dùng tk.Label thay vì CTkLabel: CTkLabel + wraplength cố định
        # hay bị canvas bên trong cắt mất chữ cuối dòng. tk.Label tự
        # wrap theo đúng độ rộng thực tế của nó nên không bị cắt.
        self.jd_title = tk.Label(
            header,
            text="",
            bg=t.white,
            fg=t.text_primary,
            font=("Segoe UI Semibold", 22),
            anchor="w",
            justify="left",
            wraplength=self._wrap_width,
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0
        )

        self.jd_title.grid(row=0, column=0, sticky="ew")
        self.jd_title.bind("<Configure>", self._on_title_resize)

        self.jd_salary = ctk.CTkLabel(
            header,
            text="",
            text_color=t.salary_color,
            font=("Segoe UI Semibold", 12),
            anchor="w"
        )

        self.jd_salary.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(6, 0)
        )

        # Mỗi dòng meta = icon + text (company / location / address / dates).
        # Dùng tk.Label vì CTkLabel có chiều cao cố định nên địa chỉ dài
        # bị cắt; tk.Label tự cao theo số dòng wrap.
        self.jd_meta_rows = {}

        for index, key in enumerate(self.META_ICONS, start=2):
            label = tk.Label(
                header,
                text="",
                bg=t.white,
                fg=t.text_secondary,
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
            label.bind("<Configure>", self._on_meta_resize)

            self.jd_meta_rows[key] = label

        source_row = ctk.CTkFrame(
            header,
            fg_color=t.white,
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
            fg_color=t.tag_bg,
            text_color=t.tag_text,
            corner_radius=6,
            padx=9,
            pady=4,
            font=("Segoe UI Semibold", 12),
            anchor="w"
        )

        self.jd_source.grid(row=0, column=0)

        self.jd_open_button = ctk.CTkButton(
            source_row,
            text="Mở link gốc ↗",
            width=110,
            height=26,
            corner_radius=6,
            fg_color=t.primary,
            hover_color=t.primary_hover,
            font=("Segoe UI Semibold", 12),
            command=self.open_selected_url,
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
            fg_color=t.border
        )

        separator.grid(
            row=3 + len(self.META_ICONS),
            column=0,
            sticky="ew",
            pady=(14, 0)
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
            _fmt_date_range(
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

    # ------------------------------------------------------------------
    # B. Thông tin khác (bullet list)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # C/D. HTML sections (Mô tả / Yêu cầu / Quyền lợi)
    # ------------------------------------------------------------------

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

        # Quyền lợi: không có dữ liệu thì ẩn luôn cả khối.
        self._set_html_section(
            self.benefits_section,
            job.get("benefits")
        )

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

        t = self.theme

        body_bg = t.jd_bg if card else t.white
        fonts = self._font_sets[font_size or self.HTML_FONT_SIZE]

        if line_gap is None:
            line_gap = (1, 6) if card else (3, 4)

        heading = ctk.CTkLabel(
            self.detail_scroll,
            text=title,
            text_color=t.text_primary,
            font=("Segoe UI Semibold", 18),
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
            border_color=t.border_light
        )

        container.grid(
            row=row + 1,
            column=0,
            sticky="ew",
            padx=self.DETAIL_PAD_X,
            pady=(0, 6)
        )

        container.grid_columnconfigure(0, weight=1)

        text = tk.Text(
            container,
            wrap="word",
            bg=body_bg,
            fg=t.text_primary,
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

        # Đếm số dòng hiển thị thực tế (đã tính cả word wrap)
        result = text.count("1.0", "end-1c", "displaylines")
        lines = result[0] if result else 1

        text.configure(height=max(1, lines))

    def _set_html_section(self, section, content, placeholder=None):
        html = _to_html(content) or _to_html(placeholder)

        if not html:
            section["heading"].grid_remove()
            section["container"].grid_remove()
            return

        section["heading"].grid()
        section["container"].grid()

        HtmlTextRenderer.render(section["text"], html)

        self.after_idle(
            self._fit_text_height,
            section["text"]
        )

    # ------------------------------------------------------------------
    # Resize / scroll
    # ------------------------------------------------------------------

    def _on_title_resize(self, event):
        # Wrap đúng bằng độ rộng label đang có -> không bao giờ tràn/cắt chữ.
        width = max(100, event.width)

        if int(self.jd_title.cget("wraplength")) != width:
            self.jd_title.configure(wraplength=width)

    def _on_meta_resize(self, event):
        width = max(100, event.width)
        label = event.widget

        if int(label.cget("wraplength")) != width:
            label.configure(wraplength=width)

    def _scroll_to_top(self):
        canvas = getattr(self.detail_scroll, "_parent_canvas", None)

        if canvas is not None:
            canvas.yview_moveto(0)
