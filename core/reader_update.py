"""读档器更新检查响应格式化。"""

from __future__ import annotations

from typing import Any


def format_reader_update(body: dict[str, Any]) -> str:
    version = str(body.get("version") or "").strip() or "未知"
    notes = str(body.get("releaseNotes") or "").strip()

    lines = [f"软件版本：{version}", "更新内容："]
    if notes:
        for line in notes.splitlines():
            text = line.strip()
            if text:
                lines.append(text)
    else:
        lines.append("（暂无）")
    return "\n".join(lines)
