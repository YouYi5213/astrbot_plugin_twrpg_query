"""指令前缀解析测试。"""

from __future__ import annotations

import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.data_loader import TwrpgDataStore, resolve_data_dir
from astrbot_plugin_twrpg_query.icon_utils import resolve_icons_dir
from astrbot_plugin_twrpg_query.query_parser import ITEM_CMD_RE, extract_item_query


class QueryParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = TwrpgDataStore(
            resolve_data_dir(PLUGIN_DIR),
            icons_dir=resolve_icons_dir(PLUGIN_DIR),
        )
        cls.store.load()

    def test_item_cmd_regex(self):
        self.assertTrue(ITEM_CMD_RE.match("世界 太阳石"))
        self.assertTrue(ITEM_CMD_RE.match("界太阳石"))
        self.assertTrue(ITEM_CMD_RE.match("世界世界破坏者"))
        self.assertFalse(ITEM_CMD_RE.match("/世界破坏者"))
        self.assertFalse(ITEM_CMD_RE.match("英雄 追星剑圣"))

    def test_extract_world_prefix_with_space(self):
        self.assertEqual(extract_item_query("世界 世界破坏者"), "世界破坏者")
        self.assertEqual(extract_item_query("界 世界破坏者"), "世界破坏者")

    def test_extract_world_prefix_without_space(self):
        self.assertEqual(extract_item_query("世界世界破坏者"), "世界破坏者")
        self.assertEqual(extract_item_query("界太阳石"), "太阳石")

    def test_slash_not_item_query(self):
        self.assertIsNone(extract_item_query("/世界破坏者"))
        self.assertIsNone(extract_item_query("/ 世界破坏者"))

    def test_extract_empty_usage(self):
        self.assertEqual(extract_item_query("世界"), "")

    def test_search_world_destroyer(self):
        for message in ("世界 世界破坏者", "世界世界破坏者", "界世界破坏者"):
            query = extract_item_query(message)
            assert query is not None
            matches = self.store.search(query, limit=3)
            self.assertTrue(matches, msg=message)
            self.assertEqual(self.store.item_name(matches[0]), "世界破坏者", msg=message)


if __name__ == "__main__":
    unittest.main()
