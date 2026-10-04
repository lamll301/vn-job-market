"""Crawl + dialog tiến độ (kiểu DevExpress Wait Form).

Toàn bộ phần liên quan tới việc hiển thị tiến độ crawl nằm trong file này:

    CrawlLogStream        bắt print() của pipeline -> queue
    CrawlProgress         parse từng dòng log -> trạng thái + chữ hiển thị
    CrawlProgressDialog   cửa sổ giao diện (spinner, chữ, nút Hủy)
    CrawlSession          điều phối: thread, hủy, đọc log, cập nhật dialog

MainWindow chỉ cần:

    session = CrawlSession(root, lambda: run_all(repo), on_finished=cb)
    session.start()
"""

import asyncio
import contextlib
import queue
import re
import sys
import threading
import tkinter as tk
from dataclasses import dataclass

RECENT_LINES = 3        # số dòng "saved" gần nhất hiển thị

SOURCE_LABELS = {
    "vietnamworks": "VietnamWorks",
    "careerlink": "CareerLink",
    "topcv": "TopCV",
}


class CrawlLogStream:
    """Thay sys.stdout trong lúc crawl: mỗi dòng log được đẩy vào queue để
    giao diện đọc (hiển thị tiến độ), đồng thời vẫn in ra console như cũ."""

    def __init__(self, log_queue, original=None):
        self._queue = log_queue
        self._original = original
        self._buffer = ""

    def write(self, text):
        if self._original is not None:
            try:
                self._original.write(text)
            except Exception:
                pass  # console không in được tiếng Việt thì thôi, vẫn parse

        self._buffer += text

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()

            if line:
                self._queue.put(("line", line))

        return len(text)

    def flush(self):
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass

    def finish(self):
        """Đẩy nốt phần còn lại chưa kết thúc bằng xuống dòng."""
        line = self._buffer.strip()
        self._buffer = ""

        if line:
            self._queue.put(("line", line))

    def __getattr__(self, name):
        # encoding, isatty, ... lấy từ stdout gốc
        original = self.__dict__.get("_original")

        if original is None:
            raise AttributeError(name)

        return getattr(original, name)


class CrawlProgress:
    """Trạng thái tiến độ, được cập nhật bằng cách parse log của pipeline."""

    START_RE = re.compile(
        r"Bắt đầu tiến trình cào dữ liệu\s+(?P<site>.+?)\s*$"
    )
    CATEGORY_RE = re.compile(r"Đang cào danh mục:\s*'(?P<name>.*)'")
    PAGE_RE = re.compile(
        r"\[(?P<src>[\w-]+)\]\s+page\s+(?P<page>\d+):\s+\d+\s+jobs"
    )
    DEDUP_RE = re.compile(r"\[(?P<src>[\w-]+)\]\s+dedup:")
    SAVED_RE = re.compile(r"^\[worker\s+\d+\]\s+saved\s+\S")
    DONE_RE = re.compile(
        r"\[(?P<src>[\w-]+)\]\s+done\s*->\s*"
        r"listed=(?P<listed>\d+)\s+new=(?P<new>\d+)"
    )
    STOP_RE = re.compile(r"^\[STOP\]\s*(?P<msg>.+)")

    def __init__(self):
        self.site = ""
        self.category = ""
        self.page = 0
        self.phase = "init"     # init | listing | checking | deduped | saving
        self.page_new = 0       # tin cần lưu của trang vừa kiểm tra trùng
        self.scanned = 0        # tổng số tin đã liệt kê (cộng dồn các trang)
        self.to_save = 0        # tin mới + tin chưa đủ dữ liệu cần lưu
        self.saved = 0          # số dòng "saved" đã thấy
        self.recent = []        # các dòng "saved" gần nhất
        self.done = []          # [(nguồn, listed, new)] từ dòng "done ->"
        self.stop = None        # lý do pipeline tự dừng ([STOP] ...)

    # --- parse log ----------------------------------------------------

    def feed(self, line):
        if self.SAVED_RE.match(line):
            self.saved += 1
            self.phase = "saving"
            self.recent.append(line)
            del self.recent[:-RECENT_LINES]
            return

        match = self.START_RE.search(line)

        if match:
            self.site = match.group("site")
            self.category = ""
            self.page = 0
            self.phase = "listing"
            return

        match = self.CATEGORY_RE.search(line)

        if match:
            self.category = match.group("name")
            self.page = 0
            self.phase = "listing"
            return

        match = self.PAGE_RE.search(line)

        if match:
            self.page = int(match.group("page")) + 1  # log đếm từ 0
            self.phase = "checking"

            if not self.site:
                src = match.group("src")
                self.site = SOURCE_LABELS.get(src.lower(), src)

            return

        if self.DEDUP_RE.search(line):
            listed = self._first_int(r"(\d+)\s+listed", line)
            incomplete = self._first_int(r"(\d+)\s+incomplete", line)
            new = self._first_int(r"(\d+)\s+new", line)

            self.scanned += listed
            self.to_save += new + incomplete
            self.page_new = new + incomplete
            self.phase = "deduped"
            return

        match = self.DONE_RE.search(line)

        if match:
            src = match.group("src")

            self.done.append((
                SOURCE_LABELS.get(src.lower(), src),
                int(match.group("listed")),
                int(match.group("new")),
            ))
            return

        match = self.STOP_RE.match(line)

        if match:
            self.stop = match.group("msg")

    @staticmethod
    def _first_int(pattern, text):
        match = re.search(pattern, text)
        return int(match.group(1)) if match else 0

    # --- tổng kết -----------------------------------------------------

    @property
    def totals(self):
        """(số tin đã liệt kê, số tin mới)."""
        if self.done:
            return (
                sum(item[1] for item in self.done),
                sum(item[2] for item in self.done),
            )

        return self.scanned, self.saved

    # --- chữ hiển thị -------------------------------------------------

    def header_text(self, stop_requested=False):
        if stop_requested:
            return "Đang dừng tiến trình cào dữ liệu..."

        if self.site:
            return f"Đang cào dữ liệu {self.site}..."

        return "Đang khởi động tiến trình cào dữ liệu..."

    def sub_text(self):
        parts = []

        if self.page:
            parts.append(f"Trang {self.page}")

        if self.category:
            parts.append(f"Danh mục '{self.category}'")

        if self.scanned:
            parts.append(f"Đã cào {self.scanned} tin")

        return "  •  ".join(parts) or "Đang chuẩn bị..."

    def action_text(self, stop_requested=False):
        if stop_requested:
            return "Đang chờ các tác vụ đang chạy kết thúc an toàn..."

        if self.stop:
            return self.stop

        if self.phase == "saving":
            return (
                "Đang lưu dữ liệu mới vào DB... "
                f"({self.saved}/{max(self.to_save, self.saved)})"
            )

        if self.phase == "deduped":
            if self.page_new:
                return f"Có {self.page_new} tin mới cần lưu ở trang này..."

            return "Không có tin mới ở trang này."

        if self.phase == "checking":
            return "Đang kiểm tra tin trùng lặp..."

        if self.phase == "listing":
            return "Đang tải danh sách tin tuyển dụng..."

        return "Đang khởi tạo tiến trình..."


@dataclass(frozen=True)
class CrawlProgressTheme:
    white: str = "#FFFFFF"
    border: str = "#E5E7EB"
    primary: str = "#2563EB"
    text_primary: str = "#111827"
    text_secondary: str = "#6B7280"
    text_muted: str = "#9CA3AF"
    cancel: str = "#B91C1C"
    cancel_hover_bg: str = "#FEF2F2"
    cancel_border: str = "#FCA5A5"


class CrawlProgressDialog:
    WIDTH = 520
    SPINNER_SIZE = 40
    SPINNER_MS = 30         # chu kỳ quay của spinner
    WATCH_MS = 50           # chu kỳ kiểm tra popup có bị che / cần canh giữa
    RECENT_LINES = RECENT_LINES
    LINE_MAX_CHARS = 60

    def __init__(self, root, on_cancel, theme=None):
        self._root = root
        self._on_cancel = on_cancel
        self._theme = theme or CrawlProgressTheme()

        self._popup = None
        self._labels = {}
        self._stop_button = None
        self._spinner = None
        self._arc = None
        self._angle = 90
        self._spin_id = None
        self._watch_id = None

    # ------------------------------------------------------------------
    # API công khai
    # ------------------------------------------------------------------

    @property
    def is_open(self):
        return self._popup is not None

    def open(self):
        if self._popup is not None:
            return

        self._build()

        popup = self._popup
        popup.update_idletasks()
        self._center()

        popup.deiconify()
        popup.lift()

        # Chặn thao tác lên cửa sổ chính trong lúc crawl
        try:
            popup.update()
            popup.grab_set()
        except tk.TclError:
            pass

        self._watch()
        self._animate()

    def set_progress(self, header, sub, action, recent_lines=()):
        """Cập nhật chữ; chỉ configure khi nội dung thật sự đổi (tránh chớp)."""
        if self._popup is None:
            return

        limit = self.LINE_MAX_CHARS

        recent = "\n".join(
            line if len(line) <= limit else line[:limit - 1] + "…"
            for line in recent_lines
        )

        for key, text in (
            ("header", header),
            ("sub", sub),
            ("action", action),
            ("recent", recent),
        ):
            label = self._labels[key]

            if label.cget("text") != text:
                label.configure(text=text)

    def set_stopping(self):
        if self._popup is not None and self._stop_button is not None:
            self._stop_button.configure(state="disabled", text="Đang dừng...")

    def close(self):
        for after_id in (self._spin_id, self._watch_id):
            if after_id is not None:
                try:
                    self._root.after_cancel(after_id)
                except tk.TclError:
                    pass

        self._spin_id = self._watch_id = None

        popup, self._popup = self._popup, None

        if popup is not None:
            try:
                popup.grab_release()
            except tk.TclError:
                pass

            try:
                popup.destroy()
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Dựng giao diện
    # ------------------------------------------------------------------

    def _build(self):
        t = self._theme
        size = self.SPINNER_SIZE
        text_width = self.WIDTH - 48 - size - 16

        popup = tk.Toplevel(self._root)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.configure(bg=t.border, padx=1, pady=1)
        popup.transient(self._root)

        # Không cho đóng popup cho tới khi crawl xong / bị hủy
        popup.protocol("WM_DELETE_WINDOW", lambda: None)

        card = tk.Frame(popup, bg=t.white, padx=24, pady=20)
        card.pack(fill="both", expand=True)
        card.grid_columnconfigure(1, weight=1)

        # --- Trái: vòng xoay tiến trình ---
        spinner = tk.Canvas(
            card, width=size, height=size, bg=t.white, highlightthickness=0
        )
        spinner.grid(row=0, column=0, sticky="n", padx=(0, 16))

        pad = 5

        spinner.create_oval(
            pad, pad, size - pad, size - pad, outline=t.border, width=4
        )

        self._arc = spinner.create_arc(
            pad, pad, size - pad, size - pad,
            start=90, extent=100, style="arc", outline=t.primary, width=4
        )

        self._spinner = spinner
        self._angle = 90

        # --- Phải: tiêu đề / mô tả / trạng thái hành động ---
        text = tk.Frame(card, bg=t.white)
        text.grid(row=0, column=1, sticky="nsew")

        # giữ cố định bề rộng cột chữ
        tk.Frame(text, width=text_width, height=1, bg=t.white).pack()

        def make_label(key, **options):
            pack_options = options.pop("pack", {})

            label = tk.Label(
                text,
                bg=t.white,
                anchor=options.pop("anchor", "w"),
                justify="left",
                **options
            )
            label.pack(fill="x", **pack_options)
            self._labels[key] = label

        make_label(
            "header",
            text="Đang khởi động tiến trình cào dữ liệu...",
            fg=t.text_primary,
            font=("Segoe UI Semibold", 12),
            wraplength=text_width,
        )

        make_label(
            "sub",
            text="Đang chuẩn bị...",
            fg=t.text_secondary,
            font=("Segoe UI", 10),
            wraplength=text_width,
            pack={"pady": (4, 0)},
        )

        make_label(
            "action",
            text="",
            fg=t.text_primary,
            font=("Segoe UI", 9),
            wraplength=text_width,
            pack={"pady": (10, 0)},
        )

        # Các dòng "[worker n] saved <id> - <tiêu đề>" gần nhất
        make_label(
            "recent",
            text="",
            fg=t.text_muted,
            font=("Segoe UI", 9),
            anchor="nw",
            height=self.RECENT_LINES,
            pack={"pady": (2, 0)},
        )

        # --- Nút Hủy tiến trình (góc dưới phải) ---
        button_row = tk.Frame(card, bg=t.white)
        button_row.grid(row=1, column=0, columnspan=2, sticky="e", pady=(14, 0))

        self._stop_button = tk.Button(
            button_row,
            text="Hủy tiến trình",
            command=self._on_cancel,
            bg=t.white,
            fg=t.cancel,
            activebackground=t.cancel_hover_bg,
            activeforeground=t.cancel,
            disabledforeground=t.text_muted,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=t.cancel_border,
            padx=14,
            pady=4,
            font=("Segoe UI Semibold", 9),
            cursor="hand2",
        )
        self._stop_button.pack()

        self._popup = popup

    # ------------------------------------------------------------------
    # Spinner
    # ------------------------------------------------------------------

    def _animate(self):
        if self._popup is None:
            return

        self._angle = (self._angle - 14) % 360
        self._spinner.itemconfigure(self._arc, start=self._angle)

        self._spin_id = self._root.after(self.SPINNER_MS, self._animate)

    # ------------------------------------------------------------------
    # Vị trí / thứ tự cửa sổ (Alt+Tab, thu nhỏ, kéo cửa sổ chính)
    # ------------------------------------------------------------------

    def _watch(self):
        """Watcher nhẹ: chỉ gọi API cửa sổ khi trạng thái THỰC SỰ đổi
        (gọi lift/deiconify mù mỗi chu kỳ sẽ làm cả giao diện chớp)."""
        if self._popup is None:
            return

        self._sync_state()
        self._watch_id = self._root.after(self.WATCH_MS, self._watch)

    def _sync_state(self):
        popup = self._popup

        try:
            minimized = self._root.state() == "iconic"
            hidden = popup.state() == "withdrawn"

            if minimized:
                if not hidden:
                    popup.withdraw()
                return

            if hidden:
                popup.deiconify()
                popup.lift()
            elif self._is_buried():
                # Alt+Tab quay lại: cửa sổ chính bị đẩy lên trên popup
                popup.lift()

                if popup.grab_current() is None:
                    popup.grab_set()

            self._center()
        except tk.TclError:
            pass

    def _is_buried(self):
        """True nếu popup đang nằm DƯỚI cửa sổ chính (`wm stackorder`
        trả về danh sách từ thấp -> cao)."""
        try:
            order = [str(w) for w in self._root.tk.call("wm", "stackorder", str(self._root))]
            return order.index(str(self._popup)) < order.index(str(self._root))
        except (tk.TclError, ValueError):
            return False

    def _center(self):
        popup, root = self._popup, self._root

        if popup is None:
            return

        width = popup.winfo_reqwidth()
        height = popup.winfo_reqheight()

        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + (root.winfo_height() - height) // 2

        x, y = max(0, x), max(0, y)

        # Cửa sổ chính bị kéo đi -> popup đi theo, vẫn nằm giữa
        if (x, y) != (popup.winfo_x(), popup.winfo_y()):
            popup.geometry(f"+{x}+{y}")


@dataclass
class CrawlResult:
    """Kết quả một lần crawl, truyền cho on_finished."""

    listed: int = 0
    new: int = 0
    saved: int = 0
    error: str = None
    cancelled: bool = False
    stop: str = None


class CrawlSession:
    """Chạy một lần crawl trong thread riêng và hiển thị dialog tiến độ.

    job_factory: hàm không tham số trả về coroutine của pipeline,
                 ví dụ ``lambda: run_all(repository)``.
    on_finished: gọi (trên luồng giao diện) với CrawlResult khi xong,
                 bị hủy hoặc lỗi; dialog đã được đóng trước đó.
    """

    POLL_MS = 100
    MAX_LINES_PER_POLL = 500

    def __init__(self, root, job_factory, on_finished, theme=None):
        self._root = root
        self._job_factory = job_factory
        self._on_finished = on_finished

        self._queue = queue.Queue()
        self._progress = CrawlProgress()
        self._dialog = CrawlProgressDialog(
            root, on_cancel=self.request_stop, theme=theme
        )

        self._loop = None
        self._task = None
        self._running = False
        self._stop_requested = False
        self._cancelled = False
        self._error = None

    @property
    def is_running(self):
        return self._running

    # --- điều khiển ---------------------------------------------------

    def start(self):
        if self._running:
            return

        self._running = True
        self._dialog.open()

        threading.Thread(target=self._worker, daemon=True).start()

        self._poll()

    def request_stop(self):
        """Nút 'Hủy tiến trình': gửi tín hiệu hủy (CancelledError) vào task
        crawl. Tin đã lưu vẫn nằm trong DB; tin đang cào dở sẽ được cào lại
        ở lần sau (dedup coi là tin mới / chưa đủ dữ liệu)."""
        if not self._running or self._stop_requested:
            return

        self._stop_requested = True
        self._dialog.set_stopping()

        loop, task = self._loop, self._task

        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass  # loop vừa đóng: crawl đã xong

    # --- thread crawl -------------------------------------------------

    async def _run(self):
        # Bọc pipeline thành một task để UI có thể gửi tín hiệu hủy
        task = asyncio.ensure_future(self._job_factory())
        self._task = task
        self._loop = asyncio.get_running_loop()

        if self._stop_requested:  # bấm Hủy trước khi task kịp tạo
            task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            if not self._stop_requested:
                raise

            self._cancelled = True

    def _worker(self):
        error = None
        stream = CrawlLogStream(self._queue, sys.stdout)

        try:
            with contextlib.redirect_stdout(stream):
                # asyncio.run tự hủy + chờ các task con còn sót lại
                asyncio.run(self._run())
        except asyncio.CancelledError:
            self._cancelled = True
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
        finally:
            stream.finish()
            self._queue.put(("end", error))

    # --- đọc log từ thread crawl (chạy trên luồng giao diện) ----------

    def _poll(self):
        if not self._running:
            return

        finished = False

        for _ in range(self.MAX_LINES_PER_POLL):
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break

            if kind == "line":
                self._progress.feed(payload)
            else:  # "end"
                self._error = payload
                finished = True
                break

        if finished:
            self._finish()
            return

        progress, stopping = self._progress, self._stop_requested

        self._dialog.set_progress(
            header=progress.header_text(stopping),
            sub=progress.sub_text(),
            action=progress.action_text(stopping),
            recent_lines=progress.recent,
        )

        self._root.after(self.POLL_MS, self._poll)

    def _finish(self):
        self._running = False
        self._dialog.close()

        listed, new = self._progress.totals

        self._on_finished(CrawlResult(
            listed=listed,
            new=new,
            saved=self._progress.saved,
            error=self._error,
            cancelled=self._cancelled,
            stop=self._progress.stop,
        ))