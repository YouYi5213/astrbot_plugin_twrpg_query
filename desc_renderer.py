"""GamePanel 风格属性框：War3 颜色码解析 + 金色嵌套边框。"""

from __future__ import annotations

import os
import re

from PIL import Image, ImageDraw, ImageFont

_WAR3_TAG_RE = re.compile(
    r"<(\w+),(\w+)(,%)?>|\|([nNrR])|\|c[0-9a-fA-F]{2}([0-9a-fA-F]{6})",
    re.IGNORECASE,
)

DEFAULT_TEXT_COLOR = (255, 255, 255)
CONTENT_PADDING = 8
LINE_HEIGHT = 20
BORDER_LAYERS = 5
CONTENT_BG = (14, 36, 46)
PANEL_BORDERS = [
    ((0, 0, 0), 6),
    ((128, 102, 0), 5),
    ((255, 204, 0), 4),
    ((128, 102, 0), 3),
    ((0, 0, 0), 2),
]

_BG_CACHE: Image.Image | None = None
_BG_PATH: str | None = None


def resolve_items_bg_path(plugin_dir: str) -> str:
    return os.path.join(plugin_dir, "assets", "items_bg.png")


def _hex_to_rgb(hex6: str) -> tuple[int, int, int]:
    return (int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16))


def parse_war3_colored_lines(text: str) -> list[list[tuple[str, tuple[int, int, int]]]]:
    if not text:
        return []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "|n")
    lines: list[list[tuple[str, tuple[int, int, int]]]] = [[]]
    current_color = DEFAULT_TEXT_COLOR
    pos = 0

    for match in _WAR3_TAG_RE.finditer(normalized):
        if match.start() > pos:
            chunk = normalized[pos : match.start()]
            if chunk:
                lines[-1].append((chunk, current_color))

        code = match.group(4)
        color_hex = match.group(5)
        if code:
            if code.lower() == "n":
                lines.append([])
            elif code.lower() == "r":
                current_color = DEFAULT_TEXT_COLOR
        elif color_hex:
            current_color = _hex_to_rgb(color_hex)
        pos = match.end()

    if pos < len(normalized):
        chunk = normalized[pos:]
        if chunk:
            lines[-1].append((chunk, current_color))

    return [line for line in lines if line]


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    if not text:
        return 0
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def wrap_colored_lines(
    draw: ImageDraw.ImageDraw,
    colored_lines: list[list[tuple[str, tuple[int, int, int]]]],
    font,
    max_width: int,
) -> list[list[tuple[str, tuple[int, int, int]]]]:
    wrapped: list[list[tuple[str, tuple[int, int, int]]]] = []

    for line in colored_lines:
        if not line:
            wrapped.append([])
            continue

        current_segments: list[tuple[str, tuple[int, int, int]]] = []
        current_width = 0
        segment_text = ""
        segment_color = DEFAULT_TEXT_COLOR

        def flush_segment() -> None:
            nonlocal segment_text, current_width
            if segment_text:
                current_segments.append((segment_text, segment_color))
                segment_text = ""

        def flush_line() -> None:
            nonlocal current_segments, current_width
            flush_segment()
            if current_segments:
                wrapped.append(current_segments)
            current_segments = []
            current_width = 0

        for text, color in line:
            for ch in text:
                char_width = _text_width(draw, ch, font)
                if current_width + char_width > max_width and segment_text:
                    flush_segment()
                    flush_line()
                if segment_color != color and segment_text:
                    flush_segment()
                segment_color = color
                segment_text += ch
                current_width += char_width

        flush_segment()
        if current_segments:
            wrapped.append(current_segments)

    return wrapped or [[]]


def _load_panel_bg(path: str, size: tuple[int, int]) -> Image.Image | None:
    global _BG_CACHE, _BG_PATH
    if not path or not os.path.exists(path):
        return None
    if _BG_CACHE is not None and _BG_PATH == path and _BG_CACHE.size == size:
        return _BG_CACHE
    try:
        bg = Image.open(path).convert("RGB")
        bg = bg.resize(size, Image.LANCZOS)
        _BG_CACHE = bg
        _BG_PATH = path
        return bg
    except OSError:
        return None


def measure_game_panel(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    panel_width: int,
) -> tuple[int, list[list[tuple[str, tuple[int, int, int]]]]]:
    text_max_width = panel_width - BORDER_LAYERS * 2 - CONTENT_PADDING * 2
    wrapped = wrap_colored_lines(draw, parse_war3_colored_lines(text), font, text_max_width)
    content_height = max(1, len(wrapped)) * LINE_HEIGHT + CONTENT_PADDING * 2
    total_height = content_height + BORDER_LAYERS * 2
    return total_height, wrapped


def draw_game_panel(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    panel_width: int,
    wrapped_lines: list[list[tuple[str, tuple[int, int, int]]]],
    font,
    bg_path: str,
) -> int:
    content_height = max(1, len(wrapped_lines)) * LINE_HEIGHT + CONTENT_PADDING * 2
    total_height = content_height + BORDER_LAYERS * 2

    bg = _load_panel_bg(bg_path, (panel_width, total_height))
    if bg:
        card.paste(bg, (x, y))

    inset = 0
    for color, radius in PANEL_BORDERS:
        draw.rounded_rectangle(
            (x + inset, y + inset, x + panel_width - inset, y + total_height - inset),
            radius=radius,
            outline=color,
            width=1,
        )
        inset += 1

    content_x = x + inset
    content_y = y + inset
    content_w = panel_width - inset * 2
    draw.rounded_rectangle(
        (content_x, content_y, content_x + content_w, content_y + content_height),
        radius=2,
        fill=CONTENT_BG,
        outline=(0, 0, 0),
        width=1,
    )

    text_y = content_y + CONTENT_PADDING
    for line in wrapped_lines:
        text_x = content_x + CONTENT_PADDING
        for segment, color in line:
            draw.text((text_x, text_y), segment, fill=color, font=font)
            text_x += _text_width(draw, segment, font)
        text_y += LINE_HEIGHT

    return total_height
