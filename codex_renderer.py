"""图鉴分类浏览卡片渲染（复用背包图标网格）。"""

from __future__ import annotations

from .card_renderer import CARD_WIDTH
from .codex import PAGE_SIZE, CodexSelection, stage_token
from .data_loader import TwrpgDataStore
from .inventory_renderer import (
    InventoryLayout,
    InventoryTile,
    generate_inventory_grid,
)

# 图鉴用 4 列，留出更多空间显示较长的物品名
CODEX_LAYOUT = InventoryLayout(
    cols=4,
    max_items=PAGE_SIZE,
    card_width=CARD_WIDTH,
    icon_size=52,
    name_zone=30,
    show_hero_dots=False,
)


def build_codex_tiles(store: TwrpgDataStore, item_ids: list[str]) -> list[InventoryTile]:
    """把物品 ID 列表转成网格卡片用的 tile。"""
    tiles: list[InventoryTile] = []
    for item_id in item_ids:
        display = store.build_display(item_id)
        if display is None:
            continue
        tiles.append(
            InventoryTile(
                raw_line="",
                name=display.name,
                quantity=1,
                display=display,
            )
        )
    return tiles


def render_codex(
    store: TwrpgDataStore, selection: CodexSelection
) -> tuple[str, str | None]:
    """渲染图鉴页，返回 (说明文字, 图片路径或 None)。"""
    if selection.total <= 0:
        return f"【图鉴】{selection.label}：没有找到符合的条目。", None

    tiles = build_codex_tiles(store, selection.item_ids)
    caption = f"【图鉴】{selection.label}（共 {selection.total} 件"
    if selection.page_count > 1:
        caption += f" · 第 {selection.page}/{selection.page_count} 页"
    caption += "）"
    if selection.has_next:
        base = f"世界图鉴 {selection.category}" if selection.category else "世界图鉴"
        if selection.stage is not None:
            base += f" {stage_token(selection.stage)}"
        if selection.keyword:
            base += f" {selection.keyword}"
        caption += f"\n下一页：{base} 第{selection.page + 1}页"

    sub_text = f"共 {selection.total} 件"
    if selection.page_count > 1:
        sub_text = f"第 {selection.page}/{selection.page_count} 页 · 共 {selection.total} 件"

    image_path = generate_inventory_grid(
        save_display_name="图鉴",
        section_label=selection.label,
        tiles=tiles,
        total_count=selection.total,
        layout=CODEX_LAYOUT,
        sub_text=sub_text,
    )
    return caption, image_path


def format_codex_text(
    store: TwrpgDataStore, selection: CodexSelection, *, limit: int = PAGE_SIZE
) -> str:
    """纯文本兜底（出图失败时使用）。"""
    if selection.total <= 0:
        return f"【图鉴】{selection.label}：没有找到符合的条目。"
    lines = [f"【图鉴】{selection.label}（共 {selection.total} 件）"]
    for index, item_id in enumerate(selection.item_ids[:limit], start=1):
        display = store.build_display(item_id)
        name = display.name if display else store.item_name(item_id)
        stage = display.stage_label if display else ""
        lines.append(f"{index}. {name} {stage}".strip())
    if selection.page_count > 1:
        lines.append(f"第 {selection.page}/{selection.page_count} 页")
    if selection.has_next:
        lines.append(f"下一页：世界图鉴 {selection.label} 第{selection.page + 1}页")
    return "\n".join(lines)
