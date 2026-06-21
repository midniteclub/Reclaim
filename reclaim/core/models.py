"""Core data models for Reclaim.

All dataclasses use ``slots=True`` for memory efficiency — a full ``C:`` scan can
produce ~1M ``FileEntry`` instances.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ScanOptions:
    """Configuration for a scan run."""
    root: Path
    follow_symlinks: bool = False
    include_hidden: bool = True
    excluded_paths: list[Path] = field(default_factory=list)
    min_size: int = 0
    compute_hashes: bool = False


@dataclass(slots=True)
class FileEntry:
    """A single scanned file with its metadata."""
    path: str
    name: str
    ext: str
    category: str
    size: int
    created: float
    modified: float
    accessed: float
    is_hidden: bool = False
    is_readonly: bool = False
    hash: str | None = None


@dataclass(slots=True)
class CategoryStat:
    """Aggregated count and size for one category."""
    category: str
    count: int
    total_size: int


@dataclass(slots=True)
class DuplicateGroup:
    """A set of files sharing identical content."""
    hash: str
    size: int
    paths: list[str]

    @property
    def wasted(self) -> int:
        """Bytes that could be reclaimed by keeping a single copy."""
        return self.size * (len(self.paths) - 1)


@dataclass(slots=True)
class DirNode:
    """Aggregated size/count for a directory (used by the treemap)."""
    path: str
    total_size: int = 0
    file_count: int = 0
    children: dict[str, "DirNode"] = field(default_factory=dict)


@dataclass(slots=True)
class ScanResult:
    """The complete result of a scan."""
    root: str
    files: list[FileEntry]
    total_size: int
    total_count: int
    errors: list[tuple[str, str]]
    duration: float

    def category_stats(self) -> list[CategoryStat]:
        """Aggregate files by category, sorted by total size descending."""
        counts: dict[str, int] = {}
        sizes: dict[str, int] = {}
        for f in self.files:
            counts[f.category] = counts.get(f.category, 0) + 1
            sizes[f.category] = sizes.get(f.category, 0) + f.size
        stats = [
            CategoryStat(category=c, count=counts[c], total_size=sizes[c])
            for c in counts
        ]
        stats.sort(key=lambda s: s.total_size, reverse=True)
        return stats

    def top_files(self, n: int = 20) -> list[FileEntry]:
        """Return the ``n`` largest files, largest first."""
        return sorted(self.files, key=lambda f: f.size, reverse=True)[:n]


@dataclass(slots=True)
class DeletionResult:
    """Outcome of a deletion request."""
    attempted: int
    deleted: int
    failed: list[tuple[str, str]]
    freed_bytes: int
    method: str  # "recycle" | "permanent" | "dry-run"


@dataclass(slots=True)
class JunkCategory:
    """A known-safe junk/temp/cache location and its size."""
    name: str
    paths: list[str]
    total_size: int
    safe_to_delete: bool


@dataclass(slots=True)
class Progress:
    """Progress snapshot passed to a scan callback."""
    files_seen: int = 0
    bytes_seen: int = 0
    current_path: str = ""
    done: bool = False
