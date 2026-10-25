"""
世界RPG（TWRPG）查询插件
==============================
指令:
  世界 <物品名> / 界 <物品名> — 物品查询（支持无空格，如 世界世界破坏者）
  世界BOSS <BOSS名> / 界BOSS <BOSS名> — BOSS 掉落查询（如 世界BOSS 土灵战神盖亚）
  英雄 <名> / 英 <名> — 英雄查询
  技能 <名> / 技 <名> — 技能查询
  世界材料 <物品名> [xN] — 按主存档库存统计目标物品缺料
  世界图鉴 [分类] [阶段] [关键词] [第N页] — 图鉴分类浏览

云存档（需在配置中启用）:
  世界登录 <用户名> <密码> — 私聊绑定云账号
  世界存档 / 世界档案 / 世界背包 / 世界仓库 等
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator, Callable

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.message.components import Image, Plain

from .card_renderer import (
    configure_runtime_cards_dir,
    format_boss_text_fallback,
    format_hero_text_fallback,
    format_skill_text_fallback,
    format_text_fallback,
    generate_boss_card,
    generate_hero_card,
    generate_item_card,
    generate_skill_card,
)
from .codex import build_selection, category_hint_text, parse_codex_args
from .codex_renderer import format_codex_text, render_codex
from .core.cloud_commands import (
    CLOUD_CMD_PRIORITY,
    CLOUD_FALLBACK_PRIORITY,
    _BACKPACK_RE,
    _CARRIED_RE,
    _CLOUD_RESERVED_RE,
    _HELP_RE,
    _LOGIN_RE,
    _ONLINE_RE,
    _PROFILE_RE,
    _READER_UPDATE_RE,
    _SAVES_RE,
    _SWITCH_RE,
    _UNBIND_RE,
    _WAREHOUSE_RE,
    cloud_command_usage,
    is_cloud_command,
)
from .core.cloud_service import (
    CLOUD_DISABLED_HINT,
    CloudInventoryResult,
    CloudSaveService,
    HELP_TEXT,
    InventorySnapshot,
)
from .data_loader import TwrpgDataStore, normalize_query, resolve_data_dir
from .icon_utils import resolve_icons_dir
from .material_planner import parse_quantity, plan_materials, resolve_item_id
from .material_renderer import (
    format_material_caption,
    format_material_text,
    generate_material_card,
)
from .query_parser import (
    BOSS_CMD_RE,
    CODEX_CMD_RE,
    HERO_CMD_RE,
    ITEM_CMD_RE,
    MATERIAL_CMD_RE,
    SKILL_CMD_RE,
    TOOL_CMD_PRIORITY,
    extract_boss_query,
    extract_codex_query,
    extract_item_query,
    extract_material_query,
    extract_prefixed_query,
    is_tool_command,
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
        self._runtime_data_dir = str(StarTools.get_data_dir())
        configure_runtime_cards_dir(self._runtime_data_dir)
        self.store = TwrpgDataStore(_DATA_DIR, icons_dir=_ICONS_DIR)
        self._cloud = CloudSaveService(
            self.config, self._runtime_data_dir, store=self.store
        )
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
        if is_cloud_command(raw) or is_tool_command(raw):
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

    @filter.regex(MATERIAL_CMD_RE, priority=TOOL_CMD_PRIORITY)
    async def on_twrpg_material_command(self, event: AstrMessageEvent):
        """世界材料 <物品名> [xN] — 按主存档库存统计目标物品缺料"""
        raw = event.message_str.strip()
        query_text = extract_material_query(raw)
        if query_text is None:
            return
        event.stop_event()

        if not self.store.loaded:
            yield event.plain_result("❌ 离线数据尚未准备。\n请确认插件目录下存在 data/twrpg_query/items.json")
            return

        if not query_text:
            yield event.plain_result(
                "用法: 世界材料 <物品名> [数量]\n"
                "例如: 世界材料 世界破坏者\n"
                "      界材料 太阳石 x5\n"
                "绑定云存档后会自动扣除携带 / 背包 / 仓库中的现成材料。"
            )
            return

        name, quantity = parse_quantity(query_text)
        target_id = resolve_item_id(self.store, name)
        if not target_id:
            yield event.plain_result(f"❌ 未找到「{name}」的相关物品。")
            return

        if not self.store.recipes.get(target_id) and not self.store.drops_by_item.get(target_id):
            yield event.plain_result(
                f"「{self.store.item_name(target_id)}」没有合成配方与掉落记录，无需统计材料。"
            )
            return

        inventory = None
        save_name = ""
        if self._cloud.enabled():
            snapshot = await self._cloud.inventory_snapshot(str(event.get_sender_id()))
            if isinstance(snapshot, InventorySnapshot):
                inventory = snapshot.counts
                save_name = snapshot.display_name

        try:
            plan = await asyncio.to_thread(
                plan_materials,
                self.store,
                target_id,
                quantity=quantity,
                inventory=inventory,
            )
        except Exception as e:
            logger.error(f"[TWRPG Query] 统计材料失败 ({target_id}): {e}")
            yield event.plain_result("材料统计失败，请稍后再试。")
            return

        if plan is None:
            yield event.plain_result(f"❌ 无法解析「{name}」的合成配方。")
            return

        try:
            image_path = await asyncio.to_thread(generate_material_card, plan)
            yield event.chain_result(
                [
                    Plain(format_material_caption(plan, save_name=save_name)),
                    Image.fromFileSystem(image_path),
                ]
            )
        except Exception as e:
            logger.error(f"[TWRPG Query] 生成材料统计卡片失败 ({target_id}): {e}")
            yield event.plain_result(format_material_text(plan, save_name=save_name))

    @filter.regex(CODEX_CMD_RE, priority=TOOL_CMD_PRIORITY)
    async def on_twrpg_codex_command(self, event: AstrMessageEvent):
        """世界图鉴 [分类] [阶段] [关键词] [第N页] — 图鉴分类浏览"""
        raw = event.message_str.strip()
        query_text = extract_codex_query(raw)
        if query_text is None:
            return
        event.stop_event()

        if not self.store.loaded:
            yield event.plain_result("❌ 离线数据尚未准备。\n请确认插件目录下存在 data/twrpg_query/items.json")
            return

        tokens = [token for token in re.split(r"\s+", query_text) if token]
        if not tokens:
            yield event.plain_result(category_hint_text(self.store))
            return

        category, stage, keyword, page = parse_codex_args(tokens)
        try:
            selection = await asyncio.to_thread(
                build_selection,
                self.store,
                category,
                stage=stage,
                keyword=keyword,
                page=page,
            )
        except Exception as e:
            logger.error(f"[TWRPG Query] 图鉴检索失败 ({query_text}): {e}")
            yield event.plain_result("图鉴检索失败，请稍后再试。")
            return

        if selection.total <= 0:
            yield event.plain_result(
                f"❌ 图鉴中没有符合「{selection.label or query_text}」的条目。\n"
                "可用分类：武器 / 衣服 / 头盔 / 饰品 / 翅膀 / 材料 / 其他 / 全部"
            )
            return

        try:
            caption, image_path = await asyncio.to_thread(
                render_codex, self.store, selection
            )
            if image_path:
                yield event.chain_result(
                    [Plain(caption), Image.fromFileSystem(image_path)]
                )
            else:
                yield event.plain_result(caption)
        except Exception as e:
            logger.error(f"[TWRPG Query] 生成图鉴卡片失败 ({query_text}): {e}")
            yield event.plain_result(format_codex_text(self.store, selection))

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
            card_path = await asyncio.to_thread(generate_card, display)
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

    @filter.regex(_READER_UPDATE_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_reader_update_content(self, event: AstrMessageEvent):
        event.stop_event()
        if not self._cloud.enabled():
            yield event.plain_result(CLOUD_DISABLED_HINT)
            return
        yield event.plain_result(await self._cloud.reader_update_content())

    @filter.regex(_CLOUD_RESERVED_RE, priority=CLOUD_FALLBACK_PRIORITY)
    async def on_cloud_command_fallback(self, event: AstrMessageEvent):
        event.stop_event()
        if not self._cloud.enabled():
            yield event.plain_result(CLOUD_DISABLED_HINT)
            return
        yield event.plain_result(cloud_command_usage(event.message_str))

    @filter.regex(_SAVES_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_list_saves(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        async for msg in self._yield_cloud_inventory(
            event, await self._cloud.list_saves(str(event.get_sender_id()))
        ):
            yield msg
        event.stop_event()

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

    @filter.regex(_ONLINE_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_online(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        event.stop_event()
        yield event.plain_result(
            await self._cloud.online_status(str(event.get_sender_id()))
        )

    async def _yield_cloud_inventory(self, event: AstrMessageEvent, result: CloudInventoryResult | str):
        if isinstance(result, str):
            yield event.plain_result(result)
            return

        image_path = result.image_path
        if image_path and os.path.exists(image_path):
            yield event.chain_result(
                [
                    Plain(result.caption),
                    Image.fromFileSystem(image_path),
                ]
            )
            return

        if image_path:
            logger.warning(f"[TWRPG Query] 云存档图片不存在: {image_path}")
        yield event.plain_result(result.caption)

    @filter.regex(_BACKPACK_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_show_backpack(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        async for msg in self._yield_cloud_inventory(
            event, await self._cloud.backpack(str(event.get_sender_id()))
        ):
            yield msg
        event.stop_event()

    @filter.regex(_WAREHOUSE_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_show_warehouse(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        async for msg in self._yield_cloud_inventory(
            event, await self._cloud.warehouse(str(event.get_sender_id()))
        ):
            yield msg
        event.stop_event()

    @filter.regex(_CARRIED_RE, priority=CLOUD_CMD_PRIORITY)
    async def on_cloud_show_carried(self, event: AstrMessageEvent):
        if not self._cloud.enabled():
            return
        async for msg in self._yield_cloud_inventory(
            event, await self._cloud.carried(str(event.get_sender_id()))
        ):
            yield msg
        event.stop_event()

    async def terminate(self):
        await self._cloud.close()
        logger.info("世界RPG 查询插件已卸载")
