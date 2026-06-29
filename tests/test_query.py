from __future__ import annotations

import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.card_renderer import (
    _estimate_hero_height,
    generate_hero_card,
    generate_item_card,
    generate_skill_card,
)
from astrbot_plugin_twrpg_query.data_loader import (
    TwrpgDataStore,
    format_skill_hotkey,
    normalize_query,
    normalize_skill_name,
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

    def test_limit_heroes_skip_missing_icons_i0a5(self):
        display = self.store.build_display("I0A5")
        assert display is not None
        self.assertEqual(len(display.limit_heroes), 21)
        for hero in display.limit_heroes:
            self.assertTrue(hero.icon and os.path.exists(hero.icon))
            self.assertNotEqual(hero.name, hero.id)

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
        self.assertTrue(
            display.recipe[0].entries[0].icon
            and os.path.exists(display.recipe[0].entries[0].icon)
        )
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

    def test_recipe_choice_group_i01m(self):
        display = self.store.build_display("I01M")
        assert display is not None
        choice_lines = [line for line in display.recipe if line.is_choice]
        self.assertEqual(len(choice_lines), 1)
        choice = choice_lines[0]
        self.assertEqual(len(choice.entries), 2)
        names = {entry.name for entry in choice.entries}
        self.assertIn("自然精粹", names)
        self.assertIn("自然之纹", names)
        for entry in choice.entries:
            self.assertTrue(entry.icon and os.path.exists(entry.icon))
        path = generate_item_card(display)
        self.assertTrue(os.path.exists(path))
        os.remove(path)

    def test_normalize_query(self):
        self.assertEqual(normalize_query("洞悉·真理之瞳"), normalize_query("洞悉 真理之瞳"))

    def test_duplicate_id_prefers_equipment_over_old_quest(self):
        self.assertEqual(self.store.item_name("I024"), "神煞者印章")
        self.assertEqual(self.store.item_name("I00Z"), "阿瓦隆护灵之翼")

    def test_i0lp_crafts_into_shows_real_item_names(self):
        display = self.store.build_display("I0LP")
        assert display is not None
        craft_names = {entry.name for entry in display.crafts_into}
        self.assertIn("神煞者印章", craft_names)
        self.assertNotIn("@Old Quest", craft_names)

    def test_search_hero_by_name(self):
        matches = self.store.search_hero("追星剑圣")
        self.assertEqual(matches[0], "H001")

    def test_search_hero_by_character(self):
        matches = self.store.search_hero("路易斯")
        self.assertIn("H001", matches)

    def test_build_hero_display(self):
        display = self.store.build_hero_display("H001")
        self.assertIsNotNone(display)
        assert display is not None
        self.assertEqual(display.name, "追星剑圣")
        self.assertIn("路易斯", display.character_name)
        self.assertTrue(display.icon and os.path.exists(display.icon))
        self.assertGreater(len(display.skills), 0)
        for skill in display.skills:
            self.assertTrue(skill.name)
            self.assertTrue(skill.icon and os.path.exists(skill.icon))
        path = generate_hero_card(display)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 3000)
        os.remove(path)

    def test_search_skill_by_name(self):
        matches = self.store.search_skill("升龙击")
        self.assertTrue(matches)
        display = self.store.build_skill_display(matches[0])
        assert display is not None
        self.assertIn("升龙击", display.name)
        self.assertEqual(display.hero_id, "H001")

    def test_generate_skill_card(self):
        matches = self.store.search_skill("升龙击")
        display = self.store.build_skill_display(matches[0])
        assert display is not None
        path = generate_skill_card(display)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 2000)
        os.remove(path)

    def test_skill_hotkey_display(self):
        self.assertEqual(normalize_skill_name("圣光裂空(Q)"), "圣光裂空")
        self.assertEqual(format_skill_hotkey("[ Q ]"), "[Q]")
        self.assertEqual(format_skill_hotkey("[ Q - W ]"), "[Q-W]")

        display = self.store.build_hero_display("H003")
        assert display is not None
        skill = next(s for s in display.skills if s.name == "圣光裂空")
        self.assertEqual(skill.name, "圣光裂空")
        self.assertEqual(skill.hotkey, "[Q]")
        self.assertNotIn("(Q)", skill.name)

        skill_display = self.store.build_skill_display(f"{display.id}:A02M")
        assert skill_display is not None
        self.assertEqual(skill_display.name, "圣光裂空")
        self.assertEqual(skill_display.hotkey, "[Q]")

    def test_hero_card_height_covers_content(self):
        from PIL import Image, ImageDraw

        hero = self.store.build_hero_display("H003")
        assert hero is not None
        measure = ImageDraw.Draw(Image.new("RGB", (640, 200)))
        estimated = _estimate_hero_height(measure, hero)

        tracked: list[int] = []
        import astrbot_plugin_twrpg_query.card_renderer as card_mod

        original = card_mod._draw_skill_block

        def tracking_block(card, draw, y, skill, panel_width):
            result = original(card, draw, y, skill, panel_width)
            tracked.append(result)
            return result

        card_mod._draw_skill_block = tracking_block
        try:
            path = generate_hero_card(hero)
        finally:
            card_mod._draw_skill_block = original

        img = Image.open(path)
        self.assertGreaterEqual(img.size[1], tracked[-1])
        self.assertGreaterEqual(img.size[1], estimated)
        img.close()
        os.remove(path)


if __name__ == "__main__":
    unittest.main()
