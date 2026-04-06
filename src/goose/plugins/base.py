"""Plugin abstract base class for Goose analysis plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from goose.core.finding import Finding
from goose.core.flight import Flight

MODE_HIERARCHY: list[str] = ["manual", "stabilized", "altitude", "position", "mission"]


class Plugin(ABC):
    """Base class for all Goose analysis plugins."""

    name: str  # unique identifier e.g. "vibration"
    description: str  # human-readable description
    version: str  # semver e.g. "1.0.0"
    min_mode: str = "manual"  # minimum flight mode required

    @abstractmethod
    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run analysis on a flight. Return list of findings."""
        ...

    def applicable(self, flight: Flight) -> bool:
        """Check if this plugin can run on this flight (mode hierarchy check)."""
        flight_level = (
            MODE_HIERARCHY.index(flight.primary_mode)
            if flight.primary_mode in MODE_HIERARCHY
            else 0
        )
        required_level = (
            MODE_HIERARCHY.index(self.min_mode)
            if self.min_mode in MODE_HIERARCHY
            else 0
        )
        return flight_level >= required_level
