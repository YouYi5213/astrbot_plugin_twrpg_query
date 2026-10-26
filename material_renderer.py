"""目标材料缺料统计卡片渲染。"""

from __future__ import annotations

import uuid

from PIL import Image, ImageDraw

from . import card_renderer as cr
from .card_renderer import (
    CARD_BOTTOM_EXTRA,
    CARD_PADDING,
    CARD_WIDTH,
    COLORS,
    HEADER_HEIGHT,
    LIST_ICON_GAP,
    LIST_ICON_SIZE,
    ROW_HEIGHT,
    SUBSECTION_HEIGHT,
    TITLE_HEIGHT,
    TITLE_ICON_SIZE,
    _draw_header,
    _font,
    _format_chance,
    _load_image,
    _paste_in_slot,
    _text_width,
    save_card_png,
)
from .material_planner import MaterialNeed, MaterialPlan

MAX_MISSING_ROWS = 22
SUMMARY_HEIGHT = 26
NOTE_HEIGHT = 24


def _missing_rows(plan: MaterialPlan) -> list[MaterialNeed]:
    return plan.missing


def _hidden_missing_count(plan: MaterialPlan) -> int:
    return max(0, len(_missing_rows(plan)) - MAX_MISSING_ROWS)


def _estimate_height(plan: MaterialPlan) -> int:
    y = CARD_PADDING + TITLE_HEIGHT
    y += HEADER_HEIGHT + SUMMARY_HEIGHT
    if plan.missing:
        y += min(len(plan.missing), MAX_MISSING_ROWS) * ROW_HEIGHT
        if _hidden_missing_count(plan):
            y += NOTE_HEIGHT
    else:
        y += NOTE_HEIGHT
    if plan.satisfied:
        y += NOTE_HEIGHT
    if plan.truncated:
        y += NOTE_HEIGHT
    sources = plan.source_materials
    if sources:
        y += HEADER_HEIGHT
        for need in sources:
            y += SUBSECTION_HEIGHT + len(need.drops) * ROW_HEIGHT
    if plan.optional_groups:
        y += HEADER_HEIGHT + len(plan.optional_groups) * ROW_HEIGHT
    return y + CARD_PADDING + CARD_BOTTOM_EXTRA


def _draw_title(card: Image.Image, draw: ImageDraw.ImageDraw, plan: MaterialPlan) -> int:
    title_font = _font(22, bold=True)
    title_x = CARD_PADDING + 8
    if plan.target_icon:
        icon = _load_image(plan.target_icon, TITLE_ICON_SIZE)
        _paste_in_slot(
            card,
            icon,
            CARD_PADDING + 8,
            CARD_PADDING,
            TITLE_ICON_SIZE[0],
            TITLE_ICON_SIZE[1],
        )
        title_x = CARD_PADDING + 8 + TITLE_ICON_SIZE[0] + 10

    title_y = CARD_PADDING + 10
    draw.text(
        (title_x, title_y),
        plan.target_name,
        fill=COLORS["title"],
        font=title_font,
    )
    tail_x = title_x + _text_width(draw, plan.target_name, title_font) + 8
    stage_text = plan.target_stage_label
    if stage_text:
        draw.text((tail_x, title_y), stage_text, fill=COLORS["stage"], font=title_font)
        tail_x += _text_width(draw, stage_text, title_font) + 8
    if plan.quantity > 1:
        qty_text = f"×{plan.quantity}"
        draw.text((tail_x, title_y), qty_text, fill=COLORS["accent"], font=title_font)

    hint_font = _font(12)
    hint = "材料统计"
    hint_w = _text_width(draw, hint, hint_font)
    draw.text(
        (CARD_WIDTH - CARD_PADDING - 8 - hint_w, CARD_PADDING + 8),
        hint,
        fill=COLORS["muted"],
        font=hint_font,
    )
    return CARD_PADDING + TITLE_HEIGHT


def _draw_summary(
    draw: ImageDraw.ImageDraw, y: int, plan: MaterialPlan
) -> int:
    font = _font(13)
    text = (
        f"需 {len(plan.needs)} 种材料 · 缺 {len(plan.missing)} 种 · "
        f"已满足 {len(plan.satisfied)} 种"
    )
    draw.text((CARD_PADDING + 8, y + 4), text, fill=COLORS["muted"], font=font)
    return y + SUMMARY_HEIGHT


def _draw_missing_rows(
    card: Image.Image, draw: ImageDraw.ImageDraw, y: int, plan: MaterialPlan
) -> int:
    font = _font(15)
    note_font = _font(13)
    icon_x = CARD_PADDING + 16
    text_x = icon_x + LIST_ICON_SIZE[0] + LIST_ICON_GAP
    right = CARD_WIDTH - CARD_PADDING - 16

    if not plan.missing:
        draw.text(
            (CARD_PADDING + 16, y + 2),
            "✅ 材料已经齐了，可以直接合成",
            fill=COLORS["header"],
            font=note_font,
        )
        return y + NOTE_HEIGHT

    for need in plan.missing[:MAX_MISSING_ROWS]:
        icon = _load_image(need.icon, LIST_ICON_SIZE)
        _paste_in_slot(card, icon, icon_x, y, LIST_ICON_SIZE[0], ROW_HEIGHT)
        draw.text((text_x, y + 6), need.name, fill=COLORS["text"], font=font)
        detail = f"缺 x{need.missing}"
        if need.owned:
            detail += f" · 需 x{need.required} · 有 x{need.owned}"
        detail_w = _text_width(draw, detail, font)
        draw.text(
            (right - detail_w, y + 6),
            detail,
            fill=COLORS["stage"] if not need.owned else COLORS["accent"],
            font=font,
        )
        y += ROW_HEIGHT

    hidden = _hidden_missing_count(plan)
    if hidden:
        draw.text(
            (CARD_PADDING + 16, y + 2),
            f"… 还有 {hidden} 种缺口材料未列出",
            fill=COLORS["muted"],
            font=note_font,
        )
        y += NOTE_HEIGHT
    return y


def _draw_notes(draw: ImageDraw.ImageDraw, y: int, plan: MaterialPlan) -> int:
    font = _font(13)
    if plan.satisfied:
        draw.text(
            (CARD_PADDING + 16, y + 2),
            f"· 另有 {len(plan.satisfied)} 种材料库存已够",
            fill=COLORS["muted"],
            font=font,
        )
        y += NOTE_HEIGHT
    if plan.truncated:
        draw.text(
            (CARD_PADDING + 16, y + 2),
            "· 配方层数过深，缺口只统计到前 8 层",
            fill=COLORS["muted"],
            font=font,
        )
        y += NOTE_HEIGHT
    return y


def _draw_sources(
    card: Image.Image, draw: ImageDraw.ImageDraw, y: int, plan: MaterialPlan
) -> int:
    font = _font(15)
    note_font = _font(13)
    icon_x = CARD_PADDING + 16
    text_x = icon_x + LIST_ICON_SIZE[0] + LIST_ICON_GAP
    right = CARD_WIDTH - CARD_PADDING - 16

    y = _draw_header(draw, y, "▎掉落来源")
    for need in plan.source_materials:
        icon = _load_image(need.icon, LIST_ICON_SIZE)
        _paste_in_slot(card, icon, icon_x, y, LIST_ICON_SIZE[0], SUBSECTION_HEIGHT)
        label = f"{need.name} · 缺 x{need.missing}"
        draw.text((text_x, y + 5), label, fill=COLORS["header"], font=note_font)
        y += SUBSECTION_HEIGHT
        for drop in need.drops:
            boss_icon = _load_image(drop.icon, LIST_ICON_SIZE)
            _paste_in_slot(card, boss_icon, icon_x, y, LIST_ICON_SIZE[0], ROW_HEIGHT)
            name = drop.boss_name
            stage_text = drop.stage_label
            draw.text((text_x, y + 6), name, fill=COLORS["text"], font=font)
            cursor_x = text_x + _text_width(draw, name, font) + 6
            if drop.source_name and drop.source_name != need.name:
                source_text = f"· {drop.source_name}"
                draw.text(
                    (cursor_x, y + 6), source_text, fill=COLORS["muted"], font=note_font
                )
                cursor_x += _text_width(draw, source_text, note_font) + 6
            if stage_text:
                draw.text(
                    (cursor_x, y + 6),
                    stage_text,
                    fill=COLORS["muted"],
                    font=note_font,
                )
            chance_text = _format_chance(drop.chance)
            chance_w = _text_width(draw, chance_text, font)
            draw.text(
                (right - chance_w, y + 6),
                chance_text,
                fill=COLORS["muted"],
                font=font,
            )
            y += ROW_HEIGHT
    return y


def _draw_optional(
    card: Image.Image, draw: ImageDraw.ImageDraw, y: int, plan: MaterialPlan
) -> int:
    font = _font(15)
    note_font = _font(13)
    icon_x = CARD_PADDING + 16
    text_x = icon_x + LIST_ICON_SIZE[0] + LIST_ICON_GAP

    y = _draw_header(draw, y, "▎可选材料（任选其一）")
    for group in plan.optional_groups:
        icon_path = group.choices[0].icon if group.choices else None
        icon = _load_image(icon_path, LIST_ICON_SIZE)
        _paste_in_slot(card, icon, icon_x, y, LIST_ICON_SIZE[0], ROW_HEIGHT)
        draw.text((text_x, y + 6), group.label, fill=COLORS["text"], font=font)
        y += ROW_HEIGHT
    return y


def generate_material_card(plan: MaterialPlan) -> str:
    """渲染材料缺口卡片，返回图片路径。"""
    cr._ensure_dirs()
    height = _estimate_height(plan)

    card = Image.new("RGB", (CARD_WIDTH, height), COLORS["bg"])
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (8, 8, CARD_WIDTH - 8, height - 8),
        radius=14,
        fill=COLORS["panel"],
        outline=COLORS["border"],
        width=1,
    )

    y = _draw_title(card, draw, plan)
    y = _draw_header(draw, y, "▎缺料汇总")
    y = _draw_summary(draw, y, plan)
    y = _draw_missing_rows(card, draw, y, plan)
    y = _draw_notes(draw, y, plan)
    if plan.source_materials:
        y = _draw_sources(card, draw, y, plan)
    if plan.optional_groups:
        y = _draw_optional(card, draw, y, plan)

    return save_card_png(card, f"material_{plan.target_id}_{uuid.uuid4().hex[:8]}.png")


def format_material_caption(plan: MaterialPlan, *, save_name: str = "") -> str:
    """与图片一起发送的文字摘要。"""
    title = plan.target_name
    stage_text = plan.target_stage_label
    if stage_text:
        title = f"{title} {stage_text}"
    if plan.quantity > 1:
        title = f"{title} ×{plan.quantity}"

    lines = [f"【材料统计】{title}"]
    missing = plan.missing
    if missing:
        parts = [f"{need.name} x{need.missing}" for need in missing[:6]]
        suffix = f" 等 {len(missing)} 种" if len(missing) > 6 else ""
        lines.append("缺口：" + " · ".join(parts) + suffix)
    else:
        lines.append("材料已经齐了，可以直接合成。")
    if save_name:
        lines.append(f"库存对比：{save_name}")
    else:
        lines.append("⚠ 未读取到存档库存，仅按配方展开缺口。")
    return "\n".join(lines)


def format_material_text(plan: MaterialPlan, *, save_name: str = "") -> str:
    """纯文本兜底（出图失败时使用）。"""
    lines = [format_material_caption(plan, save_name=save_name), ""]
    if plan.missing:
        lines.append("【缺口材料】")
        for need in plan.missing[:MAX_MISSING_ROWS]:
            detail = f"· {need.name} x{need.missing}"
            if need.owned:
                detail += f"（需 x{need.required}，库存 x{need.owned}）"
            lines.append(detail)
        lines.append("")
    if plan.source_materials:
        lines.append("【掉落来源】")
        for need in plan.source_materials:
            sources = "，".join(
                f"{drop.boss_name}{drop.stage_label} {_format_chance(drop.chance)}"
                for drop in need.drops
            )
            lines.append(f"· {need.name}：{sources}")
        lines.append("")
    if plan.optional_groups:
        lines.append("【可选材料】")
        for group in plan.optional_groups:
            lines.append(f"· {group.parent_name}：{group.label}")
    return "\n".join(lines).strip()
