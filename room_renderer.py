"""魔兽房间列表卡片渲染（深色表格，风格贴近 KK 平台房间列表）。"""

from __future__ import annotations

import io
import os
import time
import uuid

import httpx
from PIL import Image, ImageDraw, ImageOps

from .card_renderer import _font, _text_width, get_cards_dir, save_card_png
from .core.room_query import (
    Room,
    RoomSnapshot,
    attr_label,
    split_visible,
)

CARD_W = 760
PAD = 22
TITLE_H = 96
HEADER_H = 34
ROW_H = 36
MAX_ROWS = 30
LOGO_SIZE = 52
LOGO_GAP = 12

BG = (26, 26, 29)
ROW_EVEN = (31, 31, 34)
ROW_ODD = (37, 37, 41)
LINE = (48, 48, 53)
HEADER_TEXT = (150, 150, 158)
TEXT = (216, 216, 223)
MUTED = (140, 140, 148)
RED = (255, 92, 92)
YELLOW = (245, 190, 70)
ATTR_COLORS = {
    "-": (200, 200, 205),
    "观战": (120, 190, 255),
    "游戏中": (240, 180, 100),
}

# (表头, x, 可用宽度)
COLUMNS = (
    ("房间号", 22, 98),
    ("房间名称", 130, 236),
    ("模式", 380, 70),
    ("地图等级", 465, 90),
    ("房间人数", 570, 90),
    ("房间属性", 675, 63),
)


def _fit(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    text = text or ""
    if _text_width(draw, text, font) <= max_width:
        return text
    while text and _text_width(draw, text + "…", font) > max_width:
        text = text[:-1]
    return text + "…"


def _draw_lock(draw: ImageDraw.ImageDraw, x: int, cy: int) -> None:
    top = cy - 7
    color = (178, 178, 186)
    draw.arc([x + 1, top, x + 9, top + 9], 180, 360, fill=color, width=2)
    draw.rounded_rectangle([x, top + 5, x + 10, top + 14], radius=2, fill=color)


def _draw_vip(draw: ImageDraw.ImageDraw, x: int, cy: int) -> None:
    top = cy - 7
    draw.rounded_rectangle([x, top, x + 14, top + 14], radius=3, fill=YELLOW)
    draw.text((x + 7, cy), "V", font=_font(10), fill=(35, 28, 0), anchor="mm")


def _load_map_logo(url: str, map_id: int) -> Image.Image | None:
    """
    地图图标只在有人主动查询这张地图时才下载，并缓存在卡片目录的
    map_logos/ 下；地图目录构建时不会碰图片。
    """
    if not url:
        return None
    cache_dir = os.path.join(get_cards_dir(), "map_logos")
    path = os.path.join(cache_dir, f"{map_id}.png")
    try:
        if os.path.exists(path):
            with Image.open(path) as cached:
                return cached.convert("RGBA")
    except Exception:
        pass

    try:
        resp = httpx.get(url, timeout=10, trust_env=False,
                         headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        with Image.open(io.BytesIO(resp.content)) as img:
            logo = img.convert("RGBA")
    except Exception:
        return None

    try:
        os.makedirs(cache_dir, exist_ok=True)
        logo.save(path, "PNG")
    except Exception:
        pass
    return logo


def _rounded(img: Image.Image, size: tuple[int, int],
             radius: int = 10) -> Image.Image:
    fitted = ImageOps.fit(img, size, Image.LANCZOS)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(fitted, (0, 0), mask)
    return out


def _draw_title(
    draw: ImageDraw.ImageDraw,
    snap: RoomSnapshot,
    joinable: list[Room],
    playing: list[Room],
    watching: list[Room],
    include_playing: bool,
    include_watching: bool,
    text_x: int,
) -> None:
    title = f"{snap.map_name} · 可加入 {len(joinable)} 间"
    if include_playing:
        title += f" · 游戏中 {len(playing)} 间"
    if include_watching:
        title += f" · 观战 {len(watching)} 间"
    title_font = _font(22)
    draw.text((text_x, 12), title, font=title_font, fill=(242, 242, 247))

    # 地图标签（组队合作 / 冒险 …），做成小圆角标签，风格贴近平台
    chip_font = _font(12)
    x = text_x + _text_width(draw, title, title_font) + 10
    limit_x = CARD_W - PAD - 190
    for tag in snap.tags[:3]:
        width = _text_width(draw, tag, chip_font) + 14
        if x + width > limit_x:
            break
        draw.rounded_rectangle([x, 16, x + width, 36], radius=4,
                               fill=(52, 52, 58))
        draw.text((x + 7, 26), tag, font=chip_font,
                  fill=(192, 192, 200), anchor="lm")
        x += width + 6

    meta = [part for part in (
        snap.engine,
        snap.map_type,
        f"V{snap.map_version}" if snap.map_version else "",
    ) if part]
    if meta:
        draw.text((text_x, 44), " · ".join(meta), font=_font(14),
                  fill=MUTED)

    stamp = time.strftime("%H:%M", time.localtime(snap.now or time.time()))
    draw.text((text_x, 68),
              f"数据时刻 {stamp} · 在线共 {snap.total} 间",
              font=_font(14), fill=MUTED)

    stats = []
    if snap.hot:
        stats.append(f"热度 {snap.hot}")
    if snap.score is not None:
        stats.append(f"{snap.score:g} 分")
    if stats:
        draw.text((CARD_W - PAD, 24), " ｜ ".join(stats),
                  font=_font(18), fill=(245, 170, 70), anchor="rm")
    if snap.score_count:
        draw.text((CARD_W - PAD, 50), f"{snap.score_count} 人评分",
                  font=_font(13), fill=MUTED, anchor="rm")


def _draw_header(draw: ImageDraw.ImageDraw, y: int) -> None:
    font = _font(14)
    for label, x, _ in COLUMNS:
        draw.text((x, y + HEADER_H // 2), label, font=font,
                  fill=HEADER_TEXT, anchor="lm")
    draw.line([(0, y + HEADER_H), (CARD_W, y + HEADER_H)], fill=LINE)


def _draw_row(draw: ImageDraw.ImageDraw, room: Room, y: int,
              index: int) -> None:
    draw.rectangle([0, y, CARD_W, y + ROW_H],
                   fill=ROW_ODD if index % 2 else ROW_EVEN)
    cy = y + ROW_H // 2
    font = _font(16)

    draw.text((COLUMNS[0][1], cy), room.no, font=font,
              fill=(236, 236, 242), anchor="lm")

    name_x, name_w = COLUMNS[1][1], COLUMNS[1][2]
    name = _fit(draw, room.name, font, name_w - 22)
    draw.text((name_x, cy), name, font=font,
              fill=RED if room.vip else TEXT, anchor="lm")
    cursor = name_x + _text_width(draw, name, font) + 6
    if room.need_password:
        _draw_lock(draw, cursor, cy)
        cursor += 16
    if room.vip:
        _draw_vip(draw, cursor, cy)

    draw.text((COLUMNS[2][1], cy),
              _fit(draw, room.mode, font, COLUMNS[2][2]),
              font=font, fill=MUTED, anchor="lm")
    draw.text((COLUMNS[3][1], cy), room.level, font=font,
              fill=TEXT, anchor="lm")
    draw.text((COLUMNS[4][1], cy), f"{room.players}/{room.slots}",
              font=font, fill=TEXT, anchor="lm")
    draw.text((COLUMNS[5][1], cy), attr_label(room.attr), font=font,
              fill=ATTR_COLORS.get(room.attr, TEXT), anchor="lm")

    draw.line([(0, y + ROW_H), (CARD_W, y + ROW_H)], fill=LINE)


def render_room_card(snap: RoomSnapshot,
                     include_playing: bool = False,
                     include_watching: bool = False) -> str:
    """把房间快照画成一张深色表格卡片，返回图片路径。"""
    shown, joinable, playing, watching = split_visible(
        snap, include_playing, include_watching)
    rows = shown[:MAX_ROWS]
    empty = not rows
    body_h = 84 if empty else ROW_H * len(rows)
    height = TITLE_H + HEADER_H + body_h + 18 + 34 + PAD

    card = Image.new("RGB", (CARD_W, height), BG)
    draw = ImageDraw.Draw(card)

    text_x = PAD
    logo = _load_map_logo(snap.logo, snap.map_id)
    if logo is not None:
        rounded = _rounded(logo, (LOGO_SIZE, LOGO_SIZE))
        card.paste(rounded, (PAD, 14), rounded)
        text_x = PAD + LOGO_SIZE + LOGO_GAP

    _draw_title(draw, snap, joinable, playing, watching,
                include_playing, include_watching, text_x)
    y = TITLE_H
    _draw_header(draw, y)
    y += HEADER_H

    if empty:
        message = ("当前没有可直接加入的房间"
                   if snap.rooms else "当前地图没有在线房间")
        draw.text((CARD_W // 2, y + 30), message, font=_font(17),
                  fill=TEXT, anchor="mm")
        if snap.rooms:
            draw.text(
                (CARD_W // 2, y + 58),
                f"观战 {len(watching)} 间 · 游戏中 {len(playing)} 间",
                font=_font(14), fill=MUTED, anchor="mm",
            )
        y += 84
    else:
        for index, room in enumerate(rows):
            _draw_row(draw, room, y, index)
            y += ROW_H

    footer_y = y + 18 + 7
    if include_watching:
        left = f"观战 {len(watching)} 间已显示"
    else:
        left = f"观战 {len(watching)} 间已隐藏"
    if len(shown) > MAX_ROWS:
        left += f" · 还有 {len(shown) - MAX_ROWS} 间"
    draw.text((PAD, footer_y), left, font=_font(14),
              fill=MUTED, anchor="lm")

    stamp = time.strftime("%H:%M", time.localtime(snap.now or time.time()))
    draw.text((CARD_W - PAD, footer_y), f"数据时刻 {stamp}",
              font=_font(14), fill=MUTED, anchor="rm")

    return save_card_png(card, f"room_{uuid.uuid4().hex}.png")
