"""Tests for v11 Strategy Sprint case metadata and attachment model."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.forensics.models import Attachment, AttachmentType, Case
from goose.web import cases_api
from goose.web.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    svc = CaseService(base_dir=tmp_path / "cases")
    cases_api._set_service(svc)
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Case metadata
# ---------------------------------------------------------------------------


class TestCaseMetadata:
    def test_new_fields_default_to_none_or_default(self):
        c = Case(
            case_id="CASE-0001",
            created_at=datetime(2026, 4, 8),
            created_by="test",
        )
        assert c.mission_id is None
        assert c.operator_name is None
        assert c.profile == "default"

    def test_new_fields_serialize(self):
        c = Case(
            case_id="CASE-0001",
            created_at=datetime(2026, 4, 8),
            created_by="test",
            mission_id="M-42",
            platform_name="Alpha",
            profile="gov_mil",
            operator_name="Maverick",
        )
        d = c.to_dict()
        assert d["mission_id"] == "M-42"
        assert d["platform_name"] == "Alpha"
        assert d["profile"] == "gov_mil"
        assert d["operator_name"] == "Maverick"

    def test_roundtrip_preserves_metadata(self):
        c = Case(
            case_id="CASE-0002",
            created_at=datetime(2026, 4, 8),
            created_by="test",
            mission_id="M-99",
            profile="research",
            damage_summary="rotor 3 bent",
        )
        d = c.to_dict()
        restored = Case.from_dict(d)
        assert restored.mission_id == "M-99"
        assert restored.profile == "research"
        assert restored.damage_summary == "rotor 3 bent"

    def test_from_dict_ignores_unknown_keys(self):
        c = Case(
            case_id="CASE-0003",
            created_at=datetime(2026, 4, 8),
            created_by="test",
        )
        d = c.to_dict()
        d["future_field"] = "abc"
        d["another_unknown"] = 99
        restored = Case.from_dict(d)
        assert restored.case_id == "CASE-0003"

    def test_legacy_case_without_new_fields_loads(self):
        # Simulate an older case.json that lacks all v11 fields
        legacy = {
            "case_id": "CASE-LEGACY",
            "created_at": "2026-01-01T00:00:00",
            "created_by": "cli",
            "status": "open",
            "tags": ["legacy"],
            "notes": "",
            "engine_version": "1.0.0",
            "ruleset_version": None,
            "plugin_policy_version": None,
            "evidence_items": [],
            "analysis_runs": [],
            "exports": [],
        }
        c = Case.from_dict(legacy)
        assert c.case_id == "CASE-LEGACY"
        assert c.profile == "default"
        assert c.mission_id is None


# ---------------------------------------------------------------------------
# Case creation API with v11 metadata
# ---------------------------------------------------------------------------


class TestCreateCaseWithMetadata:
    def test_create_with_profile(self, client: TestClient):
        res = client.post(
            "/api/cases",
            json={
                "created_by": "test",
                "profile": "racer",
                "platform_name": "Alpha Quad",
                "recent_changes": "new motors",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["case"]["profile"] == "racer"
        assert data["case"]["platform_name"] == "Alpha Quad"
        assert data["case"]["recent_changes"] == "new motors"

    def test_create_with_gov_mil_metadata(self, client: TestClient):
        res = client.post(
            "/api/cases",
            json={
                "profile": "gov_mil",
                "mission_id": "OP-100",
                "sortie_id": "S-1",
                "unit_name": "RED-1",
                "operator_name": "Goose",
            },
        )
        assert res.status_code == 201
        case = res.json()["case"]
        assert case["profile"] == "gov_mil"
        assert case["mission_id"] == "OP-100"
        assert case["unit_name"] == "RED-1"

    def test_create_without_metadata_still_works(self, client: TestClient):
        res = client.post("/api/cases", json={})
        assert res.status_code == 201
        case = res.json()["case"]
        assert case["profile"] == "default"


# ---------------------------------------------------------------------------
# Attachment dataclass
# ---------------------------------------------------------------------------


class TestAttachmentModel:
    def _make(self, **kwargs):
        defaults = dict(
            attachment_id="ATT-1234ABCD",
            case_id="CASE-0001",
            filename="damage.jpg",
            content_type="image/jpeg",
            size_bytes=1234,
            sha256="a" * 64,
            attachment_type=AttachmentType.PHOTO,
            stored_path="/tmp/x",  # noqa: S108
            uploaded_at="2026-04-08T00:00:00",
        )
        defaults.update(kwargs)
        return Attachment(**defaults)

    def test_to_dict_has_enum_value(self):
        att = self._make()
        d = att.to_dict()
        assert d["attachment_type"] == "photo"

    def test_roundtrip(self):
        att = self._make(notes="wing damage", related_timeline_time=42.5)
        restored = Attachment.from_dict(att.to_dict())
        assert restored.attachment_id == att.attachment_id
        assert restored.attachment_type == AttachmentType.PHOTO
        assert restored.notes == "wing damage"
        assert restored.related_timeline_time == 42.5

    def test_unknown_type_falls_back_to_other(self):
        d = {
            "attachment_id": "ATT-1",
            "case_id": "CASE-1",
            "filename": "x",
            "content_type": "x",
            "size_bytes": 0,
            "sha256": "",
            "attachment_type": "not_a_real_type",
            "stored_path": "",
            "uploaded_at": "2026-04-08T00:00:00",
        }
        att = Attachment.from_dict(d)
        assert att.attachment_type == AttachmentType.OTHER

    def test_from_dict_ignores_unknown_keys(self):
        att = self._make()
        d = att.to_dict()
        d["extra"] = "ignored"
        restored = Attachment.from_dict(d)
        assert restored.attachment_id == att.attachment_id


# ---------------------------------------------------------------------------
# Attachment API
# ---------------------------------------------------------------------------


class TestAttachmentAPI:
    def _create_case(self, client: TestClient) -> str:
        r = client.post("/api/cases", json={})
        return r.json()["case"]["case_id"]

    def test_upload_and_list(self, client: TestClient):
        case_id = self._create_case(client)
        files = {"file": ("photo.jpg", io.BytesIO(b"FAKE_JPEG_BYTES"), "image/jpeg")}
        data = {"attachment_type": "photo", "notes": "front damage"}
        r = client.post(f"/api/cases/{case_id}/attachments", files=files, data=data)
        assert r.status_code == 201
        att = r.json()["attachment"]
        assert att["filename"] == "photo.jpg"
        assert att["attachment_type"] == "photo"

        # List should include it
        r2 = client.get(f"/api/cases/{case_id}/attachments")
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["count"] == 1
        assert data2["attachments"][0]["attachment_id"] == att["attachment_id"]

    def test_get_metadata(self, client: TestClient):
        case_id = self._create_case(client)
        files = {"file": ("note.txt", io.BytesIO(b"hello"), "text/plain")}
        r = client.post(
            f"/api/cases/{case_id}/attachments",
            files=files,
            data={"attachment_type": "note"},
        )
        att_id = r.json()["attachment"]["attachment_id"]
        r2 = client.get(f"/api/cases/{case_id}/attachments/{att_id}")
        assert r2.status_code == 200
        assert r2.json()["attachment"]["attachment_id"] == att_id

    def test_download_file(self, client: TestClient):
        case_id = self._create_case(client)
        payload = b"the actual bytes"
        files = {"file": ("data.bin", io.BytesIO(payload), "application/octet-stream")}
        r = client.post(
            f"/api/cases/{case_id}/attachments",
            files=files,
            data={"attachment_type": "external_data"},
        )
        att_id = r.json()["attachment"]["attachment_id"]
        r2 = client.get(f"/api/cases/{case_id}/attachments/{att_id}/file")
        assert r2.status_code == 200
        assert r2.content == payload

    def test_upload_unknown_case_404(self, client: TestClient):
        files = {"file": ("x.jpg", io.BytesIO(b"xx"), "image/jpeg")}
        r = client.post("/api/cases/NOPE/attachments", files=files, data={})
        assert r.status_code == 404
