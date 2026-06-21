"""Shared pytest fixtures and helpers.

Everything here operates on pytest's ``tmp_path`` so tests NEVER touch the
user's real files.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest


def write_file(path: Path, size_bytes: int = 0, content: bytes | None = None,
               mtime: float | None = None) -> Path:
    """Create a file with an exact size (or explicit content) and optional mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if content is None:
        content = b"\0" * size_bytes
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def make_tree(tmp_path: Path):
    """Build a known directory tree and return (root, expected) where ``expected``
    records the totals so tests can assert against them.

    Layout::

        root/
          videos/movie.mp4        (1000 bytes)
          videos/clip.mkv         (2000 bytes)
          images/photo.jpg        ( 500 bytes)
          docs/report.pdf         ( 300 bytes)
          docs/notes.txt          ( 100 bytes)
          junk/old.tmp            (  50 bytes, mtime ~2 years ago)
          empty_dir/              (no files)
    """
    root = tmp_path / "root"
    old_mtime = time.time() - 730 * 86400  # ~2 years ago

    files = {
        root / "videos" / "movie.mp4": 1000,
        root / "videos" / "clip.mkv": 2000,
        root / "images" / "photo.jpg": 500,
        root / "docs" / "report.pdf": 300,
        root / "docs" / "notes.txt": 100,
    }
    for p, sz in files.items():
        write_file(p, sz)
    write_file(root / "junk" / "old.tmp", 50, mtime=old_mtime)
    (root / "empty_dir").mkdir(parents=True, exist_ok=True)

    expected = {
        "total_count": 6,
        "total_size": 1000 + 2000 + 500 + 300 + 100 + 50,  # 3950
        "categories": {
            "Video": (2, 3000),
            "Images": (1, 500),
            "Documents": (2, 400),
            "Temp/Cache": (1, 50),
        },
    }
    return root, expected
