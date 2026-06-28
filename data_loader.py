"""TWRPG 离线数据加载与查询。"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field

_WAR3_COLOR_RE = re.compile(r"\|c[A-Fa-f0-9]{8}", re.IGNORECASE)
_WAR3_END_RE = re.compile(r"\|r", re.IGNORECASE)
_NORMALIZE_RE = re.compile(r"[\s·•・\-_]+")

WEAR_LIMIT_LABELS: dict[str, str] = {
    "1": "通用",
    "2": "近战",
    "3": "远程",
    "4": "法杖",
    "5": "枪支",
    "6": "背包",
}


def strip_color(text: str) -> str:
    if not text:
        return ""
    text = _WAR3_COLOR_RE.sub("", text)
    text = _WAR3_END_RE.sub("", text)
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def normalize_query(text: str) -> str:
    text = strip_color(text).casefold()
    text = unicodedata.normalize("NFKC", text)
    return _NORMALIZE_RE.sub("", text)


@dataclass
class CraftEntry:
    name: str
    quantity: int


@dataclass
class DropEntry:
    boss_name: str
    chance: float


@dataclass
class ExclusiveEntry:
    hero_name: str
    skill: str
    description: str


@dataclass
class ItemDisplay:
    id: str
    name: str
    description: str
    wear_limit: list[str] = field(default_factory=list)
    exclusives: list[ExclusiveEntry] = field(default_factory=list)
    recipe: list[CraftEntry] = field(default_factory=list)
    crafts_into: list[CraftEntry] = field(default_factory=list)
    boss_drops: list[DropEntry] = field(default_factory=list)


class TwrpgDataStore:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.items_by_id: dict[str, dict] = {}
        self.search_index: list[tuple[str, str]] = []
        self.recipes: dict[str, list[tuple[str, int]]] = {}
        self.used_in: dict[str, list[tuple[str, int]]] = {}
        self.drops_by_item: dict[str, list[tuple[str, float]]] = {}
        self.bosses_by_id: dict[str, dict] = {}
        self.heros_by_id: dict[str, dict] = {}
        self.exclusives_by_item: dict[str, list[dict]] = {}
        self.loaded = False

    def load(self) -> None:
        if self.loaded:
            return

        items_path = os.path.join(self.data_dir, "items.json")
        with open(items_path, "r", encoding="utf-8") as f:
            items = json.load(f)

        for item in items:
            item_id = item.get("id", "")
            if not item_id:
                continue
            self.items_by_id[item_id] = item
            for label in self._item_search_labels(item):
                key = normalize_query(label)
                if key:
                    self.search_index.append((key, item_id))

        self._load_makes()
        self._load_drops()
        self._load_bosses()
        self._load_heros()
        self._load_exclusives()
        self.loaded = True

    def _load_json(self, filename: str):
        path = os.path.join(self.data_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_makes(self) -> None:
        for row in self._load_json("makes.json"):
            item_id = row.get("id", "")
            sub_id = row.get("subId", "")
            num = int(row.get("num") or 1)
            if not item_id or not sub_id:
                continue
            self.recipes.setdefault(item_id, []).append((sub_id, num))
            self.used_in.setdefault(sub_id, []).append((item_id, num))

    def _load_drops(self) -> None:
        for row in self._load_json("drops.json"):
            boss_id = row.get("id", "")
            drop_id = row.get("dropId", "")
            if not boss_id or not drop_id:
                continue
            try:
                chance = float(row.get("chance") or 0)
            except (TypeError, ValueError):
                continue
            self.drops_by_item.setdefault(drop_id, []).append((boss_id, chance))

    def _load_bosses(self) -> None:
        for boss in self._load_json("bosses.json"):
            boss_id = boss.get("id", "")
            if boss_id:
                self.bosses_by_id[boss_id] = boss

    def _load_heros(self) -> None:
        for hero in self._load_json("heros.json"):
            hero_id = hero.get("id", "")
            if hero_id:
                self.heros_by_id[hero_id] = hero

    def _load_exclusives(self) -> None:
        for row in self._load_json("exclusives.json"):
            good_id = row.get("goodId", "")
            if good_id:
                self.exclusives_by_item.setdefault(good_id, []).append(row)

    @staticmethod
    def _item_search_labels(item: dict) -> set[str]:
        labels = {
            item.get("displayName", ""),
            item.get("name", ""),
            strip_color(item.get("colorName", "")),
            item.get("id", ""),
        }
        return {x for x in labels if x}

    def item_name(self, item_id: str) -> str:
        item = self.items_by_id.get(item_id)
        if not item:
            return item_id
        return strip_color(item.get("displayName") or item.get("name") or item_id)

    def boss_name(self, boss_id: str) -> str:
        boss = self.bosses_by_id.get(boss_id)
        if not boss:
            return boss_id
        return strip_color(boss.get("displayName") or boss.get("name") or boss_id)

    def hero_name(self, hero_id: str) -> str:
        hero = self.heros_by_id.get(hero_id)
        if not hero:
            return hero_id
        return strip_color(hero.get("displayName") or hero.get("name") or hero_id)

    @staticmethod
    def _is_queryable(item: dict) -> bool:
        item_id = str(item.get("id") or "")
        name = strip_color(item.get("displayName") or item.get("name") or "")
        if item_id.startswith("000"):
            return False
        if "说明" in name or "掉率" in name:
            return False
        return True

    def search(self, query: str, limit: int = 8) -> list[str]:
        key = normalize_query(query)
        if not key:
            return []

        exact: list[str] = []
        prefix: list[str] = []
        contains: list[str] = []
        seen: set[str] = set()

        for index_key, item_id in self.search_index:
            if item_id in seen:
                continue
            item = self.items_by_id.get(item_id)
            if not item or not self._is_queryable(item):
                continue
            if index_key == key:
                exact.append(item_id)
                seen.add(item_id)
            elif index_key.startswith(key):
                prefix.append(item_id)
                seen.add(item_id)
            elif key in index_key:
                contains.append(item_id)
                seen.add(item_id)

        ordered = exact + prefix + contains
        return ordered[:limit]

    def build_display(self, item_id: str) -> ItemDisplay | None:
        item = self.items_by_id.get(item_id)
        if not item:
            return None

        name = strip_color(item.get("displayName") or item.get("name") or item_id)
        description = strip_color(item.get("description") or "")

        wear_limit: list[str] = []
        limit = str(item.get("limit") or "").strip()
        if limit and limit != "0":
            label = WEAR_LIMIT_LABELS.get(limit, f"类型 {limit}")
            wear_limit.append(label)

        exclusives: list[ExclusiveEntry] = []
        for row in self.exclusives_by_item.get(item_id, []):
            exclusives.append(
                ExclusiveEntry(
                    hero_name=self.hero_name(row.get("heroId", "")),
                    skill=strip_color(row.get("on", "")),
                    description=strip_color(row.get("desc", "")),
                )
            )

        recipe = [
            CraftEntry(name=self.item_name(sub_id), quantity=num)
            for sub_id, num in self.recipes.get(item_id, [])
        ]

        crafts_into = [
            CraftEntry(name=self.item_name(target_id), quantity=num)
            for target_id, num in self.used_in.get(item_id, [])
        ]

        boss_drops: list[DropEntry] = []
        for boss_id, chance in self.drops_by_item.get(item_id, []):
            if boss_id not in self.bosses_by_id:
                continue
            boss_drops.append(
                DropEntry(boss_name=self.boss_name(boss_id), chance=chance)
            )
        boss_drops.sort(key=lambda x: (-x.chance, x.boss_name))

        return ItemDisplay(
            id=item_id,
            name=name,
            description=description,
            wear_limit=wear_limit,
            exclusives=exclusives,
            recipe=recipe,
            crafts_into=crafts_into,
            boss_drops=boss_drops,
        )


def resolve_data_dir(plugin_dir: str) -> str:
    candidates = [
        os.path.join(plugin_dir, "data", "twrpg_query"),
        os.path.join(os.getcwd(), "data", "twrpg_query"),
    ]
    for path in candidates:
        if os.path.exists(os.path.join(path, "items.json")):
            return path
    return candidates[0]
