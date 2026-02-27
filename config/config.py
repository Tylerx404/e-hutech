#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
File cấu hình cho bot Telegram HUTECH
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class Config:
    def __init__(self):
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
        
        # Cấu hình database PostgreSQL
        self.POSTGRES_URL = os.getenv("POSTGRES_URL", "")

        # Cấu hình Redis
        self.REDIS_URL = os.getenv("REDIS_URL", "")

        # Cấu hình network polling Telegram
        self.TELEGRAM_CONNECT_TIMEOUT = self._env_float("TELEGRAM_CONNECT_TIMEOUT", 10.0, min_value=0.0)
        self.TELEGRAM_READ_TIMEOUT = self._env_float("TELEGRAM_READ_TIMEOUT", 20.0, min_value=0.0)
        self.TELEGRAM_WRITE_TIMEOUT = self._env_float("TELEGRAM_WRITE_TIMEOUT", 20.0, min_value=0.0)
        self.TELEGRAM_POOL_TIMEOUT = self._env_float("TELEGRAM_POOL_TIMEOUT", 5.0, min_value=0.0)
        self.TELEGRAM_CONNECTION_POOL_SIZE = self._env_int("TELEGRAM_CONNECTION_POOL_SIZE", 16, min_value=1)

        self.TELEGRAM_GET_UPDATES_CONNECT_TIMEOUT = self._env_float(
            "TELEGRAM_GET_UPDATES_CONNECT_TIMEOUT",
            self.TELEGRAM_CONNECT_TIMEOUT,
            min_value=0.0,
        )
        self.TELEGRAM_GET_UPDATES_READ_TIMEOUT = self._env_float(
            "TELEGRAM_GET_UPDATES_READ_TIMEOUT",
            35.0,
            min_value=0.0,
        )
        self.TELEGRAM_GET_UPDATES_WRITE_TIMEOUT = self._env_float(
            "TELEGRAM_GET_UPDATES_WRITE_TIMEOUT",
            self.TELEGRAM_WRITE_TIMEOUT,
            min_value=0.0,
        )
        self.TELEGRAM_GET_UPDATES_POOL_TIMEOUT = self._env_float(
            "TELEGRAM_GET_UPDATES_POOL_TIMEOUT",
            self.TELEGRAM_POOL_TIMEOUT,
            min_value=0.0,
        )

        self.TELEGRAM_POLL_TIMEOUT = self._env_int("TELEGRAM_POLL_TIMEOUT", 10, min_value=1)
        self.TELEGRAM_POLL_INTERVAL = self._env_float("TELEGRAM_POLL_INTERVAL", 0.5, min_value=0.0)
        self.TELEGRAM_BOOTSTRAP_RETRIES = self._env_int("TELEGRAM_BOOTSTRAP_RETRIES", -1, min_value=-1)
        
        # Kiểm tra các biến môi trường cần thiết
        self._validate_config()

    @staticmethod
    def _env_float(name: str, default: float, min_value: float | None = None) -> float:
        raw_value = os.getenv(name)
        if raw_value is None or raw_value == "":
            return default
        try:
            value = float(raw_value)
        except ValueError:
            logger.warning("Giá trị %s=%r không hợp lệ, dùng mặc định %s", name, raw_value, default)
            return default

        if min_value is not None and value < min_value:
            logger.warning("Giá trị %s=%s nhỏ hơn %s, dùng mặc định %s", name, value, min_value, default)
            return default
        return value

    @staticmethod
    def _env_int(name: str, default: int, min_value: int | None = None) -> int:
        raw_value = os.getenv(name)
        if raw_value is None or raw_value == "":
            return default
        try:
            value = int(raw_value)
        except ValueError:
            logger.warning("Giá trị %s=%r không hợp lệ, dùng mặc định %s", name, raw_value, default)
            return default

        if min_value is not None and value < min_value:
            logger.warning("Giá trị %s=%s nhỏ hơn %s, dùng mặc định %s", name, value, min_value, default)
            return default
        return value
    
    def _validate_config(self):
        """Kiểm tra các cấu hình bắt buộc"""
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN không được để trống. Hãy đặt biến môi trường TELEGRAM_BOT_TOKEN hoặc kiểm tra file .env.")
        
        if not self.POSTGRES_URL:
            raise ValueError("POSTGRES_URL không được để trống. Hãy đặt biến môi trường POSTGRES_URL (ví dụ: postgresql+asyncpg://user:password@host:port/dbname).")

        if not self.REDIS_URL:
            raise ValueError("REDIS_URL không được để trống. Hãy đặt biến môi trường REDIS_URL (ví dụ: redis://localhost:6379/0).")
