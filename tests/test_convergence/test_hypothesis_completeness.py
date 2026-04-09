"""Tests for Convergence Sprint 1 — forensic model completeness.

Covers:
  - Task D: _PLUGIN_STREAM_MAP removed, primary_stream on all plugin manifests
  - Task E: Hypothesis system strengthening (contradicting_findings, new themes,
            unknown_mixed fallback, payload integration)
"""

from __future__ import annotations

import uuid

import pytest

from goose.forensics.canonical import (
    EvidenceReference,
    FindingSeverity,
    ForensicFinding,
)
from goose.forensics.lifting import generate_hypotheses


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finding(
    plugin_id: str,
    severity: FindingSeverity,
    title: str = "Test finding",
    finding_id: str | None = None,
) -> ForensicFinding:
    """Create a minimal ForensicFinding for hypothesis testing."""
    return ForensicFinding(
        finding_id=finding_id or f"FND-{uuid.uuid4().hex[:8].upper()}",
        plugin_id=plugin_id,
        plugin_version="1.0.0",
        title=title,
        description="Test description",
        severity=severity,
        score=80 if severity != FindingSeverity.PASS else 100,
        confidence=0.8 if severity != FindingSeverity.PASS else 1.0,
        evidence_references=[
            EvidenceReference(evidence_id="EV-001", stream_name="test")
        ],
    )


RUN_ID = "test-run-001"


# ---------------------------------------------------------------------------
# Test 1: contradicting_findings populated
# ---------------------------------------------------------------------------

class TestContradictingFindingsPopulated:
    def test_contradicting_findings_populated(self):
        """A PASS finding from a theme's plugin_ids should appear in contradicting_findings."""
        # crash_detection belongs to the "crash" theme
        findings = [
            _finding("crash_detection", FindingSeverity.CRITICAL, "Crash detected"),
            _finding("crash_detection", FindingSeverity.PASS, "No crash signature"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)

        # Find the crash or impact_damage hypothesis
        crash_hyp = next(
            (h for h in hypotheses if h.theme in ("crash", "impact_damage")),
            None,
        )
        assert crash_hyp is not None, "Expected a crash/impact hypothesis"
        assert len(crash_hyp.contradicting_findings) > 0, (
            "contradicting_findings should be non-empty when PASS findings exist"
        )
        cf = crash_hyp.contradicting_findings[0]
        assert "finding_id" in cf
        assert "title" in cf
        assert "severity" in cf
        assert cf["severity"] == "pass"

    def test_contradicting_findings_empty_when_no_pass(self):
        """No PASS findings means contradicting_findings should be empty."""
        findings = [
            _finding("crash_detection", FindingSeverity.CRITICAL, "Crash detected"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        crash_hyp = next(
            (h for h in hypotheses if h.theme in ("crash", "impact_damage")),
            None,
        )
        assert crash_hyp is not None
        assert crash_hyp.contradicting_findings == []


# ---------------------------------------------------------------------------
# Test 2: communications_link hypothesis
# ---------------------------------------------------------------------------

class TestCommunicationsLinkHypothesis:
    def test_communications_link_hypothesis_generated(self):
        """rc_signal + failsafe_events findings should produce a communications/link hypothesis."""
        findings = [
            _finding("rc_signal", FindingSeverity.WARNING, "Low RSSI"),
            _finding("failsafe_events", FindingSeverity.CRITICAL, "RC failsafe triggered"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        categories = {h.category for h in hypotheses}
        assert "communications / link issue" in categories, (
            f"Expected 'communications / link issue' hypothesis. Got: {categories}"
        )

    def test_communications_link_theme_key(self):
        """Theme key should be 'communications_link'."""
        findings = [
            _finding("rc_signal", FindingSeverity.CRITICAL, "RC dropout"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        themes = {h.theme for h in hypotheses}
        assert "communications_link" in themes


# ---------------------------------------------------------------------------
# Test 3: impact_damage hypothesis
# ---------------------------------------------------------------------------

class TestImpactDamageHypothesis:
    def test_impact_damage_hypothesis_generated(self):
        """crash_detection CRITICAL findings should trigger an impact/damage hypothesis."""
        findings = [
            _finding("crash_detection", FindingSeverity.CRITICAL, "Hard impact detected"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        categories = {h.category for h in hypotheses}
        assert "impact / damage class" in categories, (
            f"Expected 'impact / damage class' hypothesis. Got: {categories}"
        )

    def test_impact_damage_theme_key(self):
        """Theme key should be 'impact_damage'."""
        findings = [
            _finding("crash_detection", FindingSeverity.CRITICAL, "Crash"),
            _finding("vibration", FindingSeverity.WARNING, "High vibration"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        themes = {h.theme for h in hypotheses}
        assert "impact_damage" in themes


# ---------------------------------------------------------------------------
# Test 4: unknown_mixed when no strong theme
# ---------------------------------------------------------------------------

class TestUnknownMixedWhenNoStrongTheme:
    def test_unknown_mixed_on_empty_findings(self):
        """Empty findings list should produce an unknown/mixed-factor hypothesis."""
        hypotheses = generate_hypotheses([], RUN_ID)
        categories = {h.category for h in hypotheses}
        assert "unknown / mixed-factor event" in categories, (
            f"Expected 'unknown / mixed-factor event'. Got: {categories}"
        )

    def test_unknown_mixed_on_all_pass_findings(self):
        """All-PASS findings → no supporting evidence → unknown_mixed emitted."""
        findings = [
            _finding("crash_detection", FindingSeverity.PASS, "No crash"),
            _finding("battery_sag", FindingSeverity.PASS, "Battery healthy"),
            _finding("gps_health", FindingSeverity.PASS, "GPS nominal"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        themes = {h.theme for h in hypotheses}
        assert "unknown_mixed" in themes, (
            f"Expected 'unknown_mixed' theme. Got: {themes}"
        )

    def test_unknown_mixed_not_emitted_when_strong_theme_exists(self):
        """When a strong theme (confidence >= 0.3) exists, unknown_mixed should NOT appear."""
        findings = [
            _finding("crash_detection", FindingSeverity.CRITICAL, "Crash detected"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        themes = {h.theme for h in hypotheses}
        assert "unknown_mixed" not in themes, (
            "unknown_mixed should not appear when a confident theme exists"
        )


# ---------------------------------------------------------------------------
# Test 5: _PLUGIN_STREAM_MAP gone from canonical.py
# ---------------------------------------------------------------------------

class TestPluginStreamMapGone:
    def test_plugin_stream_map_not_in_canonical(self):
        """_PLUGIN_STREAM_MAP should no longer exist in goose.forensics.canonical."""
        import goose.forensics.canonical as canonical_mod
        assert not hasattr(canonical_mod, "_PLUGIN_STREAM_MAP"), (
            "_PLUGIN_STREAM_MAP should have been removed from canonical.py (Task D)"
        )


# ---------------------------------------------------------------------------
# Test 6: primary_stream on all plugin manifests
# ---------------------------------------------------------------------------

class TestPrimaryStreamOnAllPluginManifests:
    def test_all_registered_plugins_have_primary_stream(self):
        """Every plugin in PLUGIN_REGISTRY must have a non-empty primary_stream."""
        from goose.plugins import PLUGIN_REGISTRY
        assert len(PLUGIN_REGISTRY) > 0, "PLUGIN_REGISTRY must not be empty"
        missing = [
            pid for pid, plugin in PLUGIN_REGISTRY.items()
            if not plugin.manifest.primary_stream
        ]
        assert missing == [], (
            f"These plugins are missing primary_stream on their manifest: {missing}"
        )

    def test_primary_stream_is_string(self):
        """primary_stream must be a str on every manifest."""
        from goose.plugins import PLUGIN_REGISTRY
        non_str = [
            pid for pid, plugin in PLUGIN_REGISTRY.items()
            if not isinstance(plugin.manifest.primary_stream, str)
        ]
        assert non_str == [], (
            f"primary_stream must be a str, got non-str for: {non_str}"
        )
