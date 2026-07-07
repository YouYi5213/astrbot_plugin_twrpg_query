"""库存网格渲染测试。"""

import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.data_loader import TwrpgDataStore, resolve_data_dir
from astrbot_plugin_twrpg_query.inventory_renderer import (
    BACKPACK_LAYOUT,
    CARRIED_LAYOUT,
    build_inventory_tiles,
    format_save_display_name,
    generate_inventory_grid,
)

_DATA_DIR = resolve_data_dir(PLUGIN_DIR)


def test_format_save_display_name():
    assert format_save_display_name("mxdc.txt") == "mxdc"
    assert format_save_display_name("save") == "save"


def test_generate_inventory_grid_backpack():
    store = TwrpgDataStore(
        _DATA_DIR, icons_dir=os.path.join(PLUGIN_DIR, "assets", "icons")
    )
    if not os.path.exists(os.path.join(_DATA_DIR, "items.json")):
        return
    store.load()
    tiles = build_inventory_tiles(["1. 太阳石", "普瑞斯银币 x10"], store, limit=10)
    path = generate_inventory_grid(
        save_display_name="mxdc",
        section_label="背包",
        tiles=tiles,
        total_count=2,
        layout=BACKPACK_LAYOUT,
    )
    assert os.path.exists(path)


def test_generate_inventory_grid_carried():
    store = TwrpgDataStore(
        _DATA_DIR, icons_dir=os.path.join(PLUGIN_DIR, "assets", "icons")
    )
    if not os.path.exists(os.path.join(_DATA_DIR, "items.json")):
        return
    store.load()
    tiles = build_inventory_tiles(["1. 太阳石"], store, limit=6)
    path = generate_inventory_grid(
        save_display_name="mxdc",
        section_label="携带",
        tiles=tiles,
        total_count=1,
        layout=CARRIED_LAYOUT,
    )
    assert os.path.exists(path)

    from PIL import Image

    with Image.open(path) as img:
        assert img.width == CARRIED_LAYOUT.card_width
