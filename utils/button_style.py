#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Helper tạo InlineKeyboardButton theo Bot API 9.4 (style + emoji).
"""

from typing import Optional

from telegram import InlineKeyboardButton

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
    tone: str = "primary",
    emoji: Optional[str] = None,
    icon_custom_emoji_id: Optional[str] = None,
) -> InlineKeyboardButton:
    """
    Tạo InlineKeyboardButton với style Bot API 9.4.
    """
    style = TONE_TO_STYLE.get(tone, "primary")
    text = f"{emoji} {label}" if emoji else label

    api_kwargs = {"style": style}
    if icon_custom_emoji_id:
        api_kwargs["icon_custom_emoji_id"] = icon_custom_emoji_id

    return InlineKeyboardButton(text=text, callback_data=callback_data, api_kwargs=api_kwargs)
