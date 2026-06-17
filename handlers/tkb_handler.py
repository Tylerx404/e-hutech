#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý thời khóa biểu (TKB) từ hệ thống HUTECH.

Lấy TKB theo tuần (mặc định tuần hiện tại), hỗ trợ xem các tuần trước/sau
và xuất danh sách môn đã chọn ra file `.ics` (iCalendar).

Cú pháp callback:
    tkb_<offset>                 - tuần offset (-1, 0, 1, ...)
    tkb_export_ics_<offset>      - mở menu chọn môn để xuất .ics
    tkb_subject_toggle_<ma_hp>   - bật/tắt chọn môn
    tkb_subject_confirm          - xác nhận xuất
    tkb_subject_cancel           - hủy chọn môn
    tkb_time_all                 - xuất toàn bộ thời gian
    tkb_time_current             - xuất từ tuần hiện tại
    tkb_time_back                - quay lại menu chọn môn

State tạm per user (lưu trong cache):
    tkb_week_offset: int
    tkb_subjects: list
    selected_subjects: list
    tkb_subjects_dict: dict
    tkb_command_message_id: int
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
import pytz
from icalendar import Calendar, Event

from config.config import Config
from utils.button_style import make_inline_button, build_inline_keyboard
from utils.rich_message import (
    escape_html,
    section_heading,
    p_with_emoji,
    h2,
    p_bold,
    p,
    code,
    hr,
    footer,
    footer_updated_at,
    join_blocks,
    kv_line,
    table,
)
from utils.state_store import StateStore
from utils.telegram_api import TelegramAPI, TelegramAPIError

logger = logging.getLogger(__name__)

# Key prefix cho TKB state
TKB_STATE_KEY = "tkb"
TKB_TTL = 1800  # 30 phút


class TkbHandler:
    """Handler cho `/tkb` — xem thời khóa biểu, xuất .ics."""

    def __init__(self, db_manager, cache_manager, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)
        self.state = StateStore(self.cache_manager)

    # ==================== Command ====================

    async def cmd_tkb(self, chat_id: int, user_id: int, args: List[str],
                      reply_to_message_id: Optional[int]) -> None:
        if not await self.db_manager.is_user_logged_in(user_id):
            await self.telegram.send_message(
                chat_id=chat_id,
                text="Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.",
                reply_to_message_id=reply_to_message_id,
            )
            return

        week_offset = 0
        if args:
            try:
                week_offset = int(args[0])
            except (ValueError, IndexError):
                week_offset = 0

        result = await self.handle_tkb(user_id, week_offset)
        if not result["success"]:
            await self.telegram.send_message(
                chat_id=chat_id, text=result["message"], reply_to_message_id=reply_to_message_id
            )
            return

        await self.state.update_state(user_id, {"tkb_week_offset": week_offset})
        await self.telegram.send_rich_message(
            chat_id=chat_id,
            html=self.format_tkb_message(result["data"]),
            reply_markup=self._week_keyboard(week_offset),
            reply_to_message_id=reply_to_message_id,
        )

    # ==================== Callback router ====================

    async def cb_route(self, callback_id: str, chat_id: int, message_id: int,
                       user_id: int, callback_data: str) -> None:
        if callback_data.startswith("tkb_subject_"):
            await self._cb_subject(callback_id, chat_id, message_id, user_id, callback_data)
        elif callback_data.startswith("tkb_time_"):
            await self._cb_time(callback_id, chat_id, message_id, user_id, callback_data)
        elif callback_data.startswith("tkb_export_ics_"):
            await self._cb_export(callback_id, chat_id, message_id, user_id, callback_data)
        elif callback_data.startswith("tkb_"):
            await self._cb_week(callback_id, chat_id, message_id, user_id, callback_data)

    # ==================== Callback implementations ====================

    async def _cb_week(self, callback_id: str, chat_id: int, message_id: int,
                       user_id: int, callback_data: str) -> None:
        try:
            week_offset = int(callback_data.split("_")[1])
        except (ValueError, IndexError):
            week_offset = 0
        await self.telegram.answer_callback_query(callback_id, text="Đang tải thời khóa biểu...")

        result = await self.handle_tkb(user_id, week_offset)
        if not result["success"]:
            try:
                await self.telegram.edit_message_text_plain(
                    chat_id=chat_id, message_id=message_id, text=result["message"]
                )
            except TelegramAPIError:
                pass
            return
        await self.state.update_state(user_id, {"tkb_week_offset": week_offset})
        try:
            await self.telegram.edit_message_text_rich(
                chat_id=chat_id,
                message_id=message_id,
                html=self.format_tkb_message(result["data"]),
                reply_markup=self._week_keyboard(week_offset),
            )
        except TelegramAPIError as e:
            if "message is not modified" not in e.description.lower():
                raise

    async def _cb_export(self, callback_id: str, chat_id: int, message_id: int,
                        user_id: int, callback_data: str) -> None:
        try:
            week_offset = int(callback_data.split("_")[3])
        except (ValueError, IndexError):
            week_offset = 0
        await self.telegram.answer_callback_query(callback_id, text="Đang tải danh sách môn học...")

        result = await self.handle_export_tkb_ics(user_id, week_offset)
        if not result.get("success"):
            await self.telegram.answer_callback_query(
                callback_id, text=f"Lỗi: {result.get('message', 'Không rõ')}", show_alert=True
            )
            return

        subjects = result.get("subjects", [])
        await self.state.update_state(user_id, {
            "tkb_week_offset": week_offset,
            "tkb_subjects": subjects,
            "selected_subjects": [],
            "tkb_subjects_dict": {s.get("ma_hp"): s for s in subjects},
        })

        message = (
            f"📚 <b>Chọn môn học để xuất</b>\n\n"
            f"Tổng số môn học: <code>{len(subjects)}</code>\n"
            f"Đã chọn: 0 môn\n\n"
            f"Vui lòng chọn các môn học bên dưới:"
        )
        try:
            await self.telegram.edit_message_text_plain(
                chat_id=chat_id,
                message_id=message_id,
                text=message,
                reply_markup=self._subject_keyboard(subjects, []),
                parse_mode="HTML",
            )
        except TelegramAPIError:
            pass

    async def _cb_subject(self, callback_id: str, chat_id: int, message_id: int,
                         user_id: int, callback_data: str) -> None:
        st = await self.state.get_state(user_id)
        subjects = st.get("tkb_subjects", [])
        subjects_dict = st.get("tkb_subjects_dict", {})
        selected = list(st.get("selected_subjects", []))

        if callback_data == "tkb_subject_confirm":
            if not selected:
                await self.telegram.answer_callback_query(
                    callback_id, text="Vui lòng chọn ít nhất một môn học!", show_alert=True
                )
                return
            names = [subjects_dict.get(ma, {}).get("ten_hp", ma) for ma in selected if ma in subjects_dict]
            msg = f"✅ <b>Đã chọn {len(selected)} môn học:</b>\n\n" + "\n".join(f"- {n}" for n in names)
            try:
                await self.telegram.edit_message_text_plain(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=msg,
                    reply_markup=self._time_keyboard(),
                    parse_mode="HTML",
                )
            except TelegramAPIError:
                pass
            return

        if callback_data == "tkb_subject_cancel":
            for k in ("tkb_subjects", "selected_subjects", "tkb_subjects_dict", "tkb_week_offset"):
                await self.state.update_state(user_id, {k: None})
            try:
                await self.telegram.edit_message_text_plain(
                    chat_id=chat_id, message_id=message_id,
                    text="❌ <b>Đã hủy xuất file.</b>", parse_mode="HTML",
                )
            except TelegramAPIError:
                pass
            return

        if callback_data.startswith("tkb_subject_toggle_"):
            ma_hp = callback_data[len("tkb_subject_toggle_"):]
            if ma_hp in selected:
                selected.remove(ma_hp)
            else:
                selected.append(ma_hp)
            await self.state.update_state(user_id, {"selected_subjects": selected})
            message = (
                f"📚 <b>Chọn môn học để xuất</b>\n\n"
                f"Tổng số môn học: <code>{len(subjects)}</code>\n"
                f"Đã chọn: {len(selected)} môn\n\n"
                f"Vui lòng chọn các môn học bên dưới:"
            )
            try:
                await self.telegram.edit_message_text_plain(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=message,
                    reply_markup=self._subject_keyboard(subjects, selected),
                    parse_mode="HTML",
                )
            except TelegramAPIError as e:
                if "message is not modified" not in e.description.lower():
                    raise

    async def _cb_time(self, callback_id: str, chat_id: int, message_id: int,
                      user_id: int, callback_data: str) -> None:
        st = await self.state.get_state(user_id)
        selected = st.get("selected_subjects", [])
        subjects_dict = st.get("tkb_subjects_dict", {})

        if callback_data == "tkb_time_back":
            subjects = st.get("tkb_subjects", [])
            message = (
                f"📚 <b>Chọn môn học để xuất</b>\n\n"
                f"Tổng số môn học: <code>{len(subjects)}</code>\n"
                f"Đã chọn: {len(selected)} môn\n\n"
                f"Vui lòng chọn các môn học bên dưới:"
            )
            try:
                await self.telegram.edit_message_text_plain(
                    chat_id=chat_id, message_id=message_id, text=message,
                    reply_markup=self._subject_keyboard(subjects, selected), parse_mode="HTML",
                )
            except TelegramAPIError:
                pass
            return

        if callback_data == "tkb_time_all":
            time_range = "all"
            time_label = "toàn bộ thời gian"
        elif callback_data == "tkb_time_current":
            time_range = "current"
            time_label = "từ tuần hiện tại"
        else:
            return

        await self.telegram.answer_callback_query(
            callback_id, text="Đang tạo file .ics, vui lòng chờ...", show_alert=False
        )

        cache_key = f"tkb:{user_id}"
        cached = await self.cache_manager.get(cache_key)
        if not cached:
            await self.telegram.send_message(
                chat_id=chat_id, text="⚠️ Không tìm thấy dữ liệu TKB. Vui lòng thử lại."
            )
            return

        tkb_raw = cached.get("data")
        all_data = self.get_all_tkb_data(tkb_raw)
        week_offset = st.get("tkb_week_offset", 0)
        file_path = self.create_ics_file(all_data, user_id, week_offset, selected, time_range)

        if not file_path or not os.path.exists(file_path):
            await self.telegram.send_message(
                chat_id=chat_id, text="⚠️ Không có lịch học nào phù hợp với bộ lọc đã chọn."
            )
            return

        names = [subjects_dict.get(ma, {}).get("ten_hp", ma) for ma in selected if ma in subjects_dict]
        subject_list = ", ".join(names) if names else "tất cả các môn"
        caption = (
            f"🗓️ <b>File iCalendar thời khóa biểu</b>\n\n"
            f"Môn học: {subject_list}\n"
            f"Thời gian: {time_label}"
        )
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            await self.telegram.send_document(
                chat_id=chat_id,
                file=file_bytes,
                filename=f"tkb_{user_id}.ics",
                caption=caption,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Lỗi gửi file ICS cho user %s: %s", user_id, e)
            await self.telegram.send_message(
                chat_id=chat_id, text="Có lỗi xảy ra khi gửi file."
            )
        finally:
            try:
                os.remove(file_path)
            except OSError:
                pass
            await self.telegram.delete_message(chat_id, message_id)

        for k in ("tkb_subjects", "selected_subjects", "tkb_subjects_dict", "tkb_week_offset"):
            await self.state.update_state(user_id, {k: None})

    # ==================== Data layer ====================

    async def handle_tkb(self, telegram_user_id: int, week_offset: int = 0) -> Dict[str, Any]:
        try:
            cache_key = f"tkb:{telegram_user_id}"
            cached = await self.cache_manager.get(cache_key)
            if cached:
                tkb_data = cached.get("data")
                timestamp = cached.get("timestamp")
                processed = self._process_tkb_data(tkb_data, week_offset)
                processed["timestamp"] = timestamp
                return {"success": True, "message": "Lấy thời khóa biểu thành công", "data": processed}

            token = await self._get_user_token(telegram_user_id)
            if not token:
                return {"success": False, "message": "Bạn chưa đăng nhập. Vui lòng /dangnhap.", "data": None}

            response = await self._call_tkb_api(token)
            if response and isinstance(response, list):
                await self.cache_manager.set(cache_key, response, ttl=3600)
                processed = self._process_tkb_data(response, week_offset)
                cached_data = await self.cache_manager.get(cache_key)
                processed["timestamp"] = (
                    cached_data.get("timestamp") if cached_data else datetime.utcnow().isoformat()
                )
                return {"success": True, "message": "Lấy thời khóa biểu thành công", "data": processed}
            return {"success": False, "message": "Không thể lấy dữ liệu thời khóa biểu", "data": response}
        except Exception as e:
            logger.error("TKB error for user %s: %s", telegram_user_id, e)
            return {"success": False, "message": f"Lỗi: {str(e)}", "data": None}

    async def handle_export_tkb_ics(self, telegram_user_id: int, week_offset: int = 0) -> Dict[str, Any]:
        try:
            cache_key = f"tkb:{telegram_user_id}"
            cached = await self.cache_manager.get(cache_key)
            tkb_raw = None
            if cached:
                tkb_raw = cached.get("data")
            else:
                token = await self._get_user_token(telegram_user_id)
                if not token:
                    return {"success": False, "message": "Bạn chưa đăng nhập."}
                response = await self._call_tkb_api(token)
                if response and isinstance(response, list):
                    await self.cache_manager.set(cache_key, response, ttl=3600)
                    tkb_raw = response
                else:
                    return {"success": False, "message": "Không thể lấy dữ liệu TKB từ API."}

            if not tkb_raw:
                return {"success": False, "message": "Không có dữ liệu TKB để xuất."}
            subjects = self.get_all_tkb_data(tkb_raw).get("subjects", [])
            if not subjects:
                return {"success": False, "message": "Không có môn học nào để xuất."}
            return {
                "success": True, "message": "Chọn môn học để xuất",
                "keyboard": self._subject_keyboard(subjects, []),
                "subjects": subjects, "week_offset": week_offset,
            }
        except Exception as e:
            logger.error("ICS export error for user %s: %s", telegram_user_id, e)
            return {"success": False, "message": f"Lỗi khi xuất file: {str(e)}"}

    async def _call_tkb_api(self, token: str) -> Optional[Any]:
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_TKB_ENDPOINT}"
            headers = self.config.HUTECH_MOBILE_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json={}) as response:
                    if response.status == 201:
                        return await response.json()
                    return {"error": True, "status_code": response.status, "message": await response.text()}
        except aiohttp.ClientError as e:
            return {"error": True, "message": f"Lỗi kết nối: {str(e)}"}
        except json.JSONDecodeError as e:
            return {"error": True, "message": f"Lỗi phân tích dữ liệu: {str(e)}"}
        except Exception as e:
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

    # ==================== Process & format ====================

    def get_all_tkb_data(self, tkb_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            all_subjects = [
                s for s in tkb_data
                if s.get("chi_tiet_tkb") and isinstance(s["chi_tiet_tkb"], list)
            ]
            all_subjects.sort(key=lambda x: min(
                [datetime.strptime(s["ngay_hoc"], "%d/%m/%Y") for s in x["chi_tiet_tkb"] if "ngay_hoc" in s],
                default=datetime.max,
            ))
            return {"subjects": all_subjects}
        except Exception as e:
            logger.error("Error processing all TKB data: %s", e)
            return {"subjects": []}

    def _process_tkb_data(self, tkb_data: List[Dict[str, Any]], week_offset: int) -> Dict[str, Any]:
        try:
            today = datetime.now()
            days_since_monday = today.weekday()
            monday = today - timedelta(days=days_since_monday)
            target_monday = monday + timedelta(weeks=week_offset)
            target_sunday = target_monday + timedelta(days=6)
            week_start_str = target_monday.strftime("%d/%m/%Y")
            week_end_str = target_sunday.strftime("%d/%m/%Y")

            all_subjects = self.get_all_tkb_data(tkb_data).get("subjects", [])
            week_subjects = []
            for subject in all_subjects:
                week_schedules = []
                for schedule in subject.get("chi_tiet_tkb", []):
                    try:
                        schedule_date = datetime.strptime(schedule["ngay_hoc"], "%d/%m/%Y")
                        if target_monday.date() <= schedule_date.date() <= target_sunday.date():
                            week_schedules.append(schedule)
                    except (ValueError, KeyError):
                        continue
                if week_schedules:
                    subject_copy = subject.copy()
                    subject_copy["chi_tiet_tkb"] = week_schedules
                    week_subjects.append(subject_copy)

            def sort_key(x):
                thu_vals = [int(s.get("thu", 8)) if s.get("thu") is not None else 8 for s in x.get("chi_tiet_tkb", [])]
                tiet_vals = [int(s.get("tiet_bd", 16)) if s.get("tiet_bd") is not None else 16 for s in x.get("chi_tiet_tkb", [])]
                return (min(thu_vals) if thu_vals else 8, min(tiet_vals) if tiet_vals else 16)
            week_subjects.sort(key=sort_key)

            return {
                "week_start": week_start_str,
                "week_end": week_end_str,
                "week_offset": week_offset,
                "subjects": week_subjects,
            }
        except Exception as e:
            logger.error("Error processing TKB data: %s", e)
            return {"week_start": "", "week_end": "", "week_offset": week_offset, "subjects": []}

    def format_tkb_message(self, tkb_data: Dict[str, Any]) -> str:
        week_start = tkb_data.get("week_start", "")
        week_end = tkb_data.get("week_end", "")
        week_offset = tkb_data.get("week_offset", 0)
        subjects = tkb_data.get("subjects", [])
        timestamp_str = tkb_data.get("timestamp")

        if week_offset == 0:
            title = "Thời Khóa Biểu - Tuần Hiện Tại"
        elif week_offset > 0:
            title = f"Thời Khóa Biểu - Tuần Tới (+{week_offset})"
        else:
            title = f"Thời Khóa Biểu - Tuần Trước ({week_offset})"

        if not subjects:
            return join_blocks([
                section_heading("📅", title),
                p_with_emoji("🗓️", f"{week_start} - {week_end}"),
                p("🎉 Tuyệt vời! Tuần này bạn không có lịch học."),
                footer_updated_at(timestamp_str),
            ])

        # Nhãn ngắn cho cột "Thứ" trong bảng
        day_short_labels = {
            2: "T2", 3: "T3", 4: "T4", 5: "T5",
            6: "T6", 7: "T7", 8: "CN",
        }

        # Gom tất cả buổi học trong tuần thành 1 danh sách phẳng
        flat_schedules: List[Dict[str, Any]] = []
        for subject in subjects:
            for schedule in subject.get("chi_tiet_tkb", []):
                try:
                    day = int(schedule.get("thu", 0))
                except (ValueError, TypeError):
                    continue
                if 2 <= day <= 8:
                    flat_schedules.append({"subject": subject, "schedule": schedule, "day": day})

        flat_schedules.sort(
            key=lambda x: (
                x["day"],
                int(x["schedule"].get("tiet_bd", 0) or 0),
            )
        )

        rows: List[List[str]] = []
        for item in flat_schedules:
            subject = item["subject"]
            schedule = item["schedule"]
            day = item["day"]
            subject_name = subject.get("ten_hp", "N/A")
            subject_code = subject.get("ma_hp", "N/A")
            room = schedule.get("phong_hoc") or "—"
            try:
                start_period = int(schedule.get("tiet_bd", 0) or 0)
                num_periods = int(schedule.get("so_tiet", 0) or 0)
                start_time = self._period_to_time(start_period)
                end_time = self._period_to_time(start_period, num_periods)
                time_str = f"{start_time}-{end_time}" if start_time != "??:??" else "—"
            except (ValueError, TypeError):
                time_str = "—"
            rows.append([
                day_short_labels.get(day, f"T{day}"),
                subject_name or "—",
                subject_code or "—",
                time_str,
                room,
            ])

        blocks: List[str] = [
            section_heading("📅", title),
            p_with_emoji("🗓️", f"{week_start} - {week_end}"),
            table(
                ["Thứ", "Môn học", "Mã HP", "Thời gian", "Phòng"],
                rows,
                bordered=True,
                striped=True,
            ),
        ]

        ts_footer = footer_updated_at(timestamp_str)
        if ts_footer:
            blocks.append(ts_footer)
        return join_blocks(blocks)

    @staticmethod
    def _period_to_time(start_period: int, num_periods: int = 0) -> str:
        try:
            start_times = {
                1: "06:45", 2: "07:30", 3: "08:15",
                4: "09:20", 5: "10:05", 6: "10:50",
                7: "12:30", 8: "13:15", 9: "14:00",
                10: "15:05", 11: "15:50", 12: "16:35",
                13: "18:00", 14: "18:45", 15: "19:30",
            }
            if start_period not in start_times:
                return "??:??"
            if num_periods == 0:
                return start_times[start_period]
            end_period = start_period + num_periods - 1
            if start_period >= 1 and end_period <= 3:
                return "09:00"
            if start_period >= 4 and end_period <= 6:
                return "11:35"
            if start_period >= 7 and end_period <= 9:
                return "14:45"
            if start_period >= 10 and end_period <= 12:
                return "17:20"
            if start_period >= 13 and end_period <= 15:
                return "20:15"
            if end_period <= 6:
                return "11:35"
            if end_period <= 9:
                return "14:45"
            if end_period <= 12:
                return "16:35"
            if end_period <= 15:
                return "20:15"
            return "??:??"
        except (ValueError, TypeError):
            return "??:??"

    # ==================== ICS export ====================

    def create_ics_file(self, tkb_data: Dict[str, Any], telegram_user_id: int, week_offset: int = 0,
                        selected_subjects: Optional[List[str]] = None, time_range: str = "all") -> Optional[str]:
        try:
            cal = Calendar()
            cal.add("prodid", "-//HUTECH TKB Bot//hutech.edu.vn//")
            cal.add("version", "2.0")
            local_tz = pytz.timezone("Asia/Ho_Chi_Minh")
            subjects = tkb_data.get("subjects", [])
            if not subjects:
                return None
            if selected_subjects is None:
                selected_subjects = []
            today = datetime.now()
            days_since_monday = today.weekday()
            monday = today - timedelta(days=days_since_monday)
            if time_range == "current":
                filter_start_date = monday + timedelta(weeks=week_offset)
            else:
                filter_start_date = datetime.min
            for subject in subjects:
                subject_name = subject.get("ten_hp", "N/A")
                subject_code = subject.get("ma_hp", "N/A")
                if selected_subjects and subject_code not in selected_subjects:
                    continue
                for schedule in subject.get("chi_tiet_tkb", []):
                    try:
                        event = Event()
                        room = schedule.get("phong_hoc", "N/A")
                        ngay_hoc_str = schedule.get("ngay_hoc")
                        start_period = int(schedule.get("tiet_bd", 0))
                        num_periods = int(schedule.get("so_tiet", 0))
                        if not ngay_hoc_str or start_period == 0:
                            continue
                        schedule_date = datetime.strptime(ngay_hoc_str, "%d/%m/%Y")
                        if schedule_date < filter_start_date:
                            continue
                        start_time_str = self._period_to_time(start_period)
                        end_time_str = self._period_to_time(start_period, num_periods)
                        start_dt = datetime.strptime(f"{ngay_hoc_str} {start_time_str}", "%d/%m/%Y %H:%M")
                        end_dt = datetime.strptime(f"{ngay_hoc_str} {end_time_str}", "%d/%m/%Y %H:%M")
                        start_dt_local = local_tz.localize(start_dt)
                        end_dt_local = local_tz.localize(end_dt)
                        event.add("summary", subject_name)
                        event.add("dtstart", start_dt_local)
                        event.add("dtend", end_dt_local)
                        event.add("dtstamp", datetime.now(pytz.utc))
                        event.add("location", room)
                        event.add("description", f"Mã HP: {subject_code}\nPhòng: {room}")
                        cal.add_component(event)
                    except (ValueError, TypeError) as e:
                        logger.warning("Skipping event due to processing error: %s", e)
                        continue
            temp_dir = "temp"
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            file_path = os.path.join(temp_dir, f"tkb_{telegram_user_id}.ics")
            with open(file_path, "wb") as f:
                f.write(cal.to_ical())
            return file_path
        except Exception as e:
            logger.error("Error creating ICS file for user %s: %s", telegram_user_id, e)
            return None

    # ==================== Keyboards ====================

    def _week_keyboard(self, week_offset: int) -> Dict[str, Any]:
        return build_inline_keyboard([
            [
                make_inline_button("Tuần trước", f"tkb_{week_offset - 1}", tone=None),
                make_inline_button("Tuần hiện tại", "tkb_0", tone=None),
                make_inline_button("Tuần tới", f"tkb_{week_offset + 1}", tone=None),
            ],
            [
                make_inline_button("Xuất iCalendar (.ics)", f"tkb_export_ics_{week_offset}", tone="warning", emoji="🗓️"),
            ],
        ])

    def _subject_keyboard(self, subjects: List[Dict[str, Any]], selected: List[str]) -> Dict[str, Any]:
        rows: List[List[Dict[str, Any]]] = []
        for subject in subjects:
            ma_hp = subject.get("ma_hp", "")
            ten_hp = subject.get("ten_hp", "")
            text = f"{ten_hp} ({ma_hp})"
            tone = "primary" if ma_hp in selected else None
            rows.append([make_inline_button(text, f"tkb_subject_toggle_{ma_hp}", tone=tone)])
        rows.append([
            make_inline_button("Xác nhận", "tkb_subject_confirm", tone="success"),
            make_inline_button("Hủy", "tkb_subject_cancel", tone="danger"),
        ])
        return build_inline_keyboard(rows)

    def _time_keyboard(self) -> Dict[str, Any]:
        return build_inline_keyboard([
            [
                make_inline_button("Toàn bộ thời gian", "tkb_time_all", tone=None, emoji="📅"),
                make_inline_button("Từ tuần hiện tại", "tkb_time_current", tone=None, emoji="📆"),
            ],
            [
                make_inline_button("Quay lại", "tkb_time_back", tone="neutral"),
            ],
        ])
