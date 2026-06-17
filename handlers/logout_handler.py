#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý đăng xuất khỏi hệ thống HUTECH.

Luồng `/dangxuat`:
1. Kiểm tra user đã đăng nhập chưa.
2. Lấy account active, gọi API logout HUTECH (nếu có token + device UUID).
3. Xóa account khỏi DB, xóa cache của user.
4. Nếu còn account khác → chuyển sang account đó.
"""

import json
import logging
from typing import Any, Dict, Optional

import aiohttp

from config.config import Config
from utils.telegram_api import TelegramAPI

logger = logging.getLogger(__name__)


class LogoutHandler:
    """Handler xử lý `/dangxuat` — đăng xuất account hiện tại."""

    def __init__(self, db_manager, cache_manager, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)