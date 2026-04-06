"""Finding dataclass — a single analysis result from a plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Finding:
    """A single finding produced by an analysis plugin."""

    plugin_name: str
    title: str  # "Motor 3 failure detected"
    severity: str  # "critical" | "warning" | "info" | "pass"
    score: int  # 0-100 (100 = perfect, 0 = critical failure)
    description: str  # Human-readable explanation
    evidence: dict[str, Any] = field(default_factory=dict)  # Supporting data
    phase: str | None = None  # Which flight phase this occurred in
    timestamp_start: float | None = None  # When the issue started
    timestamp_end: float | None = None  # When the issue ended
