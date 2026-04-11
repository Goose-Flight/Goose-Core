#!/usr/bin/env python3
"""Train crash confidence model from stream_results.db.

Uses weak supervision: high-confidence telemetry detections as positive labels,
clean long flights as negative labels.  When human-rated logs accumulate,
those take priority as ground truth.

Usage:
    python scripts/ml_train.py                          # train + evaluate
    python scripts/ml_train.py --min-samples 500        # wait for more data
    python scripts/ml_train.py --out models/crash_v1.json  # save model
    python scripts/ml_train.py --feature-importance     # show top features
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "stream_results.db"
MODEL_DIR = ROOT / "models"

FEATURE_COLS = [
    # Crash signals
    "max_roll_deg", "max_pitch_deg", "max_yaw_rate_dps",
    "motor_cutoff_frac", "motor_cutoff_tilt", "motor_imbalance",
    "alt_peak_m", "alt_drop_rate", "alt_drop_m",
    "peak_g_last20pct", "peak_g_overall",
    # Tracking quality (commanded vs actual)
    "rate_roll_err_rms", "rate_pitch_err_rms", "rate_yaw_err_rms",
    "rate_roll_err_p95", "rate_pitch_err_p95",
    "att_roll_err_rms", "att_pitch_err_rms", "att_yaw_err_rms",
    "att_roll_err_p95", "att_pitch_err_p95",
    "vel_err_horiz_rms", "vel_err_vert_rms",
    "pos_err_horiz_rms", "pos_err_vert_rms",
    # Oscillation
    "rate_osc_freq_roll", "rate_osc_freq_pitch",
    "rate_osc_amp_roll", "rate_osc_amp_pitch",
    # Actuator fidelity
    "act_thrust_mean", "act_thrust_std",
    "act_motor_corr_min", "act_motor_corr_avg",
    "motor_sat_frac", "motor_idle_frac",
    # Battery
    "batt_v_min", "batt_drop_v", "batt_pct_min", "batt_current_max",
    # GPS
    "gps_fix_min", "gps_sat_min", "gps_hdop_max",
    # Vibration
    "vib_rms_x", "vib_rms_y", "vib_rms_z",
    # RC
    "rc_rssi_min", "rc_loss_events",
    # Events
    "failsafe_count", "mode_change_count", "error_count",
    # Flight characteristics
    "duration_sec", "vel_horiz_max", "horiz_dist_m",
    "motor_min_avg", "motor_max_avg",
    "cpu_load_max",
]


def _load_data(db_path: Path, min_confidence_pos: float = 0.80,
               min_duration_neg: float = 30.0) -> tuple:
    """Load features + weak labels from DB.

    Positive (crash=1):  crash_confidence >= min_confidence_pos
                         OR human rating is crash/not ok
    Negative (crash=0):  crash_confidence == 0.0 AND duration >= min_duration_neg
                         AND no human crash rating
    Unlabeled: everything else (excluded from training)
    """
    import pandas as pd
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql("SELECT * FROM analyzed_logs WHERE ok=1", conn)
    conn.close()

    if df.empty:
        return None, None, df

    # Build labels
    human_crash = df["rating"].isin(["crash", "not ok", "fail"])
    telem_crash  = df["crash_confidence"] >= min_confidence_pos
    telem_clean  = (df["crash_confidence"] == 0.0) & (df["duration_sec"] >= min_duration_neg)

    df["label"] = None
    df.loc[human_crash | telem_crash, "label"] = 1
    df.loc[~human_crash & telem_clean, "label"] = 0

    labeled = df.dropna(subset=["label"])
    import numpy as np
    available_cols = [c for c in FEATURE_COLS if c in labeled.columns]
    X = labeled[available_cols].copy()
    # Replace inf/-inf with NaN so fillna handles them uniformly
    X = X.replace([np.inf, -np.inf], np.nan)
    # Clip extreme outliers per column (99.9th percentile cap) before imputation
    for col in X.columns:
        p999 = X[col].quantile(0.999)
        p001 = X[col].quantile(0.001)
        X[col] = X[col].clip(lower=p001, upper=p999)
    X = X.fillna(-1)
    y = labeled["label"].astype(int)

    return X, y, labeled


def train(db_path: Path, min_samples: int, out_path: Path | None,
          show_importance: bool) -> None:
    try:
        import xgboost as xgb
        from sklearn.model_selection import StratifiedKFold, cross_val_score
        from sklearn.metrics import roc_auc_score, classification_report
        import numpy as np
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: pip install xgboost scikit-learn")
        sys.exit(1)

    print(f"Loading data from {db_path}...")
    X, y, df = _load_data(db_path)

    if X is None or len(X) == 0:
        print("No data in DB yet. Run stream_analyze.py first.")
        sys.exit(1)

    n_pos = int(y.sum())
    n_neg = int((y == 0).sum())
    print(f"Labeled samples: {len(X)} total  |  {n_pos} crash  |  {n_neg} clean")

    if len(X) < min_samples:
        print(f"Only {len(X)} labeled samples — need {min_samples}. Keep streaming.")
        sys.exit(0)

    if n_pos < 20 or n_neg < 20:
        print(f"Not enough of each class (need >=20). Got {n_pos} crash, {n_neg} clean.")
        sys.exit(0)

    # Class weights for imbalanced data
    scale = n_neg / n_pos if n_pos > 0 else 1.0

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=scale,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="auc",
        random_state=42,
        n_jobs=-1,
    )

    # Cross-validation
    cv = StratifiedKFold(n_splits=min(5, n_pos), shuffle=True, random_state=42)
    scores = cross_val_score(model, X, y, cv=cv, scoring="roc_auc")
    print(f"\nCross-validation AUC: {scores.mean():.3f} +/- {scores.std():.3f}")

    # Full fit
    model.fit(X, y)

    # Feature importance
    if show_importance:
        importance = sorted(zip(X.columns, model.feature_importances_),
                           key=lambda x: -x[1])
        print("\nTop 20 features:")
        for feat, imp in importance[:20]:
            bar = "#" * int(imp * 200)
            print(f"  {feat:<35} {imp:.4f}  {bar}")

    # Save model
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(out_path))
        # Also save metadata
        meta = {
            "n_samples": len(X),
            "n_positive": n_pos,
            "n_negative": n_neg,
            "cv_auc_mean": float(scores.mean()),
            "cv_auc_std": float(scores.std()),
            "feature_cols": list(X.columns),
            "threshold": 0.5,
        }
        meta_path = out_path.with_suffix(".meta.json")
        meta_path.write_text(json.dumps(meta, indent=2))
        print(f"\nModel saved: {out_path}")
        print(f"Metadata  : {meta_path}")

    print(f"\nDone. AUC={scores.mean():.3f} on {len(X)} labeled samples.")
    print("When AUC > 0.85 consistently, consider replacing crash_assessment() with model inference.")


def main() -> None:
    p = argparse.ArgumentParser(description="Train crash model from stream DB")
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--min-samples", type=int, default=200,
                   help="Minimum labeled samples before training (default: 200)")
    p.add_argument("--out", default=None, help="Path to save model (.json)")
    p.add_argument("--feature-importance", action="store_true")
    args = p.parse_args()

    out = Path(args.out) if args.out else MODEL_DIR / "crash_model.json"
    train(Path(args.db), args.min_samples, out, args.feature_importance)


if __name__ == "__main__":
    main()
