"""goose plugins — list and inspect installed analysis plugins."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from goose.plugins.base import Plugin


@click.group()
def plugins() -> None:
    """Manage and inspect analysis plugins."""


def _safe_load_plugins() -> list[Plugin]:
    """Load plugins, skipping any that fail to import or instantiate."""
    import sys
    if sys.version_info >= (3, 12):
        from importlib.metadata import entry_points
    else:
        from importlib.metadata import entry_points

    eps = entry_points()
    group = (
        eps.get("goose.plugins", [])
        if isinstance(eps, dict)
        else eps.select(group="goose.plugins")
    )
    import logging
    _log = logging.getLogger(__name__)
    loaded: list[Plugin] = []
    for ep in group:
        try:
            cls = ep.load()
            if isinstance(cls, type) and issubclass(cls, Plugin):
                loaded.append(cls())
        except Exception as exc:  # noqa: BLE001
            _log.warning("Failed to load plugin entry point '%s': %s", ep.name, exc)
    return loaded


@plugins.command("list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def list_plugins(as_json: bool) -> None:
    """List all installed analysis plugins."""
    import json as json_mod

    found = _safe_load_plugins()

    if as_json:
        data = [
            {
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "min_mode": p.min_mode,
            }
            for p in found
        ]
        click.echo(json_mod.dumps(data, indent=2))
        return

    console = Console()
    if not found:
        console.print("No plugins installed.")
        return

    table = Table(title="Installed Plugins")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Min Mode")
    table.add_column("Description")

    for p in sorted(found, key=lambda x: x.name):
        table.add_row(p.name, p.version, p.min_mode, p.description)

    console.print(table)


@plugins.command("info")
@click.argument("name")
def plugin_info(name: str) -> None:
    """Show details about a specific plugin."""
    console = Console()
    found = _safe_load_plugins()
    match = [p for p in found if p.name == name]

    if not match:
        raise click.ClickException(f"Plugin '{name}' not found. Run 'goose plugins list' to see available plugins.")

    p = match[0]
    console.print(f"[bold]{p.name}[/bold] v{p.version}")
    console.print(f"  {p.description}")
    console.print(f"  Minimum flight mode: {p.min_mode}")
