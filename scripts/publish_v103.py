"""提交、推送 main 并发布 v1.0.3。"""
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
TAG = "v1.0.3"
COMMIT_MESSAGE = "物品卡片标题右侧显示红色阶段标签，版本 1.0.3"
RELEASE_BODY = """## 更新内容

- 物品卡片标题区在名称右侧显示阶段标签（如 `[大天使]`），颜色为红色，与 QuickSearch / 网页一致
- 新增 `STAGE_LABELS` 阶段映射（来自 QuickSearch `common.stages`）
- 文本回退格式同步带上阶段标签
- 新增 `scripts/extract_stages.py` 便于从 QuickSearch 提取阶段名

## 示例

查询「魂隙·生死彼岸」时，标题显示为：**魂隙·生死彼岸** `[大天使]`
"""


def run(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        list(args),
        cwd=PLUGIN_DIR,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


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


def main() -> None:
    os.chdir(PLUGIN_DIR)
    env = os.environ.copy()
    env["GIT_SSL_NO_VERIFY"] = "true"

    run("git", "add", "-A")
    status = run("git", "status", "--porcelain")
    if status:
        run("git", "commit", "-m", COMMIT_MESSAGE)
        print("committed")
    else:
        print("nothing to commit")

    subprocess.run(["git", "push", "origin", "main"], cwd=PLUGIN_DIR, check=True, env=env)
    print("pushed main")

    head = run("git", "rev-parse", "HEAD")
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
        print("deleted existing release:", TAG)

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
