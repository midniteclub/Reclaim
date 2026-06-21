"""Tests for the pure squarify() treemap geometry helper (no Tk required)."""
from reclaim.gui.widgets import squarify


def _area(rect):
    _x, _y, w, h = rect
    return w * h


def test_squarify_returns_one_rect_per_value():
    rects = squarify([1, 2, 3, 4], 0, 0, 100, 100)
    assert len(rects) == 4


def test_squarify_empty_returns_empty():
    assert squarify([], 0, 0, 100, 100) == []


def test_squarify_single_value_fills_area():
    rects = squarify([5], 0, 0, 100, 80)
    assert len(rects) == 1
    x, y, w, h = rects[0]
    assert abs(w - 100) < 1e-6 and abs(h - 80) < 1e-6


def test_squarify_total_area_matches_container():
    rects = squarify([1, 2, 3, 4, 10], 0, 0, 200, 100)
    total = sum(_area(r) for r in rects)
    assert abs(total - 200 * 100) < 1e-3


def test_squarify_areas_proportional_to_values():
    values = [10, 20, 30, 40]
    rects = squarify(values, 0, 0, 100, 100)
    total_area = 100 * 100
    total_val = sum(values)
    for value, rect in zip(values, rects):
        expected = value / total_val * total_area
        assert abs(_area(rect) - expected) < 1e-3


def test_squarify_rects_within_bounds():
    rects = squarify([3, 1, 4, 1, 5, 9, 2, 6], 10, 20, 100, 80)
    for x, y, w, h in rects:
        assert x >= 10 - 1e-6 and y >= 20 - 1e-6
        assert x + w <= 10 + 100 + 1e-6
        assert y + h <= 20 + 80 + 1e-6
