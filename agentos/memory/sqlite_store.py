"""
AgentOS SQLite Store.
Durable persistent storage in WAL mode for task states, checkpoints,
idempotency tracking, episodic vectors, and migration management.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class TaskCheckpoint(BaseModel):
    checkpoint_id: str
    task_id: str
    node_id: str
    state: Dict[str, Any]
    created_at_utc: str


class IdempotencyRecord(BaseModel):
    idempotency_key: str
    action_name: str
    request_hash: str
    response_data: Optional[Dict[str, Any]] = None
    status: str  # PENDING | COMMITTED | FAILED
    created_at_utc: str


class SQLiteStore:
    def __init__(self, db_path: str | Path = "data/agentos.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def ping(self) -> None:
        with self._get_connection() as conn:
            conn.execute("SELECT 1")

    def get_semantic_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT response_json FROM semantic_cache
                WHERE cache_key = ? AND expires_at > ?
                """,
                (cache_key, now),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["response_json"])

    def set_semantic_cache(
        self, cache_key: str, task_type: str, response_json: str, ttl_sec: int
    ) -> None:
        now = datetime.now(timezone.utc)
        expires = datetime.fromtimestamp(now.timestamp() + ttl_sec, tz=timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO semantic_cache (cache_key, task_type, response_json, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    task_type=excluded.task_type,
                    response_json=excluded.response_json,
                    expires_at=excluded.expires_at
                """,
                (cache_key, task_type, response_json, expires),
            )

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode and normal synchronous writing for maximum speed & durability
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS schema_versions (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_json TEXT
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS idempotency_records (
                    idempotency_key TEXT PRIMARY KEY,
                    action_name TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_json TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    model_used TEXT NOT NULL,
                    tokens_used INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    success INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS episodic_vectors (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS semantic_cache (
                    cache_key TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
            """)

    # --- Task & Checkpoint Operations ---
    def save_task(self, task_id: str, goal: str, status: str = "PENDING") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (task_id, goal, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (task_id, goal, status, now, now),
            )

    def save_checkpoint(self, checkpoint_id: str, task_id: str, node_id: str, state: Dict[str, Any]) -> TaskCheckpoint:
        now = datetime.now(timezone.utc).isoformat()
        state_str = json.dumps(state)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints (checkpoint_id, task_id, node_id, state_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (checkpoint_id, task_id, node_id, state_str, now),
            )
        return TaskCheckpoint(
            checkpoint_id=checkpoint_id,
            task_id=task_id,
            node_id=node_id,
            state=state,
            created_at_utc=now,
        )

    def get_latest_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT checkpoint_id, task_id, node_id, state_json, created_at
                FROM checkpoints
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (task_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return TaskCheckpoint(
                checkpoint_id=row["checkpoint_id"],
                task_id=row["task_id"],
                node_id=row["node_id"],
                state=json.loads(row["state_json"]),
                created_at_utc=row["created_at"],
            )

    # --- Idempotency Key Gate ---
    def check_or_create_idempotency_key(
        self, idempotency_key: str, action_name: str, request_hash: str
    ) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Atomically inspects or acquires an idempotency reservation.
        Returns: (is_already_executed, cached_response_data)
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT status, response_json FROM idempotency_records WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cur.fetchone()
            if row:
                if row["status"] == "COMMITTED" and row["response_json"]:
                    return True, json.loads(row["response_json"])
                # In-flight or previously failed
                return True, None

            # Reserve key as PENDING
            conn.execute(
                """
                INSERT INTO idempotency_records (idempotency_key, action_name, request_hash, status, created_at)
                VALUES (?, ?, ?, 'PENDING', ?)
                """,
                (idempotency_key, action_name, request_hash, now),
            )
            return False, None

    def commit_idempotency_key(self, idempotency_key: str, response_data: Dict[str, Any]) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE idempotency_records
                SET status = 'COMMITTED', response_json = ?
                WHERE idempotency_key = ?
                """,
                (json.dumps(response_data), idempotency_key),
            )

    # --- Vector Shadow Index Atomic Switch ---
    def atomic_swap_shadow_index(self, shadow_table: str, live_table: str = "episodic_vectors") -> None:
        """
        Atomic index migration pattern:
        Shadow index validated -> atomic table rename switch -> zero query downtime.
        """
        with self._get_connection() as conn:
            backup_table = f"{live_table}_old_{int(datetime.now().timestamp())}"
            conn.executescript(f"""
                BEGIN TRANSACTION;
                ALTER TABLE {live_table} RENAME TO {backup_table};
                ALTER TABLE {shadow_table} RENAME TO {live_table};
                COMMIT;
            """)

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent task executions ordered by last update."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT task_id, goal, status, created_at, updated_at
                FROM tasks
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]
