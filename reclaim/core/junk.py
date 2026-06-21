"""Read-only scanner for known junk / temp / cache locations.

``scan_junk`` walks each whitelisted location and sums the bytes of every file
beneath it. It is strictly READ-ONLY: it never deletes, moves, or modifies
anything on disk.
"""
from __future__ import annotations

import os

from reclaim.core import constants
from reclaim.core.models import JunkCategory


def _dir_size(path: str) -> int:
    """Recursively sum the sizes of all files under ``path``.

    Per-entry ``OSError`` (permission denied, race deletion, broken link) is
    ignored so a single unreadable file never aborts the scan.
    """
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += _dir_size(entry.path)
                except OSError:
                    continue
    except OSError:
        return total
    return total


def scan_junk(
    locations: list[tuple[str, str, bool]] | None = None,
) -> list[JunkCategory]:
    """Return a :class:`JunkCategory` for each existing junk location.

    Locations whose path does not exist (or is not a directory) are skipped.
    This function performs no deletion of any kind.
    """
    if locations is None:
        locations = constants.JUNK_LOCATIONS()

    categories: list[JunkCategory] = []
    for name, path, safe in locations:
        if not path or not os.path.isdir(path):
            continue
        categories.append(
            JunkCategory(
                name=name,
                paths=[path],
                total_size=_dir_size(path),
                safe_to_delete=safe,
            )
        )
    return categories
