"""
世界RPG（TWRPG）查询插件
==============================
指令:
  世界 <物品名> / 界 <物品名> — 物品查询（支持无空格，如 世界世界破坏者）
  世界BOSS <BOSS名> / 界BOSS <BOSS名> — BOSS 掉落查询（如 世界BOSS 土灵战神盖亚）
  英雄 <名> / 英 <名> — 英雄查询
  技能 <名> / 技 <名> — 技能查询

云存档（需在配置中启用）:
  世界登录 <用户名> <密码> — 私聊绑定云账号
  世界存档 / 世界档案 / 世界背包 / 世界仓库 等
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .card_renderer import (
    format_boss_text_fallback,
    format_hero_text_fallback,
    format_skill_text_fallback,
    format_text_fallback,
    generate_boss_card,
    generate_hero_card,
    generate_item_card,
    generate_skill_card,
)
from .core.cloud_commands import (
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
    is_cloud_command,
)
from .core.cloud_service import CloudSaveService, HELP_TEXT
from .data_loader import TwrpgDataStore, normalize_query, resolve_data_dir
from .icon_utils import resolve_icons_dir
from .query_parser import (
    BOSS_CMD_RE,
    HERO_CMD_RE,
    ITEM_CMD_RE,
    SKILL_CMD_RE,
    extract_boss_query,
    extract_item_query,
    extract_prefixed_query,
    used_jie_only_item_prefix,
)
from .sgs_jie_heroes import SGS_JIE_REPLY, is_sgs_jie_hero_query

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = resolve_data_dir(_PLUGIN_DIR)
_ICONS_DIR = resolve_icons_dir(_PLUGIN_DIR)
_MAX_MATCHES = 5


class TwrpgQueryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.store = TwrpgDataStore(_DATA_DIR, icons_dir=_ICONS_DIR)
        self._cloud = CloudSaveService(self.config)
        self._load_data()

    def _load_data(self) -> None:
        items_json = os.path.join(_DATA_DIR, "items.json")
        if not os.path.exists(items_json):
            logger.warning(
                f"未找到 TWRPG 离线数据 {items_json}，"
                "请将 twrpg_data_tools/extracted_data 复制到 data/twrpg_query/"
            )
            return
        try:
            self.store.load()
            logger.info(
                "世界RPG 查询插件已加载，"
                f"物品 {len(self.store.items_by_id)} / "
                f"BOSS {len(self.store.bosses_by_id)} / "
                f"英雄 {len(self.store.heros_by_id)} / "
                f"技能 {len(self.store.skills_by_key)}"
            )
        except Exception as e:
            logger.error(f"加载 TWRPG 数据失败: {e}")

    @filter.regex(BOSS_CMD_RE, priority=9)
    async def on_twrpg_boss_command(self, event: AstrMessageEvent):
        raw = event.message_str.strip()
        query_text = extract_boss_query(raw)
        if query_text is None:
            return

        async for result in self._handle_entity_query(
            event,
            query_text,
            entity_label="BOSS",
            usage="世界BOSS <BOSS名>\n      界BOSS <BOSS名>",
            example="世界BOSS 土灵战神盖亚\n      界BOSS 盖亚\n      界BOSS 土",
            search=self.store.search_boss,
            exact_name=lambda entity_id: self.store.boss_name(entity_id),
            build_display=self.store.build_boss_display,
            match_label=lambda entity_id, query: self.store.boss_name(entity_id),
            generate_card=generate_boss_card,
            text_fallback=format_boss_text_fallback,
            log_prefix="BOSS",
        ):
            yield result
        event.stop_event()

    @filter.regex(ITEM_CMD_RE, priority=10)
    async def on_twrpg_item_command(self, event: AstrMessageEvent):
        raw = event.message_str.strip()
        if self._cloud.enabled() and is_cloud_command(raw):
            return
        query_text = extract_item_query(raw)
        if query_text is None:
            return

        if used_jie_only_item_prefix(raw) and is_sgs_jie_hero_query(query_text):
            yield event.plain_result(SGS_JIE_REPLY)
            event.stop_event()
            return

        async for result in self._handle_entity_query(
            event,
            query_text,
            entity_label="物品",
            usage="世界 <物品名>\n      界 <物品名>",
            example="世界 世界破坏者\n      世界世界破坏者\n      界 太阳石",
            search=self.store.search,
            exact_name=lambda entity_id: self.store.item_name(entity_id),
            build_display=self.store.build_display,
            match_label=lambda entity_id, query: self.store.item_name(entity_id),
            generate_card=generate_item_card,
            text_fallback=format_text_fallback,
            log_prefix="物品",
        ):
            yield result
        event.stop_event()

    @filter.regex(HERO_CMD_RE, priority=10)
    async def on_twrpg_hero_command(self, event: AstrMessageEvent):
        raw = event.message_str.strip()
        query_text = extract_prefixed_query(raw, ("英雄", "英"))
        if query_text is None:
            return

        async for result in self._handle_entity_query(
            event,
            query_text,
            entity_label="英雄",
            usage="英雄 <英雄名>\n      英 <英雄名>",
            example="英雄 追星剑圣\n      英 路易斯",
            search=self.store.search_hero,
            exact_name=lambda entity_id: self.store.hero_name(entity_id),
            build_display=self.store.build_hero_display,
            match_label=lambda entity_id, query: self.store.hero_name(entity_id),
            generate_card=generate_hero_card,
            text_fallback=format_hero_text_fallback,
            log_prefix="英雄",
        ):
            yield result
        event.stop_event()

    @filter.regex(SKILL_CMD_RE, priority=10)
    async def on_twrpg_skill_command(self, event: AstrMessageEvent):
        raw = event.message_str.strip()
        query_text = extract_prefixed_query(raw, ("技能", "技"))
        if query_text is None:
            return

        async for result in self._handle_entity_query(
            event,
            query_text,
            entity_label="技能",
            usage="技能 <技能名>\n      技 <技能名>",
            example="技能 升龙击\n      技 恩赐解脱",
            search=self.store.search_skill,
            exact_name=lambda entity_id: (
                display.name
                if (display := self.store.build_skill_display(entity_id))
                else entity_id
            ),
            build_display=self.store.build_skill_display,
            match_label=lambda entity_id, query: self.store.skill_label(entity_id),
            generate_card=generate_skill_card,
            text_fallback=format_skill_text_fallback,
            log_prefix="技能",
        ):
            yield result
        event.stop_event()

    async def _handle_entity_query(
        self,
        event: AstrMessageEvent,
        text: str,
        *,
        entity_label: str,
        usage: str,
        example: str,
        search: Callable[[str, int], list[str]],
        exact_name: Callable[[str], str],
        build_display: Callable[[str], object | None],
        match_label: Callable[[str, str], str],
        generate_card: Callable[[object], str],
        text_fallback: Callable[[object], str],
        log_prefix: str,
    ) -> AsyncIterator:
        if not self.store.loaded:
            yield event.plain_result(
                "❌ 离线数据尚未准备。\n"
                f"请确认插件目录下存在 data/twrpg_query/items.json\n"
                f"当前路径: {_DATA_DIR}"
            )
            return

        if not text:
            yield event.plain_result(f"用法: {usage}\n例如: {example}")
            return

        matches = search(text, limit=_MAX_MATCHES + 3)
        if not matches:
            yield event.plain_result(f"❌ 未找到「{text}」的相关{entity_label}。")
            return

        query_key = normalize_query(text)
        exact_matches = [
            entity_id
            for entity_id in matches
            if normalize_query(exact_name(entity_id)) == query_key
        ]
        if len(exact_matches) == 1:
            matches = exact_matches

        if len(matches) > 1:
            lines = [
                f"找到 {len(matches)} 个匹配结果，请输入更精确的名称后重新查询：",
                "",
            ]
            for entity_id in matches[:8]:
                lines.append(f"· {match_label(entity_id, text)}")
            yield event.plain_result("\n".join(lines))
            return

        entity_id = matches[0]
        display = build_display(entity_id)
        if not display:
            yield event.plain_result(f"❌ {entity_label}数据异常: {entity_id}")
            return

        try:
            card_path = generate_card(display)
            yield event.image_result(card_path)
        except Exception as e:
            logger.error(f"生成 TWRPG {log_prefix}查询卡片失败 ({entity_id}): {e}")
            yield event.plain_result(text_fallback(display))

    @filter.regex(_LOGIN_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_login(self, event: AstrMessageEvent):
        """私聊绑定云存档账号：世界登录 用户名 密码"""
        if not self._cloud.enabled():
            return
        event.stop_event()
        yield event.plain_result(await self._cloud.login(event))

    @filter.regex(_HELP_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_help(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        event.stop_event()
        yield event.plain_result(HELP_TEXT)

    @filter.regex(_UNBIND_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_unbind(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        event.stop_event()
        yield event.plain_result(await self._cloud.unbind(event.get_sender_id()))

    @filter.regex(_SAVES_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_list_saves(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        event.stop_event()
        yield event.plain_result(await self._cloud.list_saves(str(event.get_sender_id())))

    @filter.regex(_SWITCH_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_switch_save(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        event.stop_event()
        yield event.plain_result(
            await self._cloud.switch_save(str(event.get_sender_id()), event.message_str)
        )

    @filter.regex(_PROFILE_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_save_profile(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        event.stop_event()
        yield event.plain_result(await self._cloud.profile(str(event.get_sender_id())))

    @filter.regex(_BACKPACK_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_show_backpack(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        event.stop_event()
        yield event.plain_result(await self._cloud.backpack(str(event.get_sender_id())))

    @filter.regex(_WAREHOUSE_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_show_warehouse(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        event.stop_event()
        yield event.plain_result(await self._cloud.warehouse(str(event.get_sender_id())))

    @filter.regex(_CARRIED_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_show_carried(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        event.stop_event()
        yield event.plain_result(await self._cloud.carried(str(event.get_sender_id())))

    async def terminate(self):
        await self._cloud.close()
        logger.info("世界RPG 查询插件已卸载")
