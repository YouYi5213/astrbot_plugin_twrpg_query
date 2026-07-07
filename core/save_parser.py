"""解析世界RPG存档 txt（移植自 TWRPGReader SaveFileParser）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PRELOAD_RE = re.compile(r'call\s+Preload\s*\(\s*"([^"]*)"\s*\)')
SECTION_HEADER_RE = re.compile(r"^-{5,}\s*(.+?)\s*-{5,}$")
SAVE_CODE_HEAD_RE = re.compile(r"存档代码\s*(\d*)\s*:")


@dataclass
class SaveData:
    game_id: str = ""
    job: str = ""
    level: str = ""
    game_version: str = ""
    compat_version: str = ""
    carried_items: list[str] = field(default_factory=list)
    backpack_items: list[str] = field(default_factory=list)
    warehouse_items: list[str] = field(default_factory=list)
    account_badge_display: str | None = None
    account_badge_color: int = 0

    def set_account_badge_if_higher(self, display: str, priority: int) -> None:
        if self.account_badge_color == 0 or priority < self.account_badge_color:
            self.account_badge_display = display
            self.account_badge_color = priority


@dataclass
class _ParseContext:
    section: str | None = None
    stage_parse_complete: bool = False


def parse_string_for_stage(content: str) -> SaveData:
    data = SaveData()
    blocks = _extract_preload_blocks(content)
    if not blocks:
        return data
    ctx = _ParseContext()
    for block in blocks:
        for raw_line in block.splitlines():
            _process_line(data, ctx, raw_line.strip())
            if ctx.stage_parse_complete:
                return data
    return data


def _extract_preload_blocks(content: str) -> list[str]:
    blocks: list[str] = []
    for match in PRELOAD_RE.finditer(content):
        block = (match.group(1) or "").strip()
        if block:
            blocks.append(block)
    return blocks


def _process_line(data: SaveData, ctx: _ParseContext, line: str) -> None:
    if not line:
        return

    section_header = _detect_section(line)
    if section_header is not None:
        ctx.section = section_header
        return

    if SAVE_CODE_HEAD_RE.search(line):
        ctx.stage_parse_complete = True
        return

    if ctx.section is None:
        if line.startswith("游戏ID:"):
            data.game_id = line[len("游戏ID:") :].strip()
        elif line.startswith("职业:"):
            data.job = line[len("职业:") :].strip()
        elif line.startswith("等级:"):
            data.level = line[len("等级:") :].strip()
        elif line.startswith("游戏版本:"):
            data.game_version = line[len("游戏版本:") :].strip()
        elif line.startswith("兼容版本:"):
            data.compat_version = line[len("兼容版本:") :].strip()
        return

    if ctx.section == "account":
        if _is_only_dashes_or_empty(line):
            ctx.section = None
        else:
            text = _strip_leading_number(line).strip()
            if "不朽者徽章" in text:
                data.set_account_badge_if_higher("不朽者徽章", 1)
            elif "世界传奇徽章" in text:
                data.set_account_badge_if_higher("世界传奇徽章", 2)
            elif "永恒·世界大咖徽章" in text:
                data.set_account_badge_if_higher("永恒·世界大咖徽章", 3)
            elif "世界大咖徽章" in text:
                data.set_account_badge_if_higher("世界大咖徽章", 4)
        return

    if _is_only_dashes_or_empty(line):
        return

    if ctx.section == "carried":
        data.carried_items.append(line)
    elif ctx.section == "backpack":
        data.backpack_items.append(line)
    elif ctx.section == "warehouse":
        data.warehouse_items.append(line)


def _detect_section(line: str) -> str | None:
    match = SECTION_HEADER_RE.match(line.strip())
    if not match:
        return None
    inner = match.group(1).strip().replace(" ", "")
    if not inner:
        return None
    if "账号物品" in inner or inner == "账号":
        return "account"
    if "携带物品" in inner or inner == "携带":
        return "carried"
    if "背包" in inner:
        return "backpack"
    if "仓库" in inner:
        return "warehouse"
    return None


def _is_only_dashes_or_empty(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return True
    return bool(re.fullmatch(r"[-\s]+", text))


def _strip_leading_number(line: str) -> str:
    text = (line or "").strip()
    index = 0
    while index < len(text) and text[index].isdigit():
        index += 1
    if index > 0 and index < len(text) and text[index] == ".":
        if index + 1 >= len(text) or text[index + 1] == " ":
            return text[index + 1 :].strip()
    return text
