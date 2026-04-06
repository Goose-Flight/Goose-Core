"""goose analyze — run all plugins against a flight log."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from goose import __version__
from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.parsers.ulog import ULogParser
from goose.plugins.registry import load_plugins


@click.command()
@click.argument("logfile", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), help="Save JSON report to file")
@click.option("-f", "--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--no-color", is_flag=True, help="Disable colored output")
def analyze(logfile: str, output: str | None, fmt: str, no_color: bool) -> None:
    """Analyze a flight log with all available plugins."""
    console = Console(force_terminal=not no_color, no_color=no_color)
    path = Path(logfile)

    parser = ULogParser()
    if not parser.can_parse(path):
        console.print(f"[red]Unsupported file format: {path.suffix}[/red]")
        sys.exit(1)

    try:
        flight = parser.parse(path)
    except Exception as e:
        console.print(f"[red]Parse error: {e}[/red]")
        sys.exit(1)

    plugins = load_plugins()
    all_findings: list[Finding] = []

    for plugin in plugins:
        try:
            findings = plugin.analyze(flight, {})
            all_findings.extend(findings)
        except Exception as e:
            all_findings.append(Finding(
                plugin_name=plugin.name,
                title=f"Plugin error: {e}",
                severity="warning",
                score=50,
                description=f"Plugin {plugin.name} raised an exception: {e}",
            ))

    avg_score = sum(f.score for f in all_findings) / len(all_findings) if all_findings else 100

    if fmt == "json":
        report = {
            "version": __version__,
            "file": str(path.name),
            "duration_sec": flight.metadata.duration_sec,
            "autopilot": flight.metadata.autopilot,
            "vehicle_type": flight.metadata.vehicle_type,
            "overall_score": round(avg_score),
            "total_findings": len(all_findings),
            "findings": [
                {"plugin": f.plugin_name, "title": f.title, "severity": f.severity,
                 "score": f.score, "description": f.description, "phase": f.phase}
                for f in all_findings
            ],
        }
        text = json.dumps(report, indent=2)
        if output:
            Path(output).write_text(text)
            console.print(f"Report saved to {output}")
        else:
            click.echo(text)
    else:
        console.print(f"\n[bold]Goose v{__version__} — Flight Analysis[/bold]\n")
        console.print(f"  File: {path.name}")
        console.print(f"  Duration: {flight.metadata.duration_sec:.0f}s")
        console.print(f"  Overall Score: {avg_score:.0f}/100")
        console.print(f"  Plugins: {len(plugins)} loaded, {len(all_findings)} findings\n")

        if all_findings:
            table = Table(title="Findings")
            table.add_column("Plugin", style="cyan")
            table.add_column("Severity", style="bold")
            table.add_column("Score", justify="right")
            table.add_column("Title")
            for f in sorted(all_findings, key=lambda x: x.score):
                sev_color = {"critical": "red", "warning": "yellow", "info": "blue", "pass": "green"}.get(f.severity, "white")
                table.add_row(f.plugin_name, f"[{sev_color}]{f.severity}[/{sev_color}]", str(f.score), f.title)
            console.print(table)
        else:
            console.print("  [green]No findings — flight looks clean![/green]")
