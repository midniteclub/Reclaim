"""Tests for category map, protected paths, junk locations, and human_size."""
from reclaim.core import constants


def test_human_size_zero():
    assert constants.human_size(0) == "0 B"


def test_human_size_kilobytes():
    assert constants.human_size(1024) == "1.0 KB"
    assert constants.human_size(1536) == "1.5 KB"


def test_human_size_megabytes_gigabytes():
    assert constants.human_size(1048576) == "1.0 MB"
    assert constants.human_size(1073741824) == "1.0 GB"


def test_human_size_bytes_below_kilobyte():
    assert constants.human_size(512) == "512 B"


def test_ext_to_category_lookup():
    assert constants.EXT_TO_CATEGORY[".mp4"] == "Video"
    assert constants.EXT_TO_CATEGORY[".pdf"] == "Documents"
    assert constants.EXT_TO_CATEGORY[".iso"] == "Disk Images"


def test_no_extension_appears_in_two_categories():
    seen: dict[str, str] = {}
    for category, exts in constants.CATEGORY_EXTENSIONS.items():
        for ext in exts:
            assert ext not in seen, f"{ext} in both {seen.get(ext)} and {category}"
            seen[ext] = category


def test_system_protected_roots_includes_windows():
    roots = constants.system_protected_roots()
    assert roots, "protected roots must not be empty"
    joined = " ".join(roots).lower()
    assert "windows" in joined


def test_junk_locations_returns_tuples():
    locs = constants.JUNK_LOCATIONS()
    assert isinstance(locs, list)
    for item in locs:
        name, path, safe = item
        assert isinstance(name, str) and isinstance(path, str)
        assert isinstance(safe, bool)
