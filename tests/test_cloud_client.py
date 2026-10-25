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
