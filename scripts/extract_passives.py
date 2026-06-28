"""从 QuickSearch app520a4269.js 提取物品被动/主动描述。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

DEFAULT_JS = Path(r"G:/魔兽/QuickSearch_0.74c/resources/app/js/app520a4269.js")
JS_PATH = Path(os.environ.get("TWRPG_QS_JS", DEFAULT_JS))
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "twrpg_query" / "item_passives.json"

ENTRY_RE = re.compile(
    r'\{id:"([^"]+)",enName:"([^"]*)",koName:"([^"]*)",en:"((?:\\.|[^"\\])*)",cn:"((?:\\.|[^"\\])*)"\}',
)


def unescape_js_string(text: str) -> str:
    return (
        text.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def main() -> None:
    js = JS_PATH.read_text(encoding="utf-8", errors="ignore")
    entries: dict[str, dict] = {}
    for match in ENTRY_RE.finditer(js):
        item_id, en_name, ko_name, en_text, cn_text = match.groups()
        entries[item_id] = {
            "id": item_id,
            "enName": en_name,
            "koName": ko_name,
            "en": unescape_js_string(en_text),
            "cn": unescape_js_string(cn_text),
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(list(entries.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"extracted {len(entries)} passives -> {OUT_PATH}")
    sample = entries.get("srbd", {})
    if sample:
        print("srbd cn preview:")
        print(sample.get("cn", "")[:200])


if __name__ == "__main__":
    main()
