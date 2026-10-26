"""云端物品目标汇总卡片渲染测试。"""

import os
import sys
from pathlib import Path

from PIL import Image

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.card_renderer import (
    CARD_WIDTH,
    configure_cards_dir,
    get_cards_dir,
)
from astrbot_plugin_twrpg_query.data_loader import TwrpgDataStore, resolve_data_dir
from astrbot_plugin_twrpg_query.goal_renderer import (
    format_goal_caption,
    format_goal_text,
    generate_goal_card,
)
from astrbot_plugin_twrpg_query.material_planner import plan_goals

_DATA_DIR = resolve_data_dir(PLUGIN_DIR)
_ICONS_DIR = os.path.join(PLUGIN_DIR, "assets", "icons")
_CARDS_DIR = Path(__file__).resolve().parent / "runtime_cards"


def _load_store() -> TwrpgDataStore | None:
    if not os.path.exists(os.path.join(_DATA_DIR, "items.json")):
        return None
    store = TwrpgDataStore(_DATA_DIR, icons_dir=_ICONS_DIR)
    store.load()
    return store


class _CardsDir:
    """临时把卡片输出目录指向测试目录。"""

    def __enter__(self):
        self._previous = get_cards_dir()
        _CARDS_DIR.mkdir(parents=True, exist_ok=True)
        configure_cards_dir(str(_CARDS_DIR))
        return _CARDS_DIR

    def __exit__(self, exc_type, exc, tb):
        configure_cards_dir(self._previous, cleanup=False)
        for pattern in ("goals_*.png",):
            for path in _CARDS_DIR.glob(pattern):
                path.unlink(missing_ok=True)
        return False


def _goal_ids(store: TwrpgDataStore) -> list[str]:
    ids = [item_id for item_id, rows in store.recipes.items() if rows and item_id in store.items_by_id]
    return sorted(ids)[:2]


def test_goal_caption_and_text():
    store = _load_store()
    if store is None:
        return
    goals = _goal_ids(store)
    plan = plan_goals(store, goals, save_name="mxdc.txt")
    assert plan is not None
    caption = format_goal_caption(plan, save_name="mxdc")
    assert "目标缺料" in caption
    assert "mxdc" in caption
    text = format_goal_text(plan)
    assert "目标清单" in text
    if plan.missing:
        assert "合并缺口" in text


def test_generate_goal_card_writes_png():
    store = _load_store()
    if store is None:
        return
    goals = _goal_ids(store)
    plan = plan_goals(store, goals, save_name="mxdc.txt")
    assert plan is not None
    with _CardsDir() as cards_dir:
        path = generate_goal_card(plan)
        assert os.path.exists(path)
        assert Path(path).parent == cards_dir.resolve()
        with Image.open(path) as img:
            assert img.width == CARD_WIDTH
            assert img.height > 100


def test_goal_card_with_inventory_marked_satisfied():
    store = _load_store()
    if store is None:
        return
    goals = _goal_ids(store)
    plan = plan_goals(store, goals, save_name="mxdc.txt")
    assert plan is not None
    full_stock = {need.item_id: need.required + 5 for need in plan.merged_needs}
    satisfied = plan_goals(store, goals, inventory=full_stock, save_name="mxdc.txt")
    assert satisfied is not None
    assert satisfied.missing == []
    assert len(satisfied.satisfied_goals) == satisfied.count
    text = format_goal_text(satisfied)
    assert "全部目标材料已齐" in text
    with _CardsDir():
        path = generate_goal_card(satisfied)
        assert os.path.exists(path)
