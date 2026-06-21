"""Tests for reclaim.core.categorizer."""
from __future__ import annotations

from reclaim.core.categorizer import categorize


def test_categorize_filename_with_uppercase_ext():
    assert categorize("movie.MP4") == "Video"


def test_categorize_dotted_bare_ext():
    assert categorize(".pdf") == "Documents"


def test_categorize_bare_ext_no_dot():
    assert categorize("mp3") == "Audio"


def test_categorize_unknown_ext_returns_default():
    assert categorize(".unknownxyz") == "Other"


def test_categorize_no_extension_returns_default():
    assert categorize("noext") == "Other"


def test_categorize_empty_string_returns_default():
    assert categorize("") == "Other"
