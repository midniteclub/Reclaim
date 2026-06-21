"""GUI widgets and the pure squarify() treemap geometry helper.

``squarify`` has no Tk dependency and is unit-tested directly. The widget classes
(:class:`CategoryBars`, :class:`Treemap`, :class:`DetailTable`) are thin Tk views.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from reclaim.core.constants import human_size


# --------------------------------------------------------------------------- #
# Pure geometry: squarified treemap                                           #
# --------------------------------------------------------------------------- #
def _layout_row(areas, x, y, dx, dy, horizontal):
    """Lay a group of areas along one axis, returning (rects, leftover)."""
    covered = sum(areas)
    rects = []
    if covered <= 0:
        return [(x, y, 0.0, 0.0) for _ in areas], (x, y, dx, dy)
    if horizontal:
        # stack vertically in a column of fixed width
        width = covered / dy
        cy = y
        for a in areas:
            h = a / width if width else 0.0
            rects.append((x, cy, width, h))
            cy += h
        leftover = (x + width, y, dx - width, dy)
    else:
        height = covered / dx
        cx = x
        for a in areas:
            w = a / height if height else 0.0
            rects.append((cx, y, w, height))
            cx += w
        leftover = (x, y + height, dx, dy - height)
    return rects, leftover


def _worst_ratio(areas, x, y, dx, dy, horizontal):
    rects, _ = _layout_row(areas, x, y, dx, dy, horizontal)
    worst = 1.0
    for _rx, _ry, w, h in rects:
        if w <= 0 or h <= 0:
            return float("inf")
        worst = max(worst, w / h, h / w)
    return worst


def _squarify_areas(areas, x, y, dx, dy):
    """Squarified layout of pre-scaled areas within (x, y, dx, dy)."""
    if not areas:
        return []
    if dx <= 0 or dy <= 0:
        return [(x, y, 0.0, 0.0) for _ in areas]

    horizontal = dx >= dy
    if len(areas) == 1:
        rects, _ = _layout_row(areas, x, y, dx, dy, horizontal)
        return rects

    # Grow the current row while it improves (lowers) the worst aspect ratio.
    i = 1
    while i < len(areas):
        if _worst_ratio(areas[:i], x, y, dx, dy, horizontal) < \
                _worst_ratio(areas[: i + 1], x, y, dx, dy, horizontal):
            break
        i += 1

    current = areas[:i]
    remaining = areas[i:]
    rects, leftover = _layout_row(current, x, y, dx, dy, horizontal)
    lx, ly, ldx, ldy = leftover
    return rects + _squarify_areas(remaining, lx, ly, ldx, ldy)


def squarify(values, x, y, w, h):
    """Return a list of ``(x, y, w, h)`` rects, one per input value, tiling the
    container so each rect's area is proportional to its value.

    Output rects are in the SAME order as ``values``.
    """
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        return []
    total = sum(vals)
    if total <= 0 or w <= 0 or h <= 0:
        return [(x, y, 0.0, 0.0) for _ in vals]

    scale = (w * h) / total
    order = sorted(range(n), key=lambda i: vals[i], reverse=True)
    areas = [vals[i] * scale for i in order]
    laid = _squarify_areas(areas, x, y, w, h)

    result: list[tuple] = [None] * n  # type: ignore[list-item]
    for orig_i, rect in zip(order, laid):
        result[orig_i] = rect
    return result


# --------------------------------------------------------------------------- #
# Tk widgets                                                                   #
# --------------------------------------------------------------------------- #
_PALETTE = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
]


class CategoryBars(tk.Frame):
    """Horizontal proportional bars, one per category."""

    def __init__(self, parent, height=160, **kw):
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, height=height, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._stats = []
        self.canvas.bind("<Configure>", lambda e: self._redraw())

    def update_stats(self, stats):
        self._stats = list(stats)
        self._redraw()

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        if not self._stats:
            c.create_text(10, 10, anchor="nw", text="No data — run a scan.",
                          fill="#888")
            return
        width = c.winfo_width() or 600
        max_size = max(s.total_size for s in self._stats) or 1
        row_h = 22
        y = 6
        for idx, s in enumerate(self._stats):
            color = _PALETTE[idx % len(_PALETTE)]
            bar_w = int((width - 220) * (s.total_size / max_size))
            c.create_rectangle(160, y, 160 + max(bar_w, 1), y + row_h - 6, fill=color, outline="")
            c.create_text(6, y + 6, anchor="nw", text=s.category, fill="#222")
            c.create_text(width - 6, y + 6, anchor="ne",
                          text=f"{human_size(s.total_size)} ({s.count})", fill="#222")
            y += row_h


class Treemap(tk.Frame):
    """Squarified treemap of (label, size, path) items."""

    def __init__(self, parent, on_click=None, **kw):
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, background="#1e1e1e")
        self.canvas.pack(fill="both", expand=True)
        self._items = []
        self._on_click = on_click
        self._rects = []
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<Button-1>", self._handle_click)

    def set_items(self, items):
        """items: list of (label, size, path)."""
        self._items = [it for it in items if it[1] > 0]
        self._redraw()

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        self._rects = []
        if not self._items:
            c.create_text(10, 10, anchor="nw", text="No data — run a scan.", fill="#aaa")
            return
        w = c.winfo_width() or 600
        h = c.winfo_height() or 400
        sizes = [it[1] for it in self._items]
        rects = squarify(sizes, 0, 0, w, h)
        for idx, ((label, size, path), (rx, ry, rw, rh)) in enumerate(zip(self._items, rects)):
            color = _PALETTE[idx % len(_PALETTE)]
            c.create_rectangle(rx, ry, rx + rw, ry + rh, fill=color, outline="#1e1e1e")
            self._rects.append((rx, ry, rx + rw, ry + rh, path))
            if rw > 60 and rh > 24:
                c.create_text(rx + 4, ry + 4, anchor="nw",
                              text=f"{label}\n{human_size(size)}", fill="white",
                              font=("Segoe UI", 8))

    def _handle_click(self, event):
        for x0, y0, x1, y1, path in self._rects:
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                if self._on_click:
                    self._on_click(path)
                return


class DetailTable(tk.Frame):
    """Sortable, filterable file detail table."""

    COLUMNS = ("name", "size", "category", "format", "modified", "path")
    HEADINGS = {
        "name": "Name", "size": "Size", "category": "Category",
        "format": "Format", "modified": "Modified", "path": "Path",
    }

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.tree = ttk.Treeview(self, columns=self.COLUMNS, show="headings",
                                 selectmode="extended")
        for col in self.COLUMNS:
            self.tree.heading(col, text=self.HEADINGS[col],
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=120, anchor="w")
        self.tree.column("size", width=90, anchor="e")
        self.tree.column("path", width=320)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._files = []
        self._filter = ""
        self._sort_col = "size"
        self._sort_desc = True
        self._row_to_path = {}

    def set_files(self, files):
        self._files = list(files)
        self._refresh()

    def apply_filter(self, text):
        self._filter = (text or "").lower()
        self._refresh()

    def selected_paths(self):
        return [self._row_to_path[i] for i in self.tree.selection()
                if i in self._row_to_path]

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = col == "size"
        self._refresh()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._row_to_path = {}

        rows = self._files
        if self._filter:
            rows = [f for f in rows
                    if self._filter in f.name.lower() or self._filter in f.path.lower()
                    or self._filter in f.category.lower()]

        keymap = {
            "name": lambda f: f.name.lower(),
            "size": lambda f: f.size,
            "category": lambda f: f.category.lower(),
            "format": lambda f: f.ext.lower(),
            "modified": lambda f: f.modified,
            "path": lambda f: f.path.lower(),
        }
        rows = sorted(rows, key=keymap[self._sort_col], reverse=self._sort_desc)

        import datetime
        for f in rows[:5000]:  # cap rows inserted for responsiveness
            modified = datetime.datetime.fromtimestamp(f.modified).strftime("%Y-%m-%d %H:%M")
            iid = self.tree.insert("", "end", values=(
                f.name, human_size(f.size), f.category, f.ext or "—", modified, f.path,
            ))
            self._row_to_path[iid] = f.path
