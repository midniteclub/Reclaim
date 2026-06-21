"""Categories, protected paths, junk locations, and the human_size helper.

System paths are resolved at runtime from environment variables (not hardcoded to
``C:``) so the app works regardless of the Windows install drive.
"""
from __future__ import annotations

import os
import sys

# --------------------------------------------------------------------------- #
# Categories                                                                   #
# --------------------------------------------------------------------------- #
CATEGORY_EXTENSIONS: dict[str, set[str]] = {
    "Video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".aiff"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic", ".svg", ".raw", ".ico"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".epub", ".md", ".pages"},
    "Spreadsheets": {".xls", ".xlsx", ".csv", ".ods", ".tsv"},
    "Presentations": {".ppt", ".pptx", ".odp", ".key"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst"},
    "Installers/Executables": {".exe", ".msi", ".bat", ".cmd", ".com", ".msix", ".appx"},
    "Code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go",
             ".rs", ".rb", ".php", ".html", ".css", ".json", ".xml", ".yml", ".yaml", ".sql", ".sh"},
    "Disk Images": {".iso", ".img", ".vhd", ".vhdx", ".dmg", ".vmdk"},
    "Fonts": {".ttf", ".otf", ".woff", ".woff2", ".fon"},
    "Temp/Cache": {".tmp", ".temp", ".cache", ".log", ".bak", ".old", ".dmp", ".chk"},
}

DEFAULT_CATEGORY = "Other"

# Inverted map: extension -> category (built once at import time).
EXT_TO_CATEGORY: dict[str, str] = {
    ext: category
    for category, exts in CATEGORY_EXTENSIONS.items()
    for ext in exts
}


# --------------------------------------------------------------------------- #
# Protected system paths (never deletable)                                     #
# --------------------------------------------------------------------------- #
def system_protected_roots() -> list[str]:
    """Return absolute, normalized system roots that must never be deleted.

    Resolved from environment variables so it adapts to the real Windows drive.
    """
    candidates: list[str] = []

    def add(p: str | None) -> None:
        if p:
            candidates.append(os.path.normpath(p))

    windir = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    add(windir)
    add(os.environ.get("ProgramFiles") or r"C:\Program Files")
    add(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)")
    add(os.environ.get("ProgramData") or r"C:\ProgramData")
    add(os.path.join(windir, "System32"))
    add(sys.prefix)  # the running Python install
    add(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))  # the Reclaim app dir

    # The root of the system drive itself.
    system_drive = os.environ.get("SystemDrive", "C:")
    add(system_drive + os.sep)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    roots: list[str] = []
    for c in candidates:
        key = os.path.normcase(c)
        if key not in seen:
            seen.add(key)
            roots.append(c)
    return roots


# --------------------------------------------------------------------------- #
# Junk / temp / cache locations (whitelist only)                              #
# --------------------------------------------------------------------------- #
def JUNK_LOCATIONS() -> list[tuple[str, str, bool]]:
    """Return ``(name, path, safe_to_delete)`` for known junk locations.

    Only locations that actually exist on this machine are returned.
    """
    locs: list[tuple[str, str, bool]] = []
    local = os.environ.get("LOCALAPPDATA", "")
    temp = os.environ.get("TEMP") or os.environ.get("TMP", "")
    windir = os.environ.get("SystemRoot", r"C:\Windows")

    candidates: list[tuple[str, str, bool]] = [
        ("User Temp", temp, True),
        ("Windows Temp", os.path.join(windir, "Temp"), True),
        ("Thumbnail Cache", os.path.join(local, "Microsoft", "Windows", "Explorer"), True),
        ("Chrome Cache", os.path.join(local, "Google", "Chrome", "User Data", "Default", "Cache"), True),
        ("Edge Cache", os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Cache"), True),
        ("Firefox Cache", os.path.join(local, "Mozilla", "Firefox", "Profiles"), True),
        ("Windows Update Cache", os.path.join(windir, "SoftwareDistribution", "Download"), False),
        ("Prefetch", os.path.join(windir, "Prefetch"), False),
    ]
    for name, path, safe in candidates:
        if path and os.path.isdir(path):
            locs.append((name, os.path.normpath(path), safe))
    return locs


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def human_size(n: int) -> str:
    """Format a byte count as a human-readable string (binary units)."""
    if n < 1024:
        return f"{n} B"
    units = ["KB", "MB", "GB", "TB", "PB"]
    size = float(n)
    for unit in units:
        size /= 1024.0
        if size < 1024.0:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} EB"
