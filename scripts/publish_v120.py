"""推送 main 并发布 v1.2.0。"""
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
TAG = "v1.2.0"
COMMIT_MESSAGE = "整合云存档绑定功能，WebUI 可开关，版本 1.2.0"
RELEASE_BODY = """## 新增

- 整合云存档绑定（原 `astrbot_plugin_twrpg_cloud`）
- WebUI 配置 `_conf_schema.json`：`cloud_save_enabled` 开关
- 云存档指令：世界登录、世界存档、世界档案、世界背包/仓库/携带等

## 配置

- 关闭「启用云存档绑定功能」后，云指令不生效，离线查询不受影响
- 建议卸载独立的 `astrbot_plugin_twrpg_cloud` 避免重复

## 依赖

- 新增 `httpx`
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


def delete_release(tag: str) -> None:
    existing = api("GET", f"https://api.github.com/repos/{REPO}/releases/tags/{tag}")
    if existing and isinstance(existing, dict) and existing.get("id"):
        api("DELETE", f"https://api.github.com/repos/{REPO}/releases/{existing['id']}")
        print("deleted release:", tag)


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

    delete_release(TAG)
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
    print("done:", f"https://github.com/{REPO}")


if __name__ == "__main__":
    main()
