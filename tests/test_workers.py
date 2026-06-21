"""Tests for the threaded scan worker (headless — no Tk required)."""
import time

from reclaim.core.models import ScanOptions
from reclaim.core.scanner import scan
from reclaim.gui.workers import ScanWorker


def _drain_until_result(worker, timeout=10.0):
    """Poll the worker until a result/error event arrives or timeout."""
    deadline = time.time() + timeout
    events = []
    while time.time() < deadline:
        events.extend(worker.poll())
        if any(kind in ("result", "error") for kind, _ in events):
            break
        if not worker.is_alive():
            events.extend(worker.poll())  # final drain
            break
        time.sleep(0.01)
    return events


def test_worker_produces_result_matching_direct_scan(make_tree):
    root, expected = make_tree
    worker = ScanWorker(ScanOptions(root=root))
    worker.start()
    events = _drain_until_result(worker)

    results = [payload for kind, payload in events if kind == "result"]
    assert results, "worker should emit a result event"
    result = results[0]
    direct = scan(ScanOptions(root=root))
    assert result.total_count == direct.total_count == expected["total_count"]
    assert result.total_size == direct.total_size == expected["total_size"]


def test_worker_emits_progress_events(make_tree):
    root, _ = make_tree
    worker = ScanWorker(ScanOptions(root=root))
    worker.start()
    events = _drain_until_result(worker)
    kinds = [kind for kind, _ in events]
    assert "progress" in kinds


def test_worker_cancel_returns_without_hanging(make_tree):
    root, _ = make_tree
    worker = ScanWorker(ScanOptions(root=root))
    worker.cancel()  # cancel before start
    worker.start()
    events = _drain_until_result(worker, timeout=10.0)
    # Must terminate (a result event or the thread finished) — the point is no hang.
    assert any(kind == "result" for kind, _ in events) or not worker.is_alive()
