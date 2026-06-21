"""Export a ScanResult to CSV or JSON."""
from __future__ import annotations

import csv
import json
from datetime import datetime

from reclaim.core import constants
from reclaim.core.models import ScanResult

CSV_HEADER = ["name", "category", "ext", "size", "size_human", "modified_iso", "path"]


def to_csv(result: ScanResult, path) -> None:
    """Write ``result.files`` to ``path`` as CSV with a fixed header row."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADER)
        for f in result.files:
            writer.writerow([
                f.name,
                f.category,
                f.ext,
                f.size,
                constants.human_size(f.size),
                datetime.fromtimestamp(f.modified).isoformat(),
                f.path,
            ])


def to_json(result: ScanResult, path) -> None:
    """Write ``result`` to ``path`` as JSON with a summary + files structure."""
    data = {
        "summary": {
            "root": result.root,
            "total_size": result.total_size,
            "total_count": result.total_count,
            "duration": result.duration,
            "categories": [
                {"category": c.category, "count": c.count, "total_size": c.total_size}
                for c in result.category_stats()
            ],
        },
        "files": [
            {
                "name": f.name,
                "path": f.path,
                "ext": f.ext,
                "category": f.category,
                "size": f.size,
                "modified": f.modified,
            }
            for f in result.files
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
