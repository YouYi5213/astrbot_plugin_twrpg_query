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

GRID_PADDING = 10
GRID_GAP = 3
HERO_DOT = 13
TITLE_H = 34


@dataclass(frozen=True)
class InventoryLayout:
    cols: int
    max_items: int
    card_width: int
    icon_size: int
    name_zone: int
    footer_h: int = 13
    fixed_rows: int | None = None

    @property
    def icon_zone(self) -> int:
        return self.icon_size + 4

    @property
    def cell_h(self) -> int:
        return self.icon_zone + 2 + self.name_zone + self.footer_h

    @property
    def cell_w(self) -> int:
        inner = self.card_width - GRID_PADDING * 2 - GRID_GAP * (self.cols - 1)
        return inner // self.cols


BACKPACK_LAYOUT = InventoryLayout(
    cols=5,
    max_items=40,
    card_width=CARD_WIDTH,
    icon_size=46,
    name_zone=26,
)

CARRIED_LAYOUT = InventoryLayout(
    cols=2,
    max_items=6,
    card_width=280,
    icon_size=54,
    name_zone=30,
    fixed_rows=3,
)


@dataclass
class InventoryTile:
    raw_line: str
    name: str
    quantity: int = 1
    display: ItemDisplay | None = None


def format_save_display_name(filename: str) -> str:
    name = (filename or "").strip()
    if name.lower().endswith(".txt"):
        return name[:-4]
    return name


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


def _draw_stack_badge(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    count: int,
    *,
    icon_size: int,
) -> None:
    if count <= 1:
        return
    text = str(count)
    font = _font(11, bold=True)
    tw = _text_width(draw, text, font)
    th = _text_height(draw, text, font)
    bx = x + icon_size - tw - 4
    by = y + icon_size - th - 2
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
    *,
    layout: InventoryLayout,
) -> None:
    cell_w = layout.cell_w
    cell_h = layout.cell_h
    icon_size = layout.icon_size

    draw.rounded_rectangle(
        (x, y, x + cell_w - 1, y + cell_h - 1),
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

    icon_x = x + (cell_w - icon_size) // 2
    icon_y = y + 2
    icon_path = display.icon if display else None
    icon = _load_image(icon_path, (icon_size, icon_size)) if icon_path else None
    if icon is None:
        icon = _draw_placeholder(icon_size)
    _paste_in_slot(canvas, icon, icon_x, icon_y, icon_size, icon_size)
    _draw_stack_badge(draw, icon_x, icon_y, tile.quantity, icon_size=icon_size)

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
            (x + cell_w - stage_w - 3, y + 2),
            stage,
            fill=COLORS["stage"],
            font=stage_font,
        )

    name_font = _font(10)
    name_top = y + layout.icon_zone + 2
    max_name_w = cell_w - 6
    lines = _wrap_lines(draw, name, name_font, max_name_w)[:2]
    if len(lines) == 1 and _text_width(draw, name, name_font) > max_name_w:
        lines = _wrap_lines(draw, name, _font(9), max_name_w)[:2]
        name_font = _font(9)
    line_h = _text_height(draw, "测", name_font) + 1
    for index, line in enumerate(lines):
        lw = _text_width(draw, line, name_font)
        draw.text(
            (x + (cell_w - lw) // 2, name_top + index * line_h),
            line,
            fill=COLORS["text"],
            font=name_font,
        )

    footer_y = y + cell_h - layout.footer_h
    footer_font = _font(9)
    if level > 0:
        draw.text((x + 4, footer_y), f"Lv{level}", fill=COLORS["muted"], font=footer_font)
    if subtitle:
        sw = _text_width(draw, subtitle, footer_font)
        draw.text(
            (x + cell_w - sw - 4, footer_y),
            subtitle,
            fill=(210, 150, 210),
            font=footer_font,
        )


def generate_inventory_grid(
    *,
    save_display_name: str,
    section_label: str,
    tiles: list[InventoryTile],
    total_count: int,
    layout: InventoryLayout,
) -> str:
    _ensure_dirs()
    os.makedirs(_CARDS_DIR, exist_ok=True)

    cols = layout.cols
    cell_h = layout.cell_h
    card_width = layout.card_width

    if layout.fixed_rows is not None:
        rows = layout.fixed_rows
    elif tiles:
        rows = math.ceil(len(tiles) / cols)
    else:
        rows = 1

    grid_h = rows * cell_h + (rows - 1) * GRID_GAP
    height = GRID_PADDING * 2 + TITLE_H + 6 + grid_h + 8

    card = Image.new("RGB", (card_width, height), COLORS["bg"])
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (6, 6, card_width - 6, height - 6),
        radius=12,
        fill=COLORS["panel"],
        outline=COLORS["border"],
        width=1,
    )

    title_font = _font(18, bold=True)
    subtitle_font = _font(12)
    header = f"{save_display_name} · {section_label}"
    sub = f"共 {total_count} 件"
    draw.text((GRID_PADDING + 4, GRID_PADDING + 4), header, fill=COLORS["title"], font=title_font)
    sub_w = _text_width(draw, sub, subtitle_font)
    draw.text(
        (card_width - GRID_PADDING - 4 - sub_w, GRID_PADDING + 8),
        sub,
        fill=COLORS["muted"],
        font=subtitle_font,
    )

    grid_top = GRID_PADDING + TITLE_H + 4
    slots = rows * cols
    for index in range(slots):
        row = index // cols
        col = index % cols
        cx = GRID_PADDING + col * (layout.cell_w + GRID_GAP)
        cy = grid_top + row * (cell_h + GRID_GAP)
        tile = tiles[index] if index < len(tiles) else None
        _draw_tile(card, draw, tile, cx, cy, layout=layout)

    out_path = os.path.join(_CARDS_DIR, f"inv_{uuid.uuid4().hex[:8]}.png")
    card.save(out_path, format="PNG", optimize=True)
    return out_path


def render_save_inventory(
    store: TwrpgDataStore,
    *,
    save_name: str,
    section_label: str,
    raw_lines: list[str],
    layout: InventoryLayout,
) -> tuple[str, str | None]:
    """返回 (说明文字, 图片路径或 None)。"""
    display_name = format_save_display_name(save_name)
    total = len(raw_lines)
    limit = layout.max_items

    if total == 0:
        return f"【{display_name}】{section_label}（空）", None

    if not store.loaded:
        lines = [f"{index}. {item}" for index, item in enumerate(raw_lines[:limit], start=1)]
        if total > limit:
            lines.append(f"... 还有 {total - limit} 条未显示")
        body = "\n".join(lines) if lines else "（空）"
        return f"【{display_name}】{section_label}（{total}）\n{body}", None

    tiles = build_inventory_tiles(raw_lines, store, limit=limit)
    caption = f"【{display_name}】{section_label}（{total}）"
    if total > limit:
        caption += f"\n仅展示前 {limit} 件，还有 {total - limit} 件未显示。"
    image_path = generate_inventory_grid(
        save_display_name=display_name,
        section_label=section_label,
        tiles=tiles,
        total_count=total,
        layout=layout,
    )
    return caption, image_path
