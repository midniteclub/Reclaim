# Reclaim — Disk Space Analyzer & Cleaner — Design Spec

**Date:** 2026-06-21
**Status:** Approved (autonomous; user delegated all decisions and asked not to be prompted)
**Author:** Claude (Opus 4.8) via superpowers brainstorming

---

## 1. Purpose & Goal

Build a **standalone, free** Windows desktop application that lets a user:

1. **Scan** their computer (e.g. the `C:` drive or any chosen folder) and discover what is consuming disk space.
2. **Categorize** everything found (by type, size, age, location, duplication).
3. **Inspect** items in fine detail — file size, format, name, path, timestamps, attributes, metadata.
4. **Delete** selected categories *or* individual items safely.

The motivation is to replace paid tools like CCleaner / WizTree / TreeSize subscriptions with a self-owned, auditable, no-cost program.

### Non-goals (deliberately excluded)
- **Windows Registry cleaning** — high risk, low real benefit, can brick a system. Excluded for safety.
- **Startup-program / service management** — out of scope; risk of disabling needed services.
- **Real-time background monitoring / scheduling daemon** — YAGNI for v1.
- **Cloud, accounts, telemetry** — none. Fully offline and private.

---

## 2. Key Decisions & Rationale

| Decision | Choice | Rationale |
|---|---|---|
| Language/runtime | **Python 3.10** (already installed) | No runtime to install; rich filesystem stdlib; fast TDD with pytest; packageable to `.exe`. |
| GUI toolkit | **tkinter / ttk** (stdlib) | Zero external dependency → genuinely standalone; `Treeview` gives tree + sortable detail columns; `Canvas` for treemap/bar viz. Optional `customtkinter` theme used only if present (graceful degrade). |
| Safe deletion | **`send2trash`** (Recycle Bin) | Recoverable by default; the single most important safety property of a delete tool. |
| Testing | **pytest** | Standard; temp-filesystem fixtures (`tmp_path`) make the engine fully testable without touching real user data. |
| Packaging | **PyInstaller** one-file `Reclaim.exe` | Delivers a true standalone app; build script provided. App also runs as `python -m reclaim`. |
| Architecture | **Layered: core / cli / gui** | The engine (bulk of logic) is UI-free and 100% unit-testable; CLI and GUI are thin wrappers. |

---

## 3. Architecture

```
reclaim/
├── __init__.py
├── __main__.py            # `python -m reclaim` → launches GUI (or CLI if args given)
├── core/
│   ├── __init__.py
│   ├── models.py          # FileEntry, DirNode, ScanResult, CategoryStat, DuplicateGroup, DeletionResult, ScanOptions, Progress
│   ├── constants.py       # category→extension map, protected paths, junk locations, human-size helpers
│   ├── scanner.py         # recursive walk (os.scandir), size rollups, progress + cancellation
│   ├── categorizer.py     # extension → category classification
│   ├── analysis.py        # largest files/dirs, duplicates, stale files, empty folders
│   ├── junk.py            # enumerate known-safe temp/cache junk locations
│   ├── deletion.py        # safe delete (recycle/permanent), protected-path guard, audit log
│   ├── report.py          # CSV / JSON export
│   └── config.py          # load/save JSON config & scan profiles
├── cli/
│   ├── __init__.py
│   └── main.py            # argparse CLI: scan, report, find-dupes, clean-junk, delete
└── gui/
    ├── __init__.py
    ├── app.py             # main window, wiring
    ├── widgets.py         # treemap canvas, detail table, category bars
    └── workers.py         # background-thread scanning with queue-based progress
```

**Dependency direction:** `gui` → `core`, `cli` → `core`. `core` depends on nothing but the stdlib + `send2trash`. No reverse dependencies.

---

## 4. Core Data Model (`core/models.py`)

All dataclasses use `__slots__` for memory efficiency (a full `C:` scan can be ~1M files).

- **`ScanOptions`** — `root: Path`, `follow_symlinks=False`, `include_hidden=True`, `excluded_paths: list[Path]`, `min_size: int=0`, `compute_hashes=False`.
- **`FileEntry`** — `path: str`, `name`, `ext`, `category: str`, `size: int`, `created: float`, `modified: float`, `accessed: float`, `is_hidden: bool`, `is_readonly: bool`, `hash: str|None`.
- **`DirNode`** — `path`, `total_size`, `file_count`, `children` (built lazily / for treemap).
- **`CategoryStat`** — `category`, `count`, `total_size`.
- **`DuplicateGroup`** — `hash`, `size`, `paths: list[str]`, `wasted: int` (= size × (count−1)).
- **`ScanResult`** — `root`, `files: list[FileEntry]`, `total_size`, `total_count`, `errors: list[(path, reason)]`, `duration`, `category_stats`, helper methods (`top_files(n)`, `by_category()`).
- **`DeletionResult`** — `attempted`, `deleted`, `failed: list[(path, reason)]`, `freed_bytes`, `method`.
- **`Progress`** — `files_seen`, `bytes_seen`, `current_path`, `done: bool` (passed to a callback for the GUI progress bar; checked for cancellation).

---

## 5. Component Behaviour

### 5.1 Scanner (`scanner.py`)
- Uses `os.scandir` recursively; reads `stat` from the cached `DirEntry` where possible.
- **Does not follow reparse points** (junctions/symlinks) unless `follow_symlinks=True` — prevents infinite loops and double counting.
- Catches `PermissionError`/`OSError` per entry, records them in `ScanResult.errors`, and continues (a C: scan always hits locked files).
- Calls a `progress_callback(Progress)` periodically; aborts cleanly if a `should_cancel()` predicate returns true.
- Returns a `ScanResult` with all `FileEntry` items and aggregated `DirNode` rollups.

### 5.2 Categorizer (`categorizer.py`)
- Pure function `categorize(ext) -> str` driven by the map in `constants.py`.
- Categories: **Video, Audio, Images, Documents, Spreadsheets, Archives, Installers/Executables, Code, Disk Images, Fonts, Temp/Cache, System, Other**.
- Unknown extensions → `Other`.

### 5.3 Analysis (`analysis.py`)
- `largest_files(result, n)` / `largest_dirs(result, n)`.
- `find_duplicates(files)` — group by size → for each multi-file size group, compute a fast partial hash (first 64 KiB) → only fully hash (SHA-256, chunked) the partial-hash collisions. Returns `DuplicateGroup`s sorted by wasted bytes.
- `find_stale(files, days)` — files not modified/accessed within N days.
- `find_empty_dirs(root)` — directories containing no files recursively.

### 5.4 Junk detector (`junk.py`)
- **Whitelist only.** Enumerates known-safe locations: `%TEMP%`, `C:\Windows\Temp`, per-browser caches (Chrome/Edge/Firefox cache dirs under the user profile), Windows thumbnail cache, `*.tmp`, `*.log` in temp dirs, Recycle Bin size, Windows `Prefetch` (size report only). Each returns a `JunkCategory(name, paths, total_size, safe_to_delete: bool)`.
- Never invents arbitrary paths; everything is derived from documented Windows locations + the current user profile.

### 5.5 Deletion (`deletion.py`) — safety-critical
- `is_protected(path) -> bool`: true if the path is, or is inside, any protected root: `C:\Windows`, `C:\Program Files`, `C:\Program Files (x86)`, `C:\ProgramData`, the drive root itself, the Python install dir, the Reclaim app dir, and the system boot/pagefile/hiberfil files. Comparison is done on resolved, normalized, case-insensitive paths.
- `delete(paths, *, permanent=False, dry_run=False, on_progress=None) -> DeletionResult`:
  - Refuses (records failure, never raises) any protected path.
  - `dry_run=True` → reports what *would* happen, deletes nothing.
  - `permanent=False` → `send2trash` (Recycle Bin).
  - `permanent=True` → `os.remove` / `shutil.rmtree`.
  - Appends every real deletion to an **audit log** (`~/.reclaim/deletions.log`, JSONL).
- The guard is enforced **inside** `delete`, not just in the UI, so the CLI, GUI, and any future caller all inherit it.

### 5.6 Report (`report.py`)
- `to_csv(result, path)` and `to_json(result, path)` — full per-file detail + a summary block (totals, category stats, top files).

### 5.7 Config (`config.py`)
- JSON config at `~/.reclaim/config.json`: default root, excluded paths, stale-days threshold, theme, named **scan profiles**.

---

## 6. CLI (`cli/main.py`)

```
reclaim scan <path> [--json out.json] [--csv out.csv] [--top N] [--min-size SZ]
reclaim dupes <path> [--json out.json]
reclaim junk [--list]                       # show junk; safe, read-only
reclaim clean-junk [--confirm]              # default dry-run; --confirm to act (Recycle Bin)
reclaim delete <path...> [--permanent] [--confirm]   # default dry-run
```
- Deletion subcommands are **dry-run unless `--confirm`** and print a clear summary (count + total size) first.

---

## 7. GUI (`gui/`)

- **Left:** folder/treemap view — pick a root, scan, see a treemap (Canvas) + a directory tree (`Treeview`) sized by space; click to drill in.
- **Right / bottom:** sortable detail table (name, size, category, format, modified, path) with **search/filter** box; multi-select.
- **Top:** category breakdown bars + disk free-space summary; buttons: Scan, Cancel, Find Duplicates, Find Large, Find Stale, Clean Junk, Export, Delete Selected.
- Scanning runs on a **background thread**; progress + cancellation via a thread-safe queue (`gui/workers.py`) so the UI never freezes.
- Delete actions show a confirmation dialog (count, total size, recycle-vs-permanent) and route through `core.deletion` (protected-path guard always applies).

---

## 8. Error Handling

- Per-file permission/OS errors are collected, not fatal; surfaced in a "Skipped (N)" report.
- Deletion failures are collected into `DeletionResult.failed`; never crash the run.
- Protected-path attempts are reported as refusals, not errors.
- GUI catches worker exceptions and shows a dialog instead of dying.

---

## 9. Testing Strategy (TDD)

- **pytest**, tests written **before** implementation for every core module.
- Filesystem-touching code is tested against `tmp_path` (real temp dirs), never the user's real files.
- `send2trash` and OS deletion are monkeypatched / dry-run in tests; **a dedicated test asserts protected paths are NEVER deleted** (the single most important test).
- Coverage targets: scanner aggregation, categorizer mapping, duplicate grouping, stale/empty detection, junk enumeration (mocked dirs), deletion guard + dry-run + audit log, CSV/JSON round-trip, config load/save.
- The GUI is smoke-tested (imports + constructs without a display where feasible); logic lives in core, so GUI test surface is small.

---

## 10. Build / Distribution

- `requirements.txt`: `send2trash`, `pytest` (dev). (`customtkinter` optional.)
- `build.ps1` → PyInstaller one-file `dist/Reclaim.exe` (windowed).
- `run.ps1` / `run.bat` → run from source without building.
- `README.md` + `docs/USER_GUIDE.md` + `docs/DEVELOPER_GUIDE.md` so future users/agents understand it.

---

## 11. Parallelization Plan (subagents)

Shared `models.py` + `constants.py` + project skeleton + `conftest.py` are created **first** (by orchestrator) and committed. Then independent modules are built in parallel by subagents, each owning a **disjoint** set of files, each doing TDD:

- **Agent A:** `scanner.py` (+ tests)
- **Agent B:** `categorizer.py`, `analysis.py` (+ tests)
- **Agent C:** `junk.py`, `deletion.py` (+ tests) — safety-critical
- **Agent D:** `report.py`, `config.py` (+ tests)

CLI and GUI integration (depend on all core modules) are done by the orchestrator after the core merges and tests are green.

---

## 12. Success Criteria

1. `pytest` passes (engine fully green, protected-path guard proven).
2. CLI can scan a folder and emit CSV/JSON with correct totals.
3. GUI launches, scans a chosen folder without freezing, shows categories + details, and can delete selected items to the Recycle Bin.
4. No deletion of any protected system path is possible through any interface.
5. Documentation enables a new user/agent to run, use, and extend the app.
