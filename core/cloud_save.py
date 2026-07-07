"""云存档功能 Mixin，由 TwrpgQueryPlugin 继承。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import StarTools

from .cloud_client import (
    CloudSyncClient,
    CloudSyncError,
    SaveEntry,
    parse_base_urls_config,
)
from .cloud_commands import (
    CLOUD_CMD_PRIORITY,
    _BACKPACK_RE,
    _CARRIED_RE,
    _HELP_RE,
    _LOGIN_RE,
    _PROFILE_RE,
    _SAVES_RE,
    _SWITCH_RE,
    _UNBIND_RE,
    _WAREHOUSE_RE,
)
from .save_parser import SaveData, parse_string_for_stage
from .user_binding import UserBindingStore

if TYPE_CHECKING:
    from astrbot.api import AstrBotConfig

_NOT_LOGGED_HINT = "尚未绑定云存档，请私聊发送：世界登录 用户名 密码"
_PRIVATE_LOGIN_HINT = "登录涉及账号密码，请私聊机器人发送：世界登录 用户名 密码"
_HELP_TEXT = (
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


class CloudSaveMixin:
    config: AstrBotConfig

    def _init_cloud_save(self) -> None:
        data_dir = str(StarTools.get_data_dir())
        self._cloud_bindings = UserBindingStore(data_dir)
        self._cloud_base_urls = parse_base_urls_config(self.config.get("cloud_base_urls", ""))
        self._cloud_client = CloudSyncClient(self._cloud_base_urls)
        if self._cloud_save_enabled():
            logger.info(
                f"[TWRPG Query] 云存档已启用，服务器 {len(self._cloud_base_urls)} 个地址"
            )

    async def _shutdown_cloud_save(self) -> None:
        await self._cloud_client.close()

    def _cloud_save_enabled(self) -> bool:
        return bool(self.config.get("cloud_save_enabled", True))

    def _cloud_login_private_only(self) -> bool:
        return bool(self.config.get("cloud_login_private_only", True))

    def _cloud_max_items_display(self) -> int:
        return int(self.config.get("cloud_max_items_display", 30) or 30)

    def _cloud_is_private_message(self, event: AstrMessageEvent) -> bool:
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

    def _cloud_client_for(self, binding: dict) -> CloudSyncClient:
        return CloudSyncClient(self._cloud_base_urls, token=str(binding.get("token") or ""))

    async def _cloud_pick_primary_save(
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
        self._cloud_bindings.set_primary_save(qq_id, first.name)
        return first, saves

    async def _cloud_load_primary_save_data(
        self,
        qq_id: str,
    ) -> tuple[SaveData, SaveEntry, CloudSyncClient] | str:
        binding = self._cloud_bindings.get(qq_id)
        if not binding:
            return _NOT_LOGGED_HINT
        client = self._cloud_client_for(binding)
        try:
            primary, _ = await self._cloud_pick_primary_save(client, binding, qq_id)
            if primary is None:
                await client.close()
                return "云端暂无存档文件。"
            raw = await client.download_save(primary.name)
            text = raw.decode("utf-8", errors="replace")
            data = parse_string_for_stage(text)
            return data, primary, client
        except CloudSyncError as exc:
            await client.close()
            return str(exc)
        except Exception as exc:
            logger.error(f"[TWRPG Query] 读取云存档失败: {exc}")
            await client.close()
            return "读取云端存档失败，请稍后再试。"

    @filter.regex(_LOGIN_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_login(self, event: AstrMessageEvent):
        """私聊绑定云存档账号：世界登录 用户名 密码"""
        if not self._cloud_save_enabled():
            return

        if self._cloud_login_private_only() and not self._cloud_is_private_message(event):
            event.stop_event()
            yield event.plain_result(_PRIVATE_LOGIN_HINT)
            return

        match = _LOGIN_RE.match(event.message_str.strip())
        if not match:
            return

        username = match.group(2).strip()
        password = match.group(3).strip()
        if not username or not password:
            event.stop_event()
            yield event.plain_result("格式：世界登录 用户名 密码")
            return

        client = CloudSyncClient(self._cloud_base_urls)
        try:
            result = await client.login(username, password)
            client.set_token(result.token)
            saves = await client.list_saves()
            primary_save = saves[0].name if saves else ""
            self._cloud_bindings.upsert(
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
            event.stop_event()
            yield event.plain_result(
                f"✅ 登录成功！云账号：{result.username}\n{save_hint}\n"
                "发送「世界档案」查看角色信息，「世界背包」查看背包。"
            )
        except CloudSyncError as exc:
            event.stop_event()
            yield event.plain_result(f"登录失败：{exc}")
        except Exception as exc:
            logger.error(f"[TWRPG Query] 云登录异常: {exc}")
            event.stop_event()
            yield event.plain_result("登录失败，请稍后再试。")
        finally:
            await client.close()

    @filter.regex(_HELP_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_help(self, event: AstrMessageEvent):
        if not self._cloud_save_enabled():
            return
        event.stop_event()
        yield event.plain_result(_HELP_TEXT)

    @filter.regex(_UNBIND_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_unbind(self, event: AstrMessageEvent):
        if not self._cloud_save_enabled():
            return
        event.stop_event()
        if self._cloud_bindings.remove(event.get_sender_id()):
            yield event.plain_result("已解除云存档绑定。")
        else:
            yield event.plain_result("当前未绑定云存档账号。")

    @filter.regex(_SAVES_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_list_saves(self, event: AstrMessageEvent):
        if not self._cloud_save_enabled():
            return
        binding = self._cloud_bindings.get(event.get_sender_id())
        if not binding:
            event.stop_event()
            yield event.plain_result(_NOT_LOGGED_HINT)
            return

        client = self._cloud_client_for(binding)
        try:
            saves = await client.list_saves()
            if not saves:
                event.stop_event()
                yield event.plain_result(f"云账号 {binding.get('username', '')} 暂无存档。")
                return
            primary = str(binding.get("primary_save") or "")
            lines = [f"云账号：{binding.get('username', '')}（共 {len(saves)} 个存档）", ""]
            for index, entry in enumerate(saves, start=1):
                mark = " ⭐" if entry.name == primary else ""
                lines.append(
                    f"{index}. {entry.name}{mark}\n"
                    f"   大小 {_format_size(entry.size)} | 更新 {_format_ts(entry.last_modified)}"
                )
            lines.append("\n使用「世界切换 <序号>」切换主存档。")
            event.stop_event()
            yield event.plain_result("\n".join(lines))
        except CloudSyncError as exc:
            event.stop_event()
            yield event.plain_result(str(exc))
        finally:
            await client.close()

    @filter.regex(_SWITCH_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_switch_save(self, event: AstrMessageEvent):
        if not self._cloud_save_enabled():
            return
        match = _SWITCH_RE.match(event.message_str.strip())
        if not match:
            return
        index = int(match.group(2))

        binding = self._cloud_bindings.get(event.get_sender_id())
        if not binding:
            event.stop_event()
            yield event.plain_result(_NOT_LOGGED_HINT)
            return

        client = self._cloud_client_for(binding)
        try:
            saves = await client.list_saves()
            if not saves:
                event.stop_event()
                yield event.plain_result("云端暂无存档。")
                return
            if index < 1 or index > len(saves):
                event.stop_event()
                yield event.plain_result(f"序号无效，请输入 1～{len(saves)}。")
                return
            chosen = saves[index - 1]
            self._cloud_bindings.set_primary_save(event.get_sender_id(), chosen.name)
            event.stop_event()
            yield event.plain_result(f"已切换主存档为：{chosen.name}")
        except CloudSyncError as exc:
            event.stop_event()
            yield event.plain_result(str(exc))
        finally:
            await client.close()

    @filter.regex(_PROFILE_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_save_profile(self, event: AstrMessageEvent):
        if not self._cloud_save_enabled():
            return
        loaded = await self._cloud_load_primary_save_data(str(event.get_sender_id()))
        if isinstance(loaded, str):
            event.stop_event()
            yield event.plain_result(loaded)
            return

        data, primary, client = loaded
        try:
            badge = data.account_badge_display or "无"
            lines = [
                f"【{primary.name}】",
                f"游戏ID：{data.game_id or '未知'}",
                f"职业：{data.job or '未知'}",
                f"等级：{data.level or '未知'}",
                f"徽章：{badge}",
                f"携带 {len(data.carried_items)} | 背包 {len(data.backpack_items)} | 仓库 {len(data.warehouse_items)}",
            ]
            event.stop_event()
            yield event.plain_result("\n".join(lines))
        finally:
            await client.close()

    @filter.regex(_BACKPACK_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_show_backpack(self, event: AstrMessageEvent):
        if not self._cloud_save_enabled():
            return
        loaded = await self._cloud_load_primary_save_data(str(event.get_sender_id()))
        if isinstance(loaded, str):
            event.stop_event()
            yield event.plain_result(loaded)
            return

        data, primary, client = loaded
        try:
            body = _format_item_list(data.backpack_items, limit=self._cloud_max_items_display())
            event.stop_event()
            yield event.plain_result(f"【{primary.name}】背包（{len(data.backpack_items)}）\n{body}")
        finally:
            await client.close()

    @filter.regex(_WAREHOUSE_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_show_warehouse(self, event: AstrMessageEvent):
        if not self._cloud_save_enabled():
            return
        loaded = await self._cloud_load_primary_save_data(str(event.get_sender_id()))
        if isinstance(loaded, str):
            event.stop_event()
            yield event.plain_result(loaded)
            return

        data, primary, client = loaded
        try:
            body = _format_item_list(data.warehouse_items, limit=self._cloud_max_items_display())
            event.stop_event()
            yield event.plain_result(f"【{primary.name}】仓库（{len(data.warehouse_items)}）\n{body}")
        finally:
            await client.close()

    @filter.regex(_CARRIED_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_show_carried(self, event: AstrMessageEvent):
        if not self._cloud_save_enabled():
            return
        loaded = await self._cloud_load_primary_save_data(str(event.get_sender_id()))
        if isinstance(loaded, str):
            event.stop_event()
            yield event.plain_result(loaded)
            return

        data, primary, client = loaded
        try:
            body = _format_item_list(data.carried_items, limit=self._cloud_max_items_display())
            event.stop_event()
            yield event.plain_result(f"【{primary.name}】携带（{len(data.carried_items)}）\n{body}")
        finally:
            await client.close()
