"""Core data models for Goose flight analysis."""

from goose.core.crash_detector import CrashAnalysis, analyze_crash
from goose.core.finding import Finding
from goose.core.flight import (
    Flight,
    FlightEvent,
    FlightMetadata,
    FlightPhase,
    ModeChange,
)

__all__ = [
    "CrashAnalysis",
    "Finding",
    "Flight",
    "FlightEvent",
    "FlightMetadata",
    "FlightPhase",
    "ModeChange",
    "analyze_crash",
]
