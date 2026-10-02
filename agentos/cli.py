"""
AgentOS Command Line Interface.
Administrative controls, task execution, health server, audit verification, and eval runners.
"""

import argparse
import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from agentos.core.supervisor import SafetySupervisor
from agentos.evals.golden_tasks import GoldenTaskRunner
from agentos.evals.red_team import RedTeamSuite
from agentos.runtime.bootstrap import build_runtime
from agentos.runtime.health_server import HealthServer
from agentos.runtime.console_ui import render_task_result, request_action_approval
from agentos.runtime.plan_builder import build_workspace_task_plan

console = Console()


def cmd_run(args: argparse.Namespace) -> None:
    runtime = build_runtime(config_path=args.config, workspace=args.workspace)
    engine = runtime.engine

    console.print(Panel(f"[bold cyan]AgentOS v3.0.1[/bold cyan]\n{args.goal}", title="Task", border_style="cyan"))

    planned_steps = build_workspace_task_plan(goal=args.goal, workspace=args.workspace)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Running preflight gates and sandbox execution…", total=None)
        result = asyncio.run(
            engine.execute_task(
                goal=args.goal,
                planned_steps=planned_steps,
                approval_callback=lambda request: request_action_approval(request, console),
            )
        )

    render_task_result(console, result)


def cmd_audit_verify(args: argparse.Namespace) -> None:
    runtime = build_runtime(config_path=args.config)
    valid, message = runtime.audit_logger.verify_integrity()
    if valid:
        console.print(f"[bold green]Audit chain verified.[/bold green] {message}")
    else:
        console.print(f"[bold red]Audit chain failed.[/bold red] {message}")
        sys.exit(1)


def cmd_eval(args: argparse.Namespace) -> None:
    runtime = build_runtime(config_path=args.config)
    console.print("[bold]Golden tasks[/bold]")

    golden_runner = GoldenTaskRunner()
    g_res = golden_runner.run_suite()
    console.print(f"  Success rate: [green]{g_res['success_rate_pct']:.1f}%[/green]")

    console.print("[bold]Red team[/bold]")
    red_team = RedTeamSuite(
        injection_defense=runtime.injection_defense,
        policy_engine=runtime.policy_engine,
    )
    r_res = red_team.execute_adversarial_suite()
    console.print(
        f"  Defended: [green]{r_res['defended_count']}[/green] / {r_res['total_adversarial_cases']} vectors"
    )


def cmd_info(args: argparse.Namespace) -> None:
    runtime = build_runtime(config_path=args.config)
    sup: SafetySupervisor = runtime.supervisor
    caps = sup.platform

    from rich.table import Table

    table = Table(title="Platform supervisor", show_header=True, header_style="bold")
    table.add_column("Mechanism", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Operating system", caps.os_name)
    table.add_row("Windows host boundary", "Active" if caps.is_windows else "N/A")
    table.add_row("cgroups v2", "Available" if caps.cgroups_v2_supported else "Not on this host")
    table.add_row("seccomp", "Available" if caps.seccomp_supported else "Not on this host")
    table.add_row("Isolation mode", caps.boundary_mechanism)

    console.print(table)


def cmd_serve(args: argparse.Namespace) -> None:
    runtime = build_runtime(config_path=args.config, workspace=args.workspace)
    console.print(
        Panel(
            f"Listening on [bold]{args.host}:{args.port}[/bold]\n"
            "Probes: [cyan]/healthz[/cyan] (liveness), [cyan]/ready[/cyan] (readiness)",
            title="AgentOS HTTP",
            border_style="blue",
        )
    )
    server = HealthServer(
        host=args.host,
        port=args.port,
        supervisor=runtime.supervisor,
        sqlite_store=runtime.sqlite_store,
    )
    try:
        server.run_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentOS CLI (v3.0.1)")
    parser.add_argument("--config", default="agentos.yaml", help="Path to agentos.yaml")
    parser.add_argument(
        "--workspace",
        default="./workspace",
        help="Authorized workspace directory for file tools",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_run = subparsers.add_parser("run", help="Execute a goal through the cognitive engine")
    p_run.add_argument("goal", help="High-level goal description")
    p_run.set_defaults(func=cmd_run)

    p_audit = subparsers.add_parser("audit", help="Audit log operations")
    p_audit_sub = p_audit.add_subparsers(dest="audit_cmd", required=True)
    p_audit_v = p_audit_sub.add_parser("verify", help="Verify SHA-256 hash chain")
    p_audit_v.set_defaults(func=cmd_audit_verify)

    p_eval = subparsers.add_parser("eval", help="Run golden tasks and red-team suite")
    p_eval.set_defaults(func=cmd_eval)

    p_info = subparsers.add_parser("info", help="Show platform isolation capabilities")
    p_info.set_defaults(func=cmd_info)

    p_serve = subparsers.add_parser("serve", help="Start HTTP probe server for Kubernetes/Docker")
    p_serve.add_argument("--host", default="0.0.0.0", help="Bind address")
    p_serve.add_argument("--port", type=int, default=8000, help="Listen port")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
