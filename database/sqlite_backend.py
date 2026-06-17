#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database backend dùng SQLite (aiosqlite).

Phù hợp single-instance / dev / nhẹ. WAL mode cho phép đọc/ghi đồng thời.
Cú pháp khác Postgres ở vài điểm:
- Placeholder `?` thay `$1`.
- `INTEGER PRIMARY KEY AUTOINCREMENT` thay `SERIAL`.
- `TEXT` cho JSON (response_data) — serialize/deserialize qua helper.
- `INTEGER 0/1` cho BOOLEAN.
- Upsert dùng `ON CONFLICT(col) DO UPDATE SET col=excluded.col` (SQLite 3.24+).
- Instance lock: `fcntl.flock` trên file POSIX. Fallback `asyncio.Lock`
  trong cùng process nếu không có `fcntl` (vd Windows).
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

import aiosqlite

from config.config import Config
from database.base import BaseDatabase

logger = logging.getLogger(__name__)


class SqliteBackend(BaseDatabase):
    """Backend SQLite cho bot. Single connection + WAL."""

    def __init__(self):
        self.config = Config()
        self.db_path = self.config.SQLITE_PATH
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock_conn: Optional[aiosqlite.Connection] = None
        # State cho instance lock
        self._lock_fd: Optional[Any] = None
        self._lock_path = "/tmp/hutech_bot.lock"
        self._lock_held = False
        self._fallback_lock = asyncio.Lock()
        try:
            import fcntl  # noqa: F401
            self._has_fcntl = True
        except ImportError:
            self._has_fcntl = False
            logger.warning(
                "fcntl không khả dụng (Windows?). Fallback asyncio.Lock cho instance lock — "
                "chỉ bảo vệ trong cùng process. KHÔNG scale-out với SQLite."
            )

    # ==================== Lifecycle ====================

    async def connect(self):
        """Mở file SQLite, bật WAL, khởi tạo schema."""
        if self._conn is not None:
            return
        try:
            db_dir = os.path.dirname(self.db_path) or "."
            os.makedirs(db_dir, exist_ok=True)

            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row

            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")

            logger.info("Đã kết nối thành công đến SQLite @ %s", self.db_path)
            await self._init_database()
        except Exception as e:
            logger.error("Lỗi không thể kết nối đến SQLite: %s", e)
            raise

    async def close(self):
        """Nhả instance lock và đóng connection."""
        await self.release_bot_instance_lock()
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("Đã đóng kết nối SQLite.")

    async def _execute(self, query: str, params: tuple = ()) -> aiosqlite.Cursor:
        assert self._conn is not None, "SQLite chưa kết nối"
        return await self._conn.execute(query, params)

    async def _executemany(self, query: str, params_seq) -> aiosqlite.Cursor:
        assert self._conn is not None, "SQLite chưa kết nối"
        return await self._conn.executemany(query, params_seq)

    async def _fetchall(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Chạy query SELECT, trả về list[dict] (key là tên cột)."""
        assert self._conn is not None, "SQLite chưa kết nối"
        cur = await self._conn.execute(query, params)
        try:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            await cur.close()

    async def _fetchone(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Chạy query SELECT, trả về 1 row hoặc None."""
        assert self._conn is not None, "SQLite chưa kết nối"
        cur = await self._conn.execute(query, params)
        try:
            row = await cur.fetchone()
            return dict(row) if row else None
        finally:
            await cur.close()

    # ==================== Instance lock ====================

    async def acquire_bot_instance_lock(self, lock_key: int) -> bool:
        """Lấy lock single-instance. Dùng `fcntl.flock` nếu có, fallback `asyncio.Lock`."""
        if self._lock_held:
            return True

        if self._has_fcntl:
            import fcntl
            try:
                fd = open(self._lock_path, "w")
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                logger.warning("Không thể lấy bot instance lock (file %s)", self._lock_path)
                return False
            self._lock_fd = fd
            self._lock_held = True
            logger.info("Đã lấy bot instance lock (fcntl, key=%s)", lock_key)
            return True

        if self._fallback_lock.locked():
            logger.warning("Không thể lấy bot instance lock (asyncio fallback đang giữ)")
            return False
        await self._fallback_lock.acquire()
        self._lock_held = True
        logger.info("Đã lấy bot instance lock (asyncio fallback, key=%s)", lock_key)
        return True

    async def release_bot_instance_lock(self) -> None:
        """Nhả lock đang giữ (fcntl hoặc fallback)."""
        if not self._lock_held:
            return
        self._lock_held = False
        if self._lock_fd is not None:
            try:
                self._lock_fd.close()
            except Exception as e:
                logger.warning("Không thể close lock fd: %s", e)
            self._lock_fd = None
            logger.info("Đã nhả bot instance lock (fcntl).")
            return
        if self._fallback_lock.locked():
            self._fallback_lock.release()
            logger.info("Đã nhả bot instance lock (asyncio fallback).")

    # ==================== Schema ====================

    async def _init_database(self) -> None:
        """Tạo 3 bảng chính (idempotent): users, login_responses, user_consents."""
        assert self._conn is not None
        await self._conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                device_uuid TEXT NOT NULL,
                is_active INTEGER DEFAULT 0,
                preferred_campus TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(telegram_user_id, username)
            );

            CREATE TABLE IF NOT EXISTS login_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                response_data TEXT NOT NULL,
                ho_ten TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(telegram_user_id, username)
            );

            CREATE TABLE IF NOT EXISTS user_consents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL UNIQUE,
                accepted INTEGER NOT NULL DEFAULT 0,
                accepted_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        await self._conn.commit()
        logger.info("Database initialized successfully")

    # ==================== Helpers ====================

    @staticmethod
    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.lower() in ("1", "true", "t", "yes")
        return False

    # ==================== Users ====================

    async def save_user(
        self, telegram_user_id: int, username: str, password: str, device_uuid: str
    ) -> bool:
        query = '''
            INSERT INTO users (telegram_user_id, username, password, device_uuid, is_active, updated_at)
            VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_user_id, username) DO UPDATE SET
                password=excluded.password,
                device_uuid=excluded.device_uuid,
                is_active=1,
                updated_at=CURRENT_TIMESTAMP
        '''
        try:
            await self._execute(query, (telegram_user_id, username, password, device_uuid))
            await self._conn.commit()
            logger.info("User %s/%s saved successfully", telegram_user_id, username)
            return True
        except Exception as e:
            logger.error("Error saving user %s/%s: %s", telegram_user_id, username, e)
            return False

    async def save_login_response(
        self,
        telegram_user_id: int,
        username: str,
        response_data: Dict[str, Any],
        ho_ten: Optional[str] = None,
    ) -> bool:
        query = '''
            INSERT INTO login_responses (telegram_user_id, username, response_data, ho_ten, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_user_id, username) DO UPDATE SET
                response_data=excluded.response_data,
                ho_ten=excluded.ho_ten,
                created_at=CURRENT_TIMESTAMP
        '''
        try:
            await self._execute(
                query,
                (telegram_user_id, username, self.dump_json(response_data), ho_ten),
            )
            await self._conn.commit()
            logger.info("Login response for user %s/%s saved successfully", telegram_user_id, username)
            return True
        except Exception as e:
            logger.error("Error saving login response for user %s/%s: %s", telegram_user_id, username, e)
            return False

    async def get_user_accounts(
        self, telegram_user_id: int, order_by_login_time: bool = False
    ) -> List[Dict[str, Any]]:
        order_clause = (
            "ORDER BY u.created_at ASC"
            if order_by_login_time
            else "ORDER BY u.is_active DESC, u.created_at DESC"
        )
        query = f'''
            SELECT u.telegram_user_id, u.username, u.device_uuid, u.is_active, u.created_at,
                   lr.ho_ten
            FROM users u
            LEFT JOIN login_responses lr ON u.telegram_user_id = lr.telegram_user_id AND u.username = lr.username
            WHERE u.telegram_user_id = ?
            {order_clause}
        '''
        try:
            rows = await self._fetchall(query, (telegram_user_id,))
            return rows
        except Exception as e:
            logger.error("Error getting accounts for user %s: %s", telegram_user_id, e)
            return []

    async def add_account(
        self,
        telegram_user_id: int,
        username: str,
        password: str,
        device_uuid: str,
        response_data: Dict[str, Any],
        ho_ten: Optional[str] = None,
    ) -> bool:
        try:
            assert self._conn is not None
            await self._conn.execute("BEGIN")
            await self._conn.execute(
                "UPDATE users SET is_active = 0 WHERE telegram_user_id = ?",
                (telegram_user_id,),
            )
            await self._conn.execute(
                '''INSERT INTO users (telegram_user_id, username, password, device_uuid, is_active, updated_at)
                   VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                   ON CONFLICT(telegram_user_id, username) DO UPDATE SET
                       password=excluded.password,
                       device_uuid=excluded.device_uuid,
                       is_active=1,
                       updated_at=CURRENT_TIMESTAMP''',
                (telegram_user_id, username, password, device_uuid),
            )
            await self._conn.execute(
                '''INSERT INTO login_responses (telegram_user_id, username, response_data, ho_ten, created_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(telegram_user_id, username) DO UPDATE SET
                       response_data=excluded.response_data,
                       ho_ten=excluded.ho_ten,
                       created_at=CURRENT_TIMESTAMP''',
                (telegram_user_id, username, self.dump_json(response_data), ho_ten),
            )
            await self._conn.commit()
            logger.info("Account %s added for user %s, set as active", username, telegram_user_id)
            return True
        except Exception as e:
            await self._conn.rollback()
            logger.error("Error adding account for user %s/%s: %s", telegram_user_id, username, e)
            return False

    async def set_active_account(self, telegram_user_id: int, username: str) -> bool:
        try:
            await self._execute(
                "UPDATE users SET is_active = 0 WHERE telegram_user_id = ?",
                (telegram_user_id,),
            )
            await self._execute(
                "UPDATE users SET is_active = 1 WHERE telegram_user_id = ? AND username = ?",
                (telegram_user_id, username),
            )
            await self._conn.commit()
            logger.info("Account %s set as active for user %s", username, telegram_user_id)
            return True
        except Exception as e:
            await self._conn.rollback()
            logger.error("Error setting active account for user %s/%s: %s", telegram_user_id, username, e)
            return False

    async def get_active_account(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        query = '''
            SELECT u.telegram_user_id, u.username, u.device_uuid, u.is_active, u.created_at,
                   lr.ho_ten
            FROM users u
            LEFT JOIN login_responses lr ON u.telegram_user_id = lr.telegram_user_id AND u.username = lr.username
            WHERE u.telegram_user_id = ? AND u.is_active = 1
            LIMIT 1
        '''
        try:
            return await self._fetchone(query, (telegram_user_id,))
        except Exception as e:
            logger.error("Error getting active account for user %s: %s", telegram_user_id, e)
            return None

    async def remove_account(self, telegram_user_id: int, username: str) -> bool:
        try:
            assert self._conn is not None
            await self._conn.execute("BEGIN")
            await self._conn.execute(
                "DELETE FROM login_responses WHERE telegram_user_id = ? AND username = ?",
                (telegram_user_id, username),
            )
            await self._conn.execute(
                "DELETE FROM users WHERE telegram_user_id = ? AND username = ?",
                (telegram_user_id, username),
            )
            await self._conn.commit()
            logger.info("Account %s removed for user %s", username, telegram_user_id)
            return True
        except Exception as e:
            await self._conn.rollback()
            logger.error("Error removing account %s for user %s: %s", username, telegram_user_id, e)
            return False

    async def delete_all_accounts(self, telegram_user_id: int) -> bool:
        try:
            assert self._conn is not None
            await self._conn.execute("BEGIN")
            await self._conn.execute(
                "DELETE FROM login_responses WHERE telegram_user_id = ?",
                (telegram_user_id,),
            )
            await self._conn.execute(
                "DELETE FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            )
            await self._conn.commit()
            logger.info("All accounts deleted for user %s", telegram_user_id)
            return True
        except Exception as e:
            await self._conn.rollback()
            logger.error("Error deleting all accounts for user %s: %s", telegram_user_id, e)
            return False

    async def get_user(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        active = await self.get_active_account(telegram_user_id)
        if active:
            return {
                "telegram_user_id": active["telegram_user_id"],
                "username": active["username"],
                "device_uuid": active["device_uuid"],
                "is_active": bool(active["is_active"]),
            }
        return None

    async def is_user_logged_in(self, telegram_user_id: int) -> bool:
        try:
            row = await self._fetchone(
                "SELECT 1 AS x FROM users WHERE telegram_user_id = ? LIMIT 1",
                (telegram_user_id,),
            )
            return row is not None
        except Exception as e:
            logger.error("Error checking login status for user %s: %s", telegram_user_id, e)
            return False

    async def set_user_login_status(self, telegram_user_id: int, is_logged_in: bool) -> bool:
        # Deprecated — giữ để tương thích
        return True

    async def get_user_login_response(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        active = await self.get_active_account(telegram_user_id)
        if not active:
            return None
        row = await self._fetchone(
            "SELECT response_data FROM login_responses WHERE telegram_user_id = ? AND username = ?",
            (telegram_user_id, active["username"]),
        )
        if row and row["response_data"]:
            return self.parse_json(row["response_data"])
        return None

    async def get_user_login_response_by_username(
        self, telegram_user_id: int, username: str
    ) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            "SELECT response_data FROM login_responses WHERE telegram_user_id = ? AND username = ?",
            (telegram_user_id, username),
        )
        if row and row["response_data"]:
            return self.parse_json(row["response_data"])
        return None

    async def delete_user(self, telegram_user_id: int) -> bool:
        return await self.delete_all_accounts(telegram_user_id)

    async def get_all_logged_in_users(self) -> List[int]:
        try:
            rows = await self._fetchall(
                "SELECT DISTINCT telegram_user_id FROM users"
            )
            return [r["telegram_user_id"] for r in rows]
        except Exception as e:
            logger.error("Error getting all logged in users: %s", e)
            return []

    async def get_active_user_token(self, telegram_user_id: int) -> Optional[str]:
        response = await self.get_user_login_response(telegram_user_id)
        if response:
            return response.get("token")
        return None

    async def get_user_device_uuid_by_username(
        self, telegram_user_id: int, username: str
    ) -> Optional[str]:
        row = await self._fetchone(
            "SELECT device_uuid FROM users WHERE telegram_user_id = ? AND username = ?",
            (telegram_user_id, username),
        )
        return row["device_uuid"] if row else None

    # ==================== Policy / consent ====================

    async def has_accepted_policy(self, telegram_user_id: int) -> bool:
        row = await self._fetchone(
            "SELECT accepted FROM user_consents WHERE telegram_user_id = ? LIMIT 1",
            (telegram_user_id,),
        )
        return bool(row and self._bool(row["accepted"]))

    async def set_policy_consent(self, telegram_user_id: int, accepted: bool) -> bool:
        query = '''
            INSERT INTO user_consents (telegram_user_id, accepted, accepted_at, updated_at)
            VALUES (?, ?, CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE NULL END, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                accepted=excluded.accepted,
                accepted_at=excluded.accepted_at,
                updated_at=CURRENT_TIMESTAMP
        '''
        try:
            await self._execute(query, (telegram_user_id, 1 if accepted else 0, 1 if accepted else 0))
            await self._conn.commit()
            logger.info("Policy consent updated for user %s: accepted=%s", telegram_user_id, accepted)
            return True
        except Exception as e:
            logger.error("Error updating policy consent for user %s: %s", telegram_user_id, e)
            return False

    # ==================== Preferred campus ====================

    async def get_user_preferred_campus(self, telegram_user_id: int) -> Optional[str]:
        row = await self._fetchone(
            "SELECT preferred_campus FROM users WHERE telegram_user_id = ? LIMIT 1",
            (telegram_user_id,),
        )
        if row and row["preferred_campus"]:
            return row["preferred_campus"]
        return None

    async def set_user_preferred_campus(
        self, telegram_user_id: int, campus_name: str
    ) -> bool:
        try:
            await self._execute(
                "UPDATE users SET preferred_campus = ? WHERE telegram_user_id = ?",
                (campus_name, telegram_user_id),
            )
            await self._conn.commit()
            logger.info("Preferred campus '%s' saved for user %s", campus_name, telegram_user_id)
            return True
        except Exception as e:
            logger.error("Error setting preferred campus for user %s: %s", telegram_user_id, e)
            return False

    async def delete_user_preferred_campus(self, telegram_user_id: int) -> bool:
        try:
            await self._execute(
                "UPDATE users SET preferred_campus = NULL WHERE telegram_user_id = ?",
                (telegram_user_id,),
            )
            await self._conn.commit()
            logger.info("Preferred campus deleted for user %s", telegram_user_id)
            return True
        except Exception as e:
            logger.error("Error deleting preferred campus for user %s: %s", telegram_user_id, e)
            return False