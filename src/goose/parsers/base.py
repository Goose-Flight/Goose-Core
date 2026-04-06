"""Abstract base class for flight log parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from goose.core.flight import Flight


class BaseParser(ABC):
    """Base class for all Goose flight log parsers."""

    format_name: str  # "ulog", "dataflash", "tlog", "csv"
    file_extensions: list[str]  # [".ulg"], [".bin", ".log"], etc.

    @abstractmethod
    def parse(self, filepath: str | Path) -> Flight:
        """Parse a flight log file and return a normalized Flight object."""
        ...

    def can_parse(self, filepath: str | Path) -> bool:
        """Check if this parser can handle the given file based on extension."""
        return Path(filepath).suffix.lower() in self.file_extensions
