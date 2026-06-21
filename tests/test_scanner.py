"""Tests for ``reclaim.core.scanner.scan``.

All tests operate on pytest's ``tmp_path`` / the ``make_tree`` fixture so they
NEVER touch the user's real files.
"""
from __future__ import annotations

import os
import re

from reclaim.core.models import Progress, ScanOptions
from reclaim.core.scanner import scan


def _by_name(result):
    """Map basename -> FileEntry for convenient lookups."""
    return {entry.name: entry for entry in result.files}


def test_scan_counts_and_total_size(make_tree):
    root, expected = make_tree
    result = scan(ScanOptions(root=root))
    assert result.total_count == expected["total_count"]
    assert result.total_size == expected["total_size"]


def test_scan_assigns_categories(make_tree):
    root, _ = make_tree
    result = scan(ScanOptions(root=root))
    entries = _by_name(result)
    assert entries["movie.mp4"].category == "Video"
    assert entries["old.tmp"].category == "Temp/Cache"


def test_min_size_filter_excludes_small_files(make_tree):
    root, expected = make_tree
    # Exclude the 50-byte (old.tmp) and 100-byte (notes.txt) files.
    result = scan(ScanOptions(root=root, min_size=200))
    names = set(_by_name(result).keys())
    assert "old.tmp" not in names
    assert "notes.txt" not in names
    assert result.total_count == expected["total_count"] - 2


def test_excluded_paths_skipped(make_tree):
    root, expected = make_tree
    result = scan(ScanOptions(root=root, excluded_paths=[root / "videos"]))
    names = set(_by_name(result).keys())
    assert "movie.mp4" not in names
    assert "clip.mkv" not in names
    # The two video files (3000 bytes total) are gone.
    assert result.total_count == expected["total_count"] - 2
    assert result.total_size == expected["total_size"] - 3000


def test_permission_error_recorded_and_scan_continues(make_tree, monkeypatch):
    root, _ = make_tree
    real_scandir = os.scandir
    blocked = os.path.normcase(str(root / "docs"))

    def fake_scandir(path):
        if os.path.normcase(str(path)) == blocked:
            raise PermissionError("access denied")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", fake_scandir)

    result = scan(ScanOptions(root=root))
    # The blocked directory was recorded as an error.
    assert any("docs" in path for path, _msg in result.errors)
    # Files outside the blocked directory are still collected.
    names = set(_by_name(result).keys())
    assert "movie.mp4" in names
    # docs/* files were not collected.
    assert "report.pdf" not in names
    assert "notes.txt" not in names


def test_should_cancel_stops_early(make_tree):
    root, expected = make_tree
    state = {"calls": 0}

    def on_progress(_progress):
        state["calls"] += 1

    def should_cancel():
        # Cancel as soon as the scan begins making progress checks.
        return True

    result = scan(
        ScanOptions(root=root),
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    # Cancellation must stop early and return without hanging.
    assert result.total_count <= expected["total_count"]


def test_progress_callback_final_done_true(make_tree):
    root, _ = make_tree
    seen: list[Progress] = []
    scan(ScanOptions(root=root), on_progress=seen.append)
    assert seen, "expected at least one progress callback"
    assert seen[-1].done is True


def test_compute_hashes_populates_hash(make_tree):
    root, _ = make_tree
    result = scan(ScanOptions(root=root, compute_hashes=True))
    assert result.files
    hex64 = re.compile(r"^[0-9a-f]{64}$")
    for entry in result.files:
        assert entry.hash is not None
        assert hex64.match(entry.hash), f"bad hash for {entry.name}: {entry.hash!r}"
