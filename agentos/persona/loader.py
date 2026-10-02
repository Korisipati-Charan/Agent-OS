"""Load operator persona and user prefs from workspace-local markdown (Hermes-style memory files)."""

from pathlib import Path

DEFAULT_SOUL = (
    "AgentOS executes authorized tool calls inside a sandboxed workspace. "
    "Security invariants are non-negotiable."
)


def load_text(path: Path, fallback: str) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return fallback


def load_persona(project_root: Path | None = None) -> str:
    root = project_root or Path(__file__).resolve().parent
    return load_text(root / "SOUL.md", DEFAULT_SOUL)


def load_user_notes(project_root: Path | None = None) -> str:
    root = project_root or Path(__file__).resolve().parents[2]
    return load_text(root / "USER.md", "")
