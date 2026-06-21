"""Tests for core data models."""
from reclaim.core.models import (
    CategoryStat,
    DuplicateGroup,
    FileEntry,
    ScanResult,
)


def _file(name, category, size):
    return FileEntry(
        path=f"C:/x/{name}", name=name, ext=".x", category=category, size=size,
        created=0.0, modified=0.0, accessed=0.0,
    )


def test_duplicate_group_wasted_bytes():
    g = DuplicateGroup(hash="abc", size=100, paths=["a", "b", "c"])
    assert g.wasted == 200  # size * (count - 1)


def test_duplicate_group_single_path_wastes_nothing():
    g = DuplicateGroup(hash="abc", size=100, paths=["a"])
    assert g.wasted == 0


def test_category_stats_aggregates_and_sorts_desc():
    files = [
        _file("a.mp4", "Video", 1000),
        _file("b.mkv", "Video", 2000),
        _file("c.jpg", "Images", 500),
    ]
    result = ScanResult(root="C:/x", files=files, total_size=3500,
                        total_count=3, errors=[], duration=0.0)
    stats = result.category_stats()
    assert stats[0] == CategoryStat(category="Video", count=2, total_size=3000)
    assert stats[1] == CategoryStat(category="Images", count=1, total_size=500)


def test_top_files_returns_largest_first():
    files = [
        _file("small.txt", "Documents", 100),
        _file("big.mp4", "Video", 5000),
        _file("mid.jpg", "Images", 1000),
    ]
    result = ScanResult(root="C:/x", files=files, total_size=6100,
                        total_count=3, errors=[], duration=0.0)
    top = result.top_files(2)
    assert [f.name for f in top] == ["big.mp4", "mid.jpg"]
