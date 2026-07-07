"""发布 v1.3.4 GitHub Release。"""
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
TAG = "v1.3.4"
RELEASE_BODY = """## 改进

- 「世界存档」改为图片展示：4 列紧凑网格 + 简短说明，避免长文字刷屏
- 主存档在图片中带 ⭐ 高亮
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


def main() -> None:
    os.chdir(PLUGIN_DIR)
    env = os.environ.copy()
    env["GIT_SSL_NO_VERIFY"] = "true"

    head = run("git", "rev-parse", "HEAD")
    subprocess.run(["git", "tag", "-f", "-a", TAG, "-m", f"{TAG} 发布", head], cwd=PLUGIN_DIR, check=True)
    subprocess.run(["git", "push", "--force", "origin", TAG], cwd=PLUGIN_DIR, check=True, env=env)
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


if __name__ == "__main__":
    main()
