"""指令解析测试。"""

from core.cloud_commands import (
    _BACKPACK_RE,
    _HELP_RE,
    _LOGIN_RE,
    _SWITCH_RE,
    is_cloud_command,
)


def test_help_regex():
    assert _HELP_RE.match("世界云帮助")
    assert _HELP_RE.match("/界云帮助")


def test_backpack_regex():
    assert _BACKPACK_RE.match("世界背包")
    assert not _BACKPACK_RE.match("世界 背包")


def test_login_regex():
    m = _LOGIN_RE.match("世界登录 user pass word")
    assert m
    assert m.group(2) == "user"
    assert m.group(3) == "pass word"


def test_switch_regex():
    m = _SWITCH_RE.match("世界切换 2")
    assert m and m.group(2) == "2"


def test_is_cloud_command():
    assert is_cloud_command("世界仓库")
    assert is_cloud_command("世界登录 a b")
    assert not is_cloud_command("世界 太阳石")
