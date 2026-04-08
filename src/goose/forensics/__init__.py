"""Goose forensic case subsystem.

Provides the foundational types and services for case-oriented flight investigation:
- Case, EvidenceItem, EvidenceManifest, Provenance, AuditEntry models  (Sprint 1)
- CaseService for case lifecycle management and immutable evidence ingest  (Sprint 1)
- Hashing utilities (SHA-256 / SHA-512)  (Sprint 1)
- Canonical forensic models: ForensicFinding, EvidenceReference,          (Sprint 4)
  Hypothesis, SignalQuality, and supporting enums
- Lifting layer: promotes thin plugin findings to forensic-grade artifacts  (Sprint 4)
"""

from goose.forensics.canonical import (
    ConfidenceBand,
    EvidenceReference,
    FindingSeverity,
    ForensicFinding,
    Hypothesis,
    HypothesisStatus,
    SignalQuality,
)
from goose.forensics.case_service import CaseService
from goose.forensics.hashing import hash_file, sha256_file, sha512_file, verify_sha256
from goose.forensics.lifting import (
    build_signal_quality,
    generate_hypotheses,
    lift_findings,
)
from goose.forensics.models import (
    AuditAction,
    AuditEntry,
    AnalysisRun,
    Case,
    CaseExport,
    CaseStatus,
    EvidenceItem,
    EvidenceManifest,
    Provenance,
)

__all__ = [
    # Sprint 1
    "CaseService",
    "hash_file",
    "sha256_file",
    "sha512_file",
    "verify_sha256",
    "AuditAction",
    "AuditEntry",
    "AnalysisRun",
    "Case",
    "CaseExport",
    "CaseStatus",
    "EvidenceItem",
    "EvidenceManifest",
    "Provenance",
    # Sprint 4 — canonical models
    "ConfidenceBand",
    "EvidenceReference",
    "FindingSeverity",
    "ForensicFinding",
    "Hypothesis",
    "HypothesisStatus",
    "SignalQuality",
    # Sprint 4 — lifting
    "build_signal_quality",
    "generate_hypotheses",
    "lift_findings",
]
