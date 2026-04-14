"""Convergence Sprint 1 — App route regression tests.

Tests the legacy /api/analyze endpoint via actual TestClient,
mirroring the pattern used in test_hardening/test_api_modularization.py.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from goose.web.app import create_app
from goose.web.config import settings


class TestLegacyAnalyzeEndpointViaClient:
    """End-to-end route tests for the removed /api/analyze endpoint."""

    def _make_client(self) -> TestClient:
        app = create_app()
        return TestClient(
            app,
            raise_server_exceptions=False,
            headers={"Authorization": f"Bearer {settings.api_token}"},
        )

    def test_legacy_analyze_endpoint_is_gone(self):
        client = self._make_client()
        response = client.post(
            "/api/analyze",
            files={"file": ("test.ulg", io.BytesIO(b"fake data"), "application/octet-stream")},
        )
        assert response.status_code == 410

    def test_legacy_analyze_body_error_field(self):
        client = self._make_client()
        response = client.post(
            "/api/analyze",
            files={"file": ("test.ulg", io.BytesIO(b"fake data"), "application/octet-stream")},
        )
        body = response.json()
        assert body["error"] == "gone"

    def test_legacy_analyze_body_alternatives_present(self):
        client = self._make_client()
        response = client.post(
            "/api/analyze",
            files={"file": ("test.ulg", io.BytesIO(b"fake data"), "application/octet-stream")},
        )
        body = response.json()
        assert "alternatives" in body
        # Verify the alternatives point to the right new endpoints
        alts = body["alternatives"]
        assert "quick_analysis" in alts
        assert "create_case" in alts

    def test_legacy_analyze_message_mentions_quick_analysis(self):
        """Message should mention the replacement endpoint."""
        client = self._make_client()
        response = client.post(
            "/api/analyze",
            files={"file": ("test.ulg", io.BytesIO(b"fake data"), "application/octet-stream")},
        )
        body = response.json()
        assert "message" in body
        assert "quick-analysis" in body["message"].lower() or "quick_analysis" in body["message"].lower()

    def test_legacy_analyze_consumes_file_without_hanging(self):
        """Endpoint should consume the file upload and return cleanly (no connection errors)."""
        client = self._make_client()
        large_fake_file = io.BytesIO(b"U" * 65536)  # 64 KB fake file
        response = client.post(
            "/api/analyze",
            files={"file": ("big.ulg", large_fake_file, "application/octet-stream")},
        )
        assert response.status_code == 410


class TestQuickAnalysisRouteExists:
    """Smoke tests to confirm the replacement /api/quick-analysis route is registered."""

    def _make_client(self) -> TestClient:
        app = create_app()
        return TestClient(
            app,
            raise_server_exceptions=False,
            headers={"Authorization": f"Bearer {settings.api_token}"},
        )

    def test_quick_analysis_route_registered(self):
        """POST /api/quick-analysis with no file should return 400 or 422, not 404/405."""
        client = self._make_client()
        response = client.post("/api/quick-analysis")
        # Should be 400/422 (bad request — missing file), not 404 (route missing) or 405 (method not allowed)
        assert response.status_code in (400, 422)

    def test_save_as_case_route_registered(self):
        """POST /api/quick-analysis/save-as-case with no file should return 400/422, not 404/405."""
        client = self._make_client()
        response = client.post("/api/quick-analysis/save-as-case")
        assert response.status_code in (400, 422)
