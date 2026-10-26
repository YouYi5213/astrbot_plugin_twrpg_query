"""目标物品材料规划：配方递归展开、库存扣减、缺口与掉落来源。

纯逻辑模块（不依赖 Pillow），供「世界材料」指令与单元测试使用。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace

from .core.save_parser import parse_save_item_line
from .data_loader import TwrpgDataStore, normalize_query, stage_label

DEFAULT_MAX_DEPTH = 12
MAX_DROPS_PER_MATERIAL = 3
MAX_SOURCE_MATERIALS = 6

# 「魔石」「硬币」属于兑换材料，不是需要去打/合成的目标。与读档器一致：
# 当一件物品的配方全部由兑换材料组成时，不再向下展开，直接把该物品本身
# 算作缺料（玩家真正要找的是这件「完整材料」，而不是它下面的魔石）。
EXCHANGE_MATERIAL_KEYWORDS = ("魔石", "币")


def is_exchange_material(name: str) -> bool:
    """是否为兑换类材料（魔石 / 硬币）。"""
    text = (name or "").strip()
    return any(keyword in text for keyword in EXCHANGE_MATERIAL_KEYWORDS)


def recipe_has_real_material(store: TwrpgDataStore, rows) -> bool:
    """配方里是否存在非兑换类材料（存在才值得继续展开）。"""
    for row in rows or []:
        sub_id = str(row.get("sub_id") or "")
        if sub_id and not is_exchange_material(store.item_name(sub_id)):
            return True
        for opt_id, _opt_num in row.get("choose") or []:
            if not is_exchange_material(store.item_name(opt_id)):
                return True
    return False


@dataclass
class DropSource:
    """某个材料的掉落来源。"""

    boss_id: str
    boss_name: str
    chance: float | str
    stage: int = 0
    icon: str | None = None
    # 完整材料本身不掉落时，从它的兑换材料继承来源，这里记下那个魔石的名字。
    source_name: str = ""

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


def _exchange_children(store: TwrpgDataStore, item_id: str) -> list[str]:
    """配方里的兑换材料（魔石 / 硬币）item_id 列表。"""
    ids: list[str] = []
    for row in store.recipes.get(item_id) or []:
        sub_id = str(row.get("sub_id") or "")
        if sub_id:
            ids.append(sub_id)
        for opt_id, _opt_num in row.get("choose") or []:
            if opt_id:
                ids.append(str(opt_id))
    return ids


def _inherited_drop_sources(store: TwrpgDataStore, item_id: str) -> list[DropSource]:
    """完整材料自身没有掉落时，用它的魔石/硬币来源代替，并标注是哪种材料。"""
    merged: list[DropSource] = []
    seen: set[tuple[str, str, str]] = set()
    for sub_id in _exchange_children(store, item_id):
        for source in _drop_sources(store, sub_id):
            key = (source.boss_id, str(source.chance), sub_id)
            if key in seen:
                continue
            seen.add(key)
            merged.append(replace(source, source_name=store.item_name(sub_id)))

    def _sort_key(src: DropSource) -> tuple[int, float]:
        chance = src.chance if isinstance(src.chance, (int, float)) else 0.0
        return (-src.stage, -float(chance))

    merged.sort(key=_sort_key)
    return merged[:MAX_DROPS_PER_MATERIAL]


def leaf_drop_sources(store: TwrpgDataStore, item_id: str) -> list[DropSource]:
    """缺口材料的掉落来源：优先自身掉落，其次继承兑换材料的掉落。"""
    return _drop_sources(store, item_id) or _inherited_drop_sources(store, item_id)


def plan_materials(
    store: TwrpgDataStore,
    target_id: str,
    *,
    quantity: int = 1,
    inventory: dict[str, int] | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    stock: dict[str, int] | None = None,
) -> MaterialPlan | None:
    """展开目标物品配方，扣除库存，返回缺口材料与掉落来源。

    ``stock`` 传入时复用同一份库存池（会被就地扣减），供多目标汇总避免重复计数。
    """
    if target_id not in store.items_by_id:
        return None

    quantity = max(1, int(quantity or 1))
    if stock is None:
        stock = {
            key: int(value) for key, value in (inventory or {}).items() if int(value) > 0
        }

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
        # 依赖里的配方全是魔石/硬币时停在当前物品（缺的是这件完整材料）；
        # 目标物品本身仍展开一层，方便查看它需要哪些兑换材料。
        if depth > 0 and not recipe_has_real_material(store, rows):
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
            drops=leaf_drop_sources(store, item_id) if count else [],
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


@dataclass
class GoalPlan:
    """云端物品目标表的汇总结果。"""

    goals: list[MaterialPlan] = field(default_factory=list)
    merged_needs: list[MaterialNeed] = field(default_factory=list)
    save_name: str = ""

    @property
    def count(self) -> int:
        return len(self.goals)

    @property
    def missing(self) -> list[MaterialNeed]:
        return [need for need in self.merged_needs if not need.satisfied]

    @property
    def satisfied(self) -> list[MaterialNeed]:
        return [need for need in self.merged_needs if need.satisfied]

    @property
    def missing_goals(self) -> list[MaterialPlan]:
        return [plan for plan in self.goals if plan.missing]

    @property
    def satisfied_goals(self) -> list[MaterialPlan]:
        return [plan for plan in self.goals if not plan.missing]

    @property
    def truncated(self) -> bool:
        return any(plan.truncated for plan in self.goals)

    @property
    def source_materials(self) -> list[MaterialNeed]:
        return [need for need in self.missing if need.drops][:MAX_SOURCE_MATERIALS]


def _recipe_option_ids(store: TwrpgDataStore, item_id: str) -> list[str]:
    """配方里所有可选项的 item_id（含 choose 备选）。"""
    ids: list[str] = []
    for row in store.recipes.get(item_id) or []:
        sub_id = str(row.get("sub_id") or "")
        if sub_id:
            ids.append(sub_id)
        for opt_id, _opt_num in row.get("choose") or []:
            if opt_id:
                ids.append(str(opt_id))
    return ids


def _goal_depth(
    store: TwrpgDataStore,
    item_id: str,
    selected: set[str],
    memo: dict[str, int],
    chain: frozenset[str],
) -> int:
    """目标依赖深度：越大表示越「上层」（它依赖别的目标）。"""
    if item_id in memo:
        return memo[item_id]
    if item_id in chain:
        return -1
    best = 0 if item_id in selected else -1
    next_chain = chain | {item_id}
    for sub_id in _recipe_option_ids(store, item_id):
        depth = _goal_depth(store, sub_id, selected, memo, next_chain)
        if depth >= 0:
            best = max(best, depth + 1)
    memo[item_id] = best
    return best


def order_goal_ids(store: TwrpgDataStore, goal_ids: list[str]) -> list[str]:
    """按依赖深度排序目标：底层材料先算，避免共享材料的库存被上层先吃掉。"""
    unique = list(dict.fromkeys(goal_ids))
    selected = set(unique)
    memo: dict[str, int] = {}
    ranked = [
        (max(0, _goal_depth(store, goal_id, selected, memo, frozenset())), index, goal_id)
        for index, goal_id in enumerate(unique)
    ]
    ranked.sort()
    return [goal_id for _depth, _index, goal_id in ranked]


def goal_counts(goal_ids: list[str]) -> Counter[str]:
    """目标表里同一物品出现多次即数量（与读档器一致）。"""
    return Counter(item_id for item_id in goal_ids if item_id)


def plan_goals(
    store: TwrpgDataStore,
    goal_ids: list[str],
    *,
    inventory: dict[str, int] | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    save_name: str = "",
) -> GoalPlan | None:
    """把云端目标表整体展开成缺料汇总（共享同一份库存）。"""
    counts = goal_counts(goal_ids)
    known = Counter({key: value for key, value in counts.items() if key in store.items_by_id})
    if not known:
        return None

    stock = {
        key: int(value) for key, value in (inventory or {}).items() if int(value) > 0
    }
    goals: list[MaterialPlan] = []
    merged: dict[str, MaterialNeed] = {}

    for goal_id in order_goal_ids(store, list(known)):
        plan = plan_materials(
            store,
            goal_id,
            quantity=known[goal_id],
            max_depth=max_depth,
            stock=stock,
        )
        if plan is None:
            continue
        goals.append(plan)
        for need in plan.needs:
            current = merged.get(need.item_id)
            if current is None:
                merged[need.item_id] = replace(need)
            else:
                current.required += need.required
                current.owned += need.owned
                current.missing += need.missing

    ordered = sorted(
        merged.values(),
        key=lambda need: (need.satisfied, -need.stage, -need.missing, need.name),
    )
    return GoalPlan(goals=goals, merged_needs=ordered, save_name=save_name)


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
