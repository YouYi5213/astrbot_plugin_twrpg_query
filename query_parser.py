"""指令前缀解析。"""

from __future__ import annotations

import re

BOSS_CMD_PREFIXES: tuple[str, ...] = ("世界BOSS", "界BOSS")
BOSS_CMD_RE = re.compile(r"^/?(?:世界BOSS|界BOSS)")

ITEM_CMD_PREFIXES = ("世界", "界")
WORLD_ITEM_PREFIX = "世界"
JIE_ITEM_PREFIX = "界"
ITEM_CMD_RE = re.compile(r"^(?:世界|界)")

HERO_CMD_PREFIXES = ("英雄", "英")
HERO_CMD_RE = re.compile(r"^/?(英雄|英)(\s|$)")

SKILL_CMD_PREFIXES = ("技能", "技")
SKILL_CMD_RE = re.compile(r"^/?(技能|技)(\s|$)")


def dedupe_item_command_prefix(query: str) -> str:
    """去掉查询里重复的关键字，如「世界 世界破坏者」→「世界破坏者」。"""
    text = query.strip()
    if not text:
        return text
    for prefix in sorted(ITEM_CMD_PREFIXES, key=len, reverse=True):
        if text.startswith(prefix + " "):
            rest = text[len(prefix) + 1 :].strip()
            if rest:
                return rest
        if text.startswith(prefix + prefix):
            return text[len(prefix) :]
    return text


def extract_boss_query(raw: str) -> str | None:
    """解析 BOSS 查询文本；无法识别时返回 None。"""
    text = raw.strip()
    if text.startswith("/"):
        text = text[1:].strip()
    if not text:
        return None
    for prefix in sorted(BOSS_CMD_PREFIXES, key=len, reverse=True):
        if text == prefix:
            return ""
        if text.startswith(prefix + " "):
            return text[len(prefix) + 1 :].strip()
        if text.startswith(prefix) and len(text) > len(prefix):
            return text[len(prefix) :].strip()
    return None


def extract_item_query(raw: str) -> str | None:
    """解析物品查询文本；无法识别为物品指令时返回 None。"""
    text = raw.strip()
    if not text:
        return None

    if extract_boss_query(raw) is not None:
        return None

    for prefix in sorted(ITEM_CMD_PREFIXES, key=len, reverse=True):
        if text == prefix:
            return ""
        if text.startswith(prefix + " "):
            return dedupe_item_command_prefix(text[len(prefix) + 1 :].strip())
        if text.startswith(prefix) and len(text) > len(prefix):
            return dedupe_item_command_prefix(text[len(prefix) :].strip())
    return None


def used_jie_only_item_prefix(raw: str) -> bool:
    """消息是否以单独的「界」前缀触发物品查询（不含「世界」「界BOSS」）。"""
    text = raw.strip()
    if extract_boss_query(raw) is not None:
        return False
    if not text.startswith(JIE_ITEM_PREFIX):
        return False
    if text.startswith("世界"):
        return False
    return extract_item_query(raw) is not None


def _strip_leading_slash(text: str) -> str:
    text = text.strip()
    if text.startswith("/"):
        return text[1:].strip()
    return text


def extract_prefixed_query(raw: str, prefixes: tuple[str, ...]) -> str | None:
    """解析带空格前缀的查询（英雄、技能等）。"""
    text = _strip_leading_slash(raw.strip())
    for prefix in sorted(prefixes, key=len, reverse=True):
        if text == prefix:
            return ""
        if text.startswith(prefix + " "):
            return text[len(prefix) + 1 :].strip()
    return None
