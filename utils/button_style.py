#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Helper tạo inline keyboard (Bot API 9.4+).

Trả về dict (không phải object của thư viện ngoài) để gửi qua
`utils.telegram_api.TelegramAPI.call` dưới dạng JSON.

Mỗi button có dạng:
    {
        "text": "...",
        "callback_data": "...",   # hoặc "url": "..." cho link ngoài
        "style": "primary" | "success" | "danger",   # optional
        "icon_custom_emoji_id": "...",                # optional, Bot API 7.x+
    }

Style chỉ áp dụng cho callback button. Các tone hỗ trợ:
- `primary`, `success`, `danger`: ánh xạ 1-1 sang style Bot API.
- `warning`, `neutral`: ánh xạ sang `primary`.
- `None`: không đặt style.
"""

from typing import Any, Dict, List, Optional


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
    """Tạo 1 callback button.

    Args:
        label: Text hiển thị trên nút.
        callback_data: Dữ liệu callback (giới hạn 64 bytes theo Bot API).
        tone: Một trong {"primary", "success", "danger", "warning", "neutral"}.
              None để không đặt style.
        emoji: Emoji đặt ở đầu nhãn (optional).
        icon_custom_emoji_id: ID custom emoji (optional).
    """
    style = TONE_TO_STYLE.get(tone) if tone else None
    text = f"{emoji} {label}" if emoji else label

    button: Dict[str, Any] = {"text": text, "callback_data": callback_data}
    if style:
        button["style"] = style
    if icon_custom_emoji_id:
        button["icon_custom_emoji_id"] = icon_custom_emoji_id
    return button


def make_url_button(label: str, url: str, emoji: Optional[str] = None) -> Dict[str, Any]:
    """Tạo 1 URL button (mở link ngoài khi bấm)."""
    text = f"{emoji} {label}" if emoji else label
    return {"text": text, "url": url}


def build_inline_keyboard(rows: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Đóng gói danh sách row nút thành object `reply_markup` cho Bot API.

    Args:
        rows: Mỗi hàng là danh sách dict button (kết quả của make_inline_button
              hoặc make_url_button).

    Returns:
        {"inline_keyboard": [[...], [...]]}
    """
    return {"inline_keyboard": rows}
