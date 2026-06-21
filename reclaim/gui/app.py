"""Reclaim main GUI window (tkinter).

Wires the core engine to a desktop UI: pick a folder, scan it on a background
thread, browse a treemap + sortable detail table + category bars, and delete
selected items (Recycle Bin by default) through the protected-path guard.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from reclaim.core import analysis, report
from reclaim.core.config import load_config
from reclaim.core.constants import human_size
from reclaim.core.deletion import delete
from reclaim.core.models import ScanOptions, ScanResult
from reclaim.gui.widgets import CategoryBars, DetailTable, Treemap
from reclaim.gui.workers import ScanWorker


class ReclaimApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Reclaim — Disk Space Analyzer & Cleaner")
        self.geometry("1200x760")
        self.minsize(900, 600)

        self.config_data = load_config()
        self._worker: ScanWorker | None = None
        self._result: ScanResult | None = None
        self._scan_root = self.config_data.default_root

        self._build_toolbar()
        self._build_body()
        self._build_statusbar()

    # -- layout --------------------------------------------------------------
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=6)
        bar.pack(side="top", fill="x")

        ttk.Button(bar, text="Choose Folder…", command=self._choose_folder).pack(side="left")
        self.path_var = tk.StringVar(value=self._scan_root)
        ttk.Entry(bar, textvariable=self.path_var, width=50).pack(side="left", padx=4)
        ttk.Button(bar, text="Scan", command=self._start_scan).pack(side="left")
        ttk.Button(bar, text="Cancel", command=self._cancel_scan).pack(side="left", padx=(2, 10))

        ttk.Button(bar, text="Largest", command=self._show_largest).pack(side="left", padx=2)
        ttk.Button(bar, text="Duplicates", command=self._show_duplicates).pack(side="left", padx=2)
        ttk.Button(bar, text="Stale", command=self._show_stale).pack(side="left", padx=2)
        ttk.Button(bar, text="Export…", command=self._export).pack(side="left", padx=2)

        self.permanent_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Delete permanently", variable=self.permanent_var).pack(side="right")
        ttk.Button(bar, text="Delete Selected", command=self._delete_selected).pack(side="right", padx=6)

    def _build_body(self):
        self.bars = CategoryBars(self, height=150)
        self.bars.pack(side="top", fill="x", padx=6, pady=(0, 4))

        filter_row = ttk.Frame(self, padding=(6, 0))
        filter_row.pack(side="top", fill="x")
        ttk.Label(filter_row, text="Filter:").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self.table.apply_filter(self.filter_var.get()))
        ttk.Entry(filter_row, textvariable=self.filter_var, width=40).pack(side="left", padx=4)

        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(side="top", fill="both", expand=True, padx=6, pady=4)

        self.treemap = Treemap(paned, on_click=self._on_treemap_click)
        paned.add(self.treemap, weight=1)

        self.table = DetailTable(paned)
        paned.add(self.table, weight=2)

    def _build_statusbar(self):
        bar = ttk.Frame(self, padding=4)
        bar.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left")
        self.progress = ttk.Progressbar(bar, mode="determinate", length=200)
        self.progress.pack(side="right")
        self.free_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.free_var).pack(side="right", padx=10)

    # -- actions -------------------------------------------------------------
    def _choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.path_var.get() or "C:\\")
        if folder:
            self.path_var.set(folder)

    def _start_scan(self):
        root = self.path_var.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showerror("Reclaim", f"Not a valid folder:\n{root}")
            return
        self._scan_root = root
        self._update_free_space(root)
        self.status_var.set(f"Scanning {root} …")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self._worker = ScanWorker(ScanOptions(root=Path(root)))
        self._worker.start()
        self.after(100, self._poll_worker)

    def _cancel_scan(self):
        if self._worker:
            self._worker.cancel()
            self.status_var.set("Cancelling …")

    def _poll_worker(self):
        if not self._worker:
            return
        for kind, payload in self._worker.poll():
            if kind == "progress":
                self.status_var.set(f"Scanning … {payload.files_seen} files, "
                                    f"{human_size(payload.bytes_seen)}")
            elif kind == "error":
                self.progress.stop()
                self.progress.configure(mode="determinate")
                messagebox.showerror("Reclaim", f"Scan failed:\n{payload}")
                self._worker = None
                return
            elif kind == "result":
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self._apply_result(payload)
                self._worker = None
                return
        self.after(100, self._poll_worker)

    def _apply_result(self, result: ScanResult):
        self._result = result
        self.bars.update_stats(result.category_stats())
        self.table.set_files(result.files)
        self._populate_treemap()
        msg = (f"{result.total_count} files, {human_size(result.total_size)} "
               f"in {result.duration:.1f}s")
        if result.errors:
            msg += f"  ({len(result.errors)} skipped/inaccessible)"
        self.status_var.set(msg)

    def _populate_treemap(self):
        if not self._result:
            return
        dir_sizes = analysis.largest_dirs(self._result.files, n=40)
        items = [(os.path.basename(p.rstrip("\\/")) or p, size, p) for p, size in dir_sizes]
        self.treemap.set_items(items)

    def _on_treemap_click(self, path):
        # Filter the table to files within the clicked directory.
        self.filter_var.set(path)

    def _show_largest(self):
        if not self._guard_result():
            return
        self.table.set_files(self._result.top_files(200))
        self.status_var.set("Showing 200 largest files.")

    def _show_duplicates(self):
        if not self._guard_result():
            return
        self.status_var.set("Finding duplicates …")
        self.update_idletasks()
        groups = analysis.find_duplicates(self._result.files)
        wasted = sum(g.wasted for g in groups)
        paths = {p for g in groups for p in g.paths}
        dup_files = [f for f in self._result.files if f.path in paths]
        self.table.set_files(dup_files)
        messagebox.showinfo("Duplicates",
                            f"{len(groups)} duplicate groups.\n"
                            f"Reclaimable: {human_size(wasted)}")
        self.status_var.set(f"{len(groups)} duplicate groups — {human_size(wasted)} reclaimable.")

    def _show_stale(self):
        if not self._guard_result():
            return
        stale = analysis.find_stale(self._result.files, days=self.config_data.stale_days)
        self.table.set_files(stale)
        self.status_var.set(f"{len(stale)} files older than {self.config_data.stale_days} days.")

    def _export(self):
        if not self._guard_result():
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("JSON", "*.json")],
        )
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                report.to_json(self._result, path)
            else:
                report.to_csv(self._result, path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Reclaim", f"Export failed:\n{exc}")
            return
        messagebox.showinfo("Reclaim", f"Report written to:\n{path}")

    def _delete_selected(self):
        paths = self.table.selected_paths()
        if not paths:
            messagebox.showinfo("Reclaim", "No files selected.")
            return
        permanent = self.permanent_var.get()
        total = sum(self._file_size(p) for p in paths)
        method = "PERMANENTLY delete" if permanent else "move to the Recycle Bin"
        if not messagebox.askyesno(
            "Confirm delete",
            f"About to {method} {len(paths)} item(s) "
            f"totalling {human_size(total)}.\n\nProceed?",
        ):
            return
        result = delete(paths, permanent=permanent)
        protected = [p for p, r in result.failed if r == "protected"]
        summary = (f"Deleted {result.deleted}, freed {human_size(result.freed_bytes)}.")
        if protected:
            summary += f"\nRefused {len(protected)} protected system path(s)."
        other = [(p, r) for p, r in result.failed if r != "protected"]
        if other:
            summary += f"\n{len(other)} failed."
        messagebox.showinfo("Reclaim", summary)
        # Refresh: drop deleted files from the in-memory result.
        if self._result:
            deleted_set = set(paths) - {p for p, _ in result.failed}
            self._result.files[:] = [f for f in self._result.files if f.path not in deleted_set]
            self._apply_result(self._result)

    # -- helpers -------------------------------------------------------------
    def _guard_result(self) -> bool:
        if not self._result:
            messagebox.showinfo("Reclaim", "Run a scan first.")
            return False
        return True

    def _file_size(self, path) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def _update_free_space(self, root):
        try:
            usage = shutil.disk_usage(root)
            self.free_var.set(f"Free: {human_size(usage.free)} / {human_size(usage.total)}")
        except OSError:
            self.free_var.set("")


def run() -> None:
    """Launch the Reclaim GUI."""
    app = ReclaimApp()
    app.mainloop()


if __name__ == "__main__":
    run()
