"""Smoke tests: the GUI modules import and the main window constructs."""
import tkinter

import pytest


def test_gui_modules_import():
    import reclaim.gui.app  # noqa: F401
    import reclaim.gui.widgets  # noqa: F401
    import reclaim.gui.workers  # noqa: F401


def test_app_constructs_and_destroys(make_tree):
    try:
        from reclaim.gui.app import ReclaimApp
        app = ReclaimApp()
    except tkinter.TclError as exc:
        pytest.skip(f"no display available: {exc}")
    try:
        root, expected = make_tree
        # Feed a real scan result through the UI layer without a full scan run.
        from reclaim.core.scanner import scan
        from reclaim.core.models import ScanOptions
        app._apply_result(scan(ScanOptions(root=root)))
        app.update_idletasks()
        assert app._result.total_count == expected["total_count"]
    finally:
        app.destroy()
