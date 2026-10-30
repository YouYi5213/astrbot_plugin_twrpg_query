"""魔兽房间卡片渲染测试。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

from PIL import Image

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.card_renderer import (
    configure_cards_dir,
    get_cards_dir,
)
from astrbot_plugin_twrpg_query.core import room_query as rq
from astrbot_plugin_twrpg_query.room_renderer import CARD_W, render_room_card


def _raw(no, *, status=0, watch_ready=False, players=1, slots=10,
         name="测试房", vip=False, pwd=False, level=None):
    return {
        "show_id": no,
        "room_guid": f"guid-{no}",
        "room_name": name,
        "real_player_number": players,
        "total_slots": slots,
        "room_status": status,
        "watch_ready": watch_ready,
        "enter_limit_map_lvl": level or {},
        "need_password": pwd,
        "room_flag": 2 if vip else 0,
        "mode_name": "不限",
    }


def _snapshot(rooms, total=None, logo=""):
    return rq.RoomSnapshot(
        map_id=2310, map_name="世界RPG",
        total=len(rooms) if total is None else total,
        now=0, rooms=rooms, logo=logo,
    )


class RoomRendererTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._previous = get_cards_dir()
        configure_cards_dir(self._tmp.name)

    def tearDown(self):
        configure_cards_dir(self._previous, cleanup=False)
        self._tmp.cleanup()

    def test_render_card(self):
        snap = _snapshot([
            rq._to_room(_raw(1001, players=3, name="牛火12")),
            rq._to_room(_raw(1002, players=1, name="世界RPG", pwd=True)),
            rq._to_room(_raw(1003, players=4, name="VIP房", vip=True)),
            rq._to_room(_raw(1004, status=6, watch_ready=True)),
        ])
        path = render_room_card(snap)
        self.assertTrue(os.path.exists(path))
        with Image.open(path) as img:
            self.assertEqual(img.width, CARD_W)
            self.assertGreater(img.height, 100)
            self.assertEqual(img.mode, "RGB")

    def test_render_include_playing(self):
        snap = _snapshot([
            rq._to_room(_raw(1001)),
            rq._to_room(_raw(1002, status=6, watch_ready=False)),
        ])
        path = render_room_card(snap, include_playing=True)
        with Image.open(path) as img:
            self.assertGreater(img.height, 100)

    def test_render_include_watching(self):
        snap = _snapshot([
            rq._to_room(_raw(1001)),
            rq._to_room(_raw(1002, status=6, watch_ready=True)),
        ])
        path = render_room_card(snap, include_watching=True)
        self.assertTrue(os.path.exists(path))

    def test_render_empty(self):
        path = render_room_card(_snapshot([], total=5))
        self.assertTrue(os.path.exists(path))

    def test_missing_logo_does_not_fail(self):
        snap = _snapshot([rq._to_room(_raw(1001))], logo="")
        path = render_room_card(snap)
        self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
