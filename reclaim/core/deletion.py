"""SAFETY-CRITICAL deletion module.

The protected-path guard (:func:`is_protected`) is the single most important
piece of the whole project. It is fail-safe: anything that cannot be resolved
is treated as protected.

``delete`` recycles (via ``send2trash``) by default, can delete permanently,
supports a dry-run mode, an optional JSON-lines audit log, and a progress
callback. It NEVER deletes a protected path.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
from datetime import datetime

import send2trash

from reclaim.core import constants
from reclaim.core.models import DeletionResult


def is_protected(path, protected_roots: list[str] | None = None) -> bool:
    """Return ``True`` if ``path`` is, or lives under, a protected system root.

    The candidate path and each root are canonicalized with ``os.path.realpath``
    (resolves symlinks, junctions, and 8.3 short names like ``PROGRA~1``) +
    ``os.path.normcase`` (case-insensitive on Windows). A path is protected if it
    EQUALS a root or is a strict descendant of one. The descendant check is
    separator-aware so ``C:\\WindowsFoo`` is NOT considered under ``C:\\Windows``.

    Fail-safe: if anything cannot be resolved, the path is treated as protected.
    """
    if protected_roots is None:
        protected_roots = constants.system_protected_roots()

    try:
        cand = os.path.normcase(os.path.realpath(os.fspath(path)))
    except (OSError, ValueError, TypeError):
        return True  # cannot resolve -> fail safe

    # Protect a bare filesystem/drive root (e.g. "C:\\") as an EXACT path: a root
    # is its own parent. This blocks deleting the root itself without
    # subtree-protecting the whole drive (its descendants stay deletable).
    if os.path.dirname(cand) == cand:
        return True

    for root in protected_roots:
        try:
            root_norm = os.path.normcase(os.path.realpath(os.fspath(root)))
        except (OSError, ValueError, TypeError):
            # An unresolvable root shouldn't weaken protection; skip it.
            continue

        if cand == root_norm:
            return True

        # Separator-aware prefix check: the root, plus a separator, must be a
        # prefix of the candidate. This rejects sibling names like
        # "C:\\WindowsFoo" that merely share a textual prefix with "C:\\Windows".
        root_with_sep = root_norm.rstrip(os.sep) + os.sep
        if cand.startswith(root_with_sep):
            return True

        # commonpath cross-check (handles mixed separators / "." segments).
        try:
            if os.path.commonpath([cand, root_norm]) == root_norm:
                return True
        except ValueError:
            # Different drives / mixed absolute-relative -> not under this root.
            continue

    return False


def _is_reparse_point(path: str) -> bool:
    """True for a directory junction or symlink (a reparse point)."""
    try:
        attrs = os.lstat(path).st_file_attributes
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return os.path.islink(path)


def _path_size(path: str) -> int:
    """Return the size of a file, or the recursive size of a directory.

    A reparse point (junction/symlink) reports 0: deleting it removes only the
    link, freeing no real bytes from its target.
    """
    try:
        if _is_reparse_point(path):
            return 0
        if os.path.isdir(path) and not os.path.islink(path):
            total = 0
            for dirpath, _dirnames, filenames in os.walk(path):
                for fn in filenames:
                    fp = os.path.join(dirpath, fn)
                    try:
                        if not os.path.islink(fp):
                            total += os.path.getsize(fp)
                    except OSError:
                        continue
            return total
        return os.path.getsize(path)
    except OSError:
        return 0


def delete(
    paths,
    *,
    permanent: bool = False,
    dry_run: bool = False,
    on_progress=None,
    audit_log=None,
    protected_roots: list[str] | None = None,
) -> DeletionResult:
    """Delete (or recycle, or simulate deleting) the given paths.

    Protected paths are NEVER deleted: they are recorded in ``failed`` with the
    reason ``"protected"`` and skipped. In ``dry_run`` mode nothing is touched
    and no audit log is written, but the would-delete tally is reported.
    """
    paths = list(paths)
    total = len(paths)

    if dry_run:
        method = "dry-run"
    elif permanent:
        method = "permanent"
    else:
        method = "recycle"

    attempted = 0
    deleted = 0
    freed_bytes = 0
    failed: list[tuple[str, str]] = []
    done = 0

    for path in paths:
        attempted += 1
        spath = str(path)

        if is_protected(path, protected_roots):
            failed.append((spath, "protected"))
            done += 1
            if on_progress is not None:
                on_progress(done, total)
            continue

        size = _path_size(os.fspath(path))

        if dry_run:
            # Would be deleted; touch nothing, write no audit log.
            deleted += 1
            freed_bytes += size
            done += 1
            if on_progress is not None:
                on_progress(done, total)
            continue

        try:
            if permanent:
                if os.path.isdir(path) and not _is_reparse_point(os.fspath(path)):
                    shutil.rmtree(path)
                elif os.path.isdir(path):
                    # Directory junction/symlink: remove the link only, never
                    # recurse into (or delete) its target.
                    os.rmdir(path)
                else:
                    os.remove(path)
            else:
                send2trash.send2trash(path)

            deleted += 1
            freed_bytes += size

            if audit_log is not None:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "path": spath,
                    "size": size,
                    "method": method,
                }
                with open(audit_log, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
        except Exception as exc:  # noqa: BLE001 - record and continue
            failed.append((spath, str(exc)))

        done += 1
        if on_progress is not None:
            on_progress(done, total)

    return DeletionResult(
        attempted=attempted,
        deleted=deleted,
        failed=failed,
        freed_bytes=freed_bytes,
        method=method,
    )
