"""Rich CLI Interface for OpenAI Stream Sentinel.

Run a streaming probe or synthetic scenario and export diagnostic drafts.
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
        f"[bold]Assessment:[/bold] {incident.root_cause_summary}\n\n"
        f"[bold]Diagnostic rule:[/bold] [italic cyan]{incident.diagnostic_basis}[/italic cyan]",
        title=header_text,
        border_style=sev_color
    )
    console.print(summary_panel)

    table = Table(title="Streaming Observations", show_header=True, header_style="bold magenta")
    table.add_column("Metric / SLI", style="cyan")
    table.add_column("Observed Value", style="white")
    table.add_column("Local reference", style="dim")
    table.add_column("Status", style="bold")

    # TTFT Row
    ttft_display = "UNAVAILABLE" if metrics.ttft_ms is None else f"{metrics.ttft_ms:.1f} ms"
    ttft_status = "NO CONTENT" if metrics.ttft_ms is None else (
        "[green]NOMINAL[/green]" if metrics.ttft_ms < 400.0 else "[red]DEGRADED[/red]"
    )
    table.add_row("Time to First Token (TTFT)", ttft_display, "< 400.0 ms", ttft_status)

    # Generation speed
    chunk_rate = "UNAVAILABLE" if metrics.chunks_per_second is None else f"{metrics.chunks_per_second:.1f} chunks/s"
    table.add_row("Chunk Delivery Rate", chunk_rate, "Informational", "[blue]RECORDED[/blue]")

    # Jitter P95 & Max
    interval_status = "[yellow]LOW SAMPLE[/yellow]" if metrics.inter_chunk_interval_sample_count < 20 else (
        "[green]NOMINAL[/green]" if metrics.inter_chunk_interval_p95_ms < 100.0 and metrics.inter_chunk_interval_max_ms < 500.0 else "[red]LONG INTERVAL[/red]"
    )
    table.add_row("P95 Inter-Chunk Interval", f"{metrics.inter_chunk_interval_p95_ms:.1f} ms (n={metrics.inter_chunk_interval_sample_count})", "< 100.0 ms", interval_status)
    if metrics.inter_chunk_interval_max_ms > 200.0:
        table.add_row("Max Inter-Chunk Interval", f"[bold red]{metrics.inter_chunk_interval_max_ms:.1f} ms[/bold red]", "< 200.0 ms", "[red]LONG GAP[/red]")

    completion_tokens = "UNAVAILABLE" if metrics.completion_tokens is None else str(metrics.completion_tokens)
    table.add_row("Completion Tokens (API usage)", completion_tokens, "Provider-reported", "[blue]RECORDED[/blue]")

    # Prompt Cache
    if metrics.prompt_cache_hit is True:
        cache_display, cache_status = "LIKELY HIT", "[yellow]HEURISTIC[/yellow]"
    elif metrics.prompt_cache_hit is False:
        cache_display, cache_status = "LIKELY MISS", "[yellow]HEURISTIC[/yellow]"
    else:
        cache_display, cache_status = "UNKNOWN", "[dim]INSUFFICIENT SIGNAL[/dim]"
    table.add_row("Prompt Cache Signal", cache_display, "Heuristic only", cache_status)

    # Total Duration
    table.add_row("Total Stream Duration", f"{metrics.total_duration_s:.3f} s", "N/A", "[blue]RECORDED[/blue]")

    console.print(table)
    if metrics.error_occurred:
        console.print(f"Probe error (HTTP {metrics.http_status_code or 'unavailable'}): {metrics.error_details}", markup=False)


async def async_main():
    parser = argparse.ArgumentParser(description="OpenAI Stream Sentinel — Client-side streaming diagnostics")
    parser.add_argument("command", choices=["run", "probe", "suite"], help="Execution mode")
    parser.add_argument("--scenario", choices=list(SCENARIO_MAP.keys()) + ["all"], default="all", help="Scenario to simulate in 'run' mode")
    parser.add_argument("--model", default="gpt-4o", help="Target model for live probe")
    parser.add_argument("--prompt", default="Ping probe test", help="Prompt text for live probe")
    parser.add_argument("--timeout", type=float, default=30.0, help="Total live probe deadline in seconds (default: 30)")
    parser.add_argument("--out", type=Path, default=None, help="Path to write Markdown diagnostic drafts")

    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]OpenAI Stream Sentinel[/bold cyan] · [yellow]Client-side streaming diagnostics[/yellow]\n"
        "[dim]Independent project · observations and heuristic triage[/dim]",
        border_style="cyan"
    ))

    reports = []

    if args.command == "run":
        if args.scenario == "all":
            console.print("[bold yellow]Executing all six synthetic scenarios (baseline + five failure profiles)...[/bold yellow]\n")
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
        console.print("[bold green]Running the synthetic scenario suite...[/bold green]\n")
        for name, domain in SCENARIO_MAP.items():
            rep = await CanaryRunner.run_simulation(domain)
            reports.append(rep)
            print_incident_summary(rep)
            console.print()

    elif args.command == "probe":
        console.print(f"[bold cyan]Launching live probe against model: {args.model}...[/bold cyan]")
        try:
            rep = await CanaryRunner.run_live_probe(model=args.model, prompt=args.prompt, timeout=args.timeout)
            reports.append(rep)
            print_incident_summary(rep)
        except Exception as e:
            console.print(f"[bold red]Live probe failed:[/bold red] {e}")
            sys.exit(1)

    # Export markdown if requested or if output provided
    if args.out and reports:
        output_content = "# OpenAI Stream Sentinel — Streaming Diagnostic Brief\n\n"
        output_content += f"Generated on `{reports[0].incident.timestamp}`\n\n"
        for rep in reports:
            output_content += f"---\n\n{rep.customer_advisory}\n\n---\n\n{rep.engineering_postmortem}\n\n"
        
        args.out.write_text(output_content, encoding="utf-8")
        console.print(f"\n[bold green]✓ Exported diagnostic report to:[/bold green] [underline]{args.out}[/underline]")

    return int(args.command == "probe" and any(rep.incident.failure_domain != FailureDomain.HEALTHY for rep in reports))


def main():
    sys.exit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
