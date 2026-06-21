# Reclaim — User Guide

This guide explains every feature, how the safety system protects you, how to undo
deletions, and answers common questions. No technical background required.

---

## 1. Installing & launching

Reclaim needs **Python 3.10 or newer** (Windows). Check with `python --version`.

1. Open PowerShell in the Reclaim folder.
2. Install the one runtime dependency:
   ```powershell
   python -m pip install -r requirements.txt
   ```
3. Launch the app:
   ```powershell
   .\run.ps1
   ```
   (or double-click `run.bat`).

Prefer a single double-clickable program? Build a standalone executable once with
`.\build.ps1`, then run `dist\Reclaim.exe` — no Python needed afterwards.

---

## 2. The main window

```
┌───────────────────────────────────────────────────────────────────────┐
│ [Choose Folder…] [C:\Users\you ......] [Scan] [Cancel]  [Largest]       │
│ [Duplicates] [Stale] [Export…]        [Delete Selected] [☐ permanent]   │
├───────────────────────────────────────────────────────────────────────┤
│ Category bars (Video / Images / Documents …, sized by space used)       │
├───────────────────────────────────────────────────────────────────────┤
│ Filter: [______________]                                                │
├──────────────────────────┬──────────────────────────────────────────── │
│                          │  Name      Size  Category  Format  Modified  │
│   Treemap (folders       │  movie.mp4 1.2GB Video     .mp4    2025-…     │
│   sized by space)        │  …                                           │
│                          │  (sortable, filterable, multi-select)        │
├──────────────────────────┴──────────────────────────────────────────── │
│ Status: 124,003 files, 412.6 GB in 38.2s        Free: 95 GB / 931 GB    │
└───────────────────────────────────────────────────────────────────────┘
```

### Running a scan
1. Click **Choose Folder…** (or type a path) — e.g. `C:\` to scan the whole drive,
   or `C:\Users\you\Downloads` for one folder.
2. Click **Scan**. Scanning runs in the background; the status bar shows live
   progress and the app stays responsive. Click **Cancel** to stop early.
3. When it finishes, the category bars, treemap, and detail table fill in, and the
   status bar shows the total file count, total size, scan time, and how many items
   were skipped because Windows wouldn't grant access (normal for a full C: scan).

### Reading the results
- **Category bars** — at a glance, which *types* of files use the most space.
- **Treemap** — the biggest folders, drawn proportionally. Click a block to filter
  the table to that folder.
- **Detail table** — every file. Click any column header to sort (click again to
  reverse). Type in **Filter** to show only matching names/paths/categories.
- **Free** (bottom-right) — free vs. total space on the scanned drive.

### Focus tools
- **Largest** — show the 200 biggest files.
- **Duplicates** — find files with identical content (wasted copies). A popup tells
  you how much space you'd reclaim by keeping one copy of each.
- **Stale** — show files not modified in a long time (default 180 days; configurable).

### Exporting
**Export…** writes a full report. Choose a `.csv` (opens in Excel) or `.json` file.
The report includes every file's name, category, format, size, modified date, and
full path, plus a summary with category totals.

---

## 3. Deleting files

1. Select one or more rows in the detail table (Ctrl-click / Shift-click for many).
2. Decide the method:
   - **Leave "Delete permanently" unchecked (recommended)** → files go to the
     **Recycle Bin** and can be restored.
   - **Check "Delete permanently"** → files are removed immediately and cannot be
     recovered through Windows. Use only when you're certain.
3. Click **Delete Selected**. A confirmation dialog shows how many items and how much
   space. Confirm to proceed.
4. A summary reports how much was freed, and how many items were **refused** because
   they are protected system paths (see below).

### Cleaning junk (CLI)
The command line can clear known-safe temp/cache locations:
```powershell
python -m reclaim junk --list        # see what's there (read-only)
python -m reclaim clean-junk         # DRY RUN — shows what would be freed
python -m reclaim clean-junk --confirm   # actually clean (to Recycle Bin)
```

---

## 4. The safety system (please read)

Reclaim is built to make accidental damage hard:

- **Recycle Bin by default.** Unless you explicitly choose permanent deletion,
  everything goes to the Recycle Bin and can be restored.
- **Protected locations are untouchable.** Reclaim will *refuse* to delete anything
  inside:
  - `C:\Windows` (and `System32`)
  - `C:\Program Files` and `C:\Program Files (x86)`
  - `C:\ProgramData`
  - your Python installation
  - the Reclaim app folder itself
  - a bare drive root such as `C:\`

  You can still *see* these in scans (so you understand what uses space), but the
  delete button will list them as "Refused (protected)". This is enforced deep in
  the engine — there is no setting that turns it off.
- **Audit trail.** Every real deletion is recorded in `C:\Users\you\.reclaim\deletions.log`
  (one line per file). If you ever wonder "did I delete that?", check this file.

### How to recover something you deleted
- **If you used the Recycle Bin (default):** open the Recycle Bin on your desktop,
  find the file, right-click → **Restore**.
- **If you used "Delete permanently":** Windows cannot restore it. You'd need a
  third-party recovery tool or a backup. This is why permanent delete is off by
  default.

---

## 5. FAQ

**Is this safe to run on my main C: drive?**
Scanning is completely read-only and safe. Deleting is up to you — keep "permanent"
off and you can always restore from the Recycle Bin.

**A scan said it "skipped" thousands of files. Did it fail?**
No. Windows locks some files and folders (in-use or system-owned). Reclaim skips
those gracefully and reports the count. Your totals cover everything it could read.

**Why is a full C: scan slower than WizTree?**
WizTree reads the raw NTFS index (admin-only). Reclaim walks the filesystem normally,
which is a bit slower but needs no special privileges and works on any folder.

**Can it delete Windows or my programs?**
No. Those locations are protected (see section 4). It can delete your *own* files —
documents, downloads, videos, caches — which is the point.

**Does it touch the registry or startup programs?**
No, by design. Those are risky to "clean" and can break Windows. Reclaim focuses on
files and disk space only.

**Where are my settings stored?**
`C:\Users\you\.reclaim\config.json` (default folder, stale-days threshold, saved
scan profiles). Delete it to reset to defaults.

**Does it send anything online?**
No. Reclaim is fully offline.
