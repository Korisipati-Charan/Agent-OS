from pathlib import Path

from agentos.config import AgentOSConfig
from agentos.cost_governor.crc_pipeline import CostGovernor
from agentos.cost_governor.semantic_cache import SemanticCache
from agentos.cost_governor.spend_tracker import SpendTracker
from agentos.memory.sqlite_store import SQLiteStore


def test_semantic_cache_round_trip(tmp_path: Path):
    store = SQLiteStore(tmp_path / "cache.db")
    cache = SemanticCache(store)
    assert cache.is_eligible("how do I verify audit chain", "faq") is True
    cache.store("how do I verify audit chain", "faq", {"answer": "agentos audit verify"})
    hit = cache.lookup("how do I verify audit chain", "faq")
    assert hit == {"answer": "agentos audit verify"}


def test_semantic_cache_skips_volatile_queries(tmp_path: Path):
    store = SQLiteStore(tmp_path / "cache.db")
    cache = SemanticCache(store)
    assert cache.is_eligible("show latest deployment status today", "summary") is False


def test_cost_governor_prepares_cached_prefix_messages(tmp_path: Path):
    config = AgentOSConfig.from_yaml("agentos.yaml")
    store = SQLiteStore(tmp_path / "gov.db")
    spend = SpendTracker(config)
    gov = CostGovernor(config, spend, store)

    prepared = gov.prepare_llm_call(
        task_type="planning",
        instruction="Compile a workspace report plan",
        tool_schemas=[{"name": "file_read", "description": "read workspace file"}],
    )
    assert prepared["cache_hit"] is False
    assert prepared["route"] is not None
    assert prepared["messages"][0]["role"] == "system"
    assert "file_read" in prepared["messages"][0]["content"]
