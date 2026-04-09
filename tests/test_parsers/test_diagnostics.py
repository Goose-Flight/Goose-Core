"""Tests for the Sprint 3 parser contract — ParseDiagnostics and ParseResult.

These tests verify the formal parser contract independently of any specific
log format. They also cover the detect module and stub parser behavior.

Sprint 3 — Parser Framework and Diagnostics
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from goose.parsers.base import BaseParser
from goose.parsers.csv_parser import CSVParser
from goose.parsers.dataflash import DataFlashParser
from goose.parsers.detect import detect_format, detect_parser, parse_file, supported_formats
from goose.parsers.diagnostics import ParseDiagnostics, ParseResult, StreamCoverage
from goose.parsers.tlog import TLogParser
from goose.parsers.ulog import ULogParser


# ---------------------------------------------------------------------------
# ParseDiagnostics model
# ---------------------------------------------------------------------------

class TestParseDiagnosticsModel:
    def test_default_fields(self) -> None:
        d = ParseDiagnostics()
        assert d.parser_selected == ""
        assert d.supported is False
        assert d.format_confidence == 0.0
        assert d.parser_confidence == 0.0
        assert d.missing_streams == []
        assert d.warnings == []
        assert d.errors == []
        assert d.corruption_indicators == []
        assert d.timebase_anomalies == []
        assert d.assumptions == []
        assert isinstance(d.parse_started_at, datetime)
        assert d.parse_completed_at is None

    def test_to_dict_roundtrip(self) -> None:
        d = ParseDiagnostics(
            parser_selected="ULogParser",
            parser_version="1.0.0",
            detected_format="ulog",
            format_confidence=0.95,
            supported=True,
            parser_confidence=0.88,
            warnings=["Battery missing"],
            missing_streams=["battery"],
            assumptions=["Timestamps monotonic"],
        )
        d.parse_completed_at = datetime.now().replace(microsecond=0)
        d_back = ParseDiagnostics.from_dict(d.to_dict())
        assert d_back.parser_selected == "ULogParser"
        assert d_back.format_confidence == 0.95
        assert d_back.supported is True
        assert d_back.parser_confidence == 0.88
        assert d_back.warnings == ["Battery missing"]
        assert d_back.missing_streams == ["battery"]
        assert d_back.assumptions == ["Timestamps monotonic"]
        assert d_back.parse_completed_at is not None

    def test_to_json_is_valid(self) -> None:
        import json
        d = ParseDiagnostics(parser_selected="X", detected_format="ulog")
        parsed = json.loads(d.to_json())
        assert parsed["parser_selected"] == "X"

    def test_unsupported_factory(self) -> None:
        d = ParseDiagnostics.unsupported(".bin", parser_name="DataFlashParser")
        assert d.supported is False
        assert d.parser_confidence == 0.0
        assert d.format_confidence == 1.0
        assert len(d.errors) == 1
        assert ".bin" in d.errors[0] or "not supported" in d.errors[0]

    def test_failed_factory(self) -> None:
        d = ParseDiagnostics.failed(
            parser_name="ULogParser",
            parser_version="1.0",
            detected_format="ulog",
            error="corrupt header",
        )
        assert d.parser_confidence == 0.0
        assert "corrupt header" in d.errors[0]

    def test_stream_coverage_roundtrip(self) -> None:
        sc = StreamCoverage(stream_name="attitude", present=True, row_count=500)
        sc_back = StreamCoverage.from_dict(sc.to_dict())
        assert sc_back.stream_name == "attitude"
        assert sc_back.present is True
        assert sc_back.row_count == 500


# ---------------------------------------------------------------------------
# ParseResult model
# ---------------------------------------------------------------------------

class TestParseResultModel:
    def test_failure_has_no_flight(self) -> None:
        diag = ParseDiagnostics(errors=["bad file"])
        result = ParseResult.failure(diag)
        assert result.flight is None
        assert not result.success

    def test_success_requires_flight_and_no_errors(self) -> None:
        from goose.core.flight import Flight, FlightMetadata
        meta = FlightMetadata(autopilot="px4", log_format="ulog", source_file="x.ulg",
                              duration_sec=10.0, firmware_version="1.0",
                              vehicle_type="quadcopter", motor_count=4,
                              frame_type=None, hardware=None, start_time_utc=None)
        import pandas as pd
        flight = Flight(metadata=meta, position=pd.DataFrame(), position_setpoint=pd.DataFrame(),
                        velocity=pd.DataFrame(), velocity_setpoint=pd.DataFrame(),
                        attitude=pd.DataFrame(), attitude_setpoint=pd.DataFrame(),
                        attitude_rate=pd.DataFrame(), attitude_rate_setpoint=pd.DataFrame(),
                        battery=pd.DataFrame(), gps=pd.DataFrame(), motors=pd.DataFrame(),
                        vibration=pd.DataFrame(), rc_input=pd.DataFrame(),
                        ekf=pd.DataFrame(), cpu=pd.DataFrame(),
                        mode_changes=[], events=[], parameters={}, primary_mode="manual")
        diag = ParseDiagnostics(supported=True)  # no errors
        result = ParseResult(flight=flight, diagnostics=diag)
        assert result.success

    def test_flight_with_errors_is_not_success(self) -> None:
        from goose.core.flight import Flight, FlightMetadata
        import pandas as pd
        meta = FlightMetadata(autopilot="px4", log_format="ulog", source_file="x.ulg",
                              duration_sec=10.0, firmware_version="1.0",
                              vehicle_type="quadcopter", motor_count=4,
                              frame_type=None, hardware=None, start_time_utc=None)
        flight = Flight(metadata=meta, position=pd.DataFrame(), position_setpoint=pd.DataFrame(),
                        velocity=pd.DataFrame(), velocity_setpoint=pd.DataFrame(),
                        attitude=pd.DataFrame(), attitude_setpoint=pd.DataFrame(),
                        attitude_rate=pd.DataFrame(), attitude_rate_setpoint=pd.DataFrame(),
                        battery=pd.DataFrame(), gps=pd.DataFrame(), motors=pd.DataFrame(),
                        vibration=pd.DataFrame(), rc_input=pd.DataFrame(),
                        ekf=pd.DataFrame(), cpu=pd.DataFrame(),
                        mode_changes=[], events=[], parameters={}, primary_mode="manual")
        diag = ParseDiagnostics(errors=["something went wrong"])
        result = ParseResult(flight=flight, diagnostics=diag)
        assert not result.success


# ---------------------------------------------------------------------------
# Stub parsers
# ---------------------------------------------------------------------------

class TestStubParsers:
    """Stubs must not claim can_parse and must return unsupported diagnostics.

    CSVParser is intentionally excluded from the stub parametrize sets because
    it is a fully-implemented parser (implemented = True) as of Sprint 4.
    """

    @pytest.mark.parametrize("parser_cls,ext", [
        (DataFlashParser, ".bin"),
        (TLogParser, ".tlog"),
    ])
    def test_not_implemented(self, parser_cls: type, ext: str) -> None:
        parser = parser_cls()
        assert not parser.implemented

    @pytest.mark.parametrize("parser_cls,ext", [
        (DataFlashParser, ".bin"),
        (TLogParser, ".tlog"),
    ])
    def test_can_parse_returns_false(self, parser_cls: type, ext: str) -> None:
        parser = parser_cls()
        assert not parser.can_parse(f"file{ext}")

    @pytest.mark.parametrize("parser_cls,ext", [
        (DataFlashParser, ".bin"),
        (TLogParser, ".tlog"),
    ])
    def test_parse_returns_failure_not_exception(self, parser_cls: type, ext: str, tmp_path: Path) -> None:
        parser = parser_cls()
        f = tmp_path / f"test{ext}"
        f.write_bytes(b"\x00" * 10)
        result = parser.parse(f)
        assert isinstance(result, ParseResult)
        assert not result.success
        assert result.flight is None
        assert len(result.diagnostics.errors) > 0
        assert not result.diagnostics.supported

    def test_csv_parser_is_implemented(self) -> None:
        """CSVParser graduated from stub to full implementation in Sprint 4."""
        parser = CSVParser()
        assert parser.implemented
        assert parser.can_parse("flight.csv")


# ---------------------------------------------------------------------------
# Detection module
# ---------------------------------------------------------------------------

class TestDetectModule:
    def test_detect_parser_returns_ulog_for_ulg(self, normal_flight_path: Path) -> None:
        parser = detect_parser(normal_flight_path)
        assert parser is not None
        assert isinstance(parser, ULogParser)

    def test_detect_parser_returns_none_for_bin(self, tmp_path: Path) -> None:
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00")
        assert detect_parser(f) is None

    def test_detect_parser_returns_none_for_unknown(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xyz"
        f.write_bytes(b"\x00")
        assert detect_parser(f) is None

    def test_detect_format_ulg(self, tmp_path: Path) -> None:
        f = tmp_path / "test.ulg"
        f.write_bytes(b"\x00")
        assert detect_format(f) == "ulog"

    def test_detect_format_bin(self, tmp_path: Path) -> None:
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00")
        assert detect_format(f) == "dataflash"

    def test_detect_format_unknown(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xyz"
        f.write_bytes(b"\x00")
        assert detect_format(f) == "unknown"

    def test_parse_file_success_for_ulg(self, normal_flight_path: Path) -> None:
        result = parse_file(normal_flight_path)
        assert result.success
        assert result.flight is not None
        assert result.diagnostics.parser_selected == "ULogParser"

    def test_parse_file_unsupported_for_bin(self, tmp_path: Path) -> None:
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00")
        result = parse_file(f)
        assert not result.success
        assert result.flight is None
        assert not result.diagnostics.supported

    def test_parse_file_unsupported_for_unknown_ext(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xyz"
        f.write_bytes(b"\x00")
        result = parse_file(f)
        assert not result.success
        assert len(result.diagnostics.errors) > 0

    def test_supported_formats_includes_all_known(self) -> None:
        formats = supported_formats()
        names = [f["format_name"] for f in formats]
        assert "ulog" in names
        assert "dataflash" in names
        assert "tlog" in names
        assert "csv" in names

    def test_supported_formats_implemented(self) -> None:
        """ULog and CSV are both fully implemented; DataFlash and TLog remain stubs."""
        formats = supported_formats()
        implemented_names = {f["format_name"] for f in formats if f["implemented"]}
        assert "ulog" in implemented_names
        assert "csv" in implemented_names
        assert "dataflash" not in implemented_names
        assert "tlog" not in implemented_names


# ---------------------------------------------------------------------------
# ULogParser diagnostics quality (with real fixture)
# ---------------------------------------------------------------------------

class TestULogDiagnosticsQuality:
    """Verify that ULogParser produces high-quality diagnostics on real logs."""

    def test_parser_confidence_above_threshold(self, normal_flight_path: Path) -> None:
        parser = ULogParser()
        result = parser.parse(normal_flight_path)
        assert result.diagnostics.parser_confidence >= 0.5

    def test_stream_coverage_has_present_and_absent(self, normal_flight_path: Path) -> None:
        parser = ULogParser()
        result = parser.parse(normal_flight_path)
        coverage = result.diagnostics.stream_coverage
        assert any(s.present for s in coverage)
        # Not all streams need to be present, but list should be populated
        assert len(coverage) >= 5

    def test_parse_duration_recorded(self, normal_flight_path: Path) -> None:
        parser = ULogParser()
        result = parser.parse(normal_flight_path)
        assert result.diagnostics.parse_duration_ms is not None
        assert result.diagnostics.parse_duration_ms >= 0

    def test_assumptions_not_empty(self, normal_flight_path: Path) -> None:
        parser = ULogParser()
        result = parser.parse(normal_flight_path)
        assert len(result.diagnostics.assumptions) > 0

    def test_provenance_evidence_id_empty_by_default(self, normal_flight_path: Path) -> None:
        """Parser doesn't know the evidence_id — caller must fill it in."""
        parser = ULogParser()
        result = parser.parse(normal_flight_path)
        assert result.provenance is not None
        assert result.provenance.source_evidence_id == ""


# ---------------------------------------------------------------------------
# Pre-Sprint-4 stabilization — contract versioning and confidence scope
# ---------------------------------------------------------------------------

class TestParserContractVersioning:
    """Verify schema version and contract fields are present and serialized.

    These tests lock the serialized shape of ParseDiagnostics and Provenance
    before Sprint 4 downstream artifacts start depending on it.
    """

    # -- ParseDiagnostics versioning ----------------------------------------

    def test_diagnostics_version_field_exists(self) -> None:
        d = ParseDiagnostics()
        assert hasattr(d, "diagnostics_version")
        assert d.diagnostics_version == "1.0"

    def test_diagnostics_version_in_to_dict(self) -> None:
        d = ParseDiagnostics()
        serialized = d.to_dict()
        assert "diagnostics_version" in serialized
        assert serialized["diagnostics_version"] == "1.0"

    def test_diagnostics_version_in_to_json(self) -> None:
        import json
        d = ParseDiagnostics()
        parsed = json.loads(d.to_json())
        assert parsed["diagnostics_version"] == "1.0"

    def test_diagnostics_version_survives_roundtrip(self) -> None:
        d = ParseDiagnostics(diagnostics_version="1.0", parser_selected="X")
        d_back = ParseDiagnostics.from_dict(d.to_dict())
        assert d_back.diagnostics_version == "1.0"

    def test_diagnostics_from_dict_ignores_unknown_keys(self) -> None:
        """from_dict must not crash on keys from a future schema version."""
        d = ParseDiagnostics()
        raw = d.to_dict()
        raw["future_field_v2"] = "some_value"
        recovered = ParseDiagnostics.from_dict(raw)  # must not raise
        assert recovered.diagnostics_version == "1.0"

    # -- Confidence scope ---------------------------------------------------

    def test_confidence_scope_field_exists(self) -> None:
        d = ParseDiagnostics()
        assert hasattr(d, "confidence_scope")
        assert d.confidence_scope == "parser_parse_quality"

    def test_confidence_scope_in_to_dict(self) -> None:
        d = ParseDiagnostics()
        serialized = d.to_dict()
        assert "confidence_scope" in serialized
        assert serialized["confidence_scope"] == "parser_parse_quality"

    def test_confidence_scope_survives_roundtrip(self) -> None:
        d = ParseDiagnostics()
        d_back = ParseDiagnostics.from_dict(d.to_dict())
        assert d_back.confidence_scope == "parser_parse_quality"

    def test_real_parse_confidence_scope_is_parser_parse_quality(
        self, normal_flight_path: "Path"
    ) -> None:
        """Ensure ULogParser sets the correct scope on real output."""
        parser = ULogParser()
        result = parser.parse(normal_flight_path)
        assert result.diagnostics.confidence_scope == "parser_parse_quality"

    # -- Provenance contract versioning ------------------------------------

    def test_provenance_contract_version_field_exists(self) -> None:
        from goose.forensics.models import Provenance
        p = Provenance()
        assert hasattr(p, "contract_version")
        assert p.contract_version == "1.0"

    def test_provenance_contract_version_in_to_dict(self) -> None:
        from goose.forensics.models import Provenance
        p = Provenance()
        serialized = p.to_dict()
        assert "contract_version" in serialized
        assert serialized["contract_version"] == "1.0"

    def test_provenance_contract_version_survives_roundtrip(self) -> None:
        from goose.forensics.models import Provenance
        p = Provenance(contract_version="1.0", parser_name="ULogParser")
        p_back = Provenance.from_dict(p.to_dict())
        assert p_back.contract_version == "1.0"

    def test_provenance_from_dict_ignores_unknown_keys(self) -> None:
        """from_dict must not crash on keys from a future schema version."""
        from goose.forensics.models import Provenance
        p = Provenance()
        raw = p.to_dict()
        raw["future_field_v2"] = "some_value"
        recovered = Provenance.from_dict(raw)  # must not raise
        assert recovered.contract_version == "1.0"

    def test_real_parse_provenance_has_contract_version(
        self, normal_flight_path: "Path"
    ) -> None:
        parser = ULogParser()
        result = parser.parse(normal_flight_path)
        assert result.provenance is not None
        assert result.provenance.contract_version == "1.0"

    # -- Confidence scoring semantics --------------------------------------

    def test_parser_confidence_is_float_in_range(self, normal_flight_path: "Path") -> None:
        parser = ULogParser()
        result = parser.parse(normal_flight_path)
        c = result.diagnostics.parser_confidence
        assert isinstance(c, float)
        assert 0.0 <= c <= 1.0

    def test_failed_parse_has_zero_confidence(self) -> None:
        parser = ULogParser()
        result = parser.parse("nonexistent.ulg")
        assert result.diagnostics.parser_confidence == 0.0

    def test_unsupported_format_has_zero_confidence(self) -> None:
        from goose.parsers.dataflash import DataFlashParser
        parser = DataFlashParser()
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"\x00" * 10)
            tmp = f.name
        try:
            result = parser.parse(tmp)
            assert result.diagnostics.parser_confidence == 0.0
        finally:
            os.unlink(tmp)
