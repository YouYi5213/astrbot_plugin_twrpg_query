"""TWRPG 物品查询卡片图片渲染。"""

from __future__ import annotations

import os
import uuid
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from .data_loader import HeroDisplay, ItemDisplay, RecipeLine, SkillDisplay, strip_color
from .desc_renderer import draw_game_panel, measure_game_panel, resolve_items_bg_path

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.join(_PLUGIN_DIR, "assets", "fonts")
_CARDS_DIR = os.path.join(_PLUGIN_DIR, "data", "cards")
_BUNDLED_FONT = os.path.join(_FONT_DIR, "NotoSansSC-Bold.otf")
_ITEMS_BG = resolve_items_bg_path(_PLUGIN_DIR)

CARD_WIDTH = 640
CARD_PADDING = 22
SECTION_GAP = 14
LINE_GAP = 4
ROW_HEIGHT = 32
HEADER_HEIGHT = 34
TITLE_ICON_SIZE = (52, 52)
LIST_ICON_SIZE = (28, 28)
HERO_ICON_SIZE = (32, 32)
LIST_ICON_GAP = 8
TITLE_HEIGHT = 52
RECIPE_GROUP_GAP = 8
RECIPE_CHOICE_ROW_HEIGHT = 28
SKILL_ICON_SIZE = (40, 40)
SKILL_BLOCK_GAP = 10
CARD_BOTTOM_EXTRA = 16
OPTIONAL_LABEL = "[可选]"

COLORS = {
    "bg": (24, 26, 34),
    "panel": (34, 37, 48),
    "border": (88, 96, 120),
    "title": (255, 214, 120),
    "header": (120, 190, 255),
    "text": (230, 232, 240),
    "muted": (160, 166, 182),
    "accent": (255, 180, 96),
    "stage": (244, 88, 88),
    "line": (58, 62, 78),
}

_FONT_CACHE: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_RESOLVED_FONT: str | None = None


def _ensure_dirs() -> None:
    os.makedirs(_CARDS_DIR, exist_ok=True)


def _resolve_font_path() -> str | None:
    global _RESOLVED_FONT
    if _RESOLVED_FONT is not None:
        return _RESOLVED_FONT or None

    candidates = [
        _BUNDLED_FONT,
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
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
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]

    path = _resolve_font_path()
    if path:
        try:
            font = ImageFont.truetype(path, size)
            _FONT_CACHE[size] = font
            return font
        except OSError:
            pass

    font = ImageFont.load_default()
    _FONT_CACHE[size] = font
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


def _fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    w, h = img.size
    if w <= 0 or h <= 0:
        return img
    scale = min(max_w / w, max_h / h)
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    if (new_w, new_h) == (w, h):
        return img
    resample = Image.NEAREST if scale > 1 else Image.LANCZOS
    return img.resize((new_w, new_h), resample)


def _load_image(path: str | None, size: tuple[int, int] | None = None) -> Image.Image | None:
    if not path or not os.path.exists(path):
        return None
    try:
        img = Image.open(path).convert("RGBA")
        if size:
            img = _fit_image(img, size[0], size[1])
        return img
    except OSError:
        return None


def _paste_in_slot(
    card: Image.Image,
    img: Image.Image | None,
    x: int,
    y: int,
    slot_w: int,
    slot_h: int,
) -> None:
    if not img:
        return
    ox = x + max(0, (slot_w - img.width) // 2)
    oy = y + max(0, (slot_h - img.height) // 2)
    card.paste(img, (ox, oy), img)


def _format_chance(chance: float) -> str:
    if chance >= 10:
        return f"{chance:g}%"
    if chance >= 1:
        text = f"{chance:.1f}".rstrip("0").rstrip(".")
        return f"{text}%"
    return f"{chance:.2g}%"


def _section_has_content(item: ItemDisplay, section: str) -> bool:
    if section == "wear_limit":
        return bool(item.limit_heroes)
    if section == "exclusive":
        return bool(item.exclusives)
    if section == "stats":
        return bool(item.raw_description or item.description or item.passive)
    if section == "recipe":
        return bool(item.recipe)
    if section == "crafts_into":
        return bool(item.crafts_into)
    if section == "boss_drops":
        return bool(item.boss_drops)
    return False


def _hero_icon_grid_height(hero_count: int) -> int:
    if hero_count <= 0:
        return 0
    usable = CARD_WIDTH - CARD_PADDING * 2 - 24
    per_row = max(1, usable // (HERO_ICON_SIZE[0] + 6))
    rows = (hero_count + per_row - 1) // per_row
    return rows * HERO_ICON_SIZE[1] + max(0, rows - 1) * 6 + 4


def _exclusive_block_height(
    draw: ImageDraw.ImageDraw,
    exclusives,
    font,
) -> int:
    text_x = CARD_PADDING + 16 + HERO_ICON_SIZE[0] + LIST_ICON_GAP
    max_width = CARD_WIDTH - CARD_PADDING - text_x - 8
    total = 0
    for ex in exclusives:
        lines = [ln.strip() for ln in ex.description.split("\n") if ln.strip()]
        if not lines:
            lines = [""]
        line_count = 0
        for line in lines:
            wrapped = _wrap_lines(draw, line, font, max_width) or [""]
            line_count += len(wrapped)
        block_h = max(HERO_ICON_SIZE[1], line_count * 18 + 4)
        total += block_h + 6
    return total


def _draw_hero_icon_grid(
    card: Image.Image,
    y: int,
    heroes,
) -> int:
    x_start = CARD_PADDING + 16
    x = x_start
    row_y = y
    max_x = CARD_WIDTH - CARD_PADDING - 8
    gap = 6
    for hero in heroes:
        if not hero.icon:
            continue
        if x + HERO_ICON_SIZE[0] > max_x and x > x_start:
            row_y += HERO_ICON_SIZE[1] + gap
            x = x_start
        icon = _load_image(hero.icon, HERO_ICON_SIZE)
        _paste_in_slot(card, icon, x, row_y, HERO_ICON_SIZE[0], HERO_ICON_SIZE[1])
        x += HERO_ICON_SIZE[0] + gap
    return row_y + HERO_ICON_SIZE[1] + 4


def _draw_exclusive_rows(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    exclusives,
) -> int:
    font = _font(14)
    icon_x = CARD_PADDING + 16
    text_x = icon_x + HERO_ICON_SIZE[0] + LIST_ICON_GAP
    max_width = CARD_WIDTH - CARD_PADDING - text_x - 8

    for ex in exclusives:
        lines = [ln.strip() for ln in ex.description.split("\n") if ln.strip()]
        if not lines:
            continue

        wrapped_lines: list[str] = []
        for line in lines:
            wrapped_lines.extend(_wrap_lines(draw, line, font, max_width) or [line])

        block_h = max(HERO_ICON_SIZE[1], len(wrapped_lines) * 18 + 4)
        icon = _load_image(ex.icon, HERO_ICON_SIZE)
        _paste_in_slot(card, icon, icon_x, y, HERO_ICON_SIZE[0], block_h)

        text_y = y + 4
        for part in wrapped_lines:
            draw.text((text_x, text_y), part, fill=COLORS["text"], font=font)
            text_y += 18
        y += block_h + 6
    return y


def _estimate_height(draw: ImageDraw.ImageDraw, item: ItemDisplay) -> int:
    body_font = _font(15)
    small_font = _font(14)
    content_width = CARD_WIDTH - CARD_PADDING * 2 - 20
    y = CARD_PADDING + TITLE_HEIGHT + SECTION_GAP

    if _section_has_content(item, "wear_limit"):
        y += HEADER_HEIGHT
        y += _hero_icon_grid_height(len(item.limit_heroes))
        y += SECTION_GAP

    if _section_has_content(item, "exclusive"):
        y += HEADER_HEIGHT
        y += _exclusive_block_height(draw, item.exclusives, small_font)
        y += SECTION_GAP

    if _section_has_content(item, "stats"):
        y += HEADER_HEIGHT
        panel_width = content_width
        stats_text = item.raw_description or item.description
        panel_height, _ = measure_game_panel(draw, stats_text, body_font, panel_width)
        y += panel_height
        y += SECTION_GAP

    if _section_has_content(item, "recipe"):
        y += HEADER_HEIGHT
        y += _recipe_section_height(item.recipe)
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


def _recipe_line_height(line: RecipeLine) -> int:
    if line.is_choice:
        return len(line.entries) * RECIPE_CHOICE_ROW_HEIGHT
    return ROW_HEIGHT


def _recipe_section_height(recipe: list[RecipeLine]) -> int:
    if not recipe:
        return 0
    height = sum(_recipe_line_height(line) for line in recipe)
    height += RECIPE_GROUP_GAP * (len(recipe) - 1)
    return height


def _draw_icon_rows(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    rows: list[tuple[str | None, str, str | None]],
) -> int:
    font = _font(15)
    icon_x = CARD_PADDING + 16
    text_x = icon_x + LIST_ICON_SIZE[0] + LIST_ICON_GAP
    right = CARD_WIDTH - CARD_PADDING - 16
    for icon_path, left_text, right_text in rows:
        icon = _load_image(icon_path, LIST_ICON_SIZE)
        _paste_in_slot(card, icon, icon_x, y, LIST_ICON_SIZE[0], ROW_HEIGHT)
        draw.text((text_x, y + 6), left_text, fill=COLORS["text"], font=font)
        if right_text:
            rw = _text_width(draw, right_text, font)
            draw.text((right - rw, y + 6), right_text, fill=COLORS["muted"], font=font)
        y += ROW_HEIGHT
    return y


def _draw_recipe_lines(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    recipe: list[RecipeLine],
) -> int:
    font = _font(15)
    icon_x = CARD_PADDING + 16
    text_x = icon_x + LIST_ICON_SIZE[0] + LIST_ICON_GAP
    right = CARD_WIDTH - CARD_PADDING - 16

    for group_idx, line in enumerate(recipe):
        row_height = RECIPE_CHOICE_ROW_HEIGHT if line.is_choice else ROW_HEIGHT
        for entry in line.entries:
            icon = _load_image(entry.icon, LIST_ICON_SIZE)
            _paste_in_slot(card, icon, icon_x, y, LIST_ICON_SIZE[0], row_height)
            draw.text((text_x, y + 6), entry.name, fill=COLORS["text"], font=font)
            if line.is_choice:
                name_w = _text_width(draw, entry.name, font)
                opt_x = text_x + name_w + 4
                draw.text(
                    (opt_x, y + 6),
                    OPTIONAL_LABEL,
                    fill=COLORS["header"],
                    font=font,
                )
            qty = f"x{entry.quantity}"
            qty_w = _text_width(draw, qty, font)
            draw.text((right - qty_w, y + 6), qty, fill=COLORS["muted"], font=font)
            y += row_height
        if group_idx < len(recipe) - 1:
            y += RECIPE_GROUP_GAP
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
    title_x = CARD_PADDING + 8
    if item.icon:
        title_icon = _load_image(item.icon, TITLE_ICON_SIZE)
        _paste_in_slot(
            card,
            title_icon,
            CARD_PADDING + 8,
            CARD_PADDING,
            TITLE_ICON_SIZE[0],
            TITLE_ICON_SIZE[1],
        )
        title_x = CARD_PADDING + 8 + TITLE_ICON_SIZE[0] + 10
    title_y = CARD_PADDING + 10
    draw.text(
        (title_x, title_y),
        item.name,
        fill=COLORS["title"],
        font=title_font,
    )
    if item.stage_label:
        stage_x = title_x + _text_width(draw, item.name, title_font) + 8
        draw.text(
            (stage_x, title_y),
            item.stage_label,
            fill=COLORS["stage"],
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
        y = _draw_hero_icon_grid(card, y, item.limit_heroes)
        y += SECTION_GAP

    if _section_has_content(item, "exclusive"):
        y = _draw_header(draw, y, "▎专属效果")
        y = _draw_exclusive_rows(card, draw, y, item.exclusives)
        y += SECTION_GAP

    if _section_has_content(item, "stats"):
        y = _draw_header(draw, y, "▎属性")
        content_width = CARD_WIDTH - CARD_PADDING * 2 - 20
        stats_font = _font(15)
        stats_text = item.raw_description or item.description
        panel_height, wrapped = measure_game_panel(
            draw, stats_text, stats_font, content_width
        )
        draw_game_panel(
            card,
            draw,
            CARD_PADDING + 16,
            y,
            content_width,
            wrapped,
            stats_font,
            _ITEMS_BG,
        )
        y += panel_height
        y += SECTION_GAP

    if _section_has_content(item, "recipe"):
        y = _draw_header(draw, y, "▎合成方式")
        y = _draw_recipe_lines(card, draw, y, item.recipe)
        y += SECTION_GAP

    if _section_has_content(item, "crafts_into"):
        y = _draw_header(draw, y, "▎可合成物品")
        rows = [
            (entry.icon, entry.name, f"x{entry.quantity}") for entry in item.crafts_into
        ]
        y = _draw_icon_rows(card, draw, y, rows)
        y += SECTION_GAP

    if _section_has_content(item, "boss_drops"):
        y = _draw_header(draw, y, "▎来源")
        rows = [
            (entry.icon, entry.boss_name, _format_chance(entry.chance))
            for entry in item.boss_drops
        ]
        y = _draw_icon_rows(card, draw, y, rows)

    out_path = os.path.join(_CARDS_DIR, f"{item.id}_{uuid.uuid4().hex[:8]}.png")
    card.save(out_path, format="PNG", optimize=True)
    return out_path


def format_text_fallback(item: ItemDisplay) -> str:
    title = item.name
    if item.stage_label:
        title = f"{title} {item.stage_label}"
    lines = [title, ""]

    if _section_has_content(item, "wear_limit"):
        lines.append("【佩戴限定】")
        for hero in item.limit_heroes:
            lines.append(f"· {hero.name}")
        lines.append("")

    if _section_has_content(item, "exclusive"):
        lines.append("【专属效果】")
        for ex in item.exclusives:
            if ex.description:
                lines.append(ex.description)
        lines.append("")

    if _section_has_content(item, "stats"):
        lines.append("【属性】")
        lines.append(strip_color(item.raw_description or item.description))
        lines.append("")

    if _section_has_content(item, "recipe"):
        lines.append("【合成方式】")
        for line in item.recipe:
            for entry in line.entries:
                suffix = f" {OPTIONAL_LABEL}" if line.is_choice else ""
                lines.append(f"· {entry.name}{suffix} x{entry.quantity}")
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


def _skill_block_height(
    draw: ImageDraw.ImageDraw,
    skill,
    font,
    panel_width: int,
) -> int:
    text_x = CARD_PADDING + 16 + SKILL_ICON_SIZE[0] + LIST_ICON_GAP
    text_width = CARD_WIDTH - CARD_PADDING - text_x - 8
    title_h = 22 if skill.name else 0
    desc_text = skill.raw_description or skill.description
    panel_height, _ = measure_game_panel(
        draw,
        desc_text,
        font,
        min(panel_width, text_width),
    )
    return max(SKILL_ICON_SIZE[1], title_h + panel_height + 4)


def _draw_skill_block(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    skill,
    panel_width: int,
) -> int:
    font = _font(15)
    title_font = _font(15, bold=True)
    icon_x = CARD_PADDING + 16
    text_x = icon_x + SKILL_ICON_SIZE[0] + LIST_ICON_GAP
    text_width = CARD_WIDTH - CARD_PADDING - text_x - 8

    desc_text = skill.raw_description or skill.description
    panel_height, wrapped = measure_game_panel(
        draw,
        desc_text,
        font,
        min(panel_width, text_width),
    )
    title_h = 22 if skill.name else 0
    block_h = max(SKILL_ICON_SIZE[1], title_h + panel_height + 4)

    icon = _load_image(skill.icon, SKILL_ICON_SIZE)
    _paste_in_slot(card, icon, icon_x, y, SKILL_ICON_SIZE[0], block_h)

    text_y = y
    if skill.name:
        title = skill.name
        if skill.hotkey:
            title = f"{title} {skill.hotkey}"
        draw.text((text_x, text_y), title, fill=COLORS["accent"], font=title_font)
        text_y += title_h

    draw_game_panel(
        card,
        draw,
        text_x,
        text_y,
        min(panel_width, text_width),
        wrapped,
        font,
        _ITEMS_BG,
    )
    return y + block_h + SKILL_BLOCK_GAP


def _estimate_hero_height(draw: ImageDraw.ImageDraw, hero: HeroDisplay) -> int:
    body_font = _font(15)
    content_width = CARD_WIDTH - CARD_PADDING * 2 - 20
    y = CARD_PADDING + TITLE_HEIGHT

    if hero.skills:
        y += HEADER_HEIGHT
        for skill in hero.skills:
            y += _skill_block_height(draw, skill, body_font, content_width)
            y += SKILL_BLOCK_GAP
        y -= SKILL_BLOCK_GAP

    return y + CARD_PADDING + CARD_BOTTOM_EXTRA


def _estimate_skill_height(draw: ImageDraw.ImageDraw, skill: SkillDisplay) -> int:
    body_font = _font(15)
    content_width = CARD_WIDTH - CARD_PADDING * 2 - 20
    y = CARD_PADDING + TITLE_HEIGHT
    y += HEADER_HEIGHT
    y += _skill_block_height(draw, skill, body_font, content_width)
    return y + CARD_PADDING + CARD_BOTTOM_EXTRA


def generate_hero_card(hero: HeroDisplay) -> str:
    _ensure_dirs()
    tmp = Image.new("RGB", (CARD_WIDTH, 200), COLORS["bg"])
    measure = ImageDraw.Draw(tmp)
    height = _estimate_hero_height(measure, hero)

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
    subtitle_font = _font(15)
    title_x = CARD_PADDING + 8
    if hero.icon:
        title_icon = _load_image(hero.icon, TITLE_ICON_SIZE)
        _paste_in_slot(
            card,
            title_icon,
            CARD_PADDING + 8,
            CARD_PADDING,
            TITLE_ICON_SIZE[0],
            TITLE_ICON_SIZE[1],
        )
        title_x = CARD_PADDING + 8 + TITLE_ICON_SIZE[0] + 10

    title_y = CARD_PADDING + 8
    draw.text(
        (title_x, title_y),
        hero.name,
        fill=COLORS["title"],
        font=title_font,
    )
    if hero.character_name:
        sub_y = title_y + 28
        draw.text(
            (title_x, sub_y),
            hero.character_name,
            fill=COLORS["muted"],
            font=subtitle_font,
        )

    id_text = f"ID: {hero.id}"
    id_font = _font(12)
    id_w = _text_width(draw, id_text, id_font)
    draw.text(
        (CARD_WIDTH - CARD_PADDING - 8 - id_w, CARD_PADDING + 8),
        id_text,
        fill=COLORS["muted"],
        font=id_font,
    )

    y = CARD_PADDING + TITLE_HEIGHT
    content_width = CARD_WIDTH - CARD_PADDING * 2 - 20

    if hero.skills:
        y = _draw_header(draw, y, "▎技能")
        for skill in hero.skills:
            y = _draw_skill_block(card, draw, y, skill, content_width)

    out_path = os.path.join(_CARDS_DIR, f"hero_{hero.id}_{uuid.uuid4().hex[:8]}.png")
    card.save(out_path, format="PNG", optimize=True)
    return out_path


def generate_skill_card(skill: SkillDisplay) -> str:
    _ensure_dirs()
    tmp = Image.new("RGB", (CARD_WIDTH, 200), COLORS["bg"])
    measure = ImageDraw.Draw(tmp)
    height = _estimate_skill_height(measure, skill)

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
    subtitle_font = _font(15)
    title_x = CARD_PADDING + 8
    if skill.icon:
        title_icon = _load_image(skill.icon, TITLE_ICON_SIZE)
        _paste_in_slot(
            card,
            title_icon,
            CARD_PADDING + 8,
            CARD_PADDING,
            TITLE_ICON_SIZE[0],
            TITLE_ICON_SIZE[1],
        )
        title_x = CARD_PADDING + 8 + TITLE_ICON_SIZE[0] + 10

    title_y = CARD_PADDING + 8
    title = skill.name
    if skill.hotkey:
        title = f"{title} {skill.hotkey}"
    draw.text(
        (title_x, title_y),
        title,
        fill=COLORS["title"],
        font=title_font,
    )

    if skill.hero_name:
        hero_x = title_x
        hero_y = title_y + 28
        if skill.hero_icon:
            hero_icon = _load_image(skill.hero_icon, LIST_ICON_SIZE)
            _paste_in_slot(
                card,
                hero_icon,
                hero_x,
                hero_y - 2,
                LIST_ICON_SIZE[0],
                LIST_ICON_SIZE[1],
            )
            hero_x += LIST_ICON_SIZE[0] + 6
        draw.text(
            (hero_x, hero_y),
            skill.hero_name,
            fill=COLORS["muted"],
            font=subtitle_font,
        )

    id_text = f"ID: {skill.id}"
    id_font = _font(12)
    id_w = _text_width(draw, id_text, id_font)
    draw.text(
        (CARD_WIDTH - CARD_PADDING - 8 - id_w, CARD_PADDING + 8),
        id_text,
        fill=COLORS["muted"],
        font=id_font,
    )

    y = CARD_PADDING + TITLE_HEIGHT
    content_width = CARD_WIDTH - CARD_PADDING * 2 - 20
    y = _draw_header(draw, y, "▎描述")
    _draw_skill_block(card, draw, y, skill, content_width)

    out_path = os.path.join(_CARDS_DIR, f"skill_{skill.id}_{uuid.uuid4().hex[:8]}.png")
    card.save(out_path, format="PNG", optimize=True)
    return out_path


def format_hero_text_fallback(hero: HeroDisplay) -> str:
    lines = [hero.name]
    if hero.character_name:
        lines.append(hero.character_name)
    lines.append("")
    for skill in hero.skills:
        title = skill.name
        if skill.hotkey:
            title = f"{title} {skill.hotkey}"
        lines.append(f"【{title}】")
        lines.append(strip_color(skill.raw_description or skill.description))
        lines.append("")
    return "\n".join(lines).strip()


def format_skill_text_fallback(skill: SkillDisplay) -> str:
    title = skill.name
    if skill.hotkey:
        title = f"{title} {skill.hotkey}"
    lines = [title]
    if skill.hero_name:
        lines.append(f"英雄: {skill.hero_name}")
    lines.append("")
    lines.append(strip_color(skill.raw_description or skill.description))
    return "\n".join(lines).strip()
