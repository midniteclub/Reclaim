"""Tests for reclaim.core.analysis."""
from __future__ import annotations

import os
import time
from pathlib import Path

from reclaim.core.analysis import (
    find_duplicates,
    find_empty_dirs,
    find_stale,
    hash_file,
    largest_dirs,
    largest_files,
)
from reclaim.core.models import FileEntry


def write_file(path: Path, content: bytes = b"") -> Path:
    """Local helper mirroring conftest.write_file (kept self-contained so the
    test module imports cleanly regardless of conftest's path placement)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _entry(path: str, size: int, modified: float = 0.0) -> FileEntry:
    """Build a FileEntry with sensible defaults for analysis tests."""
    p = Path(path)
    return FileEntry(
        path=str(p),
        name=p.name,
        ext=p.suffix.lower(),
        category="Other",
        size=size,
        created=0.0,
        modified=modified,
        accessed=0.0,
    )


# --------------------------------------------------------------------------- #
# hash_file                                                                    #
# --------------------------------------------------------------------------- #
def test_hash_file_identical_content_same_hash(tmp_path: Path):
    a = write_file(tmp_path / "a.bin", content=b"hello world")
    b = write_file(tmp_path / "b.bin", content=b"hello world")
    c = write_file(tmp_path / "c.bin", content=b"different content")

    assert hash_file(a) == hash_file(b)
    assert hash_file(a) != hash_file(c)


def test_hash_file_partial_only_reads_prefix(tmp_path: Path):
    prefix = b"x" * 100
    a = write_file(tmp_path / "a.bin", content=prefix + b"AAAA")
    b = write_file(tmp_path / "b.bin", content=prefix + b"BBBB")

    assert hash_file(a, 100) == hash_file(b, 100)
    assert hash_file(a) != hash_file(b)


# --------------------------------------------------------------------------- #
# largest_files                                                                #
# --------------------------------------------------------------------------- #
def test_largest_files_returns_top_n_desc():
    files = [
        _entry("d:/a", 10),
        _entry("d:/b", 50),
        _entry("d:/c", 30),
        _entry("d:/d", 20),
    ]
    top = largest_files(files, n=2)
    assert len(top) == 2
    assert [f.size for f in top] == [50, 30]


# --------------------------------------------------------------------------- #
# largest_dirs                                                                 #
# --------------------------------------------------------------------------- #
def test_largest_dirs_sums_by_parent():
    files = [
        _entry("d:/one/a", 100),
        _entry("d:/one/b", 200),
        _entry("d:/two/c", 50),
    ]
    dirs = largest_dirs(files, n=10)
    as_dict = dict(dirs)
    # Derive expected dir keys from the stored (OS-normalized) FileEntry paths
    # so the assertion is robust to path separator normalization on Windows.
    dir_one = os.path.dirname(files[0].path)
    dir_two = os.path.dirname(files[2].path)
    assert as_dict[dir_one] == 300
    assert as_dict[dir_two] == 50
    # sorted desc by summed size
    assert [size for _, size in dirs] == [300, 50]


# --------------------------------------------------------------------------- #
# find_duplicates                                                              #
# --------------------------------------------------------------------------- #
def test_find_duplicates_groups_identical(tmp_path: Path):
    content = b"duplicate content here" * 10
    size = len(content)
    p1 = write_file(tmp_path / "dup1.bin", content=content)
    p2 = write_file(tmp_path / "dup2.bin", content=content)
    p3 = write_file(tmp_path / "dup3.bin", content=content)
    # A unique file of a DIFFERENT size so it never joins a size group.
    p4 = write_file(tmp_path / "unique.bin", content=b"unique" * 3)

    files = [
        _entry(str(p1), size),
        _entry(str(p2), size),
        _entry(str(p3), size),
        _entry(str(p4), len(b"unique" * 3)),
    ]
    groups = find_duplicates(files)
    assert len(groups) == 1
    group = groups[0]
    assert len(group.paths) == 3
    assert group.size == size
    assert group.wasted == 2 * size


def test_find_duplicates_same_size_different_content_not_grouped(tmp_path: Path):
    a = write_file(tmp_path / "a.bin", content=b"A" * 64)
    b = write_file(tmp_path / "b.bin", content=b"B" * 64)
    files = [_entry(str(a), 64), _entry(str(b), 64)]
    assert find_duplicates(files) == []


# --------------------------------------------------------------------------- #
# find_stale                                                                   #
# --------------------------------------------------------------------------- #
def test_find_stale_returns_only_old():
    now = time.time()
    old = _entry("d:/old", 1, modified=now - 400 * 86400)
    recent = _entry("d:/recent", 1, modified=now - 1 * 86400)
    stale = find_stale([old, recent], days=180, now=now)
    assert stale == [old]


# --------------------------------------------------------------------------- #
# find_empty_dirs                                                              #
# --------------------------------------------------------------------------- #
def test_find_empty_dirs(tmp_path: Path):
    root = tmp_path / "root"
    (root / "empty").mkdir(parents=True)
    write_file(root / "full" / "file.txt", content=b"data")

    empty = find_empty_dirs(root)
    assert empty == [str(root / "empty")]
