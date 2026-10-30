"""KK 房间列表查询（世界RPG 等地图的在线房间）。

token 由 Windows 端的 kk_sync 同步过来，放在插件数据目录下：

    <data_dir>/kk_room/token.json

接口事实（与 KK房间查询 项目一致）：
  * 鉴权只需要 header: token = <64~128 位 hex>
  * start 是「房间数偏移」不是页号，limit 服务端硬顶 32
  * 房间属性：room_status == 0 → 可加入；watch_ready → 观战；其余 → 游戏中
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field

import httpx

MAP_API = "https://map-api.kkdzpt.com"
DEFAULT_MAP_ID = 2310
GAME_TYPE = "war3rpg"
PAGE_CAP = 32            # 服务端硬顶
MAX_PAGES = 20
HTTP_TIMEOUT = 12.0
CACHE_TTL = 10.0         # 群聊里连续查询时复用同一份，别把上游当压测目标
MAX_LINES = 50

TOKEN_SUBDIR = "kk_room"
TOKEN_NAME = "token.json"
INDEX_NAME = "map_index.json"
INDEX_PAGE_LIMIT = 500      # 服务端允许一次拿 500+ 条
INDEX_MAX_PAGES = 80
INDEX_CONCURRENCY = 4
INDEX_COMMANDS = frozenset({"更新目录", "刷新目录", "更新地图", "刷新地图"})
# 世界RPG（2310）和守护小天使（197239）不参与官方地图目录，
# 构建索引时用 mapId 直接补入；补入时同样跳过测试图。
SEED_MAP_IDS = (DEFAULT_MAP_ID, 197239)

# 和官方客户端一致的 UA（Platform.exe 里的 QtWebEngine 5.15.2）
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) QtWebEngine/5.15.2 Chrome/83.0.4103.122 "
    "Safari/537.36"
)
_TOKEN_RE = re.compile(r"^[0-9a-f]{64,128}$")

TOKEN_MISSING_HINT = (
    "❌ 还没收到房间 token。\n"
    "请确认 Windows 端的 kk_sync 已同步到插件数据目录的 kk_room/token.json。"
)
TOKEN_EXPIRED_HINT = (
    "❌ 房间 token 已过期（服务端判定 403）。\n"
    "Windows 端守护进程通常会在 1 分钟内自动续签，稍后再试。"
)


class RoomQueryError(Exception):
    """查询失败；异常消息可以直接展示给用户。"""


class TokenExpired(RoomQueryError):
    """token 过期或无效。"""


class AmbiguousMap(RoomQueryError):
    """地图名匹配到多个结果；异常消息里已经列好候选。"""


@dataclass
class MapCandidate:
    map_id: int
    name: str


@dataclass
class Room:
    no: str
    name: str
    players: int
    slots: int
    level: str
    attr: str
    need_password: bool
    mode: str = "不限"
    vip: bool = False


@dataclass
class RoomSnapshot:
    map_id: int
    map_name: str
    total: int
    now: int
    rooms: list[Room]
    logo: str = ""
    map_version: str = ""
    war3_version: str = ""
    map_type: str = ""
    engine: str = "War3"
    tags: list[str] = field(default_factory=list)
    hot: int = 0
    score: float | None = None
    score_count: int = 0


# ---------------------------------------------------------------- token

def _room_dir(data_dir: str, token_override: str = "") -> str:
    if token_override:
        parent = os.path.dirname(os.path.abspath(token_override))
        return parent or data_dir
    return os.path.join(data_dir, TOKEN_SUBDIR)


def resolve_token_path(data_dir: str, override: str = "") -> str:
    if override:
        return override
    return os.path.join(_room_dir(data_dir), TOKEN_NAME)


def map_index_path(data_dir: str, token_override: str = "") -> str:
    return os.path.join(_room_dir(data_dir, token_override), INDEX_NAME)


def load_token(path: str) -> str:
    if not os.path.exists(path):
        raise RoomQueryError(TOKEN_MISSING_HINT)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        raise RoomQueryError(TOKEN_MISSING_HINT) from None
    token = str((data or {}).get("token") or "").strip()
    if not _TOKEN_RE.match(token):
        raise RoomQueryError(TOKEN_MISSING_HINT)
    return token


# ---------------------------------------------------------------- 参数

def parse_room_args(text: str) -> tuple[str, bool]:
    """解析「魔兽房间」后面的参数，返回 (地图参数, 是否包含游戏中)。"""
    tokens = [t for t in re.split(r"\s+", (text or "").strip()) if t]
    include_playing = False
    rest: list[str] = []
    for token in tokens:
        if token in ("全部", "所有", "含游戏中"):
            include_playing = True
        elif token in ("可加入", "可进"):
            include_playing = False
        else:
            rest.append(token)
    return " ".join(rest), include_playing


# ---------------------------------------------------------------- HTTP

def make_client() -> httpx.AsyncClient:
    # trust_env=False：忽略系统代理。本机有 Clash 时代理会让 map-api 的
    # TLS 握手直接断开（见 KK房间查询 README 第 8 节）。
    return httpx.AsyncClient(
        base_url=MAP_API,
        timeout=HTTP_TIMEOUT,
        trust_env=False,
        headers={"Accept": "application/json, text/plain, */*"},
    )


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Origin": "https://kk.kkdzpt.com",
        "Referer": "https://kk.kkdzpt.com/",
        "X-Web-Channel": "client",
        "x-kk-ag": "4",
    }
    if token:
        headers["token"] = token
    return headers


async def _get(
    client: httpx.AsyncClient,
    path: str,
    params: dict,
    token: str | None = None,
) -> dict:
    try:
        resp = await client.get(path, params=params, headers=_headers(token))
    except httpx.HTTPError as exc:
        raise RoomQueryError(f"❌ 连不上房间服务：{type(exc).__name__}") from exc

    try:
        body = resp.json()
    except Exception:
        raise RoomQueryError(f"❌ 房间服务返回了非 JSON 响应（HTTP {resp.status_code}）") from None

    if resp.status_code == 403 or body.get("status") == 40301:
        raise TokenExpired(TOKEN_EXPIRED_HINT)
    if resp.status_code != 200:
        raise RoomQueryError(f"❌ 房间服务异常（HTTP {resp.status_code}）")
    return body


MAX_MAP_CANDIDATES = 10


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", "", name or "").lower()


_mem_index: tuple[float, str, dict[int, str]] | None = None


def format_map_candidates(query: str, candidates: list[MapCandidate]) -> str:
    lines = [f"🔍 找到 {len(candidates)} 个和「{query}」相似的地图：", ""]
    for index, item in enumerate(candidates[:MAX_MAP_CANDIDATES], 1):
        lines.append(f"{index}. {item.name}（ID {item.map_id}）")
    if len(candidates) > MAX_MAP_CANDIDATES:
        lines.append(f"…还有 {len(candidates) - MAX_MAP_CANDIDATES} 个")
    lines.append("")
    lines.append("发送「魔兽房间 <ID>」查询指定地图，或把地图名写完整一些。")
    return "\n".join(lines)


# ---------------------------------------------------------------- 地图目录
#
# 官方没有可用的「地图名搜索」接口（/api/v3/map/search 会忽略 keyword，
# 只认 tabId / page / limit）。所以第一次按名字查询时把各分类的地图目录
# 拉一次，存成 map_index.json，之后 7 天都读本地文件。
# 一周约 40 个请求，均摊每天几个；默认地图和按 ID 查询根本不拉。

def _load_map_index(path: str) -> tuple[float, dict[int, str]]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ts = float(data.get("ts") or 0)
        maps = {int(i): str(n) for i, n in (data.get("maps") or [])}
        return ts, maps
    except Exception:
        return 0.0, {}


def _save_map_index(path: str, maps: dict[int, str]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            {"ts": time.time(),
             "maps": [[mid, name] for mid, name in maps.items()]},
            f, ensure_ascii=False,
        )
    os.replace(tmp, path)


async def _index_page(
    client: httpx.AsyncClient, tab_id: int, page: int,
    sem: asyncio.Semaphore,
) -> dict:
    async with sem:
        return await _get(
            client, "/api/v3/map/search",
            {"tabId": tab_id, "page": page, "limit": INDEX_PAGE_LIMIT},
        )


async def build_map_index(client: httpx.AsyncClient) -> dict[int, str]:
    """按分类分批拉地图目录。大 limit 会少覆盖一些冷门图，多翻一页补上。"""
    tabs_body = await _get(client, "/api/v3/map/tabs", {})
    tab_ids = [
        int(tab["id"])
        for tab in (tabs_body.get("data") or [])
        if tab.get("id") is not None
    ]
    sem = asyncio.Semaphore(INDEX_CONCURRENCY)
    maps: dict[int, str] = {}

    def absorb(body: dict) -> int:
        data = body.get("data") or {}
        for row in data.get("rows") or []:
            mid, name = row.get("mapId"), row.get("mapName")
            if not (mid and name):
                continue
            # 测试图不进目录（例如名字里带「测试」的图）
            if row.get("testMap") or "测试" in str(name):
                continue
            maps[int(mid)] = str(name)
        return int(data.get("total") or 0)

    firsts = await asyncio.gather(
        *[_index_page(client, tid, 1, sem) for tid in tab_ids],
        return_exceptions=True,
    )
    totals: dict[int, int] = {}
    for tid, body in zip(tab_ids, firsts):
        if isinstance(body, Exception):
            continue
        totals[tid] = absorb(body)

    pages = []
    for tid, total in totals.items():
        count = min(
            (total + INDEX_PAGE_LIMIT - 1) // INDEX_PAGE_LIMIT + 1,
            INDEX_MAX_PAGES,
        )
        pages.extend(
            _index_page(client, tid, page, sem) for page in range(2, count + 1)
        )
    for body in await asyncio.gather(*pages, return_exceptions=True):
        if not isinstance(body, Exception):
            absorb(body)

    # 补上不在目录里的官方地图（世界RPG / 守护小天使）；测试图跳过
    for mid in SEED_MAP_IDS:
        if mid in maps:
            continue
        try:
            async with sem:
                body = await _get(client, "/api/v3/map/detail", {"mapId": mid})
            data = body.get("data") or {}
            name = data.get("mapName")
            if name and not data.get("testMap") and "测试" not in str(name):
                maps[int(mid)] = str(name)
        except Exception:
            continue
    return maps


async def get_map_index(
    data_dir: str, token_override: str = ""
) -> dict[int, str]:
    """
    只读本地缓存，**不联网**。目录只在用户手动「更新目录」时才拉取。
    没有缓存时返回空表，按名字查会提示先更新目录。
    """
    global _mem_index
    path = map_index_path(data_dir, token_override)
    if _mem_index and _mem_index[1] == path:
        return _mem_index[2]
    ts, maps = _load_map_index(path)
    if maps:
        _mem_index = (ts, path, maps)
    return maps


async def refresh_map_index(
    data_dir: str, token_override: str = ""
) -> str:
    """手动更新地图目录（唯一会联网拉目录的入口）。"""
    global _mem_index
    path = map_index_path(data_dir, token_override)
    async with make_client() as client:
        maps = await build_map_index(client)
    if not maps:
        raise RoomQueryError("❌ 地图目录拉取失败，请稍后再试。")
    _mem_index = (time.time(), path, maps)
    try:
        _save_map_index(path, maps)
        note = ""
    except Exception:
        note = "\n（写入 map_index.json 失败，本次只缓存在内存中）"
    return f"✅ 地图目录已更新：{len(maps)} 张地图。{note}"


def is_index_command(text: str) -> bool:
    return (text or "").strip() in INDEX_COMMANDS


def search_map_index(
    index: dict[int, str], query: str
) -> list[tuple[int, str]]:
    """模糊匹配：完全相同 > 前缀 > 包含 > 被包含。结果由近到远排好。"""
    q = _norm_name(query)
    if not q:
        return []
    scored = []
    for mid, name in index.items():
        if "测试" in name:
            continue
        n = _norm_name(name)
        if n == q:
            rank = 0
        elif n.startswith(q):
            rank = 1
        elif q in n:
            rank = 2
        elif n in q:
            rank = 3
        else:
            continue
        scored.append((rank, len(n), mid, name))
    scored.sort()
    return [(mid, name) for _, _, mid, name in scored]


async def resolve_map(
    client: httpx.AsyncClient,
    spec: str,
    index: dict[int, str] | None = None,
) -> tuple[int, str]:
    """
    把「2310」或地图名解析成 (mapId, 地图名)。

    地图名走本地目录做模糊匹配：
      * 正好有一个名字完全相同 → 直接用
      * 只匹配到一个          → 直接用
      * 匹配到多个相似名字     → 抛 AmbiguousMap，消息里列出候选
    """
    spec = (spec or "").strip()
    if not spec:
        return DEFAULT_MAP_ID, ""
    if spec.isdigit():
        return int(spec), ""
    if not index:
        raise RoomQueryError(
            "❌ 本地还没有地图目录，暂时只能按地图ID查询。\n"
            "管理员发送「魔兽房间 更新目录」可以手动拉取一次。"
        )
    matches = search_map_index(index or {}, spec)
    if not matches:
        raise RoomQueryError(
            f"❌ 地图目录里没有匹配「{spec}」的地图。\n"
            "可以发送「魔兽房间 更新目录」刷新目录，"
            "或发送「魔兽房间 <地图ID>」直接查询。"
        )
    exact = [m for m in matches if _norm_name(m[1]) == _norm_name(spec)]
    if len(exact) == 1:
        return exact[0]
    if len(matches) == 1:
        return matches[0]
    raise AmbiguousMap(
        format_map_candidates(
            spec, [MapCandidate(mid, name) for mid, name in matches]
        )
    )


async def _fetch_map_meta(
    client: httpx.AsyncClient, map_id: int, token: str = ""
) -> dict:
    """地图名 / 版本 / 分类 / 标签 / 热度 / 评分，一次请求拿全。"""
    try:
        body = await _get(
            client, "/api/v3/map/search_by_map_ids", {"mapIds": map_id},
            token)
        rows = (body.get("data") or {}).get("rows") or []
        if rows:
            return rows[0]
    except Exception:
        pass
    try:
        body = await _get(client, "/api/v3/map/detail", {"mapId": map_id})
        return body.get("data") or {}
    except Exception:
        return {}


async def fetch_snapshot(
    client: httpx.AsyncClient, token: str, map_id: int, map_name: str = ""
) -> RoomSnapshot:
    """拉地图信息 + 房间列表。服务端每页硬顶 32，按 room_guid 去重。"""
    meta = await _fetch_map_meta(client, map_id, token)
    name = str(meta.get("mapName") or map_name or f"地图 {map_id}")
    logo = str(meta.get("logo") or "")
    score = meta.get("score")
    try:
        score = float(score) if score not in (None, "") else None
    except (TypeError, ValueError):
        score = None

    seen: dict[str, dict] = {}
    total = 0
    now = 0
    start = 0

    for _ in range(MAX_PAGES):
        body = await _get(
            client, "/api/v3/map/w3_roomList",
            {"mapId": map_id, "start": start, "limit": PAGE_CAP,
             "gameType": GAME_TYPE},
            token,
        )
        data = body.get("data") or {}
        total = int(data.get("count") or total or 0)
        now = int(data.get("now") or now or 0)
        batch = data.get("preparing") or []
        if not batch:
            break

        for raw in batch:
            gid = str(raw.get("room_guid") or "")
            if gid and gid not in seen:
                seen[gid] = raw
            if not logo:
                logo = str(raw.get("url_logo") or "")

        # 房间顺序会随时间变化，可能出现重复页；按 offset 走完全部页，
        # 不要因为「这一页没有新房间」就提前停止，否则会漏掉后面的房间。
        start += len(batch)
        if total and start >= total:
            break

    return RoomSnapshot(
        map_id=map_id,
        map_name=name,
        total=total,
        now=now,
        rooms=[_to_room(raw) for raw in seen.values()],
        logo=logo,
        map_version=str(meta.get("mapVersion") or ""),
        war3_version=str(meta.get("war3Version") or ""),
        map_type=str(meta.get("mapTypeStr") or ""),
        engine="Y3" if meta.get("y3Map") else "War3",
        tags=[str(t) for t in (meta.get("tagsString") or []) if t],
        hot=int(meta.get("hot") or 0),
        score=score,
        score_count=int(meta.get("scoreCount") or 0),
    )


# ---------------------------------------------------------------- 整理

def room_attr(raw: dict) -> str:
    """房间属性：可加入 / 观战 / 游戏中（与官方客户端一致）。"""
    if int(raw.get("room_status") or 0) == 0:
        return "-"
    if raw.get("watch_ready"):
        return "观战"
    return "游戏中"


def _format_level(level: dict) -> str:
    lo = int(level.get("min_map_lvl") or 0)
    hi = int(level.get("max_map_lvl") or 0)
    if lo and hi:
        return f"{lo}~{hi}"
    if lo:
        return f"≥{lo}"
    if hi:
        return f"≤{hi}"
    return "-"


def _to_room(raw: dict) -> Room:
    return Room(
        no=str(raw.get("show_id") or "-"),
        name=(raw.get("room_name") or "").strip(),
        players=int(
            raw.get("real_player_number") or raw.get("player_number") or 0
        ),
        slots=int(raw.get("total_slots") or 0),
        level=_format_level(raw.get("enter_limit_map_lvl") or {}),
        attr=room_attr(raw),
        need_password=bool(raw.get("need_password")),
        mode=str(raw.get("mode_name") or raw.get("mode") or "不限"),
        vip=int(raw.get("room_flag") or 0) == 2,
    )


def _room_no_key(no: str) -> int:
    try:
        return int(no)
    except (TypeError, ValueError):
        return 0


def split_visible(
    snap: RoomSnapshot, include_playing: bool = False
) -> tuple[list[Room], list[Room], list[Room], list[Room]]:
    """返回 (要显示的, 可加入, 游戏中, 观战)。

    排序：无密码房优先，然后按人数从多到少；带密码的沉到最后。
    """
    joinable = [r for r in snap.rooms if r.attr == "-"]
    playing = [r for r in snap.rooms if r.attr == "游戏中"]
    watching = [r for r in snap.rooms if r.attr == "观战"]

    shown = joinable + (playing if include_playing else [])
    shown.sort(key=lambda r: (r.need_password, -r.players,
                              _room_no_key(r.no)))
    return shown, joinable, playing, watching


def format_snapshot(snap: RoomSnapshot, include_playing: bool = False) -> str:
    shown, joinable, playing, watching = split_visible(snap, include_playing)

    stamp = time.strftime(
        "%H:%M", time.localtime(snap.now or time.time())
    )
    head = f"🗺️ {snap.map_name} · 可加入 {len(joinable)} 间"
    if include_playing:
        head += f" · 游戏中 {len(playing)} 间"
    meta_parts = []
    if snap.engine:
        meta_parts.append(snap.engine)
    if snap.map_type:
        meta_parts.append(snap.map_type)
    if snap.map_version:
        meta_parts.append(f"V{snap.map_version}")
    if snap.hot:
        meta_parts.append(f"热度 {snap.hot}")
    if snap.score is not None:
        meta_parts.append(f"{snap.score:g} 分")
    lines = [head]
    if meta_parts:
        lines.append(" · ".join(meta_parts))
    lines.append(f"🕒 {stamp}｜在线共 {snap.total} 间")

    if not shown:
        lines.append("")
        if snap.rooms:
            lines.append("当前没有可直接加入的房间。")
            lines.append(f"（观战 {len(watching)} 间、游戏中 {len(playing)} 间）")
        else:
            lines.append("当前地图没有在线房间。")
        return "\n".join(lines)

    lines.append("")
    for room in shown[:MAX_LINES]:
        lock = "🔒" if room.need_password else ""
        name = re.sub(r"\s+", " ", room.name)[:18]
        lines.append(
            f"{room.no}  {room.players}/{room.slots}  "
            f"[等级{room.level}] {lock}{name}"
        )
    if len(shown) > MAX_LINES:
        lines.append(f"…还有 {len(shown) - MAX_LINES} 间")
    if watching:
        lines.append("")
        lines.append(f"观战 {len(watching)} 间已隐藏")
    return "\n".join(lines)


# ---------------------------------------------------------------- 对外入口

_cache: dict[str, tuple[float, RoomSnapshot]] = {}
_lock = asyncio.Lock()


async def query_rooms(
    data_dir: str,
    query: str = "",
    token_path_override: str = "",
) -> tuple[RoomSnapshot, bool]:
    """按指令参数查询，返回 (快照, 是否包含游戏中)。"""
    spec, include_playing = parse_room_args(query)
    token = load_token(resolve_token_path(data_dir, token_path_override))

    cached = _cache.get(spec)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1], include_playing

    async with _lock:
        cached = _cache.get(spec)
        if cached and time.time() - cached[0] < CACHE_TTL:
            return cached[1], include_playing

        index: dict[int, str] = {}
        if spec and not spec.isdigit():
            # 只有按名字查才需要地图目录；目录也是本地缓存的
            index = await get_map_index(data_dir, token_path_override)
        async with make_client() as client:
            map_id, map_name = await resolve_map(client, spec, index)
            snap = await fetch_snapshot(client, token, map_id, map_name)
        _cache[spec] = (time.time(), snap)
        return snap, include_playing


async def query_rooms_text(
    data_dir: str,
    query: str = "",
    token_path_override: str = "",
) -> str:
    """按指令参数查询房间，返回可直接发到群里的文本。"""
    snap, include_playing = await query_rooms(
        data_dir, query, token_path_override)
    return format_snapshot(snap, include_playing=include_playing)
