from core.reader_update import format_reader_update


SAMPLE = {
    "version": "2.0.5",
    "releaseNotes": (
        '调整：1、历史存档改为按"存档名/年份/月"分目录保存，例如 "历史存档\\mxdc\\2026年\\07月\\..."。\n'
        '调整：2、设置页移除"历史存档最大保存数量"显示，不再按数量上限自动删除旧历史。\n'
        '新增：3、设置页增加"删除历史存档"入口，可按月份、年份或全部清理历史存档。\n'
        "优化：4、再次优化部分性能。"
    ),
    "downloadUrl": "https://example.com/twrpg.zip",
    "downloadUrlFallback": "",
}


def test_format_reader_update():
    text = format_reader_update(SAMPLE)
    assert text.startswith("软件版本：2.0.5")
    assert "更新内容：" in text
    assert "调整：1、" in text
    assert "新增：3、" in text
    assert "downloadUrl" not in text
    assert "example.com" not in text


def test_format_reader_update_empty_notes():
    text = format_reader_update({"version": "1.0.0", "releaseNotes": ""})
    assert "软件版本：1.0.0" in text
    assert "（暂无）" in text
