#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rich Message HTML markup helper (Bot API 10.1).

Mọi hàm trả về chuỗi HTML đã escape các ký tự đặc biệt đúng cách. Kết quả
gửi qua `utils.telegram_api.TelegramAPI.send_rich_message` với
`rich_message.html`.

Quy ước tag:
- `<h1>` / `<h2>`: tiêu đề.
- `<p>`: đoạn văn.
- `<b>`: in đậm.
- `<code>`: inline code.
- `<hr/>`: phân cách.
- `<footer>`: chân trang.
- `<table bordered striped>` với `<tr><th>` cho header và `<tr><td>` cho data.

Lưu ý: Trong `<td>`/`<th>` chỉ được chứa inline tag. Code tự thay newline
trong cell bằng `<br/>`.
"""

from datetime import datetime, timedelta
from html import escape as _html_escape
from typing import Iterable, List


def escape_html(text: str) -> str:
    """Escape ký tự HTML đặc biệt trong text node. Trả về chuỗi rỗng nếu input là None."""
    if text is None:
        return ""
    return _html_escape(str(text), quote=False)


def h1(text: str) -> str:
    """Tiêu đề lớn `<h1>...</h1>`."""
    return f"<h1>{escape_html(text)}</h1>"


def h2(text: str) -> str:
    """Tiêu đề phụ `<h2>...</h2>`."""
    return f"<h2>{escape_html(text)}</h2>"


def p(text: str) -> str:
    """Đoạn văn `<p>...</p>`."""
    return f"<p>{escape_html(text)}</p>"


def b(text: str) -> str:
    """In đậm `<b>...</b>`."""
    return f"<b>{escape_html(text)}</b>"


def code(text: str) -> str:
    """Inline code `<code>...</code>`."""
    return f"<code>{escape_html(text)}</code>"


def hr() -> str:
    """Đường phân cách `<hr/>`."""
    return "<hr/>"


def footer(text: str) -> str:
    """Chân trang `<footer>...</footer>`."""
    return f"<footer>{escape_html(text)}</footer>"


def section_heading(emoji: str, title: str) -> str:
    """Tiêu đề lớn có emoji ở đầu. Vd: `<h1>📅 TKB</h1>`."""
    prefix = f"{emoji} " if emoji else ""
    return f"<h1>{escape_html(prefix + title)}</h1>"


def kv_line(key: str, value: str) -> str:
    """Một dòng kiểu `key: <code>value</code>`. Vd: `Mã HP: <code>MAT101</code>`."""
    return f"<p>{escape_html(key)}: <code>{escape_html(value)}</code></p>"


def p_bold(text: str) -> str:
    """Đoạn văn với chữ in đậm `<p><b>...</b></p>`."""
    return f"<p><b>{escape_html(text)}</b></p>"


def p_with_emoji(emoji: str, text: str) -> str:
    """Đoạn văn có emoji ở đầu. Vd: `🗓️ 23/06/2026 - 29/06/2026`."""
    prefix = f"{emoji} " if emoji else ""
    return f"<p>{escape_html(prefix + text)}</p>"


def cell(text: str) -> str:
    """Render 1 ô `<td>` của bảng. Tự escape HTML và thay newline bằng `<br/>`."""
    if text is None:
        return "<td></td>"
    safe = escape_html(str(text)).replace("\n", "<br/>")
    return f"<td>{safe}</td>"


def header_cell(text: str) -> str:
    """Render 1 ô header `<th>` của bảng."""
    if text is None:
        return "<th></th>"
    safe = escape_html(str(text)).replace("\n", "<br/>")
    return f"<th>{safe}</th>"


def table(
    headers: Iterable[str],
    rows: Iterable[Iterable[str]],
    bordered: bool = True,
    striped: bool = False,
) -> str:
    """Tạo bảng HTML theo cú pháp Rich Message.

    Args:
        headers: Danh sách tiêu đề cột, render trong `<th>`.
        rows: Danh sách các dòng, mỗi dòng là iterable chuỗi cho từng ô.
        bordered: Thêm thuộc tính `bordered`.
        striped: Thêm thuộc tính `striped` (sọc xen kẽ).

    Returns:
        Chuỗi `<table>...</table>` đã sẵn sàng nhúng vào Rich Message.
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
    """Nối nhiều block, bỏ qua block rỗng/None."""
    return "".join(b for b in blocks if b)


def footer_updated_at(timestamp_str: str | None, tz_offset_hours: int = 7) -> str:
    """Tạo footer `Cập nhật lúc: HH:MM dd/mm/yyyy` từ ISO timestamp UTC (mặc định GMT+7)."""
    if not timestamp_str:
        return ""
    try:
        ts_utc = datetime.fromisoformat(timestamp_str)
        ts_local = ts_utc + timedelta(hours=tz_offset_hours)
        return footer(f"Cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}")
    except (ValueError, TypeError):
        return ""


def rich_text_html(parts: List[str]) -> str:
    """Nối nhiều block thành 1 chuỗi HTML hoàn chỉnh."""
    return join_blocks(parts)
