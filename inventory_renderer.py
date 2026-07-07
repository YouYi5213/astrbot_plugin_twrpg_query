"""云存档背包/仓库/携带 — 密集图标网格卡片。"""

from __future__ import annotations

import math
import os
import uuid
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .card_renderer import (
    CARD_WIDTH,
    COLORS,
    _ensure_dirs,
    _font,
    _load_image,
    _paste_in_slot,
    _text_height,
    _text_width,
    _wrap_lines,
)
from .core.save_parser import parse_save_item_line
from .data_loader import ItemDisplay, TwrpgDataStore

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_CARDS_DIR = os.path.join(_PLUGIN_DIR, "data", "cards")

GRID_COLS = 5
INVENTORY_DISPLAY_LIMIT = 40
GRID_PADDING = 10
GRID_GAP = 3
CELL_W = (CARD_WIDTH - GRID_PADDING * 2 - GRID_GAP * (GRID_COLS - 1)) // GRID_COLS
ICON_SIZE = 46
ICON_ZONE = 50
NAME_ZONE = 26
FOOTER_H = 13
CELL_H = ICON_ZONE + 2 + NAME_ZONE + FOOTER_H
HERO_DOT = 13
TITLE_H = 34


@dataclass
class InventoryTile:
    raw_line: str
    name: str
    quantity: int = 1
    display: ItemDisplay | None = None


def build_inventory_tiles(
    raw_lines: list[str],
    store: TwrpgDataStore,
    *,
    limit: int,
) -> list[InventoryTile]:
    tiles: list[InventoryTile] = []
    for raw in raw_lines[:limit]:
        name, qty = parse_save_item_line(raw)
        if not name:
            continue
        tiles.append(
            InventoryTile(
                raw_line=raw,
                name=name,
                quantity=qty,
                display=store.resolve_item_by_name(name) if store.loaded else None,
            )
        )
    return tiles


def _draw_placeholder(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (1, 1, size - 2, size - 2),
        radius=6,
        fill=(48, 52, 66, 255),
        outline=(72, 78, 96, 255),
        width=1,
    )
    font = _font(16, bold=True)
    w = _text_width(draw, "?", font)
    h = _text_height(draw, "?", font)
    draw.text(((size - w) // 2, (size - h) // 2 - 1), "?", fill=(130, 136, 152), font=font)
    return img


def _draw_stack_badge(draw: ImageDraw.ImageDraw, x: int, y: int, count: int) -> None:
    if count <= 1:
        return
    text = str(count)
    font = _font(11, bold=True)
    tw = _text_width(draw, text, font)
    th = _text_height(draw, text, font)
    bx = x + ICON_SIZE - tw - 4
    by = y + ICON_SIZE - th - 2
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.text((bx + dx, by + dy), text, fill=(0, 0, 0), font=font)
    draw.text((bx, by), text, fill=(255, 255, 255), font=font)


def _tile_subtitle(tile: InventoryTile) -> str:
    display = tile.display
    if not display:
        return ""
    if display.exclusives:
        return display.exclusives[0].hero_name[:6]
    if display.limit_heroes:
        return display.limit_heroes[0].name[:6]
    return ""


def _draw_tile(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    tile: InventoryTile | None,
    x: int,
    y: int,
) -> None:
    draw.rounded_rectangle(
        (x, y, x + CELL_W - 1, y + CELL_H - 1),
        radius=8,
        fill=(40, 43, 56),
        outline=(62, 68, 86),
        width=1,
    )
    if tile is None:
        return

    display = tile.display
    name = display.name if display else tile.name
    stage = display.stage_label if display else ""
    level = display.level if display else 0
    subtitle = _tile_subtitle(tile)

    icon_x = x + (CELL_W - ICON_SIZE) // 2
    icon_y = y + 2
    icon_path = display.icon if display else None
    icon = _load_image(icon_path, (ICON_SIZE, ICON_SIZE)) if icon_path else None
    if icon is None:
        icon = _draw_placeholder(ICON_SIZE)
    _paste_in_slot(canvas, icon, icon_x, icon_y, ICON_SIZE, ICON_SIZE)
    _draw_stack_badge(draw, icon_x, icon_y, tile.quantity)

    if display and display.limit_heroes:
        hx = x + 3
        for hero in display.limit_heroes[:3]:
            hero_icon = _load_image(hero.icon, (HERO_DOT, HERO_DOT))
            if hero_icon:
                canvas.paste(hero_icon, (hx, y + 3), hero_icon)
                hx += HERO_DOT - 3

    if stage:
        stage_font = _font(9, bold=True)
        stage_w = _text_width(draw, stage, stage_font)
        draw.text(
            (x + CELL_W - stage_w - 3, y + 2),
            stage,
            fill=COLORS["stage"],
            font=stage_font,
        )

    name_font = _font(10)
    name_top = y + ICON_ZONE + 2
    max_name_w = CELL_W - 6
    lines = _wrap_lines(draw, name, name_font, max_name_w)[:2]
    if len(lines) == 1 and _text_width(draw, name, name_font) > max_name_w:
        lines = _wrap_lines(draw, name, _font(9), max_name_w)[:2]
        name_font = _font(9)
    line_h = _text_height(draw, "测", name_font) + 1
    for index, line in enumerate(lines):
        lw = _text_width(draw, line, name_font)
        draw.text(
            (x + (CELL_W - lw) // 2, name_top + index * line_h),
            line,
            fill=COLORS["text"],
            font=name_font,
        )

    footer_y = y + CELL_H - FOOTER_H
    footer_font = _font(9)
    if level > 0:
        draw.text((x + 4, footer_y), f"Lv{level}", fill=COLORS["muted"], font=footer_font)
    if subtitle:
        sw = _text_width(draw, subtitle, footer_font)
        draw.text(
            (x + CELL_W - sw - 4, footer_y),
            subtitle,
            fill=(210, 150, 210),
            font=footer_font,
        )


def generate_inventory_grid(
    *,
    title: str,
    tiles: list[InventoryTile],
    total_count: int | None = None,
) -> str:
    _ensure_dirs()
    os.makedirs(_CARDS_DIR, exist_ok=True)

    count = total_count if total_count is not None else len(tiles)
    rows = max(1, math.ceil(len(tiles) / GRID_COLS)) if tiles else 1
    grid_h = rows * CELL_H + (rows - 1) * GRID_GAP
    height = GRID_PADDING * 2 + TITLE_H + 6 + grid_h + 8

    card = Image.new("RGB", (CARD_WIDTH, height), COLORS["bg"])
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (6, 6, CARD_WIDTH - 6, height - 6),
        radius=12,
        fill=COLORS["panel"],
        outline=COLORS["border"],
        width=1,
    )

    title_font = _font(18, bold=True)
    subtitle_font = _font(12)
    header = title
    sub = f"共 {count} 件"
    draw.text((GRID_PADDING + 4, GRID_PADDING + 4), header, fill=COLORS["title"], font=title_font)
    sub_w = _text_width(draw, sub, subtitle_font)
    draw.text(
        (CARD_WIDTH - GRID_PADDING - 4 - sub_w, GRID_PADDING + 8),
        sub,
        fill=COLORS["muted"],
        font=subtitle_font,
    )

    grid_top = GRID_PADDING + TITLE_H + 4
    slots = rows * GRID_COLS
    for index in range(slots):
        row = index // GRID_COLS
        col = index % GRID_COLS
        cx = GRID_PADDING + col * (CELL_W + GRID_GAP)
        cy = grid_top + row * (CELL_H + GRID_GAP)
        tile = tiles[index] if index < len(tiles) else None
        _draw_tile(card, draw, tile, cx, cy)

    out_path = os.path.join(_CARDS_DIR, f"inv_{uuid.uuid4().hex[:8]}.png")
    card.save(out_path, format="PNG", optimize=True)
    return out_path


def render_save_inventory(
    store: TwrpgDataStore,
    *,
    save_name: str,
    section_label: str,
    raw_lines: list[str],
    limit: int,
) -> tuple[str, str | None]:
    """返回 (说明文字, 图片路径或 None)。"""
    total = len(raw_lines)
    if total == 0:
        return f"【{save_name}】{section_label}（空）", None

    if not store.loaded:
        lines = [f"{index}. {item}" for index, item in enumerate(raw_lines[:limit], start=1)]
        if len(raw_lines) > limit:
            lines.append(f"... 还有 {len(raw_lines) - limit} 条未显示")
        body = "\n".join(lines) if lines else "（空）"
        return f"【{save_name}】{section_label}（{total}）\n{body}", None

    tiles = build_inventory_tiles(raw_lines, store, limit=limit)
    caption = f"【{save_name}】{section_label}（{total}）"
    if total > limit:
        caption += f"\n仅展示前 {limit} 件，还有 {total - limit} 件未显示。"
    image_path = generate_inventory_grid(
        title=f"{section_label}",
        tiles=tiles,
        total_count=total,
    )
    return caption, image_path
