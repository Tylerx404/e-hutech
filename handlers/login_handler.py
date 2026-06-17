#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý đăng nhập vào hệ thống HUTECH.

Luồng đăng nhập 2 bước, dùng state tạm để nhớ user đang ở bước nào:
1. User gửi `/dangnhap` → hỏi username.
2. User nhập username → hỏi password.
3. User nhập password → gọi API HUTECH, lưu account vào DB, xóa state.

State per user (lưu trong cache qua `utils/state_store`):
    {
        "step": "awaiting_username" | "awaiting_password",
        "username": "...",
        "username_prompt_message_id": ...,
        "password_prompt_message_id": ...,
        "login_command_message_id": ...,
    }
"""

import json
import logging
from typing import Any, Dict, Optional

import aiohttp

from config.config import Config
from utils.state_store import StateStore
from utils.telegram_api import TelegramAPI, TelegramAPIError
from utils.utils import generate_uuid
from utils.rich_message import p, b, code, section_heading

logger = logging.getLogger(__name__)

# Tên các step trong state
STEP_AWAITING_USERNAME = "awaiting_username"
STEP_AWAITING_PASSWORD = "awaiting_password"


class LoginHandler:
    """Handler quản lý flow đăng nhập 2 bước vào hệ thống HUTECH."""

    def __init__(self, db_manager, cache_manager, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)
        self.state = StateStore(self.cache_manager)