"""目标物品材料规划：配方递归展开、库存扣减、缺口与掉落来源。

纯逻辑模块（不依赖 Pillow），供「世界材料」指令与单元测试使用。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .core.save_parser import parse_save_item_line
from .data_loader import TwrpgDataStore, normalize_query, stage_label

DEFAULT_MAX_DEPTH = 12
MAX_DROPS_PER_MATERIAL = 3
MAX_SOURCE_MATERIALS = 6


@dataclass
class DropSource:
    """某个材料的掉落来源。"""

    boss_id: str
    boss_name: str
    chance: float | str
    stage: int = 0
    icon: str | None = None

    @property
    def stage_label(self) -> str:
        return stage_label(self.stage)


@dataclass
class MaterialNeed:
    """一种材料的需求情况。"""

    item_id: str
    name: str
    required: int
    owned: int
    missing: int
    stage: int = 0
    icon: str | None = None
    depth: int = 0
    drops: list[DropSource] = field(default_factory=list)

    @property
    def stage_label(self) -> str:
        return stage_label(self.stage)

    @property
    def satisfied(self) -> bool:
        return self.missing <= 0


@dataclass
class OptionalChoice:
    name: str
    quantity: int
    icon: str | None = None
    stage: int = 0


@dataclass
class OptionalGroup:
    """配方中的「任选其一」材料组。"""

    parent_name: str
    quantity: int
    choices: list[OptionalChoice] = field(default_factory=list)

    @property
    def label(self) -> str:
        names = " / ".join(choice.name for choice in self.choices)
        return f"{names} x{self.quantity}"


@dataclass
class MaterialPlan:
    target_id: str
    target_name: str
    quantity: int = 1
    target_stage: int = 0
    target_icon: str | None = None
    needs: list[MaterialNeed] = field(default_factory=list)
    optional_groups: list[OptionalGroup] = field(default_factory=list)
    truncated: bool = False

    @property
    def target_stage_label(self) -> str:
        return stage_label(self.target_stage)

    @property
    def missing(self) -> list[MaterialNeed]:
        return [need for need in self.needs if not need.satisfied]

    @property
    def satisfied(self) -> list[MaterialNeed]:
        return [need for need in self.needs if need.satisfied]

    @property
    def source_materials(self) -> list[MaterialNeed]:
        """需要列出掉落来源的材料（限缺口材料）。"""
        return [need for need in self.missing if need.drops][:MAX_SOURCE_MATERIALS]


def resolve_item_id(store: TwrpgDataStore, name: str) -> str | None:
    """按存档/聊天里出现的名字解析物品 ID。"""
    text = (name or "").strip()
    if not text:
        return None
    key = normalize_query(text)
    if not key:
        return None
    item_id = store.name_to_item_id.get(key)
    if item_id and store._is_queryable(store.items_by_id.get(item_id, {})):
        return item_id
    matches = store.search(text, limit=12)
    exact = [cid for cid in matches if normalize_query(store.item_name(cid)) == key]
    if exact:
        return store._pick_best_item_id(exact)
    if len(matches) == 1:
        return matches[0]
    return store._pick_best_item_id(matches)


def inventory_from_save_lines(
    store: TwrpgDataStore,
    lines,
    *,
    into: dict[str, int] | None = None,
) -> dict[str, int]:
    """把存档物品行聚合成 {item_id: 数量}。"""
    counts = into if into is not None else {}
    for raw in lines or []:
        name, qty = parse_save_item_line(raw)
        if not name:
            continue
        item_id = resolve_item_id(store, name)
        if not item_id:
            continue
        counts[item_id] = counts.get(item_id, 0) + max(1, int(qty))
    return counts


def _drop_sources(store: TwrpgDataStore, item_id: str) -> list[DropSource]:
    rows = store.drops_by_item.get(item_id) or []
    sources = [
        DropSource(
            boss_id=boss_id,
            boss_name=store.boss_name(boss_id),
            chance=chance,
            stage=store.infer_boss_stage(boss_id),
            icon=store._entity_icon(
                (store.bosses_by_id.get(boss_id) or {}).get("img", "")
            ),
        )
        for boss_id, chance in rows
    ]
    def _sort_key(src: DropSource) -> tuple[int, float]:
        chance = src.chance if isinstance(src.chance, (int, float)) else 0.0
        return (-src.stage, -float(chance))

    sources.sort(key=_sort_key)
    return sources[:MAX_DROPS_PER_MATERIAL]


def plan_materials(
    store: TwrpgDataStore,
    target_id: str,
    *,
    quantity: int = 1,
    inventory: dict[str, int] | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> MaterialPlan | None:
    """展开目标物品配方，扣除库存，返回缺口材料与掉落来源。"""
    if target_id not in store.items_by_id:
        return None

    quantity = max(1, int(quantity or 1))
    stock = {key: int(value) for key, value in (inventory or {}).items() if int(value) > 0}

    gross: Counter[str] = Counter()
    owned: Counter[str] = Counter()
    leaves: Counter[str] = Counter()
    depths: dict[str, int] = {}
    optional_groups: list[OptionalGroup] = []
    seen_groups: set[tuple[str, tuple[str, ...]]] = set()
    truncated = False

    def expand(item_id: str, qty: int, depth: int, chain: frozenset[str]) -> None:
        nonlocal truncated
        if qty <= 0:
            return
        gross[item_id] += qty
        depths[item_id] = min(depths.get(item_id, depth), depth)

        take = min(stock.get(item_id, 0), qty)
        if take:
            stock[item_id] -= take
            owned[item_id] += take
            qty -= take
        if qty <= 0:
            return

        rows = store.recipes.get(item_id) or []
        if not rows or item_id in chain:
            leaves[item_id] += qty
            return
        if depth >= max_depth:
            truncated = True
            leaves[item_id] += qty
            return

        next_chain = chain | {item_id}
        for row in rows:
            sub_id = str(row.get("sub_id") or "")
            if not sub_id:
                continue
            num = max(1, int(row.get("num") or 1))
            choose = row.get("choose") or []
            if choose:
                choices = [
                    OptionalChoice(
                        name=store.item_name(opt_id),
                        quantity=num * qty,
                        icon=store.item_icon(opt_id),
                        stage=store.item_stage(opt_id),
                    )
                    for opt_id, _opt_num in choose
                ]
                key = (store.item_name(item_id), tuple(choice.name for choice in choices))
                if key not in seen_groups:
                    seen_groups.add(key)
                    optional_groups.append(
                        OptionalGroup(
                            parent_name=store.item_name(item_id),
                            quantity=num * qty,
                            choices=choices,
                        )
                    )
                continue
            expand(sub_id, qty * num, depth + 1, next_chain)

    expand(target_id, quantity, 0, frozenset())

    needs: list[MaterialNeed] = []
    for item_id, count in leaves.items():
        need = MaterialNeed(
            item_id=item_id,
            name=store.item_name(item_id),
            required=gross.get(item_id, count),
            owned=owned.get(item_id, 0),
            missing=count,
            stage=store.item_stage(item_id),
            icon=store.item_icon(item_id),
            depth=depths.get(item_id, 0),
            drops=_drop_sources(store, item_id) if count else [],
        )
        needs.append(need)

    needs.sort(key=lambda need: (need.satisfied, -need.stage, -need.missing, need.name))

    return MaterialPlan(
        target_id=target_id,
        target_name=store.item_name(target_id),
        quantity=quantity,
        target_stage=store.item_stage(target_id),
        target_icon=store.item_icon(target_id),
        needs=needs,
        optional_groups=optional_groups,
        truncated=truncated,
    )


def inventory_summary(store: TwrpgDataStore, counts: dict[str, int]) -> int:
    """库存里的物品种类数。"""
    return sum(1 for item_id, qty in counts.items() if qty > 0 and item_id in store.items_by_id)


def parse_quantity(text: str) -> tuple[str, int]:
    """解析「物品名 x2」里的数量后缀，返回 (名称, 数量)。"""
    value = (text or "").strip()
    for sep in ("x", "X", "×", "*", "＊"):
        idx = value.rfind(sep)
        if idx <= 0:
            continue
        tail = value[idx + 1 :].strip()
        if not tail.isdigit():
            continue
        name = value[:idx].strip()
        if not name:
            continue
        qty = int(tail)
        if 1 <= qty <= 99:
            return name, qty
    return value, 1
