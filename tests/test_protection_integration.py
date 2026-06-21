"""Integration tests for the protected-path guard using the DEFAULT system roots.

These pin the most important real-world property: the app must protect system
locations and the bare drive root, while still allowing ordinary user files on
the C: drive to be deleted (otherwise the cleaner is useless).
"""
import os
import subprocess

import pytest

from reclaim.core.deletion import delete, is_protected


def _make_junction(link: str, target: str) -> bool:
    """Create a directory junction (no admin needed). Return True on success."""
    try:
        res = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                             capture_output=True, text=True)
        return res.returncode == 0 and os.path.isdir(link)
    except OSError:
        return False


def test_default_roots_allow_ordinary_user_file_on_c_drive():
    # A normal file under the user's profile must NOT be protected, or the user
    # could never clean their own C: drive.
    user = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    candidate = os.path.join(user, "Downloads", "some_big_video.mp4")
    assert is_protected(candidate) is False


def test_default_roots_protect_bare_drive_root():
    drive_root = os.environ.get("SystemDrive", "C:") + os.sep
    assert is_protected(drive_root) is True


def test_default_roots_protect_windows_system_dir():
    windir = os.environ.get("SystemRoot", r"C:\Windows")
    assert is_protected(os.path.join(windir, "System32", "kernel32.dll")) is True


def test_default_roots_protect_program_files():
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    assert is_protected(os.path.join(pf, "SomeApp", "app.exe")) is True


def test_short_name_for_program_files_is_protected():
    """An 8.3 short name (PROGRA~1) must not bypass the guard (review M3)."""
    short = r"C:\PROGRA~1"
    if os.path.realpath(short).upper() == short.upper():
        pytest.skip("8.3 short names not available on this volume")
    assert is_protected(os.path.join(short, "SomeApp", "app.exe")) is True


def test_junction_into_protected_root_is_protected(tmp_path):
    """A junction pointing into a protected root must not bypass the guard (M2)."""
    protected = tmp_path / "protected_target"
    protected.mkdir()
    link = tmp_path / "sneaky_link"
    if not _make_junction(str(link), str(protected)):
        pytest.skip("could not create a junction on this system")
    candidate = os.path.join(str(link), "secret.txt")
    assert is_protected(candidate, protected_roots=[str(protected)]) is True


def test_permanent_delete_of_directory_junction_removes_only_the_link(tmp_path):
    """Permanently deleting a junction must remove the link, not the target (M1)."""
    target = tmp_path / "real_target"
    target.mkdir()
    (target / "keep.txt").write_text("important")
    link = tmp_path / "junction"
    if not _make_junction(str(link), str(target)):
        pytest.skip("could not create a junction on this system")

    # protected_roots set to an unrelated dir so the junction itself is deletable.
    result = delete([str(link)], permanent=True, protected_roots=[str(tmp_path / "nope")])
    assert result.deleted == 1
    assert not os.path.exists(str(link))          # link removed
    assert (target / "keep.txt").exists()         # target contents preserved
