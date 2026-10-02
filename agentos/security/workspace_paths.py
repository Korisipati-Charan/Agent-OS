"""
Workspace path resolution with traversal-safe anchoring.
Single source of truth for policy checks and file tools (OWASP path traversal).
"""

from pathlib import Path
from typing import List, Optional, Tuple


def resolve_within_workspace(workspace: Path, user_path: str) -> Tuple[Optional[Path], Optional[str]]:
    ws = workspace.resolve()
    raw = Path(user_path)
    target = raw.resolve() if raw.is_absolute() else (ws / raw).resolve()

    if target != ws and ws not in target.parents:
        return None, f"Path '{target}' is outside workspace '{ws}'"
    return target, None


def resolve_in_allowed_workspaces(
    workspaces: List[Path], user_path: str
) -> Tuple[Optional[Path], Optional[str]]:
    if not user_path:
        return None, "Missing path argument."

    raw = Path(user_path)
    if raw.is_absolute():
        resolved = raw.resolve()
        for ws in workspaces:
            if resolved == ws or ws in resolved.parents:
                return resolved, None
        return None, f"Path '{resolved}' is outside authorized write workspaces."

    for ws in workspaces:
        target, err = resolve_within_workspace(ws, user_path)
        if err is None:
            return target, None

    resolved = raw.resolve()
    for ws in workspaces:
        if resolved == ws or ws in resolved.parents:
            return resolved, None

    return None, f"Path '{resolved}' is outside authorized write workspaces."
