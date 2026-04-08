"""Tests for Sprint 5 plugin contract, manifests, and forensic analyze method."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from goose.core.flight import Flight, FlightMetadata
from goose.forensics.canonical import ForensicFinding
from goose.parsers.diagnostics import ParseDiagnostics
from goose.plugins.contract import (
    PluginCategory,
    PluginDiagnostics,
    PluginManifest,
    PluginTrustState,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _empty_df() -> pd.DataFrame:
    return pd.DataFrame()


def _make_metadata(**overrides) -> FlightMetadata:
    defaults = dict(
        source_file="test.ulg",
        autopilot="px4",
        firmware_version="1.14.0",
        vehicle_type="quadcopter",
        frame_type=None,
        hardware=None,
        duration_sec=120.0,
        start_time_utc=datetime(2025, 1, 1),
        log_format="ulog",
        motor_count=4,
    )
    defaults.update(overrides)
    return FlightMetadata(**defaults)


def _make_minimal_flight(**stream_overrides) -> Flight:
    """Build a minimal Flight with empty streams, optionally overriding some."""
    meta = _make_metadata()
    flight = Flight(metadata=meta)
    for attr, df in stream_overrides.items():
        setattr(flight, attr, df)
    return flight


def _make_parse_diagnostics() -> ParseDiagnostics:
    return ParseDiagnostics(
        parser_selected="ulog",
        detected_format="ulog",
        supported=True,
        parser_confidence=0.95,
    )


# ---------------------------------------------------------------------------
# PluginManifest serialization
# ---------------------------------------------------------------------------

class TestPluginManifest:
    def test_to_dict_roundtrip(self):
        m = PluginManifest(
            plugin_id="test_plugin",
            name="Test Plugin",
            version="1.2.3",
            author="Test Author",
            description="A test plugin",
            category=PluginCategory.CRASH,
            supported_vehicle_types=["multirotor"],
            required_streams=["position", "attitude"],
            optional_streams=["vibration"],
            output_finding_types=["crash_detected"],
            minimum_contract_version="2.0",
            plugin_type="builtin",
            trust_state=PluginTrustState.BUILTIN_TRUSTED,
        )
        d = m.to_dict()
        assert d["plugin_id"] == "test_plugin"
        assert d["category"] == "crash"
        assert d["trust_state"] == "builtin_trusted"
        assert d["required_streams"] == ["position", "attitude"]

        # Round-trip
        m2 = PluginManifest.from_dict(d)
        assert m2.plugin_id == m.plugin_id
        assert m2.category == m.category
        assert m2.trust_state == m.trust_state
        assert m2.required_streams == m.required_streams
        assert m2.version == m.version

    def test_from_dict_ignores_unknown_keys(self):
        d = {
            "plugin_id": "x",
            "name": "X",
            "version": "0.1",
            "author": "A",
            "description": "D",
            "category": "health",
            "supported_vehicle_types": [],
            "required_streams": [],
            "optional_streams": [],
            "output_finding_types": [],
            "unknown_future_field": 42,
        }
        m = PluginManifest.from_dict(d)
        assert m.plugin_id == "x"


# ---------------------------------------------------------------------------
# PluginDiagnostics serialization
# ---------------------------------------------------------------------------

class TestPluginDiagnostics:
    def test_to_dict(self):
        pd_obj = PluginDiagnostics(
            plugin_id="crash_detection",
            plugin_version="1.0.0",
            run_id="RUN-00000001",
            executed=True,
            skipped=False,
            findings_emitted=3,
            execution_duration_ms=42.5,
        )
        d = pd_obj.to_dict()
        assert d["plugin_id"] == "crash_detection"
        assert d["executed"] is True
        assert d["skipped"] is False
        assert d["findings_emitted"] == 3
        assert d["execution_duration_ms"] == 42.5

    def test_skipped_diagnostics(self):
        pd_obj = PluginDiagnostics(
            plugin_id="vibration",
            plugin_version="1.0.0",
            run_id="RUN-00000002",
            executed=False,
            skipped=True,
            skip_reason="Missing required streams: vibration",
            missing_streams=["vibration"],
        )
        d = pd_obj.to_dict()
        assert d["skipped"] is True
        assert d["executed"] is False
        assert "vibration" in d["skip_reason"]


# ---------------------------------------------------------------------------
# All 11 plugins have valid manifests
# ---------------------------------------------------------------------------

class TestAllPluginManifests:
    def test_all_plugins_have_manifests(self):
        from goose.plugins import PLUGIN_REGISTRY

        assert len(PLUGIN_REGISTRY) == 11, (
            f"Expected 11 plugins, got {len(PLUGIN_REGISTRY)}: "
            f"{list(PLUGIN_REGISTRY.keys())}"
        )

        for plugin_id, plugin in PLUGIN_REGISTRY.items():
            m = plugin.manifest
            assert m.plugin_id, f"Plugin {plugin_id} has empty plugin_id"
            assert m.name, f"Plugin {plugin_id} has empty name"
            assert m.version, f"Plugin {plugin_id} has empty version"
            assert isinstance(m.category, PluginCategory), (
                f"Plugin {plugin_id} has invalid category type"
            )
            assert isinstance(m.trust_state, PluginTrustState), (
                f"Plugin {plugin_id} has invalid trust_state type"
            )

    def test_plugin_ids_match(self):
        from goose.plugins import PLUGIN_REGISTRY

        for plugin_id, plugin in PLUGIN_REGISTRY.items():
            assert plugin.manifest.plugin_id == plugin_id, (
                f"Registry key '{plugin_id}' != manifest plugin_id '{plugin.manifest.plugin_id}'"
            )

    def test_manifest_serialization_roundtrip(self):
        from goose.plugins import PLUGIN_REGISTRY

        for plugin_id, plugin in PLUGIN_REGISTRY.items():
            d = plugin.manifest.to_dict()
            m2 = PluginManifest.from_dict(d)
            assert m2.plugin_id == plugin.manifest.plugin_id
            assert m2.version == plugin.manifest.version


# ---------------------------------------------------------------------------
# forensic_analyze returns correct types
# ---------------------------------------------------------------------------

class TestForensicAnalyze:
    def test_analyze_returns_correct_types_with_data(self):
        """Test that forensic_analyze returns (list[ForensicFinding], PluginDiagnostics)."""
        from goose.plugins import PLUGIN_REGISTRY

        # Build a minimal flight with position data so crash_detection can run
        pos = pd.DataFrame({
            "timestamp": [float(i) for i in range(100)],
            "lat": [47.0 + i * 0.0001 for i in range(100)],
            "lon": [8.0 + i * 0.0001 for i in range(100)],
            "alt_rel": [10.0] * 100,
            "alt_msl": [500.0] * 100,
        })
        flight = _make_minimal_flight(position=pos)
        parse_diag = _make_parse_diagnostics()

        # Test with log_health (no required streams — always runs)
        plugin = PLUGIN_REGISTRY["log_health"]
        findings, diag = plugin.forensic_analyze(
            flight, "EV-TEST-001", "RUN-TEST-001", {}, parse_diag,
        )

        assert isinstance(findings, list)
        assert isinstance(diag, PluginDiagnostics)
        assert diag.plugin_id == "log_health"
        assert diag.executed is True
        assert diag.skipped is False

        for f in findings:
            assert isinstance(f, ForensicFinding), (
                f"Expected ForensicFinding, got {type(f)}"
            )
            assert f.confidence_scope == "finding_analysis"
            assert f.run_id == "RUN-TEST-001"
            assert len(f.evidence_references) > 0
            assert f.evidence_references[0].evidence_id == "EV-TEST-001"

    def test_missing_required_streams_returns_skipped(self):
        """Test that a plugin with missing required_streams returns skipped=True."""
        from goose.plugins import PLUGIN_REGISTRY

        # Vibration plugin requires 'vibration' stream
        plugin = PLUGIN_REGISTRY["vibration"]
        flight = _make_minimal_flight()  # empty vibration
        parse_diag = _make_parse_diagnostics()

        findings, diag = plugin.forensic_analyze(
            flight, "EV-TEST-002", "RUN-TEST-002", {}, parse_diag,
        )

        assert findings == []
        assert diag.skipped is True
        assert diag.executed is False
        assert "vibration" in diag.skip_reason
        assert "vibration" in diag.missing_streams

    def test_battery_skipped_when_no_data(self):
        """Battery plugin requires 'battery' stream."""
        from goose.plugins import PLUGIN_REGISTRY

        plugin = PLUGIN_REGISTRY["battery_sag"]
        flight = _make_minimal_flight()
        parse_diag = _make_parse_diagnostics()

        findings, diag = plugin.forensic_analyze(
            flight, "EV-TEST-003", "RUN-TEST-003", {}, parse_diag,
        )

        assert diag.skipped is True
        assert "battery" in diag.missing_streams

    def test_failsafe_runs_with_no_required_streams(self):
        """Failsafe plugin has no required streams — always executes."""
        from goose.plugins import PLUGIN_REGISTRY

        plugin = PLUGIN_REGISTRY["failsafe_events"]
        flight = _make_minimal_flight()
        parse_diag = _make_parse_diagnostics()

        findings, diag = plugin.forensic_analyze(
            flight, "EV-TEST-004", "RUN-TEST-004", {}, parse_diag,
        )

        assert diag.executed is True
        assert diag.skipped is False
        assert isinstance(findings, list)
        assert diag.findings_emitted == len(findings)

    def test_all_plugins_forensic_analyze_returns_tuple(self):
        """Every plugin's forensic_analyze returns a 2-tuple with correct types."""
        from goose.plugins import PLUGIN_REGISTRY

        # Build a flight with enough data for every plugin to at least attempt
        flight = _make_minimal_flight()
        parse_diag = _make_parse_diagnostics()

        for plugin_id, plugin in PLUGIN_REGISTRY.items():
            result = plugin.forensic_analyze(
                flight, "EV-ALL", "RUN-ALL", {}, parse_diag,
            )
            assert isinstance(result, tuple), f"{plugin_id} did not return tuple"
            assert len(result) == 2, f"{plugin_id} returned {len(result)}-tuple"
            findings, diag = result
            assert isinstance(findings, list), f"{plugin_id} findings is not a list"
            assert isinstance(diag, PluginDiagnostics), (
                f"{plugin_id} diag is not PluginDiagnostics"
            )


# ---------------------------------------------------------------------------
# Registry access functions
# ---------------------------------------------------------------------------

class TestRegistryFunctions:
    def test_get_plugin_manifests(self):
        from goose.plugins import get_plugin_manifests
        manifests = get_plugin_manifests()
        assert len(manifests) == 11
        assert all(isinstance(m, PluginManifest) for m in manifests)

    def test_get_plugin(self):
        from goose.plugins import get_plugin
        p = get_plugin("crash_detection")
        assert p is not None
        assert p.manifest.plugin_id == "crash_detection"

    def test_get_plugin_missing(self):
        from goose.plugins import get_plugin
        p = get_plugin("nonexistent_plugin")
        assert p is None
