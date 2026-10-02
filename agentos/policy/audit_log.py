"""
AgentOS Audit Log.
Implements an append-only, SHA-256 hash-chained cryptographic audit log.
Guarantees tamper-evidence for tool calls, approvals, policy decisions, and spend events.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    index: int
    timestamp_utc: str
    action_type: str
    actor: str
    payload: Dict[str, Any]
    previous_hash: str
    record_hash: str = ""

    def calculate_hash(self) -> str:
        canonical_payload = json.dumps(self.payload, sort_keys=True)
        raw = f"{self.index}|{self.timestamp_utc}|{self.action_type}|{self.actor}|{self.previous_hash}|{canonical_payload}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AuditLogger:
    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(self, log_path: str | Path = "data/audit.jsonl") -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._last_index = 0
        self._last_hash = self.GENESIS_HASH
        self._initialize_chain()

    def _initialize_chain(self) -> None:
        with self._lock:
            if self.log_path.exists() and self.log_path.stat().st_size > 0:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            record = AuditRecord.model_validate(data)
                            self._last_index = record.index
                            self._last_hash = record.record_hash

    def log(self, action_type: str, actor: str, payload: Dict[str, Any]) -> AuditRecord:
        with self._lock:
            next_index = self._last_index + 1
            now_iso = datetime.now(timezone.utc).isoformat()
            record = AuditRecord(
                index=next_index,
                timestamp_utc=now_iso,
                action_type=action_type,
                actor=actor,
                payload=payload,
                previous_hash=self._last_hash,
            )
            record.record_hash = record.calculate_hash()

            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(record.model_dump_json() + "\n")

            self._last_index = next_index
            self._last_hash = record.record_hash
            return record

    def verify_integrity(self) -> tuple[bool, Optional[str]]:
        """Verifies the SHA-256 hash-chain from start to end."""
        with self._lock:
            if not self.log_path.exists():
                return True, "Audit log is empty."

            expected_prev_hash = self.GENESIS_HASH
            current_index = 0

            with open(self.log_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        rec = AuditRecord.model_validate(data)
                    except Exception as err:
                        return False, f"Line {line_num}: JSON parse failure: {err}"

                    if rec.index != current_index + 1:
                        return False, f"Line {line_num}: Sequence gap. Expected index {current_index + 1}, got {rec.index}."

                    if rec.previous_hash != expected_prev_hash:
                        return False, f"Line {line_num}: Hash chain broken. Expected prev_hash {expected_prev_hash}, got {rec.previous_hash}."

                    calc_hash = rec.calculate_hash()
                    if rec.record_hash != calc_hash:
                        return False, f"Line {line_num}: Tampered record. Stored {rec.record_hash}, calculated {calc_hash}."

                    current_index = rec.index
                    expected_prev_hash = rec.record_hash

            return True, f"Audit log verified. {current_index} records intact."
