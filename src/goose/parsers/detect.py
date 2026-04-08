"""Parser detection and dispatch for Goose forensic framework.

The detection registry maps file extensions to concrete parser instances.
Only parsers with ``implemented = True`` are returned from ``detect_parser()``.

Parsers registered here but marked ``implemented = False`` will return an
unsupported-format ParseResult rather than silently failing.

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

# All known parsers — order matters for detection (more specific first)
_ALL_PARSERS: list[BaseParser] = [
    ULogParser(),
    DataFlashParser(),
    TLogParser(),
    CSVParser(),
]

# Implemented parsers only (used for capability display in GUI)
_IMPLEMENTED_PARSERS: list[BaseParser] = [p for p in _ALL_PARSERS if p.implemented]


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
