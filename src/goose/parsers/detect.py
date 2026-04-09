"""Parser detection and dispatch for Goose forensic framework.

The detection registry maps file extensions to concrete parser instances.
Only parsers with ``implemented = True`` are returned from ``detect_parser()``.

Parsers registered here but marked ``implemented = False`` will return an
unsupported-format ParseResult rather than silently failing.

Parser Extension Seam
---------------------
Pro parser packages can add new parsers at runtime by calling
``register_parser()`` with an instantiated parser object.  Registered parsers
are appended to ``_ALL_PARSERS`` after the Core parsers so Core detection order
is never disrupted.

Pro packages should call ``register_parser()`` at import time, typically in
their ``__init__.py``::

    from goose.parsers.detect import register_parser
    from my_pro_package.parsers import MyProParser
    register_parser(MyProParser())

After registration, ``detect_parser()`` and ``parse_file()`` will consider the
Pro parser for any file it claims.  Core parsers always take priority because
they appear earlier in the list.

Sprint 3 — Parser Framework
"""

from __future__ import annotations

from pathlib import Path

from goose.parsers.base import BaseParser
from goose.parsers.csv_parser import CSVParser
from goose.parsers.dataflash import DataFlashParser
from goose.parsers.diagnostics import ParseDiagnostics, ParseResult
from goose.parsers.tlog import TLogParser
from goose.parsers.ulog import ULogParser

# All known parsers — order matters for detection (more specific first).
# This list is mutable so Pro extension packages can append via register_parser().
# Core parsers must always appear before extension parsers.
_ALL_PARSERS: list[BaseParser] = [
    ULogParser(),
    DataFlashParser(),
    TLogParser(),
    CSVParser(),
]

# Implemented parsers only (used for capability display in GUI).
# Rebuilt whenever _ALL_PARSERS is extended via register_parser().
_IMPLEMENTED_PARSERS: list[BaseParser] = [p for p in _ALL_PARSERS if p.implemented]


def register_parser(parser_instance: BaseParser) -> None:
    """Register an additional parser from a Pro or extension package.

    Pro packages should call this at import time or via a plugin registration
    hook.  Registered parsers are appended to the detection order after Core
    parsers so Core detection priority is never disrupted.

    The ``_IMPLEMENTED_PARSERS`` cache is updated immediately so the new parser
    is picked up by ``detect_parser()`` and ``parse_file()`` on the next call.

    Args:
        parser_instance: An instantiated ``BaseParser`` subclass.  Must have
            ``can_parse()``, ``parse()``, ``file_extensions``, ``format_name``,
            and ``implemented`` attributes.

    Raises:
        TypeError: If ``parser_instance`` is not a ``BaseParser`` instance.
    """
    if not isinstance(parser_instance, BaseParser):
        raise TypeError(
            f"register_parser() requires a BaseParser instance, got {type(parser_instance).__name__}"
        )
    _ALL_PARSERS.append(parser_instance)
    # Rebuild the implemented cache in-place
    _IMPLEMENTED_PARSERS.clear()
    _IMPLEMENTED_PARSERS.extend(p for p in _ALL_PARSERS if p.implemented)


def detect_parser(filepath: str | Path) -> BaseParser | None:
    """Return the first *implemented* parser that claims the given file.

    Returns None if no implemented parser matches. Does not try stubs.
    """
    path = Path(filepath)
    for parser in _IMPLEMENTED_PARSERS:
        if parser.can_parse(path):
            return parser
    return None


def detect_format(filepath: str | Path) -> str:
    """Return the detected format name or 'unknown'.

    Checks all parsers (including stubs) for format identification,
    but does not imply support.
    """
    path = Path(filepath)
    for parser in _ALL_PARSERS:
        if Path(path).suffix.lower() in parser.file_extensions:
            return parser.format_name
    return "unknown"


def parse_file(filepath: str | Path) -> ParseResult:
    """Detect the format and parse the file.

    Always returns a ParseResult — never raises.
    If no implemented parser claims the file, returns an unsupported-format result.
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    # Try implemented parsers first
    parser = detect_parser(path)
    if parser is not None:
        return parser.parse(path)

    # Check if any stub claims the extension (format known but not supported)
    for p in _ALL_PARSERS:
        if ext in p.file_extensions:
            diag = ParseDiagnostics.unsupported(ext, parser_name=type(p).__name__)
            return ParseResult.failure(diag)

    # Completely unknown format
    diag = ParseDiagnostics.unsupported(ext)
    diag.errors = [
        f"Unknown file format '{ext}'. "
        "Supported formats: .ulg (PX4 ULog). "
        "Not yet implemented: .bin/.log (DataFlash), .tlog (MAVLink), .csv."
    ]
    return ParseResult.failure(diag)


def supported_formats() -> list[dict[str, object]]:
    """Return a list of all known formats and their implementation status."""
    seen: set[str] = set()
    result = []
    for parser in _ALL_PARSERS:
        if parser.format_name in seen:
            continue
        seen.add(parser.format_name)
        result.append({
            "format_name": parser.format_name,
            "extensions": parser.file_extensions,
            "implemented": parser.implemented,
            "parser_class": type(parser).__name__,
        })
    return result
