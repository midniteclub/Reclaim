"""Map a file extension (or name) to a high-level category."""
from __future__ import annotations

from reclaim.core import constants


def categorize(ext_or_name: str) -> str:
    """Return the category for ``ext_or_name``.

    Accepts a full name ("movie.mp4"), a dotted extension (".pdf"), or a bare
    extension ("mp3"), case-insensitively. Returns ``constants.DEFAULT_CATEGORY``
    when the extension is unknown or absent.
    """
    if not ext_or_name:
        return constants.DEFAULT_CATEGORY

    text = ext_or_name.strip().lower()
    if "." in text:
        ext = text[text.rfind("."):]  # includes the leading dot
        if ext == ".":  # input ended with a dot, no extension
            return constants.DEFAULT_CATEGORY
    else:
        # No dot at all: treat the whole thing as a bare extension.
        ext = "." + text

    return constants.EXT_TO_CATEGORY.get(ext, constants.DEFAULT_CATEGORY)
