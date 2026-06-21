"""SAFETY-CRITICAL tests for ``reclaim.core.deletion``.

The protected-path guard is the single most important thing in the project.
Every test that exercises recycling MONKEYPATCHES ``send2trash.send2trash`` so
the real Recycle Bin is never touched. All filesystem work is under ``tmp_path``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from reclaim.core.deletion import delete, is_protected
from tests.conftest import write_file


# --------------------------------------------------------------------------- #
# is_protected                                                                 #
# --------------------------------------------------------------------------- #
def test_is_protected_true_for_root_and_descendants(tmp_path: Path):
    root = tmp_path / "fake_protected"
    nested = write_file(root / "deep" / "inner.txt", 5)

    roots = [str(root)]
    assert is_protected(root, protected_roots=roots) is True
    assert is_protected(nested, protected_roots=roots) is True


def test_is_protected_false_for_unrelated_path(tmp_path: Path):
    root = tmp_path / "fake_protected"
    root.mkdir()
    outside = write_file(tmp_path / "other" / "free.txt", 5)
    # A sibling whose name merely *starts with* the root name must NOT be
    # treated as living under the root ("...fake_protected_extra").
    sibling = tmp_path / "fake_protected_extra"
    sibling.mkdir()

    roots = [str(root)]
    assert is_protected(outside, protected_roots=roots) is False
    assert is_protected(sibling, protected_roots=roots) is False


# --------------------------------------------------------------------------- #
# delete: protection guard                                                     #
# --------------------------------------------------------------------------- #
def test_delete_refuses_protected_path_and_file_survives(tmp_path: Path):
    root = tmp_path / "fake_protected"
    f = write_file(root / "victim.txt", 123)

    result = delete([f], permanent=True, protected_roots=[str(root)])

    assert f.exists()  # MUST survive
    assert result.deleted == 0
    assert (str(f), "protected") in result.failed


# --------------------------------------------------------------------------- #
# delete: dry-run                                                              #
# --------------------------------------------------------------------------- #
def test_dry_run_deletes_nothing(tmp_path: Path):
    f = write_file(tmp_path / "keep.txt", 42)

    result = delete([f], dry_run=True)

    assert f.exists()
    assert result.method == "dry-run"
    assert result.attempted == 1


# --------------------------------------------------------------------------- #
# delete: recycle (monkeypatched send2trash)                                   #
# --------------------------------------------------------------------------- #
def test_recycle_calls_send2trash_without_touching_real_bin(tmp_path: Path, monkeypatch):
    calls: list = []
    monkeypatch.setattr("send2trash.send2trash", lambda p: calls.append(p))

    f = write_file(tmp_path / "trash_me.txt", 64)

    # Scope protection to an unrelated root so the default guard (which protects
    # the entire C:\ system drive, and therefore tmp_path) does not block this
    # filesystem-mechanics test.
    result = delete([f], protected_roots=[str(tmp_path / "guarded")])

    assert len(calls) == 1
    assert calls[0] == f
    assert result.method == "recycle"
    assert result.freed_bytes == 64
    assert result.deleted == 1


# --------------------------------------------------------------------------- #
# delete: permanent                                                            #
# --------------------------------------------------------------------------- #
def test_permanent_delete_removes_file(tmp_path: Path):
    f = write_file(tmp_path / "gone.txt", 10)

    result = delete([f], permanent=True, protected_roots=[str(tmp_path / "guarded")])

    assert not f.exists()
    assert result.method == "permanent"
    assert result.deleted == 1


# --------------------------------------------------------------------------- #
# delete: audit log                                                            #
# --------------------------------------------------------------------------- #
def test_audit_log_written(tmp_path: Path):
    f = write_file(tmp_path / "logged.txt", 77)
    log = tmp_path / "a.log"

    delete([f], permanent=True, audit_log=log,
           protected_roots=[str(tmp_path / "guarded")])

    lines = log.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["path"] == str(f)
    assert entry["size"] == 77
    assert entry["method"] == "permanent"
    assert "timestamp" in entry


# --------------------------------------------------------------------------- #
# delete: continues after an error                                             #
# --------------------------------------------------------------------------- #
def test_delete_continues_after_error(tmp_path: Path, monkeypatch):
    f1 = write_file(tmp_path / "f1.txt", 11)
    f2 = write_file(tmp_path / "f2.txt", 22)

    def fake_send2trash(p):
        if str(p) == str(f1):
            raise OSError("boom")
        # f2 succeeds (do nothing)

    monkeypatch.setattr("send2trash.send2trash", fake_send2trash)

    result = delete([f1, f2], protected_roots=[str(tmp_path / "guarded")])

    failed_paths = [p for p, _ in result.failed]
    assert str(f1) in failed_paths
    assert result.deleted == 1


# --------------------------------------------------------------------------- #
# delete: default protected roots block the real Windows dir                   #
# --------------------------------------------------------------------------- #
def test_default_protected_roots_block_windows_dir():
    assert is_protected(os.environ["SystemRoot"]) is True
