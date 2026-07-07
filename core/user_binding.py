"""QQ 用户与云存档账号绑定持久化。"""

from __future__ import annotations

import copy
import json
import os
import time
from typing import Any

from astrbot.api import logger


class UserBindingStore:
    def __init__(self, data_dir: str):
        self.path = os.path.join(data_dir, "twrpg_cloud_bindings.json")
        os.makedirs(data_dir, exist_ok=True)
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.error(f"[TWRPG Cloud] 加载绑定数据失败: {exc}")
            return {}

    def _save(self) -> None:
        temp_path = self.path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, self.path)

    def get(self, qq_id: Any) -> dict[str, Any] | None:
        item = self._data.get(str(qq_id))
        return copy.deepcopy(item) if item else None

    def upsert(
        self,
        qq_id: Any,
        *,
        username: str,
        token: str,
        cloud_user_id: int | None = None,
        primary_save: str = "",
    ) -> dict[str, Any]:
        key = str(qq_id)
        record = {
            "username": username,
            "token": token,
            "cloud_user_id": cloud_user_id,
            "primary_save": primary_save,
            "bind_time": int(time.time()),
        }
        self._data[key] = record
        self._save()
        return copy.deepcopy(record)

    def set_primary_save(self, qq_id: Any, save_name: str) -> bool:
        key = str(qq_id)
        record = self._data.get(key)
        if not record:
            return False
        record["primary_save"] = save_name
        self._save()
        return True

    def remove(self, qq_id: Any) -> bool:
        key = str(qq_id)
        if key not in self._data:
            return False
        del self._data[key]
        self._save()
        return True
