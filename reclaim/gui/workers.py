"""Background scanning for the GUI.

``ScanWorker`` runs :func:`reclaim.core.scanner.scan` on a daemon thread and
publishes events onto a thread-safe queue so the Tk main loop can poll without
blocking. Events are ``(kind, payload)`` tuples where ``kind`` is one of
``"progress"`` (payload: :class:`Progress`), ``"result"`` (payload:
:class:`ScanResult`), or ``"error"`` (payload: the exception).
"""
from __future__ import annotations

import queue
import threading

from reclaim.core.models import Progress, ScanOptions
from reclaim.core.scanner import scan


class ScanWorker:
    """Run a scan on a background thread, exposing progress via a queue."""

    def __init__(self, options: ScanOptions):
        self._options = options
        self._queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Begin scanning on a daemon thread."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        """Request cancellation; the scan stops at the next checkpoint."""
        self._cancel.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def poll(self) -> list[tuple[str, object]]:
        """Return (and remove) all events queued since the last poll."""
        events: list[tuple[str, object]] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    # -- internal ------------------------------------------------------------
    def _run(self) -> None:
        def on_progress(p: Progress) -> None:
            self._queue.put(("progress", p))

        try:
            result = scan(
                self._options,
                on_progress=on_progress,
                should_cancel=self._cancel.is_set,
            )
            self._queue.put(("result", result))
        except Exception as exc:  # noqa: BLE001 - surface to the UI thread
            self._queue.put(("error", exc))
