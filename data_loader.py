"""TWRPG 离线数据加载与查询。"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field

from .icon_utils import resolve_icon_path

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

_PASSIVE_ATTRIB_RE = re.compile(r"\n*\s*装备翻译来自B站UP 阿我的手\s*$")

# QuickSearch buildGood: Kle()[item.limit] -> limitHeroes
# QuickSearch locale: common.stages
STAGE_LABELS: list[str] = [
    "",
    "[野外]",
    "[粉末]",
    "[小四]",
    "[四大]",
    "[主龙]",
    "[白怨火水]",
    "[君主]",
    "[爵土马判]",
    "[大天使]",
]


def stage_label(stage: int | None) -> str:
    if stage is None or stage <= 0 or stage >= len(STAGE_LABELS):
        return ""
    return STAGE_LABELS[stage]


LIMIT_HERO_IDS: dict[str, list[str]] = {
    "2": [
        "H001", "H004", "H00E", "H000", "H00H", "H003", "Hmkg", "Hblm",
        "H01H", "H01V", "H011", "H02M", "H021", "H04Q", "H04R", "H04S",
        "H05T", "H065", "H076", "H07X", "H09M", "H07Y", "H086", "H09R", "H019",
    ],
    "3": [
        "H006", "H005", "H002", "H007", "H009", "H008", "H00J", "H01I",
        "H01N", "H02M", "H021", "H066", "H065", "Hmkg", "H003", "H08G",
    ],
    "4": ["H00Z", "H015"],
    "5": ["H00K", "H05B", "H09N"],
    "6": ["H04Q", "H065"],
}


def clean_passive_text(text: str) -> str:
    return _PASSIVE_ATTRIB_RE.sub("", text or "").rstrip()


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
    icon: str | None = None


@dataclass
class RecipeLine:
    entries: list[CraftEntry]
    is_choice: bool = False


@dataclass
class DropEntry:
    boss_name: str
    chance: float
    icon: str | None = None


@dataclass
class HeroRef:
    id: str
    name: str
    icon: str | None = None


@dataclass
class ExclusiveEntry:
    hero_id: str
    hero_name: str
    icon: str | None = None
    skill: str = ""
    description: str = ""


@dataclass
class ItemDisplay:
    id: str
    name: str
    description: str
    raw_description: str = ""
    stage_label: str = ""
    icon: str | None = None
    passive: str = ""
    limit_heroes: list[HeroRef] = field(default_factory=list)
    exclusives: list[ExclusiveEntry] = field(default_factory=list)
    recipe: list[RecipeLine] = field(default_factory=list)
    crafts_into: list[CraftEntry] = field(default_factory=list)
    boss_drops: list[DropEntry] = field(default_factory=list)


class TwrpgDataStore:
    def __init__(self, data_dir: str, icons_dir: str = ""):
        self.data_dir = data_dir
        self.icons_dir = icons_dir
        self.items_by_id: dict[str, dict] = {}
        self.search_index: list[tuple[str, str]] = []
        self.recipes: dict[str, list[dict]] = {}
        self.used_in: dict[str, list[tuple[str, int]]] = {}
        self.drops_by_item: dict[str, list[tuple[str, float]]] = {}
        self.bosses_by_id: dict[str, dict] = {}
        self.heros_by_id: dict[str, dict] = {}
        self.exclusives_by_item: dict[str, list[dict]] = {}
        self.passives_by_id: dict[str, dict] = {}
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
        self._load_passives()
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

            choose_rows = row.get("choose") or []
            if choose_rows:
                options = [
                    (opt.get("subId", ""), int(opt.get("num") or 1))
                    for opt in choose_rows
                    if opt.get("subId")
                ]
                if not options:
                    continue
                self.recipes.setdefault(item_id, []).append(
                    {"sub_id": sub_id, "num": num, "choose": options}
                )
                for opt_id, opt_num in options:
                    self.used_in.setdefault(opt_id, []).append((item_id, opt_num))
                continue

            self.recipes.setdefault(item_id, []).append(
                {"sub_id": sub_id, "num": num, "choose": None}
            )
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

    def _load_passives(self) -> None:
        path = os.path.join(self.data_dir, "item_passives.json")
        if not os.path.exists(path):
            return
        for row in self._load_json("item_passives.json"):
            item_id = row.get("id", "")
            if not item_id:
                continue
            cn = row.get("cn", "")
            if cn:
                row = {**row, "cn": clean_passive_text(cn)}
            self.passives_by_id[item_id] = row

    def _item_icon(self, item_id: str) -> str | None:
        item = self.items_by_id.get(item_id)
        if not item:
            return None
        return resolve_icon_path(self.icons_dir, item.get("img", ""))

    def _entity_icon(self, img: str) -> str | None:
        return resolve_icon_path(self.icons_dir, img)

    def _hero_icon(self, hero_id: str) -> str | None:
        hero = self.heros_by_id.get(hero_id)
        if not hero:
            return None
        return self._entity_icon(hero.get("img", ""))

    def _limit_heroes(self, limit: str) -> list[HeroRef]:
        heroes: list[HeroRef] = []
        for hero_id in LIMIT_HERO_IDS.get(limit, []):
            icon = self._hero_icon(hero_id)
            if not icon:
                continue
            heroes.append(
                HeroRef(
                    id=hero_id,
                    name=self.hero_name(hero_id),
                    icon=icon,
                )
            )
        return heroes

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
        raw_description = item.get("rawDesc") or item.get("description") or ""

        limit = str(item.get("limit") or "").strip()
        limit_heroes = self._limit_heroes(limit) if limit and limit != "0" else []

        exclusives: list[ExclusiveEntry] = []
        for row in self.exclusives_by_item.get(item_id, []):
            hero_id = row.get("heroId", "")
            exclusives.append(
                ExclusiveEntry(
                    hero_id=hero_id,
                    hero_name=self.hero_name(hero_id),
                    icon=self._hero_icon(hero_id),
                    skill=strip_color(row.get("on", "")),
                    description=strip_color(row.get("desc", "")),
                )
            )

        recipe: list[RecipeLine] = []
        for row in self.recipes.get(item_id, []):
            choose = row.get("choose")
            if choose:
                entries = [
                    CraftEntry(
                        name=self.item_name(opt_id),
                        quantity=opt_num,
                        icon=self._item_icon(opt_id),
                    )
                    for opt_id, opt_num in choose
                ]
                recipe.append(RecipeLine(entries=entries, is_choice=True))
                continue
            sub_id = row.get("sub_id", "")
            num = int(row.get("num") or 1)
            recipe.append(
                RecipeLine(
                    entries=[
                        CraftEntry(
                            name=self.item_name(sub_id),
                            quantity=num,
                            icon=self._item_icon(sub_id),
                        )
                    ]
                )
            )

        crafts_into = [
            CraftEntry(
                name=self.item_name(target_id),
                quantity=num,
                icon=self._item_icon(target_id),
            )
            for target_id, num in self.used_in.get(item_id, [])
        ]

        boss_drops: list[DropEntry] = []
        for boss_id, chance in self.drops_by_item.get(item_id, []):
            boss = self.bosses_by_id.get(boss_id)
            if not boss:
                continue
            boss_drops.append(
                DropEntry(
                    boss_name=self.boss_name(boss_id),
                    chance=chance,
                    icon=self._entity_icon(boss.get("img", "")),
                )
            )
        boss_drops.sort(key=lambda x: (-x.chance, x.boss_name))

        passive = strip_color(self.passives_by_id.get(item_id, {}).get("cn", ""))
        if passive:
            raw_description = raw_description.rstrip() + "\n" + passive

        return ItemDisplay(
            id=item_id,
            name=name,
            stage_label=stage_label(item.get("stage")),
            description=description,
            raw_description=raw_description,
            icon=self._item_icon(item_id),
            passive=passive,
            limit_heroes=limit_heroes,
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
