from __future__ import annotations

import os
import time
from pathlib import Path

from PIL import Image

from astrbot_plugin_twrpg_query.card_renderer import (
    configure_cards_dir,
    get_cards_dir,
    save_card_png,
)

_CARDS_DIR = Path(__file__).resolve().parent / "runtime_cards"


def _cleanup_test_pngs() -> None:
    for name in ("fresh.png", "old.png"):
        try:
            (_CARDS_DIR / name).unlink()
        except FileNotFoundError:
            pass


def test_configure_cards_dir_writes_to_runtime_dir():
    previous = get_cards_dir()
    _cleanup_test_pngs()
    try:
        configure_cards_dir(str(_CARDS_DIR))
        path = save_card_png(Image.new("RGB", (2, 2)), "fresh.png")
        assert Path(path).parent == _CARDS_DIR.resolve()
        assert Path(path).exists()
    finally:
        configure_cards_dir(previous, cleanup=False)
        _cleanup_test_pngs()


def test_generated_card_cleanup_removes_expired_png():
    previous = get_cards_dir()
    _cleanup_test_pngs()
    try:
        configure_cards_dir(str(_CARDS_DIR))
        old_path = _CARDS_DIR / "old.png"
        old_path.write_bytes(b"old")
        old_mtime = time.time() - 4 * 24 * 60 * 60
        os.utime(old_path, (old_mtime, old_mtime))

        save_card_png(Image.new("RGB", (2, 2)), "fresh.png")

        assert not old_path.exists()
    finally:
        configure_cards_dir(previous, cleanup=False)
        _cleanup_test_pngs()
