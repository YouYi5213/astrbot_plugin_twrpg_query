"""世界房间查询（core/room_query.py）测试。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest

import httpx

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from astrbot_plugin_twrpg_query.core import room_query as rq
from astrbot_plugin_twrpg_query.query_parser import (
    ROOM_CMD_RE,
    extract_room_query,
    is_tool_command,
)


def _raw(
    no,
    *,
    status=0,
    watch_ready=False,
    players=1,
    slots=10,
    level=None,
    name="测试房",
    pwd=False,
):
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
    }


def _client(handler):
    return httpx.AsyncClient(
        base_url=rq.MAP_API, transport=httpx.MockTransport(handler)
    )


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_path(self):
        path = rq.resolve_token_path(self.dir)
        self.assertEqual(path, os.path.join(self.dir, "kk_room", "token.json"))

    def test_override_path(self):
        self.assertEqual(
            rq.resolve_token_path(self.dir, "/tmp/x.json"), "/tmp/x.json"
        )

    def test_missing_token(self):
        with self.assertRaises(rq.RoomQueryError):
            rq.load_token(rq.resolve_token_path(self.dir))

    def test_invalid_token_shape(self):
        path = os.path.join(self.dir, "token.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"token": "telpwd-abc"}, f)
        with self.assertRaises(rq.RoomQueryError):
            rq.load_token(path)

    def test_valid_token(self):
        path = os.path.join(self.dir, "token.json")
        token = "a" * 96
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"token": token, "ts": 1, "source": "test"}, f)
        self.assertEqual(rq.load_token(path), token)


class ParserTests(unittest.TestCase):
    def test_room_command_regex(self):
        self.assertTrue(ROOM_CMD_RE.match("魔兽房间"))
        self.assertTrue(ROOM_CMD_RE.match("魔兽房间 守护小天使"))
        self.assertFalse(ROOM_CMD_RE.match("世界房间"))
        self.assertFalse(ROOM_CMD_RE.match("魔兽 房间"))

    def test_extract_room_query(self):
        self.assertEqual(extract_room_query("魔兽房间"), "")
        self.assertEqual(extract_room_query("魔兽房间 全部"), "全部")
        self.assertEqual(extract_room_query("魔兽房间 守护小天使"), "守护小天使")
        self.assertIsNone(extract_room_query("世界房间"))

    def test_tool_command_lets_item_handler_yield(self):
        self.assertTrue(is_tool_command("魔兽房间 2310"))
        self.assertTrue(is_tool_command("/魔兽房间"))
        self.assertFalse(is_tool_command("世界 房间"))

    def test_parse_default(self):
        self.assertEqual(rq.parse_room_args(""), ("", False, False))

    def test_parse_map_id(self):
        self.assertEqual(rq.parse_room_args("2310"), ("2310", False, False))

    def test_parse_map_name(self):
        self.assertEqual(rq.parse_room_args("世界RPG"),
                         ("世界RPG", False, False))
        self.assertEqual(rq.parse_room_args("守护小天使"),
                         ("守护小天使", False, False))

    def test_parse_all(self):
        self.assertEqual(rq.parse_room_args("全部"), ("", True, False))
        self.assertEqual(rq.parse_room_args("世界RPG 全部"),
                         ("世界RPG", True, False))

    def test_parse_joinable_resets(self):
        self.assertEqual(rq.parse_room_args("全部 可加入"),
                         ("", False, False))

    def test_parse_watch_toggle(self):
        self.assertEqual(rq.parse_room_args("观战"), ("", False, True))
        self.assertEqual(rq.parse_room_args("世界RPG 全部 观战"),
                         ("世界RPG", True, True))
        self.assertEqual(rq.parse_room_args("不观战"), ("", False, False))
        # 配置默认显示时，命令里可以用「不观战」临时关掉
        self.assertEqual(rq.parse_room_args("", True), ("", False, True))
        self.assertEqual(rq.parse_room_args("不观战", True),
                         ("", False, False))


class AttrTests(unittest.TestCase):
    def test_attr_mapping(self):
        self.assertEqual(rq.room_attr({"room_status": 0}), "-")
        self.assertEqual(
            rq.room_attr({"room_status": 6, "watch_ready": True}), "观战"
        )
        self.assertEqual(
            rq.room_attr({"room_status": 6, "watch_ready": False}), "游戏中"
        )

    def test_attr_label(self):
        self.assertEqual(rq.attr_label("-"), "可加入")
        self.assertEqual(rq.attr_label("观战"), "观战")
        self.assertEqual(rq.attr_label("游戏中"), "游戏中")


class FormatTests(unittest.TestCase):
    def _snap(self):
        return rq.RoomSnapshot(
            map_id=2310,
            map_name="世界RPG",
            total=3,
            now=0,
            rooms=[
                rq._to_room(_raw(1001, players=3)),
                rq._to_room(_raw(1002, status=6, watch_ready=True)),
                rq._to_room(_raw(1003, status=6, watch_ready=False)),
            ],
        )

    def test_default_hides_watching_and_playing(self):
        text = rq.format_snapshot(self._snap())
        self.assertIn("1001", text)
        self.assertNotIn("1002", text)
        self.assertNotIn("1003", text)
        self.assertIn("观战 1 间已隐藏", text)

    def test_include_playing_still_hides_watching(self):
        text = rq.format_snapshot(self._snap(), include_playing=True)
        self.assertIn("1001", text)
        self.assertNotIn("1002", text)
        self.assertIn("1003", text)

    def test_include_watching_shows_watch_rooms(self):
        text = rq.format_snapshot(self._snap(), include_watching=True)
        self.assertIn("1001", text)
        self.assertIn("1002", text)
        self.assertNotIn("1003", text)
        self.assertIn("观战 1 间", text)

    def test_max_30_rows(self):
        snap = rq.RoomSnapshot(
            2310, "世界RPG", 35, 0,
            [rq._to_room(_raw(1000 + i)) for i in range(35)],
        )
        text = rq.format_snapshot(snap)
        rows = [line for line in text.splitlines() if line.startswith("10")]
        self.assertEqual(len(rows), 30)
        self.assertIn("还有 5 间", text)

    def test_empty_room_list(self):
        snap = rq.RoomSnapshot(2310, "世界RPG", 0, 0, [])
        self.assertIn("没有在线房间", rq.format_snapshot(snap))

    def test_level_always_shown(self):
        snap = rq.RoomSnapshot(
            2310, "世界RPG", 1, 0, [rq._to_room(_raw(1001))]
        )
        self.assertIn("[等级-]", rq.format_snapshot(snap))

        limited = rq.RoomSnapshot(
            2310, "世界RPG", 1, 0,
            [rq._to_room(_raw(1001, level={"min_map_lvl": 5}))],
        )
        self.assertIn("[等级≥5]", rq.format_snapshot(limited))

    def test_password_rooms_sorted_last(self):
        snap = rq.RoomSnapshot(
            2310, "世界RPG", 2, 0,
            [
                rq._to_room(_raw(1001, players=9, name="密码房", pwd=True)),
                rq._to_room(_raw(1002, players=1, name="普通房")),
            ],
        )
        for text in (rq.format_snapshot(snap),
                     rq.format_snapshot(snap, include_playing=True)):
            self.assertLess(text.index("1002"), text.index("1001"))

    def test_sort_by_players_desc(self):
        snap = rq.RoomSnapshot(
            2310, "世界RPG", 2, 0,
            [
                rq._to_room(_raw(1001, players=1)),
                rq._to_room(_raw(1002, players=8)),
            ],
        )
        text = rq.format_snapshot(snap)
        self.assertLess(text.index("1002"), text.index("1001"))


class FetchTests(unittest.TestCase):
    def test_pagination_and_dedupe(self):
        pages = {
            0: ([_raw(1), _raw(2)], 3),
            2: ([_raw(3)], 3),
        }

        def handler(request):
            start = int(request.url.params.get("start", "0"))
            rooms, count = pages.get(start, ([], 3))
            return httpx.Response(
                200,
                json={"status": 200,
                      "data": {"preparing": rooms, "count": count, "now": 1}},
                request=request,
            )

        async def run():
            async with _client(handler) as client:
                return await rq.fetch_snapshot(client, "a" * 96, 2310, "世界RPG")

        snap = asyncio.run(run())
        self.assertEqual(snap.total, 3)
        self.assertEqual(len(snap.rooms), 3)

    def test_duplicate_page_does_not_stop_early(self):
        # 房间顺序漂移时，第 2 页可能整页都是第 1 页出现过的房间。
        # 旧逻辑会在这里 break，漏掉后面的新房间。
        pages = {
            0: [_raw(1), _raw(2)],
            2: [_raw(2), _raw(3)],
        }

        def handler(request):
            start = int(request.url.params.get("start", "0"))
            rooms = pages.get(start, [])
            return httpx.Response(
                200,
                json={"status": 200,
                      "data": {"preparing": rooms, "count": 4, "now": 1}},
                request=request,
            )

        async def run():
            async with _client(handler) as client:
                return await rq.fetch_snapshot(client, "a" * 96, 2310)

        snap = asyncio.run(run())
        self.assertEqual(sorted(r.no for r in snap.rooms), ["1", "2", "3"])

    def test_403_raises_token_expired(self):
        def handler(request):
            return httpx.Response(
                403,
                json={"status": 40301, "message": "invalid token"},
                request=request,
            )

        async def run():
            async with _client(handler) as client:
                await rq.fetch_snapshot(client, "a" * 96, 2310)

        with self.assertRaises(rq.TokenExpired):
            asyncio.run(run())

    def test_snapshot_keeps_map_logo(self):
        def handler(request):
            return httpx.Response(
                200,
                json={"status": 200, "data": {
                    "preparing": [{
                        **_raw(1),
                        "url_logo": "https://example.com/logo.png",
                    }],
                    "count": 1, "now": 1,
                }},
                request=request,
            )

        async def run():
            async with _client(handler) as client:
                return await rq.fetch_snapshot(client, "a" * 96, 2310)

        snap = asyncio.run(run())
        self.assertEqual(snap.logo, "https://example.com/logo.png")

    def test_snapshot_falls_back_to_detail_logo(self):
        def handler(request):
            if request.url.path == "/api/v3/map/detail":
                return httpx.Response(
                    200,
                    json={"status": 200,
                          "data": {"logo": "https://example.com/d.png"}},
                    request=request,
                )
            return httpx.Response(
                200,
                json={"status": 200,
                      "data": {"preparing": [], "count": 0, "now": 1}},
                request=request,
            )

        async def run():
            async with _client(handler) as client:
                return await rq.fetch_snapshot(client, "a" * 96, 2310)

        self.assertEqual(asyncio.run(run()).logo,
                         "https://example.com/d.png")

    def test_resolve_map_by_name(self):
        index = {197239: "守护小天使"}

        async def run():
            async with _client(
                lambda r: httpx.Response(200, json={}, request=r)
            ) as client:
                return await rq.resolve_map(client, "守护小天使", index)

        self.assertEqual(asyncio.run(run()), (197239, "守护小天使"))

    def test_resolve_map_prefers_exact_name(self):
        index = {2310: "世界RPG", 197239: "世界RPG·测试"}

        async def run():
            async with _client(
                lambda r: httpx.Response(200, json={}, request=r)
            ) as client:
                return await rq.resolve_map(client, "世界RPG", index)

        self.assertEqual(asyncio.run(run()), (2310, "世界RPG"))

    def test_resolve_map_ambiguous_lists_candidates(self):
        index = {100: "守护小天使", 200: "守护小天使·外传"}

        async def run():
            async with _client(
                lambda r: httpx.Response(200, json={}, request=r)
            ) as client:
                await rq.resolve_map(client, "守护", index)

        with self.assertRaises(rq.AmbiguousMap) as ctx:
            asyncio.run(run())
        message = str(ctx.exception)
        self.assertIn("守护小天使", message)
        self.assertIn("ID 100", message)
        self.assertIn("ID 200", message)
        self.assertIn("魔兽房间 <ID>", message)

    def test_resolve_map_not_found(self):
        index = {2310: "世界RPG"}

        async def run():
            async with _client(
                lambda r: httpx.Response(200, json={}, request=r)
            ) as client:
                await rq.resolve_map(client, "守护小天使", index)

        with self.assertRaises(rq.RoomQueryError):
            asyncio.run(run())

    def test_resolve_map_without_index_prompts_update(self):
        async def run():
            async with _client(
                lambda r: httpx.Response(200, json={}, request=r)
            ) as client:
                await rq.resolve_map(client, "世界RPG", {})

        with self.assertRaises(rq.RoomQueryError) as ctx:
            asyncio.run(run())
        self.assertIn("更新目录", str(ctx.exception))

    def test_resolve_map_by_id(self):
        async def run():
            async with _client(
                lambda r: httpx.Response(200, json={}, request=r)
            ) as client:
                return await rq.resolve_map(client, "2310")

        # 数字 ID 直接返回，地图名由随后的 search_by_map_ids 补齐
        self.assertEqual(asyncio.run(run()), (2310, ""))


class MapIndexTests(unittest.TestCase):
    def test_index_command(self):
        self.assertTrue(rq.is_index_command("更新目录"))
        self.assertTrue(rq.is_index_command(" 刷新目录 "))
        self.assertTrue(rq.is_index_command("更新地图"))
        self.assertFalse(rq.is_index_command("更新"))

    def test_get_index_is_offline_when_missing(self):
        # 没有缓存时不能自己联网；直接返回空表
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(asyncio.run(rq.get_map_index(tmp)), {})

    def test_search_skips_test_maps(self):
        index = {1: "世界RPG·测试", 2: "世界RPG", 3: "测试图"}
        self.assertEqual(
            [mid for mid, _ in rq.search_map_index(index, "世界RPG")],
            [2],
        )
        self.assertEqual(rq.search_map_index(index, "测试"), [])

    def test_search_ranking(self):
        index = {1: "守护", 2: "守护者", 3: "我的守护", 4: "无关"}
        self.assertEqual(
            [mid for mid, _ in rq.search_map_index(index, "守护")],
            [1, 2, 3],
        )
        self.assertEqual(rq.search_map_index(index, "无关")[0][0], 4)
        self.assertEqual(rq.search_map_index(index, "不存在"), [])

    def test_search_ignores_spaces_and_case(self):
        index = {2310: "World RPG"}
        self.assertEqual(rq.search_map_index(index, "worldrpg")[0][0], 2310)
        self.assertEqual(rq.search_map_index(index, "World RPG")[0][0], 2310)

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = rq.map_index_path(tmp)
            rq._save_map_index(path, {2310: "世界RPG"})
            ts, maps = rq._load_map_index(path)
            self.assertGreater(ts, 0)
            self.assertEqual(maps, {2310: "世界RPG"})

    def test_build_index_skips_test_maps(self):
        def handler(request):
            if request.url.path == "/api/v3/map/tabs":
                return httpx.Response(
                    200, json={"status": 200, "data": [{"id": 1}]},
                    request=request,
                )
            if request.url.path == "/api/v3/map/detail":
                return httpx.Response(
                    200,
                    json={"status": 200, "data": {"mapName": "正常图"}},
                    request=request,
                )
            return httpx.Response(
                200,
                json={"status": 200, "data": {
                    "rows": [
                        {"mapId": 1, "mapName": "正常图", "testMap": False},
                        {"mapId": 2, "mapName": "世界RPG·测试", "testMap": False},
                        {"mapId": 3, "mapName": "测试服图", "testMap": True},
                    ],
                    "total": 3,
                }},
                request=request,
            )

        async def run():
            async with _client(handler) as client:
                return await rq.build_map_index(client)

        maps = asyncio.run(run())
        self.assertEqual(maps.get(1), "正常图")
        self.assertNotIn(2, maps)
        self.assertNotIn(3, maps)

    def test_build_index_paginates(self):
        def handler(request):
            if request.url.path == "/api/v3/map/tabs":
                return httpx.Response(
                    200,
                    json={"status": 200, "data": [{"id": 1}, {"id": 2}]},
                    request=request,
                )
            if request.url.path == "/api/v3/map/detail":
                mid = int(request.url.params.get("mapId", "0"))
                return httpx.Response(
                    200,
                    json={"status": 200,
                          "data": {"mapName": f"seed-{mid}"}},
                    request=request,
                )
            tab = int(request.url.params.get("tabId", "0"))
            page = int(request.url.params.get("page", "1"))
            rows, total = {
                (1, 1): ([{"mapId": 1, "mapName": "A"},
                          {"mapId": 2, "mapName": "B"}], 501),
                (1, 2): ([{"mapId": 3, "mapName": "C"}], 501),
                (2, 1): ([{"mapId": 4, "mapName": "D"}], 1),
            }.get((tab, page), ([], 0))
            return httpx.Response(
                200,
                json={"status": 200,
                      "data": {"rows": rows, "total": total}},
                request=request,
            )

        async def run():
            async with _client(handler) as client:
                return await rq.build_map_index(client)

        self.assertEqual(
            asyncio.run(run()),
            {1: "A", 2: "B", 3: "C", 4: "D",
             rq.DEFAULT_MAP_ID: f"seed-{rq.DEFAULT_MAP_ID}",
             197239: "seed-197239"},
        )


if __name__ == "__main__":
    unittest.main()
