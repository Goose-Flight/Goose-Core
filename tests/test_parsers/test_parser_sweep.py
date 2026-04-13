"""Phase 2 Bulletproofing Sprint — Parser sweep regression tests.

Validates parse_file() against all available fixtures and edge cases:
- All real fixtures parse successfully with correct structure
- Parser contract fields (success, flight, diagnostics, provenance) are populated
- Parser confidence is in [0, 1]
- Stream coverage is non-empty on success
- Edge cases produce graceful failure (not a crash)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from goose.parsers.detect import (
    detect_format,
    detect_parser,
    parse_file,
    supported_formats,
)
from goose.parsers.diagnostics import ParseResult

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ULG_FIXTURES = [
    FIXTURES_DIR / "px4_vibration_crash.ulg",
    FIXTURES_DIR / "px4_motor_failure.ulg",
    FIXTURES_DIR / "px4_normal_flight.ulg",
]

DATAFLASH_FIXTURES = [
    FIXTURES_DIR / "ardupilot_minimal.log",
]

ALL_FIXTURES = ULG_FIXTURES + DATAFLASH_FIXTURES


# ---------------------------------------------------------------------------
# Contract helpers
# ---------------------------------------------------------------------------

def _assert_success_contract(result: ParseResult, label: str) -> None:
    """Assert full ParseResult contract for a successful parse."""
    assert result.success is True, f"{label}: success should be True, errors={result.diagnostics.errors}"
    assert result.flight is not None, f"{label}: flight should not be None"
    assert result.diagnostics is not None, f"{label}: diagnostics missing"
    assert result.provenance is not None, f"{label}: provenance missing"

    conf = result.diagnostics.parser_confidence
    assert 0.0 <= conf <= 1.0, f"{label}: parser_confidence out of [0,1]: {conf}"

    streams = result.diagnostics.stream_coverage
    assert len(streams) > 0, f"{label}: stream_coverage is empty"

    assert result.diagnostics.errors == [], f"{label}: unexpected errors: {result.diagnostics.errors}"
    assert result.provenance.parser_name, f"{label}: provenance.parser_name is empty"


def _assert_failure_contract(result: ParseResult, label: str) -> None:
    """Assert ParseResult contract for a failure (graceful failure, no crash)."""
    assert result.success is False, f"{label}: success should be False"
    assert result.flight is None, f"{label}: flight should be None on failure"
    assert result.diagnostics is not None, f"{label}: diagnostics missing even on failure"
    assert len(result.diagnostics.errors) > 0, f"{label}: errors list should be non-empty on failure"


# ---------------------------------------------------------------------------
# Happy-path: all fixture files parse successfully
# ---------------------------------------------------------------------------

class TestFixtureParsing:
    @pytest.mark.parametrize("fixture_path", ULG_FIXTURES, ids=lambda p: p.name)
    def test_ulg_fixture_parses_successfully(self, fixture_path: Path):
        assert fixture_path.exists(), f"Fixture not found: {fixture_path}"
        result = parse_file(fixture_path)
        _assert_success_contract(result, fixture_path.name)

    @pytest.mark.parametrize("fixture_path", DATAFLASH_FIXTURES, ids=lambda p: p.name)
    def test_dataflash_fixture_parses_successfully(self, fixture_path: Path):
        assert fixture_path.exists(), f"Fixture not found: {fixture_path}"
        result = parse_file(fixture_path)
        _assert_success_contract(result, fixture_path.name)

    def test_ulg_provenance_parser_name(self):
        result = parse_file(FIXTURES_DIR / "px4_vibration_crash.ulg")
        assert result.provenance.parser_name == "ULogParser"

    def test_dataflash_provenance_parser_name(self):
        result = parse_file(FIXTURES_DIR / "ardupilot_minimal.log")
        assert result.provenance.parser_name == "dataflash"

    def test_vibration_crash_high_confidence(self):
        """Vibration crash fixture has full data — confidence should be high."""
        result = parse_file(FIXTURES_DIR / "px4_vibration_crash.ulg")
        assert result.diagnostics.parser_confidence >= 0.9

    def test_stream_coverage_has_named_streams(self):
        result = parse_file(FIXTURES_DIR / "px4_vibration_crash.ulg")
        stream_names = [s.stream_name for s in result.diagnostics.stream_coverage]
        assert len(stream_names) >= 5
        # At least position and attitude must be present in a full ULG
        assert "position" in stream_names
        assert "attitude" in stream_names

    def test_stream_coverage_row_counts_are_positive(self):
        result = parse_file(FIXTURES_DIR / "px4_vibration_crash.ulg")
        for sc in result.diagnostics.stream_coverage:
            if sc.present:
                assert sc.row_count > 0, f"stream {sc.stream_name!r} marked present but row_count=0"

    def test_flight_metadata_populated(self):
        result = parse_file(FIXTURES_DIR / "px4_vibration_crash.ulg")
        meta = result.flight.metadata
        assert meta.source_file is not None
        assert meta.duration_sec > 0

    def test_normal_flight_has_no_crash_flag(self):
        result = parse_file(FIXTURES_DIR / "px4_normal_flight.ulg")
        assert result.success
        # Normal flight — crashed flag should be False
        assert result.flight.crashed is False

    def test_vibration_crash_fixture_parses_as_flight(self):
        """Vibration crash fixture must parse successfully as a usable Flight."""
        result = parse_file(FIXTURES_DIR / "px4_vibration_crash.ulg")
        assert result.success
        assert result.flight is not None
        # The fixture represents a problematic flight — just confirm it's
        # parseable and the flight object is valid (crashed flag is
        # determined by log data, not fixture name).
        assert result.flight.metadata.duration_sec > 0

    def test_diagnostics_confidence_scope_label(self):
        """confidence_scope must always be 'parser_parse_quality' — not root-cause."""
        for fixture in ALL_FIXTURES:
            result = parse_file(fixture)
            assert result.diagnostics.confidence_scope == "parser_parse_quality", (
                f"{fixture.name}: confidence_scope was {result.diagnostics.confidence_scope!r}"
            )


# ---------------------------------------------------------------------------
# Edge cases — graceful failure
# ---------------------------------------------------------------------------

class TestEdgeCaseGracefulFailure:
    def test_nonexistent_file_returns_failure(self):
        result = parse_file("does_not_exist_at_all.ulg")
        _assert_failure_contract(result, "nonexistent file")

    def test_nonexistent_file_has_descriptive_error(self):
        result = parse_file("does_not_exist.ulg")
        assert any("not found" in e.lower() or "no such" in e.lower() for e in result.diagnostics.errors)

    def test_empty_ulg_file_returns_failure(self, tmp_path: Path):
        empty = tmp_path / "empty.ulg"
        empty.write_bytes(b"")
        result = parse_file(empty)
        _assert_failure_contract(result, "empty .ulg file")

    def test_corrupt_binary_ulg_returns_failure(self, tmp_path: Path):
        corrupt = tmp_path / "corrupt.ulg"
        corrupt.write_bytes(bytes([0xFF, 0x00, 0xAB, 0xCD] * 64))
        result = parse_file(corrupt)
        _assert_failure_contract(result, "corrupt .ulg file")

    def test_txt_file_returns_failure(self, tmp_path: Path):
        txt = tmp_path / "readme.txt"
        txt.write_text("this is not a flight log", encoding="utf-8")
        result = parse_file(txt)
        # .txt is not a supported format
        assert result.success is False
        assert result.diagnostics is not None
        assert len(result.diagnostics.errors) > 0

    def test_unknown_extension_returns_failure(self, tmp_path: Path):
        unk = tmp_path / "flight.xyz"
        unk.write_bytes(b"\x00" * 128)
        result = parse_file(unk)
        _assert_failure_contract(result, "unknown .xyz extension")

    def test_wrong_extension_for_ulg_content_fails(self, tmp_path: Path):
        """A file with .csv extension but ULog content should fail gracefully."""
        # Read real ULG bytes and give it wrong extension
        real_ulg = FIXTURES_DIR / "px4_normal_flight.ulg"
        if not real_ulg.exists():
            pytest.skip("fixture not available")
        wrong_ext = tmp_path / "flight_data.csv"
        wrong_ext.write_bytes(real_ulg.read_bytes())
        result = parse_file(wrong_ext)
        # CSV parser is a stub, so this should be unsupported
        assert result.success is False

    def test_empty_dataflash_file_returns_failure(self, tmp_path: Path):
        empty = tmp_path / "empty.log"
        empty.write_bytes(b"")
        result = parse_file(empty)
        _assert_failure_contract(result, "empty .log file")


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

class TestDetectionHelpers:
    def test_detect_parser_for_ulg(self):
        parser = detect_parser(FIXTURES_DIR / "px4_vibration_crash.ulg")
        assert parser is not None
        assert parser.format_name == "ulog"

    def test_detect_parser_for_log(self):
        parser = detect_parser(FIXTURES_DIR / "ardupilot_minimal.log")
        assert parser is not None
        assert parser.format_name == "dataflash"

    def test_detect_format_ulog(self):
        fmt = detect_format("flight.ulg")
        assert fmt == "ulog"

    def test_detect_format_log(self):
        fmt = detect_format("ardupilot.log")
        assert fmt == "dataflash"

    def test_detect_format_unknown(self):
        fmt = detect_format("mystery.xyz")
        assert fmt == "unknown"

    def test_supported_formats_returns_list(self):
        formats = supported_formats()
        assert isinstance(formats, list)
        assert len(formats) > 0
        names = [f["format_name"] for f in formats]
        assert "ulog" in names

    def test_supported_formats_have_required_keys(self):
        for fmt in supported_formats():
            for key in ("format_name", "extensions", "implemented", "parser_class"):
                assert key in fmt, f"format entry missing key {key!r}"
