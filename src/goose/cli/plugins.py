"""goose plugins — list installed analysis plugins."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from goose.plugins.registry import load_plugins


@click.command()
@click.option("--no-color", is_flag=True, help="Disable colored output")
def plugins(no_color: bool) -> None:
    """List all available analysis plugins."""
    console = Console(no_color=no_color)
    loaded = load_plugins()

    if not loaded:
        console.print("[yellow]No plugins found.[/yellow]")
        return

    table = Table(title=f"Goose Plugins ({len(loaded)} loaded)")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Description")

    for p in sorted(loaded, key=lambda x: x.name):
        table.add_row(p.name, getattr(p, "version", "-"), getattr(p, "description", "-"))

    console.print(table)
