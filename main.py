"""
世界RPG（TWRPG）物品查询插件
==============================
指令: 世界 <物品名> 或 界 <物品名>（无需 / 前缀）
功能: 从本地离线数据库查询物品，以图片卡片展示属性、合成、掉落等信息
"""

from __future__ import annotations

import os
import re

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .card_renderer import format_text_fallback, generate_item_card
from .data_loader import TwrpgDataStore, normalize_query, resolve_data_dir
from .icon_utils import resolve_icons_dir

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = resolve_data_dir(_PLUGIN_DIR)
_ICONS_DIR = resolve_icons_dir(_PLUGIN_DIR)
_MAX_MATCHES = 5

_CMD_RE = re.compile(r"^/?(世界|界)(\s|$)")


def _normalize_message(text: str) -> str:
    text = text.strip()
    if text.startswith("/"):
        return text[1:].strip()
    return text


def _extract_query_text(text: str) -> str | None:
    normalized = _normalize_message(text)
    for prefix in ("世界", "界"):
        if normalized == prefix:
            return ""
        if normalized.startswith(prefix + " "):
            return normalized[len(prefix) + 1 :].strip()
    return None


def _match_label(store: TwrpgDataStore, item_id: str, query: str) -> str:
    display = store.build_display(item_id)
    if not display:
        return item_id
    key = normalize_query(query)
    name_key = normalize_query(display.name)
    if name_key == key:
        return display.name
    return display.name


class TwrpgQueryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.store = TwrpgDataStore(_DATA_DIR, icons_dir=_ICONS_DIR)
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
                f"世界RPG 查询插件已加载，共 {len(self.store.items_by_id)} 个物品"
            )
        except Exception as e:
            logger.error(f"加载 TWRPG 数据失败: {e}")

    @filter.regex(_CMD_RE, priority=10)
    async def on_twrpg_command(self, event: AstrMessageEvent):
        """处理世界RPG 物品查询指令（支持无 / 前缀）。"""
        raw = event.message_str.strip()
        query_text = _extract_query_text(raw)
        if query_text is None:
            return

        async for result in self._handle_query(event, query_text):
            yield result
        event.stop_event()

    async def _handle_query(self, event: AstrMessageEvent, text: str):
        if not self.store.loaded:
            yield event.plain_result(
                "❌ 离线数据尚未准备。\n"
                f"请确认插件目录下存在 data/twrpg_query/items.json\n"
                f"当前路径: {_DATA_DIR}"
            )
            return

        if not text:
            yield event.plain_result(
                "用法: 世界 <物品名>\n"
                "      界 <物品名>\n"
                "例如: 世界 洞悉·真理之瞳\n"
                "      界 太阳石"
            )
            return

        matches = self.store.search(text, limit=_MAX_MATCHES + 3)
        if not matches:
            yield event.plain_result(f"❌ 未找到「{text}」的相关物品。")
            return

        query_key = normalize_query(text)
        exact_matches = [
            item_id
            for item_id in matches
            if normalize_query(self.store.item_name(item_id)) == query_key
        ]
        if len(exact_matches) == 1:
            matches = exact_matches

        if len(matches) > 1:
            lines = [
                f"找到 {len(matches)} 个匹配结果，请输入更精确的名称后重新查询：",
                "",
            ]
            for item_id in matches[:8]:
                lines.append(f"· {_match_label(self.store, item_id, text)}")
            yield event.plain_result("\n".join(lines))
            return

        item_id = matches[0]
        display = self.store.build_display(item_id)
        if not display:
            yield event.plain_result(f"❌ 物品数据异常: {item_id}")
            return

        try:
            card_path = generate_item_card(display)
            yield event.image_result(card_path)
        except Exception as e:
            logger.error(f"生成 TWRPG 查询卡片失败 ({item_id}): {e}")
            yield event.plain_result(format_text_fallback(display))

    async def terminate(self):
        logger.info("世界RPG 查询插件已卸载")
