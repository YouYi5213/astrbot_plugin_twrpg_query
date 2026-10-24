"""图鉴分类浏览：分类表、筛选与分页（纯逻辑，不依赖 Pillow）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .data_loader import TwrpgDataStore, normalize_query, stage_label

# 规范分类名 → items.json 里 category 必须同时包含的标签
CODEX_CATEGORIES: dict[str, tuple[str, ...]] = {
    "装备": ("Equip",),
    "武器": ("Equip", "Weapon"),
    "衣服": ("Equip", "Armor"),
    "头盔": ("Equip", "Helm"),
    "饰品": ("Equip", "Ring"),
    "翅膀": ("Equip", "Wings"),
    "材料": ("Material",),
    "其他": ("Other",),
    "全部": (),
}

# 玩家常用别名 → 规范分类名
CODEX_CATEGORY_ALIASES: dict[str, str] = {
    "武器": "武器",
    "武": "武器",
    "兵器": "武器",
    "剑": "武器",
    "刀": "武器",
    "弓": "武器",
    "杖": "武器",
    "衣": "衣服",
    "衣服": "衣服",
    "护甲": "衣服",
    "甲": "衣服",
    "头": "头盔",
    "头盔": "头盔",
    "帽子": "头盔",
    "饰品": "饰品",
    "戒指": "饰品",
    "戒": "饰品",
    "项链": "饰品",
    "翅膀": "翅膀",
    "翼": "翅膀",
    "材料": "材料",
    "素材": "材料",
    "其他": "其他",
    "杂物": "其他",
    "全部": "全部",
    "所有": "全部",
    "装备": "装备",
}

# 阶段筛选别名
STAGE_ALIASES: dict[str, int] = {
    "野外": 1,
    "粉末": 2,
    "小四": 3,
    "四大": 4,
    "主龙": 5,
    "白怨火水": 6,
    "白怨": 6,
    "火水": 6,
    "君主": 7,
    "爵土马判": 8,
    "大天使": 9,
    "无": 0,
    "无阶段": 0,
}

PAGE_SIZE = 32


@dataclass
class CodexSelection:
    """一次图鉴查询的筛选结果。"""

    category: str | None = None
    stage: int | None = None
    keyword: str = ""
    page: int = 1
    item_ids: list[str] = field(default_factory=list)
    total: int = 0

    @property
    def label(self) -> str:
        parts: list[str] = []
        if self.category:
            parts.append(self.category)
        if self.stage is not None:
            parts.append(stage_label(self.stage).strip("[]") or f"阶段{self.stage}")
        if self.keyword:
            parts.append(f"“{self.keyword}”")
        return " · ".join(parts) if parts else "全部物品"

    @property
    def page_count(self) -> int:
        if self.total <= 0:
            return 0
        return (self.total + PAGE_SIZE - 1) // PAGE_SIZE

    @property
    def has_next(self) -> bool:
        return self.page < self.page_count


def resolve_category(token: str) -> str | None:
    """把玩家输入的分类词解析成规范分类名。"""
    text = normalize_query(token)
    if not text:
        return None
    for alias, canonical in CODEX_CATEGORY_ALIASES.items():
        if normalize_query(alias) == text:
            return canonical
    for alias, canonical in CODEX_CATEGORY_ALIASES.items():
        key = normalize_query(alias)
        if len(key) >= 2 and key in text:
            return canonical
    return None


def resolve_stage(token: str) -> int | None:
    """把阶段词（四大/4/大天使…）解析成阶段数字。"""
    text = normalize_query(token)
    if not text:
        return None
    if text.isdigit():
        value = int(text)
        return value if 0 <= value <= 9 else None
    for alias, stage in STAGE_ALIASES.items():
        if normalize_query(alias) == text:
            return stage
    return None


_STAGE_TOKENS: dict[int, str] = {
    1: "野外",
    2: "粉末",
    3: "小四",
    4: "四大",
    5: "主龙",
    6: "白怨火水",
    7: "君主",
    8: "爵土马判",
    9: "大天使",
}


def stage_token(stage: int) -> str:
    """阶段数字 → 可用于指令的阶段词。"""
    return _STAGE_TOKENS.get(int(stage), str(int(stage)))


def _matches_category(item: dict, required: tuple[str, ...]) -> bool:
    if not required:
        return True
    categories = item.get("category") or []
    return all(token in categories for token in required)


def select_items(
    store: TwrpgDataStore,
    category: str | None = None,
    *,
    stage: int | None = None,
    keyword: str = "",
) -> list[str]:
    """按分类/阶段/关键词筛选图鉴条目，按阶段与品质倒序排列。"""
    required = CODEX_CATEGORIES.get(category or "", ())
    key = normalize_query(keyword)
    result: list[str] = []
    for item_id, item in store.items_by_id.items():
        if not store._is_queryable(item):
            continue
        if not _matches_category(item, required):
            continue
        if stage is not None and int(item.get("stage") or 0) != stage:
            continue
        if key:
            name_key = normalize_query(store.item_name(item_id))
            raw_key = normalize_query(str(item.get("name") or ""))
            if key not in name_key and key not in raw_key:
                continue
        result.append(item_id)
    result.sort(
        key=lambda item_id: (
            -int((store.items_by_id.get(item_id) or {}).get("stage") or 0),
            -int((store.items_by_id.get(item_id) or {}).get("quality") or 0),
            store.item_name(item_id),
        )
    )
    return result


def build_selection(
    store: TwrpgDataStore,
    category: str | None = None,
    *,
    stage: int | None = None,
    keyword: str = "",
    page: int = 1,
) -> CodexSelection:
    """筛选 + 分页，返回当前页条目。"""
    all_ids = select_items(store, category, stage=stage, keyword=keyword)
    total = len(all_ids)
    page_count = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 0
    page = max(1, int(page or 1))
    if page_count and page > page_count:
        page = page_count
    start = (page - 1) * PAGE_SIZE
    return CodexSelection(
        category=category,
        stage=stage,
        keyword=keyword,
        page=page,
        item_ids=all_ids[start : start + PAGE_SIZE],
        total=total,
    )


def category_hint_text(store: TwrpgDataStore | None = None) -> str:
    """「世界图鉴」无参数时的分类提示。"""
    lines = ["【世界RPG 图鉴】按分类浏览物品", ""]
    order = ("武器", "衣服", "头盔", "饰品", "翅膀", "材料", "其他", "装备", "全部")
    for name in order:
        count = ""
        if store is not None:
            total = len(select_items(store, name))
            count = f"（{total} 件）"
        lines.append(f"· 世界图鉴 {name} {count}".rstrip())
    lines.append("")
    lines.append("可加阶段与关键词筛选，例如：")
    lines.append("· 世界图鉴 武器 四大")
    lines.append("· 世界图鉴 武器 剑")
    lines.append("· 世界图鉴 武器 四大 第2页")
    return "\n".join(lines)


def parse_codex_args(tokens: list[str]) -> tuple[str | None, int | None, str, int]:
    """解析图鉴参数，返回 (分类, 阶段, 关键词, 页码)。"""
    category: str | None = None
    stage: int | None = None
    keyword_parts: list[str] = []
    page = 1

    for index, token in enumerate(tokens):
        text = token.strip()
        if not text:
            continue
        page_value, is_page = _parse_page(text)
        if is_page:
            page = page_value
            continue
        if category is None:
            canonical = resolve_category(text)
            if canonical is not None:
                category = canonical
                continue
        stage_value = resolve_stage(text)
        if stage_value is not None:
            stage = stage_value
            continue
        keyword_parts.append(text)

    return category, stage, "".join(keyword_parts), page


def _parse_page(token: str) -> tuple[int, bool]:
    text = normalize_query(token)
    if not text:
        return 1, False
    if text.startswith("第") and text.endswith("页"):
        text = text[1:-1]
    elif text.endswith("页"):
        text = text[:-1]
    elif text.startswith("页"):
        text = text[1:]
    else:
        return 1, False
    if not text.isdigit():
        return 1, False
    return max(1, int(text)), True
