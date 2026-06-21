"""Tests for CSV/JSON report export."""
from __future__ import annotations

import csv
import json
from datetime import datetime

from reclaim.core import constants
from reclaim.core import report
from reclaim.core.models import FileEntry, ScanResult


def make_result() -> ScanResult:
    """Build a small ScanResult directly (no filesystem scan)."""
    files = [
        FileEntry(
            path=r"C:\root\videos\movie.mp4",
            name="movie.mp4",
            ext=".mp4",
            category="Video",
            size=1000,
            created=1_600_000_000.0,
            modified=1_600_000_100.0,
            accessed=1_600_000_200.0,
        ),
        FileEntry(
            path=r"C:\root\images\photo.jpg",
            name="photo.jpg",
            ext=".jpg",
            category="Images",
            size=500,
            created=1_600_000_300.0,
            modified=1_600_000_400.0,
            accessed=1_600_000_500.0,
        ),
        FileEntry(
            path=r"C:\root\docs\report.pdf",
            name="report.pdf",
            ext=".pdf",
            category="Documents",
            size=300,
            created=1_600_000_600.0,
            modified=1_600_000_700.0,
            accessed=1_600_000_800.0,
        ),
    ]
    return ScanResult(
        root=r"C:\root",
        files=files,
        total_size=1800,
        total_count=3,
        errors=[],
        duration=1.25,
    )


def test_to_csv_has_header_and_row_per_file(tmp_path):
    result = make_result()
    out = tmp_path / "r.csv"
    report.to_csv(result, out)

    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    expected_header = ["name", "category", "ext", "size", "size_human", "modified_iso", "path"]
    assert rows[0] == expected_header

    data_rows = rows[1:]
    assert len(data_rows) == len(result.files)

    # Find the known movie.mp4 row and verify name + size land in the right columns.
    movie_row = next(r for r in data_rows if r[0] == "movie.mp4")
    assert movie_row[0] == "movie.mp4"          # name column
    assert movie_row[3] == "1000"               # size column
    assert movie_row[6] == r"C:\root\videos\movie.mp4"  # path column


def test_to_json_summary_totals(tmp_path):
    result = make_result()
    out = tmp_path / "r.json"
    report.to_json(result, out)

    with open(out, encoding="utf-8") as fh:
        data = json.load(fh)

    summary = data["summary"]
    assert summary["total_count"] == result.total_count
    assert summary["total_size"] == result.total_size
    assert len(data["files"]) == result.total_count

    cats = summary["categories"]
    assert isinstance(cats, list)
    assert len(cats) > 0
    for c in cats:
        assert isinstance(c, dict)
        assert set(c.keys()) == {"category", "count", "total_size"}


def test_to_csv_size_human_column(tmp_path):
    result = make_result()
    out = tmp_path / "r.csv"
    report.to_csv(result, out)

    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    movie_row = next(r for r in rows[1:] if r[0] == "movie.mp4")
    movie = next(f for f in result.files if f.name == "movie.mp4")
    assert movie_row[4] == constants.human_size(movie.size)
    # also confirm modified_iso column matches
    assert movie_row[5] == datetime.fromtimestamp(movie.modified).isoformat()
