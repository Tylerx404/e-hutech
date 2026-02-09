#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
File cấu hình cho bot Telegram HUTECH
"""

import os
from pathlib import Path
from dotenv import load_dotenv

class Config:
    def __init__(self):
        # Tải biến môi trường từ file .env (chỉ khi chạy local)
        # Trong Docker, biến môi trường đã được thiết lập sẵn
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
        
        # Các endpoint API học phần
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
        
        # Headers cho API thời khóa biểu
        self.HUTECH_MOBILE_HEADERS = {
            "user-agent": "Dart/3.8 (dart:io)",
            "app-key": "MOBILE_HUTECH",
            "content-type": "application/json"
        }
        
        # Cấu hình database PostgreSQL
        self.POSTGRES_URL = os.getenv("POSTGRES_URL", "")

        # Cấu hình Redis
        self.REDIS_URL = os.getenv("REDIS_URL", "")
        
        # Kiểm tra các biến môi trường cần thiết
        self._validate_config()
    
    def _validate_config(self):
        """Kiểm tra các cấu hình bắt buộc"""
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN không được để trống. Hãy đặt biến môi trường TELEGRAM_BOT_TOKEN hoặc kiểm tra file .env.")
        
        if not self.POSTGRES_URL:
            raise ValueError("POSTGRES_URL không được để trống. Hãy đặt biến môi trường POSTGRES_URL (ví dụ: postgresql+asyncpg://user:password@host:port/dbname).")

        if not self.REDIS_URL:
            raise ValueError("REDIS_URL không được để trống. Hãy đặt biến môi trường REDIS_URL (ví dụ: redis://localhost:6379/0).")