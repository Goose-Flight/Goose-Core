"""goose crash — crash root cause analysis CLI command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.text import Text

from goose import __version__
from goose.core.crash_detector import CrashAnalysis, analyze_crash
from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.parsers.ulog import ULogParser
from goose.plugins.base import Plugin


# Scoring weights per plugin
WEIGHTS: dict[str, float] = {
    "crash_detection": 3.0,
    "vibration": 1.5,
    "battery_sag": 2.0,
    "gps_health": 1.5,
    "motor_saturation": 2.0,
    "ekf_consistency": 1.5,
    "rc_signal": 1.0,
    "attitude_tracking": 1.0,
    "position_tracking": 1.0,
    "failsafe_events": 1.5,
    "log_health": 0.5,
}


def _parse_log(filepath: Path) -> Flight:
    """Parse a log file, auto-detecting format."""
    ext = filepath.suffix.lower()
    if ext == ".ulg":
        parser = ULogParser()
        return parser.parse(filepath)
    raise click.ClickException(f"Unsupported log format: {ext}")


def _load_and_run_plugins(flight: Flight) -> list[Finding]:
    """Discover, filter, and run all applicable plugins."""
    findings: list[Finding] = []
    try:
        from goose.plugins.registry import load_plugins
        plugins = load_plugins()
    except Exception:
        plugins = []

    for plugin in plugins:
        if not plugin.applicable(flight):
            continue
        try:
            plugin_findings = plugin.analyze(flight, {})
            findings.extend(plugin_findings)
        except Exception:
            # Plugin failed — record as info finding so it appears in output
            findings.append(Finding(
                plugin_name=plugin.name,
                title=f"{plugin.name} plugin error",
                severity="info",
                score=50,
                description=f"Plugin {plugin.name} failed to analyze this flight",
            ))
    return findings


def _format_duration(seconds: float) -> str:
    """Format seconds as XmYYs."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}m{s:02d}s"


def _overall_score(findings: list[Finding]) -> int:
    """Compute weighted overall score from plugin findings."""
    # Group best (minimum) score per plugin
    plugin_scores: dict[str, int] = {}
    for f in findings:
        if f.plugin_name not in plugin_scores:
            plugin_scores[f.plugin_name] = f.score
        else:
            plugin_scores[f.plugin_name] = min(plugin_scores[f.plugin_name], f.score)

    total_weight = 0.0
    weighted_sum = 0.0
    for plugin_name, score in plugin_scores.items():
        w = WEIGHTS.get(plugin_name, 1.0)
        weighted_sum += score * w
        total_weight += w

    if total_weight == 0:
        return 0
    return round(weighted_sum / total_weight)


def _plugin_result_line(plugin_name: str, score: int, summary: str) -> Text:
    """Format a single plugin result line."""
    # Icon based on score
    if score >= 90:
        icon = "[+]"
        style = "green"
    elif score >= 60:
        icon = "[*]"
        style = "yellow"
    else:
        icon = "[!]"
        style = "red"

    # Pad plugin name with dots to fixed width
    name_padded = f"{plugin_name} ".ljust(22, ".")
    score_str = str(score).rjust(3)

    text = Text()
    text.append(f"  {icon} ", style=style)
    text.append(f"{name_padded} {score_str}", style=style)
    text.append(f"   {summary}")
    return text


def _print_text_report(
    flight: Flight,
    findings: list[Finding],
    analysis: CrashAnalysis,
    console: Console,
    verbose: bool,
) -> None:
    """Print the Rich-formatted crash report to the console."""
    filepath = Path(flight.metadata.source_file)
    duration = _format_duration(flight.metadata.duration_sec)
    hw = flight.metadata.hardware or "Unknown"
    vehicle = flight.metadata.vehicle_type.capitalize()
    fw = flight.metadata.firmware_version
    mode = flight.primary_mode.capitalize()

    console.print()
    console.print(f"[GOOSE] Goose v{__version__} - Crash Analysis", style="bold")
    console.print()
    console.print(f"  File: {filepath.name}")
    console.print(f"  Aircraft: PX4 {fw} · {vehicle} · {hw}")
    console.print(f"  Duration: {duration} · Mode: {mode}")
    console.print()

    if analysis.crashed:
        conf_pct = int(analysis.confidence * 100)
        label = analysis.classification.replace("_", " ").title()
        console.print(
            f"  [CRASH] CRASH DETECTED — {label} ({conf_pct}% confidence)",
            style="bold red",
        )
        console.print()
        console.print(f"  Root cause: {analysis.root_cause}")

        # Impact summary from timeline
        if analysis.timeline:
            last_event = analysis.timeline[-1]
            ts = last_event["timestamp"]
            console.print(f"  Impact: t={ts:.0f}s")

        console.print()

        # Timeline
        if analysis.timeline:
            console.print("  Timeline:", style="bold")
            for event in analysis.timeline:
                ts = event["timestamp"]
                desc = event["event"]
                console.print(f"    t={ts:.0f}s  {desc}")
            console.print()
    else:
        console.print("  [OK] NO CRASH DETECTED", style="bold green")
        console.print()

    # Plugin results
    if findings:
        console.print("  Plugin Results:", style="bold")
        # Group findings by plugin, take worst score per plugin
        plugin_best: dict[str, tuple[int, str]] = {}
        for f in findings:
            if f.plugin_name not in plugin_best or f.score < plugin_best[f.plugin_name][0]:
                plugin_best[f.plugin_name] = (f.score, f.title)

        # Sort: worst scores first
        for pname, (score, title) in sorted(plugin_best.items(), key=lambda x: x[1][0]):
            console.print(_plugin_result_line(pname, score, title))

        if verbose:
            console.print()
            console.print("  Detailed Evidence:", style="bold")
            for f in findings:
                console.print(f"    [{f.severity}] {f.plugin_name}: {f.title}")
                console.print(f"      {f.description}")
                if f.evidence:
                    for k, v in f.evidence.items():
                        console.print(f"        {k}: {v}")

        console.print()

    # Inspect checklist
    if analysis.crashed and analysis.inspect_checklist:
        console.print("  Inspect:", style="bold")
        for item in analysis.inspect_checklist:
            console.print(f"  [ ] {item}")
        console.print()

    # Overall score
    score = _overall_score(findings)
    console.print(f"  Overall Score: {score}/100", style="bold")
    console.print()


def _build_json_report(
    flight: Flight,
    findings: list[Finding],
    analysis: CrashAnalysis,
) -> dict[str, Any]:
    """Build a JSON-serializable report dict."""
    return {
        "version": __version__,
        "file": flight.metadata.source_file,
        "autopilot": flight.metadata.autopilot,
        "firmware_version": flight.metadata.firmware_version,
        "vehicle_type": flight.metadata.vehicle_type,
        "duration_sec": flight.metadata.duration_sec,
        "crashed": analysis.crashed,
        "crash_classification": analysis.classification,
        "crash_confidence": analysis.confidence,
        "root_cause": analysis.root_cause,
        "evidence_chain": analysis.evidence_chain,
        "contributing_factors": analysis.contributing_factors,
        "inspect_checklist": analysis.inspect_checklist,
        "timeline": analysis.timeline,
        "findings": [
            {
                "plugin": f.plugin_name,
                "title": f.title,
                "severity": f.severity,
                "score": f.score,
                "description": f.description,
            }
            for f in findings
        ],
        "overall_score": _overall_score(findings),
    }


@click.command()
@click.argument("logfile", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None, help="Save report to file")
@click.option("-f", "--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Show detailed evidence")
@click.option("--no-color", is_flag=True, default=False, help="Disable colored output")
def crash(
    logfile: Path,
    output: Path | None,
    fmt: str,
    verbose: bool,
    no_color: bool,
) -> None:
    """Analyze a flight log for crash root cause."""
    console = Console(no_color=no_color, stderr=False)

    # Parse
    try:
        flight = _parse_log(logfile)
    except Exception as e:
        raise click.ClickException(f"Failed to parse {logfile}: {e}") from e

    # Run plugins
    findings = _load_and_run_plugins(flight)

    # Analyze
    analysis = analyze_crash(flight, findings)

    # Output
    if fmt == "json":
        report = _build_json_report(flight, findings, analysis)
        json_str = json.dumps(report, indent=2, default=str)
        if output:
            output.write_text(json_str)
            console.print(f"Report saved: {output}")
        else:
            click.echo(json_str)
    else:
        _print_text_report(flight, findings, analysis, console, verbose)
        if output:
            # Save text output to file
            file_console = Console(no_color=True, file=output.open("w"))
            _print_text_report(flight, findings, analysis, file_console, verbose)
            console.print(f"  Report saved: {output}")
