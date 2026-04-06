"""Click CLI root group for Goose."""

from __future__ import annotations

import click

from goose import __version__
from goose.cli.crash import crash
from goose.cli.analyze import analyze
from goose.cli.serve import serve
from goose.cli.plugins import plugins


@click.group()
@click.version_option(version=__version__, prog_name="goose")
def cli() -> None:
    """Goose — Open source drone flight log crash analysis and validation engine."""


cli.add_command(crash)
cli.add_command(analyze)
cli.add_command(serve)
cli.add_command(plugins)
