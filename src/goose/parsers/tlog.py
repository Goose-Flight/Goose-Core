"""MAVLink TLog (.tlog) parser — NOT YET IMPLEMENTED.

This stub exists so the format can be referenced in detection and documentation
without implying that parsing is available. All parsing attempts will fail
honestly with a clear unsupported-format diagnostic.

To implement: remove ``implemented = False`` and write a real parser.
"""

from __future__ import annotations

from pathlib import Path

from goose.parsers.base import BaseParser
from goose.parsers.diagnostics import ParseDiagnostics, ParseResult


class TLogParser(BaseParser):
    """Stub for MAVLink TLog format — not implemented."""

    format_name = "tlog"
    file_extensions = [".tlog"]
    implemented = False  # disabled until real implementation exists

    def parse(self, filepath: str | Path) -> ParseResult:
        ext = Path(filepath).suffix
        diag = ParseDiagnostics.unsupported(ext, parser_name="TLogParser")
        diag.errors = ["TLog (.tlog) format is not yet implemented. Only PX4 ULog (.ulg) files are currently supported."]
        return ParseResult.failure(diag)
