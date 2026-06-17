#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rich Message HTML markup helper (Bot API 10.1).

Mọi hàm trả về chuỗi HTML đã escape đúng các ký tự đặc biệt. Kết quả
dùng để gửi qua `sendRichMessage` với `rich_message.html` (xem utils/telegram_api.py).

Quy ước:
- Tiêu đề lớn:   <h1>...</h1>
- Tiêu đề phụ:   <h2>...</h2>
- Đoạn văn:      <p>...</p>
- In đậm:        <b>...</b>
- Inline code:   <code>...</code>
- Phân cách:     <hr/>
- Chân trang:    <footer>...</footer>
- Bảng:          <table bordered striped>...</table> với <tr><th>...</th></tr> cho header
                 và <tr><td>...</td></tr> cho dữ liệu.

Lưu ý: Trong `<td>`/`<th>` chỉ được chứa inline tags, không được chứa block
như `<p>`, `<h*>`, `<img>`. Code sẽ tự động thay newline trong cell bằng `<br/>`.
"""

from html import escape as _html_escape

from typing import Iterable, List


def escape_html(text: str) -> str:
    """Escape ký tự đặc biệt của HTML cho nội dung text node."""
    if text is None:
        return ""
    return _html_escape(str(text), quote=False)


def h1(text: str) -> str:
    return f"<h1>{escape_html(text)}</h1>"


def h2(text: str) -> str:
    return f"<h2>{escape_html(text)}</h2>"


def p(text: str) -> str:
    return f"<p>{escape_html(text)}</p>"


def b(text: str) -> str:
    return f"<b>{escape_html(text)}</b>"


def code(text: str) -> str:
    return f"<code>{escape_html(text)}</code>"


def hr() -> str:
    return "<hr/>"


def footer(text: str) -> str:
    return f"<footer>{escape_html(text)}</footer>"


def section_heading(emoji: str, title: str) -> str:
    """Tiêu đề lớn có emoji ở đầu, ví dụ: <h1>📅 TKB</h1>"""
    prefix = f"{emoji} " if emoji else ""
    return f"<h1>{escape_html(prefix + title)}</h1>"


def kv_line(key: str, value: str) -> str:
    """Một dòng kiểu `key: <code>value</code>`, ví dụ: Mã HP: <code>MAT101</code>"""
    return f"<p>{escape_html(key)}: <code>{escape_html(value)}</code></p>"


def p_bold(text: str) -> str:
    """Đoạn văn với chữ in đậm."""
    return f"<p><b>{escape_html(text)}</b></p>"


def p_with_emoji(emoji: str, text: str) -> str:
    """Đoạn văn có emoji ở đầu, ví dụ: 🗓️ 23/06/2026 - 29/06/2026"""
    prefix = f"{emoji} " if emoji else ""
    return f"<p>{escape_html(prefix + text)}</p>"


def cell(text: str) -> str:
    """Escape nội dung cho 1 ô bảng và thay newline bằng <br/>."""
    if text is None:
        return "<td></td>"
    safe = escape_html(str(text)).replace("\n", "<br/>")
    return f"<td>{safe}</td>"


def header_cell(text: str) -> str:
    if text is None:
        return "<th></th>"
    safe = escape_html(str(text)).replace("\n", "<br/>")
    return f"<th>{safe}</th>"


def table(headers: Iterable[str], rows: Iterable[Iterable[str]],
         bordered: bool = True, striped: bool = False) -> str:
    """
    Tạo bảng HTML theo cú pháp Rich Message.

    Args:
        headers: Danh sách tiêu đề cột, sẽ render trong <th>.
        rows: Danh sách các dòng, mỗi dòng là iterable chuỗi cho từng ô.
        bordered: Thêm thuộc tính `bordered` (viền).
        striped: Thêm thuộc tính `striped` (sọc xen kẽ các hàng).

    Ví dụ:
        table(['STT', 'Mã HP', 'Tên HP'], [['1', 'MAT101', 'Toán cao cấp']],
              bordered=True, striped=True)

    Trả về:
        <table bordered striped><tr><th>STT</th>...</tr><tr><td>1</td>...</tr></table>
    """
    attrs: List[str] = []
    if bordered:
        attrs.append("bordered")
    if striped:
        attrs.append("striped")
    attr_str = f' {" ".join(attrs)}' if attrs else ""
    parts = [f"<table{attr_str}>"]
    parts.append("<tr>")
    for h in headers:
        parts.append(header_cell(h))
    parts.append("</tr>")
    for row in rows:
        parts.append("<tr>")
        for c in row:
            parts.append(cell(c))
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def join_blocks(blocks: Iterable[str]) -> str:
    """Nối nhiều block, bỏ qua các block rỗng/None."""
    return "".join(b for b in blocks if b)


def footer_updated_at(timestamp_str: str | None, tz_offset_hours: int = 7) -> str:
    """Tạo footer `Cập nhật lúc: HH:MM dd/mm/yyyy` từ ISO timestamp UTC."""
    if not timestamp_str:
        return ""
    try:
        from datetime import datetime, timedelta
        ts_utc = datetime.fromisoformat(timestamp_str)
        ts_local = ts_utc + timedelta(hours=tz_offset_hours)
        return footer(f"Cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}")
    except (ValueError, TypeError):
        return ""


def rich_text_html(parts: List[str]) -> str:
    """Nối nhiều block thành 1 chuỗi HTML hợp lệ."""
    return join_blocks(parts)
