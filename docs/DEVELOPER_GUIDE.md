# Reclaim — Developer Guide

For developers and AI agents extending or maintaining Reclaim. Read this top to
bottom and you'll understand the whole system.

---

## 1. Philosophy & architecture

Reclaim is **layered** so that all real logic lives in a pure-Python, UI-free
**core** engine that is fully unit-tested. The CLI and GUI are thin wrappers.

```
              ┌─────────────┐        ┌─────────────┐
              │  reclaim.gui │        │ reclaim.cli │
              │ (tkinter)    │        │ (argparse)  │
              └──────┬───────┘        └──────┬──────┘
                     │   both depend only on │
                     ▼                       ▼
                 ┌───────────────────────────────┐
                 │        reclaim.core            │
                 │  models · constants · scanner  │
                 │  categorizer · analysis · junk │
                 │  deletion · report · config    │
                 └───────────────────────────────┘
                 depends only on the stdlib + send2trash
```

**Dependency rule:** `core` imports nothing from `cli`/`gui`. This keeps the engine
testable without a display and means the safety guard is shared by every caller.

Why this matters: the single most important invariant — *never delete a protected
system path* — is enforced in `core/deletion.py`. Because both UIs route deletion
through that one function, neither UI can bypass it.

---

## 2. Repository layout

```
reclaim/
  __init__.py        __version__
  __main__.py        entry point: CLI if argv given, else GUI
  core/
    models.py        dataclasses (slots): ScanOptions, FileEntry, DirNode,
                     CategoryStat, DuplicateGroup, ScanResult, DeletionResult,
                     JunkCategory, Progress
    constants.py     CATEGORY_EXTENSIONS, EXT_TO_CATEGORY, DEFAULT_CATEGORY,
                     system_protected_roots(), JUNK_LOCATIONS(), human_size()
    scanner.py       scan(options, on_progress, should_cancel) -> ScanResult
    categorizer.py   categorize(ext_or_name) -> str
    analysis.py      hash_file, largest_files, largest_dirs, find_duplicates,
                     find_stale, find_empty_dirs
    junk.py          scan_junk(locations=None) -> list[JunkCategory]
    deletion.py      is_protected(...), delete(...)  ← SAFETY-CRITICAL
    report.py        to_csv(result, path), to_json(result, path)
    config.py        AppConfig, load_config(path), save_config(cfg, path)
  cli/main.py        main(argv) -> int  (subcommands: scan/dupes/junk/clean-junk/delete)
  gui/
    workers.py       ScanWorker — threaded scan + event queue
    widgets.py       squarify() + CategoryBars, Treemap, DetailTable
    app.py           ReclaimApp(tk.Tk), run()
tests/               pytest suite (74 tests), conftest.py with make_tree fixture
docs/                this guide, the user guide, spec & plan
run.ps1/run.bat      run from source
build.ps1            PyInstaller → dist/Reclaim.exe
requirements.txt     send2trash (runtime); pytest/pyinstaller (dev)
```

---

## 3. Data model (`core/models.py`)

All dataclasses use `slots=True` (a full C: scan can create ~1M `FileEntry`).

| Type | Key fields |
|---|---|
| `ScanOptions` | `root: Path`, `follow_symlinks=False`, `include_hidden=True`, `excluded_paths`, `min_size=0`, `compute_hashes=False` |
| `FileEntry` | `path, name, ext, category, size, created, modified, accessed, is_hidden, is_readonly, hash` |
| `CategoryStat` | `category, count, total_size` |
| `DuplicateGroup` | `hash, size, paths`; `.wasted == size*(len(paths)-1)` |
| `DirNode` | `path, total_size, file_count, children` |
| `ScanResult` | `root, files, total_size, total_count, errors, duration`; `.category_stats()`, `.top_files(n)` |
| `DeletionResult` | `attempted, deleted, failed, freed_bytes, method` (`"recycle"｜"permanent"｜"dry-run"`) |
| `JunkCategory` | `name, paths, total_size, safe_to_delete` |
| `Progress` | `files_seen, bytes_seen, current_path, done` |

---

## 4. Module APIs

### scanner.py
```python
scan(options: ScanOptions,
     on_progress: Callable[[Progress], None] | None = None,
     should_cancel: Callable[[], bool] | None = None) -> ScanResult
```
Iterative `os.scandir` walk. Skips files below `min_size` and anything under
`excluded_paths`. Does **not** follow reparse points (junctions/symlinks) unless
`follow_symlinks`. Per-entry `PermissionError`/`OSError` are recorded in
`result.errors` and the scan continues. Emits `Progress` periodically and a final
`done=True`. Honours `should_cancel()` between directories. Optional SHA-256 hashing.

### categorizer.py
```python
categorize(ext_or_name: str) -> str
```
Accepts `".mp4"`, `"mp4"`, or `"movie.mp4"` (case-insensitive). Unknown → `"Other"`.
(Note: `scanner.py` computes categories directly from `constants.EXT_TO_CATEGORY`
for speed; `categorize` is the convenience entry point for callers/tests.)

### analysis.py
- `hash_file(path, partial_bytes=None)` — SHA-256 hex, chunked; partial mode hashes
  only the first N bytes (used to prune duplicate candidates cheaply).
- `largest_files(files, n=20)` / `largest_dirs(files, n=20)`.
- `find_duplicates(files)` — group by size → partial hash (64 KiB) → full hash;
  returns `DuplicateGroup`s sorted by `.wasted` desc.
- `find_stale(files, days, now=None)` — files older than `days` before `now`.
- `find_empty_dirs(root)` — directories with no files anywhere beneath them.

### junk.py
```python
scan_junk(locations=None) -> list[JunkCategory]
```
Defaults to `constants.JUNK_LOCATIONS()`. Sums sizes of existing locations; skips
missing ones. **Read-only — never deletes.**

### deletion.py — SAFETY-CRITICAL
```python
is_protected(path, protected_roots=None) -> bool
delete(paths, *, permanent=False, dry_run=False,
       on_progress=None, audit_log=None, protected_roots=None) -> DeletionResult
```
- `is_protected` normalizes with `abspath` + `normcase`; a path is protected if it
  equals or is a strict, separator-aware descendant of any root (so `C:\WindowsFoo`
  is **not** under `C:\Windows`). A bare drive root (its own parent) is protected as
  an exact path. Unresolvable paths → **protected** (fail-safe).
- `delete` refuses protected paths (recorded in `failed` as `"protected"`, never
  raised), supports dry-run (touches nothing, writes no audit), recycles via
  `send2trash` by default or removes permanently, measures freed bytes, writes a
  JSON-lines audit entry per real deletion, and continues past per-path errors.

> **Invariant to preserve:** all deletion in the app must go through `delete()`.
> Never call `os.remove`/`send2trash` directly from the CLI/GUI.

### report.py / config.py
- `to_csv` / `to_json` — full per-file detail + summary.
- `AppConfig` + `load_config`/`save_config` — JSON at `~/.reclaim/config.json`
  (default root, excluded paths, `stale_days`, theme, named scan `profiles`).

### gui/workers.py
`ScanWorker(options)` runs `scan` on a daemon thread and publishes
`("progress"|"result"|"error", payload)` events on a `queue.Queue`. The Tk loop
polls via `after()`. Headless-testable.

### gui/widgets.py
`squarify(values, x, y, w, h)` is a pure squarified-treemap layout returning one
`(x, y, w, h)` rect per input value, **in input order**, with areas proportional to
values. The Tk widgets (`CategoryBars`, `Treemap`, `DetailTable`) are thin views.

---

## 5. Testing

```powershell
python -m pip install pytest
python -m pytest            # 74 tests, ~1s
```
- Tests live in `tests/`; `conftest.py` provides `write_file(...)` and the
  `make_tree` fixture (a known tree under `tmp_path` with documented totals).
- **Everything uses `tmp_path`** — tests never touch real user files or the real
  Recycle Bin (`send2trash` is monkeypatched).
- `test_protection_integration.py` pins the real-world guard behavior with the
  **default** protected roots: ordinary user files on C: are deletable; system dirs
  and the bare drive root are not. `test_cli.py` proves the CLI refuses to delete
  `C:\Windows\explorer.exe`.
- TDD was used throughout: write the failing test, watch it fail, implement, pass.

---

## 6. Extending

**Add a file category or extension:** edit `CATEGORY_EXTENSIONS` in
`core/constants.py`. `EXT_TO_CATEGORY` is derived automatically. Add a test to
`tests/test_constants.py` asserting the new mapping (and that no extension appears in
two categories).

**Add a junk location:** add a `(name, path, safe_to_delete)` candidate in
`JUNK_LOCATIONS()` in `core/constants.py`. Only `safe_to_delete=True` locations are
ever auto-cleaned. Keep `safe_to_delete=False` for anything you're unsure about
(it'll be reported but not cleaned).

**Add a protected location:** add it in `system_protected_roots()` in
`core/constants.py`. Add a test in `tests/test_protection_integration.py`.

**Add a CLI command:** add a subparser + handler in `cli/main.py`, route any
deletion through `core.deletion.delete`, and add tests to `tests/test_cli.py`.

---

## 7. Packaging

`build.ps1` runs PyInstaller (`--onefile --windowed --name Reclaim
--collect-all send2trash reclaim/__main__.py`) → `dist/Reclaim.exe`. The exe is a
GUI app on double-click and a CLI when given arguments (`Reclaim.exe scan C:\`).

---

## 8. Why registry & startup cleaning are excluded (design decision)

Reclaim intentionally does **not** clean the Windows Registry or manage
startup/services:

- **Registry "cleaning" is high-risk, low-reward.** Modern Windows is unaffected by
  "orphaned" registry keys; removing the wrong key can prevent apps — or Windows —
  from booting. The space saved is negligible. Reputable engineers (and Microsoft)
  advise against it. A *safe* file cleaner shouldn't ship a foot-gun.
- **Startup/service management** can disable drivers or security software. It belongs
  in Task Manager / Autoruns where the user has full context, not in a bulk cleaner.

Reclaim's scope is deliberately **files and disk space**, where deletion is
recoverable (Recycle Bin), auditable, and guarded. If you add risky features later,
keep them behind the same engine-level guard + audit-log + dry-run discipline used by
`core/deletion.py`.
