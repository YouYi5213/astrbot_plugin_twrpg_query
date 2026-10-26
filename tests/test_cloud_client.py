from __future__ import annotations

import asyncio

import httpx
import pytest

from core.cloud_client import CloudSyncClient, CloudSyncError, MSG_SESSION_EXPIRED


def test_retryable_status_reports_last_http_status():
    async def run():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(503, request=request)
        )
        client = CloudSyncClient(["https://primary.example", "https://backup.example"])
        client._client = httpx.AsyncClient(transport=transport)
        try:
            with pytest.raises(CloudSyncError) as exc_info:
                await client._request_text("GET", "/api/saves")
        finally:
            await client.close()
        message = str(exc_info.value)
        assert "HTTP 503" in message
        assert "None" not in message

    asyncio.run(run())


def test_online_count_parses_payload():
    async def run():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"onlineCount": 5}, request=request)
        )
        client = CloudSyncClient(["https://primary.example"], token="t")
        client._client = httpx.AsyncClient(transport=transport)
        try:
            return await client.get_online_count()
        finally:
            await client.close()

    assert asyncio.run(run()) == 5


def test_online_count_handles_odd_payload():
    async def run(payload):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload, request=request)
        )
        client = CloudSyncClient(["https://primary.example"], token="t")
        client._client = httpx.AsyncClient(transport=transport)
        try:
            return await client.get_online_count()
        finally:
            await client.close()

    assert asyncio.run(run({})) == 0
    assert asyncio.run(run({"onlineCount": "abc"})) == 0
    assert asyncio.run(run({"onlineCount": -3})) == 0


def test_online_count_expired_token():
    async def run():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(401, json={}, request=request)
        )
        client = CloudSyncClient(["https://primary.example"], token="t")
        client._client = httpx.AsyncClient(transport=transport)
        try:
            with pytest.raises(CloudSyncError) as exc_info:
                await client.get_online_count()
        finally:
            await client.close()
        return str(exc_info.value)

    assert asyncio.run(run()) == MSG_SESSION_EXPIRED


def test_forbidden_counts_as_expired_session():
    """后端无 authenticationEntryPoint，令牌过期返回 403 而非 401。"""

    async def run(call):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(403, json={"status": 403}, request=request)
        )
        client = CloudSyncClient(["https://primary.example"], token="t")
        client._client = httpx.AsyncClient(transport=transport)
        try:
            with pytest.raises(CloudSyncError) as exc_info:
                await call(client)
        finally:
            await client.close()
        return str(exc_info.value)

    assert asyncio.run(run(lambda c: c.get_online_count())) == MSG_SESSION_EXPIRED
    assert asyncio.run(run(lambda c: c.list_saves())) == MSG_SESSION_EXPIRED
    assert asyncio.run(run(lambda c: c.get_profile())) == MSG_SESSION_EXPIRED
    assert asyncio.run(run(lambda c: c.download_save("a.txt"))) == MSG_SESSION_EXPIRED


def test_get_item_goals_filters_and_encodes_save_name():
    seen = {}

    async def run():
        def handler(request):
            seen['path'] = request.url.path
            seen['save'] = request.url.params.get('saveName')
            seen['auth'] = request.headers.get('Authorization')
            return httpx.Response(200, json=['I018', ' ', '', 'I0B4'], request=request)

        transport = httpx.MockTransport(handler)
        client = CloudSyncClient(['https://primary.example'], token='t')
        client._client = httpx.AsyncClient(transport=transport)
        try:
            return await client.get_item_goals('mxdc 的存档.txt')
        finally:
            await client.close()

    goals = asyncio.run(run())
    assert goals == ['I018', 'I0B4']
    assert seen['path'] == '/api/item-goals'
    assert seen['save'] == 'mxdc 的存档.txt'
    assert seen['auth'] == 'Bearer t'


def test_get_item_goals_empty_name_skips_request():
    async def run():
        def handler(request):
            raise AssertionError('不应发起请求')

        client = CloudSyncClient(['https://primary.example'], token='t')
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            return await client.get_item_goals('   ')
        finally:
            await client.close()

    assert asyncio.run(run()) == []


def test_get_item_goals_handles_non_list_and_403():
    async def run(payload, status):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(status, json=payload, request=request)
        )
        client = CloudSyncClient(['https://primary.example'], token='t')
        client._client = httpx.AsyncClient(transport=transport)
        try:
            return await client.get_item_goals('a.txt')
        finally:
            await client.close()

    assert asyncio.run(run({}, 200)) == []
    with pytest.raises(CloudSyncError) as exc_info:
        asyncio.run(run({'message': 'no'}, 403))
    assert str(exc_info.value) == MSG_SESSION_EXPIRED
