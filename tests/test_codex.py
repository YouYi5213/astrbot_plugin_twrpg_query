"""图鉴分类浏览逻辑测试。"""

import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.codex import (
    CODEX_CATEGORIES,
    PAGE_SIZE,
    build_selection,
    category_hint_text,
    parse_codex_args,
    resolve_category,
    resolve_stage,
    select_items,
    stage_token,
)
from astrbot_plugin_twrpg_query.data_loader import TwrpgDataStore, resolve_data_dir

_DATA_DIR = resolve_data_dir(PLUGIN_DIR)
_ICONS_DIR = os.path.join(PLUGIN_DIR, "assets", "icons")


def _load_store() -> TwrpgDataStore | None:
    if not os.path.exists(os.path.join(_DATA_DIR, "items.json")):
        return None
    store = TwrpgDataStore(_DATA_DIR, icons_dir=_ICONS_DIR)
    store.load()
    return store


def test_resolve_category_alias():
    assert resolve_category("武器") == "武器"
    assert resolve_category("武") == "武器"
    assert resolve_category("剑") == "武器"
    assert resolve_category("戒指") == "饰品"
    assert resolve_category("帽子") == "头盔"
    assert resolve_category("素材") == "材料"
    assert resolve_category("杂物") == "其他"
    assert resolve_category("所有") == "全部"
    assert resolve_category("不存在") is None


def test_resolve_stage_alias_and_digits():
    assert resolve_stage("四大") == 4
    assert resolve_stage("粉末") == 2
    assert resolve_stage("大天使") == 9
    assert resolve_stage("7") == 7
    assert resolve_stage("99") is None
    assert resolve_stage("乱写") is None


def test_stage_token_round_trip():
    for stage in range(1, 10):
        assert resolve_stage(stage_token(stage)) == stage


def test_parse_codex_args_combinations():
    assert parse_codex_args(["武器"]) == ("武器", None, "", 1)
    assert parse_codex_args(["武器", "四大"]) == ("武器", 4, "", 1)
    assert parse_codex_args(["武器", "四大", "第2页"]) == ("武器", 4, "", 2)
    assert parse_codex_args(["武器", "剑"]) == ("武器", None, "剑", 1)
    assert parse_codex_args(["四大"]) == (None, 4, "", 1)
    assert parse_codex_args(["3页"]) == (None, None, "", 3)
    assert parse_codex_args([]) == (None, None, "", 1)


def test_select_items_filters_by_category():
    store = _load_store()
    if store is None:
        return
    weapons = select_items(store, "武器")
    assert weapons
    for item_id in weapons:
        categories = store.items_by_id[item_id].get("category") or []
        assert "Equip" in categories and "Weapon" in categories

    materials = select_items(store, "材料")
    assert materials
    for item_id in materials:
        assert "Material" in (store.items_by_id[item_id].get("category") or [])

    assert len(select_items(store, "全部")) >= len(weapons)


def test_select_items_stage_and_keyword():
    store = _load_store()
    if store is None:
        return
    stage4 = select_items(store, "武器", stage=4)
    for item_id in stage4:
        assert int(store.items_by_id[item_id].get("stage") or 0) == 4

    keyword_hits = select_items(store, "武器", keyword="剑")
    assert isinstance(keyword_hits, list)


def test_build_selection_pages():
    store = _load_store()
    if store is None:
        return
    first = build_selection(store, "全部", page=1)
    assert first.total > 0
    assert len(first.item_ids) <= PAGE_SIZE
    assert first.page == 1
    if first.total > PAGE_SIZE:
        assert first.has_next
        second = build_selection(store, "全部", page=2)
        assert second.page == 2
        assert set(first.item_ids).isdisjoint(second.item_ids)
    overflow = build_selection(store, "全部", page=999)
    assert overflow.page == max(1, overflow.page_count)


def test_selection_label_contains_filters():
    store = _load_store()
    if store is None:
        return
    selection = build_selection(store, "武器", stage=4, keyword="剑")
    assert "武器" in selection.label
    assert "剑" in selection.label


def test_category_hint_text_lists_categories():
    store = _load_store()
    if store is None:
        return
    text = category_hint_text(store)
    for name in ("武器", "衣服", "头盔", "饰品", "翅膀", "材料", "其他"):
        assert name in text
    assert "世界图鉴" in text
    assert set(CODEX_CATEGORIES) >= {"武器", "材料", "全部"}
