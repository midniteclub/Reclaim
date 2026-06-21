"""Tests for the Reclaim CLI."""
import json
import os

from reclaim.cli.main import main


def test_scan_prints_totals_and_category(make_tree, capsys):
    root, expected = make_tree
    rc = main(["scan", str(root)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Video" in out
    assert str(expected["total_count"]) in out


def test_scan_writes_json_report(make_tree, tmp_path, capsys):
    root, expected = make_tree
    out_file = tmp_path / "report.json"
    rc = main(["scan", str(root), "--json", str(out_file)])
    assert rc == 0
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["summary"]["total_count"] == expected["total_count"]
    assert data["summary"]["total_size"] == expected["total_size"]


def test_delete_without_confirm_is_dry_run(tmp_path, capsys):
    f = tmp_path / "victim.txt"
    f.write_text("data")
    rc = main(["delete", str(f)])
    out = capsys.readouterr().out.lower()
    assert rc == 0
    assert f.exists()  # dry-run must not delete
    assert "dry" in out


def test_delete_confirm_permanent_removes_file(tmp_path, capsys):
    f = tmp_path / "victim.txt"
    f.write_text("data")
    rc = main(["delete", str(f), "--confirm", "--permanent"])
    assert rc == 0
    assert not f.exists()


def test_delete_refuses_protected_system_file(capsys):
    # explorer.exe lives under C:\Windows -> protected. Even with --confirm
    # --permanent the CLI must refuse and leave it untouched.
    sysfile = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "explorer.exe")
    if not os.path.exists(sysfile):
        import pytest
        pytest.skip("explorer.exe not present")
    rc = main(["delete", sysfile, "--confirm", "--permanent"])
    out = capsys.readouterr().out.lower()
    assert os.path.exists(sysfile)  # MUST still exist
    assert "protected" in out or "refused" in out


def test_dupes_reports_wasted(tmp_path, capsys):
    (tmp_path / "a.bin").write_bytes(b"identical-content")
    (tmp_path / "b.bin").write_bytes(b"identical-content")
    rc = main(["dupes", str(tmp_path)])
    out = capsys.readouterr().out.lower()
    assert rc == 0
    assert "wasted" in out or "duplicate" in out


def test_junk_list_runs(capsys):
    rc = main(["junk", "--list"])
    assert rc == 0
