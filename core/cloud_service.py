"""云存档业务逻辑（不含 @filter，避免 AstrBot 扫描子模块失败）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent

from .cloud_client import (
    CloudSyncClient,
    CloudSyncError,
    SaveEntry,
    parse_base_urls_config,
)
from .cloud_commands import _LOGIN_RE, _SWITCH_RE
from .save_parser import parse_string_for_stage
from .user_binding import UserBindingStore

_NOT_LOGGED_HINT = "尚未绑定云存档，请私聊发送：世界登录 用户名 密码"
_PRIVATE_LOGIN_HINT = "登录涉及账号密码，请私聊机器人发送：世界登录 用户名 密码"
HELP_TEXT = (
    "【世界RPG 云存档】\n"
    "私聊：世界登录 用户名 密码\n"
    "世界解绑 — 解除绑定\n"
    "世界存档 — 云端存档列表\n"
    "世界切换 <序号> — 切换主存档\n"
    "世界档案 — 角色信息\n"
    "世界背包 / 世界仓库 / 世界携带 — 物品列表\n\n"
    "查物品仍用：世界 <物品名> 或 界 <物品名>"
)


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _format_ts(ms: int | None) -> str:
    if not ms:
        return "未知"
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "未知"


def _format_item_list(items: list[str], *, limit: int) -> str:
    if not items:
        return "（空）"
    lines = [f"{index}. {item}" for index, item in enumerate(items[:limit], start=1)]
    if len(items) > limit:
        lines.append(f"... 还有 {len(items) - limit} 条未显示")
    return "\n".join(lines)


def _is_private_message(event: AstrMessageEvent) -> bool:
    origin = str(getattr(event, "message_obj", None) and getattr(event.message_obj, "type", "") or "")
    if origin:
        lowered = origin.lower()
        if "private" in lowered or "friend" in lowered:
            return True
        if "group" in lowered:
            return False
    group_id = getattr(event, "group_id", None)
    if group_id not in (None, "", "0", 0):
        return False
    return True


class CloudSaveService:
    def __init__(self, config: AstrBotConfig | dict[str, Any], data_dir: str):
        self.config = config or {}
        self._bindings = UserBindingStore(data_dir)
        self._base_urls = parse_base_urls_config(self.config.get("cloud_base_urls", ""))
        self._client = CloudSyncClient(self._base_urls)
        if self.enabled():
            logger.info(f"[TWRPG Query] 云存档已启用，服务器 {len(self._base_urls)} 个地址")

    def enabled(self) -> bool:
        return bool(self.config.get("cloud_save_enabled", True))

    def _login_private_only(self) -> bool:
        return bool(self.config.get("cloud_login_private_only", True))

    def _max_items_display(self) -> int:
        return int(self.config.get("cloud_max_items_display", 30) or 30)

    async def close(self) -> None:
        await self._client.close()

    def _client_for(self, binding: dict) -> CloudSyncClient:
        return CloudSyncClient(self._base_urls, token=str(binding.get("token") or ""))

    async def _pick_primary_save(
        self,
        client: CloudSyncClient,
        binding: dict,
        qq_id: str,
    ) -> tuple[SaveEntry | None, list[SaveEntry]]:
        saves = await client.list_saves()
        if not saves:
            return None, saves
        preferred = str(binding.get("primary_save") or "").strip()
        if preferred:
            for entry in saves:
                if entry.name == preferred:
                    return entry, saves
        first = saves[0]
        self._bindings.set_primary_save(qq_id, first.name)
        return first, saves

    async def login(self, event: AstrMessageEvent) -> str:
        if self._login_private_only() and not _is_private_message(event):
            return _PRIVATE_LOGIN_HINT

        match = _LOGIN_RE.match(event.message_str.strip())
        if not match:
            return "格式：世界登录 用户名 密码"

        username = match.group(2).strip()
        password = match.group(3).strip()
        if not username or not password:
            return "格式：世界登录 用户名 密码"

        client = CloudSyncClient(self._base_urls)
        try:
            result = await client.login(username, password)
            client.set_token(result.token)
            saves = await client.list_saves()
            primary_save = saves[0].name if saves else ""
            self._bindings.upsert(
                event.get_sender_id(),
                username=result.username,
                token=result.token,
                cloud_user_id=result.user_id,
                primary_save=primary_save,
            )
            save_hint = f"已检测到 {len(saves)} 个云端存档。"
            if primary_save:
                save_hint += f"\n当前主存档：{primary_save}"
            else:
                save_hint += "\n云端暂无存档文件。"
            return (
                f"✅ 登录成功！云账号：{result.username}\n{save_hint}\n"
                "发送「世界档案」查看角色信息，「世界背包」查看背包。"
            )
        except CloudSyncError as exc:
            return f"登录失败：{exc}"
        except Exception as exc:
            logger.error(f"[TWRPG Query] 云登录异常: {exc}")
            return "登录失败，请稍后再试。"
        finally:
            await client.close()

    async def unbind(self, qq_id: str) -> str:
        if self._bindings.remove(qq_id):
            return "已解除云存档绑定。"
        return "当前未绑定云存档账号。"

    async def list_saves(self, qq_id: str) -> str:
        binding = self._bindings.get(qq_id)
        if not binding:
            return _NOT_LOGGED_HINT

        client = self._client_for(binding)
        try:
            saves = await client.list_saves()
            if not saves:
                return f"云账号 {binding.get('username', '')} 暂无存档。"
            primary = str(binding.get("primary_save") or "")
            lines = [f"云账号：{binding.get('username', '')}（共 {len(saves)} 个存档）", ""]
            for index, entry in enumerate(saves, start=1):
                mark = " ⭐" if entry.name == primary else ""
                lines.append(
                    f"{index}. {entry.name}{mark}\n"
                    f"   大小 {_format_size(entry.size)} | 更新 {_format_ts(entry.last_modified)}"
                )
            lines.append("\n使用「世界切换 <序号>」切换主存档。")
            return "\n".join(lines)
        except CloudSyncError as exc:
            return str(exc)
        finally:
            await client.close()

    async def switch_save(self, qq_id: str, raw: str) -> str:
        match = _SWITCH_RE.match(raw.strip())
        if not match:
            return "格式：世界切换 <序号>"

        index = int(match.group(2))
        binding = self._bindings.get(qq_id)
        if not binding:
            return _NOT_LOGGED_HINT

        client = self._client_for(binding)
        try:
            saves = await client.list_saves()
            if not saves:
                return "云端暂无存档。"
            if index < 1 or index > len(saves):
                return f"序号无效，请输入 1～{len(saves)}。"
            chosen = saves[index - 1]
            self._bindings.set_primary_save(qq_id, chosen.name)
            return f"已切换主存档为：{chosen.name}"
        except CloudSyncError as exc:
            return str(exc)
        finally:
            await client.close()

    async def profile(self, qq_id: str) -> str:
        binding = self._bindings.get(qq_id)
        if not binding:
            return _NOT_LOGGED_HINT

        client = self._client_for(binding)
        try:
            primary, _ = await self._pick_primary_save(client, binding, qq_id)
            if primary is None:
                return "云端暂无存档文件。"
            raw = await client.download_save(primary.name)
            data = parse_string_for_stage(raw.decode("utf-8", errors="replace"))
            badge = data.account_badge_display or "无"
            lines = [
                f"【{primary.name}】",
                f"游戏ID：{data.game_id or '未知'}",
                f"职业：{data.job or '未知'}",
                f"等级：{data.level or '未知'}",
                f"徽章：{badge}",
                f"携带 {len(data.carried_items)} | 背包 {len(data.backpack_items)} | 仓库 {len(data.warehouse_items)}",
            ]
            return "\n".join(lines)
        except CloudSyncError as exc:
            return str(exc)
        except Exception as exc:
            logger.error(f"[TWRPG Query] 读取云存档失败: {exc}")
            return "读取云端存档失败，请稍后再试。"
        finally:
            await client.close()

    async def backpack(self, qq_id: str) -> str:
        return await self._item_section(qq_id, "backpack")

    async def warehouse(self, qq_id: str) -> str:
        return await self._item_section(qq_id, "warehouse")

    async def carried(self, qq_id: str) -> str:
        return await self._item_section(qq_id, "carried")

    async def _item_section(self, qq_id: str, section: str) -> str:
        binding = self._bindings.get(qq_id)
        if not binding:
            return _NOT_LOGGED_HINT

        client = self._client_for(binding)
        try:
            primary, _ = await self._pick_primary_save(client, binding, qq_id)
            if primary is None:
                return "云端暂无存档文件。"
            raw = await client.download_save(primary.name)
            data = parse_string_for_stage(raw.decode("utf-8", errors="replace"))
            if section == "backpack":
                items, label = data.backpack_items, "背包"
            elif section == "warehouse":
                items, label = data.warehouse_items, "仓库"
            else:
                items, label = data.carried_items, "携带"
            body = _format_item_list(items, limit=self._max_items_display())
            return f"【{primary.name}】{label}（{len(items)}）\n{body}"
        except CloudSyncError as exc:
            return str(exc)
        except Exception as exc:
            logger.error(f"[TWRPG Query] 读取云存档失败: {exc}")
            return "读取云端存档失败，请稍后再试。"
        finally:
            await client.close()
