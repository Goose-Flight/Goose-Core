"""Pro/extension plugin discovery via Python entry_points.

TWO PLUGIN SYSTEMS — READ THIS FIRST
-------------------------------------
See ``goose.plugins.__init__`` for a full explanation of the two systems.

This module is the **Pro extension seam**.  It discovers plugins installed by
third-party packages (e.g. goose-pro) via Python entry_points and makes them
available alongside Core built-ins.

How Pro packages register plugins
----------------------------------
A Pro package adds the following to its ``pyproject.toml``::

    [project.entry-points."goose.plugins"]
    my_plugin = "my_package.plugins:MyPlugin"

After ``pip install goose-pro``, ``discover_pro_plugins()`` will return an
instance of ``MyPlugin`` and ``get_all_plugins()`` in ``__init__.py`` will
include it in the merged registry.

Core built-ins are NOT discovered here.  They live in ``PLUGIN_REGISTRY``
in ``goose.plugins.__init__``.  This module only discovers extensions.

Rule: Core must never import Pro.  This module is a one-way door — Core calls
``discover_pro_plugins()`` to learn about Pro plugins, but Pro packages never
reach back into Core internals.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator

from goose.plugins.base import Plugin

if sys.version_info >= (3, 12):
    from importlib.metadata import entry_points
else:
    from importlib.metadata import entry_points

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "goose.plugins"


def discover_pro_plugins() -> list[Plugin]:
    """Discover and instantiate Pro/extension plugins via entry_points.

    Returns only entry_point-registered plugins — NOT Core built-ins.
    Core built-ins are managed in ``PLUGIN_REGISTRY`` in ``goose.plugins.__init__``.

    Plugins that fail to load (import errors, missing deps, bad class) are
    logged at DEBUG level and silently skipped so a broken Pro package cannot
    crash Core analysis.

    Called by ``get_all_plugins()`` in ``goose.plugins.__init__`` to build the
    merged Core+Pro registry.  Do not call this in hot paths — it scans
    installed packages each time.
    """
    plugins: list[Plugin] = []
    eps = entry_points()
    group = (
        eps.get(ENTRY_POINT_GROUP, [])
        if isinstance(eps, dict)
        else eps.select(group=ENTRY_POINT_GROUP)
    )
    for ep in group:
        try:
            plugin_cls = ep.load()
            if isinstance(plugin_cls, type) and issubclass(plugin_cls, Plugin):
                plugins.append(plugin_cls())
            else:
                logger.debug(
                    "Entry point %s did not resolve to a Plugin subclass — skipped.", ep.name
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Failed to load entry-point plugin %s: %s — skipped.", ep.name, exc
            )
    return plugins


def load_plugins() -> list[Plugin]:
    """Return Core built-ins merged with Pro entry-point plugins.

    This is the legacy discovery function used by the old ``/api`` router
    (``goose.web.api``) and the CLI ``goose plugins`` command.  New code should
    prefer ``get_all_plugins()`` from ``goose.plugins.__init__``, which returns
    a dict keyed by plugin_id.

    Returns a list because the legacy callers iterate; order is Core built-ins
    (registry insertion order) followed by Pro plugins (entry_point scan order).
    """
    from goose.plugins import get_all_plugins
    return list(get_all_plugins().values())


def iter_plugins() -> Iterator[Plugin]:
    """Iterate over all plugins (Core + Pro extensions).

    Thin wrapper around ``load_plugins()`` for callers that prefer an iterator.
    """
    yield from load_plugins()
