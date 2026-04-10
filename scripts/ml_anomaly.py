#!/usr/bin/env python3
"""Isolation Forest anomaly detector — no labels needed.

Trains on flights with no crash signals (clean baseline).
Scores all logs — high anomaly score = unusual flight worth investigating
even if it didn't trip any specific crash rule.

Usage:
    python scripts/ml_anomaly.py                    # train + score all
    python scripts/ml_anomaly.py --top 20           # show 20 most anomalous
    python scripts/ml_anomaly.py --export out.csv   # export scores
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "stream_results.db"

FEATURE_COLS = [
    "max_roll_deg", "max_pitch_deg",
    "motor_cutoff_frac", "motor_imbalance",
    "alt_drop_rate", "peak_g_last20pct",
    "rate_roll_err_rms", "rate_pitch_err_rms",
    "att_roll_err_rms", "att_pitch_err_rms",
    "vel_err_horiz_rms", "vel_err_vert_rms",
    "batt_v_min", "batt_drop_v",
    "motor_sat_frac", "rc_rssi_min",
    "failsafe_count", "vib_rms_z",
    "gps_hdop_max", "cpu_load_max",
]


def run(db_path: Path, top_n: int, export: str | None) -> None:
    try:
        import pandas as pd
        import numpy as np
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import RobustScaler
    except ImportError as e:
        print(f"Missing: {e}\nRun: pip install scikit-learn pandas")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql("SELECT * FROM analyzed_logs WHERE ok=1", conn)
    conn.close()

    if len(df) < 30:
        print(f"Only {len(df)} logs — need at least 30 to fit anomaly detector.")
        sys.exit(0)

    available = [c for c in FEATURE_COLS if c in df.columns]
    X_all = df[available].fillna(-1)

    # Train on clean baseline (no crash signals, score > 40)
    clean_mask = (df["crash_confidence"] == 0.0) & (df["score"].fillna(0) > 40)
    X_clean = X_all[clean_mask]

    if len(X_clean) < 10:
        print(f"Not enough clean flights ({len(X_clean)}) for baseline. Using all data.")
        X_clean = X_all

    print(f"Training on {len(X_clean)} clean flights, scoring {len(X_all)} total...")

    scaler = RobustScaler()
    X_clean_s = scaler.fit_transform(X_clean)
    X_all_s   = scaler.transform(X_all)

    iso = IsolationForest(n_estimators=200, contamination=0.05, random_state=42, n_jobs=-1)
    iso.fit(X_clean_s)

    scores = iso.decision_function(X_all_s)  # higher = more normal
    anomaly_scores = -scores  # flip: higher = more anomalous, 0-based

    # Normalize to 0-100
    lo, hi = anomaly_scores.min(), anomaly_scores.max()
    if hi > lo:
        norm_scores = ((anomaly_scores - lo) / (hi - lo) * 100).round(1)
    else:
        norm_scores = anomaly_scores * 0

    df["anomaly_score"] = norm_scores

    print(f"\nAnomaly score distribution:")
    print(f"  Mean  : {norm_scores.mean():.1f}")
    print(f"  Median: {norm_scores.median():.1f}")
    print(f"  >70   : {(norm_scores > 70).sum()} logs")
    print(f"  >90   : {(norm_scores > 90).sum()} logs")

    top = df.nlargest(top_n, "anomaly_score")[
        ["log_id", "anomaly_score", "crash_confidence", "score",
         "hardware", "duration_sec", "max_roll_deg", "rate_roll_err_rms"]
    ]
    print(f"\nTop {top_n} most anomalous logs:")
    print(top.to_string(index=False))

    if export:
        df[["log_id", "anomaly_score", "crash_confidence", "score",
            "hardware", "duration_sec"] + available].to_csv(export, index=False)
        print(f"\nExported to {export}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--export", default=None)
    args = p.parse_args()
    run(Path(args.db), args.top, args.export)


if __name__ == "__main__":
    main()
