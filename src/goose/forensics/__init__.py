"""Goose forensic case subsystem.

Provides the foundational types and services for case-oriented flight investigation:
- Case, EvidenceItem, EvidenceManifest, Provenance, AuditEntry models
- CaseService for case lifecycle management and immutable evidence ingest
- Hashing utilities (SHA-256 / SHA-512)

Sprint 1 — Case & Evidence Foundation
"""

from goose.forensics.case_service import CaseService
from goose.forensics.hashing import hash_file, sha256_file, sha512_file, verify_sha256
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
]
