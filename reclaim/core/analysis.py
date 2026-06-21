"""Analysis helpers: hashing, largest files/dirs, duplicates, stale & empty dirs."""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from reclaim.core.models import DuplicateGroup, FileEntry

_CHUNK = 65536
_PARTIAL_BYTES = 65536


def hash_file(path, partial_bytes: int | None = None) -> str:
    """Return the sha256 hex digest of ``path``.

    If ``partial_bytes`` is given, only the first ``partial_bytes`` bytes are
    hashed. Reads are chunked to keep memory bounded for large files.
    """
    h = hashlib.sha256()
    remaining = partial_bytes if partial_bytes is not None else None
    with open(path, "rb") as fh:
        while True:
            if remaining is not None:
                if remaining <= 0:
                    break
                to_read = min(_CHUNK, remaining)
            else:
                to_read = _CHUNK
            chunk = fh.read(to_read)
            if not chunk:
                break
            h.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return h.hexdigest()


def largest_files(files: list[FileEntry], n: int = 20) -> list[FileEntry]:
    """Return the ``n`` largest files, largest first."""
    return sorted(files, key=lambda f: f.size, reverse=True)[:n]


def largest_dirs(files: list[FileEntry], n: int = 20) -> list[tuple[str, int]]:
    """Return the ``n`` directories with the largest summed file size.

    Files are grouped by their immediate parent directory
    (``os.path.dirname``). Returns ``(dirpath, total_size)`` sorted descending.
    """
    sizes: dict[str, int] = {}
    for f in files:
        parent = os.path.dirname(f.path)
        sizes[parent] = sizes.get(parent, 0) + f.size
    ranked = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:n]


def find_duplicates(files: list[FileEntry]) -> list[DuplicateGroup]:
    """Find sets of files with identical content.

    Strategy: group by size, prune with a partial (first 64 KiB) hash, then
    confirm with a full hash. Returns one :class:`DuplicateGroup` per set of
    >=2 identical files, sorted by wasted bytes descending.
    """
    by_size: dict[int, list[FileEntry]] = {}
    for f in files:
        by_size.setdefault(f.size, []).append(f)

    groups: list[DuplicateGroup] = []
    for size, entries in by_size.items():
        if len(entries) < 2:
            continue

        # Prune within the size group by a partial hash.
        by_partial: dict[str, list[FileEntry]] = {}
        for entry in entries:
            try:
                ph = hash_file(entry.path, _PARTIAL_BYTES)
            except OSError:
                continue
            by_partial.setdefault(ph, []).append(entry)

        for candidates in by_partial.values():
            if len(candidates) < 2:
                continue

            # Confirm with the full hash.
            by_full: dict[str, list[FileEntry]] = {}
            for entry in candidates:
                try:
                    fh = hash_file(entry.path)
                except OSError:
                    continue
                by_full.setdefault(fh, []).append(entry)

            for full_hash, matched in by_full.items():
                if len(matched) < 2:
                    continue
                groups.append(
                    DuplicateGroup(
                        hash=full_hash,
                        size=size,
                        paths=[e.path for e in matched],
                    )
                )

    groups.sort(key=lambda g: g.wasted, reverse=True)
    return groups


def find_stale(files: list[FileEntry], days: int, now: float | None = None) -> list[FileEntry]:
    """Return files whose ``modified`` time is older than ``days`` before ``now``."""
    if now is None:
        now = time.time()
    cutoff = now - days * 86400
    return [f for f in files if f.modified < cutoff]


def find_empty_dirs(root) -> list[str]:
    """Return directories under ``root`` that contain no files anywhere beneath them.

    A directory is "empty" if its entire subtree contains zero files (it may
    still contain other empty subdirectories). Returns absolute path strings.
    """
    root = Path(root)
    empty: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath == str(root):
            # Skip the root itself; we only report subdirectories.
            continue
        if not _has_file_below(dirpath):
            empty.append(str(Path(dirpath)))
    return empty


def _has_file_below(dirpath: str) -> bool:
    """True if ``dirpath`` contains at least one file anywhere in its subtree."""
    for _, _, filenames in os.walk(dirpath):
        if filenames:
            return True
    return False
