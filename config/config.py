#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
File cấu hình cho bot Telegram HUTECH.

Bot gọi trực tiếp https://api.telegram.org/bot<TOKEN>/<METHOD> qua aiohttp,
không qua thư viện python-telegram-bot. Vì vậy hầu hết timeout/pool/connection
của thư viện đã được lược bỏ. Chỉ giữ lại vài tham số thật sự cần cho long-polling.

Backend tự động phát hiện:
- POSTGRES_URL có giá trị → dùng postgres, ngược lại dùng SQLite
- REDIS_URL có giá trị → dùng redis, ngược lại dùng in-memory
Bạn có thể set STORAGE_BACKEND / CACHE_BACKEND trong .env để override thủ công (không cần trong docker-compose).

Class `Config` là singleton: nhiều module gọi `Config()` nhưng chỉ thực sự
load env + log 1 lần. Các lần sau trả về instance đã cache.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class Config:
    _instance: "Config | None" = None
    _initialized: bool = False

    def __new__(cls):
        # Singleton: mọi lần gọi Config() đều trả về cùng 1 instance
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Chỉ chạy 1 lần dù __init__ có được gọi nhiều lần
        if Config._initialized:
            return
        Config._initialized = True

        env_path = Path('.env')
        if env_path.exists():
            load_dotenv()

        # Token của bot Telegram
        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

        # Cấu hình API HUTECH
        self.HUTECH_API_BASE_URL = "https://api.hutech.edu.vn"
        self.HUTECH_LOGIN_ENDPOINT = "/api-permission-v2-sinh-vien/api/authen/user/enter-system/login-normal"
        self.HUTECH_LOGOUT_ENDPOINT = "/api-permission-v2-sinh-vien/api/authen/user/enter-system/logout"
        self.HUTECH_TKB_ENDPOINT = "/api-elearning-v2/api/tkb-sinh-vien/xem-tkb"
        self.HUTECH_LICHTHI_ENDPOINT = "/api-elearning-v2/api/lich-thi-sinh-vien/xem-lich-thi"
        self.HUTECH_DIEM_ENDPOINT = "/api-elearning-v2/api/diem-sinh-vien/xem-diem"
        self.HUTECH_HOC_PHAN_NAM_HOC_HOC_KY_ENDPOINT = "/api-elearning/api/lop-hoc-phan/sinh-vien/nam-hoc-hoc-ky/get"
        self.HUTECH_HOC_PHAN_SEARCH_ENDPOINT = "/api-elearning/api/lop-hoc-phan/sinh-vien/search"
        self.HUTECH_HOC_PHAN_DIEM_DANH_ENDPOINT = "/api-elearning/api/lop-hoc-phan/sinh-vien/diem-danh/get-list"
        self.HUTECH_HOC_PHAN_DANH_SACH_SINH_VIEN_ENDPOINT = "/api-elearning/api/lop-hoc-phan/sinh-vien/get"
        self.HUTECH_DIEM_DANH_SUBMIT_ENDPOINT = "/api-elearning/api/qr-code/submit"

        # Headers cho API
        self.HUTECH_STUDENT_HEADERS = {
            "user-agent": "Dart/3.8 (dart:io)",
            "app-key": "SINHVIEN_DAIHOC",
            "content-type": "application/json"
        }

        self.HUTECH_MOBILE_HEADERS = {
            "user-agent": "Dart/3.8 (dart:io)",
            "app-key": "MOBILE_HUTECH",
            "content-type": "application/json"
        }

        # Cấu hình database & cache
        self.POSTGRES_URL = os.getenv("POSTGRES_URL", "")
        self.REDIS_URL = os.getenv("REDIS_URL", "")
        self.SQLITE_PATH = os.getenv("SQLITE_PATH", "/data/bot.db")
        self.STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "").lower()
        self.CACHE_BACKEND = os.getenv("CACHE_BACKEND", "").lower()

        # Auto-detect backend khi chưa set thủ công
        if not self.STORAGE_BACKEND:
            self.STORAGE_BACKEND = "postgres" if self.POSTGRES_URL else "sqlite"
        if not self.CACHE_BACKEND:
            self.CACHE_BACKEND = "redis" if self.REDIS_URL else "memory"

        # Kiểm tra các biến môi trường cần thiết (chỉ 1 lần)
        self._validate_config()

    def _validate_config(self):
        """Kiểm tra các cấu hình bắt buộc. Bỏ raise cho URL rỗng — chỉ raise khi
        backend được chọn thủ công mà thiếu URL tương ứng."""
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN không được để trống. "
                "Hãy đặt biến môi trường TELEGRAM_BOT_TOKEN hoặc kiểm tra file .env."
            )

        if self.STORAGE_BACKEND not in ("postgres", "sqlite"):
            raise ValueError(
                f"STORAGE_BACKEND không hợp lệ: {self.STORAGE_BACKEND!r}. "
                "Chỉ chấp nhận 'postgres' hoặc 'sqlite'."
            )
        if self.CACHE_BACKEND not in ("redis", "memory"):
            raise ValueError(
                f"CACHE_BACKEND không hợp lệ: {self.CACHE_BACKEND!r}. "
                "Chỉ chấp nhận 'redis' hoặc 'memory'."
            )

        # Raise chỉ khi user CHỌN postgres/redis mà quên URL tương ứng
        if self.STORAGE_BACKEND == "postgres" and not self.POSTGRES_URL:
            raise ValueError(
                "STORAGE_BACKEND=postgres yêu cầu POSTGRES_URL. "
                "Để trống STORAGE_BACKEND để tự động fallback sang sqlite."
            )
        if self.CACHE_BACKEND == "redis" and not self.REDIS_URL:
            raise ValueError(
                "CACHE_BACKEND=redis yêu cầu REDIS_URL. "
                "Để trống CACHE_BACKEND để tự động fallback sang in-memory."
            )

        # Log rõ backend nào đang dùng để user thấy lúc khởi động (1 lần)
        storage_label = (
            f"postgres ({self._redact_url(self.POSTGRES_URL)})"
            if self.STORAGE_BACKEND == "postgres"
            else f"sqlite @ {self.SQLITE_PATH}"
        )
        cache_label = (
            f"redis ({self._redact_url(self.REDIS_URL)})"
            if self.CACHE_BACKEND == "redis"
            else "in-memory (mất khi restart, không share giữa instances)"
        )
        logger.info("Storage backend: %s", storage_label)
        logger.info("Cache backend:   %s", cache_label)

    @staticmethod
    def _redact_url(url: str) -> str:
        """Ẩn password trong URL khi log."""
        if "@" not in url:
            return url
        try:
            scheme_userpass, host_part = url.rsplit("@", 1)
            scheme, userpass = scheme_userpass.split("://", 1)
            if ":" in userpass:
                user, _ = userpass.split(":", 1)
                return f"{scheme}://{user}:***@{host_part}"
            return url
        except Exception:
            return url