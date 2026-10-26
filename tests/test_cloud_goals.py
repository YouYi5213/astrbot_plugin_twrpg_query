"""云存档「世界目标」业务逻辑测试（用 astrbot 轻量替身，无需真实 AstrBot）。"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import httpx

PLUGIN_DIR = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
PARENT_DIR = __import__("os").path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)


def _install_astrbot_stub() -> None:
    if "astrbot" in sys.modules:
        return

    class _Logger:
        def info(self, *args: Any, **kwargs: Any) -> None:
            pass

        def warning(self, *args: Any, **kwargs: Any) -> None:
            pass

        def error(self, *args: Any, **kwargs: Any) -> None:
            pass

    class _AstrMessageEvent:
        pass

    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = _Logger()
    api.AstrBotConfig = dict
    event_mod = types.ModuleType("astrbot.api.event")
    event_mod.AstrMessageEvent = _AstrMessageEvent
    astrbot.api = api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event_mod


_install_astrbot_stub()

from astrbot_plugin_twrpg_query.core.cloud_client import CloudSyncClient
from astrbot_plugin_twrpg_query.core.cloud_service import (
    CloudSaveService,
    GoalSnapshot,
)

_NOT_LOGGED_HINT = "尚未绑定云存档，请私聊发送：世界登录 用户名 密码"
_SAVE_BODY = "\n".join(
    [
        "背包:",
        "I018 弗罗斯特先驱的衣服 x1",
        "I09R 自然之纹 x2",
    ]
).encode("utf-8")


def _mock_client(handler) -> CloudSyncClient:
    client = CloudSyncClient(["https://example.test"], token="token-abc")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


class _StubStore:
    """只满足 resolve_item_id 所需接口的最小物品库。"""

    def __init__(self) -> None:
        self.items_by_id = {
            "I018": {"name": "弗罗斯特先驱的衣服"},
            "I09R": {"name": "自然之纹"},
        }
        self.name_to_item_id = {
            item["name"]: item_id for item_id, item in self.items_by_id.items()
        }

    def item_name(self, item_id: str) -> str:
        return self.items_by_id.get(item_id, {}).get("name", item_id)

    def search(self, query: str, limit: int = 12):
        return []

    def _is_queryable(self, item) -> bool:
        return True

    def _pick_best_item_id(self, ids):
        return ids[0] if ids else None


def _stub_store() -> _StubStore:
    return _StubStore()


def _bind(service: CloudSaveService, qq_id: str = "42") -> None:
    service._bindings.upsert(
        qq_id, username="mxdc", token="token-abc", cloud_user_id=1, primary_save="mxdc.txt"
    )


def test_goal_snapshot_reads_goals_and_inventory(tmp_path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/saves":
            return httpx.Response(
                200,
                json=[{"name": "mxdc.txt", "size": 123, "lastModified": "2026-10-01"}],
                request=request,
            )
        if request.url.path == "/api/saves/mxdc.txt":
            return httpx.Response(200, content=_SAVE_BODY, request=request)
        if request.url.path == "/api/item-goals":
            seen.append(str(request.url.params.get("saveName")))
            assert request.headers["Authorization"] == "Bearer token-abc"
            return httpx.Response(200, json=["I018", "I018", "I0B4"], request=request)
        return httpx.Response(404, json={}, request=request)

    async def run():
        service = CloudSaveService({"cloud_save_enabled": True}, str(tmp_path), store=_stub_store())
        _bind(service)
        client = _mock_client(handler)
        service._client_for = lambda binding: client  # type: ignore[method-assign]
        try:
            return await service.goal_snapshot("42")
        finally:
            await client.close()

    snapshot = asyncio.run(run())
    assert isinstance(snapshot, GoalSnapshot)
    assert snapshot.save_name == "mxdc.txt"
    assert snapshot.goal_ids == ["I018", "I018", "I0B4"]
    assert snapshot.goal_count == 3
    assert seen == ["mxdc.txt"]


def test_goal_snapshot_without_binding(tmp_path):
    async def run():
        service = CloudSaveService({"cloud_save_enabled": True}, str(tmp_path), store=_stub_store())
        return await service.goal_snapshot("99")

    assert asyncio.run(run()) == _NOT_LOGGED_HINT


def test_goal_snapshot_without_store(tmp_path):
    async def run():
        service = CloudSaveService({"cloud_save_enabled": True}, str(tmp_path))
        _bind(service)
        return await service.goal_snapshot("42")

    assert "物品数据尚未就绪" in asyncio.run(run())


def test_goal_snapshot_expired_token(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "无权限"}, request=request)

    async def run():
        service = CloudSaveService({"cloud_save_enabled": True}, str(tmp_path), store=_stub_store())
        _bind(service)
        client = _mock_client(handler)
        service._client_for = lambda binding: client  # type: ignore[method-assign]
        try:
            return await service.goal_snapshot("42")
        finally:
            await client.close()

    text = asyncio.run(run())
    assert isinstance(text, str)
    assert "世界登录" in text


def test_goal_snapshot_empty_goals(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/saves":
            return httpx.Response(200, json=[{"name": "mxdc.txt", "size": 1}], request=request)
        if request.url.path == "/api/saves/mxdc.txt":
            return httpx.Response(200, content=_SAVE_BODY, request=request)
        if request.url.path == "/api/item-goals":
            return httpx.Response(200, json=[], request=request)
        return httpx.Response(404, json={}, request=request)

    async def run():
        service = CloudSaveService({"cloud_save_enabled": True}, str(tmp_path), store=_stub_store())
        _bind(service)
        client = _mock_client(handler)
        service._client_for = lambda binding: client  # type: ignore[method-assign]
        try:
            return await service.goal_snapshot("42")
        finally:
            await client.close()

    snapshot = asyncio.run(run())
    assert isinstance(snapshot, GoalSnapshot)
    assert snapshot.goal_ids == []
    assert snapshot.goal_count == 0
