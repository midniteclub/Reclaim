"""Tests for AppConfig load/save."""
from __future__ import annotations

from reclaim.core.config import AppConfig, load_config, save_config


def test_load_missing_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert isinstance(cfg, AppConfig)
    assert cfg.default_root == "C:\\"
    assert cfg.stale_days == 180


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = AppConfig(
        default_root="D:\\",
        excluded_paths=["D:\\skip", "E:\\nope"],
        stale_days=90,
        theme="dark",
        profiles={"quick": {"root": "D:\\", "min_size": 1000}},
    )
    save_config(cfg, path)

    loaded = load_config(path)
    assert loaded.default_root == "D:\\"
    assert loaded.excluded_paths == ["D:\\skip", "E:\\nope"]
    assert loaded.stale_days == 90
    assert loaded.theme == "dark"
    assert loaded.profiles == {"quick": {"root": "D:\\", "min_size": 1000}}


def test_save_creates_parent_dirs(tmp_path):
    path = tmp_path / "sub" / "deep" / "config.json"
    save_config(AppConfig(), path)
    assert path.exists()
