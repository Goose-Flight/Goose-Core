"""Tests for the ArduPilot DataFlash parser.

Covers text-format parsing, stream extraction, diagnostics, provenance,
edge-case resilience (empty file, malformed bytes).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from goose.parsers.dataflash import DataFlashParser
from goose.parsers.detect import detect_parser

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ardupilot_minimal.log"


# ---------------------------------------------------------------------------
# Helper — parse the fixture once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def parsed():
    parser = DataFlashParser()
    return parser.parse(FIXTURE)


# ---------------------------------------------------------------------------
# 1. Format detection
# ---------------------------------------------------------------------------


def test_dataflash_text_detects_format():
    """detect_parser() must return the DataFlash parser for a .log file."""
    parser = detect_parser(FIXTURE)
    assert parser is not None, "No implemented parser returned for .log file"
    assert isinstance(parser, DataFlashParser)


# ---------------------------------------------------------------------------
# 2. Parse succeeds
# ---------------------------------------------------------------------------


def test_dataflash_text_parse_succeeds(parsed):
    """Parsing the minimal fixture must succeed."""
    assert parsed.success is True, f"Parse failed. errors={parsed.diagnostics.errors}"
    assert parsed.flight is not None


# ---------------------------------------------------------------------------
# 3. Attitude extracted
# ---------------------------------------------------------------------------


def test_dataflash_text_flight_has_attitude(parsed):
    """ATT messages must produce a non-empty attitude DataFrame with roll/pitch/yaw."""
    att = parsed.flight.attitude
    assert att is not None
    assert not att.empty, "Attitude DataFrame is empty"
    assert "roll" in att.columns, f"Expected 'roll' column; got {att.columns.tolist()}"
    assert "pitch" in att.columns
    assert "yaw" in att.columns
    assert len(att) >= 3


# ---------------------------------------------------------------------------
# 4. Battery extracted
# ---------------------------------------------------------------------------


def test_dataflash_text_flight_has_battery(parsed):
    """BAT messages must produce a non-empty battery DataFrame with voltage."""
    bat = parsed.flight.battery
    assert bat is not None
    assert not bat.empty, "Battery DataFrame is empty"
    assert "voltage" in bat.columns, f"Expected 'voltage' column; got {bat.columns.tolist()}"
    assert len(bat) >= 3


# ---------------------------------------------------------------------------
# 5. GPS extracted
# ---------------------------------------------------------------------------


def test_dataflash_text_flight_has_gps(parsed):
    """GPS messages must produce a non-empty gps DataFrame with lat/lon."""
    gps = parsed.flight.gps
    assert gps is not None
    assert not gps.empty, "GPS DataFrame is empty"
    assert "lat" in gps.columns, f"Expected 'lat' column; got {gps.columns.tolist()}"
    assert "lon" in gps.columns
    assert len(gps) >= 3


# ---------------------------------------------------------------------------
# 6. Mode changes extracted
# ---------------------------------------------------------------------------


def test_dataflash_text_mode_changes_extracted(parsed):
    """MODE messages must produce at least 2 ModeChange entries."""
    mc = parsed.flight.mode_changes
    assert mc is not None
    assert len(mc) >= 2, f"Expected >= 2 mode changes, got {len(mc)}: {mc}"
    # Verify structure
    from goose.core.flight import ModeChange

    for m in mc:
        assert isinstance(m, ModeChange)
        assert isinstance(m.timestamp, float)
        assert m.to_mode  # non-empty mode name


# ---------------------------------------------------------------------------
# 7. Diagnostics structure
# ---------------------------------------------------------------------------


def test_dataflash_diagnostics_structure(parsed):
    """ParseDiagnostics must have a confidence >= 0.5 and non-empty stream_coverage."""
    diag = parsed.diagnostics
    assert diag.parser_confidence >= 0.5, f"parser_confidence too low: {diag.parser_confidence}"
    assert diag.stream_coverage, "stream_coverage is empty"
    # All StreamCoverage entries must have a name
    for sc in diag.stream_coverage:
        assert sc.stream_name
    # Confidence scope must always be this exact string (contract requirement)
    assert diag.confidence_scope == "parser_parse_quality"


# ---------------------------------------------------------------------------
# 8. Provenance recorded
# ---------------------------------------------------------------------------


def test_dataflash_provenance_recorded(parsed):
    """Provenance must be populated with correct parser_name."""
    prov = parsed.provenance
    assert prov is not None
    assert prov.parser_name == "dataflash"
    assert prov.parser_version == "1.0.0"
    assert "dataflash" in prov.detected_format


# ---------------------------------------------------------------------------
# 9. Metadata autopilot
# ---------------------------------------------------------------------------


def test_dataflash_metadata_autopilot(parsed):
    """Flight metadata must identify ArduPilot as the autopilot."""
    meta = parsed.flight.metadata
    assert meta.autopilot == "ardupilot"
    assert meta.log_format.startswith("dataflash")


# ---------------------------------------------------------------------------
# 10. Empty file does not crash
# ---------------------------------------------------------------------------


def test_dataflash_empty_file_does_not_crash(tmp_path):
    """Parsing an empty file must return success=False without raising."""
    empty = tmp_path / "empty.log"
    empty.write_bytes(b"")
    parser = DataFlashParser()
    result = parser.parse(empty)
    assert result.success is False
    assert result.diagnostics.errors  # at least one error message


# ---------------------------------------------------------------------------
# 11. Malformed binary file does not crash
# ---------------------------------------------------------------------------


def test_dataflash_malformed_file_does_not_crash(tmp_path):
    """Parsing random bytes must not raise an exception."""
    import os

    bad = tmp_path / "garbage.bin"
    bad.write_bytes(os.urandom(512))
    parser = DataFlashParser()
    try:
        result = parser.parse(bad)
        # Either success or failure is acceptable — just no exception
        assert isinstance(result.success, bool)
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"Parser raised an exception on malformed input: {exc}")
