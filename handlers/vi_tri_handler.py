#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler quản lý vị trí điểm danh (campus) mặc định.

Dùng cho `/diemdanh` và `/diemdanhtatca` — bot sẽ dùng campus đã lưu làm
vị trí GPS mặc định khi submit điểm danh. Nếu chưa set, user phải chọn
trong menu trước khi nhập mã số.

UI dùng Rich Message (Bot API 10.1): mỗi khi user chọn / xoá campus,
message được edit kèm `<tg-map>` preview vị trí GPS.

Cú pháp callback:
    vitri_select_<campus_name>  - lưu campus làm mặc định
    vitri_delete                - xóa campus đã lưu
"""

import logging
from typing import Any, Dict, List, Optional

from utils.button_style import make_inline_button, build_inline_keyboard
from utils.rich_message import (
    escape_html,
    join_blocks,
    p,
    p_html,
    section_heading,
    tg_map,
)
from utils.telegram_api import TelegramAPI, TelegramAPIError
from config.config import Config

logger = logging.getLogger(__name__)

# Danh sách campus của HUTECH kèm tọa độ GPS
CAMPUS_LOCATIONS: Dict[str, Dict[str, float]] = {
    "Thu Duc Campus": {"lat": 10.8550845, "long": 106.7853143},
    "Sai Gon Campus": {"lat": 10.8021417, "long": 106.7149192},
    "Ung Van Khiem Campus": {"lat": 10.8098001, "long": 106.714906},
    "Hitech Park Campus": {"lat": 10.8408075, "long": 106.8088987},
}


def build_campus_map_block(campus_name: Optional[str]) -> str:
    """Trả về `<tg-map>` cho campus (chuỗi rỗng nếu không hợp lệ).

    Dùng chung cho `vi_tri_handler`, `diem_danh_handler`,
    `diem_danh_tat_ca_handler` để hiển thị map preview ở cùng tọa độ.
    """
    if not campus_name:
        return ""
    loc = CAMPUS_LOCATIONS.get(campus_name)
    if not loc:
        return ""
    return tg_map(
        loc["lat"],
        loc["long"],
        zoom=16,
        caption=f"{loc['lat']}, {loc['long']}",
    )


class ViTriHandler:
    """Handler cho `/vitri` — quản lý campus mặc định cho điểm danh."""

    def __init__(self, db_manager, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)

    # ==================== Public API ====================

    async def get_user_preferred_campus(self, telegram_user_id: int) -> Optional[str]:
        return await self.db_manager.get_user_preferred_campus(telegram_user_id)

    async def set_user_preferred_campus(self, telegram_user_id: int, campus_name: str) -> bool:
        return await self.db_manager.set_user_preferred_campus(telegram_user_id, campus_name)

    async def delete_user_preferred_campus(self, telegram_user_id: int) -> bool:
        return await self.db_manager.delete_user_preferred_campus(telegram_user_id)

    def get_campus_location(self, campus_name: str) -> Optional[Dict[str, float]]:
        return CAMPUS_LOCATIONS.get(campus_name)

    def get_all_campuses(self) -> List[str]:
        return list(CAMPUS_LOCATIONS.keys())

    async def cmd_vitri(self, chat_id: int, user_id: int, reply_to_message_id: Optional[int]) -> None:
        preferred = await self.get_user_preferred_campus(user_id)
        await self.telegram.send_rich_message(
            chat_id=chat_id,
            html=self._format_rich_menu(preferred),
            reply_markup=self._build_keyboard(preferred),
            reply_to_message_id=reply_to_message_id,
        )

    async def cb_handle(self, callback_id: str, chat_id: int, message_id: int,
                       user_id: int, callback_data: str) -> None:
        await self.telegram.answer_callback_query(callback_id)

        if callback_data == "vitri_delete":
            await self.delete_user_preferred_campus(user_id)
            preferred = None
            html = self._format_rich_menu(None)
            markup = self._build_keyboard(None)
        elif callback_data.startswith("vitri_select_"):
            campus_name = callback_data[len("vitri_select_"):]
            await self.set_user_preferred_campus(user_id, campus_name)
            preferred = campus_name
            html = self._format_rich_menu(campus_name)
            markup = self._build_keyboard(campus_name)
        else:
            return

        try:
            await self.telegram.edit_message_text_rich(
                chat_id=chat_id,
                message_id=message_id,
                html=html,
                reply_markup=markup,
            )
        except TelegramAPIError as e:
            if "message is not modified" not in e.description.lower():
                raise

    # ==================== Internal ====================

    @staticmethod
    def _format_rich_menu(preferred_campus: Optional[str]) -> str:
        blocks: List[str] = [section_heading("📍", "Quản Lý Vị Trí Điểm Danh")]
        if preferred_campus:
            loc = CAMPUS_LOCATIONS.get(preferred_campus)
            campus_line = f"Vị trí hiện tại: <b>{escape_html(preferred_campus)}</b>"
            blocks.append(p_html(campus_line))
            if loc:
                blocks.append(build_campus_map_block(preferred_campus))
        else:
            blocks.append(p("Chưa cài đặt vị trí."))
        blocks.append(p("Chọn một campus để lưu làm vị trí mặc định."))
        return join_blocks(blocks)

    def _build_keyboard(self, preferred_campus: Optional[str]) -> Dict[str, Any]:
        rows: List[List[Dict[str, Any]]] = []
        row: List[Dict[str, Any]] = []
        for i, name in enumerate(self.get_all_campuses()):
            row.append(make_inline_button(name, f"vitri_select_{name}", tone=None, emoji="📍"))
            if len(row) == 2 or i == len(self.get_all_campuses()) - 1:
                rows.append(row)
                row = []
        if preferred_campus:
            rows.append([make_inline_button("Xóa vị trí đã lưu", "vitri_delete", tone="danger")])
        return build_inline_keyboard(rows)
