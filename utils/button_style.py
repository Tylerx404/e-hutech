#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Helper tạo nút bấm (inline keyboard) theo cú pháp Bot API.

Trả về dict (không phải object InlineKeyboardButton của python-telegram-bot)
để gửi qua HTTP API dưới dạng JSON trong trường `reply_markup.inline_keyboard`.

Mỗi nút có dạng:
    {
        "text": "...",
        "callback_data": "...",     # hoặc "url": "..." cho link ngoài
        "style": "primary" | "success" | "danger" | None,
        "icon_custom_emoji_id": "..."  # optional
    }

`style` chỉ áp dụng cho callback button. Các giá trị hợp lệ theo Bot API 9.4:
primary, success, danger.
"""

from typing import Optional, List, Dict, Any


TONE_TO_STYLE = {
    "primary": "primary",
    "success": "success",
    "danger": "danger",
    "warning": "primary",
    "neutral": "primary",
}


def make_inline_button(
    label: str,
    callback_data: str,
    tone: Optional[str] = "primary",
    emoji: Optional[str] = None,
    icon_custom_emoji_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tạo 1 inline button (dạng dict) cho callback query.

    Args:
        label: Text hiển thị trên nút.
        callback_data: Dữ liệu callback (giới hạn 64 bytes theo Bot API).
        tone: Một trong {"primary", "success", "danger", "warning", "neutral"}.
              None để không đặt style.
        emoji: Emoji đặt ở đầu nhãn (optional).
        icon_custom_emoji_id: ID custom emoji (optional, Bot API 7.x+).
    """
    style = TONE_TO_STYLE.get(tone) if tone else None
    text = f"{emoji} {label}" if emoji else label

    button: Dict[str, Any] = {"text": text, "callback_data": callback_data}
    if style:
        button["style"] = style
    if icon_custom_emoji_id:
        button["icon_custom_emoji_id"] = icon_custom_emoji_id
    return button


def make_url_button(
    label: str,
    url: str,
    emoji: Optional[str] = None,
) -> Dict[str, Any]:
    """Tạo 1 URL button."""
    text = f"{emoji} {label}" if emoji else label
    return {"text": text, "url": url}


def build_inline_keyboard(rows: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Đóng gói danh sách row nút thành object `reply_markup` cho Bot API.

    Args:
        rows: Danh sách các hàng, mỗi hàng là danh sách các dict button
              (kết quả của make_inline_button / make_url_button).

    Returns:
        {"inline_keyboard": [[...], [...]]}
    """
    return {"inline_keyboard": rows}
