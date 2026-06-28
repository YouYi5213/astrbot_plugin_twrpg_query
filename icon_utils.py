"""图标路径解析。"""

from __future__ import annotations

import os


def img_field_to_icon_name(img: str) -> str:
    if not img:
        return ""
    normalized = img.replace("\\", "/")
    base = os.path.basename(normalized)
    stem, _ext = os.path.splitext(base)
    return stem


def resolve_icon_path(icons_dir: str, img: str) -> str | None:
    icon_name = img_field_to_icon_name(img)
    if not icon_name or not icons_dir:
        return None
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = os.path.join(icons_dir, icon_name + ext)
        if os.path.exists(path):
            return path
    return None


def resolve_icons_dir(plugin_dir: str) -> str:
    return os.path.join(plugin_dir, "assets", "icons")
