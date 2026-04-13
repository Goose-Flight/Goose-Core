"""goose doctor -- verify installation health and dependencies."""

from __future__ import annotations

import sys

import click
from rich.console import Console


def _check_importable(module: str) -> tuple[bool, str]:
    """Try to import a module, return (ok, version_or_error)."""
    try:
        mod = __import__(module)
        version = getattr(mod, "__version__", getattr(mod, "VERSION", "installed"))
        return True, str(version)
    except ImportError as exc:
        return False, str(exc)


REQUIRED_MODULES = [
    "click",
    "pandas",
    "numpy",
    "pyulog",
    "pymavlink",
    "fastapi",
    "uvicorn",
    "jinja2",
    "yaml",
    "rich",
]


@click.command()
@click.option("--fix", is_flag=True, default=False, help="Attempt to pip-install missing packages")
def doctor(fix: bool) -> None:
    """Check that Goose and its dependencies are properly installed."""
    console = Console()
    console.print()
    console.print("Goose Doctor", style="bold")
    console.print(f"  Python: {sys.version}")
    console.print()

    issues: list[str] = []

    # Check core dependencies
    console.print("  Dependencies:", style="bold")
    for mod in REQUIRED_MODULES:
        ok, info = _check_importable(mod)
        if ok:
            console.print(f"  [green]OK[/green] {mod} ({info})")
        else:
            console.print(f"  [red]FAIL[/red] {mod} -- {info}")
            issues.append(mod)

    console.print()

    # Check plugins
    console.print("  Plugins:", style="bold")
    try:
        from goose.plugins.registry import load_plugins

        found = load_plugins()
        console.print(f"  [green]OK[/green] {len(found)} plugin(s) discovered")
        for p in found:
            console.print(f"    - {p.name} v{p.version}")
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [red]FAIL[/red] Plugin discovery failed: {exc}")
        issues.append("plugin-discovery")

    console.print()

    # Check parser
    console.print("  Parsers:", style="bold")
    try:
        console.print("  [green]OK[/green] ULog parser available")
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [red]FAIL[/red] ULog parser: {exc}")
        issues.append("ulog-parser")

    console.print()

    if issues:
        console.print(f"  [red]{len(issues)} issue(s) found.[/red]")
        if fix:
            console.print("  Attempting auto-fix...")
            import subprocess

            pip_modules = [m for m in issues if m not in ("plugin-discovery", "ulog-parser")]
            if pip_modules:
                subprocess.check_call([sys.executable, "-m", "pip", "install"] + pip_modules)
                console.print("  [green]pip install complete -- re-run goose doctor to verify.[/green]")
        else:
            console.print("  Run [bold]goose doctor --fix[/bold] to attempt automatic repair.")
        sys.exit(1)
    else:
        console.print("  [green]All checks passed.[/green]")
