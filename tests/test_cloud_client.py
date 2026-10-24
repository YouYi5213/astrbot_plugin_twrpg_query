from __future__ import annotations

import asyncio

import httpx
import pytest

from core.cloud_client import CloudSyncClient, CloudSyncError


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
