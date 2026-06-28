from __future__ import annotations

import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.card_renderer import generate_item_card
from astrbot_plugin_twrpg_query.data_loader import (
    TwrpgDataStore,
    normalize_query,
    resolve_data_dir,
    stage_label,
)
from astrbot_plugin_twrpg_query.icon_utils import resolve_icons_dir


class TwrpgQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = TwrpgDataStore(
            resolve_data_dir(PLUGIN_DIR),
            icons_dir=resolve_icons_dir(PLUGIN_DIR),
        )
        cls.store.load()

    def test_load_items(self):
        self.assertGreater(len(self.store.items_by_id), 1000)

    def test_search_by_name(self):
        matches = self.store.search("洞悉真理之瞳")
        self.assertEqual(matches[0], "I0ET")

    def test_search_by_id(self):
        matches = self.store.search("I0ET")
        self.assertEqual(matches[0], "I0ET")

    def test_build_display_sections(self):
        display = self.store.build_display("I0ET")
        self.assertIsNotNone(display)
        assert display is not None
        self.assertEqual(display.id, "I0ET")
        self.assertGreater(len(display.recipe), 0)

    def test_limit_heroes_and_exclusives_i026(self):
        display = self.store.build_display("I026")
        assert display is not None
        self.assertEqual(stage_label(9), "[大天使]")
        self.assertEqual(display.stage_label, "[大天使]")
        hero_ids = {hero.id for hero in display.limit_heroes}
        self.assertIn("H065", hero_ids)
        self.assertIn("H04Q", hero_ids)
        for hero in display.limit_heroes:
            self.assertTrue(hero.icon and os.path.exists(hero.icon))
        self.assertEqual(len(display.exclusives), 1)
        ex = display.exclusives[0]
        self.assertEqual(ex.hero_id, "H04Q")
        self.assertIn("着手成春", ex.description)
        self.assertIn("危险爆破", ex.description)
        self.assertTrue(ex.icon and os.path.exists(ex.icon))
        path = generate_item_card(display)
        self.assertTrue(os.path.exists(path))
        os.remove(path)

    def test_boss_drop_only(self):
        display = self.store.build_display("I023")
        assert display is not None
        self.assertEqual(len(display.boss_drops), 1)
        self.assertGreater(display.boss_drops[0].chance, 0)

    def test_generate_card(self):
        display = self.store.build_display("I0ET")
        assert display is not None
        path = generate_item_card(display)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 1000)
        os.remove(path)

    def test_srbd_passive_and_icons(self):
        display = self.store.build_display("srbd")
        assert display is not None
        self.assertIn("15% 额外伤害", display.passive)
        self.assertIn("18.75", display.passive)
        self.assertTrue(display.icon and os.path.exists(display.icon))
        self.assertGreater(len(display.recipe), 0)
        self.assertTrue(display.recipe[0].icon and os.path.exists(display.recipe[0].icon))
        self.assertGreater(len(display.crafts_into), 0)
        self.assertTrue(
            display.crafts_into[0].icon and os.path.exists(display.crafts_into[0].icon)
        )
        self.assertEqual(len(display.boss_drops), 1)
        self.assertTrue(
            display.boss_drops[0].icon and os.path.exists(display.boss_drops[0].icon)
        )
        path = generate_item_card(display)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 5000)
        os.remove(path)

    def test_normalize_query(self):
        self.assertEqual(normalize_query("洞悉·真理之瞳"), normalize_query("洞悉 真理之瞳"))


if __name__ == "__main__":
    unittest.main()
