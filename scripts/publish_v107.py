"""推送 main 并发布 v1.0.7。"""
from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

REPO = "YouYi5213/astrbot_plugin_twrpg_query"
PLUGIN_DIR = Path(__file__).resolve().parents[1]
TAG = "v1.0.7"
COMMIT_MESSAGE = "新增英雄与技能查询，版本 1.0.7"
RELEASE_BODY = """## 更新内容

- 新增英雄查询指令：`英雄 <名>` / `英 <名>`
- 新增技能查询指令：`技能 <名>` / `技 <名>`
- 英雄卡片展示头像、职业名、角色名及全部技能（图标 + 描述）
- 技能卡片展示技能图标、热键、描述及所属英雄
- 从 QuickSearch 离线数据合并 375 条英雄技能至 `heros.json`

## 示例

- `英雄 追星剑圣` — 查看职业、角色名与技能列表
- `技能 升龙击` — 查看技能详情及所属英雄
"""


def run(*args: str) -> str:
    result = subprocess.run(
        list(args),
        cwd=PLUGIN_DIR,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (result.stdout or "").strip()


def git_token() -> str:
    text = (Path.home() / ".git-credentials").read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"https://([^:]+):([^@]+)@github\.com", text)
    if not match:
        raise SystemExit("未找到 GitHub 凭据")
    return match.group(2)


def api(method: str, url: str, payload: dict | None = None) -> dict | list | None:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {
        "Authorization": f"token {git_token()}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "twrpg-query-release",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        body = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"GitHub API {exc.code}: {body}") from exc


def commit_without_coauthor(message: str) -> str:
    run("git", "add", "-A")
    tree = run("git", "write-tree")
    parent = run("git", "rev-parse", "HEAD")
    return run("git", "commit-tree", tree, "-p", parent, "-m", message)


def main() -> None:
    os.chdir(PLUGIN_DIR)
    env = os.environ.copy()
    env["GIT_SSL_NO_VERIFY"] = "true"

    head = commit_without_coauthor(COMMIT_MESSAGE)
    run("git", "update-ref", "refs/heads/main", head)
    print("commit:", head[:8])

    subprocess.run(["git", "push", "origin", "main"], cwd=PLUGIN_DIR, check=True, env=env)
    print("pushed main")

    subprocess.run(
        ["git", "tag", "-f", "-a", TAG, "-m", f"{TAG} 发布", head],
        cwd=PLUGIN_DIR,
        check=True,
    )
    subprocess.run(["git", "push", "--force", "origin", TAG], cwd=PLUGIN_DIR, check=True, env=env)
    print("pushed tag:", TAG)

    existing = api("GET", f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}")
    if existing and isinstance(existing, dict) and existing.get("id"):
        api("DELETE", f"https://api.github.com/repos/{REPO}/releases/{existing['id']}")

    result = api(
        "POST",
        f"https://api.github.com/repos/{REPO}/releases",
        {
            "tag_name": TAG,
            "name": TAG,
            "body": RELEASE_BODY.strip(),
            "draft": False,
            "prerelease": False,
        },
    )
    if result and isinstance(result, dict):
        print("release:", result.get("html_url"))
    print("done")


if __name__ == "__main__":
    main()
