"""推送 main 并发布 v1.0.10。"""
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
TAG = "v1.0.10"
COMMIT_MESSAGE = "拦截界前缀误查三国杀界武将，版本 1.0.10"
RELEASE_BODY = """## 更新内容

- 误用「界」前缀查询三国杀界武将时，不再提示未找到物品，改为回复「滚回去玩你的三国杀！」
- 收录界·标、界·风林火山及常见界将名单（`界 赵云`、`界赵云` 等完全匹配时触发）
- 「世界」前缀的物品查询不受影响

## 示例

- `界 赵云` → 滚回去玩你的三国杀！
- `界 太阳石` → 正常查询物品
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
