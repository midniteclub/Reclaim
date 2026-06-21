"""Integration tests for the protected-path guard using the DEFAULT system roots.

These pin the most important real-world property: the app must protect system
locations and the bare drive root, while still allowing ordinary user files on
the C: drive to be deleted (otherwise the cleaner is useless).
"""
import os

from reclaim.core.deletion import is_protected


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
