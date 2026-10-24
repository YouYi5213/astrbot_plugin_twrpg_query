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
    inventory_from_save_lines,
    inventory_summary,
    parse_quantity,
    plan_materials,
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
