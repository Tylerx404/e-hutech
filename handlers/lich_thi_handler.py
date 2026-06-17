#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý lịch thi từ hệ thống HUTECH.

Sử dụng Rich Message (Bot API 10.1):
- Danh sách môn thi theo từng học kỳ: bảng <table bordered striped> với các cột
  (Môn học, Mã HP, Ngày thi, Giờ thi, Phòng, Hình thức, Thời lượng).

Cú pháp: gửi /lichthi để xem tất cả lịch thi sắp tới.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

from config.config import Config
from utils.rich_message import (
    section_heading,
    p,
    p_with_emoji,
    hr,
    footer_updated_at,
    table,
    join_blocks,
)
from utils.telegram_api import TelegramAPI

logger = logging.getLogger(__name__)


class LichThiHandler:
    def __init__(self, db_manager, cache_manager, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)

    # ==================== Command ====================

    async def cmd_lichthi(self, chat_id: int, user_id: int, reply_to_message_id: Optional[int]) -> None:
        if not await self.db_manager.is_user_logged_in(user_id):
            await self.telegram.send_message(
                chat_id=chat_id,
                text="Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.",
                reply_to_message_id=reply_to_message_id,
            )
            return

        result = await self.handle_lich_thi(user_id)
        if result["success"]:
            await self.telegram.send_rich_message(
                chat_id=chat_id,
                html=self._format_message(result["data"]),
                reply_to_message_id=reply_to_message_id,
            )
        else:
            await self.telegram.send_message(
                chat_id=chat_id,
                text=f"Không thể lấy lịch thi: {result.get('message', 'Lỗi không xác định')}",
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id,
            )

    # ==================== Data layer ====================

    async def handle_lich_thi(self, telegram_user_id: int) -> Dict[str, Any]:
        try:
            cache_key = f"lichthi:{telegram_user_id}"
            cached = await self.cache_manager.get(cache_key)
            if cached:
                processed = self._process(cached.get("data"))
                processed["timestamp"] = cached.get("timestamp")
                return {"success": True, "message": "Lấy lịch thi thành công", "data": processed}

            token = await self._get_user_token(telegram_user_id)
            if not token:
                return {
                    "success": False,
                    "message": "Bạn chưa đăng nhập. Vui lòng sử dụng /dangnhap để đăng nhập.",
                    "data": None,
                }

            response = await self._call_api(token)
            if response and isinstance(response, list):
                await self.cache_manager.set(cache_key, response, ttl=86400)
                processed = self._process(response)
                cached_data = await self.cache_manager.get(cache_key)
                processed["timestamp"] = (
                    cached_data.get("timestamp") if cached_data else datetime.utcnow().isoformat()
                )
                return {
                    "success": True,
                    "message": "Lấy lịch thi thành công (dữ liệu mới)",
                    "data": processed,
                }
            return {
                "success": True,
                "message": "📅 *Lịch Thi*\n\nKhông có lịch thi nào được tìm thấy.",
                "data": {"hocky_data": {}, "timestamp": datetime.utcnow().isoformat()},
            }
        except Exception as e:
            logger.error("Lịch thi error for user %s: %s", telegram_user_id, e)
            return {
                "success": False,
                "message": f"🚫 *Lỗi*\n\nĐã xảy ra lỗi khi lấy lịch thi: {str(e)}",
                "data": None,
            }

    async def _call_api(self, token: str) -> Optional[Any]:
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_LICHTHI_ENDPOINT}"
            headers = self.config.HUTECH_MOBILE_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json={}) as response:
                    if response.status == 201:
                        return await response.json()
                    error_text = await response.text()
                    logger.error("Lịch thi API error: %s - %s", response.status, error_text)
                    return {"error": True, "status_code": response.status, "message": error_text}
        except aiohttp.ClientError as e:
            logger.error("HTTP client error: %s", e)
            return {"error": True, "message": f"Lỗi kết nối: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error("JSON decode error: %s", e)
            return {"error": True, "message": f"Lỗi phân tích dữ liệu: {str(e)}"}
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return {"error": True, "message": f"Lỗi không xác định: {str(e)}"}

    async def _get_user_token(self, telegram_user_id: int) -> Optional[str]:
        try:
            response_data = await self.db_manager.get_user_login_response(telegram_user_id)
            if not response_data:
                return None
            old_login_info = response_data.get("old_login_info")
            if isinstance(old_login_info, dict) and old_login_info.get("token"):
                return old_login_info["token"]
            return response_data.get("token")
        except Exception as e:
            logger.error("Error getting token for user %s: %s", telegram_user_id, e)
            return None

    @staticmethod
    def _process(lich_thi_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            hocky_data: Dict[str, Any] = {}
            for hocky in lich_thi_data:
                if "nam_hoc_hoc_ky" in hocky and "lich_thi" in hocky:
                    key = hocky["nam_hoc_hoc_ky"]
                    lich_thi_list = sorted(
                        hocky.get("lich_thi", []),
                        key=lambda x: x.get("ngay_thi", ""),
                    )
                    hocky_data[key] = {
                        "hocky_name": hocky.get("nam_hoc_hoc_ky_name", ""),
                        "lich_thi": lich_thi_list,
                    }
            return {"hocky_data": hocky_data}
        except Exception as e:
            logger.error("Error processing lịch thi data: %s", e)
            return {"hocky_data": {}}

    def _format_message(self, lich_thi_data: Dict[str, Any]) -> str:
        hocky_data = lich_thi_data.get("hocky_data", {})
        timestamp_str = lich_thi_data.get("timestamp")
        if not hocky_data:
            return join_blocks([
                section_heading("📅", "Lịch Thi"),
                p("Không có lịch thi nào được tìm thấy."),
                footer_updated_at(timestamp_str),
            ])

        blocks: List[str] = [section_heading("📅", "Lịch Thi Sắp Tới")]
        sorted_keys = sorted(hocky_data.keys(), reverse=True)
        for key in sorted_keys:
            data = hocky_data[key]
            hocky_name = data.get("hocky_name", "N/A")
            lich_thi_list = data.get("lich_thi", [])
            if not lich_thi_list:
                continue
            blocks.append(p_with_emoji("🎓", hocky_name))
            rows: List[List[str]] = []
            for mon_thi in lich_thi_list:
                rows.append(self._exam_row(mon_thi))
            blocks.append(table(
                ["Môn học", "Mã HP", "Ngày thi", "Giờ thi", "Phòng", "Hình thức", "Thời lượng"],
                rows,
                bordered=True,
                striped=True,
            ))

        ts = footer_updated_at(timestamp_str)
        if ts:
            blocks.append(ts)
        return join_blocks(blocks)

    @staticmethod
    def _exam_row(mon_thi: Dict[str, Any]) -> List[str]:
        ten_hp = mon_thi.get("ten_hp") or "—"
        ma_hp = mon_thi.get("ma_hp") or "—"
        ngay_thi = mon_thi.get("ngay_thi", "N/A")
        gio_thi = mon_thi.get("gio_thi") or "—"
        phong_thi = mon_thi.get("phong_thi") or "—"
        hinh_thuc_thi = mon_thi.get("hinh_thuc_thi") or "—"
        so_phut = mon_thi.get("so_phut")
        try:
            ngay_thi_dt = datetime.strptime(ngay_thi, "%Y-%m-%d")
            ngay_thi_str = ngay_thi_dt.strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            ngay_thi_str = ngay_thi or "—"
        thoi_luong = f"{so_phut} phút" if so_phut not in (None, "", "N/A") else "—"
        return [
            ten_hp, ma_hp, ngay_thi_str, gio_thi, phong_thi,
            hinh_thuc_thi, thoi_luong,
        ]
