"""TWRPG 云存档 API 客户端（对应读档器 CloudSyncClient）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_BASE_URLS = (
    "http://81.71.72.19:8080",
    "https://lostatong.top:8443",
    "https://lostatong.top",
)

MSG_SESSION_EXPIRED = "登录已过期，请私聊发送「世界登录 用户名 密码」重新登录。"
USER_AGENT = "TWRPGQuery/1.2 AstrBot-Plugin"
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_RETRYABLE_STATUSES = frozenset({500, 502, 503, 504})


@dataclass
class LoginResult:
    token: str
    user_id: int | None
    username: str
    admin: bool = False


@dataclass
class SaveEntry:
    name: str
    size: int
    last_modified: int | None = None


@dataclass
class ProfileInfo:
    username: str
    nickname: str
    level: int
    total_online_seconds: int


class CloudSyncError(Exception):
    pass


class CloudSyncClient:
    def __init__(self, base_urls: list[str] | None = None, token: str = ""):
        self.base_urls = _normalize_urls(base_urls or list(DEFAULT_BASE_URLS))
        self.token = token or ""
        self._preferred_base: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def set_token(self, token: str) -> None:
        self.token = token or ""

    async def login(self, username: str, password: str) -> LoginResult:
        payload = {"username": username, "password": password}
        status, body = await self._request_json("POST", "/api/login", json_body=payload, auth=False)
        if status == 401:
            raise CloudSyncError(_json_message(body, "用户名或密码错误"))
        if status == 429:
            raise CloudSyncError(_json_message(body, "操作过于频繁，请稍后再试"))
        if status != 200:
            raise CloudSyncError(_json_message(body, f"登录失败 (HTTP {status})"))
        token = str(body.get("token") or "")
        if not token:
            raise CloudSyncError("登录失败：服务器未返回令牌")
        return LoginResult(
            token=token,
            user_id=body.get("userId"),
            username=str(body.get("username") or username),
            admin=bool(body.get("admin")),
        )

    async def list_saves(self) -> list[SaveEntry]:
        status, body = await self._request_json("GET", "/api/saves")
        if status == 401:
            raise CloudSyncError(MSG_SESSION_EXPIRED)
        if status != 200:
            raise CloudSyncError(f"获取存档列表失败 (HTTP {status})")
        if not isinstance(body, list):
            return []
        entries: list[SaveEntry] = []
        for item in body:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            entries.append(
                SaveEntry(
                    name=name,
                    size=int(item.get("size") or 0),
                    last_modified=item.get("lastModified"),
                )
            )
        return entries

    async def download_save(self, filename: str) -> bytes:
        encoded = quote(filename, safe="")
        status, data = await self._request_bytes("GET", f"/api/saves/{encoded}")
        if status == 401:
            raise CloudSyncError(MSG_SESSION_EXPIRED)
        if status == 404:
            raise CloudSyncError("存档不存在")
        if status != 200:
            raise CloudSyncError(f"下载存档失败 (HTTP {status})")
        return data

    async def get_profile(self) -> ProfileInfo:
        status, body = await self._request_json("GET", "/api/account/profile")
        if status == 401:
            raise CloudSyncError(MSG_SESSION_EXPIRED)
        if status != 200:
            raise CloudSyncError(f"获取账号资料失败 (HTTP {status})")
        return ProfileInfo(
            username=str(body.get("username") or ""),
            nickname=str(body.get("nickname") or ""),
            level=int(body.get("level") or 0),
            total_online_seconds=int(body.get("totalOnlineSeconds") or 0),
        )

    async def check_update(self) -> dict[str, Any]:
        status, body = await self._request_json("GET", "/api/update/check", auth=False)
        if status != 200:
            raise CloudSyncError(f"获取更新信息失败 (HTTP {status})")
        if not isinstance(body, dict):
            raise CloudSyncError("获取更新信息失败：响应格式异常")
        return body

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> tuple[int, Any]:
        status, text = await self._request_text(method, path, json_body=json_body, auth=auth)
        if not text:
            return status, {}
        try:
            return status, json.loads(text)
        except json.JSONDecodeError:
            return status, {}

    async def _request_bytes(self, method: str, path: str) -> tuple[int, bytes]:
        status, content = await self._request(method, path, response_mode="bytes")
        return status, content

    async def _request_text(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> tuple[int, str]:
        status, text = await self._request(
            method,
            path,
            json_body=json_body,
            auth=auth,
            response_mode="text",
        )
        return status, text

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        auth: bool = True,
        response_mode: str = "text",
    ) -> tuple[int, str | bytes]:
        client = await self._get_client()
        urls = _ordered_urls(self.base_urls, self._preferred_base)
        headers = _headers(self.token if auth else "", json_body is not None)
        last_error: Exception | None = None
        last_status: int | None = None

        for base in urls:
            try:
                resp = await client.request(
                    method,
                    base + path,
                    headers=headers,
                    json=json_body,
                )
                status = resp.status_code
                last_status = status
                if status in _REDIRECT_STATUSES or status in _RETRYABLE_STATUSES:
                    self._preferred_base = None
                    continue
                self._preferred_base = base
                if response_mode == "bytes":
                    return status, resp.content
                return status, resp.text
            except httpx.RequestError as exc:
                last_error = exc
                self._preferred_base = None
                continue

        if last_status in _REDIRECT_STATUSES:
            raise CloudSyncError(
                "云服务器地址发生重定向，请在插件配置中使用带端口的地址，"
                "例如 http://81.71.72.19:8080"
            )
        raise CloudSyncError(f"无法连接云存档服务器：{last_error}")


def _headers(token: str, json_body: bool = False) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if json_body:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _normalize_urls(urls: list[str]) -> list[str]:
    result: list[str] = []
    for url in urls:
        cleaned = (url or "").strip().rstrip("/")
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result or list(DEFAULT_BASE_URLS)


def _ordered_urls(urls: list[str], preferred: str | None) -> list[str]:
    if preferred and preferred in urls:
        return [preferred] + [u for u in urls if u != preferred]
    return urls


def _json_message(body: Any, fallback: str) -> str:
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"])
    return fallback


def parse_base_urls_config(raw: str) -> list[str]:
    lines = [line.strip() for line in (raw or "").splitlines()]
    urls = [line.rstrip("/") for line in lines if line and not line.startswith("#")]
    return _normalize_urls(urls) if urls else list(DEFAULT_BASE_URLS)
