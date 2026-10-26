"""云端物品目标的缺料汇总卡片渲染。"""

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
    _draw_header,
    _font,
    _format_chance,
    _load_image,
    _paste_in_slot,
    _text_width,
    save_card_png,
)
from .material_planner import GoalPlan, MaterialNeed, MaterialPlan

MAX_GOAL_ROWS = 12
MAX_MISSING_ROWS = 22
SUMMARY_HEIGHT = 26
NOTE_HEIGHT = 24


def _hidden_count(total: int, limit: int) -> int:
    return max(0, total - limit)


def _estimate_height(plan: GoalPlan) -> int:
    y = CARD_PADDING + TITLE_HEIGHT
    y += HEADER_HEIGHT + SUMMARY_HEIGHT
    y += min(len(plan.goals), MAX_GOAL_ROWS) * ROW_HEIGHT
    if _hidden_count(len(plan.goals), MAX_GOAL_ROWS):
        y += NOTE_HEIGHT
    y += HEADER_HEIGHT + SUMMARY_HEIGHT
    if plan.missing:
        y += min(len(plan.missing), MAX_MISSING_ROWS) * ROW_HEIGHT
        if _hidden_count(len(plan.missing), MAX_MISSING_ROWS):
            y += NOTE_HEIGHT
    else:
        y += NOTE_HEIGHT
    if plan.truncated:
        y += NOTE_HEIGHT
    sources = plan.source_materials
    if sources:
        y += HEADER_HEIGHT
        for need in sources:
            y += SUBSECTION_HEIGHT + len(need.drops) * ROW_HEIGHT
    return y + CARD_PADDING + CARD_BOTTOM_EXTRA


def _draw_summary(
    draw: ImageDraw.ImageDraw, y: int, text: str
) -> int:
    draw.text((CARD_PADDING + 8, y + 4), text, fill=COLORS["muted"], font=_font(13))
    return y + SUMMARY_HEIGHT


def _draw_title(card: Image.Image, draw: ImageDraw.ImageDraw, plan: GoalPlan) -> int:
    title_font = _font(22, bold=True)
    title_x = CARD_PADDING + 8
    label = plan.save_name or "云端目标"
    draw.text((title_x, CARD_PADDING + 12), label, fill=COLORS["title"], font=title_font)

    badge_font = _font(14)
    badge = f"{plan.count} 个目标"
    badge_w = _text_width(draw, badge, badge_font)
    draw.text(
        (CARD_WIDTH - CARD_PADDING - 16 - badge_w, CARD_PADDING + 18),
        badge,
        fill=COLORS["muted"],
        font=badge_font,
    )
    return CARD_PADDING + TITLE_HEIGHT


def _draw_goal_rows(
    card: Image.Image, draw: ImageDraw.ImageDraw, y: int, plan: GoalPlan
) -> int:
    font = _font(15)
    note_font = _font(13)
    icon_x = CARD_PADDING + 16
    text_x = icon_x + LIST_ICON_SIZE[0] + LIST_ICON_GAP
    right = CARD_WIDTH - CARD_PADDING - 16

    for goal in plan.goals[:MAX_GOAL_ROWS]:
        icon = _load_image(goal.target_icon, LIST_ICON_SIZE)
        _paste_in_slot(card, icon, icon_x, y, LIST_ICON_SIZE[0], ROW_HEIGHT)
        name = goal.target_name
        if goal.quantity > 1:
            name = f"{name} x{goal.quantity}"
        draw.text((text_x, y + 6), name, fill=COLORS["text"], font=font)
        stage_text = goal.target_stage_label
        if stage_text:
            name_w = _text_width(draw, name, font)
            draw.text(
                (text_x + name_w + 6, y + 7),
                stage_text,
                fill=COLORS["muted"],
                font=note_font,
            )
        if goal.missing:
            status = f"缺 {len(goal.missing)} 种"
            color = COLORS["accent"]
        else:
            status = "已齐"
            color = COLORS["stage"]
        status_w = _text_width(draw, status, font)
        draw.text((right - status_w, y + 6), status, fill=color, font=font)
        y += ROW_HEIGHT

    hidden = _hidden_count(len(plan.goals), MAX_GOAL_ROWS)
    if hidden:
        draw.text(
            (text_x, y + 4), f"... 还有 {hidden} 个目标未列出", fill=COLORS["muted"], font=note_font
        )
        y += NOTE_HEIGHT
    return y


def _draw_summary_rows(
    card: Image.Image, draw: ImageDraw.ImageDraw, y: int, plan: GoalPlan
) -> int:
    font = _font(15)
    note_font = _font(13)
    icon_x = CARD_PADDING + 16
    text_x = icon_x + LIST_ICON_SIZE[0] + LIST_ICON_GAP
    right = CARD_WIDTH - CARD_PADDING - 16

    if not plan.missing:
        draw.text(
            (text_x, y + 4),
            "全部目标材料已齐，可以直接合成。",
            fill=COLORS["stage"],
            font=font,
        )
        return y + NOTE_HEIGHT

    for need in plan.missing[:MAX_MISSING_ROWS]:
        icon = _load_image(need.icon, LIST_ICON_SIZE)
        _paste_in_slot(card, icon, icon_x, y, LIST_ICON_SIZE[0], ROW_HEIGHT)
        draw.text((text_x, y + 6), need.name, fill=COLORS["text"], font=font)
        right_text = f"缺 x{need.missing}"
        if need.owned:
            right_text += f" · 需 x{need.required} · 有 x{need.owned}"
        right_w = _text_width(draw, right_text, font)
        draw.text(
            (right - right_w, y + 6), right_text, fill=COLORS["accent"], font=font
        )
        y += ROW_HEIGHT

    hidden = _hidden_count(len(plan.missing), MAX_MISSING_ROWS)
    if hidden:
        draw.text(
            (text_x, y + 4),
            f"... 还有 {hidden} 种缺口材料未列出",
            fill=COLORS["muted"],
            font=note_font,
        )
        y += NOTE_HEIGHT
    return y


def _draw_sources(
    card: Image.Image, draw: ImageDraw.ImageDraw, y: int, plan: GoalPlan
) -> int:
    font = _font(15)
    note_font = _font(13)
    icon_x = CARD_PADDING + 16
    text_x = icon_x + LIST_ICON_SIZE[0] + LIST_ICON_GAP
    right = CARD_WIDTH - CARD_PADDING - 16

    for need in plan.source_materials:
        icon = _load_image(need.icon, LIST_ICON_SIZE)
        _paste_in_slot(card, icon, icon_x, y, LIST_ICON_SIZE[0], SUBSECTION_HEIGHT)
        draw.text(
            (text_x, y + 5),
            f"{need.name} · 缺 x{need.missing}",
            fill=COLORS["header"],
            font=note_font,
        )
        y += SUBSECTION_HEIGHT
        for drop in need.drops:
            boss_icon = _load_image(drop.icon, LIST_ICON_SIZE)
            _paste_in_slot(card, boss_icon, icon_x, y, LIST_ICON_SIZE[0], ROW_HEIGHT)
            draw.text((text_x, y + 6), drop.boss_name, fill=COLORS["text"], font=font)
            cursor_x = text_x + _text_width(draw, drop.boss_name, font) + 6
            if drop.source_name and drop.source_name != need.name:
                source_text = f"· {drop.source_name}"
                draw.text(
                    (cursor_x, y + 6), source_text, fill=COLORS["muted"], font=note_font
                )
                cursor_x += _text_width(draw, source_text, note_font) + 6
            if drop.stage_label:
                draw.text(
                    (cursor_x, y + 6),
                    drop.stage_label,
                    fill=COLORS["muted"],
                    font=note_font,
                )
            chance_text = _format_chance(drop.chance)
            chance_w = _text_width(draw, chance_text, font)
            draw.text(
                (right - chance_w, y + 6), chance_text, fill=COLORS["muted"], font=font
            )
            y += ROW_HEIGHT
    return y


def generate_goal_card(plan: GoalPlan) -> str:
    """渲染目标缺料汇总卡片，返回图片路径。"""
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
    y = _draw_header(draw, y, "▎目标清单")
    y = _draw_summary(
        draw,
        y,
        f"共 {plan.count} 个目标 · 缺料 {len(plan.missing_goals)} 个 · "
        f"已满足 {len(plan.satisfied_goals)} 个",
    )
    y = _draw_goal_rows(card, draw, y, plan)
    y = _draw_header(draw, y, "▎合并缺口")
    y = _draw_summary(
        draw,
        y,
        f"需 {len(plan.merged_needs)} 种材料 · 缺 {len(plan.missing)} 种 · "
        f"已满足 {len(plan.satisfied)} 种",
    )
    y = _draw_summary_rows(card, draw, y, plan)
    if plan.truncated:
        draw.text(
            (CARD_PADDING + 16, y + 4),
            "⚠ 部分配方层数过深，缺口可能偏少。",
            fill=COLORS["muted"],
            font=_font(13),
        )
        y += NOTE_HEIGHT
    if plan.source_materials:
        y = _draw_header(draw, y, "▎掉落来源")
        y = _draw_sources(card, draw, y, plan)

    return save_card_png(card, f"goals_{uuid.uuid4().hex[:8]}.png")


def format_goal_caption(plan: GoalPlan, *, save_name: str = "") -> str:
    """与图片一起发送的文字摘要。"""
    title = save_name or plan.save_name or "云端目标"
    lines = [f"【目标缺料】{title} · {plan.count} 个目标"]
    if plan.missing:
        parts = [f"{need.name} x{need.missing}" for need in plan.missing[:6]]
        suffix = f" 等 {len(plan.missing)} 种" if len(plan.missing) > 6 else ""
        lines.append("合并缺口：" + " · ".join(parts) + suffix)
        done = len(plan.satisfied_goals)
        if done:
            lines.append(f"已满足目标：{done} 个")
    else:
        lines.append("全部目标材料已齐，可以直接合成。")
    return "\n".join(lines)


def format_goal_text(plan: GoalPlan, *, save_name: str = "") -> str:
    """纯文本兜底（出图失败或目标很多时使用）。"""
    lines = [format_goal_caption(plan, save_name=save_name), ""]
    lines.append("【目标清单】")
    for goal in plan.goals[:MAX_GOAL_ROWS]:
        if goal.missing:
            detail = "缺 " + "、".join(
                f"{need.name} x{need.missing}" for need in goal.missing[:6]
            )
            if len(goal.missing) > 6:
                detail += f" 等 {len(goal.missing)} 种"
        else:
            detail = "已齐"
        quantity = f" x{goal.quantity}" if goal.quantity > 1 else ""
        lines.append(f"· {goal.target_name}{quantity}：{detail}")
    hidden = _hidden_count(len(plan.goals), MAX_GOAL_ROWS)
    if hidden:
        lines.append(f"... 还有 {hidden} 个目标未列出")
    if plan.missing:
        lines.append("")
        lines.append("【合并缺口】")
        for need in plan.missing[:MAX_MISSING_ROWS]:
            detail = f"· {need.name} x{need.missing}"
            if need.owned:
                detail += f"（需 x{need.required}，库存 x{need.owned}）"
            lines.append(detail)
    if plan.source_materials:
        lines.append("")
        lines.append("【掉落来源】")
        for need in plan.source_materials:
            sources = "，".join(
                f"{drop.boss_name}{drop.stage_label} {_format_chance(drop.chance)}"
                for drop in need.drops
            )
            lines.append(f"· {need.name}：{sources}")
    return "\n".join(lines)
