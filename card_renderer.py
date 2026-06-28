"""TWRPG 物品查询卡片图片渲染。"""

from __future__ import annotations

import os
import uuid
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from .data_loader import ItemDisplay

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.join(_PLUGIN_DIR, "assets", "fonts")
_CARDS_DIR = os.path.join(_PLUGIN_DIR, "data", "cards")

CARD_WIDTH = 640
CARD_PADDING = 22
SECTION_GAP = 14
LINE_GAP = 4
ROW_HEIGHT = 28
HEADER_HEIGHT = 34
TITLE_HEIGHT = 42

COLORS = {
    "bg": (24, 26, 34),
    "panel": (34, 37, 48),
    "border": (88, 96, 120),
    "title": (255, 214, 120),
    "header": (120, 190, 255),
    "text": (230, 232, 240),
    "muted": (160, 166, 182),
    "accent": (255, 180, 96),
    "line": (58, 62, 78),
}

_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_RESOLVED_FONT: str | None = None


def _ensure_dirs() -> None:
    os.makedirs(_CARDS_DIR, exist_ok=True)


def _resolve_font_path() -> str | None:
    global _RESOLVED_FONT
    if _RESOLVED_FONT is not None:
        return _RESOLVED_FONT or None

    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        os.path.join(_FONT_DIR, "NotoSansSC-Bold.otf"),
        os.path.join(_FONT_DIR, "NotoSansSC-Regular.otf"),
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                ImageFont.truetype(path, 16)
                _RESOLVED_FONT = path
                return path
            except OSError:
                continue
    _RESOLVED_FONT = ""
    return None


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    key = ("bold" if bold else "regular", size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    path = _resolve_font_path()
    if path:
        try:
            font = ImageFont.truetype(path, size)
            _FONT_CACHE[key] = font
            return font
        except OSError:
            pass

    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    if not text:
        return 0
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _text_height(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    if not text:
        return 0
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def _wrap_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_width: int,
) -> list[str]:
    if not text:
        return []

    lines: list[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        if _text_width(draw, paragraph, font) <= max_width:
            lines.append(paragraph)
            continue
        current = ""
        for ch in paragraph:
            candidate = current + ch
            if _text_width(draw, candidate, font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def _format_chance(chance: float) -> str:
    if chance >= 10:
        return f"{chance:g}%"
    if chance >= 1:
        text = f"{chance:.1f}".rstrip("0").rstrip(".")
        return f"{text}%"
    return f"{chance:.2g}%"


def _section_has_content(item: ItemDisplay, section: str) -> bool:
    if section == "wear_limit":
        return bool(item.wear_limit or item.exclusives)
    if section == "stats":
        return bool(item.description)
    if section == "recipe":
        return bool(item.recipe)
    if section == "crafts_into":
        return bool(item.crafts_into)
    if section == "boss_drops":
        return bool(item.boss_drops)
    return False


def _estimate_height(draw: ImageDraw.ImageDraw, item: ItemDisplay) -> int:
    body_font = _font(15)
    small_font = _font(14)
    content_width = CARD_WIDTH - CARD_PADDING * 2 - 20
    y = CARD_PADDING + TITLE_HEIGHT + SECTION_GAP

    if _section_has_content(item, "wear_limit"):
        y += HEADER_HEIGHT
        if item.wear_limit:
            y += len(item.wear_limit) * ROW_HEIGHT
        for ex in item.exclusives:
            y += ROW_HEIGHT
            y += len(_wrap_lines(draw, ex.description, small_font, content_width - 16)) * 18
            y += LINE_GAP
        y += SECTION_GAP

    if _section_has_content(item, "stats"):
        y += HEADER_HEIGHT
        y += len(_wrap_lines(draw, item.description, body_font, content_width)) * 20
        y += SECTION_GAP

    if _section_has_content(item, "recipe"):
        y += HEADER_HEIGHT
        y += len(item.recipe) * ROW_HEIGHT
        y += SECTION_GAP

    if _section_has_content(item, "crafts_into"):
        y += HEADER_HEIGHT
        y += len(item.crafts_into) * ROW_HEIGHT
        y += SECTION_GAP

    if _section_has_content(item, "boss_drops"):
        y += HEADER_HEIGHT
        y += len(item.boss_drops) * ROW_HEIGHT
        y += SECTION_GAP

    return y + CARD_PADDING


def _draw_header(draw: ImageDraw.ImageDraw, y: int, title: str) -> int:
    draw.text(
        (CARD_PADDING + 8, y),
        title,
        fill=COLORS["header"],
        font=_font(16, bold=True),
    )
    line_y = y + 24
    draw.line(
        [(CARD_PADDING, line_y), (CARD_WIDTH - CARD_PADDING, line_y)],
        fill=COLORS["line"],
        width=1,
    )
    return line_y + 10


def _draw_bullet_lines(
    draw: ImageDraw.ImageDraw,
    y: int,
    lines: Iterable[str],
    font,
    indent: int = 16,
    color=COLORS["text"],
) -> int:
    x = CARD_PADDING + indent
    max_width = CARD_WIDTH - CARD_PADDING - indent - 8
    for line in lines:
        wrapped = _wrap_lines(draw, line, font, max_width)
        if not wrapped:
            y += 18
            continue
        for part in wrapped:
            draw.text((x, y), part, fill=color, font=font)
            y += _text_height(draw, part, font) + LINE_GAP
    return y


def _draw_list_rows(
    draw: ImageDraw.ImageDraw,
    y: int,
    rows: list[tuple[str, str | None]],
) -> int:
    font = _font(15)
    left = CARD_PADDING + 16
    right = CARD_WIDTH - CARD_PADDING - 16
    for left_text, right_text in rows:
        draw.text((left, y + 4), left_text, fill=COLORS["text"], font=font)
        if right_text:
            rw = _text_width(draw, right_text, font)
            draw.text((right - rw, y + 4), right_text, fill=COLORS["muted"], font=font)
        y += ROW_HEIGHT
    return y


def generate_item_card(item: ItemDisplay) -> str:
    _ensure_dirs()
    tmp = Image.new("RGB", (CARD_WIDTH, 200), COLORS["bg"])
    measure = ImageDraw.Draw(tmp)
    height = _estimate_height(measure, item)

    card = Image.new("RGB", (CARD_WIDTH, height), COLORS["bg"])
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (8, 8, CARD_WIDTH - 8, height - 8),
        radius=14,
        fill=COLORS["panel"],
        outline=COLORS["border"],
        width=1,
    )

    title_font = _font(22, bold=True)
    draw.text(
        (CARD_PADDING + 8, CARD_PADDING),
        item.name,
        fill=COLORS["title"],
        font=title_font,
    )
    id_text = f"ID: {item.id}"
    id_font = _font(12)
    id_w = _text_width(draw, id_text, id_font)
    draw.text(
        (CARD_WIDTH - CARD_PADDING - 8 - id_w, CARD_PADDING + 8),
        id_text,
        fill=COLORS["muted"],
        font=id_font,
    )

    y = CARD_PADDING + TITLE_HEIGHT

    if _section_has_content(item, "wear_limit"):
        y = _draw_header(draw, y, "▎佩戴限定")
        wear_lines = [f"· {label}" for label in item.wear_limit]
        y = _draw_bullet_lines(draw, y, wear_lines, _font(15))
        for ex in item.exclusives:
            header = f"· {ex.hero_name}"
            if ex.skill:
                header += f" · {ex.skill}"
            draw.text(
                (CARD_PADDING + 16, y),
                header,
                fill=COLORS["accent"],
                font=_font(15, bold=True),
            )
            y += ROW_HEIGHT
            if ex.description:
                y = _draw_bullet_lines(
                    draw,
                    y,
                    [ex.description],
                    _font(14),
                    indent=28,
                    color=COLORS["muted"],
                )
        y += SECTION_GAP

    if _section_has_content(item, "stats"):
        y = _draw_header(draw, y, "▎属性")
        content_width = CARD_WIDTH - CARD_PADDING * 2 - 20
        for line in _wrap_lines(draw, item.description, _font(15), content_width):
            draw.text((CARD_PADDING + 16, y), line, fill=COLORS["text"], font=_font(15))
            y += 20
        y += SECTION_GAP

    if _section_has_content(item, "recipe"):
        y = _draw_header(draw, y, "▎合成方式")
        rows = [(f"· {entry.name}", f"x{entry.quantity}") for entry in item.recipe]
        y = _draw_list_rows(draw, y, rows)
        y += SECTION_GAP

    if _section_has_content(item, "crafts_into"):
        y = _draw_header(draw, y, "▎可合成物品")
        rows = [(f"· {entry.name}", f"x{entry.quantity}") for entry in item.crafts_into]
        y = _draw_list_rows(draw, y, rows)
        y += SECTION_GAP

    if _section_has_content(item, "boss_drops"):
        y = _draw_header(draw, y, "▎来源")
        rows = [
            (f"· {entry.boss_name}", _format_chance(entry.chance))
            for entry in item.boss_drops
        ]
        y = _draw_list_rows(draw, y, rows)

    out_path = os.path.join(_CARDS_DIR, f"{item.id}_{uuid.uuid4().hex[:8]}.png")
    card.save(out_path, format="PNG", optimize=True)
    return out_path


def format_text_fallback(item: ItemDisplay) -> str:
    lines = [item.name, ""]

    if _section_has_content(item, "wear_limit"):
        lines.append("【佩戴限定】")
        for label in item.wear_limit:
            lines.append(f"· {label}")
        for ex in item.exclusives:
            header = ex.hero_name
            if ex.skill:
                header += f" · {ex.skill}"
            lines.append(f"· {header}")
            if ex.description:
                lines.append(f"  {ex.description}")
        lines.append("")

    if _section_has_content(item, "stats"):
        lines.append("【属性】")
        lines.append(item.description)
        lines.append("")

    if _section_has_content(item, "recipe"):
        lines.append("【合成方式】")
        for entry in item.recipe:
            lines.append(f"· {entry.name} x{entry.quantity}")
        lines.append("")

    if _section_has_content(item, "crafts_into"):
        lines.append("【可合成物品】")
        for entry in item.crafts_into:
            lines.append(f"· {entry.name} x{entry.quantity}")
        lines.append("")

    if _section_has_content(item, "boss_drops"):
        lines.append("【来源】")
        for entry in item.boss_drops:
            lines.append(f"· {entry.boss_name} ({_format_chance(entry.chance)})")

    return "\n".join(lines).strip()
