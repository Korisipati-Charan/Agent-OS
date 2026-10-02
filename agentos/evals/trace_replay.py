"""
AgentOS Deterministic Trace Replay Engine.
Implements the Core Invariant: "Never equate a log with deterministic replay."
Records model/tool outputs, random seeds, and environment metadata.
During replay, external side effects are stubbed or reconciled rather than blindly re-executed.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RecordedStep(BaseModel):
    step_id: str
    tool_name: str
    inputs: Dict[str, Any]
    output: Any
    random_seed: Optional[int] = None
    environment_metadata: Dict[str, str] = Field(default_factory=dict)
    is_external_side_effect: bool = False


class TraceSession(BaseModel):
    session_id: str
    goal: str
    recorded_steps: List[RecordedStep] = Field(default_factory=list)


class TraceReplayEngine:
    def __init__(self, trace_store_dir: str | Path = "data/traces") -> None:
        self.trace_store_dir = Path(trace_store_dir)
        self.trace_store_dir.mkdir(parents=True, exist_ok=True)

    def record_step(self, session: TraceSession, step: RecordedStep) -> None:
        session.recorded_steps.append(step)

    def replay_step(
        self,
        step: RecordedStep,
        side_effect_reconciler: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Replays a step. If the step is an external side effect,
        it is stubbed using recorded outputs or reconciled against actual external state,
        preventing duplicate external writes or charges.
        """
        if step.is_external_side_effect:
            reconciled_val = (side_effect_reconciler or {}).get(step.step_id) or step.output
            return {
                "step_id": step.step_id,
                "replayed": True,
                "mode": "stubbed_external_side_effect",
                "output": reconciled_val,
            }

        # For non-side-effect actions, return deterministic recorded output
        return {
            "step_id": step.step_id,
            "replayed": True,
            "mode": "deterministic_recorded",
            "output": step.output,
        }
