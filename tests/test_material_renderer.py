"""材料统计卡片与图鉴卡片渲染测试。"""

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
from astrbot_plugin_twrpg_query.codex import build_selection
from astrbot_plugin_twrpg_query.codex_renderer import (
    build_codex_tiles,
    format_codex_text,
    render_codex,
)
from astrbot_plugin_twrpg_query.data_loader import TwrpgDataStore, resolve_data_dir
from astrbot_plugin_twrpg_query.material_planner import plan_materials, resolve_item_id
from astrbot_plugin_twrpg_query.material_renderer import (
    format_material_caption,
    format_material_text,
    generate_material_card,
)

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
        for pattern in ("material_*.png", "inv_*.png", "inventory_*.png", "grid_*.png"):
            for path in _CARDS_DIR.glob(pattern):
                path.unlink(missing_ok=True)
        return False


def _craftable_item_id(store: TwrpgDataStore) -> str | None:
    for item_id, rows in store.recipes.items():
        if rows and item_id in store.items_by_id:
            return item_id
    return None


def test_material_caption_without_inventory():
    store = _load_store()
    if store is None:
        return
    item_id = _craftable_item_id(store)
    if item_id is None:
        return
    plan = plan_materials(store, item_id)
    assert plan is not None
    caption = format_material_caption(plan)
    assert "材料统计" in caption
    assert "未读取到存档库存" in caption

    caption_saved = format_material_caption(plan, save_name="mxdc")
    assert "库存对比：mxdc" in caption_saved


def test_material_text_fallback_lists_sections():
    store = _load_store()
    if store is None:
        return
    item_id = _craftable_item_id(store)
    if item_id is None:
        return
    plan = plan_materials(store, item_id)
    assert plan is not None
    text = format_material_text(plan)
    assert "材料统计" in text
    if plan.missing:
        assert "缺口材料" in text


def test_generate_material_card_writes_png():
    store = _load_store()
    if store is None:
        return
    item_id = _craftable_item_id(store)
    if item_id is None:
        return
    plan = plan_materials(store, item_id)
    assert plan is not None
    with _CardsDir() as cards_dir:
        path = generate_material_card(plan)
        assert os.path.exists(path)
        assert Path(path).parent == cards_dir.resolve()
        with Image.open(path) as img:
            assert img.width == CARD_WIDTH
            assert img.height > 100


def test_build_codex_tiles_matches_items():
    store = _load_store()
    if store is None:
        return
    selection = build_selection(store, "武器")
    tiles = build_codex_tiles(store, selection.item_ids)
    assert len(tiles) == len(selection.item_ids)
    assert all(tile.name for tile in tiles)


def test_render_codex_produces_image_and_caption():
    store = _load_store()
    if store is None:
        return
    selection = build_selection(store, "武器")
    if selection.total <= 0:
        return
    with _CardsDir() as cards_dir:
        caption, image_path = render_codex(store, selection)
        assert "图鉴" in caption
        assert image_path is not None
        assert os.path.exists(image_path)
        assert Path(image_path).parent == cards_dir.resolve()


def test_format_codex_text_lists_entries():
    store = _load_store()
    if store is None:
        return
    selection = build_selection(store, "材料")
    if selection.total <= 0:
        return
    text = format_codex_text(store, selection)
    assert "图鉴" in text
    assert str(selection.total) in text
