"""
AgentOS v3.0.1 - Autonomous Agent Supervisor and Cognitive Engine.

Core Invariants:
1. Authorize before side effect (Action Gate).
2. Verify after side effect (Postcondition Gate).
3. Checkpoint before retry (Durable DAG & Idempotency).
4. Replay records randomness & environment; mocks/reconciles side effects.
5. Hot-patching activates exclusively at task boundaries.
"""

__version__ = "3.0.1"
