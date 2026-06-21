"""Tests for the read-only junk scanner (``reclaim.core.junk``).

All tests operate on ``tmp_path`` and pass explicit ``locations`` so nothing
real is ever touched. ``scan_junk`` is READ-ONLY and must never delete.
"""
from __future__ import annotations

from pathlib import Path

from reclaim.core.junk import scan_junk
from tests.conftest import write_file


def test_scan_junk_sums_sizes(tmp_path: Path):
    junk = tmp_path / "FakeTemp"
    write_file(junk / "a.tmp", 100)
    write_file(junk / "b.tmp", 250)
    write_file(junk / "nested" / "c.tmp", 400)
    expected_total = 100 + 250 + 400

    result = scan_junk(locations=[("FakeTemp", str(junk), True)])

    assert len(result) == 1
    cat = result[0]
    assert cat.name == "FakeTemp"
    assert cat.paths == [str(junk)]
    assert cat.total_size == expected_total
    assert cat.safe_to_delete is True


def test_scan_junk_skips_missing_paths(tmp_path: Path):
    real = tmp_path / "real"
    write_file(real / "x.tmp", 10)
    missing = tmp_path / "does_not_exist"

    result = scan_junk(locations=[
        ("Missing", str(missing), True),
        ("Real", str(real), True),
    ])

    names = [c.name for c in result]
    assert names == ["Real"]
    assert result[0].total_size == 10


def test_scan_junk_is_readonly(tmp_path: Path):
    junk = tmp_path / "FakeTemp"
    f1 = write_file(junk / "a.tmp", 100)
    f2 = write_file(junk / "nested" / "b.tmp", 200)

    scan_junk(locations=[("FakeTemp", str(junk), True)])

    assert f1.exists()
    assert f2.exists()
    assert junk.exists()
