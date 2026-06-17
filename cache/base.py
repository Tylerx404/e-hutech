#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Interface chung cho cache backend.

Tất cả backend đều wrap value theo format `{timestamp, data}` khi `set`,
và trả về dict tương ứng khi `get`. Điều này giúp `StateStore` và các
handler đọc cache đồng nhất, không phụ thuộc backend.
"""

import abc
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseCache(abc.ABC):
    """Interface chung cho mọi cache backend."""

    @abc.abstractmethod
    async def connect(self) -> None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    @abc.abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]: ...

    @abc.abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 3600) -> None: ...

    @abc.abstractmethod
    async def delete(self, key: str) -> None: ...

    @abc.abstractmethod
    async def clear_user_cache(self, telegram_user_id: int, log_info: bool = True) -> None: ...