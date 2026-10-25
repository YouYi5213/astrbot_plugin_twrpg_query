"""云存档「世界在线」业务逻辑测试（用 astrbot 轻量替身，无需真实 AstrBot）。"""

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
    _format_online_duration,
)

_NOT_LOGGED_HINT = "尚未绑定云存档，请私聊发送：世界登录 用户名 密码"


def _mock_client(handler) -> CloudSyncClient:
    client = CloudSyncClient(["https://example.test"], token="token-abc")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def _bind(service: CloudSaveService, qq_id: str = "42") -> None:
    service._bindings.upsert(
        qq_id, username="mxdc", token="token-abc", cloud_user_id=1, primary_save="mxdc.txt"
    )


def test_format_online_duration():
    assert _format_online_duration(0) == "0 秒"
    assert _format_online_duration(59) == "59 秒"
    assert _format_online_duration(60) == "1 分钟"
    assert _format_online_duration(3720) == "1 小时 2 分钟"
    assert _format_online_duration(-5) == "0 秒"


def test_online_status_reports_count_and_profile(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/account/online-count":
            assert request.headers["Authorization"] == "Bearer token-abc"
            return httpx.Response(200, json={"onlineCount": 7}, request=request)
        if request.url.path == "/api/account/profile":
            return httpx.Response(
                200,
                json={
                    "username": "mxdc",
                    "nickname": "阿强",
                    "level": 12,
                    "totalOnlineSeconds": 7320,
                },
                request=request,
            )
        return httpx.Response(404, json={}, request=request)

    async def run() -> str:
        service = CloudSaveService({"cloud_save_enabled": True}, str(tmp_path))
        _bind(service)
        client = _mock_client(handler)
        service._client_for = lambda binding: client  # type: ignore[method-assign]
        try:
            return await service.online_status("42")
        finally:
            await client.close()

    text = asyncio.run(run())
    assert "当前在线 7 人" in text
    assert "5 分钟内活跃" in text
    assert "阿强" in text
    assert "Lv12" in text
    assert "2 小时 2 分钟" in text


def test_online_status_without_binding(tmp_path):
    async def run() -> str:
        service = CloudSaveService({"cloud_save_enabled": True}, str(tmp_path))
        return await service.online_status("99")

    assert asyncio.run(run()) == _NOT_LOGGED_HINT


def test_online_status_expired_token(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "请先登录"}, request=request)

    async def run() -> str:
        service = CloudSaveService({"cloud_save_enabled": True}, str(tmp_path))
        _bind(service)
        client = _mock_client(handler)
        service._client_for = lambda binding: client  # type: ignore[method-assign]
        try:
            return await service.online_status("42")
        finally:
            await client.close()

    text = asyncio.run(run())
    assert "世界登录" in text
