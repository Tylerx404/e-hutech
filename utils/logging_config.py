#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cấu hình logging cho toàn bộ bot.

Hỗ trợ 2 format:
- Plain text (mặc định, dễ đọc khi chạy local).
- JSON (bật qua `LOG_JSON=true`, dễ parse khi chạy trong Docker).

Tự động giảm log noise từ thư viện HTTP (`httpx`, `httpcore`) xuống WARNING
để log polling Telegram không bị spam.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional


class JsonFormatter(logging.Formatter):
    """Render log record thành 1 dòng JSON. Dùng cho môi trường production."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def _parse_bool_env(value: Optional[str], default: bool = False) -> bool:
    """Parse env string thành bool. Chấp nhận 1/true/yes/on (case-insensitive)."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def setup_logging() -> None:
    """Cấu hình root logger theo biến môi trường LOG_LEVEL và LOG_JSON.

    Hàm này được gọi 1 lần ở đầu `bot.py` trước khi import các module khác.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    use_json = _parse_bool_env(os.getenv("LOG_JSON"), default=False)

    handler = logging.StreamHandler()
    if use_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Giảm log spam từ thư viện HTTP — chỉ giữ warning trở lên
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
