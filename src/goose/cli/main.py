"""Click CLI root group for Goose."""

from __future__ import annotations

import click

from goose import __version__
from goose.cli.crash import crash


@click.group()
@click.version_option(version=__version__, prog_name="goose")
def cli() -> None:
    """Goose — Open source drone flight log crash analysis and validation engine."""


cli.add_command(crash)
