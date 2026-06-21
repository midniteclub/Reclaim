"""Filesystem scanner for Reclaim.

Recursively walks a directory tree with :func:`os.scandir`, building a
:class:`~reclaim.core.models.FileEntry` per file and aggregating the totals into
a :class:`~reclaim.core.models.ScanResult`.

The walk is resilient: per-directory and per-entry errors are recorded in
``ScanResult.errors`` and the scan continues. It supports cooperative
cancellation, progress callbacks, size/exclusion filtering, reparse-point
(junction/symlink) avoidance and optional SHA-256 hashing.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Callable

from reclaim.core import constants
from reclaim.core.models import FileEntry, Progress, ScanOptions, ScanResult

# Windows file attribute bitmasks (used only when ``st_file_attributes`` exists).
_FILE_ATTRIBUTE_HIDDEN = 0x2
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400

# Emit a progress callback roughly every this many files.
_PROGRESS_INTERVAL = 500

# SHA-256 read chunk size: 1 MiB.
_HASH_CHUNK = 1024 * 1024


def _normalized_excludes(excluded_paths: list[Path]) -> list[str]:
    """Return absolute, normcased string forms of the excluded paths."""
    out: list[str] = []
    for p in excluded_paths:
        try:
            out.append(os.path.normcase(os.path.abspath(str(p))))
        except OSError:
            continue
    return out


def _is_excluded(abspath: str, excludes: list[str]) -> bool:
    """True if ``abspath`` is equal to, or nested under, any excluded path."""
    key = os.path.normcase(abspath)
    for ex in excludes:
        if key == ex or key.startswith(ex + os.sep):
            return True
    return False


def _is_reparse_point(entry: os.DirEntry) -> bool:
    """Detect junctions/symlinks/reparse points for a directory entry."""
    try:
        if entry.is_symlink():
            return True
    except OSError:
        pass
    try:
        st = entry.stat(follow_symlinks=False)
    except OSError:
        return False
    if hasattr(st, "st_file_attributes"):
        return bool(st.st_file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def _compute_hash(path: str) -> str | None:
    """Return the SHA-256 hex digest of a file, or ``None`` on error."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(_HASH_CHUNK)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def scan(
    options: ScanOptions,
    on_progress: Callable[[Progress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ScanResult:
    """Scan the tree under ``options.root`` and return a :class:`ScanResult`."""
    start = time.perf_counter()

    root_path = os.path.abspath(str(options.root))
    excludes = _normalized_excludes(options.excluded_paths)

    files: list[FileEntry] = []
    errors: list[tuple[str, str]] = []
    files_seen = 0
    bytes_seen = 0
    current_path = ""
    cancelled = False

    def emit_progress(done: bool = False) -> None:
        if on_progress is not None:
            on_progress(
                Progress(
                    files_seen=files_seen,
                    bytes_seen=bytes_seen,
                    current_path=current_path,
                    done=done,
                )
            )

    # Iterative DFS so deep trees don't blow the Python recursion limit.
    stack: list[str] = [root_path]
    while stack:
        if should_cancel is not None and should_cancel():
            cancelled = True
            break

        dir_path = stack.pop()
        if _is_excluded(dir_path, excludes):
            continue

        try:
            scandir_it = os.scandir(dir_path)
        except OSError as exc:
            errors.append((dir_path, str(exc)))
            continue

        with scandir_it:
            while True:
                try:
                    entry = next(scandir_it)
                except StopIteration:
                    break
                except OSError as exc:
                    errors.append((dir_path, str(exc)))
                    break

                entry_path = entry.path
                if _is_excluded(entry_path, excludes):
                    continue

                try:
                    is_dir = entry.is_dir(follow_symlinks=options.follow_symlinks)
                except OSError as exc:
                    errors.append((entry_path, str(exc)))
                    continue

                if is_dir:
                    # Avoid descending into reparse points unless asked to.
                    if not options.follow_symlinks and _is_reparse_point(entry):
                        continue
                    stack.append(entry_path)
                    continue

                # Regular file (or something stat-able as a file).
                try:
                    st = entry.stat()
                except OSError as exc:
                    errors.append((entry_path, str(exc)))
                    continue

                size = st.st_size
                if size < options.min_size:
                    continue

                name = entry.name
                ext = os.path.splitext(name)[1].lower()
                category = constants.EXT_TO_CATEGORY.get(
                    ext, constants.DEFAULT_CATEGORY
                )

                is_hidden = False
                if hasattr(st, "st_file_attributes"):
                    is_hidden = bool(st.st_file_attributes & _FILE_ATTRIBUTE_HIDDEN)

                try:
                    is_readonly = not os.access(entry_path, os.W_OK)
                except OSError:
                    is_readonly = False

                file_hash = None
                if options.compute_hashes:
                    file_hash = _compute_hash(entry_path)

                files.append(
                    FileEntry(
                        path=entry_path,
                        name=name,
                        ext=ext,
                        category=category,
                        size=size,
                        created=st.st_ctime,
                        modified=st.st_mtime,
                        accessed=st.st_atime,
                        is_hidden=is_hidden,
                        is_readonly=is_readonly,
                        hash=file_hash,
                    )
                )
                files_seen += 1
                bytes_seen += size
                current_path = entry_path

                if files_seen % _PROGRESS_INTERVAL == 0:
                    emit_progress()
                    if should_cancel is not None and should_cancel():
                        cancelled = True
                        break

        if cancelled:
            break

    total_count = len(files)
    total_size = sum(f.size for f in files)
    duration = time.perf_counter() - start

    # Always emit a final progress with done=True (even for zero files).
    emit_progress(done=True)

    return ScanResult(
        root=root_path,
        files=files,
        total_size=total_size,
        total_count=total_count,
        errors=errors,
        duration=duration,
    )
