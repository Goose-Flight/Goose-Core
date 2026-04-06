"""Plugin discovery and registry via entry points."""

from __future__ import annotations

import sys
from typing import Iterator

from goose.plugins.base import Plugin

if sys.version_info >= (3, 12):
    from importlib.metadata import entry_points
else:
    from importlib.metadata import entry_points

ENTRY_POINT_GROUP = "goose.plugins"


def discover_plugins() -> list[type[Plugin]]:
    """Discover all installed plugins via entry points."""
    plugins: list[type[Plugin]] = []
    eps = entry_points()
    group = eps.get(ENTRY_POINT_GROUP, []) if isinstance(eps, dict) else eps.select(group=ENTRY_POINT_GROUP)
    for ep in group:
        try:
            plugin_cls = ep.load()
            if isinstance(plugin_cls, type) and issubclass(plugin_cls, Plugin):
                plugins.append(plugin_cls)
        except Exception:
            # Skip plugins that fail to load (missing, empty, or broken)
            pass
    return plugins


def load_plugins() -> list[Plugin]:
    """Discover and instantiate all installed plugins."""
    return [cls() for cls in discover_plugins()]


def iter_plugins() -> Iterator[Plugin]:
    """Iterate over instantiated plugins."""
    yield from load_plugins()
