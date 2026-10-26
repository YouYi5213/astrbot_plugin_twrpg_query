"""材料统计逻辑测试。"""

import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.data_loader import TwrpgDataStore, resolve_data_dir
from astrbot_plugin_twrpg_query.material_planner import (
    DEFAULT_MAX_DEPTH,
    MaterialPlan,
    goal_counts,
    inventory_from_save_lines,
    inventory_summary,
    is_exchange_material,
    leaf_drop_sources,
    order_goal_ids,
    parse_quantity,
    plan_goals,
    plan_materials,
    recipe_has_real_material,
    resolve_item_id,
)

_DATA_DIR = resolve_data_dir(PLUGIN_DIR)
_ICONS_DIR = os.path.join(PLUGIN_DIR, "assets", "icons")


def _load_store() -> TwrpgDataStore | None:
    if not os.path.exists(os.path.join(_DATA_DIR, "items.json")):
        return None
    store = TwrpgDataStore(_DATA_DIR, icons_dir=_ICONS_DIR)
    store.load()
    return store


def test_parse_quantity_variants():
    assert parse_quantity("太阳石") == ("太阳石", 1)
    assert parse_quantity("太阳石 x5") == ("太阳石", 5)
    assert parse_quantity("太阳石X3") == ("太阳石", 3)
    assert parse_quantity("太阳石 ×2") == ("太阳石", 2)
    assert parse_quantity("太阳石 *4") == ("太阳石", 4)
    assert parse_quantity("太阳石 x0") == ("太阳石 x0", 1)
    assert parse_quantity("x3") == ("x3", 1)


def test_resolve_item_id_exact_and_fuzzy():
    store = _load_store()
    if store is None:
        return
    item_id = resolve_item_id(store, "太阳石")
    assert item_id is not None
    assert store.item_name(item_id) == "太阳石"
    assert resolve_item_id(store, "") is None
    assert resolve_item_id(store, "绝对不存在的物品名 XYZ") is None


def test_inventory_from_save_lines_accumulates():
    store = _load_store()
    if store is None:
        return
    counts = inventory_from_save_lines(store, ["1. 太阳石", "2. 太阳石 x3"])
    item_id = resolve_item_id(store, "太阳石")
    assert counts[item_id] == 4
    assert inventory_summary(store, counts) == 1


def _leaf_item_id(store: TwrpgDataStore) -> str | None:
    """找一种没有配方的基础材料。"""
    for item_id in store.items_by_id:
        if store.recipes.get(item_id):
            continue
        if not store._is_queryable(store.items_by_id[item_id]):
            continue
        return item_id
    return None


def test_plan_materials_leaf_material_without_recipe():
    store = _load_store()
    if store is None:
        return
    item_id = _leaf_item_id(store)
    if item_id is None:
        return
    plan = plan_materials(store, item_id, quantity=3)
    assert isinstance(plan, MaterialPlan)
    assert plan.quantity == 3
    assert plan.needs
    total_missing = sum(need.missing for need in plan.needs)
    assert total_missing == 3


def test_plan_materials_subtracts_inventory():
    store = _load_store()
    if store is None:
        return
    item_id = _leaf_item_id(store)
    if item_id is None:
        return
    plan_full = plan_materials(store, item_id, quantity=5)
    plan_stocked = plan_materials(store, item_id, quantity=5, inventory={item_id: 2})
    missing_full = sum(need.missing for need in plan_full.needs)
    missing_stocked = sum(need.missing for need in plan_stocked.needs)
    assert missing_full == 5
    assert missing_stocked == 3


def test_plan_materials_expands_recipe_tree():
    store = _load_store()
    if store is None:
        return
    craftable = next(
        (
            item_id
            for item_id, rows in store.recipes.items()
            if rows and item_id in store.items_by_id
        ),
        None,
    )
    if craftable is None:
        return
    plan = plan_materials(store, craftable)
    assert plan is not None
    assert plan.target_id == craftable
    assert plan.needs
    assert not plan.truncated
    assert all(need.missing >= 0 for need in plan.needs)
    assert sum(need.missing for need in plan.needs) > 0


def test_plan_materials_deepest_recipe_not_truncated():
    store = _load_store()
    if store is None:
        return
    # 最深的合成链不应被默认层数截断
    for item_id in store.recipes:
        if item_id not in store.items_by_id:
            continue
        if not store.recipes.get(item_id):
            continue
        deepest = plan_materials(store, item_id)
        assert deepest is not None
        if deepest.truncated:
            raise AssertionError(f"{item_id} 在默认层数下被截断")


def test_plan_materials_depth_limit_marks_truncated():
    store = _load_store()
    if store is None:
        return
    craftable = next(
        (
            item_id
            for item_id, rows in store.recipes.items()
            if rows and item_id in store.items_by_id
        ),
        None,
    )
    if craftable is None:
        return
    plan = plan_materials(store, craftable, max_depth=0)
    assert plan is not None
    assert plan.truncated
    assert DEFAULT_MAX_DEPTH >= 11


def test_plan_materials_unknown_item_returns_none():
    store = _load_store()
    if store is None:
        return
    assert plan_materials(store, "NOT_A_REAL_ITEM_ID") is None


def test_is_exchange_material():
    assert is_exchange_material("土神魔石")
    assert is_exchange_material("公爵魔石")
    assert is_exchange_material("普瑞斯黄金硬币")
    assert is_exchange_material("普瑞斯银币")
    assert not is_exchange_material("自然之纹")
    assert not is_exchange_material("")
    assert not is_exchange_material("秘银")


class _StubStore:
    """只保留 leaf_drop_sources 需要的接口。"""

    def __init__(self) -> None:
        self.recipes = {"FULL": [{"sub_id": "STONE", "num": 2}]}
        self.drops_by_item = {"STONE": [("boss1", 0.2)]}
        self.bosses_by_id = {"boss1": {"img": ""}}
        self.items_by_id = {
            "FULL": {"name": "自然之纹"},
            "STONE": {"name": "土神魔石"},
        }

    def item_name(self, item_id: str) -> str:
        return self.items_by_id.get(item_id, {}).get("name", item_id)

    def item_stage(self, item_id: str) -> int:
        return 8

    def item_icon(self, item_id: str):
        return None

    def boss_name(self, boss_id: str) -> str:
        return "土灵战神盖亚"

    def infer_boss_stage(self, boss_id: str) -> int:
        return 8

    def _entity_icon(self, img):
        return None


def test_recipe_has_real_material():
    store = _StubStore()
    assert recipe_has_real_material(store, [{"sub_id": "STONE", "num": 2}]) is False
    assert recipe_has_real_material(store, []) is False
    assert recipe_has_real_material(store, [{"sub_id": "STONE", "num": 2, "choose": [("FULL", 1)]}]) is True


def test_leaf_drop_sources_inherits_exchange_material_drops():
    store = _StubStore()
    drops = leaf_drop_sources(store, "FULL")
    assert len(drops) == 1
    assert drops[0].boss_name == "土灵战神盖亚"
    assert drops[0].source_name == "土神魔石"
    assert float(drops[0].chance) == 0.2


def _item_id_by_name(store: TwrpgDataStore, name: str) -> str | None:
    for item_id, item in store.items_by_id.items():
        if item.get("name") == name and store._is_queryable(item):
            return item_id
    return None


def test_plan_stops_at_complete_material():
    """配方全是魔石/硬币的物品，缺料应报物品本身而不是魔石。"""
    store = _load_store()
    if store is None:
        return
    target_id = _item_id_by_name(store, "弗罗斯特先驱的衣服")
    if target_id is None:
        return
    plan = plan_materials(store, target_id)
    assert plan is not None
    names = {need.name for need in plan.needs}
    assert "自然之纹" in names
    assert "堕落灰烬" in names
    assert "土神魔石" not in names
    assert "公爵魔石" not in names


def test_plan_expands_target_exchange_material():
    """直接把完整材料当目标查询时，仍展开一层显示需要的魔石。"""
    store = _load_store()
    if store is None:
        return
    target_id = _item_id_by_name(store, "自然之纹")
    if target_id is None:
        return
    plan = plan_materials(store, target_id)
    assert plan is not None
    assert [need.name for need in plan.needs] == ["土神魔石"]
    assert plan.needs[0].missing == 2


def test_goal_counts_duplicates_as_quantity():
    counts = goal_counts(["I018", "I018", "I0B4", "", "I018"])
    assert counts == {"I018": 3, "I0B4": 1}


def test_order_goal_ids_puts_ingredient_first():
    store = _load_store()
    if store is None:
        return
    parent = _item_id_by_name(store, "弗罗斯特先驱的衣服")
    if parent is None:
        return
    child = store.recipes[parent][0]["sub_id"]
    ordered = order_goal_ids(store, [parent, child])
    assert ordered == [child, parent]


def test_plan_goals_shares_stock_between_goals():
    store = _load_store()
    if store is None:
        return
    target_id = _item_id_by_name(store, "自然之纹")
    if target_id is None:
        return
    # 同一目标出现两次 → 需要 2 份，库存只有 2 个魔石 → 合计仍缺 2 个
    plan = plan_goals(store, [target_id, target_id], inventory={"I0LY": 2})
    assert plan is not None
    assert plan.count == 1
    assert plan.goals[0].quantity == 2
    merged = {need.item_id: need for need in plan.merged_needs}
    assert merged["I0LY"].required == 4
    assert merged["I0LY"].owned == 2
    assert merged["I0LY"].missing == 2


def test_plan_goals_hides_satisfied_goals_from_missing():
    store = _load_store()
    if store is None:
        return
    target_id = _item_id_by_name(store, "自然之纹")
    if target_id is None:
        return
    plan = plan_goals(store, [target_id], inventory={"I0LY": 10})
    assert plan is not None
    assert plan.missing == []
    assert len(plan.satisfied_goals) == 1
    assert plan.missing_goals == []


def test_plan_goals_skips_unknown_ids():
    store = _load_store()
    if store is None:
        return
    target_id = _item_id_by_name(store, "自然之纹")
    if target_id is None:
        return
    assert plan_goals(store, ["NOT_REAL_ID"]) is None
    plan = plan_goals(store, ["NOT_REAL_ID", target_id])
    assert plan is not None
    assert plan.count == 1
