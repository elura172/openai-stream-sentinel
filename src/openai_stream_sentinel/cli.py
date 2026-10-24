"""Rich CLI Interface for OpenAI Stream Sentinel.

Enables developers and SREs to run live or simulated diagnostics, observe TTFT/jitter,
and export enterprise-ready Root Cause Analysis (RCA) reports.
"""

import sys
import argparse
import asyncio
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from .models import FailureDomain, SeverityLevel
from .canary import CanaryRunner


console = Console()

SCENARIO_MAP = {
    "healthy": FailureDomain.HEALTHY,
    "buffer-bloat": FailureDomain.PROXY_BUFFER_BLOAT,
    "cache-miss": FailureDomain.PROMPT_CACHE_EVICTION,
    "rate-limit": FailureDomain.RATE_LIMIT_BURST,
    "tcp-rst": FailureDomain.TCP_RST_TRUNCATION,
    "tool-timeout": FailureDomain.TOOL_TIMEOUT_SCHEMA_MISMATCH
}


def print_incident_summary(report):
    incident = report.incident
    metrics = incident.metrics

    # Color mapping
    sev_color = "green"
    if "SEV-1" in incident.severity.value:
        sev_color = "bold red"
    elif "SEV-2" in incident.severity.value:
        sev_color = "bold yellow"
    elif "SEV-3" in incident.severity.value:
        sev_color = "yellow"

    header_text = Text()
    header_text.append(f"[{incident.incident_id}] ", style="bold cyan")
    header_text.append(f"{incident.failure_domain.value} ", style="bold white")
    header_text.append(f"({incident.severity.value})", style=sev_color)

    summary_panel = Panel(
        f"[bold]Root Cause:[/bold] {incident.root_cause_summary}\n\n"
        f"[bold]Theoretical Reference:[/bold] [italic cyan]{incident.mit_course_reference}[/italic cyan]",
        title=header_text,
        border_style=sev_color
    )
    console.print(summary_panel)

    table = Table(title="Streaming Telemetry & SLI Metrics", show_header=True, header_style="bold magenta")
    table.add_column("Metric / SLI", style="cyan")
    table.add_column("Observed Value", style="white")
    table.add_column("Baseline Target", style="dim")
    table.add_column("Status", style="bold")

    # TTFT Row
    ttft_status = "[green]NOMINAL[/green]" if metrics.ttft_ms < 400.0 else "[red]DEGRADED[/red]"
    table.add_row("Time to First Token (TTFT)", f"{metrics.ttft_ms:.1f} ms", "< 350.0 ms", ttft_status)

    # Generation speed
    table.add_row("Token Generation Cadence", f"{metrics.tokens_per_second:.1f} tok/s", "> 30.0 tok/s", "[green]NOMINAL[/green]" if metrics.tokens_per_second > 20 else "[yellow]ATTENTION[/yellow]")

    # Jitter P95 & Max
    jitter_status = "[green]NOMINAL[/green]" if metrics.jitter_p95_ms < 100.0 and metrics.jitter_max_ms < 500.0 else "[red]EXCESSIVE JITTER[/red]"
    table.add_row("P95 Inter-Chunk Jitter", f"{metrics.jitter_p95_ms:.1f} ms", "< 60.0 ms", jitter_status)
    if metrics.jitter_max_ms > 200.0:
        table.add_row("Max Inter-Chunk Delay (Stall)", f"[bold red]{metrics.jitter_max_ms:.1f} ms[/bold red]", "< 150.0 ms", "[red]BUFFER STALL[/red]")

    # Prompt Cache
    cache_display = "[green]HIT[/green]" if metrics.prompt_cache_hit else "[yellow]MISS / UNCACHED[/yellow]"
    table.add_row("KV Prompt Cache Locality", cache_display, "Prefix >1k tok", "[cyan]EVALUATED[/cyan]")

    # Total Duration
    table.add_row("Total Stream Duration", f"{metrics.total_duration_s:.3f} s", "N/A", "[blue]RECORDED[/blue]")

    console.print(table)


async def async_main():
    parser = argparse.ArgumentParser(description="OpenAI Stream Sentinel — Enterprise Observability & Auto-RCA Canary")
    parser.add_argument("command", choices=["run", "probe", "suite"], help="Execution mode")
    parser.add_argument("--scenario", choices=list(SCENARIO_MAP.keys()) + ["all"], default="all", help="Scenario to simulate in 'run' mode")
    parser.add_argument("--model", default="gpt-4o", help="Target model for live probe")
    parser.add_argument("--prompt", default="Ping probe test", help="Prompt text for live probe")
    parser.add_argument("--out", type=Path, default=None, help="Path to write dual-format Markdown RCA report")

    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]OpenAI Stream Sentinel[/bold cyan] · [yellow]Enterprise Diagnostic Probe & Auto-RCA Canary[/yellow]\n"
        "[dim]Theoretical Framework: MIT 6.033 (Fault Tolerance) · MIT 6.172 (Performance) · MIT 6.824 (Distributed Systems)[/dim]",
        border_style="cyan"
    ))

    reports = []

    if args.command == "run":
        if args.scenario == "all":
            console.print("[bold yellow]Executing full enterprise failure simulation matrix (5 scenarios + baseline)...[/bold yellow]\n")
            for name, domain in SCENARIO_MAP.items():
                with console.status(f"[cyan]Simulating {name} ({domain.value})...[/cyan]"):
                    rep = await CanaryRunner.run_simulation(domain)
                    reports.append(rep)
                print_incident_summary(rep)
                console.print()
        else:
            domain = SCENARIO_MAP[args.scenario]
            with console.status(f"[cyan]Simulating {args.scenario} ({domain.value})...[/cyan]"):
                rep = await CanaryRunner.run_simulation(domain)
                reports.append(rep)
            print_incident_summary(rep)

    elif args.command == "suite":
        console.print("[bold green]Running comprehensive automated verification test suite...[/bold green]\n")
        for name, domain in SCENARIO_MAP.items():
            rep = await CanaryRunner.run_simulation(domain)
            reports.append(rep)
            print_incident_summary(rep)
            console.print()

    elif args.command == "probe":
        console.print(f"[bold cyan]Launching live probe against model: {args.model}...[/bold cyan]")
        try:
            rep = await CanaryRunner.run_live_probe(model=args.model, prompt=args.prompt)
            reports.append(rep)
            print_incident_summary(rep)
        except Exception as e:
            console.print(f"[bold red]Live probe failed:[/bold red] {e}")
            sys.exit(1)

    # Export markdown if requested or if output provided
    if args.out and reports:
        output_content = "# OpenAI Stream Sentinel — Incident RCA & Diagnostic Brief\n\n"
        output_content += f"Generated on `{reports[0].incident.timestamp}`\n\n"
        for rep in reports:
            output_content += f"---\n\n{rep.customer_advisory}\n\n---\n\n{rep.engineering_postmortem}\n\n"
        
        args.out.write_text(output_content, encoding="utf-8")
        console.print(f"\n[bold green]✓ Exported dual-format RCA report to:[/bold green] [underline]{args.out}[/underline]")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
