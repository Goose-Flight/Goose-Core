#!/usr/bin/env python3
"""Compute fleet-wide percentile benchmarks from stream_results.db.

Outputs a JSON file of percentile breakpoints per feature, segmented by
vehicle_type and hardware.  The Goose API can load this to tell users
"your motor imbalance is 94th percentile for quadcopters."

Usage:
    python scripts/ml_percentiles.py                        # compute + save
    python scripts/ml_percentiles.py --query log_id=abc123  # score one log
    python scripts/ml_percentiles.py --min-count 100        # require 100 samples
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH   = ROOT / "data" / "stream_results.db"
OUT_PATH  = ROOT / "data" / "fleet_percentiles.json"

BENCHMARK_COLS = {
    # (column, higher_is_worse)
    "max_roll_deg":        True,
    "max_pitch_deg":       True,
    "motor_imbalance":     True,
    "rate_roll_err_rms":   True,
    "rate_pitch_err_rms":  True,
    "att_roll_err_rms":    True,
    "att_pitch_err_rms":   True,
    "vel_err_horiz_rms":   True,
    "pos_err_horiz_rms":   True,
    "peak_g_last20pct":    True,
    "batt_drop_v":         True,
    "batt_v_min":          False,   # lower is worse
    "motor_sat_frac":      True,
    "rc_rssi_min":         False,
    "failsafe_count":      True,
    "vib_rms_z":           True,
    "gps_hdop_max":        True,
    "cpu_load_avg":        True,
    "rate_osc_amp_roll":   True,
    "rate_osc_amp_pitch":  True,
    "act_motor_corr_min":  False,   # lower = worse actuator fidelity
    "wind_speed_avg":      True,
    "score":               False,   # lower score is worse
}

PERCENTILES = [10, 25, 50, 75, 90, 95, 99]


def compute(db_path: Path, min_count: int, out_path: Path) -> dict:
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        print("Run: pip install pandas")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql("SELECT * FROM analyzed_logs WHERE ok=1", conn)
    conn.close()

    if len(df) < min_count:
        print(f"Only {len(df)} logs — need {min_count}. Keep streaming.")
        sys.exit(0)

    available = {col: hiw for col, hiw in BENCHMARK_COLS.items() if col in df.columns}
    result = {
        "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
        "total_logs": len(df),
        "global": {},
        "by_vehicle_type": {},
        "by_hardware": {},
    }

    def _compute_for(subset: pd.DataFrame, label: str) -> dict:
        out = {}
        for col, higher_is_worse in available.items():
            vals = subset[col].dropna()
            if len(vals) < 10:
                continue
            pcts = np.percentile(vals, PERCENTILES).tolist()
            out[col] = {
                "n": len(vals),
                "percentiles": dict(zip([str(p) for p in PERCENTILES], [round(v, 4) for v in pcts])),
                "mean": round(float(vals.mean()), 4),
                "std":  round(float(vals.std()), 4),
                "higher_is_worse": higher_is_worse,
            }
        return out

    result["global"] = _compute_for(df, "global")

    for vt, grp in df.groupby("vehicle_type"):
        if pd.isna(vt) or len(grp) < 20:
            continue
        result["by_vehicle_type"][str(vt)] = _compute_for(grp, str(vt))

    for hw, grp in df.groupby("hardware"):
        if pd.isna(hw) or len(grp) < 10:
            continue
        result["by_hardware"][str(hw)] = _compute_for(grp, str(hw))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"Percentiles computed from {len(df)} logs -> {out_path}")
    print(f"  Global metrics: {len(result['global'])}")
    print(f"  Vehicle types : {len(result['by_vehicle_type'])}")
    print(f"  Hardware types: {len(result['by_hardware'])}")
    return result


def query_log(db_path: Path, percentile_path: Path, log_id: str) -> None:
    """Score a single log against fleet percentiles."""
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        sys.exit(1)

    if not percentile_path.exists():
        print(f"No percentile file at {percentile_path} — run without --query first.")
        sys.exit(1)

    pct_data = json.loads(percentile_path.read_text())
    conn = sqlite3.connect(str(db_path))
    row = pd.read_sql(f"SELECT * FROM analyzed_logs WHERE log_id LIKE '{log_id}%'", conn)
    conn.close()

    if row.empty:
        print(f"log_id {log_id} not found in DB.")
        sys.exit(1)

    row = row.iloc[0]
    vt = row.get("vehicle_type")
    hw = row.get("hardware")
    benchmarks = pct_data.get("by_vehicle_type", {}).get(str(vt) if vt else "", {}) or pct_data["global"]

    print(f"\nFleet comparison for {log_id[:8]}... ({vt} / {hw})")
    print(f"{'Metric':<30} {'Value':>8}  {'Pct':>5}  {'vs fleet'}")
    print("-" * 60)

    for col, info in benchmarks.items():
        val = row.get(col)
        if val is None or pd.isna(val):
            continue
        pcts = info["percentiles"]
        vals = [float(pcts[str(p)]) for p in PERCENTILES]
        # Find percentile rank
        rank = 0
        for p, v in zip(PERCENTILES, vals):
            if float(val) >= v:
                rank = p
        higher_is_worse = info["higher_is_worse"]
        if higher_is_worse:
            flag = "!!" if rank >= 90 else ("!" if rank >= 75 else "")
        else:
            flag = "!!" if rank <= 10 else ("!" if rank <= 25 else "")
        print(f"  {col:<28} {val:>8.3f}  p{rank:>2}   {flag}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--out", default=str(OUT_PATH))
    p.add_argument("--min-count", type=int, default=50)
    p.add_argument("--query", metavar="LOG_ID", help="Score a specific log against fleet")
    args = p.parse_args()

    if args.query:
        query_log(Path(args.db), Path(args.out), args.query)
    else:
        compute(Path(args.db), args.min_count, Path(args.out))


if __name__ == "__main__":
    main()
