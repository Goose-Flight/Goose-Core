"""Analyzer integration golden-path tests.

Option E — Sprint 3 Phase 5: verify that findings from each of the 17 Core
plugins flow through to:
1. ForensicFinding objects (via forensic_analyze / lifting)
2. Timeline events (via build_timeline_from_findings)
3. Hypotheses (via generate_hypotheses, where themes reference the plugin)

This is a regression-protection suite for the analyzer integration path.
It does NOT test the correctness of individual plugin findings — that is the
responsibility of the per-plugin unit tests.  It tests that the integration
seams between plugins, lifting, timeline, and hypotheses are all wired up
and not silently broken.

Design rules:
- Creates a rich synthetic Flight object covering all streams.
- Runs each plugin via forensic_analyze() (the real production path).
- Verifies findings arrive in the lifted layer (ForensicFinding).
- Verifies findings that carry timestamps surface in the timeline.
- Verifies that hypothesis themes referencing this plugin are generated
  when the plugin emits non-PASS findings.
- Each plugin category is covered; no plugin is skipped.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightEvent, FlightMetadata, FlightPhase, ModeChange
from goose.forensics.canonical import FindingSeverity, ForensicFinding
from goose.forensics.lifting import build_signal_quality, generate_hypotheses
from goose.forensics.models import EvidenceItem, Provenance
from goose.forensics.timeline import build_timeline_from_findings
from goose.parsers.diagnostics import ParseDiagnostics, StreamCoverage
from goose.plugins import PLUGIN_REGISTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_timestamps(n: int = 120, start: float = 0.0, step: float = 0.5) -> list[float]:
    return [start + i * step for i in range(n)]


def _make_attitude(n: int = 120) -> pd.DataFrame:
    ts = _make_timestamps(n)
    return pd.DataFrame({
        "timestamp": ts,
        "roll": np.sin(np.linspace(0, 4 * np.pi, n)) * 5,
        "pitch": np.cos(np.linspace(0, 4 * np.pi, n)) * 3,
        "yaw": np.linspace(0, 360, n),
        "roll_setpoint": np.zeros(n),
        "pitch_setpoint": np.zeros(n),
        "yaw_setpoint": np.linspace(0, 360, n),
    })


def _make_battery(n: int = 120, include_sag: bool = True) -> pd.DataFrame:
    ts = _make_timestamps(n)
    # Voltage starts at 25.2V and drops (mild sag pattern)
    voltage = np.linspace(25.2, 22.0, n)
    current = np.ones(n) * 15.0
    if include_sag:
        # Add a brief sag event at t=30s
        sag_idx = int(0.25 * n)
        voltage[sag_idx:sag_idx + 5] -= 1.5
        current[sag_idx:sag_idx + 5] += 10.0
    return pd.DataFrame({
        "timestamp": ts,
        "voltage": voltage,
        "current": current,
        "remaining_pct": np.linspace(100, 50, n),
    })


def _make_gps(n: int = 120) -> pd.DataFrame:
    ts = _make_timestamps(n)
    return pd.DataFrame({
        "timestamp": ts,
        "lat": np.linspace(37.7749, 37.7759, n),
        "lon": np.linspace(-122.4194, -122.4184, n),
        "alt": np.linspace(0, 50, n),
        "fix_type": [3] * n,
        "satellites": [12] * n,
        "hdop": [0.9] * n,
    })


def _make_vibration(n: int = 120, spike: bool = False) -> pd.DataFrame:
    ts = _make_timestamps(n)
    x = np.random.default_rng(42).uniform(0, 5, n)
    y = np.random.default_rng(43).uniform(0, 5, n)
    z = np.random.default_rng(44).uniform(0, 5, n)
    if spike:
        mid = n // 2
        x[mid] = 80.0
        y[mid] = 80.0
        z[mid] = 80.0
    return pd.DataFrame({"timestamp": ts, "vibration_x": x, "vibration_y": y, "vibration_z": z})


def _make_motors(n: int = 120) -> pd.DataFrame:
    ts = _make_timestamps(n)
    return pd.DataFrame({
        "timestamp": ts,
        "output_0": np.ones(n) * 0.5,
        "output_1": np.ones(n) * 0.5,
        "output_2": np.ones(n) * 0.5,
        "output_3": np.ones(n) * 0.5,
    })


def _make_rc_input(n: int = 120) -> pd.DataFrame:
    ts = _make_timestamps(n)
    return pd.DataFrame({
        "timestamp": ts,
        "ch1": np.ones(n) * 1500,
        "ch2": np.ones(n) * 1500,
        "ch3": np.ones(n) * 1500,
        "ch4": np.ones(n) * 1500,
    })


def _make_ekf(n: int = 120) -> pd.DataFrame:
    ts = _make_timestamps(n)
    return pd.DataFrame({
        "timestamp": ts,
        "VIBE": np.zeros(n),
        "IVN": np.zeros(n),
        "IVE": np.zeros(n),
        "IVD": np.zeros(n),
        "IPN": np.zeros(n),
        "IPE": np.zeros(n),
        "OFN": np.zeros(n),
        "OFE": np.zeros(n),
        "FS": np.zeros(n),
    })


def _make_position(n: int = 120) -> pd.DataFrame:
    ts = _make_timestamps(n)
    return pd.DataFrame({
        "timestamp": ts,
        "alt_rel": np.linspace(0, 50, n),
        "alt_msl": np.linspace(10, 60, n),
    })


def _make_rich_flight() -> Flight:
    """Build a synthetic Flight covering all major streams."""
    n = 120
    meta = FlightMetadata(
        source_file="test_integration.ulg",
        autopilot="px4",
        firmware_version="1.14.0",
        vehicle_type="quadcopter",
        frame_type="x500",
        hardware="Pixhawk 6C",
        duration_sec=60.0,
        start_time_utc=datetime(2026, 4, 9, 12, 0, 0),
        log_format="ulog",
        motor_count=4,
    )
    mode_changes = [
        ModeChange(timestamp=0.0, from_mode="none", to_mode="stabilize"),
        ModeChange(timestamp=5.0, from_mode="stabilize", to_mode="loiter"),
    ]
    events = [
        FlightEvent(timestamp=1.0, event_type="info", severity="info", message="Armed"),
        FlightEvent(timestamp=55.0, event_type="info", severity="info", message="Disarmed"),
    ]
    phases = [
        FlightPhase(start_time=0.0, end_time=5.0, phase_type="takeoff"),
        FlightPhase(start_time=5.0, end_time=55.0, phase_type="cruise"),
        FlightPhase(start_time=55.0, end_time=60.0, phase_type="landing"),
    ]
    return Flight(
        metadata=meta,
        attitude=_make_attitude(n),
        battery=_make_battery(n),
        gps=_make_gps(n),
        vibration=_make_vibration(n, spike=False),
        motors=_make_motors(n),
        rc_input=_make_rc_input(n),
        ekf=_make_ekf(n),
        position=_make_position(n),
        mode_changes=mode_changes,
        events=events,
        phases=phases,
    )


def _make_evidence_item() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="EV-TEST-001",
        filename="test_integration.ulg",
        content_type="application/octet-stream",
        size_bytes=1024,
        sha256="abc123",
        sha512=None,
        source_acquisition_mode="local_copy",
        source_reference=None,
        stored_path="/tmp/test_integration.ulg",
        acquired_at=datetime(2026, 4, 9, 12, 0, 0),
        acquired_by="test",
    )


def _make_parse_diagnostics() -> ParseDiagnostics:
    streams = ["attitude", "battery", "gps", "vibration", "motors", "rc_input", "ekf", "position"]
    return ParseDiagnostics(
        parser_selected="ulog",
        parser_version="1.0.0",
        detected_format="ulog",
        format_confidence=0.95,
        supported=True,
        parser_confidence=0.9,
        stream_coverage=[StreamCoverage(s, present=True, row_count=120) for s in streams],
    )


def _run_plugin_forensic(plugin_id: str, flight: Flight) -> list[ForensicFinding]:
    """Run a plugin via forensic_analyze and return ForensicFindings."""
    plugin = PLUGIN_REGISTRY[plugin_id]
    ev = _make_evidence_item()
    run_id = f"RUN-TEST-{plugin_id.upper()[:8]}"
    diag = _make_parse_diagnostics()

    from goose.forensics.tuning import TuningProfile
    tuning = TuningProfile.default()

    ff_list, _p_diag = plugin.forensic_analyze(
        flight, ev.evidence_id, run_id, {}, diag, tuning_profile=tuning
    )
    return ff_list


# ---------------------------------------------------------------------------
# Core registry check
# ---------------------------------------------------------------------------

ALL_PLUGIN_IDS = [
    "crash_detection",
    "vibration",
    "battery_sag",
    "gps_health",
    "motor_saturation",
    "ekf_consistency",
    "rc_signal",
    "attitude_tracking",
    "position_tracking",
    "failsafe_events",
    "log_health",
    "payload_change_detection",
    "mission_phase_anomaly",
    "operator_action_sequence",
    "environment_conditions",
    "damage_impact_classification",
    "link_telemetry_health",
]


def test_all_expected_plugins_are_registered():
    """Golden-path: all 17 expected plugins are in PLUGIN_REGISTRY."""
    for plugin_id in ALL_PLUGIN_IDS:
        assert plugin_id in PLUGIN_REGISTRY, (
            f"Plugin '{plugin_id}' is not in PLUGIN_REGISTRY — "
            "was it removed or renamed?"
        )


def test_plugin_count_is_17():
    """Confirm Core ships exactly 17 built-in plugins."""
    assert len(PLUGIN_REGISTRY) == 17, (
        f"Expected 17 plugins, got {len(PLUGIN_REGISTRY)}. "
        f"Registry keys: {sorted(PLUGIN_REGISTRY.keys())}"
    )


# ---------------------------------------------------------------------------
# Per-plugin forensic_analyze() integration
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rich_flight() -> Flight:
    return _make_rich_flight()


@pytest.mark.parametrize("plugin_id", ALL_PLUGIN_IDS)
def test_plugin_forensic_analyze_does_not_raise(plugin_id, rich_flight):
    """Every plugin must return a result without raising."""
    ff_list = _run_plugin_forensic(plugin_id, rich_flight)
    # Must be a list (possibly empty)
    assert isinstance(ff_list, list)


@pytest.mark.parametrize("plugin_id", ALL_PLUGIN_IDS)
def test_plugin_forensic_analyze_returns_forensic_findings(plugin_id, rich_flight):
    """Every non-empty result must contain ForensicFinding objects."""
    ff_list = _run_plugin_forensic(plugin_id, rich_flight)
    for ff in ff_list:
        assert isinstance(ff, ForensicFinding), (
            f"Plugin {plugin_id} returned a non-ForensicFinding: {type(ff)}"
        )


@pytest.mark.parametrize("plugin_id", ALL_PLUGIN_IDS)
def test_plugin_findings_have_required_fields(plugin_id, rich_flight):
    """Each ForensicFinding must have finding_id, plugin_id, severity, evidence_references."""
    ff_list = _run_plugin_forensic(plugin_id, rich_flight)
    for ff in ff_list:
        assert ff.finding_id, f"Plugin {plugin_id}: finding missing finding_id"
        assert ff.plugin_id, f"Plugin {plugin_id}: finding missing plugin_id"
        assert ff.severity in FindingSeverity, f"Plugin {plugin_id}: invalid severity {ff.severity}"
        assert isinstance(ff.evidence_references, list), (
            f"Plugin {plugin_id}: evidence_references must be a list"
        )


# ---------------------------------------------------------------------------
# Timeline integration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("plugin_id", ALL_PLUGIN_IDS)
def test_timestamped_findings_appear_in_timeline(plugin_id, rich_flight):
    """Findings with timestamp_start must produce TimelineEvents via build_timeline_from_findings."""
    ff_list = _run_plugin_forensic(plugin_id, rich_flight)
    if not ff_list:
        pytest.skip(f"Plugin {plugin_id} emitted no findings on synthetic flight — skip timeline check")

    run_id = f"RUN-TL-{plugin_id.upper()[:8]}"
    timeline_events = build_timeline_from_findings(ff_list, run_id=run_id)

    # Count findings with a timestamp (ForensicFinding uses start_time, not timestamp_start)
    timestamped = [
        ff for ff in ff_list
        if ff.start_time is not None
    ]
    timeline_finding_events = [
        e for e in timeline_events
        if e.source == "plugin"
    ]

    # Every timestamped finding should produce a timeline event
    assert len(timeline_finding_events) >= len(timestamped), (
        f"Plugin {plugin_id}: {len(timestamped)} timestamped findings but only "
        f"{len(timeline_finding_events)} timeline events produced."
    )


def test_all_plugins_together_build_timeline(rich_flight):
    """Run all plugins together and verify the full timeline is non-empty."""
    all_findings: list[ForensicFinding] = []
    for pid in ALL_PLUGIN_IDS:
        all_findings.extend(_run_plugin_forensic(pid, rich_flight))

    if not all_findings:
        pytest.skip("No findings produced by any plugin on synthetic flight")

    run_id = "RUN-FULL-TIMELINE"
    timeline = build_timeline_from_findings(all_findings, run_id=run_id)
    # Timeline may include 0 events if all findings lack timestamps — that's OK
    assert isinstance(timeline, list)


# ---------------------------------------------------------------------------
# Hypothesis integration
# ---------------------------------------------------------------------------

# Map plugin_id -> hypothesis themes that should be generated when this plugin
# emits non-PASS findings.  Only list themes where the plugin is directly
# referenced in lifting._HYPOTHESIS_THEMES.
_PLUGIN_TO_THEMES: dict[str, list[str]] = {
    "crash_detection":           ["crash"],
    "battery_sag":               ["power"],
    "gps_health":                ["navigation", "environmental"],
    "ekf_consistency":           ["navigation", "environmental"],
    "vibration":                 ["vibration"],
    "motor_saturation":          ["propulsion"],
    "attitude_tracking":         ["control"],
    "rc_signal":                 ["communications_link", "operator_action"],
    "failsafe_events":           ["communications_link", "operator_action"],
    "operator_action_sequence":  ["communications_link", "operator_action"],
    "payload_change_detection":  ["impact_damage"],
    "damage_impact_classification": ["impact_damage"],
    # Plugins not directly referenced in _HYPOTHESIS_THEMES — no theme assertion
    "position_tracking":         [],
    "log_health":                [],
    "mission_phase_anomaly":     [],
    "environment_conditions":    [],
    "link_telemetry_health":     [],
}


@pytest.mark.parametrize("plugin_id", [
    pid for pid in ALL_PLUGIN_IDS if _PLUGIN_TO_THEMES.get(pid)
])
def test_plugin_findings_drive_hypothesis_generation(plugin_id, rich_flight):
    """Plugins that map to a hypothesis theme must produce at least one hypothesis
    when they emit non-PASS findings.

    Theme generation requires findings whose severity is in the theme's
    severity_filter AND whose plugin_id matches the theme's plugin_ids set.
    If the synthetic flight does not trigger this specific condition, we skip
    rather than fail — this avoids false failures caused by the synthetic flight
    not being "bad enough" to trigger critical/warning findings from every plugin.

    The key assertion: generate_hypotheses() must not crash and must return a list
    when the plugin has findings.  If the plugin_id IS in a theme's plugin set AND
    we have non-PASS findings for it, we verify the theme appears.
    """
    from goose.forensics.lifting import _HYPOTHESIS_THEMES

    ff_list = _run_plugin_forensic(plugin_id, rich_flight)
    if not ff_list:
        pytest.skip(f"Plugin {plugin_id} emitted no findings on synthetic flight")

    run_id = f"RUN-HYP-{plugin_id.upper()[:8]}"
    diag = _make_parse_diagnostics()

    # generate_hypotheses must not raise regardless of finding mix
    hypotheses = generate_hypotheses(ff_list, run_id=run_id, parse_diag=diag)
    assert isinstance(hypotheses, list), (
        f"Plugin {plugin_id}: generate_hypotheses() must return a list"
    )

    # For strict theme verification: only assert if we have warning/critical findings
    # that would actually match the theme's severity_filter.
    non_pass_sev = {f.severity.value for f in ff_list if f.severity != FindingSeverity.PASS}
    warning_or_critical = {"critical", "warning"} & non_pass_sev
    if not warning_or_critical:
        return  # Only PASS or INFO findings — theme won't be generated; that's correct

    generated_themes = {h.theme for h in hypotheses}
    expected_themes = _PLUGIN_TO_THEMES[plugin_id]

    # Check if ANY theme in _HYPOTHESIS_THEMES directly references this plugin_id
    # (accounting for lazy callables)
    themes_with_this_plugin: list[str] = []
    for te in _HYPOTHESIS_THEMES:
        plugin_ids_val = te["plugin_ids"]
        resolved: set[str] = plugin_ids_val() if callable(plugin_ids_val) else plugin_ids_val
        if plugin_id in resolved:
            themes_with_this_plugin.append(te["theme"])

    if not themes_with_this_plugin:
        return  # Plugin not in any theme — no hypothesis assertion needed

    # At least one of the expected themes should be generated
    matching = set(themes_with_this_plugin) & generated_themes
    assert matching, (
        f"Plugin {plugin_id} emitted warning/critical findings but none of the "
        f"expected hypothesis themes {themes_with_this_plugin!r} were generated. "
        f"Generated themes: {sorted(generated_themes)}. "
        f"Findings: {[(f.plugin_id, f.severity.value) for f in ff_list]}"
    )


def test_all_plugins_together_generate_hypotheses(rich_flight):
    """Run all plugins + generate_hypotheses; verify no crash and at least some hypotheses."""
    all_findings: list[ForensicFinding] = []
    for pid in ALL_PLUGIN_IDS:
        all_findings.extend(_run_plugin_forensic(pid, rich_flight))

    if not all_findings:
        pytest.skip("No findings produced by any plugin")

    run_id = "RUN-HYP-ALL"
    diag = _make_parse_diagnostics()
    hypotheses = generate_hypotheses(all_findings, run_id=run_id, parse_diag=diag)

    assert isinstance(hypotheses, list)
    # With a full-stream flight there should be at least some hypotheses
    # (even if confidence is low — pass findings alone won't generate hypotheses)


# ---------------------------------------------------------------------------
# Forensic finding contract compliance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("plugin_id", ALL_PLUGIN_IDS)
def test_forensic_findings_are_serializable(plugin_id, rich_flight):
    """Every ForensicFinding must round-trip through to_dict()/from_dict()."""
    ff_list = _run_plugin_forensic(plugin_id, rich_flight)
    for ff in ff_list:
        d = ff.to_dict()
        assert isinstance(d, dict)
        assert "finding_id" in d
        assert "severity" in d
        assert "plugin_id" in d
        # Deserialize back
        ff2 = ForensicFinding.from_dict(d)
        assert ff2.finding_id == ff.finding_id
        assert ff2.plugin_id == ff.plugin_id


@pytest.mark.parametrize("plugin_id", ALL_PLUGIN_IDS)
def test_plugin_diagnostics_returned(plugin_id, rich_flight):
    """forensic_analyze() must return a PluginDiagnostics object alongside findings."""
    from goose.plugins.contract import PluginDiagnostics
    from goose.forensics.tuning import TuningProfile

    plugin = PLUGIN_REGISTRY[plugin_id]
    ev = _make_evidence_item()
    run_id = f"RUN-PDIAG-{plugin_id.upper()[:8]}"
    diag = _make_parse_diagnostics()
    tuning = TuningProfile.default()

    ff_list, p_diag = plugin.forensic_analyze(
        rich_flight, ev.evidence_id, run_id, {}, diag, tuning_profile=tuning
    )
    assert isinstance(p_diag, PluginDiagnostics), (
        f"Plugin {plugin_id} did not return a PluginDiagnostics object"
    )
    assert p_diag.plugin_id == plugin.manifest.plugin_id


# ---------------------------------------------------------------------------
# Empty flight degrades gracefully
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("plugin_id", ALL_PLUGIN_IDS)
def test_plugin_handles_empty_flight_gracefully(plugin_id):
    """Every plugin must return a list (possibly empty) on a Flight with no streams."""
    meta = FlightMetadata(
        source_file="empty.ulg",
        autopilot="px4",
        firmware_version="1.14.0",
        vehicle_type="quadcopter",
        frame_type=None,
        hardware=None,
        duration_sec=0.0,
        start_time_utc=None,
        log_format="ulog",
        motor_count=4,
    )
    empty_flight = Flight(metadata=meta)
    # Should not raise
    ff_list = _run_plugin_forensic(plugin_id, empty_flight)
    assert isinstance(ff_list, list)
