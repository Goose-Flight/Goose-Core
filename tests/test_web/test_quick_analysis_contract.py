"""Integration contract test for POST /api/quick-analysis.

Uploads the richest real flight log (rich_flight.ulg) and asserts every
field that the frontend JavaScript reads is present and correctly typed
in the JSON response. This prevents the class of bug where Python model
field names drift from what the SPA expects.

Run with:
    pytest tests/test_web/test_quick_analysis_contract.py -v
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── Test fixture ──────────────────────────────────────────────────────────────

RICH_LOG = Path(__file__).parent.parent / "fixtures" / "rich_flight.ulg"
FALLBACK_LOG = Path(__file__).parent.parent / "fixtures" / "px4_normal_flight.ulg"


def _best_fixture() -> Path:
    if RICH_LOG.exists():
        return RICH_LOG
    if FALLBACK_LOG.exists():
        return FALLBACK_LOG
    pytest.skip("No fixture log file available")


# ── App + auth setup ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("GOOSE_API_TOKEN", "test-token-contract")
    from goose.web.app import create_app
    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="module")
def auth():
    return {"Authorization": "Bearer test-token-contract"}


@pytest.fixture(scope="module")
def qa_response(client, auth):
    """POST the rich fixture log and return the parsed JSON (cached per module)."""
    log_path = _best_fixture()
    log_bytes = log_path.read_bytes()
    resp = client.post(
        "/api/quick-analysis",
        files={"file": (log_path.name, io.BytesIO(log_bytes), "application/octet-stream")},
        data={"profile": "default"},
        headers=auth,
    )
    assert resp.status_code == 200, f"Quick analysis failed: {resp.status_code} {resp.text[:500]}"
    return resp.json()


# ── Top-level shape ───────────────────────────────────────────────────────────

class TestTopLevel:
    def test_ok_flag(self, qa_response):
        assert qa_response.get("ok") is True

    def test_overall_score(self, qa_response):
        score = qa_response.get("overall_score")
        assert isinstance(score, int), f"overall_score should be int, got {type(score)}"
        assert 0 <= score <= 100

    def test_profile_present(self, qa_response):
        p = qa_response.get("profile")
        assert isinstance(p, dict)
        assert "profile_id" in p

    def test_metadata_present(self, qa_response):
        assert "metadata" in qa_response

    def test_summary_present(self, qa_response):
        assert "summary" in qa_response

    def test_findings_list(self, qa_response):
        assert isinstance(qa_response.get("findings"), list)

    def test_hypotheses_list(self, qa_response):
        assert isinstance(qa_response.get("hypotheses"), list)

    def test_signal_quality_list(self, qa_response):
        assert isinstance(qa_response.get("signal_quality"), list)

    def test_timeseries_present(self, qa_response):
        assert isinstance(qa_response.get("timeseries"), dict)


# ── Metadata fields (read by JS as meta.X) ────────────────────────────────────

class TestMetadata:
    REQUIRED = ["filename", "autopilot", "vehicle_type", "firmware_version",
                "duration_sec", "primary_mode", "crashed"]

    def test_required_fields(self, qa_response):
        meta = qa_response["metadata"]
        missing = [f for f in self.REQUIRED if f not in meta]
        assert not missing, f"metadata missing fields: {missing}"

    def test_duration_is_number(self, qa_response):
        assert isinstance(qa_response["metadata"]["duration_sec"], (int, float))

    def test_crashed_is_bool(self, qa_response):
        assert isinstance(qa_response["metadata"]["crashed"], bool)


# ── Summary fields (read by JS as summary.X / bysev.X) ───────────────────────

class TestSummary:
    def test_total_findings(self, qa_response):
        assert "total_findings" in qa_response["summary"]

    def test_by_severity(self, qa_response):
        bysev = qa_response["summary"].get("by_severity", {})
        for key in ("critical", "warning", "info", "pass"):
            assert key in bysev, f"by_severity missing '{key}'"

    def test_plugins_run(self, qa_response):
        assert "plugins_run" in qa_response["summary"]


# ── Signal quality fields (the bug that prompted this test) ───────────────────

class TestSignalQuality:
    # Frontend reads: s.stream_name, s.reliability_estimate, s.row_count, s.notes
    # (Previously broken: was reading s.stream, s.quality_score, s.present)

    def test_has_entries(self, qa_response):
        sigs = qa_response["signal_quality"]
        assert len(sigs) > 0, "Expected at least one signal quality entry"

    def test_stream_name_field(self, qa_response):
        for s in qa_response["signal_quality"]:
            assert "stream_name" in s, f"Missing stream_name in: {s}"
            # Explicitly ensure old wrong name is NOT what we rely on
            assert isinstance(s["stream_name"], str)

    def test_reliability_estimate_field(self, qa_response):
        for s in qa_response["signal_quality"]:
            assert "reliability_estimate" in s, f"Missing reliability_estimate in: {s}"
            val = s["reliability_estimate"]
            assert isinstance(val, (int, float)), f"reliability_estimate not numeric: {val}"
            assert 0.0 <= val <= 1.0, f"reliability_estimate out of range: {val}"

    def test_row_count_field(self, qa_response):
        for s in qa_response["signal_quality"]:
            assert "row_count" in s
            assert isinstance(s["row_count"], int)

    def test_no_old_broken_fields(self, qa_response):
        """Guard against re-introducing the old wrong field names."""
        for s in qa_response["signal_quality"]:
            assert "quality_score" not in s, "Old field 'quality_score' re-introduced"
            # 'stream' is not a field; 'stream_name' is
            # 'present' is not a field in the serialized form


# ── Findings fields (read by JS as f.X) ──────────────────────────────────────

class TestFindings:
    # Canonical ForensicFinding fields
    CANONICAL = ["finding_id", "plugin_id", "title", "severity", "score",
                 "description", "start_time", "end_time", "supporting_metrics",
                 "evidence_references", "phase"]
    # Frontend alias fields (added by ForensicFinding.to_dict for SPA compat)
    ALIASES = ["plugin_name", "timestamp_start", "timestamp_end", "evidence"]

    def test_finding_fields(self, qa_response):
        findings = qa_response["findings"]
        if not findings:
            pytest.skip("No findings in this log — cannot validate shape")
        for f in findings:
            missing = [k for k in self.CANONICAL + self.ALIASES if k not in f]
            assert not missing, f"Finding missing fields {missing}: {f.get('title')}"

    def test_aliases_match_canonical(self, qa_response):
        """Frontend aliases must equal their canonical counterparts."""
        for f in qa_response["findings"]:
            assert f["plugin_name"] == f["plugin_id"]
            assert f["timestamp_start"] == f["start_time"]
            assert f["timestamp_end"] == f["end_time"]
            assert f["evidence"] == f["supporting_metrics"]

    def test_severity_values(self, qa_response):
        valid = {"critical", "warning", "info", "pass"}
        for f in qa_response["findings"]:
            assert f["severity"] in valid, f"Invalid severity: {f['severity']}"

    def test_score_is_int(self, qa_response):
        for f in qa_response["findings"]:
            assert isinstance(f["score"], int), f"score not int: {f['score']}"

    def test_evidence_is_dict(self, qa_response):
        for f in qa_response["findings"]:
            assert isinstance(f["evidence"], dict)
            assert isinstance(f["supporting_metrics"], dict)


# ── Hypotheses fields (read by JS as h.X) ────────────────────────────────────

class TestHypotheses:
    def test_hypothesis_fields(self, qa_response):
        hyps = qa_response["hypotheses"]
        if not hyps:
            pytest.skip("No hypotheses — cannot validate shape")
        for h in hyps:
            assert "statement" in h, f"Hypothesis missing 'statement': {h}"
            assert "confidence" in h, f"Hypothesis missing 'confidence': {h}"

    def test_confidence_range(self, qa_response):
        for h in qa_response["hypotheses"]:
            c = h.get("confidence", 0)
            assert 0.0 <= c <= 1.0, f"confidence out of range: {c}"


# ── Timeseries keys (read by JS as ts.X.timestamps, ts.X.colname) ────────────

class TestTimeseries:
    # These are the keys the frontend _buildQAChart() reads
    EXPECTED_KEYS = [
        "altitude", "attitude", "velocity", "battery", "motors",
        "vibration", "gps", "ekf", "rc", "attitude_rate",
        "mode_changes", "events",
    ]

    def test_mode_changes_is_list(self, qa_response):
        ts = qa_response["timeseries"]
        assert isinstance(ts.get("mode_changes"), list)

    def test_events_is_list(self, qa_response):
        ts = qa_response["timeseries"]
        assert isinstance(ts.get("events"), list)

    def test_present_keys_have_timestamps(self, qa_response):
        ts = qa_response["timeseries"]
        for key in self.EXPECTED_KEYS:
            if key in ts and isinstance(ts[key], dict):
                assert "timestamps" in ts[key], f"ts.{key} missing 'timestamps'"
                assert isinstance(ts[key]["timestamps"], list)

    def test_altitude_columns(self, qa_response):
        ts = qa_response["timeseries"]
        if "altitude" not in ts:
            pytest.skip("No altitude data in this log")
        alt = ts["altitude"]
        assert "timestamps" in alt
        has_alt = "alt_rel" in alt or "alt_msl" in alt
        assert has_alt, f"altitude series has no alt_rel or alt_msl: {list(alt.keys())}"

    def test_attitude_columns(self, qa_response):
        ts = qa_response["timeseries"]
        if "attitude" not in ts:
            pytest.skip("No attitude data in this log")
        att = ts["attitude"]
        for col in ("roll", "pitch", "yaw"):
            assert col in att, f"attitude missing '{col}'"

    def test_velocity_columns(self, qa_response):
        ts = qa_response["timeseries"]
        if "velocity" not in ts:
            pytest.skip("No velocity data in this log")
        vel = ts["velocity"]
        for col in ("vx", "vy", "vz"):
            assert col in vel, f"velocity missing '{col}'"

    def test_battery_columns(self, qa_response):
        ts = qa_response["timeseries"]
        if "battery" not in ts:
            pytest.skip("No battery data in this log")
        bat = ts["battery"]
        assert "voltage" in bat or "remaining_pct" in bat

    def test_no_nan_in_timeseries(self, qa_response):
        """Frontend can't render NaN — backend must replace with null."""
        import math
        ts = qa_response["timeseries"]
        failures = []
        for key, series in ts.items():
            if not isinstance(series, dict):
                continue
            for col, vals in series.items():
                if not isinstance(vals, list):
                    continue
                for i, v in enumerate(vals):
                    if isinstance(v, float) and math.isnan(v):
                        failures.append(f"ts.{key}.{col}[{i}] is NaN")
        assert not failures, "NaN values found (should be null):\n" + "\n".join(failures[:10])


# ── Flight path shape ─────────────────────────────────────────────────────────

class TestFlightPath:
    def test_flight_path_shape(self, qa_response):
        fp = qa_response.get("flight_path")
        if fp is None:
            pytest.skip("No GPS data in this log")
        for key in ("lat", "lon", "alt", "point_count"):
            assert key in fp, f"flight_path missing '{key}'"
        assert len(fp["lat"]) == len(fp["lon"]) == len(fp["alt"])
        assert fp["point_count"] == len(fp["lat"])
