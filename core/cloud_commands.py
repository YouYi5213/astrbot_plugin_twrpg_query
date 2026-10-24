"""云存档指令正则（无需 / 前缀，且优先于物品查询）。"""

from __future__ import annotations

import re

CLOUD_CMD_PRIORITY = 15
CLOUD_FALLBACK_PRIORITY = CLOUD_CMD_PRIORITY - 1

_LOGIN_RE = re.compile(r"^/?(世界登录|界登录)\s+(\S+)\s+(.+)$", re.IGNORECASE)
_UNBIND_RE = re.compile(r"^/?(世界解绑|界解绑)\s*$")
_SAVES_RE = re.compile(r"^/?(世界存档|界存档)\s*$")
_SWITCH_RE = re.compile(r"^/?(世界切换|界切换)\s+(\d+)\s*$")
_PROFILE_RE = re.compile(r"^/?(世界档案|界档案)\s*$")
_BACKPACK_RE = re.compile(r"^/?(世界背包|界背包)\s*$")
_WAREHOUSE_RE = re.compile(r"^/?(世界仓库|界仓库)\s*$")
_CARRIED_RE = re.compile(r"^/?(世界携带|界携带)\s*$")
_HELP_RE = re.compile(r"^/?(世界云帮助|界云帮助|世界云)\s*$")
_READER_UPDATE_RE = re.compile(r"^/?(读档器更新内容|读档器更新日志|读档器更新)\s*$")

CLOUD_RESERVED_PREFIXES = (
    "世界登录",
    "界登录",
    "世界解绑",
    "界解绑",
    "世界存档",
    "界存档",
    "世界切换",
    "界切换",
    "世界档案",
    "界档案",
    "世界背包",
    "界背包",
    "世界仓库",
    "界仓库",
    "世界携带",
    "界携带",
    "世界云帮助",
    "界云帮助",
    "世界云",
)

_CLOUD_RESERVED_RE = re.compile(
    r"^/?(?:"
    + "|".join(
        re.escape(prefix)
        for prefix in sorted(CLOUD_RESERVED_PREFIXES, key=len, reverse=True)
    )
    + r")(?:\s+.*)?$",
    re.IGNORECASE,
)


def _cloud_command_text(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("/"):
        text = text[1:].strip()
    return text


def is_cloud_command(raw: str) -> bool:
    text = _cloud_command_text(raw)
    return any(
        text == prefix or text.startswith(prefix + " ")
        for prefix in sorted(CLOUD_RESERVED_PREFIXES, key=len, reverse=True)
    )


def cloud_command_usage(raw: str) -> str:
    text = _cloud_command_text(raw)
    for prefix in sorted(CLOUD_RESERVED_PREFIXES, key=len, reverse=True):
        if text != prefix and not text.startswith(prefix + " "):
            continue
        if prefix in ("世界登录", "界登录"):
            return "格式：世界登录 用户名 密码"
        if prefix in ("世界切换", "界切换"):
            return "格式：世界切换 <序号>"
        if prefix in ("世界解绑", "界解绑"):
            return "格式：世界解绑"
        if prefix in ("世界存档", "界存档"):
            return "格式：世界存档"
        if prefix in ("世界档案", "界档案"):
            return "格式：世界档案"
        if prefix in ("世界背包", "界背包"):
            return "格式：世界背包"
        if prefix in ("世界仓库", "界仓库"):
            return "格式：世界仓库"
        if prefix in ("世界携带", "界携带"):
            return "格式：世界携带"
        if prefix in ("世界云帮助", "界云帮助", "世界云"):
            return "格式：世界云帮助 或 世界云"
    return "云存档指令格式有误，请发送「世界云帮助」查看用法。"
