"""CaseService — manages case directories, evidence ingest, and audit trail.

Responsibilities:
- case creation and persistence
- immutable evidence ingest (copy + hash + manifest + audit)
- case loading and listing

Sprint 1 — Case & Evidence Foundation
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import uuid
from datetime import datetime
from pathlib import Path

from goose import __version__
from goose.forensics.hashing import hash_file, verify_sha256
from goose.forensics.models import (
    AuditAction,
    AuditEntry,
    Case,
    CaseStatus,
    EvidenceItem,
    EvidenceManifest,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(tz=None).replace(microsecond=0)


def _new_id() -> str:
    return uuid.uuid4().hex[:8].upper()


def _sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filenames, collapse whitespace to underscores."""
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:200]


class CaseService:
    """Manages forensic cases stored on the local filesystem.

    All cases are stored under `base_dir/cases/`.
    Each case has its own directory named by case_id.
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path.cwd() / "cases"
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Case management
    # ------------------------------------------------------------------

    def create_case(
        self,
        created_by: str = "cli",
        tags: list[str] | None = None,
        notes: str = "",
    ) -> Case:
        """Create a new case, set up directory structure, write audit entry.

        Returns the new Case with case_id assigned.
        """
        case_id = self._next_case_id()
        case_dir = self.base_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=False)

        # Create sub-directories
        (case_dir / "evidence").mkdir()
        (case_dir / "manifests").mkdir()
        (case_dir / "parsed").mkdir()
        (case_dir / "analysis").mkdir()
        (case_dir / "audit").mkdir()
        (case_dir / "exports").mkdir()

        case = Case(
            case_id=case_id,
            created_at=_utcnow(),
            created_by=created_by,
            status=CaseStatus.OPEN,
            tags=list(tags or []),
            notes=notes,
            engine_version=__version__,
        )

        self._save_case(case)
        self._append_audit(
            case_id,
            AuditEntry(
                event_id=_new_id(),
                timestamp=_utcnow(),
                actor=created_by,
                action=AuditAction.CASE_CREATED,
                object_type="case",
                object_id=case_id,
                details={"tags": case.tags, "notes": notes},
            ),
        )

        return case

    # Accepts both legacy sequential IDs (CASE-2026-000001) and new random-hex IDs
    # (CASE-2026-A3F7C912).  Both formats are validated before any filesystem use.
    _CASE_ID_RE: re.Pattern = re.compile(r"^CASE-\d{4}-(?:\d{6}|[0-9A-F]{8})$")

    @classmethod
    def _check_case_id(cls, case_id: str) -> None:
        """Raise ValueError if case_id fails the allowlist regex.

        This is the first line of defence against path-traversal: an ID like
        ``../../etc/passwd`` or ``CASE-2026-000001/../../evil`` will not match
        the pattern and is rejected before any filesystem path is constructed.
        """
        if not cls._CASE_ID_RE.match(case_id):
            raise ValueError(f"Invalid case_id format: {case_id!r}")

    def _safe_case_path(self, case_id: str) -> Path:
        """Return the resolved case directory path, verifying it stays inside base_dir."""
        self._check_case_id(case_id)
        resolved = (self.base_dir / case_id).resolve()
        if not resolved.is_relative_to(self.base_dir.resolve()):
            raise ValueError(f"case_id {case_id!r} resolves outside base directory")
        return resolved

    def get_case(self, case_id: str) -> Case:
        """Load a case from disk by case_id.

        Raises FileNotFoundError if case does not exist or case_id format is
        invalid (an invalid format ID can never correspond to an existing case).
        """
        try:
            self._check_case_id(case_id)
        except ValueError as exc:
            raise FileNotFoundError(f"Case not found: {case_id}") from exc
        case_json = self.base_dir / case_id / "case.json"
        if not case_json.exists():
            raise FileNotFoundError(f"Case not found: {case_id}")
        return Case.from_json(case_json.read_text(encoding="utf-8"))

    def list_cases(self) -> list[Case]:
        """Return all cases sorted by creation time (newest first)."""
        cases: list[Case] = []
        for case_dir in sorted(self.base_dir.iterdir()):
            if not case_dir.is_dir():
                continue
            case_json = case_dir / "case.json"
            if not case_json.exists():
                continue
            try:
                cases.append(Case.from_json(case_json.read_text(encoding="utf-8")))
            except (ValueError, KeyError, OSError) as exc:
                logger.warning("Skipping corrupt case dir %s: %s", case_dir.name, exc)
        return sorted(cases, key=lambda c: c.created_at, reverse=True)

    def save_case(self, case: Case) -> None:
        """Persist a case to disk (updates case.json)."""
        self._save_case(case)

    def update_status(self, case_id: str, status: CaseStatus, actor: str = "system") -> Case:
        """Change a case's status and persist it."""
        case = self.get_case(case_id)
        old_status = case.status
        case.status = status
        self._save_case(case)
        self._append_audit(
            case_id,
            AuditEntry(
                event_id=_new_id(),
                timestamp=_utcnow(),
                actor=actor,
                action=AuditAction.CASE_STATUS_CHANGED,
                object_type="case",
                object_id=case_id,
                details={"from": old_status.value, "to": status.value},
            ),
        )
        return case

    # ------------------------------------------------------------------
    # Evidence ingest
    # ------------------------------------------------------------------

    def ingest_evidence(
        self,
        case_id: str,
        source_path: str | Path,
        acquired_by: str = "cli",
        notes: str = "",
    ) -> EvidenceItem:
        """Copy a file into the case as immutable evidence.

        Steps:
        1. Assign evidence ID
        2. Copy file to case/evidence/ directory
        3. Set stored copy to read-only
        4. Hash the stored copy (SHA-256 + SHA-512)
        5. Build EvidenceItem
        6. Update EvidenceManifest
        7. Update case.json
        8. Write AuditEntry

        The original source file is NOT modified.
        """
        case = self.get_case(case_id)
        source = Path(source_path)

        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        evidence_id = self._next_evidence_id(case)
        safe_name = _sanitize_filename(source.name)
        stored_name = f"{evidence_id}-{safe_name}"
        dest = self.base_dir / case_id / "evidence" / stored_name

        # Copy — do not modify source
        shutil.copy2(str(source), str(dest))

        # Make stored copy read-only immediately
        self._make_readonly(dest)

        # Hash the stored copy
        sha256, sha512 = hash_file(dest)

        ev = EvidenceItem(
            evidence_id=evidence_id,
            filename=source.name,
            content_type=self._detect_content_type(source),
            size_bytes=dest.stat().st_size,
            sha256=sha256,
            sha512=sha512,
            source_acquisition_mode="local_copy",
            source_reference=str(source.resolve()),
            stored_path=str(dest.resolve()),
            acquired_at=_utcnow(),
            acquired_by=acquired_by,
            immutable=True,
            notes=notes,
        )

        # Update case
        case.evidence_items.append(ev)
        self._save_case(case)

        # Update manifest
        self._write_manifest(case)

        # Audit
        self._append_audit(
            case_id,
            AuditEntry(
                event_id=_new_id(),
                timestamp=_utcnow(),
                actor=acquired_by,
                action=AuditAction.EVIDENCE_INGESTED,
                object_type="evidence",
                object_id=evidence_id,
                details={
                    "case_id": case_id,
                    "filename": source.name,
                    "size_bytes": ev.size_bytes,
                    "sha256": sha256,
                    "stored_path": str(dest),
                },
            ),
        )

        return ev

    def ingest_evidence_bytes(
        self,
        case_id: str,
        filename: str,
        content: bytes,
        acquired_by: str = "gui",
        notes: str = "",
    ) -> EvidenceItem:
        """Ingest evidence from raw bytes (for web upload flow).

        Writes bytes to a temp location, then calls ingest_evidence.
        The temp file is cleaned up after ingest.
        """
        import tempfile

        safe = _sanitize_filename(filename)
        suffix = Path(filename).suffix or ".bin"

        with tempfile.NamedTemporaryFile(suffix=suffix, prefix="goose_ingest_", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            ev = self.ingest_evidence(
                case_id,
                tmp_path,
                acquired_by=acquired_by,
                notes=notes,
            )
            # Overwrite filename with the sanitized original name (not temp name)
            ev = EvidenceItem(
                evidence_id=ev.evidence_id,
                filename=safe,
                content_type=ev.content_type,
                size_bytes=ev.size_bytes,
                sha256=ev.sha256,
                sha512=ev.sha512,
                source_acquisition_mode="upload",
                source_reference=None,
                stored_path=ev.stored_path,
                acquired_at=ev.acquired_at,
                acquired_by=acquired_by,
                immutable=True,
                notes=notes,
            )
            # Update case with corrected EvidenceItem
            case = self.get_case(case_id)
            case.evidence_items[-1] = ev
            self._save_case(case)
            self._write_manifest(case)
            return ev
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def verify_evidence(self, case_id: str, evidence_id: str) -> bool:
        """Verify that stored evidence still matches its recorded SHA-256.

        Returns True if intact, False if tampered or missing.
        """
        case = self.get_case(case_id)
        ev = next((e for e in case.evidence_items if e.evidence_id == evidence_id), None)
        if ev is None:
            return False
        return verify_sha256(ev.stored_path, ev.sha256)

    def get_audit_log(self, case_id: str) -> list[AuditEntry]:
        """Return all audit entries for a case (oldest first)."""
        audit_path = self.base_dir / case_id / "audit" / "audit_log.jsonl"
        if not audit_path.exists():
            return []
        entries: list[AuditEntry] = []
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(AuditEntry.from_dict(json.loads(line)))
                except (json.JSONDecodeError, ValueError, KeyError) as exc:
                    logger.warning("Malformed audit entry in %s: %s", audit_path, exc)
        return entries

    def case_dir(self, case_id: str) -> Path:
        """Return the root directory for a case (path-traversal safe)."""
        return self._safe_case_path(case_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _save_case(self, case: Case) -> None:
        path = self.base_dir / case.case_id / "case.json"
        path.write_text(case.to_json(), encoding="utf-8")

    def _write_manifest(self, case: Case) -> None:
        manifest = EvidenceManifest(
            case_id=case.case_id,
            generated_at=_utcnow(),
            evidence=list(case.evidence_items),
        )
        path = self.base_dir / case.case_id / "manifests" / "evidence_manifest.json"
        path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    def _append_audit(self, case_id: str, entry: AuditEntry) -> None:
        path = self.base_dir / case_id / "audit" / "audit_log.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.to_jsonl() + "\n")

    def _next_case_id(self) -> str:
        """Generate a non-enumerable case ID.

        Format: CASE-YYYY-XXXXXXXX where XXXXXXXX is 8 random hex chars.
        This makes case directories non-guessable (M-3), while keeping the
        CASE-YYYY- prefix for human readability and the regex allowlist.
        Old CASE-YYYY-NNNNNN sequential IDs are still accepted by the validator.
        """
        import secrets

        year = datetime.now().year
        rnd = secrets.token_hex(4).upper()  # 8 random hex chars
        candidate = f"CASE-{year}-{rnd}"
        # Extremely unlikely collision, but guard anyway
        while (self.base_dir / candidate).exists():
            rnd = secrets.token_hex(4).upper()
            candidate = f"CASE-{year}-{rnd}"
        return candidate

    def _next_evidence_id(self, case: Case) -> str:
        return f"EV-{len(case.evidence_items) + 1:04d}"

    @staticmethod
    def _make_readonly(path: Path) -> None:
        """Remove write permissions from a file."""
        current = stat.S_IMODE(path.stat().st_mode)
        path.chmod(current & ~(stat.S_IWRITE | stat.S_IWGRP | stat.S_IWOTH))

    @staticmethod
    def _detect_content_type(path: Path) -> str:
        ext_map = {
            ".ulg": "application/x-ulog",
            ".bin": "application/octet-stream",
            ".log": "text/plain",
            ".tlog": "application/x-tlog",
            ".csv": "text/csv",
            ".json": "application/json",
        }
        return ext_map.get(path.suffix.lower(), "application/octet-stream")
