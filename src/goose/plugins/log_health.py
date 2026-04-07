"""Log health analysis plugin — checks log file integrity and data quality."""

from __future__ import annotations

from typing import Any

import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin

# Streams to inspect
KEY_STREAMS = ["position", "attitude", "battery", "gps", "motors"]

# Threshold for detecting a data dropout (seconds)
DROPOUT_GAP_SEC = 1.0

# Minimum acceptable data rate (samples/second) for key streams
MIN_DATA_RATE_HZ = 1.0

# Tolerance for log duration mismatch (seconds)
DURATION_TOLERANCE_SEC = 5.0


class LogHealthPlugin(Plugin):
    """Check log file integrity and data quality."""

    name = "log_health"
    description = "Log file integrity and data quality"
    version = "1.0.0"
    min_mode = "manual"

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        findings: list[Finding] = []

        findings.extend(self._check_missing_streams(flight))
        findings.extend(self._check_dropouts(flight))
        findings.extend(self._check_data_rates(flight))
        findings.extend(self._check_duration(flight))

        return findings

    # ------------------------------------------------------------------
    # Missing streams
    # ------------------------------------------------------------------

    def _check_missing_streams(self, flight: Flight) -> list[Finding]:
        """Report any key data streams that are absent or empty."""
        findings: list[Finding] = []
        missing: list[str] = []

        for stream_name in KEY_STREAMS:
            df: pd.DataFrame | None = getattr(flight, stream_name, None)
            if df is None or df.empty:
                missing.append(stream_name)
                findings.append(Finding(
                    plugin_name=self.name,
                    title=f"Missing data stream: {stream_name}",
                    severity="info",
                    score=70,
                    description=(
                        f"The '{stream_name}' data stream is absent or empty in this flight log. "
                        "Some analysis plugins may not be able to run."
                    ),
                    evidence={"missing_stream": stream_name},
                ))

        if not missing:
            findings.append(Finding(
                plugin_name=self.name,
                title="All key data streams present",
                severity="pass",
                score=100,
                description=(
                    f"All {len(KEY_STREAMS)} key data streams are present: "
                    f"{', '.join(KEY_STREAMS)}."
                ),
                evidence={"checked_streams": KEY_STREAMS},
            ))

        return findings

    # ------------------------------------------------------------------
    # Data dropouts
    # ------------------------------------------------------------------

    def _check_dropouts(self, flight: Flight) -> list[Finding]:
        """Detect timestamp gaps larger than DROPOUT_GAP_SEC in each stream."""
        findings: list[Finding] = []

        for stream_name in KEY_STREAMS:
            df: pd.DataFrame | None = getattr(flight, stream_name, None)
            if df is None or df.empty:
                continue
            if "timestamp" not in df.columns:
                continue

            ts = df["timestamp"].dropna().sort_values().reset_index(drop=True)
            if len(ts) < 2:
                continue

            gaps = ts.diff().dropna()
            dropout_mask = gaps > DROPOUT_GAP_SEC
            n_dropouts = int(dropout_mask.sum())

            if n_dropouts == 0:
                continue

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

            severity = "critical" if max_gap > 5.0 or n_dropouts > 10 else "warning"
            score = 20 if severity == "critical" else 55

            findings.append(Finding(
                plugin_name=self.name,
                title=f"Data dropout in '{stream_name}' — {n_dropouts} gap(s), longest {max_gap}s",
                severity=severity,
                score=score,
                description=(
                    f"Found {n_dropouts} data gap(s) longer than {DROPOUT_GAP_SEC}s "
                    f"in the '{stream_name}' stream. "
                    f"Longest gap: {max_gap}s, total dropout time: {total_dropout_sec}s. "
                    "Data dropouts may indicate logging issues or hardware problems."
                ),
                evidence={
                    "stream": stream_name,
                    "dropout_count": n_dropouts,
                    "max_gap_sec": max_gap,
                    "total_dropout_sec": total_dropout_sec,
                    "dropouts": dropout_details[:20],
                },
                timestamp_start=dropout_details[0]["start"] if dropout_details else None,
                timestamp_end=dropout_details[-1]["end"] if dropout_details else None,
            ))

        return findings

    # ------------------------------------------------------------------
    # Data rates
    # ------------------------------------------------------------------

    def _check_data_rates(self, flight: Flight) -> list[Finding]:
        """Check that key streams have acceptable sample rates."""
        findings: list[Finding] = []

        for stream_name in KEY_STREAMS:
            df: pd.DataFrame | None = getattr(flight, stream_name, None)
            if df is None or df.empty:
                continue
            if "timestamp" not in df.columns:
                continue

            ts = df["timestamp"].dropna().sort_values()
            if len(ts) < 2:
                continue

            duration = float(ts.iloc[-1] - ts.iloc[0])
            if duration <= 0:
                continue

            rate_hz = (len(ts) - 1) / duration

            if rate_hz < MIN_DATA_RATE_HZ:
                findings.append(Finding(
                    plugin_name=self.name,
                    title=f"Low data rate for '{stream_name}' — {rate_hz:.2f} Hz",
                    severity="warning",
                    score=60,
                    description=(
                        f"The '{stream_name}' stream has a mean data rate of {rate_hz:.2f} Hz, "
                        f"which is below the minimum acceptable rate of {MIN_DATA_RATE_HZ} Hz. "
                        "Low data rates may degrade analysis quality."
                    ),
                    evidence={
                        "stream": stream_name,
                        "rate_hz": round(rate_hz, 3),
                        "min_rate_hz": MIN_DATA_RATE_HZ,
                        "sample_count": len(ts),
                        "duration_sec": round(duration, 3),
                    },
                ))

        return findings

    # ------------------------------------------------------------------
    # Duration check
    # ------------------------------------------------------------------

    def _check_duration(self, flight: Flight) -> list[Finding]:
        """Verify that data duration matches the metadata duration_sec field."""
        findings: list[Finding] = []
        meta_duration = flight.metadata.duration_sec

        # Measure duration from position or attitude data
        measured_duration: float | None = None
        for stream_name in ("position", "attitude", "gps"):
            df: pd.DataFrame | None = getattr(flight, stream_name, None)
            if df is None or df.empty:
                continue
            if "timestamp" not in df.columns:
                continue
            ts = df["timestamp"].dropna().sort_values()
            if len(ts) >= 2:
                measured_duration = float(ts.iloc[-1] - ts.iloc[0])
                break

        if measured_duration is None:
            findings.append(Finding(
                plugin_name=self.name,
                title="Cannot verify log duration — no timestamp data",
                severity="info",
                score=70,
                description=(
                    "Could not measure actual data duration because no timestamped "
                    "position, attitude, or GPS data is present."
                ),
                evidence={"metadata_duration_sec": meta_duration},
            ))
            return findings

        diff = abs(measured_duration - meta_duration)
        if diff <= DURATION_TOLERANCE_SEC:
            findings.append(Finding(
                plugin_name=self.name,
                title="Log duration consistent with metadata",
                severity="pass",
                score=100,
                description=(
                    f"Measured data duration ({measured_duration:.1f}s) matches "
                    f"metadata duration ({meta_duration:.1f}s) within {DURATION_TOLERANCE_SEC}s."
                ),
                evidence={
                    "metadata_duration_sec": round(meta_duration, 2),
                    "measured_duration_sec": round(measured_duration, 2),
                    "difference_sec": round(diff, 2),
                    "tolerance_sec": DURATION_TOLERANCE_SEC,
                },
            ))
        else:
            severity = "critical" if diff > 30.0 else "warning"
            score = 20 if severity == "critical" else 55
            findings.append(Finding(
                plugin_name=self.name,
                title=f"Log duration mismatch — {diff:.1f}s difference",
                severity=severity,
                score=score,
                description=(
                    f"Measured data duration ({measured_duration:.1f}s) differs from "
                    f"metadata duration ({meta_duration:.1f}s) by {diff:.1f}s. "
                    "This may indicate a truncated log or incorrect metadata."
                ),
                evidence={
                    "metadata_duration_sec": round(meta_duration, 2),
                    "measured_duration_sec": round(measured_duration, 2),
                    "difference_sec": round(diff, 2),
                    "tolerance_sec": DURATION_TOLERANCE_SEC,
                },
            ))

        return findings
