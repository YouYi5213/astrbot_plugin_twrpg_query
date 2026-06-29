"""从 QuickSearch 中文版 .data 提取英雄技能并合并到 heros.json。"""

from __future__ import annotations

import json
import os
import sys
import zlib
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR.parent))

from astrbot_plugin_twrpg_query.data_loader import format_skill_hotkey, normalize_skill_name, strip_color

DEFAULT_QS_DIR = Path(r"G:/魔兽/QuickSearch_0.74c/resources/app")
QS_DIR = Path(os.environ.get("TWRPG_QS_DIR", DEFAULT_QS_DIR))
CN_DATA = "e7c6a4d33083c01a38b979d70108013d.data"
HEROS_PATH = PLUGIN_DIR / "data" / "twrpg_query" / "heros.json"
TOOLS_HEROS_PATH = (
    Path(__file__).resolve().parents[2]
    / "twrpg_data_tools"
    / "extracted_data"
    / "heros.json"
)

def _skill_entry(skill: dict) -> dict:
    desc = skill.get("desc") or ""
    raw_name = strip_color(skill.get("displayName") or "")
    entry = {
        "id": skill.get("id", ""),
        "name": normalize_skill_name(raw_name),
        "displayName": skill.get("displayName") or "",
        "img": skill.get("img") or "",
        "description": strip_color(desc),
        "rawDesc": desc,
        "hotkey": format_skill_hotkey(skill.get("hotKeys") or ""),
    }
    close = skill.get("closeInfo")
    if close:
        close_desc = close.get("desc") or ""
        close_raw = strip_color(close.get("displayName") or "")
        entry["closeInfo"] = {
            "name": normalize_skill_name(close_raw),
            "displayName": close.get("displayName") or "",
            "img": close.get("img") or "",
            "description": strip_color(close_desc),
            "rawDesc": close_desc,
        }
    return entry


def load_cn_heroes() -> dict[str, dict]:
    data_path = QS_DIR / CN_DATA
    with open(data_path, "rb") as f:
        cn_data = json.loads(zlib.decompress(f.read(), -15).decode("utf-8"))
    return {hero["id"]: hero for hero in cn_data.get("heroes", []) if hero.get("id")}


def merge_heroes(existing: list[dict], cn_by_id: dict[str, dict]) -> list[dict]:
    merged: list[dict] = []
    for hero in existing:
        hero_id = hero.get("id", "")
        cn = cn_by_id.get(hero_id, {})
        raw_stats = dict(hero.get("rawStats") or {})
        upro = cn.get("upro") or raw_stats.get("upro") or ""
        if upro:
            raw_stats["upro"] = upro
        skills = [_skill_entry(skill) for skill in cn.get("skills") or []]
        merged.append(
            {
                **hero,
                "characterName": upro,
                "rawStats": raw_stats if raw_stats else None,
                "skills": skills,
            }
        )
    return merged


def write_heroes(path: Path, heroes: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(heroes, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    cn_by_id = load_cn_heroes()
    existing = json.loads(HEROS_PATH.read_text(encoding="utf-8"))
    merged = merge_heroes(existing, cn_by_id)
    write_heroes(HEROS_PATH, merged)
    write_heroes(TOOLS_HEROS_PATH, merged)

    skill_count = sum(len(h.get("skills") or []) for h in merged)
    print(f"merged {len(merged)} heroes, {skill_count} skills -> {HEROS_PATH}")
    sample = next(h for h in merged if h.get("id") == "H001")
    print(f"sample {sample['displayName']} skills={len(sample.get('skills', []))}")


if __name__ == "__main__":
    main()
