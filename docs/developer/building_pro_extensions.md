# Building Goose Pro Extensions

**Audience:** Developers building `goose-pro` or third-party Goose extension packages.  
**Last updated:** 2026-04-09

---

## Overview

Goose-Core exposes three extension seams that Pro (or third-party) packages can
plug into without modifying Core source files:

| Seam | What it enables |
|------|----------------|
| `goose.plugins` entry_point | Register additional analysis plugins |
| `goose.parsers` entry_point | Register additional flight log parsers |
| `goose.reports` entry_point | Register additional report generators |

All three seams use Python packaging `entry_points` (PEP 517/660). No monkey-patching,
no import hacks. Core discovers registered extensions at runtime using
`importlib.metadata`.

---

## Creating a Pro Plugin

### 1. Implement the plugin class

Pro plugins follow the same contract as Core plugins. Subclass `goose.plugins.base.Plugin`
and declare a `PluginManifest`.

```python
# goose_pro/plugins/phase2_payload.py
from __future__ import annotations

from typing import Any

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import (
    PluginCategory,
    PluginManifest,
    PluginTrustState,
)


class Phase2PayloadPlugin(Plugin):
    """Phase 2 payload event classifier — Pro tier."""

    name = "phase2_payload"
    description = "Multi-signal payload event classification (Pro)."
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="phase2_payload",
        name="Phase 2 Payload Classifier",
        version="1.0.0",
        author="Goose Pro",
        description="Multi-signal payload event classification using current, motors, and IMU.",
        category=PluginCategory.MISSION_RULES,
        supported_vehicle_types=["multirotor", "all"],
        required_streams=["battery", "motors"],
        optional_streams=["vibration", "attitude"],
        output_finding_types=["payload_release_confirmed", "payload_load_confirmed"],
        minimum_contract_version="2.0",
        plugin_type="builtin",  # use "extension" for third-party packages
        trust_state=PluginTrustState.BUILTIN_TRUSTED,
        primary_stream="battery",
    )

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        findings: list[Finding] = []
        # ... your analysis logic here ...
        return findings


# Module-level instance — required by the plugin registry loader
plugin = Phase2PayloadPlugin()
```

Key rules:
- `manifest.plugin_id` must be globally unique. Use a namespaced prefix (e.g. `"pro_phase2_payload"`).
- `analyze()` must never raise. Catch all exceptions and return `[]` on failure.
- `required_streams` lists Flight attributes that must be non-empty DataFrames. The base
  class `forensic_analyze()` enforces this and emits a skip diagnostic if streams are missing.
- Set `trust_state = PluginTrustState.BUILTIN_TRUSTED` only for plugins you control.
  Third-party plugins should use `PluginTrustState.UNVERIFIED` and supply a `sha256_hash`.

### 2. Declare the entry_point in `pyproject.toml`

```toml
[project.entry-points."goose.plugins"]
phase2_payload = "goose_pro.plugins.phase2_payload:Phase2PayloadPlugin"
```

The key (left of `=`) becomes the plugin's lookup key in the registry.
The value (right of `=`) is the importable path to the **class** (not instance).

Core's `PLUGIN_REGISTRY` and `get_plugin_manifests()` automatically include
registered extensions when the package is installed.

### 3. Test your plugin

```python
# goose_pro/tests/test_phase2_payload.py
import pandas as pd
import pytest

from goose.core.flight import Flight, FlightMetadata
from goose_pro.plugins.phase2_payload import Phase2PayloadPlugin


def _make_flight(**kwargs):
    meta = FlightMetadata(
        source_file="test.ulg",
        autopilot="px4",
        firmware_version="1.14.0",
        vehicle_type="quadcopter",
        frame_type=None,
        hardware=None,
        duration_sec=60.0,
        start_time_utc=None,
        log_format="ulog",
        motor_count=4,
    )
    f = Flight(metadata=meta, **kwargs)
    return f


def test_phase2_payload_no_battery_returns_empty():
    flight = _make_flight()
    plugin = Phase2PayloadPlugin()
    findings = plugin.analyze(flight, {})
    assert findings == []


def test_phase2_payload_detects_drop():
    # Build a battery stream where current drops sharply at t=30s
    times = list(range(60))
    current = [10.0] * 30 + [5.0] * 30   # 5A drop at t=30
    battery = pd.DataFrame({"timestamp": times, "current": current, "voltage": [22.0] * 60})

    flight = _make_flight(battery=battery)
    plugin = Phase2PayloadPlugin()
    findings = plugin.analyze(flight, {})
    assert len(findings) >= 1
    assert any("payload" in f.title.lower() for f in findings)
```

---

## Creating a Pro Parser

### 1. Implement the parser class

Subclass `goose.parsers.base.BaseParser`. The contract requires:
- `format_name` and `file_extensions` class attributes.
- `implemented = True` (otherwise `can_parse()` returns False).
- `parse()` always returns a `ParseResult` — never raises.

```python
# goose_pro/parsers/tlog.py
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from goose.core.flight import Flight, FlightMetadata
from goose.forensics.models import Provenance
from goose.parsers.base import BaseParser
from goose.parsers.diagnostics import ParseDiagnostics, ParseResult, StreamCoverage

MAVLINK_STX_V1 = 0xFE   # MAVLink v1 start byte
MAVLINK_STX_V2 = 0xFD   # MAVLink v2 start byte

# MAVLink message IDs we care about
MSG_HEARTBEAT       = 0
MSG_SYS_STATUS      = 1
MSG_GPS_RAW_INT     = 24
MSG_ATTITUDE        = 30
MSG_GLOBAL_POS_INT  = 33
MSG_BATTERY_STATUS  = 147


class TLogParser(BaseParser):
    """MAVLink TLog (.tlog) parser — minimal honest implementation."""

    format_name = "tlog"
    file_extensions = [".tlog"]
    implemented = True  # Pro ships real implementation

    PARSER_VERSION = "1.0.0"

    def parse(self, filepath: str | Path) -> ParseResult:
        filepath = Path(filepath)
        t0 = time.monotonic()

        diag = ParseDiagnostics(
            parser_selected="tlog",
            parser_version=self.PARSER_VERSION,
            detected_format="tlog",
            format_confidence=0.0,
            supported=True,
            parse_started_at=datetime.now().replace(microsecond=0),
            confidence_scope="parser_parse_quality",
        )

        if not filepath.exists():
            diag.errors.append(f"File not found: {filepath}")
            return ParseResult.failure(diag)

        try:
            data = filepath.read_bytes()
        except OSError as exc:
            diag.errors.append(f"Cannot read file: {exc}")
            return ParseResult.failure(diag)

        if len(data) < 6:
            diag.errors.append("File too small to be a valid TLog.")
            return ParseResult.failure(diag)

        # Format probe: look for MAVLink start bytes in first 512 bytes
        probe = data[:512]
        has_mavlink = MAVLINK_STX_V1 in probe or MAVLINK_STX_V2 in probe
        if not has_mavlink:
            diag.errors.append(
                "No MAVLink start bytes (0xFE or 0xFD) found in first 512 bytes. "
                "File does not appear to be a MAVLink TLog."
            )
            diag.format_confidence = 0.0
            return ParseResult.failure(diag)

        diag.format_confidence = 0.85

        # ... full parsing implementation ...
        # This is a minimal skeleton; the real Pro implementation
        # unpacks each MAVLink frame and extracts the streams below.

        # Build minimal Flight for demonstration
        meta = FlightMetadata(
            source_file=str(filepath),
            autopilot="ardupilot",
            firmware_version="unknown",
            vehicle_type="quadcopter",
            frame_type=None,
            hardware=None,
            duration_sec=0.0,
            start_time_utc=None,
            log_format="tlog",
            motor_count=4,
        )
        flight = Flight(metadata=meta)

        diag.parser_confidence = 0.5
        diag.parse_completed_at = datetime.now().replace(microsecond=0)
        diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
        diag.warnings.append(
            "TLog parser: minimal implementation. "
            "HEARTBEAT/ATTITUDE/GPS streams extracted where present."
        )

        provenance = Provenance(
            source_evidence_id="",
            parser_name="tlog",
            parser_version=self.PARSER_VERSION,
            detected_format="mavlink_tlog",
            parsed_at=diag.parse_started_at,
            transformation_chain=["raw_tlog -> canonical_flight"],
        )

        return ParseResult(
            flight=flight,
            diagnostics=diag,
            provenance=provenance,
        )


# Module-level instance — required by the parser registry loader
parser = TLogParser()
```

### 2. Declare the entry_point

```toml
[project.entry-points."goose.parsers"]
tlog = "goose_pro.parsers.tlog:TLogParser"
```

Core's `detect.py` `parse_file()` iterates all registered parsers and calls
`can_parse()` on each one. The first parser that returns `True` wins.
Order is non-deterministic across packages; ensure `file_extensions` are unique.

### 3. Test your parser

Use the same fixture conventions as `tests/test_parsers/test_dataflash.py`:

```python
# goose_pro/tests/test_tlog_parser.py
import pytest
from pathlib import Path

from goose_pro.parsers.tlog import TLogParser


MINIMAL_TLOG = bytes([0xFE, 9, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])  # stub frame


def test_tlog_rejects_non_tlog(tmp_path):
    f = tmp_path / "not_a_tlog.tlog"
    f.write_bytes(b"This is not a MAVLink file at all ...")
    parser = TLogParser()
    result = parser.parse(f)
    assert not result.success
    assert any("MAVLink" in e for e in result.diagnostics.errors)


def test_tlog_format_probe_accepts_mavlink_start_byte(tmp_path):
    f = tmp_path / "minimal.tlog"
    f.write_bytes(MINIMAL_TLOG)
    parser = TLogParser()
    result = parser.parse(f)
    # Should not error on format detection
    assert result.diagnostics.format_confidence > 0.0


def test_tlog_can_parse_extension():
    parser = TLogParser()
    assert parser.can_parse(Path("flight.tlog"))
    assert not parser.can_parse(Path("flight.ulg"))
```

---

## Creating a Pro Report Generator

### 1. Implement the report generator

Report generators consume `ForensicCaseReport` (from `goose.forensics.reports`)
and produce output in a target format.

```python
# goose_pro/reports/html_report.py
from __future__ import annotations

from pathlib import Path

from goose.forensics.reports import ForensicCaseReport


class HTMLReportGenerator:
    """Generate a self-contained HTML report from a ForensicCaseReport."""

    format_name = "html"
    file_extension = ".html"
    version = "1.0.0"

    def generate(self, report: ForensicCaseReport, output_path: Path) -> Path:
        """Write the HTML report and return the output path."""
        html = self._render(report)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def _render(self, report: ForensicCaseReport) -> str:
        # Jinja2 template rendering in real implementation
        parts = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>",
            f"<title>Goose Forensic Report — {report.case_id}</title>",
            "</head><body>",
            f"<h1>Case {report.case_id}</h1>",
            f"<p>Generated: {report.generated_at}</p>",
            # ... full template rendering ...
            "</body></html>",
        ]
        return "\n".join(parts)


generator = HTMLReportGenerator()
```

### 2. Declare the entry_point

```toml
[project.entry-points."goose.reports"]
html = "goose_pro.reports.html_report:HTMLReportGenerator"
```

---

## Example `pyproject.toml` for a Pro Package

This is the complete skeleton for `goose-pro`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "goose-pro"
version = "1.0.0"
description = "Pro extensions for the Goose drone flight analysis engine"
license = "Proprietary"
requires-python = ">=3.10"
readme = "README.md"
dependencies = [
    "goose-flight>=1.3.0",   # minimum Core version with stable seams
    "pymavlink>=2.4.40",     # for TLog parsing
    "jinja2>=3.1",           # for HTML reports
    "weasyprint>=60.0",      # for PDF reports (optional)
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]

[project.entry-points."goose.plugins"]
payload_change_detection = "goose_pro.plugins.payload_change_detection:PayloadChangeDetectionPlugin"
mission_phase_anomaly    = "goose_pro.plugins.mission_phase_anomaly:MissionPhaseAnomalyPlugin"
operator_action_sequence = "goose_pro.plugins.operator_action_sequence:OperatorActionSequencePlugin"
environment_conditions   = "goose_pro.plugins.environment_conditions:EnvironmentConditionsPlugin"
damage_impact_classification = "goose_pro.plugins.damage_impact_classification:DamageImpactClassificationPlugin"
phase2_payload           = "goose_pro.plugins.phase2_payload:Phase2PayloadPlugin"

[project.entry-points."goose.parsers"]
dataflash = "goose_pro.parsers.dataflash:DataFlashParser"
tlog      = "goose_pro.parsers.tlog:TLogParser"

[project.entry-points."goose.reports"]
html = "goose_pro.reports.html_report:HTMLReportGenerator"
pdf  = "goose_pro.reports.pdf_report:PDFReportGenerator"

[tool.hatch.build.targets.wheel]
packages = ["goose_pro"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

---

## Development Workflow

1. Install Core in editable mode: `pip install -e /path/to/goose-core`
2. Install your Pro package in editable mode: `pip install -e .`
3. After install, `goose plugins list` should show both Core and Pro plugins.
4. Run `python -m pytest` from your Pro package root to run Pro tests.
5. Run `python -m pytest /path/to/goose-core/tests` to verify Core tests still pass
   with Pro installed (no regressions).

## Versioning Contract

- `goose-pro` must declare a `minimum_contract_version` in each `PluginManifest`.
  Current contract version is `"2.0"`.
- When Core increments the plugin contract version (a breaking change to
  `PluginManifest` or `forensic_analyze()` signature), Pro must update.
- Core guarantees backward-compatible reading of prior `ParseResult`,
  `ForensicFinding`, and `Hypothesis` artifacts via `from_dict()` unknown-key
  dropping.

## What Pro Must Never Do

- Import from `goose.web.*` internals (API routes are not a stable API).
- Write to Core's case directory layout without going through `CaseService`.
- Modify `PLUGIN_REGISTRY` directly — use entry_points only.
- Ship billing, auth, or hosted-service logic inside the Pro local package.
- Emit findings that reference streams not declared in `required_streams`
  or `optional_streams` — the contract checker will flag this.
