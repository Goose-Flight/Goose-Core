"""Abstract base class for flight log parsers.

Sprint 3: parse() now returns ParseResult (diagnostics + flight + provenance).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from goose.parsers.diagnostics import ParseResult


class BaseParser(ABC):
    """Base class for all Goose flight log parsers.

    Contract:
    - ``format_name`` and ``file_extensions`` must be class-level attributes.
    - ``can_parse()`` must return True only for formats that are *actually* implemented.
    - ``parse()`` must always return a ParseResult — never raise unhandled exceptions.
      On failure, return ParseResult.failure() with populated diagnostics.
    - Parsers that are stubs / not yet implemented must set ``implemented = False``
      and should not appear in the detection registry as capable of parsing.
    """

    format_name: str  # "ulog", "dataflash", "tlog", "csv"
    file_extensions: list[str]  # [".ulg"], [".bin", ".log"], etc.
    implemented: bool = True  # set False for stub parsers

    @abstractmethod
    def parse(self, filepath: str | Path) -> ParseResult:
        """Parse a flight log file and return a ParseResult.

        Must always return a ParseResult — never raise.
        On failure, return ParseResult.failure(diagnostics=...).
        """
        ...

    def can_parse(self, filepath: str | Path) -> bool:
        """Return True only if this parser is implemented AND the file extension matches."""
        if not self.implemented:
            return False
        return Path(filepath).suffix.lower() in self.file_extensions
