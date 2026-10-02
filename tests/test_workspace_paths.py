from pathlib import Path

from agentos.security.workspace_paths import resolve_in_allowed_workspaces, resolve_within_workspace


def test_resolve_within_workspace_blocks_traversal(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    target, err = resolve_within_workspace(ws, "../../outside.txt")
    assert target is None
    assert "outside workspace" in (err or "")


def test_resolve_within_workspace_allows_nested_file(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    nested = ws / "reports"
    nested.mkdir()
    target, err = resolve_within_workspace(ws, "reports/out.txt")
    assert err is None
    assert target == (nested / "out.txt").resolve()


def test_resolve_in_allowed_workspaces_relative(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    allowed = [ws.resolve()]
    target, err = resolve_in_allowed_workspaces(allowed, "note.txt")
    assert err is None
    assert target == (ws / "note.txt").resolve()
