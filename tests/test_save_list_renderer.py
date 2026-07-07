"""云存档列表图片渲染测试。"""

import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.save_list_renderer import (
    PRIMARY_MARK,
    SaveListRow,
    generate_save_list_image,
    render_save_list,
)


def test_render_save_list():
    names = [f"save{i}.txt" for i in range(1, 10)]
    caption, path = render_save_list("atong", names, primary_name="save3.txt")
    assert "共 9 个存档" in caption
    assert PRIMARY_MARK in caption
    assert os.path.exists(path)

    from PIL import Image

    with Image.open(path) as img:
        assert img.width == 640
        assert img.height > 100


def test_generate_save_list_image_many_columns():
    entries = [
        SaveListRow(index=i, display_name=f"slot{i}", is_primary=i == 5)
        for i in range(1, 40)
    ]
    path = generate_save_list_image(username="atong", entries=entries)
    assert os.path.exists(path)

    from PIL import Image

    with Image.open(path) as img:
        assert img.width == 640
