"""从 QuickSearch 安装目录同步图标，并提取被动描述。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_QS_APP = Path(r"G:/魔兽/QuickSearch_0.74c/resources/app")
PLUGIN_DIR = Path(__file__).resolve().parents[1]
ICONS_DST = PLUGIN_DIR / "assets" / "icons"


def copy_icons(src_dir: Path, dst_dir: Path) -> int:
    dst_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in src_dir.glob("*"):
        if not src.is_file():
            continue
        dst = dst_dir / src.name
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy2(src, dst)
        count += 1
    return count


def main() -> None:
    qs_app = Path(os.environ.get("TWRPG_QS_APP", DEFAULT_QS_APP))
    icons_src = qs_app / "extracted_icons"
    if not icons_src.exists():
        raise SystemExit(f"未找到图标目录: {icons_src}")

    copied = copy_icons(icons_src, ICONS_DST)
    print(f"icons synced: {copied} -> {ICONS_DST}")

    bg_src = qs_app / "assets" / "items_bg.png"
    bg_dst = PLUGIN_DIR / "assets" / "items_bg.png"
    if bg_src.exists():
        bg_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bg_src, bg_dst)
        print(f"items_bg synced -> {bg_dst}")
    else:
        print(f"warning: items_bg not found at {bg_src}")

    extract_script = Path(__file__).with_name("extract_passives.py")
    env = os.environ.copy()
    env["TWRPG_QS_JS"] = str(qs_app / "js" / "app520a4269.js")
    subprocess.check_call([sys.executable, str(extract_script)], env=env)


if __name__ == "__main__":
    main()
