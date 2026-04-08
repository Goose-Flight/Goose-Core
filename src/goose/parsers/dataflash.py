"""ArduPilot DataFlash (.bin/.log) parser — NOT YET IMPLEMENTED.

This stub exists so the format can be referenced in detection and documentation
without implying that parsing is available. All parsing attempts will fail
honestly with a clear unsupported-format diagnostic.

To implement: remove ``implemented = False`` and write a real parser.
"""

from __future__ import annotations

from pathlib import Path

from goose.parsers.base import BaseParser
from goose.parsers.diagnostics import ParseDiagnostics, ParseResult


class DataFlashParser(BaseParser):
    """Stub for ArduPilot DataFlash format — not implemented."""

    format_name = "dataflash"
    file_extensions = [".bin", ".log"]
    implemented = False  # disabled until real implementation exists

    def parse(self, filepath: str | Path) -> ParseResult:
        ext = Path(filepath).suffix
        diag = ParseDiagnostics.unsupported(ext, parser_name="DataFlashParser")
        diag.errors = [
            "DataFlash (.bin/.log) format is not yet implemented. "
            "Only PX4 ULog (.ulg) files are currently supported."
        ]
        return ParseResult.failure(diag)
