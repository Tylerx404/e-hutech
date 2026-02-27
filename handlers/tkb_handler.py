#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý thời khóa biểu (TKB) từ hệ thống HUTECH
"""

import json
import logging
import aiohttp
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from icalendar import Calendar, Event
import pytz
import os

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

from config.config import Config
from utils.button_style import make_inline_button

logger = logging.getLogger(__name__)

class TkbHandler:
    def __init__(self, db_manager, cache_manager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
    
    async def handle_tkb(self, telegram_user_id: int, week_offset: int = 0) -> Dict[str, Any]:
        """
        Xử lý lấy thời khóa biểu của người dùng
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            week_offset: Tuần hiện tại + week_offset (0 = tuần hiện tại, 1 = tuần tới, -1 = tuần trước)
            
        Returns:
            Dict chứa kết quả và dữ liệu thời khóa biểu
        """
        try:
            # Tạo cache key
            cache_key = f"tkb:{telegram_user_id}"

            # 1. Kiểm tra cache trước
            cached_result = await self.cache_manager.get(cache_key)
            if cached_result:
                # Xử lý dữ liệu từ cache
                tkb_data = cached_result.get("data")
                timestamp = cached_result.get("timestamp")
                
                processed_data = self._process_tkb_data(tkb_data, week_offset)
                processed_data["timestamp"] = timestamp # Thêm timestamp vào dữ liệu đã xử lý

                return {
                    "success": True,
                    "message": "Lấy thời khóa biểu thành công",
                    "data": processed_data,
                    "week_offset": week_offset
                }

            # 2. Nếu cache miss, gọi API
            token = await self._get_user_token(telegram_user_id)
            
            if not token:
                return {
                    "success": False,
                    "message": "Bạn chưa đăng nhập. Vui lòng sử dụng /login để đăng nhập.",
                    "data": None
                }
            
            response_data = await self._call_tkb_api(token)
            
            # 3. Lưu vào cache và database
            if response_data and isinstance(response_data, list):
                await self.cache_manager.set(cache_key, response_data, ttl=3600) # Cache trong 1 giờ
                # await self._save_tkb_response(telegram_user_id, response_data, 0) # Đã chuyển sang Redis
            
            # Kiểm tra kết quả
            if response_data and isinstance(response_data, list):
                # Xử lý dữ liệu thời khóa biểu theo tuần
                processed_data = self._process_tkb_data(response_data, week_offset)
                # Lấy timestamp từ cache manager để đồng bộ
                cached_data = await self.cache_manager.get(cache_key)
                if cached_data:
                    processed_data["timestamp"] = cached_data.get("timestamp")
                else:
                    processed_data["timestamp"] = datetime.utcnow().isoformat()

                return {
                    "success": True,
                    "message": "Lấy thời khóa biểu thành công (dữ liệu mới)",
                    "data": processed_data,
                    "week_offset": week_offset
                }
            else:
                return {
                    "success": False,
                    "message": "Không thể lấy dữ liệu thời khóa biểu",
                    "data": response_data
                }
        
        except Exception as e:
            logger.error(f"TKB error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"Lỗi lấy thời khóa biểu: {str(e)}",
                "data": None
            }

    async def handle_export_tkb_ics(self, telegram_user_id: int, week_offset: int = 0) -> Dict[str, Any]:
        """
        Xử lý yêu cầu xuất TKB ra file iCalendar (.ics).
        Trả về keyboard chọn môn học nếu chưa có danh sách môn được chọn.
        """
        try:
            # 1. Lấy dữ liệu TKB (ưu tiên cache)
            cache_key = f"tkb:{telegram_user_id}"
            cached_result = await self.cache_manager.get(cache_key)

            tkb_raw_data = None
            if cached_result:
                tkb_raw_data = cached_result.get("data")
            else:
                token = await self._get_user_token(telegram_user_id)
                if not token:
                    return {"success": False, "message": "Bạn chưa đăng nhập."}

                response_data = await self._call_tkb_api(token)
                if response_data and isinstance(response_data, list):
                    await self.cache_manager.set(cache_key, response_data, ttl=3600)
                    tkb_raw_data = response_data
                else:
                    return {"success": False, "message": "Không thể lấy dữ liệu TKB từ API."}

            if not tkb_raw_data:
                return {"success": False, "message": "Không có dữ liệu TKB để xuất."}

            # 2. Lấy danh sách môn học
            all_tkb_data = self.get_all_tkb_data(tkb_raw_data)
            subjects = all_tkb_data.get("subjects", [])

            if not subjects:
                return {"success": False, "message": "Không có môn học nào để xuất."}

            # 3. Tạo keyboard chọn môn học
            keyboard = self.create_subject_selection_keyboard(subjects)

            return {
                "success": True,
                "message": "Chọn môn học để xuất",
                "keyboard": keyboard,
                "subjects": subjects,
                "week_offset": week_offset
            }

        except Exception as e:
            logger.error(f"ICS export error for user {telegram_user_id}: {e}")
            return {"success": False, "message": f"Lỗi khi xuất file: {str(e)}"}
    
    async def _call_tkb_api(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Gọi API thời khóa biểu của HUTECH
        
        Args:
            token: Token xác thực
            
        Returns:
            Response data từ API hoặc None nếu có lỗi
        """
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_TKB_ENDPOINT}"
            
            # Tạo headers riêng cho API thời khóa biểu
            headers = self.config.HUTECH_MOBILE_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json={}  # Request body rỗng theo tài liệu
                ) as response:
                    if response.status == 201:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"TKB API error: {response.status} - {error_text}")
                        return {
                            "error": True,
                            "status_code": response.status,
                            "message": error_text
                        }
        
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error: {e}")
            return {
                "error": True,
                "message": f"Lỗi kết nối: {str(e)}"
            }
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {
                "error": True,
                "message": f"Lỗi phân tích dữ liệu: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {
                "error": True,
                "message": f"Lỗi không xác định: {str(e)}"
            }
    
    
    async def _get_user_token(self, telegram_user_id: int) -> Optional[str]:
        """
        Lấy token của người dùng từ database (ưu tiên token từ old_login_info cho các API cũ).
        """
        try:
            response_data = await self.db_manager.get_user_login_response(telegram_user_id)
            if not response_data:
                return None

            # Ưu tiên sử dụng token từ old_login_info cho các API elearning cũ
            old_login_info = response_data.get("old_login_info")
            if isinstance(old_login_info, dict) and old_login_info.get("token"):
                return old_login_info["token"]

            # Nếu không, sử dụng token chính
            return response_data.get("token")

        except Exception as e:
            logger.error(f"Error getting token for user {telegram_user_id}: {e}")
            return None

    def create_subject_selection_keyboard(
        self,
        subjects: List[Dict[str, Any]],
        selected_subjects: Optional[List[str]] = None,
    ) -> InlineKeyboardMarkup:
        """
        Tạo keyboard chọn môn học bằng tone màu theo trạng thái chọn.

        Args:
            subjects: Danh sách môn học.
            selected_subjects: Danh sách mã học phần đã chọn.

        Returns:
            InlineKeyboardMarkup với các nút chọn môn học.
        """
        keyboard = []
        selected_subjects_set = set(selected_subjects or [])

        # Tạo nút cho từng môn học
        for subject in subjects:
            ma_hp = subject.get("ma_hp", "")
            ten_hp = subject.get("ten_hp", "")
            button_text = f"{ten_hp} ({ma_hp})"
            callback_data = f"tkb_subject_toggle_{ma_hp}"
            tone = "primary" if ma_hp in selected_subjects_set else None
            keyboard.append([make_inline_button(button_text, callback_data, tone=tone)])

        # Thêm nút xác nhận và hủy
        keyboard.append([
            make_inline_button("Xác nhận", "tkb_subject_confirm", tone="success", emoji=None),
            make_inline_button("Hủy", "tkb_subject_cancel", tone="danger", emoji=None)
        ])

        return InlineKeyboardMarkup(keyboard)

    def create_time_range_keyboard(self) -> InlineKeyboardMarkup:
        """
        Tạo keyboard chọn khoảng thời gian.

        Returns:
            InlineKeyboardMarkup với các nút chọn thời gian.
        """
        keyboard = [
            [
                make_inline_button("Toàn bộ thời gian", "tkb_time_all", tone=None, emoji="📅"),
                make_inline_button("Từ tuần hiện tại", "tkb_time_current", tone=None, emoji="📆")
            ],
            [
                make_inline_button("Quay lại", "tkb_time_back", tone="neutral", emoji=None)
            ]
        ]

        return InlineKeyboardMarkup(keyboard)
    
    def get_all_tkb_data(self, tkb_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Xử lý và trả về toàn bộ dữ liệu TKB có lịch học chi tiết.

        Args:
            tkb_data: Dữ liệu TKB thô từ API.

        Returns:
            Dữ liệu đã xử lý chứa tất cả các môn học.
        """
        try:
            all_subjects = []
            for subject in tkb_data:
                # Chỉ lấy những môn có lịch học chi tiết
                if subject.get("chi_tiet_tkb") and isinstance(subject["chi_tiet_tkb"], list):
                    all_subjects.append(subject)
            
            # Sắp xếp các môn học theo ngày học đầu tiên
            all_subjects.sort(key=lambda x: min(
                [datetime.strptime(s["ngay_hoc"], "%d/%m/%Y") for s in x["chi_tiet_tkb"] if "ngay_hoc" in s],
                default=datetime.max
            ))

            return {"subjects": all_subjects}
        except Exception as e:
            logger.error(f"Error processing all TKB data: {e}")
            return {"subjects": []}

    def _process_tkb_data(self, tkb_data: List[Dict[str, Any]], week_offset: int) -> Dict[str, Any]:
        """
        Xử lý dữ liệu thời khóa biểu theo tuần
        
        Args:
            tkb_data: Dữ liệu thời khóa biểu thô từ API
            week_offset: Tuần hiện tại + week_offset
            
        Returns:
            Dữ liệu đã được xử lý theo tuần
        """
        try:
            # Lấy ngày hiện tại
            today = datetime.now()
            
            # Tính ngày đầu tuần (Thứ 2)
            days_since_monday = today.weekday()
            monday = today - timedelta(days=days_since_monday)
            
            # Tính ngày đầu tuần theo offset
            target_monday = monday + timedelta(weeks=week_offset)
            
            # Tính ngày cuối tuần (Chủ nhật)
            target_sunday = target_monday + timedelta(days=6)
            
            # Định dạng ngày để hiển thị
            week_start_str = target_monday.strftime("%d/%m/%Y")
            week_end_str = target_sunday.strftime("%d/%m/%Y")
            
            # Lấy toàn bộ môn học có lịch
            all_subjects_data = self.get_all_tkb_data(tkb_data)
            all_subjects = all_subjects_data.get("subjects", [])

            # Lọc các môn học có lịch trong tuần được chọn
            week_subjects = []
            
            for subject in all_subjects:
                # Lọc các buổi học trong tuần được chọn
                week_schedules = []
                for schedule in subject["chi_tiet_tkb"]:
                    try:
                        schedule_date = datetime.strptime(schedule["ngay_hoc"], "%d/%m/%Y")
                        if target_monday.date() <= schedule_date.date() <= target_sunday.date():
                            week_schedules.append(schedule)
                    except (ValueError, KeyError):
                        continue
                
                # Nếu có lịch học trong tuần, thêm vào danh sách
                if week_schedules:
                    subject_copy = subject.copy()
                    subject_copy["chi_tiet_tkb"] = week_schedules
                    week_subjects.append(subject_copy)
            
            # Sắp xếp theo thứ và tiết bắt đầu
            week_subjects.sort(key=lambda x: (
                min([int(s.get("thu", 8)) if s.get("thu") is not None else 8 for s in x.get("chi_tiet_tkb", [])]),
                min([int(s.get("tiet_bd", 16)) if s.get("tiet_bd") is not None else 16 for s in x.get("chi_tiet_tkb", [])])
            ))
            
            return {
                "week_start": week_start_str,
                "week_end": week_end_str,
                "week_offset": week_offset,
                "subjects": week_subjects
            }
        
        except Exception as e:
            logger.error(f"Error processing TKB data: {e}")
            return {
                "week_start": "",
                "week_end": "",
                "week_offset": week_offset,
                "subjects": []
            }
    
    def format_tkb_message(self, tkb_data: Dict[str, Any]) -> str:
        """
        Định dạng dữ liệu thời khóa biểu thành tin nhắn
        
        Args:
            tkb_data: Dữ liệu thời khóa biểu đã được xử lý
            
        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            week_start = tkb_data.get("week_start", "")
            week_end = tkb_data.get("week_end", "")
            week_offset = tkb_data.get("week_offset", 0)
            subjects = tkb_data.get("subjects", [])
            timestamp_str = tkb_data.get("timestamp")
            
            # Tạo tiêu đề
            if week_offset == 0:
                title = "📅 *Thời Khóa Biểu - Tuần Hiện Tại*"
            elif week_offset > 0:
                title = f"📅 *Thời Khóa Biểu - Tuần Tới (+{week_offset})*"
            else:
                title = f"📅 *Thời Khóa Biểu - Tuần Trước ({week_offset})*"
            
            message = f"{title}\n"
            message += f"🗓️ `{week_start} - {week_end}`\n"
            
            # Kiểm tra nếu không có môn học nào
            if not subjects:
                message += "\n🎉 *Tuyệt vời!* Tuần này bạn không có lịch học."
                if timestamp_str:
                    try:
                        ts_utc = datetime.fromisoformat(timestamp_str)
                        ts_local = ts_utc + timedelta(hours=7)
                        message += f"\n\n_Dữ liệu cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}_"
                    except (ValueError, TypeError):
                        pass
                return message

            # Nhóm lịch học theo ngày
            schedules_by_day = {day: [] for day in range(2, 9)}  # 2-7: T2-T7, 8: CN

            for subject in subjects:
                for schedule in subject.get("chi_tiet_tkb", []):
                    try:
                        day = int(schedule.get("thu", 0))
                        if 2 <= day <= 8:
                            schedules_by_day[day].append({
                                "subject": subject,
                                "schedule": schedule
                            })
                    except (ValueError, TypeError):
                        continue
            
            # Hiển thị lịch học
            has_schedule = False
            week_days = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
            
            for day_code, day_name in zip(range(2, 9), week_days):
                day_schedules = schedules_by_day.get(day_code, [])
                if day_schedules:
                    has_schedule = True
                    message += f"\n\n- - - - - *{day_name.upper()}* - - - - -\n"
                    
                    day_schedules.sort(key=lambda x: int(x["schedule"].get("tiet_bd", 0)))
                    
                    for item in day_schedules:
                        subject = item["subject"]
                        schedule = item["schedule"]
                        
                        subject_name = subject.get("ten_hp", "N/A")
                        subject_code = subject.get("ma_hp", "N/A")
                        room = schedule.get("phong_hoc", "N/A")
                        
                        try:
                            start_period = int(schedule.get("tiet_bd", 0))
                            num_periods = int(schedule.get("so_tiet", 0))
                            start_time = self._period_to_time(start_period)
                            end_time = self._period_to_time(start_period, num_periods)
                            time_str = f"{start_time} - {end_time}"
                        except (ValueError, TypeError):
                            time_str = "N/A"

                        message += f"\n📚 *{subject_name}*\n"
                        message += f"   - *Mã HP:* `{subject_code}`\n"
                        message += f"   - *Thời gian:* {time_str}\n"
                        message += f"   - *Phòng:* `{room}`\n"

            if not has_schedule:
                message += "\n🎉 *Tuyệt vời!* Tuần này bạn không có lịch học."
                if timestamp_str:
                    try:
                        ts_utc = datetime.fromisoformat(timestamp_str)
                        ts_local = ts_utc + timedelta(hours=7)
                        message += f"\n\n_Dữ liệu cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}_"
                    except (ValueError, TypeError):
                        pass
                return message

            if timestamp_str:
                try:
                    ts_utc = datetime.fromisoformat(timestamp_str)
                    ts_local = ts_utc + timedelta(hours=7)
                    message += f"\n\n_Dữ liệu cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}_"
                except (ValueError, TypeError):
                    pass
            
            return message
        
        except Exception as e:
            logger.error(f"Error formatting TKB message: {e}")
            return f"Lỗi định dạng thời khóa biểu: {str(e)}"
    
    def _period_to_time(self, start_period: int, num_periods: int = 0) -> str:
        """
        Chuyển đổi tiết học thành thời gian (HH:MM) dựa trên các ca học cố định.
        Nếu num_periods > 0, tính toán thời gian kết thúc.
        Nếu num_periods = 0, trả về thời gian bắt đầu.
        """
        try:
            # Mốc thời gian BẮT ĐẦU của từng tiết
            start_times = {
                1: "06:45", 2: "07:30", 3: "08:15",
                4: "09:20", 5: "10:05", 6: "10:50",
                7: "12:30", 8: "13:15", 9: "14:00",
                10: "15:05", 11: "15:50", 12: "16:35",
                13: "18:00", 14: "18:45", 15: "19:30"
            }

            if start_period not in start_times:
                return "??:??"

            # Trả về thời gian bắt đầu nếu không yêu cầu tính thời gian kết thúc
            if num_periods == 0:
                return start_times[start_period]

            # Logic tính toán thời gian KẾT THÚC dựa trên ca học
            end_period = start_period + num_periods - 1

            # Ca 1 (Tiết 1-3) -> 09:00
            if start_period >= 1 and end_period <= 3:
                return "09:00"
            
            # Ca 2 (Tiết 4-6) -> 11:35
            if start_period >= 4 and end_period <= 6:
                return "11:35"

            # Ca 3 (Tiết 7-9) -> 14:45
            if start_period >= 7 and end_period <= 9:
                return "14:45"

            # Ca 4 (Tiết 10-12) -> 17:20
            if start_period >= 10 and end_period <= 12:
                return "17:20"

            # Ca 5 (Tiết 13-15) -> 20:15
            if start_period >= 13 and end_period <= 15:
                return "20:15"

            # Xử lý các trường hợp học kéo dài qua nhiều ca (lấy mốc của ca kết thúc)
            if end_period <= 6: return "11:35"
            if end_period <= 9: return "14:45"
            if end_period <= 12: return "16:35"
            if end_period <= 15: return "20:15"

            return "??:??"

        except (ValueError, TypeError):
            return "??:??"

    def create_ics_file(self, tkb_data: Dict[str, Any], telegram_user_id: int, week_offset: int = 0,
                        selected_subjects: Optional[List[str]] = None, time_range: str = "all") -> Optional[str]:
        """
        Tạo file iCalendar (.ics) từ dữ liệu thời khóa biểu.

        Args:
            tkb_data: Dữ liệu TKB đã được xử lý cho tất cả các tuần.
            telegram_user_id: ID người dùng Telegram để đặt tên file.
            week_offset: Số tuần offset từ tuần hiện tại để bắt đầu xuất.
            selected_subjects: Danh sách mã học phần được chọn. Nếu None, xuất tất cả.
            time_range: "all" cho toàn bộ thời gian, "current" cho từ tuần hiện tại.

        Returns:
            Đường dẫn đến file .ics đã tạo hoặc None nếu có lỗi.
        """
        try:
            cal = Calendar()
            cal.add('prodid', '-//HUTECH TKB Bot//hutech.edu.vn//')
            cal.add('version', '2.0')

            # Thiết lập múi giờ
            local_tz = pytz.timezone('Asia/Ho_Chi_Minh')

            subjects = tkb_data.get("subjects", [])
            if not subjects:
                return None

            # Xử lý danh sách môn học được chọn
            if selected_subjects is None:
                selected_subjects = []

            # Tính ngày bắt đầu lọc dựa trên time_range và week_offset
            today = datetime.now()
            days_since_monday = today.weekday()
            monday = today - timedelta(days=days_since_monday)

            if time_range == "current":
                # Từ tuần hiện tại + week_offset
                filter_start_date = monday + timedelta(weeks=week_offset)
            else:
                # Toàn bộ thời gian - không lọc theo ngày
                filter_start_date = datetime.min

            for subject in subjects:
                subject_name = subject.get("ten_hp", "N/A")
                subject_code = subject.get("ma_hp", "N/A")

                # Skip nếu môn học không được chọn (khi có danh sách chọn lọc)
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

                        # Skip nếu ngày học trước filter_start_date
                        schedule_date = datetime.strptime(ngay_hoc_str, "%d/%m/%Y")
                        if schedule_date < filter_start_date:
                            continue

                        # Tính toán thời gian bắt đầu và kết thúc
                        start_time_str = self._period_to_time(start_period)
                        end_time_str = self._period_to_time(start_period, num_periods)

                        start_dt_str = f"{ngay_hoc_str} {start_time_str}"
                        end_dt_str = f"{ngay_hoc_str} {end_time_str}"

                        # Chuyển đổi sang datetime object với múi giờ
                        start_dt = datetime.strptime(start_dt_str, "%d/%m/%Y %H:%M")
                        end_dt = datetime.strptime(end_dt_str, "%d/%m/%Y %H:%M")

                        start_dt_local = local_tz.localize(start_dt)
                        end_dt_local = local_tz.localize(end_dt)

                        # Thêm thông tin vào sự kiện
                        event.add('summary', subject_name)
                        event.add('dtstart', start_dt_local)
                        event.add('dtend', end_dt_local)
                        event.add('dtstamp', datetime.now(pytz.utc))
                        event.add('location', room)
                        event.add('description', f"Mã HP: {subject_code}\nPhòng: {room}")

                        # Thêm sự kiện vào calendar
                        cal.add_component(event)

                    except (ValueError, TypeError) as e:
                        logger.warning(f"Skipping event due to processing error: {e}")
                        continue

            # Tạo thư mục temp nếu chưa có
            temp_dir = "temp"
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)

            # Ghi file
            file_path = os.path.join(temp_dir, f"tkb_{telegram_user_id}.ics")
            with open(file_path, 'wb') as f:
                f.write(cal.to_ical())

            return file_path

        except Exception as e:
            logger.error(f"Error creating ICS file for user {telegram_user_id}: {e}")
            return None

    # ==================== Command Methods ====================

    async def tkb_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /tkb"""
        user_id = update.effective_user.id

        # Kiểm tra xem người dùng đã đăng nhập chưa
        if not await self.db_manager.is_user_logged_in(user_id):
            await update.message.reply_text("Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.", reply_to_message_id=update.message.message_id)
            return

        # Lấy tuần offset từ context (nếu có)
        week_offset = 0
        if context.args:
            try:
                week_offset = int(context.args[0])
            except (ValueError, IndexError):
                week_offset = 0

        # Lấy thời khóa biểu
        result = await self.handle_tkb(user_id, week_offset)

        if result["success"]:
            # Định dạng dữ liệu thời khóa biểu
            message = self.format_tkb_message(result["data"])

            # Tạo keyboard cho các nút điều hướng
            keyboard = [
                [
                    make_inline_button("Tuần trước", f"tkb_{week_offset-1}", tone=None, emoji=None),
                    make_inline_button("Tuần hiện tại", "tkb_0", tone=None, emoji=None),
                    make_inline_button("Tuần tới", f"tkb_{week_offset+1}", tone=None, emoji=None)
                ],
                [
                    make_inline_button("Xuất iCalendar (.ics)", f"tkb_export_ics_{week_offset}", tone="warning", emoji="🗓️")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            sent_message = await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id
            )
            # Lưu ID của tin nhắn lệnh gốc và tin nhắn trả lời của bot
            context.user_data['tkb_command_message_id'] = update.message.message_id
            context.user_data['tkb_reply_message_id'] = sent_message.message_id
        else:
            await update.message.reply_text(result['message'], reply_to_message_id=update.message.message_id)

    # ==================== Callback Methods ====================

    async def tkb_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ các nút điều hướng tuần và xuất file"""
        query = update.callback_query
        user_id = query.from_user.id

        # Lấy callback_data
        callback_data = query.data

        # === XỬ LÝ CHỌN MÔN HỌC ===
        if callback_data.startswith("tkb_subject_"):
            await self._handle_tkb_subject_callback(update, context)
            return

        # === XỬ LÝ CHỌN THỜI GIAN ===
        if callback_data.startswith("tkb_time_"):
            await self._handle_tkb_time_callback(update, context)
            return

        if callback_data.startswith("tkb_export_ics_"):
            try:
                week_offset = int(callback_data.split("_")[3])
            except (ValueError, IndexError):
                week_offset = 0

            # Lưu week_offset vào context
            context.user_data["tkb_week_offset"] = week_offset

            await query.answer("Đang tải danh sách môn học...")
            result = await self.handle_export_tkb_ics(user_id, week_offset)

            if result.get("success"):
                keyboard = result.get("keyboard")
                subjects = result.get("subjects", [])

                # Lưu danh sách môn học vào context
                context.user_data["tkb_subjects"] = subjects
                context.user_data["selected_subjects"] = []  # Danh sách trống ban đầu
                context.user_data["tkb_subjects_dict"] = {s.get("ma_hp"): s for s in subjects}

                message = f"📚 *Chọn môn học để xuất*\n\n" \
                          f"Tổng số môn học: {len(subjects)}\n" \
                          f"Đã chọn: 0 môn\n\n" \
                          f"Vui lòng chọn các môn học bên dưới:"

                await query.edit_message_text(
                    text=message,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await query.answer(f"Lỗi: {result.get('message', 'Không rõ')}", show_alert=True)
            return

        if callback_data.startswith("tkb_") and not callback_data.startswith("tkb_export_ics_") and not callback_data.startswith("tkb_subject_") and not callback_data.startswith("tkb_time_"):
            try:
                week_offset = int(callback_data.split("_")[1])
            except (ValueError, IndexError):
                week_offset = 0

            # Hiển thị thông báo đang xử lý
            await query.answer("Đang tải thời khóa biểu...")

            # Lấy thời khóa biểu
            result = await self.handle_tkb(user_id, week_offset)

            if result["success"]:
                # Định dạng dữ liệu thời khóa biểu
                message = self.format_tkb_message(result["data"])

                # Tạo keyboard cho các nút điều hướng
                keyboard = [
                    [
                        make_inline_button("Tuần trước", f"tkb_{week_offset-1}", tone=None, emoji=None),
                        make_inline_button("Tuần hiện tại", "tkb_0", tone=None, emoji=None),
                        make_inline_button("Tuần tới", f"tkb_{week_offset+1}", tone=None, emoji=None)
                    ],
                    [
                        make_inline_button("Xuất iCalendar (.ics)", f"tkb_export_ics_{week_offset}", tone="warning", emoji="🗓️")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                # Cập nhật tin nhắn
                await query.edit_message_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(result['message'])

    async def _handle_tkb_subject_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ menu chọn môn học"""
        query = update.callback_query
        callback_data = query.data
        user_id = query.from_user.id

        # Lấy dữ liệu từ context
        subjects = context.user_data.get("tkb_subjects", [])
        subjects_dict = context.user_data.get("tkb_subjects_dict", {})
        selected_subjects = context.user_data.get("selected_subjects", [])
        week_offset = context.user_data.get("tkb_week_offset", 0)

        # Xử lý từng loại callback
        if callback_data == "tkb_subject_confirm":
            # Xác nhận - chuyển sang chọn thời gian
            if not selected_subjects:
                await query.answer("Vui lòng chọn ít nhất một môn học!", show_alert=True)
                return

            # Tạo thông báo danh sách đã chọn
            selected_names = []
            for ma_hp in selected_subjects:
                if ma_hp in subjects_dict:
                    subj = subjects_dict[ma_hp]
                    selected_names.append(f"- {subj.get('ten_hp', ma_hp)} ({ma_hp})")

            message = f"✅ *Đã chọn {len(selected_subjects)} môn học:*\n\n" + "\n".join(selected_names)

            # Hiển thị menu chọn thời gian
            time_keyboard = self.create_time_range_keyboard()

            await query.edit_message_text(
                text=message,
                reply_markup=time_keyboard,
                parse_mode="Markdown"
            )
            return

        if callback_data == "tkb_subject_cancel":
            # Hủy - xóa menu và thông báo
            # Xóa dữ liệu tạm
            context.user_data.pop("tkb_subjects", None)
            context.user_data.pop("selected_subjects", None)
            context.user_data.pop("tkb_subjects_dict", None)
            context.user_data.pop("tkb_week_offset", None)

            await query.edit_message_text("❌ *Đã hủy xuất file.*", parse_mode="Markdown")
            return

        # Xử lý toggle môn học
        if callback_data.startswith("tkb_subject_toggle_"):
            ma_hp = callback_data.split("_")[-1]

            if ma_hp in selected_subjects:
                # Bỏ chọn
                selected_subjects.remove(ma_hp)
            else:
                # Chọn
                selected_subjects.append(ma_hp)

            # Cập nhật context
            context.user_data["selected_subjects"] = selected_subjects

            keyboard = self.create_subject_selection_keyboard(subjects, selected_subjects)

            # Cập nhật tin nhắn
            message = f"📚 *Chọn môn học để xuất*\n\n" \
                      f"Tổng số môn học: {len(subjects)}\n" \
                      f"Đã chọn: {len(selected_subjects)} môn\n\n" \
                      f"Vui lòng chọn các môn học bên dưới:"

            await query.edit_message_text(
                text=message,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )

        await query.answer()

    async def _handle_tkb_time_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ menu chọn thời gian"""
        query = update.callback_query
        callback_data = query.data
        user_id = query.from_user.id

        # Lấy dữ liệu từ context
        selected_subjects = context.user_data.get("selected_subjects", [])
        subjects_dict = context.user_data.get("tkb_subjects_dict", {})
        week_offset = context.user_data.get("tkb_week_offset", 0)

        if callback_data == "tkb_time_back":
            # Quay lại menu chọn môn học
            subjects = context.user_data.get("tkb_subjects", [])
            keyboard = self.create_subject_selection_keyboard(subjects, selected_subjects)

            message = f"📚 *Chọn môn học để xuất*\n\n" \
                      f"Tổng số môn học: {len(subjects)}\n" \
                      f"Đã chọn: {len(selected_subjects)} môn\n\n" \
                      f"Vui lòng chọn các môn học bên dưới:"

            await query.edit_message_text(
                text=message,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return

        if callback_data == "tkb_time_all":
            # Toàn bộ thời gian
            time_range = "all"
            time_label = "toàn bộ thời gian"
        elif callback_data == "tkb_time_current":
            # Từ tuần hiện tại
            time_range = "current"
            time_label = "từ tuần hiện tại"
        else:
            await query.answer()
            return

        await query.answer("Đang tạo file .ics, vui lòng chờ...", show_alert=False)

        # Lấy dữ liệu TKB từ cache
        cache_key = f"tkb:{user_id}"
        cached_result = await self.cache_manager.get(cache_key)

        if cached_result:
            tkb_raw_data = cached_result.get("data")
            all_tkb_data = self.get_all_tkb_data(tkb_raw_data)

            # Tạo file ICS với các tham số đã chọn
            file_path = self.create_ics_file(
                all_tkb_data,
                user_id,
                week_offset,
                selected_subjects,
                time_range
            )

            if file_path and os.path.exists(file_path):
                # Tạo thông báo kết quả
                selected_names = []
                for ma_hp in selected_subjects:
                    if ma_hp in subjects_dict:
                        subj = subjects_dict[ma_hp]
                        selected_names.append(subj.get("ten_hp", ma_hp))

                subject_list = ", ".join(selected_names) if selected_names else "tất cả các môn"

                caption = f"🗓️ *File iCalendar thời khóa biểu*\n\n" \
                          f"Môn học: {subject_list}\n" \
                          f"Thời gian: {time_label}"

                try:
                    await query.message.reply_document(
                        document=open(file_path, 'rb'),
                        filename=f"tkb_{user_id}.ics",
                        caption=caption,
                        parse_mode="Markdown"
                    )
                    # Xóa tin nhắn menu cũ
                    await query.message.delete()
                except Exception as e:
                    logger.error(f"Lỗi gửi file ICS cho user {user_id}: {e}")
                    await query.message.reply_text("Có lỗi xảy ra khi gửi file.")
                finally:
                    os.remove(file_path)
            else:
                await query.message.reply_text("⚠️ Không có lịch học nào phù hợp với bộ lọc đã chọn.")
        else:
            await query.message.reply_text("⚠️ Không tìm thấy dữ liệu TKB. Vui lòng thử lại.")

        # Xóa dữ liệu tạm sau khi hoàn thành
        context.user_data.pop("tkb_subjects", None)
        context.user_data.pop("selected_subjects", None)
        context.user_data.pop("tkb_subjects_dict", None)
        context.user_data.pop("tkb_week_offset", None)

    def register_commands(self, application: Application) -> None:
        """Đăng ký command handlers với Application"""
        application.add_handler(CommandHandler("tkb", self.tkb_command))

    def register_callbacks(self, application: Application) -> None:
        """Đăng ký callback handlers với Application"""
        application.add_handler(CallbackQueryHandler(self.tkb_callback, pattern="^tkb_"))
