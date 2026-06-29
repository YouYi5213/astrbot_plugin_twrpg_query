"""BOSS 掉落查询测试。"""

from __future__ import annotations

import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.boss_aliases import BOSS_ALIAS_TO_ID
from astrbot_plugin_twrpg_query.card_renderer import generate_boss_card
from astrbot_plugin_twrpg_query.data_loader import TwrpgDataStore, normalize_query, resolve_data_dir
from astrbot_plugin_twrpg_query.icon_utils import resolve_icons_dir
from astrbot_plugin_twrpg_query.query_parser import BOSS_CMD_RE, extract_boss_query, extract_item_query


class BossQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = TwrpgDataStore(
            resolve_data_dir(PLUGIN_DIR),
            icons_dir=resolve_icons_dir(PLUGIN_DIR),
        )
        cls.store.load()

    def test_boss_cmd_parser(self):
        self.assertTrue(BOSS_CMD_RE.match("世界BOSS 盖亚"))
        self.assertTrue(BOSS_CMD_RE.match("世界BOSS盖亚"))
        self.assertEqual(extract_boss_query("世界BOSS 土灵战神盖亚"), "土灵战神盖亚")
        self.assertEqual(extract_boss_query("世界BOSS盖亚"), "盖亚")
        self.assertIsNone(extract_item_query("世界BOSS 盖亚"))
        self.assertEqual(extract_item_query("世界 太阳石"), "太阳石")

    def test_search_boss_by_name_and_alias(self):
        matches = self.store.search_boss("土灵战神盖亚", limit=3)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0], "h09B")

        for alias in ("盖亚", "土"):
            alias_matches = self.store.search_boss(alias, limit=3)
            self.assertIn("h09B", alias_matches)

        for alias, boss_id in BOSS_ALIAS_TO_ID.items():
            exact = self.store.search_boss(alias, limit=5)
            self.assertIn(
                boss_id,
                exact,
                msg=f"alias {alias} -> {boss_id}, got {exact}",
            )

    def test_build_gaia_boss_display(self):
        display = self.store.build_boss_display("h09B")
        assert display is not None
        self.assertEqual(display.name, "土灵战神盖亚")
        self.assertEqual(display.stage_label, "[爵土马判]")
        drop_names = [entry.item_name for entry in display.drops]
        self.assertIn("土神魔石", drop_names)
        self.assertIn("堕落灰烬", drop_names)
        self.assertIn("自然精粹", drop_names)
        self.assertTrue(any("生命之袍" in name for name in drop_names))
        for entry in display.drops:
            self.assertTrue(entry.icon and os.path.exists(entry.icon))

        path = generate_boss_card(display)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 2000)
        os.remove(path)


if __name__ == "__main__":
    unittest.main()
