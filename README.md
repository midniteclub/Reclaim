# Reclaim — Free Disk Space Analyzer & Cleaner

Reclaim is a **free, standalone, offline** Windows app that scans your computer,
shows you exactly what is consuming disk space, and lets you **safely** delete what
you don't need — selected categories or individual files. It's a no-subscription
alternative to tools like CCleaner / WizTree / TreeSize.

- **Private & offline** — no accounts, no telemetry, no internet required.
- **Safe by design** — deletes to the Recycle Bin by default, refuses to touch
  protected system locations, supports dry-run, and logs every deletion.
- **Two interfaces** — a desktop GUI and a scriptable command line, both built on
  the same audited engine.

> ⚠️ **It's still a deletion tool.** Read the [Safety model](#safety-model) before
> deleting anything. The authors are not responsible for data you choose to delete.

---

## Quick start

You need **Python 3.10+** on Windows (already installed if `python --version` works).

```powershell
# from the project folder:
python -m pip install -r requirements.txt   # installs send2trash
.\run.ps1                                    # launch the GUI
```

Or use the command line:

```powershell
.\run.ps1 scan C:\Users\you\Downloads        # summarize a folder
python -m reclaim scan C:\ --csv report.csv  # full scan, export to CSV
python -m reclaim dupes C:\Users\you\Pictures
python -m reclaim junk --list                # show junk/temp locations (read-only)
python -m reclaim delete "C:\path\to\file.iso"            # DRY RUN (shows what would happen)
python -m reclaim delete "C:\path\to\file.iso" --confirm  # actually recycle it
```

## Build a standalone .exe (optional)

If you want a double-clickable app with no Python needed at run time:

```powershell
.\build.ps1
# → dist\Reclaim.exe   (GUI on double-click; also a CLI: dist\Reclaim.exe scan C:\)
```

---

## What it does

- **Scan** any folder or whole drive; per-directory size rollups.
- **Categorize** everything: Video, Audio, Images, Documents, Spreadsheets,
  Presentations, Archives, Installers/Executables, Code, Disk Images, Fonts,
  Temp/Cache, and Other.
- **Visualize** with a treemap and category bars; see disk free space.
- **Inspect** every file in detail: name, size, format, category, modified date,
  full path (sortable & filterable table).
- **Find** the biggest files, duplicate files (content-hash based), and stale files.
- **Clean junk** from known-safe temp/cache locations (whitelist only).
- **Delete** selected categories or individual items — Recycle Bin by default.
- **Export** a full report to CSV or JSON.

## Safety model

1. **Recycle Bin by default.** Permanent deletion is opt-in (a checkbox in the GUI,
   `--permanent` in the CLI). Recycled files can be restored from the Windows
   Recycle Bin.
2. **Protected paths.** The engine **refuses** to delete anything inside Windows,
   Program Files, Program Files (x86), ProgramData, System32, your Python install,
   the Reclaim app folder, or a bare drive root (e.g. `C:\`). This guard lives in
   the engine, so the GUI, the CLI, and any future caller all inherit it.
3. **Dry-run.** CLI deletion commands do nothing unless you add `--confirm`.
4. **Audit log.** Every real deletion is appended to `~/.reclaim/deletions.log`
   (one JSON line per file: path, size, method, timestamp).
5. **Junk cleaning is whitelist-only.** Only documented, known-safe temp/cache
   locations are ever offered.

**Deliberately excluded:** Reclaim does **not** clean the Windows Registry or change
startup programs/services. Those are high-risk, low-benefit operations that can
destabilize Windows; see the Developer Guide for the rationale.

---

## Documentation

- **[User Guide](docs/USER_GUIDE.md)** — every feature, the safety model in depth,
  how to recover deleted files, and an FAQ.
- **[Developer Guide](docs/DEVELOPER_GUIDE.md)** — architecture, module-by-module
  API, data model, how to run the tests, and how to extend categories/junk rules.
- **[Design spec](docs/superpowers/specs/2026-06-21-reclaim-disk-cleaner-design.md)**
  and **[implementation plan](docs/superpowers/plans/2026-06-21-reclaim-disk-cleaner.md)**.

## Project layout

```
reclaim/core/   pure-Python engine (no UI) — scanner, categorizer, analysis,
                junk, deletion, report, config, models, constants
reclaim/cli/    argparse command line
reclaim/gui/    tkinter desktop UI (app, widgets, background worker)
tests/          pytest suite (74 tests)
```

## Tests

```powershell
python -m pip install pytest
python -m pytest          # 74 tests
```

## License / disclaimer

Provided as-is for personal use. Always review what you're deleting. When in doubt,
recycle (don't use `--permanent`) so you can restore from the Recycle Bin.
