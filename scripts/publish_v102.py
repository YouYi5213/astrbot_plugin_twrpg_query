"""重写提交说明为中文，推送 main 并发布 v1.0.2。"""
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

COMMIT_MESSAGES = [
    "初始提交：添加世界RPG 离线物品查询插件",
    "修复中文乱码：内置 NotoSansSC-Bold 字体用于卡片渲染",
    "新增物品图标、被动描述与 GamePanel 金色属性框样式",
    "修正插件版本号为 1.0.1",
]

NEW_COMMIT_MESSAGE = (
    "修复佩戴限定与专属效果展示，佩戴限定改为英雄头像，专属效果独立区块，版本 1.0.2"
)

RELEASES = {
    "v1.0.0": {
        "commit_index": 0,
        "body": """## 更新内容

- 首次发布世界RPG（TWRPG）离线物品查询插件
- 支持「世界 / 界 + 物品名」指令查询
- 图片卡片展示属性、合成、可合成物品、BOSS 掉落等信息
- 内置离线 JSON 数据（items / makes / drops / bosses / heros / exclusives）
""",
    },
    "v1.0.1": {
        "commit_index": 3,
        "body": """## 更新内容

- 查询卡片新增图标：物品主图、合成材料、可合成物品、来源 BOSS
- 新增完整被动/主动描述（item_passives.json，共 532 条）
- 属性区采用 QuickSearch 同款 GamePanel 金色边框，并按 War3 颜色码渲染 rawDesc 彩色文本
- 内置 items_bg.png 属性框背景图
- 新增 scripts/sync_assets.py，可从本地 QuickSearch 同步图标与被动数据

## 资源同步（可选）

```bash
python scripts/sync_assets.py
```
""",
    },
    "v1.0.2": {
        "commit_index": -1,
        "body": """## 更新内容

- 佩戴限定改为显示可佩戴英雄头像（与 QuickSearch limitHeroes 一致），不再仅显示文字「背包」等
- 专属效果独立为「▎专属效果」区块，展示英雄头像与专属改动说明
- 佩戴限定与专属效果不再混在同一区块

## 示例

查询「魂隙·生死彼岸」时，佩戴限定显示旅行商人、幽人头像；专属效果显示着手成春 / 净世契约 / 永不凋谢等改动。
""",
    },
}


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
        raise


def rewrite_history() -> None:
    entries = [
        line.split(maxsplit=1)
        for line in run("git", "log", "--reverse", "--format=%H %T").splitlines()
        if line.strip()
    ]
    if len(entries) != len(COMMIT_MESSAGES):
        raise SystemExit(
            f"提交数量不匹配：期望 {len(COMMIT_MESSAGES)}，实际 {len(entries)}"
        )

    parent = None
    new_commits: list[str] = []
    for (commit_hash, tree), message in zip(entries, COMMIT_MESSAGES):
        args = ["git", "commit-tree", tree]
        if parent:
            args.extend(["-p", parent])
        args.extend(["-m", message])
        new_hash = run(*args)
        new_commits.append(new_hash)
        parent = new_hash

    run("git", "update-ref", "refs/heads/main", parent)
    print("history rewritten:", new_commits[-1][:7])
    return new_commits


def commit_current(new_commits: list[str]) -> str:
    run("git", "add", "-A")
    tree = run("git", "write-tree")
    parent = new_commits[-1]
    head = run("git", "commit-tree", tree, "-p", parent, "-m", NEW_COMMIT_MESSAGE)
    run("git", "update-ref", "refs/heads/main", head)
    new_commits.append(head)
    print("new commit:", head[:7])
    return head


def push_all(new_commits: list[str]) -> None:
    env = os.environ.copy()
    env["GIT_SSL_NO_VERIFY"] = "true"
    subprocess.run(
        ["git", "push", "--force", "origin", "main"],
        cwd=PLUGIN_DIR,
        check=True,
        env=env,
    )

    tag_commits = {
        "v1.0.0": new_commits[0],
        "v1.0.1": new_commits[3],
        "v1.0.2": new_commits[-1],
    }
    for tag in ("v1.0.1", "v1.1.0", "v1.0.0", "v1.0.2"):
        subprocess.run(
            ["git", "push", "origin", f":refs/tags/{tag}"],
            cwd=PLUGIN_DIR,
            env=env,
            capture_output=True,
        )
    for tag, commit in tag_commits.items():
        subprocess.run(
            ["git", "tag", "-f", "-a", tag, "-m", f"{tag} 发布", commit],
            cwd=PLUGIN_DIR,
            check=True,
        )
        subprocess.run(
            ["git", "push", "--force", "origin", tag],
            cwd=PLUGIN_DIR,
            check=True,
            env=env,
        )
    print("tags pushed:", ", ".join(tag_commits))


def sync_releases() -> None:
    existing = api("GET", f"https://api.github.com/repos/{REPO}/releases") or []
    for rel in existing:
        api("DELETE", f"https://api.github.com/repos/{REPO}/releases/{rel['id']}")
        print("deleted release:", rel.get("tag_name"))

    for tag, info in RELEASES.items():
        result = api(
            "POST",
            f"https://api.github.com/repos/{REPO}/releases",
            {
                "tag_name": tag,
                "name": tag,
                "body": info["body"].strip(),
                "draft": False,
                "prerelease": False,
            },
        )
        print("created release:", result["html_url"] if result else tag)


def main() -> None:
    os.chdir(PLUGIN_DIR)
    commits = rewrite_history()
    commit_current(commits)
    push_all(commits)
    sync_releases()
    print("done")


if __name__ == "__main__":
    main()
