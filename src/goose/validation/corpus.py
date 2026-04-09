"""Corpus case definitions and manifest loading for Goose-Core.

Advanced Forensic Validation Sprint — Regression corpus and expectations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExpectedParserBehavior:
    should_succeed: bool = True
    expected_format: str = "ulog"
    min_parser_confidence: float = 0.0
    expected_warnings: list[str] = field(default_factory=list)
    expected_missing_streams: list[str] = field(default_factory=list)
    expected_corruption: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_succeed": self.should_succeed,
            "expected_format": self.expected_format,
            "min_parser_confidence": self.min_parser_confidence,
            "expected_warnings": self.expected_warnings,
            "expected_missing_streams": self.expected_missing_streams,
            "expected_corruption": self.expected_corruption,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExpectedParserBehavior:
        known = {
            "should_succeed", "expected_format", "min_parser_confidence",
            "expected_warnings", "expected_missing_streams", "expected_corruption",
        }
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class ExpectedAnalyzerBehavior:
    plugin_id: str
    should_run: bool = True
    should_find: list[str] = field(default_factory=list)
    should_not_find: list[str] = field(default_factory=list)
    min_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "should_run": self.should_run,
            "should_find": self.should_find,
            "should_not_find": self.should_not_find,
            "min_confidence": self.min_confidence,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExpectedAnalyzerBehavior:
        known = {"plugin_id", "should_run", "should_find", "should_not_find", "min_confidence"}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class CorpusCase:
    corpus_id: str
    description: str
    category: str  # "normal", "crash", "battery_sag", "gps_degradation", "partial", "vibration", "rc_loss"
    evidence_filename: str
    expected_parser: ExpectedParserBehavior
    expected_analyzers: list[ExpectedAnalyzerBehavior] = field(default_factory=list)
    notes: str = ""
    active: bool = True
    profile: str = "default"  # analysis profile id (default/racer/etc.)

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_id": self.corpus_id,
            "description": self.description,
            "category": self.category,
            "evidence_filename": self.evidence_filename,
            "expected_parser": self.expected_parser.to_dict(),
            "expected_analyzers": [a.to_dict() for a in self.expected_analyzers],
            "notes": self.notes,
            "active": self.active,
            "profile": self.profile,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CorpusCase:
        d = dict(d)
        d["expected_parser"] = ExpectedParserBehavior.from_dict(d.get("expected_parser", {}))
        d["expected_analyzers"] = [
            ExpectedAnalyzerBehavior.from_dict(a) for a in d.get("expected_analyzers", [])
        ]
        known = {
            "corpus_id", "description", "category", "evidence_filename",
            "expected_parser", "expected_analyzers", "notes", "active", "profile",
        }
        return cls(**{k: v for k, v in d.items() if k in known})


def load_corpus_manifest(corpus_dir: Path) -> list[CorpusCase]:
    """Load all corpus cases from the manifest file."""
    manifest_path = corpus_dir / "corpus_manifest.json"
    if not manifest_path.exists():
        return []

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases_data = data.get("cases", [])
    return [CorpusCase.from_dict(c) for c in cases_data]
