"""goose analyze — full flight log analysis (all plugins)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from goose import __version__
from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.parsers.detect import parse_file
from goose.plugins.registry import load_plugins


def _parse_log(filepath: Path) -> Flight:
    """Parse a log file via the formal parser contract."""
    result = parse_file(filepath)
    if not result.success:
        errors = "; ".join(result.diagnostics.errors)
        raise click.ClickException(f"Cannot parse '{filepath.name}': {errors}")
    assert result.flight is not None
    return result.flight


@click.command()
@click.argument("logfile", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None, help="Save report to file")
@click.option("-f", "--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Show detailed evidence per finding")
@click.option("--plugin", "plugin_filter", multiple=True, help="Run only named plugins (repeatable)")
@click.option("--no-color", is_flag=True, default=False, help="Disable colored output")
def analyze(
    logfile: Path,
    output: Path | None,
    fmt: str,
    verbose: bool,
    plugin_filter: tuple[str, ...],
    no_color: bool,
) -> None:
    """Run all analysis plugins against a flight log.

    Unlike ``crash`` (which focuses on crash root-cause), ``analyze`` runs
    every registered plugin and reports each finding individually.
    """
    console = Console(no_color=no_color, stderr=False)

    try:
        flight = _parse_log(logfile)
    except Exception as e:
        raise click.ClickException(f"Failed to parse {logfile}: {e}") from e

    plugins = load_plugins()
    if plugin_filter:
        plugins = [p for p in plugins if p.name in plugin_filter]

    findings: list[Finding] = []
    for plugin in plugins:
        if not plugin.applicable(flight):
            continue
        try:
            findings.extend(plugin.analyze(flight, {}))
        except Exception as exc:  # noqa: BLE001
            findings.append(
                Finding(
                    plugin_name=plugin.name,
                    title=f"{plugin.name} plugin error",
                    severity="info",
                    score=50,
                    description=str(exc),
                )
            )

    if fmt == "json":
        report: dict[str, Any] = {
            "version": __version__,
            "file": str(logfile),
            "plugins_run": [p.name for p in plugins],
            "findings": [
                {
                    "plugin": f.plugin_name,
                    "title": f.title,
                    "severity": f.severity,
                    "score": f.score,
                    "description": f.description,
                    **({"evidence": f.evidence} if verbose and f.evidence else {}),
                }
                for f in findings
            ],
        }
        json_str = json.dumps(report, indent=2, default=str)
        if output:
            output.write_text(json_str)
            console.print(f"Report saved: {output}")
        else:
            click.echo(json_str)
    else:
        console.print()
        console.print(f"Goose v{__version__} -- Full Analysis", style="bold")
        console.print(f"  File: {logfile.name}")
        console.print(f"  Plugins run: {len(plugins)}")
        console.print()

        for f in sorted(findings, key=lambda x: x.score):
            icon = "+" if f.score >= 90 else ("!" if f.score >= 60 else "x")
            style = "green" if f.score >= 90 else ("yellow" if f.score >= 60 else "red")
            console.print(f"  [{style}]{icon}[/{style}] {f.plugin_name}: {f.title} (score {f.score})")
            if verbose:
                console.print(f"    {f.description}")
                if f.evidence:
                    for k, v in f.evidence.items():
                        console.print(f"      {k}: {v}")
        console.print()

        if output:
            file_console = Console(no_color=True, file=output.open("w"))
            for f in sorted(findings, key=lambda x: x.score):
                file_console.print(f"{f.plugin_name}: {f.title} (score {f.score})")
            console.print(f"  Report saved: {output}")
