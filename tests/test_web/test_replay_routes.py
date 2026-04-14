"""Tests for replay, run comparison, tuning profile, and validation API routes.

Advanced Forensic Validation Sprint.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_and_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a TestClient with a CaseService rooted in tmp_path."""
    monkeypatch.chdir(tmp_path)

    # Reset the case service so it picks up the new cwd
    from goose.forensics import CaseService
    from goose.web import cases_api

    cases_api._set_service(CaseService(base_dir=tmp_path / "cases"))

    from goose.web.app import create_app
    from goose.web.config import settings

    app = create_app()
    client = TestClient(app, headers={"Authorization": f"Bearer {settings.api_token}"})
    yield client, cases_api.get_service()


def test_get_tuning_profile_route(client_and_service, normal_flight_path: Path):
    client, svc = client_and_service
    case = svc.create_case(created_by="test")
    # Ingest evidence so the case is considered valid
    svc.ingest_evidence(case.case_id, normal_flight_path, acquired_by="test")

    r = client.get(f"/api/cases/{case.case_id}/tuning-profile")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "tuning_profile" in data
    tp = data["tuning_profile"]
    assert tp["profile_id"] == "default"
    assert tp["version"] == "1.0.0"
    assert len(tp["analyzer_configs"]) >= 11


def test_get_tuning_profile_route_404(client_and_service):
    client, _ = client_and_service
    r = client.get("/api/cases/CASE-DOES-NOT-EXIST/tuning-profile")
    assert r.status_code == 404


def test_replay_route_404_on_missing_case(client_and_service):
    client, _ = client_and_service
    r = client.post("/api/cases/CASE-NOPE/runs/RUN-X/replay")
    assert r.status_code == 404


def test_replay_route_404_on_missing_run(client_and_service, normal_flight_path: Path):
    client, svc = client_and_service
    case = svc.create_case(created_by="test")
    svc.ingest_evidence(case.case_id, normal_flight_path, acquired_by="test")
    r = client.post(f"/api/cases/{case.case_id}/runs/RUN-NOPE/replay")
    assert r.status_code == 404


def test_replay_verification_route_returns_none_when_absent(client_and_service, normal_flight_path: Path):
    client, svc = client_and_service
    case = svc.create_case(created_by="test")
    svc.ingest_evidence(case.case_id, normal_flight_path, acquired_by="test")
    r = client.get(f"/api/cases/{case.case_id}/runs/RUN-X/replay-verification")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["replay"] is None


def test_compare_runs_route_same_run(client_and_service, normal_flight_path: Path):
    client, svc = client_and_service
    case = svc.create_case(created_by="test")
    svc.ingest_evidence(case.case_id, normal_flight_path, acquired_by="test")

    r = client.post(
        f"/api/cases/{case.case_id}/compare-runs",
        json={"run_a_id": "RUN-A", "run_b_id": "RUN-A"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "comparison" in data
    assert data["comparison"]["has_differences"] is False


def test_compare_runs_route_404_on_missing_case(client_and_service):
    client, _ = client_and_service
    r = client.post(
        "/api/cases/CASE-NOPE/compare-runs",
        json={"run_a_id": "RUN-A", "run_b_id": "RUN-B"},
    )
    assert r.status_code == 404


def test_validation_results_when_empty(client_and_service):
    client, _ = client_and_service
    r = client.get("/api/validation/results")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True


def test_validation_run_endpoint(client_and_service, monkeypatch: pytest.MonkeyPatch):
    """Run the validation endpoint with a pointer to the seeded corpus."""
    client, _ = client_and_service

    # The validation route resolves corpus from cwd/tests/corpus.
    # The TestClient was created with tmp_path as cwd, which has no corpus,
    # so we monkey-patch the corpus_dir resolver.
    repo_corpus = Path(__file__).parent.parent / "corpus"

    from goose.web.routes import validation as val_mod

    monkeypatch.setattr(val_mod, "_corpus_dir", lambda: repo_corpus)

    r = client.post("/api/validation/run")
    # May take a few seconds due to real parsing
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "summary" in data
    assert data["summary"]["total_cases"] >= 1
    assert "quality_report" in data
