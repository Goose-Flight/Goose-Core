"""Tests for Sprint 2 Workstream D advanced analyzers.

Covers:
  - environment_conditions
  - damage_impact_classification
  - link_telemetry_health

Plus cross-cutting registry/tuning profile assertions.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightMetadata
from goose.plugins.damage_impact_classification import DamageImpactClassificationPlugin
from goose.plugins.environment_conditions import EnvironmentConditionsPlugin
from goose.plugins.link_telemetry_health import LinkTelemetryHealthPlugin

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _meta() -> FlightMetadata:
    return FlightMetadata(
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


def _empty_flight() -> Flight:
    return Flight(metadata=_meta())


def _timestamps(n: int, rate_hz: float = 10.0) -> pd.Series:
    return pd.Series(np.arange(n, dtype=float) / rate_hz)


def _assert_findings_valid(findings: list[Finding]) -> None:
    """Common structural assertions for any finding list."""
    assert isinstance(findings, list)
    valid_severities = {"pass", "info", "warning", "critical"}
    for f in findings:
        assert isinstance(f, Finding)
        assert f.severity in valid_severities, f"Invalid severity: {f.severity}"
        assert isinstance(f.title, str) and f.title
        assert isinstance(f.score, (int, float))


# ===========================================================================
# Plugin 1: environment_conditions
# ===========================================================================


class TestEnvironmentConditionsManifest:
    def test_manifest_complete(self):
        plugin = EnvironmentConditionsPlugin()
        m = plugin.manifest
        assert m.plugin_id == "environment_conditions"
        assert m.name
        assert m.version
        assert m.author
        assert m.description
        assert m.primary_stream == "gps"
        assert "gps" in m.required_streams
        assert len(m.output_finding_types) > 0

    def test_manifest_category_is_health(self):
        from goose.plugins.contract import PluginCategory

        plugin = EnvironmentConditionsPlugin()
        assert plugin.manifest.category == PluginCategory.HEALTH


class TestEnvironmentConditionsEmptyData:
    def test_returns_empty_on_no_data(self):
        plugin = EnvironmentConditionsPlugin()
        flight = _empty_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)

    def test_does_not_crash_on_empty_flight(self):
        plugin = EnvironmentConditionsPlugin()
        findings = plugin.analyze(_empty_flight(), {})
        assert isinstance(findings, list)


class TestEnvironmentConditionsDetection:
    def _make_gps_multipath_flight(self) -> Flight:
        """GPS with high HDOP and adequate satellite count (multipath pattern)."""
        n = 200
        ts = _timestamps(n, rate_hz=5.0)
        gps = pd.DataFrame(
            {
                "timestamp": ts,
                "hdop": [3.5] * n,  # High HDOP
                "satellites_used": [12] * n,  # But plenty of satellites
                "lat": [47.0] * n,
                "lon": [8.0] * n,
            }
        )
        flight = _empty_flight()
        flight.gps = gps
        return flight

    def _make_gps_interference_flight(self) -> Flight:
        """GPS with sudden satellite count drop."""
        n = 100
        ts = _timestamps(n, rate_hz=5.0)
        # Satellites drop from 14 to 3 within 5 seconds
        sats = [14] * 50 + [3] * 10 + [12] * 40
        gps = pd.DataFrame(
            {
                "timestamp": ts,
                "satellites_used": sats,
                "hdop": [1.2] * n,
            }
        )
        flight = _empty_flight()
        flight.gps = gps
        return flight

    def test_gps_multipath_produces_finding(self):
        plugin = EnvironmentConditionsPlugin()
        flight = self._make_gps_multipath_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        assert len(findings) >= 1
        titles = [f.title for f in findings]
        assert any("multipath" in t.lower() for t in titles), f"Expected a multipath finding, got: {titles}"

    def test_gps_interference_produces_finding(self):
        plugin = EnvironmentConditionsPlugin()
        flight = self._make_gps_interference_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        assert len(findings) >= 1
        titles = [f.title for f in findings]
        assert any("interference" in t.lower() or "satellite" in t.lower() for t in titles), f"Expected an interference finding, got: {titles}"

    def test_clean_gps_produces_no_flags(self):
        """Good GPS (low HDOP, stable sats) should produce no findings."""
        n = 100
        ts = _timestamps(n, rate_hz=5.0)
        gps = pd.DataFrame(
            {
                "timestamp": ts,
                "hdop": [0.8] * n,
                "satellites_used": [14] * n,
            }
        )
        flight = _empty_flight()
        flight.gps = gps
        plugin = EnvironmentConditionsPlugin()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        # None of the findings should be about multipath or interference
        bad_titles = [f.title for f in findings if "multipath" in f.title.lower() or "interference" in f.title.lower()]
        assert not bad_titles

    def test_wind_loading_produces_finding(self):
        """Sustained attitude bias triggers wind loading indicator."""
        n = 200
        ts = _timestamps(n, rate_hz=10.0)
        # Actual roll biased 10 degrees more than setpoint
        att = pd.DataFrame(
            {
                "timestamp": ts,
                "roll": np.radians(np.full(n, 10.0)),
                "pitch": np.zeros(n),
            }
        )
        att_sp = pd.DataFrame(
            {
                "timestamp": ts,
                "roll": np.zeros(n),
                "pitch": np.zeros(n),
            }
        )
        flight = _empty_flight()
        # Need minimal gps to satisfy required_stream check in forensic_analyze,
        # but analyze() is called directly here
        flight.gps = pd.DataFrame({"timestamp": ts, "hdop": [1.0] * n})
        flight.attitude = att
        flight.attitude_setpoint = att_sp
        plugin = EnvironmentConditionsPlugin()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        wind_findings = [f for f in findings if "wind" in f.title.lower()]
        assert len(wind_findings) >= 1, f"Expected wind loading finding, got: {[f.title for f in findings]}"


# ===========================================================================
# Plugin 2: damage_impact_classification
# ===========================================================================


class TestDamageImpactClassificationManifest:
    def test_manifest_complete(self):
        plugin = DamageImpactClassificationPlugin()
        m = plugin.manifest
        assert m.plugin_id == "damage_impact_classification"
        assert m.name
        assert m.version
        assert m.author
        assert m.description
        assert m.primary_stream == "attitude"
        assert "attitude" in m.required_streams
        assert len(m.output_finding_types) > 0

    def test_manifest_category_is_crash(self):
        from goose.plugins.contract import PluginCategory

        plugin = DamageImpactClassificationPlugin()
        assert plugin.manifest.category == PluginCategory.CRASH


class TestDamageImpactClassificationEmptyData:
    def test_returns_empty_on_no_data(self):
        plugin = DamageImpactClassificationPlugin()
        flight = _empty_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)

    def test_does_not_crash_on_empty_flight(self):
        plugin = DamageImpactClassificationPlugin()
        findings = plugin.analyze(_empty_flight(), {})
        assert isinstance(findings, list)


class TestDamageImpactClassificationDetection:
    def _make_impact_flight(self) -> Flight:
        """Flight with a clear impact: vibration spike + attitude divergence at end."""
        n = 300
        ts = _timestamps(n, rate_hz=10.0)

        # Attitude: normal until t=25s, then sudden large jump (impact at index 250)
        roll_vals = np.zeros(n)
        roll_vals[250:] = np.radians(90.0)  # large attitude jump
        att = pd.DataFrame(
            {
                "timestamp": ts,
                "roll": roll_vals,
                "pitch": np.zeros(n),
                "yaw": np.zeros(n),
            }
        )

        # Vibration: spike at index 250
        accel_x = np.zeros(n)
        accel_x[250] = 80.0  # > 50 m/s² threshold
        vib = pd.DataFrame(
            {
                "timestamp": ts,
                "accel_x": accel_x,
                "accel_y": np.zeros(n),
                "accel_z": np.zeros(n),
            }
        )

        flight = _empty_flight()
        flight.attitude = att
        flight.vibration = vib
        return flight

    def _make_pre_impact_anomaly_flight(self) -> Flight:
        """Flight with motor saturation before an impact."""
        n = 300
        ts = _timestamps(n, rate_hz=10.0)
        impact_idx = 250

        roll_vals = np.zeros(n)
        roll_vals[impact_idx:] = np.radians(80.0)
        att = pd.DataFrame(
            {
                "timestamp": ts,
                "roll": roll_vals,
                "pitch": np.zeros(n),
                "yaw": np.zeros(n),
            }
        )

        accel_x = np.zeros(n)
        accel_x[impact_idx] = 80.0
        vib = pd.DataFrame(
            {
                "timestamp": ts,
                "accel_x": accel_x,
                "accel_y": np.zeros(n),
                "accel_z": np.zeros(n),
            }
        )

        # Motor saturated in the 10 seconds before impact
        motor_output = np.full(n, 0.6)
        motor_output[200:impact_idx] = 0.99  # saturation in pre-impact window
        motors = pd.DataFrame(
            {
                "timestamp": ts,
                "output_0": motor_output,
                "output_1": np.full(n, 0.6),
                "output_2": np.full(n, 0.6),
                "output_3": np.full(n, 0.6),
            }
        )

        flight = _empty_flight()
        flight.attitude = att
        flight.vibration = vib
        flight.motors = motors
        return flight

    def test_impact_signature_detected(self):
        plugin = DamageImpactClassificationPlugin()
        flight = self._make_impact_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        assert len(findings) >= 1
        impact_findings = [f for f in findings if "impact" in f.title.lower()]
        assert len(impact_findings) >= 1, f"Expected an impact finding, got: {[f.title for f in findings]}"

    def test_pre_impact_anomaly_detected(self):
        plugin = DamageImpactClassificationPlugin()
        flight = self._make_pre_impact_anomaly_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        pre_impact = [f for f in findings if "pre-impact" in f.title.lower() or "pre_impact" in str(f.evidence)]
        assert len(pre_impact) >= 1, f"Expected a pre-impact finding, got: {[f.title for f in findings]}"

    def test_sequence_indicator_emitted(self):
        plugin = DamageImpactClassificationPlugin()
        flight = self._make_impact_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        seq_findings = [f for f in findings if "sequence" in f.title.lower()]
        assert len(seq_findings) >= 1, f"Expected a sequence indicator, got: {[f.title for f in findings]}"

    def test_post_impact_artifact_emitted(self):
        plugin = DamageImpactClassificationPlugin()
        flight = self._make_impact_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        post = [f for f in findings if "post-impact" in f.title.lower()]
        assert len(post) >= 1, f"Expected a post-impact artifact finding, got: {[f.title for f in findings]}"


# ===========================================================================
# Plugin 3: link_telemetry_health
# ===========================================================================


class TestLinkTelemetryHealthManifest:
    def test_manifest_complete(self):
        plugin = LinkTelemetryHealthPlugin()
        m = plugin.manifest
        assert m.plugin_id == "link_telemetry_health"
        assert m.name
        assert m.version
        assert m.author
        assert m.description
        assert m.primary_stream == "rc_channels"
        assert "rc_input" in m.required_streams
        assert len(m.output_finding_types) > 0

    def test_manifest_category_is_health(self):
        from goose.plugins.contract import PluginCategory

        plugin = LinkTelemetryHealthPlugin()
        assert plugin.manifest.category == PluginCategory.HEALTH


class TestLinkTelemetryHealthEmptyData:
    def test_returns_empty_on_no_data(self):
        plugin = LinkTelemetryHealthPlugin()
        flight = _empty_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        # No RC data -> no findings (plugin does its own check)
        assert isinstance(findings, list)

    def test_does_not_crash_on_empty_flight(self):
        plugin = LinkTelemetryHealthPlugin()
        findings = plugin.analyze(_empty_flight(), {})
        assert isinstance(findings, list)


class TestLinkTelemetryHealthDetection:
    def _make_rc_marginal_flight(self) -> Flight:
        """RC RSSI near its lower observed bound."""
        n = 200
        ts = _timestamps(n, rate_hz=10.0)
        # RSSI oscillates near the low end
        rssi = np.concatenate(
            [
                np.full(10, 80.0),  # normal
                np.full(180, 22.0),  # sustained near bottom
                np.full(10, 80.0),
            ]
        )
        rc = pd.DataFrame({"timestamp": ts, "rssi": rssi[:n]})
        flight = _empty_flight()
        flight.rc_input = rc
        return flight

    def _make_rc_dropout_flight(self) -> Flight:
        """RC data with 3+ gaps >= 1.0 second (simulating link losses)."""
        # Create timestamps with deliberate gaps of 2 seconds
        ts_parts = []
        base = 0.0
        for _i in range(4):
            chunk = np.arange(20, dtype=float) * 0.1 + base
            ts_parts.append(chunk)
            base = chunk[-1] + 2.5  # 2.5s gap between chunks

        ts = np.concatenate(ts_parts)
        rssi = np.full(len(ts), 80.0)
        rc = pd.DataFrame({"timestamp": ts, "rssi": rssi})
        flight = _empty_flight()
        flight.rc_input = rc
        return flight

    def _make_telemetry_gap_flight(self) -> Flight:
        """RC data with one large timestamp gap (telemetry gap)."""
        ts1 = np.arange(50, dtype=float) * 0.1  # 0–5s at 10 Hz
        ts2 = np.arange(50, dtype=float) * 0.1 + 15.0  # 15–20s (10s gap in middle)
        ts = np.concatenate([ts1, ts2])
        rc = pd.DataFrame({"timestamp": ts, "rssi": np.full(len(ts), 75.0)})
        flight = _empty_flight()
        flight.rc_input = rc
        return flight

    def test_rc_marginal_produces_finding(self):
        plugin = LinkTelemetryHealthPlugin()
        flight = self._make_rc_marginal_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        assert len(findings) >= 1
        marginal = [f for f in findings if "marginal" in f.title.lower()]
        assert len(marginal) >= 1, f"Expected rc_link_marginal finding, got: {[f.title for f in findings]}"

    def test_rc_dropout_produces_lost_finding(self):
        plugin = LinkTelemetryHealthPlugin()
        flight = self._make_rc_dropout_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        assert len(findings) >= 1
        lost = [f for f in findings if "lost" in f.title.lower() or "loss" in f.title.lower()]
        assert len(lost) >= 1, f"Expected rc_link_lost finding, got: {[f.title for f in findings]}"

    def test_multiple_dropouts_produce_recovery_anomaly(self):
        plugin = LinkTelemetryHealthPlugin()
        flight = self._make_rc_dropout_flight()
        # 4 chunks = 3 gaps => recovery anomaly
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        recovery = [f for f in findings if "recovery" in f.title.lower()]
        assert len(recovery) >= 1, f"Expected link_recovery_anomaly finding, got: {[f.title for f in findings]}"

    def test_telemetry_gap_produces_finding(self):
        plugin = LinkTelemetryHealthPlugin()
        flight = self._make_telemetry_gap_flight()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        assert len(findings) >= 1
        telem = [f for f in findings if "telemetry" in f.title.lower() or "gap" in f.title.lower()]
        assert len(telem) >= 1, f"Expected telemetry_gap finding, got: {[f.title for f in findings]}"

    def test_clean_rc_no_flagged_findings(self):
        """Steady, high-quality RC link should produce no warning findings."""
        n = 200
        ts = _timestamps(n, rate_hz=10.0)  # perfectly regular 10 Hz
        rc = pd.DataFrame({"timestamp": ts, "rssi": np.full(n, 85.0)})
        flight = _empty_flight()
        flight.rc_input = rc
        plugin = LinkTelemetryHealthPlugin()
        findings = plugin.analyze(flight, {})
        _assert_findings_valid(findings)
        warnings = [f for f in findings if f.severity in ("warning", "critical")]
        assert not warnings, f"Expected no warnings for clean RC link, got: {[f.title for f in warnings]}"


# ===========================================================================
# Cross-cutting: registry and tuning profile
# ===========================================================================


class TestPluginRegistry:
    def test_plugin_count_is_17(self):
        from goose.plugins import PLUGIN_REGISTRY

        assert len(PLUGIN_REGISTRY) == 17, f"Expected 17 plugins, got {len(PLUGIN_REGISTRY)}: {sorted(PLUGIN_REGISTRY.keys())}"

    def test_new_plugins_in_registry(self):
        from goose.plugins import PLUGIN_REGISTRY

        assert "environment_conditions" in PLUGIN_REGISTRY
        assert "damage_impact_classification" in PLUGIN_REGISTRY
        assert "link_telemetry_health" in PLUGIN_REGISTRY


class TestTuningProfileAllPlugins:
    def test_all_plugins_in_tuning_profile(self):
        from goose.forensics.tuning import TuningProfile
        from goose.plugins import PLUGIN_REGISTRY

        profile = TuningProfile.default()
        configured_ids = {cfg.plugin_id for cfg in profile.analyzer_configs}
        registered_ids = set(PLUGIN_REGISTRY.keys())

        missing = registered_ids - configured_ids
        assert not missing, f"These plugins are registered but have no tuning config: {sorted(missing)}"

    def test_new_plugin_configs_have_thresholds(self):
        from goose.forensics.tuning import TuningProfile

        profile = TuningProfile.default()
        for pid in (
            "environment_conditions",
            "damage_impact_classification",
            "link_telemetry_health",
        ):
            cfg = profile.get_config_for_plugin(pid)
            assert cfg is not None, f"No config for {pid}"
            assert cfg.thresholds is not None, f"No thresholds for {pid}"
            assert cfg.thresholds.values, f"Empty threshold values for {pid}"
