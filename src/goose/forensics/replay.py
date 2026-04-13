"""Formal replay subsystem for Goose-Core.

Advanced Forensic Validation Sprint — Replay, Verification, Determinism

Re-runs analysis on a case and compares to a prior run, producing a
ReplayVerificationRecord with full structured diff.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReplayStatus(str, Enum):
    EXACT_MATCH = "exact_match"
    EXPECTED_DRIFT = "expected_drift"
    UNEXPECTED_DRIFT = "unexpected_drift"
    INCOMPATIBLE = "incompatible"


class DriftCategory(str, Enum):
    ENGINE_VERSION = "engine_version"
    PARSER_VERSION = "parser_version"
    PLUGIN_VERSION = "plugin_version"
    TUNING_PROFILE = "tuning_profile"
    SCHEMA_VERSION = "schema_version"
    EVIDENCE_MISSING = "evidence_missing"
    FINDINGS_CHANGED = "findings_changed"
    CONFIDENCE_SHIFTED = "confidence_shifted"


@dataclass
class ReplayRequest:
    source_case_id: str
    source_run_id: str
    requested_at: str = field(default_factory=lambda: datetime.now().isoformat())
    requested_by: str = "system"
    override_tuning_profile: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_case_id": self.source_case_id,
            "source_run_id": self.source_run_id,
            "requested_at": self.requested_at,
            "requested_by": self.requested_by,
            "override_tuning_profile": self.override_tuning_profile,
        }


@dataclass
class FindingDifference:
    finding_id: str
    change_type: str  # "added", "removed", "confidence_changed", "severity_changed"
    original_value: dict[str, Any] | None = None
    replay_value: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "change_type": self.change_type,
            "original_value": self.original_value,
            "replay_value": self.replay_value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FindingDifference:
        return cls(
            **{
                k: v
                for k, v in d.items()
                if k
                in {
                    "finding_id",
                    "change_type",
                    "original_value",
                    "replay_value",
                }
            }
        )


@dataclass
class ReplayDifferenceSummary:
    findings_added: list[str] = field(default_factory=list)
    findings_removed: list[str] = field(default_factory=list)
    findings_changed: list[FindingDifference] = field(default_factory=list)
    # Human-readable finding titles for added/removed findings — makes the
    # replay output immediately readable without cross-referencing finding IDs.
    finding_titles_added: list[str] = field(default_factory=list)
    finding_titles_removed: list[str] = field(default_factory=list)
    hypotheses_added: int = 0
    hypotheses_removed: int = 0
    parser_confidence_delta: float | None = None
    plugin_execution_changes: list[str] = field(default_factory=list)
    drift_categories: list[DriftCategory] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings_added": self.findings_added,
            "findings_removed": self.findings_removed,
            "findings_changed": [f.to_dict() for f in self.findings_changed],
            "finding_titles_added": self.finding_titles_added,
            "finding_titles_removed": self.finding_titles_removed,
            "hypotheses_added": self.hypotheses_added,
            "hypotheses_removed": self.hypotheses_removed,
            "parser_confidence_delta": self.parser_confidence_delta,
            "plugin_execution_changes": self.plugin_execution_changes,
            "drift_categories": [d.value for d in self.drift_categories],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReplayDifferenceSummary:
        d = dict(d)
        d["findings_changed"] = [FindingDifference.from_dict(f) for f in d.get("findings_changed", [])]
        d["drift_categories"] = [DriftCategory(c) for c in d.get("drift_categories", [])]
        return cls(
            **{
                k: v
                for k, v in d.items()
                if k
                in {
                    "findings_added",
                    "findings_removed",
                    "findings_changed",
                    "finding_titles_added",
                    "finding_titles_removed",
                    "hypotheses_added",
                    "hypotheses_removed",
                    "parser_confidence_delta",
                    "plugin_execution_changes",
                    "drift_categories",
                }
            }
        )


@dataclass
class ReplayVerificationRecord:
    """Persisted replay verification artifact."""

    replay_id: str
    source_case_id: str
    source_run_id: str
    replay_run_id: str
    status: ReplayStatus
    original_engine_version: str
    replay_engine_version: str
    original_parser_version: str
    replay_parser_version: str
    original_plugin_versions: dict[str, str]
    replay_plugin_versions: dict[str, str]
    original_tuning_profile: str
    replay_tuning_profile: str
    difference_summary: ReplayDifferenceSummary
    verified_at: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "replay_id": self.replay_id,
            "source_case_id": self.source_case_id,
            "source_run_id": self.source_run_id,
            "replay_run_id": self.replay_run_id,
            "status": self.status.value,
            "original_engine_version": self.original_engine_version,
            "replay_engine_version": self.replay_engine_version,
            "original_parser_version": self.original_parser_version,
            "replay_parser_version": self.replay_parser_version,
            "original_plugin_versions": self.original_plugin_versions,
            "replay_plugin_versions": self.replay_plugin_versions,
            "original_tuning_profile": self.original_tuning_profile,
            "replay_tuning_profile": self.replay_tuning_profile,
            "difference_summary": self.difference_summary.to_dict(),
            "verified_at": self.verified_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReplayVerificationRecord:
        d = dict(d)
        d["status"] = ReplayStatus(d["status"])
        d["difference_summary"] = ReplayDifferenceSummary.from_dict(d.get("difference_summary", {}))
        known = {
            "replay_id",
            "source_case_id",
            "source_run_id",
            "replay_run_id",
            "status",
            "original_engine_version",
            "replay_engine_version",
            "original_parser_version",
            "replay_parser_version",
            "original_plugin_versions",
            "replay_plugin_versions",
            "original_tuning_profile",
            "replay_tuning_profile",
            "difference_summary",
            "verified_at",
            "notes",
        }
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------


def _diff_findings(
    original_findings: list[dict[str, Any]],
    replay_findings: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[FindingDifference]]:
    """Compare two finding lists. Returns (added_ids, removed_ids, changed)."""
    orig_map: dict[str, dict[str, Any]] = {}
    for f in original_findings:
        fid = f.get("finding_id", f.get("title", str(id(f))))
        orig_map[fid] = f

    replay_map: dict[str, dict[str, Any]] = {}
    for f in replay_findings:
        fid = f.get("finding_id", f.get("title", str(id(f))))
        replay_map[fid] = f

    orig_ids = set(orig_map.keys())
    replay_ids = set(replay_map.keys())

    added = sorted(replay_ids - orig_ids)
    removed = sorted(orig_ids - replay_ids)

    changed: list[FindingDifference] = []
    for fid in orig_ids & replay_ids:
        o = orig_map[fid]
        r = replay_map[fid]
        if o.get("severity") != r.get("severity"):
            changed.append(
                FindingDifference(
                    finding_id=fid,
                    change_type="severity_changed",
                    original_value={"severity": o.get("severity")},
                    replay_value={"severity": r.get("severity")},
                )
            )
        elif o.get("confidence") != r.get("confidence"):
            changed.append(
                FindingDifference(
                    finding_id=fid,
                    change_type="confidence_changed",
                    original_value={"confidence": o.get("confidence")},
                    replay_value={"confidence": r.get("confidence")},
                )
            )

    return added, removed, changed


# ---------------------------------------------------------------------------
# Replay execution
# ---------------------------------------------------------------------------


def execute_replay(
    case_dir: Path,
    source_run_id: str,
    engine_version: str = "1.3.4",
) -> ReplayVerificationRecord:
    """Re-run analysis on a case and compare to a prior run.

    Returns a ReplayVerificationRecord with full diff.
    """
    from goose import __version__
    from goose.forensics.models import AuditAction, AuditEntry

    replay_id = f"RPL-{uuid.uuid4().hex[:8].upper()}"
    replay_run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"

    # 1. Load case.json
    case_json_path = case_dir / "case.json"
    if not case_json_path.exists():
        return _incompatible_record(
            replay_id,
            "",
            source_run_id,
            replay_run_id,
            "Case JSON not found",
        )

    case_data = json.loads(case_json_path.read_text(encoding="utf-8"))
    case_id = case_data.get("case_id", "")

    # 2. Find the source run
    runs = case_data.get("analysis_runs", [])
    source_run = None
    for r in runs:
        if r.get("run_id") == source_run_id:
            source_run = r
            break

    if source_run is None:
        return _incompatible_record(
            replay_id,
            case_id,
            source_run_id,
            replay_run_id,
            f"Source run {source_run_id} not found in case",
        )

    # 3. Load original findings and hypotheses
    analysis_dir = case_dir / "analysis"
    original_findings: list[dict[str, Any]] = []
    original_hypotheses: list[dict[str, Any]] = []
    original_parser_confidence: float | None = None

    findings_path = analysis_dir / "findings.json"
    if findings_path.exists():
        try:
            fb = json.loads(findings_path.read_text(encoding="utf-8"))
            if fb.get("run_id") == source_run_id:
                original_findings = fb.get("findings", [])
        except (json.JSONDecodeError, ValueError, KeyError, OSError) as exc:
            logger.debug("Failed to load original findings: %s", exc)

    hyp_path = analysis_dir / "hypotheses.json"
    if hyp_path.exists():
        try:
            hb = json.loads(hyp_path.read_text(encoding="utf-8"))
            if hb.get("run_id") == source_run_id:
                original_hypotheses = hb.get("hypotheses", [])
        except (json.JSONDecodeError, ValueError, KeyError, OSError) as exc:
            logger.debug("Failed to load original hypotheses: %s", exc)

    # Load original parser confidence
    diag_path = analysis_dir / "plugin_diagnostics.json"
    original_plugin_diag: dict[str, Any] = {}
    if diag_path.exists():
        try:
            original_plugin_diag = json.loads(diag_path.read_text(encoding="utf-8"))
            original_parser_confidence = original_plugin_diag.get("parser_confidence")
        except (json.JSONDecodeError, ValueError, KeyError, OSError) as exc:
            logger.debug("Failed to load plugin diagnostics: %s", exc)

    # 4. Check evidence exists for replay
    evidence_items = case_data.get("evidence_items", [])
    if not evidence_items:
        return _incompatible_record(
            replay_id,
            case_id,
            source_run_id,
            replay_run_id,
            "No evidence items in case — cannot replay",
        )

    last_ev = evidence_items[-1]
    ev_path = last_ev.get("stored_path", "")
    if not ev_path or not Path(ev_path).exists():
        return _incompatible_record(
            replay_id,
            case_id,
            source_run_id,
            replay_run_id,
            f"Evidence file not found: {ev_path}",
        )

    # 5. Re-run parse + analysis
    try:
        from goose.parsers.detect import parse_file

        parse_result = parse_file(ev_path)
    except Exception as exc:  # noqa: BLE001
        return _incompatible_record(
            replay_id,
            case_id,
            source_run_id,
            replay_run_id,
            f"Parse failed during replay: {exc}",
        )

    if parse_result is None or not parse_result.success:
        return _incompatible_record(
            replay_id,
            case_id,
            source_run_id,
            replay_run_id,
            "Parse did not succeed during replay",
        )

    flight = parse_result.flight

    # Run plugins
    from goose.plugins import PLUGIN_REGISTRY
    from goose.plugins.contract import PluginDiagnostics as PDiag
    from goose.plugins.trust import TrustPolicy, fingerprint_plugin

    plugins = list(PLUGIN_REGISTRY.values())
    replay_forensic_findings: list[Any] = []
    replay_plugin_versions: dict[str, str] = {}
    replay_plugin_diagnostics: list[PDiag] = []

    trust_policy = TrustPolicy()
    for plugin in plugins:
        replay_plugin_versions[plugin.name] = getattr(plugin, "version", "unknown")
        fp = fingerprint_plugin(plugin)
        allowed, reason = trust_policy.evaluate(plugin.manifest, fp)
        if not allowed:
            replay_plugin_diagnostics.append(
                PDiag(
                    plugin_id=plugin.manifest.plugin_id,
                    plugin_version=plugin.manifest.version,
                    run_id=replay_run_id,
                    executed=False,
                    blocked=True,
                    block_reason=reason,
                    trust_state=plugin.manifest.trust_state.value,
                )
            )
            continue
        try:
            ff_list, p_diag = plugin.forensic_analyze(
                flight,
                last_ev.get("evidence_id", ""),
                replay_run_id,
                {},
                parse_result.diagnostics,
            )
            replay_forensic_findings.extend(ff_list)
            replay_plugin_diagnostics.append(p_diag)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Replay plugin %s failed: %s", plugin.manifest.plugin_id, exc)

    # Generate replay hypotheses
    from goose.forensics.lifting import generate_hypotheses

    replay_hypotheses = generate_hypotheses(replay_forensic_findings, run_id=replay_run_id)

    # 6. Compare outputs
    replay_findings_dicts = [f.to_dict() for f in replay_forensic_findings]
    replay_hyp_dicts = [h.to_dict() for h in replay_hypotheses]

    added, removed, changed = _diff_findings(original_findings, replay_findings_dicts)

    # Plugin execution changes
    orig_plugin_vers = source_run.get("plugin_versions", {})
    plugin_exec_changes: list[str] = []
    for pid in set(list(orig_plugin_vers.keys()) + list(replay_plugin_versions.keys())):
        ov = orig_plugin_vers.get(pid)
        rv = replay_plugin_versions.get(pid)
        if ov != rv:
            plugin_exec_changes.append(pid)

    # Parser confidence delta
    replay_parser_confidence = parse_result.diagnostics.parser_confidence
    confidence_delta: float | None = None
    if original_parser_confidence is not None and replay_parser_confidence is not None:
        confidence_delta = replay_parser_confidence - original_parser_confidence

    # Determine drift categories
    drift_cats: list[DriftCategory] = []
    orig_engine = source_run.get("engine_version", "")
    if orig_engine and orig_engine != __version__:
        drift_cats.append(DriftCategory.ENGINE_VERSION)
    if plugin_exec_changes:
        drift_cats.append(DriftCategory.PLUGIN_VERSION)
    if added or removed:
        drift_cats.append(DriftCategory.FINDINGS_CHANGED)
    if confidence_delta is not None and abs(confidence_delta) > 0.01:
        drift_cats.append(DriftCategory.CONFIDENCE_SHIFTED)

    # Original parser info
    orig_parser_version = ""
    prov_path = case_dir / "parsed" / "provenance.json"
    if prov_path.exists():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            orig_parser_version = prov.get("parser_version", "")
        except (json.JSONDecodeError, ValueError, KeyError, OSError) as exc:
            logger.debug("Failed to load provenance: %s", exc)

    replay_parser_version = ""
    if parse_result.provenance:
        replay_parser_version = parse_result.provenance.parser_version

    if orig_parser_version and replay_parser_version and orig_parser_version != replay_parser_version:
        drift_cats.append(DriftCategory.PARSER_VERSION)

    # Resolve human-readable titles for added/removed findings
    def _get_title(finding_id: str, findings_list: list[dict[str, Any]]) -> str:
        for f in findings_list:
            if f.get("finding_id", f.get("title")) == finding_id:
                return f.get("title", finding_id)
        return finding_id

    finding_titles_added = [_get_title(fid, replay_findings_dicts) for fid in added]
    finding_titles_removed = [_get_title(fid, original_findings) for fid in removed]

    diff_summary = ReplayDifferenceSummary(
        findings_added=added,
        findings_removed=removed,
        findings_changed=changed,
        finding_titles_added=finding_titles_added,
        finding_titles_removed=finding_titles_removed,
        hypotheses_added=max(0, len(replay_hyp_dicts) - len(original_hypotheses)),
        hypotheses_removed=max(0, len(original_hypotheses) - len(replay_hyp_dicts)),
        parser_confidence_delta=confidence_delta,
        plugin_execution_changes=plugin_exec_changes,
        drift_categories=drift_cats,
    )

    # 7. Determine status
    # drift_cats is a list — convert to set before intersection to avoid TypeError
    has_version_drift = bool(
        set(drift_cats)
        & {
            DriftCategory.ENGINE_VERSION,
            DriftCategory.PARSER_VERSION,
            DriftCategory.PLUGIN_VERSION,
            DriftCategory.TUNING_PROFILE,
        }
    )
    has_output_drift = bool(added or removed or changed)

    if not has_version_drift and not has_output_drift:
        status = ReplayStatus.EXACT_MATCH
    elif has_version_drift:
        status = ReplayStatus.EXPECTED_DRIFT
    else:
        status = ReplayStatus.UNEXPECTED_DRIFT

    record = ReplayVerificationRecord(
        replay_id=replay_id,
        source_case_id=case_id,
        source_run_id=source_run_id,
        replay_run_id=replay_run_id,
        status=status,
        original_engine_version=orig_engine,
        replay_engine_version=__version__,
        original_parser_version=orig_parser_version,
        replay_parser_version=replay_parser_version,
        original_plugin_versions=orig_plugin_vers,
        replay_plugin_versions=replay_plugin_versions,
        original_tuning_profile=source_run.get("tuning_profile") or "default",
        replay_tuning_profile="default",
        difference_summary=diff_summary,
        verified_at=datetime.now().isoformat(),
    )

    # 8. Persist replay record
    exports_dir = case_dir / "exports"
    exports_dir.mkdir(exist_ok=True)
    replay_path = exports_dir / f"replay_{replay_id}.json"
    replay_path.write_text(
        json.dumps(record.to_dict(), indent=2),
        encoding="utf-8",
    )

    # 9. Audit entry
    try:
        audit_path = case_dir / "audit" / "audit_log.jsonl"
        entry = AuditEntry(
            event_id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            timestamp=datetime.now(),
            actor="system",
            action=AuditAction.ANALYSIS_COMPLETED,
            object_type="replay",
            object_id=replay_id,
            details={
                "source_run_id": source_run_id,
                "replay_run_id": replay_run_id,
                "status": status.value,
            },
        )
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(entry.to_jsonl() + "\n")
    except OSError as exc:
        logger.debug("Best-effort audit write failed: %s", exc)

    return record


def _incompatible_record(
    replay_id: str,
    case_id: str,
    source_run_id: str,
    replay_run_id: str,
    reason: str,
) -> ReplayVerificationRecord:
    """Return an INCOMPATIBLE record with an explanation."""
    return ReplayVerificationRecord(
        replay_id=replay_id,
        source_case_id=case_id,
        source_run_id=source_run_id,
        replay_run_id=replay_run_id,
        status=ReplayStatus.INCOMPATIBLE,
        original_engine_version="",
        replay_engine_version="",
        original_parser_version="",
        replay_parser_version="",
        original_plugin_versions={},
        replay_plugin_versions={},
        original_tuning_profile="",
        replay_tuning_profile="",
        difference_summary=ReplayDifferenceSummary(
            drift_categories=[DriftCategory.EVIDENCE_MISSING],
        ),
        verified_at=datetime.now().isoformat(),
        notes=reason,
    )
