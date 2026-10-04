import re
from html.parser import HTMLParser


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
