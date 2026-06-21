# Reclaim Disk Cleaner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a free, standalone Windows app (Python) that scans the disk, categorizes what consumes space, shows fine-grained per-file detail, and safely deletes selected categories or items.

**Architecture:** Layered. A pure-Python, UI-free `core` engine (fully TDD'd) holds all logic; thin `cli` (argparse) and `gui` (tkinter) layers wrap it. Deletion safety (Recycle Bin default, protected-path guard, dry-run, audit log) is enforced inside the engine so every caller inherits it.

**Tech Stack:** Python 3.10, stdlib (`os.scandir`, `pathlib`, `hashlib`, `tkinter/ttk`), `send2trash` (Recycle Bin), `pytest` (tests), PyInstaller (packaging).

---

## File Structure

| File | Responsibility |
|---|---|
| `reclaim/__init__.py` | package marker + version |
| `reclaim/__main__.py` | entry: GUI if no args, else CLI |
| `reclaim/core/models.py` | dataclasses (slots): ScanOptions, FileEntry, DirNode, CategoryStat, DuplicateGroup, ScanResult, DeletionResult, JunkCategory, Progress |
| `reclaim/core/constants.py` | category↔ext map, protected paths, junk locations, `human_size`, `categorize` helper inputs |
| `reclaim/core/scanner.py` | recursive scan, size rollups, progress, cancel, error capture |
| `reclaim/core/categorizer.py` | ext → category |
| `reclaim/core/analysis.py` | largest files/dirs, duplicates, stale, empty dirs |
| `reclaim/core/junk.py` | enumerate whitelist junk/temp/cache locations |
| `reclaim/core/deletion.py` | safe delete + protected-path guard + audit log |
| `reclaim/core/report.py` | CSV / JSON export |
| `reclaim/core/config.py` | load/save config + scan profiles |
| `reclaim/cli/main.py` | argparse CLI |
| `reclaim/gui/app.py` | main window + wiring |
| `reclaim/gui/widgets.py` | treemap canvas, detail table, category bars |
| `reclaim/gui/workers.py` | background scan thread + progress queue |
| `tests/test_*.py` | one test module per core module |
| `requirements.txt`, `build.ps1`, `run.ps1`, `run.bat` | deps + build/run |
| `README.md`, `docs/USER_GUIDE.md`, `docs/DEVELOPER_GUIDE.md` | docs |

**Wave dependency:** Wave 0 (foundation) → Wave 1 (4 parallel core modules) → Wave 2 (CLI) → Wave 3 (GUI) → Wave 4 (packaging + docs). Wave 1 tasks touch disjoint files and may run concurrently.

---

## WAVE 0 — Foundation (orchestrator, sequential)

### Task 0.1: Project skeleton + tooling

**Files:**
- Create: `reclaim/__init__.py`, `reclaim/core/__init__.py`, `reclaim/cli/__init__.py`, `reclaim/gui/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `requirements.txt`, `pytest.ini`

- [ ] **Step 1:** Create package dirs with `__init__.py`. `reclaim/__init__.py` sets `__version__ = "1.0.0"`.
- [ ] **Step 2:** `requirements.txt`: `send2trash>=1.8` and a dev section comment for `pytest>=8`.
- [ ] **Step 3:** `pytest.ini` with `[pytest]\ntestpaths = tests`.
- [ ] **Step 4:** `tests/conftest.py` — shared fixture `make_tree(tmp_path)` that builds a known directory tree (files of known sizes/extensions/mtimes) and returns its root. Include a helper `write_file(path, size_bytes, mtime=None)`.
- [ ] **Step 5:** Install deps: `python -m pip install send2trash pytest`.
- [ ] **Step 6:** Run `python -m pytest -q` (expect: no tests collected, exit 5 — acceptable) then commit.

```bash
git add -A && git commit -m "chore: project skeleton, deps, pytest config"
```

### Task 0.2: Core data models (`core/models.py`)

**Files:** Create `reclaim/core/models.py`, Test `tests/test_models.py`

Define these dataclasses (all `@dataclass(slots=True)`), exact field names — later tasks depend on them:

```python
@dataclass(slots=True)
class ScanOptions:
    root: Path
    follow_symlinks: bool = False
    include_hidden: bool = True
    excluded_paths: list[Path] = field(default_factory=list)
    min_size: int = 0
    compute_hashes: bool = False

@dataclass(slots=True)
class FileEntry:
    path: str; name: str; ext: str; category: str; size: int
    created: float; modified: float; accessed: float
    is_hidden: bool = False; is_readonly: bool = False; hash: str | None = None

@dataclass(slots=True)
class CategoryStat:
    category: str; count: int; total_size: int

@dataclass(slots=True)
class DuplicateGroup:
    hash: str; size: int; paths: list[str]
    @property
    def wasted(self) -> int: return self.size * (len(self.paths) - 1)

@dataclass(slots=True)
class DirNode:
    path: str; total_size: int = 0; file_count: int = 0
    children: dict[str, "DirNode"] = field(default_factory=dict)

@dataclass(slots=True)
class ScanResult:
    root: str; files: list[FileEntry]; total_size: int; total_count: int
    errors: list[tuple[str, str]]; duration: float
    def category_stats(self) -> list[CategoryStat]: ...   # aggregate by category, desc by size
    def top_files(self, n: int = 20) -> list[FileEntry]: ...  # largest n

@dataclass(slots=True)
class DeletionResult:
    attempted: int; deleted: int; failed: list[tuple[str, str]]
    freed_bytes: int; method: str          # "recycle" | "permanent" | "dry-run"

@dataclass(slots=True)
class JunkCategory:
    name: str; paths: list[str]; total_size: int; safe_to_delete: bool

@dataclass(slots=True)
class Progress:
    files_seen: int = 0; bytes_seen: int = 0; current_path: str = ""; done: bool = False
```

- [ ] **Step 1:** Write `tests/test_models.py`: assert `DuplicateGroup(hash="x", size=100, paths=["a","b","c"]).wasted == 200`; assert `ScanResult.category_stats()` aggregates two files of same category into one `CategoryStat` with summed size and count, sorted size-desc; assert `top_files(2)` returns the two largest.
- [ ] **Step 2:** Run tests → fail.
- [ ] **Step 3:** Implement `models.py`.
- [ ] **Step 4:** Run → pass.
- [ ] **Step 5:** Commit `feat: core data models`.

### Task 0.3: Constants + size helper (`core/constants.py`)

**Files:** Create `reclaim/core/constants.py`, Test `tests/test_constants.py`

Contents:
- `CATEGORY_EXTENSIONS: dict[str, set[str]]` mapping category → lowercase extensions (with dot). Categories & sample exts:
  - Video: `.mp4 .mkv .avi .mov .wmv .flv .webm .m4v`
  - Audio: `.mp3 .wav .flac .aac .ogg .m4a .wma`
  - Images: `.jpg .jpeg .png .gif .bmp .tiff .webp .heic .svg .raw`
  - Documents: `.pdf .doc .docx .txt .rtf .odt .epub .md`
  - Spreadsheets: `.xls .xlsx .csv .ods`
  - Archives: `.zip .rar .7z .tar .gz .bz2 .xz`
  - Installers/Executables: `.exe .msi .bat .cmd .com`
  - Code: `.py .js .ts .java .c .cpp .h .cs .go .rs .html .css .json .xml .yml .yaml`
  - Disk Images: `.iso .img .vhd .vhdx .dmg`
  - Fonts: `.ttf .otf .woff .woff2`
  - Temp/Cache: `.tmp .temp .cache .log .bak .old .dmp`
- `EXT_TO_CATEGORY: dict[str, str]` inverted map (built once).
- `DEFAULT_CATEGORY = "Other"`.
- `PROTECTED_ROOTS: list[str]` — normalized lowercase: the Windows dir (`%SystemRoot%`), `Program Files`, `Program Files (x86)`, `ProgramData`, the Python prefix (`sys.prefix`), plus a function `system_protected_roots()` that resolves these at runtime (env-var based, not hardcoded `C:`).
- `JUNK_LOCATIONS()` -> list of `(name, path, safe)` derived from env (`%TEMP%`, `%SystemRoot%\Temp`, browser cache dirs under `%LOCALAPPDATA%`, thumbnail cache).
- `human_size(n: int) -> str` (e.g. 1536 → "1.5 KB"; binary units KB/MB/GB/TB).

- [ ] **Step 1:** Write `tests/test_constants.py`: `human_size(0)=="0 B"`, `human_size(1024)=="1.0 KB"`, `human_size(1536)=="1.5 KB"`, `human_size(1048576)=="1.0 MB"`; `EXT_TO_CATEGORY[".mp4"]=="Video"`; every ext appears in exactly one category (no dup across sets); `system_protected_roots()` is non-empty and contains the windows dir.
- [ ] **Step 2:** Run → fail. **Step 3:** Implement. **Step 4:** Run → pass. **Step 5:** Commit `feat: categories, protected paths, junk locations, human_size`.

---

## WAVE 1 — Core modules (4 PARALLEL subagents; disjoint files)

> Each subagent: do TDD (test first, fail, implement, pass, commit). Use `conftest.make_tree`. Never touch the user's real files — only `tmp_path`. Import models/constants from Wave 0; do not modify those files.

### Task A: Scanner (`core/scanner.py`) — Agent A

**Files:** Create `reclaim/core/scanner.py`, Test `tests/test_scanner.py`

**Interface:**
```python
def scan(options: ScanOptions,
         on_progress: Callable[[Progress], None] | None = None,
         should_cancel: Callable[[], bool] | None = None) -> ScanResult
```
Behaviour: recurse with `os.scandir`; per file build a `FileEntry` (category via `categorizer.categorize`, size/mtimes from `stat`, hidden/readonly from attrs); skip entries below `options.min_size`; skip `excluded_paths`; do **not** follow reparse points unless `follow_symlinks`; collect `PermissionError`/`OSError` into `errors` and continue; call `on_progress` every ~500 files and at end with `done=True`; check `should_cancel()` periodically and stop early if true; populate `compute_hashes` hash only if requested (delegate to a `_hash_file` in analysis or a local helper — local helper here to avoid cross-dep).

**Key tests (against `make_tree`):**
- total `total_count` and `total_size` equal the known tree.
- `min_size` filter excludes small files.
- `excluded_paths` subtree is skipped.
- a directory the OS denies (simulate by monkeypatching `os.scandir` to raise on one path) → recorded in `errors`, scan still completes.
- `should_cancel` returning True after first batch stops the scan early (fewer files than total).
- progress callback is invoked and final call has `done=True`.

Commit `feat: filesystem scanner with progress, cancel, error capture`.

### Task B: Categorizer + Analysis (`core/categorizer.py`, `core/analysis.py`) — Agent B

**Files:** Create `reclaim/core/categorizer.py`, `reclaim/core/analysis.py`; Test `tests/test_categorizer.py`, `tests/test_analysis.py`

**categorizer interface:**
```python
def categorize(ext_or_name: str) -> str   # accepts ".mp4", "mp4", or "movie.mp4"; case-insensitive; unknown → "Other"
```
Tests: `categorize("movie.MP4")=="Video"`, `categorize(".unknownxyz")=="Other"`, `categorize("noext")=="Other"`.

**analysis interface (operate on `list[FileEntry]` or a root path):**
```python
def largest_files(files: list[FileEntry], n: int = 20) -> list[FileEntry]
def largest_dirs(files: list[FileEntry], n: int = 20) -> list[tuple[str, int]]   # (dir, total_size)
def find_duplicates(files: list[FileEntry], read_chunk=lambda p, sz: ...) -> list[DuplicateGroup]
def find_stale(files: list[FileEntry], days: int, now: float | None = None) -> list[FileEntry]
def find_empty_dirs(root: str | Path) -> list[str]
def hash_file(path: str, partial_bytes: int | None = None) -> str   # sha256, chunked
```
`find_duplicates`: group by size; for groups >1, compute partial hash (first 64 KiB) to prune; full-hash the partial collisions; emit `DuplicateGroup` sorted by `wasted` desc. (Inject a reader so tests don't need real files, OR just read real `tmp_path` files — prefer real files for honesty.)

**Key tests:**
- `largest_files` returns top-N sorted desc.
- `largest_dirs` sums sizes per parent dir.
- `find_duplicates`: create 3 identical-content files + 1 unique → one group with 3 paths, wasted == 2×size; different-size files never grouped.
- `find_stale`: files with old mtime vs recent, with fixed `now` → only old returned.
- `find_empty_dirs`: nested empty dir returned, non-empty not.
- `hash_file`: identical content → identical hash; different → different.

Commit `feat: categorizer + analysis (largest, duplicates, stale, empty, hashing)`.

### Task C: Junk + Deletion (`core/junk.py`, `core/deletion.py`) — Agent C (SAFETY-CRITICAL)

**Files:** Create `reclaim/core/junk.py`, `reclaim/core/deletion.py`; Test `tests/test_junk.py`, `tests/test_deletion.py`

**junk interface:**
```python
def scan_junk(locations: list[tuple[str, str, bool]] | None = None) -> list[JunkCategory]
```
Uses `constants.JUNK_LOCATIONS()` by default; for each existing path, sum sizes (reuse a small local walker or `os.scandir`); skip missing paths; return `JunkCategory` per location. Read-only — never deletes.
Tests: build fake temp dirs via `tmp_path`, pass explicit `locations`, assert sizes and that missing paths are skipped.

**deletion interface (SAFETY-CRITICAL):**
```python
def is_protected(path: str | Path, protected_roots: list[str] | None = None) -> bool
def delete(paths: Iterable[str | Path], *, permanent: bool = False, dry_run: bool = False,
           on_progress: Callable[[int, int], None] | None = None,
           audit_log: Path | None = None,
           protected_roots: list[str] | None = None) -> DeletionResult
```
- `is_protected`: resolve + normcase; True if path equals or is under any protected root (default `constants.system_protected_roots()`). Also protect the drive root itself.
- `delete`: for each path — if protected → append to `failed` with reason "protected", skip. If `dry_run` → count as if deleted, method "dry-run", no FS change, no audit write. Else recycle (`send2trash.send2trash`) unless `permanent` (`os.remove`/`shutil.rmtree`). Sum freed bytes (stat before delete). Append JSONL audit line per real deletion to `audit_log`. Catch per-path errors into `failed`, never raise.

**Key tests (the most important in the project):**
- `is_protected(<windows dir>)` is True; `is_protected(<windows dir>\sub\f.txt)` is True; `is_protected(tmp_path/file)` is False.
- **`delete([protected_path])` deletes nothing** and returns it in `failed` with reason "protected" — assert the file still exists. (Use a fake protected root = a `tmp_path` subdir passed via `protected_roots`, containing a real file.)
- `dry_run=True` removes nothing, `method=="dry-run"`, `attempted` counts inputs.
- recycle path: monkeypatch `send2trash.send2trash` to record calls (don't hit real Recycle Bin) → called once per non-protected file; `freed_bytes` == summed sizes; `method=="recycle"`.
- permanent path: real files in `tmp_path` → actually removed; `method=="permanent"`.
- audit log: after a real (monkeypatched-recycle or permanent) delete, the JSONL file has one line per deletion with path+size+method+timestamp.
- a path that errors (monkeypatch send2trash to raise for one) → recorded in `failed`, others still deleted.

Commit `feat: junk scanner + safety-critical deletion engine with protected-path guard and audit log`.

### Task D: Report + Config (`core/report.py`, `core/config.py`) — Agent D

**Files:** Create `reclaim/core/report.py`, `reclaim/core/config.py`; Test `tests/test_report.py`, `tests/test_config.py`

**report interface:**
```python
def to_csv(result: ScanResult, path: str | Path) -> None
def to_json(result: ScanResult, path: str | Path) -> None
```
CSV: header `name,category,ext,size,size_human,modified_iso,path` + one row per file. JSON: `{summary:{root,total_size,total_count,duration,categories:[...]}, files:[...]}`.
Tests: build a small `ScanResult` (construct `FileEntry`s directly), write CSV → re-read, assert row count == files+header and a known row's fields; write JSON → `json.load`, assert summary totals and `len(files)`.

**config interface:**
```python
@dataclass
class AppConfig:
    default_root: str = "C:\\"; excluded_paths: list[str] = ...; stale_days: int = 180
    theme: str = "light"; profiles: dict[str, dict] = ...
def load_config(path: Path | None = None) -> AppConfig    # default ~/.reclaim/config.json; missing → defaults
def save_config(cfg: AppConfig, path: Path | None = None) -> None
```
Tests: save then load round-trips (use `tmp_path` config file); loading a missing file returns defaults; a saved profile survives round-trip.

Commit `feat: CSV/JSON reporting + config & scan profiles`.

---

## WAVE 2 — CLI (orchestrator)

### Task 2.1: CLI (`cli/main.py`, `reclaim/__main__.py`)

**Files:** Create `reclaim/cli/main.py`, `reclaim/__main__.py`; Test `tests/test_cli.py`

**Commands** (argparse subcommands), `main(argv: list[str]) -> int`:
- `scan PATH [--json F] [--csv F] [--top N] [--min-size BYTES]` → scans, prints totals + category table + top-N, writes reports if requested.
- `dupes PATH [--json F]` → prints duplicate groups + total wasted.
- `junk [--list]` → prints junk categories + sizes (read-only).
- `clean-junk [--confirm]` → dry-run unless `--confirm`; routes through `deletion.delete` on safe junk paths.
- `delete PATH... [--permanent] [--confirm]` → dry-run unless `--confirm`; prints summary first.
- `__main__.py`: if `sys.argv[1:]` → `cli.main`; else launch GUI.

**Key tests (invoke `main([...])` on `tmp_path`):**
- `scan` returns 0 and (capsys) prints total size and a category.
- `scan --json out` writes a valid JSON report.
- `delete <file>` WITHOUT `--confirm` → file still exists (dry-run), exit 0.
- `delete <file> --confirm --permanent` → file removed.
- `delete <protected> --confirm` → refused, file remains.

Commit `feat: CLI (scan/dupes/junk/clean-junk/delete) + entrypoint`.

---

## WAVE 3 — GUI (orchestrator)

### Task 3.1: Background worker (`gui/workers.py`)

**Files:** Create `reclaim/gui/workers.py`, Test `tests/test_workers.py`

`ScanWorker`: runs `scanner.scan` on a `threading.Thread`, pushes `Progress` and final `ScanResult` onto a `queue.Queue`; exposes `start()`, `cancel()`, `poll() -> events`. Logic is headless-testable.
Tests: run worker on `make_tree`, drain queue until a result event appears, assert the result totals match a direct `scan`; `cancel()` before/at start yields a (possibly partial) result without hanging.

Commit `feat: threaded scan worker with progress queue`.

### Task 3.2: Widgets (`gui/widgets.py`)

**Files:** Create `reclaim/gui/widgets.py`

- `CategoryBars(parent)` — horizontal bars per `CategoryStat` (Canvas), `.update_stats(list[CategoryStat])`.
- `Treemap(parent)` — squarified treemap of `DirNode`/top dirs on a Canvas, click → callback(path).
- `DetailTable(parent)` — `ttk.Treeview` columns: Name, Size (human), Category, Format, Modified, Path; sortable by clicking headers; `.set_files(list[FileEntry])`, `.selected_paths()`; search/filter via `.apply_filter(text)`.
- Pure-helper `squarify(values, x, y, w, h) -> list[rects]` extracted and unit-tested in `tests/test_widgets.py` (geometry only, no Tk): areas proportional, rects within bounds.

Commit `feat: GUI widgets (category bars, treemap, detail table) + squarify`.

### Task 3.3: Main app (`gui/app.py`)

**Files:** Create `reclaim/gui/app.py`

`ReclaimApp(tk.Tk)`: toolbar (Choose Folder, Scan, Cancel, Find Duplicates, Find Large, Find Stale, Clean Junk, Export, Delete Selected, recycle-vs-permanent toggle), disk free-space label, `CategoryBars`, `Treemap`, `DetailTable`, status/progress bar. Wires `ScanWorker` with `after()` polling. Delete button → confirm dialog (count + human total) → `deletion.delete` (guard always applies) → refresh. `def run(): ReclaimApp().mainloop()`. Graceful fallback if `customtkinter` absent (use ttk). Wrap worker exceptions → messagebox.

Manual smoke (documented, not auto): launch, scan a small folder, verify table + bars + treemap, export, dry-delete.

Commit `feat: Reclaim GUI main window`.

---

## WAVE 4 — Packaging & Docs (orchestrator)

### Task 4.1: Run/build scripts

**Files:** Create `run.ps1`, `run.bat`, `build.ps1`
- `run.ps1`/`run.bat`: `python -m reclaim`.
- `build.ps1`: ensure PyInstaller, then `pyinstaller --noconfirm --onefile --windowed --name Reclaim reclaim/__main__.py` → `dist/Reclaim.exe`. Document that CLI use of the exe works via `Reclaim.exe scan PATH`.

Commit `chore: run + build scripts`.

### Task 4.2: Documentation

**Files:** Create `README.md`, `docs/USER_GUIDE.md`, `docs/DEVELOPER_GUIDE.md`
- README: what it is, install, quick start (GUI + CLI), safety notes, build to exe.
- USER_GUIDE: every feature, screenshots-by-description, the safety model, how to recover from Recycle Bin, FAQ.
- DEVELOPER_GUIDE: architecture, module-by-module API, data model, how to run tests, how to extend categories/junk locations, how to build. Explicitly explain protected-path guard and why registry/startup cleaning are excluded.

Commit `docs: README + user & developer guides`.

### Task 4.3: Final verification

- [ ] `python -m pytest -q` → all green (capture count).
- [ ] `python -m reclaim scan <small folder> --json /tmp/r.json` → valid output.
- [ ] `python -m reclaim` → GUI launches (or documented if no display).
- [ ] Update README with the real test count.
- [ ] Commit `chore: final verification`.

---

## Self-Review (against spec)

- **Scan/categorize/detail/delete** → Tasks A, B, C, 2.1, 3.x ✓
- **Safety (recycle default, protected guard, dry-run, audit, junk whitelist)** → Task C + 2.1 ✓
- **Duplicates / large / stale / empty** → Task B ✓
- **Junk/temp** → Task C ✓
- **Report CSV/JSON, config/profiles** → Task D ✓
- **CLI + GUI** → Waves 2, 3 ✓
- **Treemap/bars/search/progress/cancel/free-space** → Tasks 3.1–3.3 ✓
- **Packaging + docs** → Wave 4 ✓
- **Excluded (registry/startup)** documented in 4.2 ✓
- Type/signature names (FileEntry fields, `categorize`, `delete`, `scan`, `ScanResult.category_stats`) are consistent across tasks ✓
- No placeholders; each task has concrete interfaces + named test cases ✓
