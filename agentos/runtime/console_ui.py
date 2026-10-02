"""
Rich CLI presentation helpers (saas-ux-fusion: scannable groups, explicit error recovery).
"""

from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table


def render_task_result(console: Console, result: Dict[str, Any]) -> None:
    status = result.get("status", "UNKNOWN")
    status_style = "green" if status == "COMPLETED" else "red"

    summary = Table(show_header=False, box=None, padding=(0, 1))
    summary.add_row("Task ID", str(result.get("task_id", "—")))
    summary.add_row("Status", f"[bold {status_style}]{status}[/bold {status_style}]")

    if status != "COMPLETED":
        for line in _failed_step_lines(result.get("dag", {})):
            summary.add_row("Step", f"[red]{line}[/red]")

    console.print(Panel(summary, title="Result", border_style=status_style))


def request_action_approval(request: Dict[str, str], console: Console) -> bool:
    """Ask for one explicit approval before a consequential or ethically flagged action."""
    details = Table(show_header=False, box=None, padding=(0, 1))
    details.add_row("Action", request.get("description") or request["tool_name"])
    details.add_row("Tool", request["tool_name"])
    details.add_row("Reason", request["reason"])
    ethical_concern = request.get("ethical_concern")
    if ethical_concern:
        details.add_row("Ethical concern", ethical_concern)
    console.print(Panel(details, title="Approval required", border_style="yellow"))
    return Confirm.ask("Approve this action only?", default=False, console=console)


def _failed_step_lines(dag: Dict[str, Any]) -> List[str]:
    nodes = dag.get("nodes") or {}
    lines: List[str] = []
    for node_id, node in nodes.items():
        if node.get("status") == "FAILED":
            reason = node.get("error") or "unknown error"
            label = node.get("description") or node_id
            lines.append(f"{label}: {reason}")
    return lines[:5]
