"""
Tests for SHA-256 Hash Chained Audit Log.
"""

import json
from pathlib import Path
from agentos.policy.audit_log import AuditLogger


def test_audit_hash_chain_integrity(tmp_path: Path):
    log_file = tmp_path / "audit.jsonl"
    logger = AuditLogger(log_file)

    logger.log("ACTION_ONE", "agent", {"key": "val1"})
    logger.log("ACTION_TWO", "agent", {"key": "val2"})
    logger.log("ACTION_THREE", "supervisor", {"key": "val3"})

    valid, msg = logger.verify_integrity()
    assert valid is True
    assert "3 records intact" in msg


def test_audit_tamper_detection(tmp_path: Path):
    log_file = tmp_path / "audit.jsonl"
    logger = AuditLogger(log_file)

    logger.log("ACTION_A", "agent", {"secret": 123})
    logger.log("ACTION_B", "agent", {"secret": 456})

    # Tamper with the first record in the file
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    rec1 = json.loads(lines[0])
    rec1["payload"]["secret"] = 999  # Tamper payload without recomputing hash!
    lines[0] = json.dumps(rec1)
    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Verification must detect the tampering
    new_logger = AuditLogger(log_file)
    valid, msg = new_logger.verify_integrity()
    assert valid is False
    assert "Tampered record" in msg
