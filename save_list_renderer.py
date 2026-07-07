"""云存档列表 — 紧凑多列图片卡片。"""

from __future__ import annotations

import math
import os
import uuid
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .card_renderer import CARD_WIDTH, COLORS, _ensure_dirs, _font, _text_height, _text_width
from .inventory_renderer import format_save_display_name

_CARDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cards")

PRIMARY_MARK = "\u2605"  # ★ — 内置字体可渲染，emoji ⭐ 会显示为方框

LIST_COLS = 4
LIST_PADDING = 12
LIST_GAP = 4
ROW_H = 28
TITLE_H = 36
FOOTER_H = 24


@dataclass(frozen=True)
class SaveListRow:
    index: int
    display_name: str
    is_primary: bool


def _truncate_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if _text_width(draw, text, font) <= max_width:
        return text
    trimmed = text
    while trimmed and _text_width(draw, trimmed + "…", font) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + "…") if trimmed else "…"


def _cell_width() -> int:
    inner = CARD_WIDTH - LIST_PADDING * 2 - LIST_GAP * (LIST_COLS - 1)
    return inner // LIST_COLS


def generate_save_list_image(
    *,
    username: str,
    entries: list[SaveListRow],
) -> str:
    _ensure_dirs()
    os.makedirs(_CARDS_DIR, exist_ok=True)

    cols = LIST_COLS
    cell_w = _cell_width()
    rows = max(1, math.ceil(len(entries) / cols)) if entries else 1
    grid_h = rows * ROW_H + max(0, rows - 1) * LIST_GAP
    height = LIST_PADDING * 2 + TITLE_H + 6 + grid_h + FOOTER_H

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
    header = f"云存档 · {username}"
    sub = f"共 {len(entries)} 个"
    draw.text((LIST_PADDING + 4, LIST_PADDING + 4), header, fill=COLORS["title"], font=title_font)
    sub_w = _text_width(draw, sub, subtitle_font)
    draw.text(
        (CARD_WIDTH - LIST_PADDING - 4 - sub_w, LIST_PADDING + 8),
        sub,
        fill=COLORS["muted"],
        font=subtitle_font,
    )

    item_font = _font(12)
    primary_font = _font(12, bold=True)
    grid_top = LIST_PADDING + TITLE_H + 4
    slots = rows * cols

    for slot in range(slots):
        row = slot // cols
        col = slot % cols
        cx = LIST_PADDING + col * (cell_w + LIST_GAP)
        cy = grid_top + row * (ROW_H + LIST_GAP)

        if slot >= len(entries):
            continue

        entry = entries[slot]
        label = f"{entry.index}. {entry.display_name}"
        if entry.is_primary:
            star = f" {PRIMARY_MARK}"
            draw.rounded_rectangle(
                (cx, cy, cx + cell_w - 1, cy + ROW_H - 1),
                radius=6,
                fill=(52, 58, 74),
                outline=(255, 200, 96),
                width=1,
            )
            font = primary_font
            color = COLORS["title"]
            star_w = _text_width(draw, star, font)
            text = _truncate_text(draw, label, font, cell_w - 8 - star_w) + star
        else:
            font = item_font
            color = COLORS["text"]
            text = _truncate_text(draw, label, font, cell_w - 8)
        ty = cy + (ROW_H - _text_height(draw, text, font)) // 2
        draw.text((cx + 4, ty), text, fill=color, font=font)

    footer_font = _font(11)
    footer = f"{PRIMARY_MARK} 主存档 · 世界切换 <序号>"
    draw.text(
        (LIST_PADDING + 4, height - LIST_PADDING - FOOTER_H + 4),
        footer,
        fill=COLORS["muted"],
        font=footer_font,
    )

    out_path = os.path.join(_CARDS_DIR, f"saves_{uuid.uuid4().hex[:8]}.png")
    card.save(out_path, format="PNG", optimize=True)
    return out_path


def render_save_list(
    username: str,
    save_names: list[str],
    *,
    primary_name: str = "",
) -> tuple[str, str]:
    """返回 (说明文字, 图片路径)。"""
    entries = [
        SaveListRow(
            index=index,
            display_name=format_save_display_name(name),
            is_primary=name == primary_name,
        )
        for index, name in enumerate(save_names, start=1)
    ]
    caption = (
        f"云账号 {username} · 共 {len(entries)} 个存档\n"
        f"{PRIMARY_MARK} 主存档 · 使用「世界切换 <序号>」"
    )
    image_path = generate_save_list_image(username=username, entries=entries)
    return caption, image_path
