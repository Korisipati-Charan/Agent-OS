"""
Tests for SQLiteStore: WAL mode, durable checkpoints, and atomic table migrations.
"""

from pathlib import Path
from agentos.memory.sqlite_store import SQLiteStore


def test_sqlite_checkpoints_and_tasks(tmp_path: Path):
    store = SQLiteStore(tmp_path / "test.db")

    # 1. Save and update task
    store.save_task("task_01", "Build web application", status="RUNNING")

    # 2. Checkpoint state
    chk = store.save_checkpoint(
        checkpoint_id="chk_01",
        task_id="task_01",
        node_id="node_01",
        state={"step": "compiler", "progress": 50},
    )
    assert chk.checkpoint_id == "chk_01"

    latest = store.get_latest_checkpoint("task_01")
    assert latest is not None
    assert latest.node_id == "node_01"
    assert latest.state["progress"] == 50


def test_sqlite_shadow_index_swap(tmp_path: Path):
    store = SQLiteStore(tmp_path / "test.db")

    with store._get_connection() as conn:
        conn.execute("CREATE TABLE episodic_vectors_shadow (id TEXT PRIMARY KEY, content TEXT, metadata_json TEXT, created_at TEXT);")
        conn.execute("INSERT INTO episodic_vectors_shadow VALUES ('v1', 'shadow content', '{}', '2026-01-01');")

    # Atomic swap
    store.atomic_swap_shadow_index("episodic_vectors_shadow", "episodic_vectors")

    with store._get_connection() as conn:
        cur = conn.execute("SELECT content FROM episodic_vectors WHERE id = 'v1'")
        row = cur.fetchone()
        assert row is not None
        assert row["content"] == "shadow content"
