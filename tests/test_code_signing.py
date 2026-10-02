from pathlib import Path
import yaml

from agentos.security.code_signing import find_signtool, sign_executable


def test_find_signtool_is_safe_and_non_damaging():
    # Calling find_signtool must never mutate or raise an exception
    result = find_signtool()
    assert result is None or isinstance(result, Path)


def test_sign_executable_safe_mode_without_cert(tmp_path: Path):
    dummy_exe = tmp_path / "dummy.exe"
    dummy_exe.write_bytes(b"MZ\x90\x00dummy executable content")

    # In safe mode (no cert), it must succeed without modifying system keystores
    success = sign_executable(dummy_exe, cert_path=None)
    assert success is True
    # Ensure binary content remains intact and uncorrupted
    assert dummy_exe.read_bytes() == b"MZ\x90\x00dummy executable content"


def test_sign_executable_nonexistent_file_returns_false(tmp_path: Path):
    nonexistent = tmp_path / "nonexistent.exe"
    success = sign_executable(nonexistent)
    assert success is False


def test_release_binaries_workflow_structure():
    workflow_file = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release-binaries.yml"
    assert workflow_file.exists()

    data = yaml.safe_load(workflow_file.read_text(encoding="utf-8"))
    assert data["permissions"]["contents"] == "write"
    assert "build-windows-exe" in data["jobs"]
    assert data["jobs"]["build-windows-exe"]["runs-on"] == "windows-latest"
