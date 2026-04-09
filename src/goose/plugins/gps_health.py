"""GPS health analysis plugin — validates satellite count, HDOP, position jumps, and dropouts."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState

# Thresholds
MIN_SATELLITES = 8          # below this is degraded GPS
MAX_HDOP = 2.0              # above this is poor horizontal accuracy
POSITION_JUMP_METERS = 5.0  # max plausible movement between consecutive samples (m)
DROPOUT_GAP_SEC = 2.0       # gap longer than this = GPS dropout


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two lat/lon points."""
    R = 6_371_000.0  # Earth radius in metres
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return float(2 * R * np.arcsin(np.sqrt(a)))


class GPSHealthPlugin(Plugin):
    """Validate GPS signal quality throughout a flight."""

    name = "gps_health"
    description = (
        "Checks satellite count, HDOP, position jump anomalies, and GPS dropout intervals"
    )
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="gps_health",
        name="GPS Health",
        version="1.0.0",
        author="Goose Flight",
        description="Checks satellite count, HDOP, position jump anomalies, and GPS dropout intervals",
        category=PluginCategory.NAVIGATION,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=["gps"],
        optional_streams=[],
        output_finding_types=["satellite_count", "hdop", "position_jump", "gps_dropout"],
    )

    DEFAULT_MIN_SATELLITES = MIN_SATELLITES
    DEFAULT_MAX_HDOP = MAX_HDOP
    DEFAULT_POSITION_JUMP_METERS = POSITION_JUMP_METERS
    DEFAULT_DROPOUT_GAP_SEC = DROPOUT_GAP_SEC

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run GPS health checks. Returns findings for each check category."""
        findings: list[Finding] = []
        cfg = config or {}
        min_sats = int(cfg.get("min_satellites", MIN_SATELLITES))
        max_hdop = float(cfg.get("max_hdop", MAX_HDOP))
        jump_m = float(cfg.get("position_jump_meters", POSITION_JUMP_METERS))
        dropout_sec = float(cfg.get("dropout_gap_sec", DROPOUT_GAP_SEC))

        if flight.gps is None or flight.gps.empty:
            findings.append(Finding(
                plugin_name=self.name,
                title="No GPS data available",
                severity="info",
                score=50,
                description="No GPS data found in the flight log. GPS health checks skipped.",
            ))
            return findings

        gps = flight.gps.copy()

        # Require at minimum a timestamp column
        if "timestamp" not in gps.columns:
            findings.append(Finding(
                plugin_name=self.name,
                title="GPS data missing timestamp column",
                severity="info",
                score=50,
                description="GPS DataFrame present but has no 'timestamp' column.",
            ))
            return findings

        findings.extend(self._check_satellites(gps, min_sats))
        findings.extend(self._check_hdop(gps, max_hdop))
        findings.extend(self._check_position_jumps(gps, jump_m))
        findings.extend(self._check_dropouts(gps, dropout_sec))

        return findings

    # ------------------------------------------------------------------
    # Satellite count
    # ------------------------------------------------------------------

    def _check_satellites(self, gps: pd.DataFrame, MIN_SATELLITES: int = MIN_SATELLITES) -> list[Finding]:
        """Check that satellite count stays at or above the minimum threshold."""
        if "satellites" not in gps.columns:
            return []

        sats = gps["satellites"].dropna()
        if sats.empty:
            return []

        below_mask = sats < MIN_SATELLITES
        n_below = int(below_mask.sum())
        pct_below = n_below / len(sats) * 100
        min_sats = int(sats.min())
        mean_sats = round(float(sats.mean()), 1)

        if n_below == 0:
            return [Finding(
                plugin_name=self.name,
                title="Satellite count nominal",
                severity="pass",
                score=95,
                description=(
                    f"Satellite count remained at or above {MIN_SATELLITES} throughout the flight. "
                    f"Mean: {mean_sats}, minimum: {min_sats}."
                ),
                evidence={"min_satellites": min_sats, "mean_satellites": mean_sats,
                          "threshold": MIN_SATELLITES},
            )]

        # Find the worst timestamp window
        ts = gps["timestamp"]
        low_sat_idx = gps.index[gps["satellites"] < MIN_SATELLITES]
        ts_start = float(ts.loc[low_sat_idx[0]]) if len(low_sat_idx) else None
        ts_end = float(ts.loc[low_sat_idx[-1]]) if len(low_sat_idx) else None

        severity = "critical" if pct_below > 20 else "warning"
        score = 20 if pct_below > 20 else 55

        return [Finding(
            plugin_name=self.name,
            title=f"Low satellite count — below {MIN_SATELLITES} for {pct_below:.1f}% of flight",
            severity=severity,
            score=score,
            description=(
                f"Satellite count dropped below the minimum of {MIN_SATELLITES} "
                f"in {n_below} samples ({pct_below:.1f}% of GPS data). "
                f"Minimum observed: {min_sats}. Poor satellite coverage degrades position accuracy."
            ),
            evidence={
                "threshold": MIN_SATELLITES,
                "min_satellites": min_sats,
                "mean_satellites": mean_sats,
                "samples_below_threshold": n_below,
                "percent_below": round(pct_below, 2),
            },
            timestamp_start=ts_start,
            timestamp_end=ts_end,
        )]

    # ------------------------------------------------------------------
    # HDOP
    # ------------------------------------------------------------------

    def _check_hdop(self, gps: pd.DataFrame, MAX_HDOP: float = MAX_HDOP) -> list[Finding]:
        """Check horizontal dilution of precision stays below the threshold."""
        if "hdop" not in gps.columns:
            return []

        hdop = gps["hdop"].dropna()
        if hdop.empty:
            return []

        above_mask = hdop > MAX_HDOP
        n_above = int(above_mask.sum())
        pct_above = n_above / len(hdop) * 100
        max_hdop = round(float(hdop.max()), 3)
        mean_hdop = round(float(hdop.mean()), 3)

        if n_above == 0:
            return [Finding(
                plugin_name=self.name,
                title="HDOP within acceptable range",
                severity="pass",
                score=95,
                description=(
                    f"HDOP remained below {MAX_HDOP} throughout the flight. "
                    f"Mean HDOP: {mean_hdop}, peak: {max_hdop}."
                ),
                evidence={"max_hdop": max_hdop, "mean_hdop": mean_hdop,
                          "threshold": MAX_HDOP},
            )]

        ts = gps["timestamp"]
        high_hdop_idx = gps.index[gps["hdop"] > MAX_HDOP]
        ts_start = float(ts.loc[high_hdop_idx[0]]) if len(high_hdop_idx) else None
        ts_end = float(ts.loc[high_hdop_idx[-1]]) if len(high_hdop_idx) else None

        severity = "critical" if pct_above > 25 or max_hdop > 5.0 else "warning"
        score = 25 if severity == "critical" else 55

        return [Finding(
            plugin_name=self.name,
            title=f"Elevated HDOP — exceeded {MAX_HDOP} for {pct_above:.1f}% of flight",
            severity=severity,
            score=score,
            description=(
                f"HDOP exceeded the maximum acceptable value of {MAX_HDOP} "
                f"in {n_above} samples ({pct_above:.1f}% of GPS data). "
                f"Peak HDOP: {max_hdop}. High HDOP indicates poor horizontal position accuracy."
            ),
            evidence={
                "threshold": MAX_HDOP,
                "max_hdop": max_hdop,
                "mean_hdop": mean_hdop,
                "samples_above_threshold": n_above,
                "percent_above": round(pct_above, 2),
            },
            timestamp_start=ts_start,
            timestamp_end=ts_end,
        )]

    # ------------------------------------------------------------------
    # Position jumps
    # ------------------------------------------------------------------

    def _check_position_jumps(
        self, gps: pd.DataFrame, POSITION_JUMP_METERS: float = POSITION_JUMP_METERS
    ) -> list[Finding]:
        """Detect unrealistically large position jumps between consecutive GPS samples."""
        if "lat" not in gps.columns or "lon" not in gps.columns:
            return []

        df = gps[["timestamp", "lat", "lon"]].dropna()
        if len(df) < 2:
            return []

        distances: list[float] = []
        for i in range(1, len(df)):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]
            d = _haversine_m(prev["lat"], prev["lon"], curr["lat"], curr["lon"])
            distances.append(d)

        dist_series = pd.Series(distances)
        jump_mask = dist_series > POSITION_JUMP_METERS
        n_jumps = int(jump_mask.sum())

        if n_jumps == 0:
            return [Finding(
                plugin_name=self.name,
                title="No GPS position jumps detected",
                severity="pass",
                score=95,
                description=(
                    f"All consecutive GPS samples are within {POSITION_JUMP_METERS}m of each other."
                ),
                evidence={"threshold_m": POSITION_JUMP_METERS,
                          "max_step_m": round(float(dist_series.max()), 2)},
            )]

        jump_indices = dist_series[jump_mask].index
        # Timestamps correspond to the *second* point in each pair (index i)
        ts_values = df["timestamp"].iloc[1:].reset_index(drop=True)
        jump_timestamps = [float(ts_values.iloc[i]) for i in jump_indices]
        max_jump = round(float(dist_series.max()), 2)

        severity = "critical" if n_jumps > 5 or max_jump > 50.0 else "warning"
        score = 15 if severity == "critical" else 50

        return [Finding(
            plugin_name=self.name,
            title=f"GPS position jumps detected — {n_jumps} jump(s) exceeding {POSITION_JUMP_METERS}m",
            severity=severity,
            score=score,
            description=(
                f"Detected {n_jumps} instance(s) where consecutive GPS samples differ by "
                f"more than {POSITION_JUMP_METERS}m. Largest jump: {max_jump}m. "
                "This may indicate multipath interference, signal loss, or log corruption."
            ),
            evidence={
                "threshold_m": POSITION_JUMP_METERS,
                "jump_count": n_jumps,
                "max_jump_m": max_jump,
                "jump_timestamps": jump_timestamps[:20],  # cap evidence payload
            },
            timestamp_start=jump_timestamps[0] if jump_timestamps else None,
            timestamp_end=jump_timestamps[-1] if jump_timestamps else None,
        )]

    # ------------------------------------------------------------------
    # Dropouts
    # ------------------------------------------------------------------

    def _check_dropouts(
        self, gps: pd.DataFrame, DROPOUT_GAP_SEC: float = DROPOUT_GAP_SEC
    ) -> list[Finding]:
        """Detect gaps in GPS data longer than DROPOUT_GAP_SEC seconds."""
        ts = gps["timestamp"].dropna().sort_values().reset_index(drop=True)
        if len(ts) < 2:
            return []

        gaps = ts.diff().dropna()
        dropout_mask = gaps > DROPOUT_GAP_SEC
        n_dropouts = int(dropout_mask.sum())

        if n_dropouts == 0:
            return [Finding(
                plugin_name=self.name,
                title="No GPS dropouts detected",
                severity="pass",
                score=95,
                description=(
                    f"GPS data is continuous with no gaps exceeding {DROPOUT_GAP_SEC}s."
                ),
                evidence={"threshold_sec": DROPOUT_GAP_SEC,
                          "max_gap_sec": round(float(gaps.max()), 3)},
            )]

        dropout_indices = gaps[dropout_mask].index
        dropout_details: list[dict[str, float]] = []
        for idx in dropout_indices:
            gap_start = float(ts.iloc[idx - 1])
            gap_end = float(ts.iloc[idx])
            dropout_details.append({
                "start": round(gap_start, 3),
                "end": round(gap_end, 3),
                "duration_sec": round(gap_end - gap_start, 3),
            })

        max_gap = round(float(max(d["duration_sec"] for d in dropout_details)), 3)
        total_dropout_sec = round(sum(d["duration_sec"] for d in dropout_details), 3)

        severity = "critical" if max_gap > 10.0 or n_dropouts > 10 else "warning"
        score = 20 if severity == "critical" else 50

        return [Finding(
            plugin_name=self.name,
            title=f"GPS dropouts detected — {n_dropouts} gap(s), longest {max_gap}s",
            severity=severity,
            score=score,
            description=(
                f"Found {n_dropouts} GPS data gap(s) longer than {DROPOUT_GAP_SEC}s. "
                f"Longest gap: {max_gap}s. Total dropout time: {total_dropout_sec}s. "
                "During dropouts the autopilot may fall back to dead-reckoning or failsafe."
            ),
            evidence={
                "threshold_sec": DROPOUT_GAP_SEC,
                "dropout_count": n_dropouts,
                "max_gap_sec": max_gap,
                "total_dropout_sec": total_dropout_sec,
                "dropouts": dropout_details[:20],  # cap evidence payload
            },
            timestamp_start=dropout_details[0]["start"] if dropout_details else None,
            timestamp_end=dropout_details[-1]["end"] if dropout_details else None,
        )]
