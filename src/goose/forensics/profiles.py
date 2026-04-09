"""User profile system for Goose-Core.

v11 Strategy Sprint — data-driven profile configurations.

A ``ProfileConfig`` is a pure data description of how the UI and reports should
be biased for a given user class (Racer, Research, Shop/Repair, Factory/QA,
Gov/Mil, Advanced, Default). Profiles **never** change forensic truth — the
same parser, plugins, and canonical models are used for every profile. They
only change defaults (which plugins are emphasized, which charts are shown
first, which case fields are prominent) and wording on the UI/report surface.

This module is intentionally a flat data file — no branching logic, no
hardcoded UI conditionals. Add a new profile by adding a new entry to
``PROFILE_CONFIGS``. The UI should read ``ProfileConfig`` at runtime and
present accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class UserProfile(str, Enum):
    """Formal user-class identifiers. Used for validation and routing."""
    RACER = "racer"
    RESEARCH = "research"
    SHOP_REPAIR = "shop_repair"
    FACTORY_QA = "factory_qa"
    GOV_MIL = "gov_mil"
    ADVANCED = "advanced"
    DEFAULT = "default"


@dataclass
class WordingPack:
    """Profile-specific terminology.

    Lets the same forensic artifact be rendered with profile-appropriate
    language without forking any backend logic. A Racer sees "Run" where
    a Gov/Mil user sees "Sortie"; the underlying record is identical.
    """
    profile_id: str
    workflow_label: str          # "Run" vs "Case" vs "Sortie" vs "Test"
    event_label: str             # "Crash" vs "Anomaly" vs "Mishap" vs "Incident"
    operator_label: str          # "Pilot" vs "Operator" vs "Technician" vs "Tester"
    platform_label: str          # "Quad" vs "UAV" vs "UAS" vs "Aircraft"
    analysis_label: str          # "Check" vs "Analysis" vs "Investigation" vs "Inspection"
    summary_heading: str         # heading used in reports
    report_sections: dict[str, str] = field(default_factory=dict)  # section key -> display title

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "workflow_label": self.workflow_label,
            "event_label": self.event_label,
            "operator_label": self.operator_label,
            "platform_label": self.platform_label,
            "analysis_label": self.analysis_label,
            "summary_heading": self.summary_heading,
            "report_sections": dict(self.report_sections),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WordingPack:
        known = {"profile_id", "workflow_label", "event_label", "operator_label",
                 "platform_label", "analysis_label", "summary_heading", "report_sections"}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class ProfileConfig:
    """Data-driven profile configuration — no hardcoded UI conditionals.

    Every field is either a string, a list of strings, or a ``WordingPack``.
    Clients (GUI, report builders, API consumers) can read this blob and
    render their interface accordingly.
    """
    profile_id: str
    name: str
    description: str
    default_entry_path: str          # "quick_analysis" or "investigation_case"
    default_plugins: list[str]       # plugin_ids to emphasize
    secondary_plugins: list[str]     # plugin_ids available but not primary
    deprioritized_plugins: list[str] # plugin_ids de-emphasized for this profile
    chart_presets: list[str]         # signal names to show by default
    findings_sort_priority: list[str]    # severity categories to sort first
    hypothesis_priority: list[str]       # hypothesis themes to show first
    visible_case_fields: list[str]       # which Case metadata fields to show prominently
    deprioritized_case_fields: list[str] # fields to hide/collapse by default
    wording: WordingPack
    report_defaults: list[str]       # default report types to offer

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "description": self.description,
            "default_entry_path": self.default_entry_path,
            "default_plugins": list(self.default_plugins),
            "secondary_plugins": list(self.secondary_plugins),
            "deprioritized_plugins": list(self.deprioritized_plugins),
            "chart_presets": list(self.chart_presets),
            "findings_sort_priority": list(self.findings_sort_priority),
            "hypothesis_priority": list(self.hypothesis_priority),
            "visible_case_fields": list(self.visible_case_fields),
            "deprioritized_case_fields": list(self.deprioritized_case_fields),
            "wording": self.wording.to_dict(),
            "report_defaults": list(self.report_defaults),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProfileConfig:
        d = dict(d)
        wording = d.get("wording")
        if isinstance(wording, dict):
            d["wording"] = WordingPack.from_dict(wording)
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)


# ---------------------------------------------------------------------------
# Registered profiles
# ---------------------------------------------------------------------------

PROFILE_CONFIGS: dict[str, ProfileConfig] = {
    "racer": ProfileConfig(
        profile_id="racer",
        name="Racer",
        description="FPV racer and performance tuning",
        default_entry_path="quick_analysis",
        default_plugins=["vibration", "motor_saturation", "attitude_tracking", "battery_sag"],
        secondary_plugins=["rc_signal", "crash_detection"],
        deprioritized_plugins=["log_health"],
        chart_presets=["gyro_rad_s", "battery_voltage_v", "motor_output"],
        findings_sort_priority=["critical", "warning"],
        hypothesis_priority=[
            "propulsion / motor issue",
            "vibration-induced instability",
            "battery / power issue",
        ],
        visible_case_fields=["platform_name", "battery_config", "recent_changes", "propulsion_notes"],
        deprioritized_case_fields=["mission_id", "sortie_id", "unit_name", "corrective_actions"],
        wording=WordingPack(
            profile_id="racer",
            workflow_label="Run",
            event_label="Crash",
            operator_label="Pilot",
            platform_label="Quad",
            analysis_label="Check",
            summary_heading="Race Run Analysis",
            report_sections={
                "summary": "Run Summary",
                "findings": "Performance Issues",
                "recommendations": "Tune Recommendations",
            },
        ),
        report_defaults=["MissionSummaryReport", "AnomalyReport"],
    ),
    "research": ProfileConfig(
        profile_id="research",
        name="Research / University",
        description="Research and academic flight analysis",
        default_entry_path="investigation_case",
        default_plugins=["log_health", "gps_health", "ekf_health", "ekf_consistency", "vibration"],
        secondary_plugins=[
            "battery_sag", "attitude_tracking", "position_tracking",
            "payload_change_detection",
        ],
        deprioritized_plugins=[],
        chart_presets=["altitude_m", "velocity_m_s", "gps_fix_type", "ekf_innovation"],
        findings_sort_priority=["critical", "warning", "info"],
        hypothesis_priority=[
            "navigation / GPS issue",
            "estimator / EKF issue",
            "vibration-induced instability",
        ],
        visible_case_fields=[
            "operator_name", "tester_name", "firmware_version",
            "hardware_config", "environment_summary",
        ],
        deprioritized_case_fields=["customer_name", "ticket_id", "unit_name"],
        wording=WordingPack(
            profile_id="research",
            workflow_label="Test",
            event_label="Anomaly",
            operator_label="Operator",
            platform_label="UAV",
            analysis_label="Analysis",
            summary_heading="Flight Test Analysis",
            report_sections={
                "summary": "Test Summary",
                "findings": "Observations",
                "recommendations": "Recommendations",
            },
        ),
        report_defaults=["MissionSummaryReport", "AnomalyReport", "ForensicCaseReport"],
    ),
    "shop_repair": ProfileConfig(
        profile_id="shop_repair",
        name="Drone Shop / Repair",
        description="Repair shop triage and fault isolation",
        default_entry_path="quick_analysis",
        default_plugins=[
            "crash_detection", "battery_sag", "vibration",
            "motor_saturation", "log_health",
        ],
        secondary_plugins=["gps_health", "ekf_health", "rc_signal"],
        deprioritized_plugins=[],
        chart_presets=["battery_voltage_v", "motor_output", "altitude_m"],
        findings_sort_priority=["critical", "warning"],
        hypothesis_priority=[
            "propulsion / motor issue",
            "battery / power issue",
            "impact / damage class",
        ],
        visible_case_fields=[
            "customer_name", "ticket_id", "platform_name",
            "damage_summary", "technician_name",
        ],
        deprioritized_case_fields=["mission_id", "unit_name", "sortie_id"],
        wording=WordingPack(
            profile_id="shop_repair",
            workflow_label="Job",
            event_label="Incident",
            operator_label="Customer",
            platform_label="Aircraft",
            analysis_label="Inspection",
            summary_heading="Repair Diagnostic Report",
            report_sections={
                "summary": "Fault Assessment",
                "findings": "Likely Cause",
                "recommendations": "Inspection Checklist",
            },
        ),
        report_defaults=["AnomalyReport", "CrashMishapReport"],
    ),
    "factory_qa": ProfileConfig(
        profile_id="factory_qa",
        name="Factory / QA",
        description="Manufacturing QA and acceptance testing",
        default_entry_path="investigation_case",
        default_plugins=[
            "log_health", "vibration", "motor_saturation",
            "attitude_tracking", "battery_sag",
        ],
        secondary_plugins=["ekf_consistency", "gps_health"],
        deprioritized_plugins=[],
        chart_presets=["motor_output", "gyro_rad_s", "battery_voltage_v"],
        findings_sort_priority=["critical", "warning", "info", "pass"],
        hypothesis_priority=[
            "propulsion / motor issue",
            "vibration-induced instability",
        ],
        visible_case_fields=[
            "serial_number", "tester_name", "firmware_version", "hardware_config",
        ],
        deprioritized_case_fields=["customer_name", "operator_name", "mission_id"],
        wording=WordingPack(
            profile_id="factory_qa",
            workflow_label="Test",
            event_label="Failure",
            operator_label="Tester",
            platform_label="Unit",
            analysis_label="Inspection",
            summary_heading="QA Test Report",
            report_sections={
                "summary": "Test Summary",
                "findings": "Out-of-Tolerance Findings",
                "recommendations": "Corrective Actions",
            },
        ),
        report_defaults=["MissionSummaryReport", "AnomalyReport"],
    ),
    "gov_mil": ProfileConfig(
        profile_id="gov_mil",
        name="Gov / Mil",
        description="Government, military, and public safety investigation",
        default_entry_path="investigation_case",
        default_plugins=[
            "crash_detection", "battery_sag", "gps_health",
            "ekf_health", "failsafe_events", "log_health",
        ],
        secondary_plugins=[
            "vibration", "motor_saturation", "attitude_tracking",
            "rc_signal", "position_tracking", "payload_change_detection",
        ],
        deprioritized_plugins=[],
        chart_presets=["altitude_m", "velocity_m_s", "battery_voltage_v", "gps_fix_type"],
        findings_sort_priority=["critical", "warning", "info"],
        hypothesis_priority=[
            "impact / damage class",
            "navigation / GPS issue",
            "communications / link issue",
            "propulsion / motor issue",
        ],
        visible_case_fields=[
            "mission_id", "sortie_id", "operation_type", "operator_name",
            "team_name", "unit_name", "location_name", "environment_summary",
            "damage_summary", "recommendations", "corrective_actions",
        ],
        deprioritized_case_fields=["customer_name", "ticket_id"],
        wording=WordingPack(
            profile_id="gov_mil",
            workflow_label="Sortie",
            event_label="Mishap",
            operator_label="Operator",
            platform_label="UAS",
            analysis_label="Investigation",
            summary_heading="Mishap Investigation Report",
            report_sections={
                "summary": "Incident Summary",
                "findings": "Causal Factors",
                "evidence": "Contributing Evidence",
                "unresolved": "Unresolved Questions",
                "recommendations": "Recommendations",
            },
        ),
        report_defaults=["ForensicCaseReport", "CrashMishapReport", "EvidenceManifestReport"],
    ),
    "advanced": ProfileConfig(
        profile_id="advanced",
        name="Advanced / Custom",
        description="Minimal assumptions, full control",
        default_entry_path="investigation_case",
        default_plugins=[],   # all plugins, no preference
        secondary_plugins=[],
        deprioritized_plugins=[],
        chart_presets=[],
        findings_sort_priority=["critical", "warning", "info", "pass"],
        hypothesis_priority=[],
        visible_case_fields=[],   # show all
        deprioritized_case_fields=[],
        wording=WordingPack(
            profile_id="advanced",
            workflow_label="Case",
            event_label="Event",
            operator_label="Operator",
            platform_label="Vehicle",
            analysis_label="Analysis",
            summary_heading="Investigation Report",
            report_sections={
                "summary": "Summary",
                "findings": "Findings",
                "recommendations": "Recommendations",
            },
        ),
        report_defaults=["MissionSummaryReport", "AnomalyReport", "ForensicCaseReport"],
    ),
    "default": ProfileConfig(
        profile_id="default",
        name="Default",
        description="Standard investigation workflow",
        default_entry_path="investigation_case",
        default_plugins=[
            "crash_detection", "battery_sag", "gps_health",
            "log_health", "vibration",
        ],
        secondary_plugins=[
            "ekf_health", "ekf_consistency", "motor_saturation",
            "attitude_tracking", "rc_signal", "position_tracking",
            "failsafe_events",
        ],
        deprioritized_plugins=[],
        chart_presets=["altitude_m", "battery_voltage_v"],
        findings_sort_priority=["critical", "warning", "info", "pass"],
        hypothesis_priority=[],
        visible_case_fields=[],
        deprioritized_case_fields=[],
        wording=WordingPack(
            profile_id="default",
            workflow_label="Case",
            event_label="Event",
            operator_label="Operator",
            platform_label="Vehicle",
            analysis_label="Analysis",
            summary_heading="Investigation Report",
            report_sections={
                "summary": "Summary",
                "findings": "Findings",
                "recommendations": "Recommendations",
            },
        ),
        report_defaults=["MissionSummaryReport", "AnomalyReport"],
    ),
}


def get_profile(profile_id: str) -> ProfileConfig:
    """Return profile config, falling back to default if not found.

    This function never raises — unknown profile_ids resolve to the default
    profile so the GUI cannot crash on a stale profile string stored in an
    older case.json.
    """
    return PROFILE_CONFIGS.get(profile_id, PROFILE_CONFIGS["default"])
