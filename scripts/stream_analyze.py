#!/usr/bin/env python3
"""Stream-analyze public PX4 logs from logs.px4.io.

Downloads one log at a time, runs full Goose analysis, stores results in
SQLite, then deletes the file.  Fully resumable — already-analyzed log_ids
are skipped on every run.  Designed to scale to all 371k+ public logs.

Usage:
    python scripts/stream_analyze.py --limit 100          # first run / test
    python scripts/stream_analyze.py --limit 1000         # larger batch
    python scripts/stream_analyze.py --resume             # skip already done
    python scripts/stream_analyze.py --stats              # show DB stats only
    python scripts/stream_analyze.py --export results.csv # export DB to CSV
    python scripts/stream_analyze.py --rated-crashes-only # only logs rated as crash/not ok
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sqlite3
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOGS_BASE = "https://logs.px4.io"
BROWSE_URL = f"{LOGS_BASE}/browse_data_retrieval"
DOWNLOAD_URL = f"{LOGS_BASE}/download"
USER_AGENT = "goose-flight/1.0 (research; stream-analyze)"
RATE_LIMIT_SEC = 1.2   # seconds between downloads — be polite
PAGE_SIZE = 100        # entries per listing request

DB_PATH = ROOT / "data" / "stream_results.db"

# ---------------------------------------------------------------------------
# DB schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyzed_logs (
    log_id              TEXT PRIMARY KEY,
    analyzed_at         TEXT NOT NULL,
    -- Listing metadata (from logs.px4.io API)
    date                TEXT,
    vehicle_type_api    TEXT,
    airframe            TEXT,
    hardware_api        TEXT,
    firmware_api        TEXT,
    duration_api        TEXT,
    rating              TEXT,
    mode_api            TEXT,
    -- Parse / analysis outcome
    ok                  INTEGER NOT NULL DEFAULT 0,
    error               TEXT,
    -- Flight metadata (from parsed log)
    duration_sec        REAL,
    vehicle_type        TEXT,
    hardware            TEXT,
    firmware            TEXT,
    primary_mode        TEXT,
    -- Crash assessment
    crashed             INTEGER,
    crash_confidence    REAL,
    crash_signals       TEXT,
    -- Plugin results
    score               INTEGER,
    critical_count      INTEGER,
    warning_count       INTEGER,
    info_count          INTEGER,
    -- Signal availability
    has_gps             INTEGER,
    has_attitude        INTEGER,
    has_battery         INTEGER,
    has_motors          INTEGER,
    has_vibration       INTEGER,
    signal_streams      INTEGER
);

CREATE INDEX IF NOT EXISTS idx_analyzed_at ON analyzed_logs (analyzed_at);
CREATE INDEX IF NOT EXISTS idx_crashed ON analyzed_logs (crashed);
CREATE INDEX IF NOT EXISTS idx_crash_confidence ON analyzed_logs (crash_confidence);
CREATE INDEX IF NOT EXISTS idx_rating ON analyzed_logs (rating);
CREATE INDEX IF NOT EXISTS idx_score ON analyzed_logs (score);
"""

# ---------------------------------------------------------------------------
# Listing helpers (reused from download_public_logs.py)
# ---------------------------------------------------------------------------

def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _build_browse_url(start: int, length: int, rated_crashes_only: bool = False) -> str:
    params = {
        "draw": "1",
        "start": str(start),
        "length": str(length),
        "columns[0][data]": "0",
        "columns[1][data]": "1",
        "columns[2][data]": "2",
        "columns[3][data]": "3",
        "columns[4][data]": "4",
        "columns[5][data]": "5",
        "columns[6][data]": "6",
        "columns[7][data]": "7",
        "columns[8][data]": "8",
        "columns[9][data]": "9",
        "order[0][column]": "1",
        "order[0][dir]": "desc",
    }
    if rated_crashes_only:
        # Filter by rating column (col 8) — value "crash" or "not ok"
        params["columns[8][search][value]"] = "crash"
    return BROWSE_URL + "?" + urllib.parse.urlencode(params)


def _extract_log_id(html_cell: str) -> str | None:
    m = re.search(r'log=([0-9a-f-]{36})', html_cell)
    return m.group(1) if m else None


def _extract_text(html_cell: str) -> str:
    m = re.search(r'>([^<]+)<', html_cell)
    return m.group(1).strip() if m else str(html_cell).strip()


def _parse_row(row: list) -> dict:
    return {
        "log_id":       _extract_log_id(str(row[1])) if len(row) > 1 else None,
        "date":         _extract_text(str(row[1])) if len(row) > 1 else None,
        "vehicle_type": str(row[3]) if len(row) > 3 else None,
        "airframe":     str(row[4]) if len(row) > 4 else None,
        "hardware":     str(row[5]) if len(row) > 5 else None,
        "firmware":     str(row[6]) if len(row) > 6 else None,
        "duration":     str(row[7]) if len(row) > 7 else None,
        "rating":       str(row[8]).lower().strip() if len(row) > 8 else None,
        "mode":         str(row[9]) if len(row) > 9 else None,
    }

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download_to_temp(log_id: str) -> str | None:
    """Download log to a temp file. Returns path on success, None on failure."""
    url = f"{DOWNLOAD_URL}?log={urllib.parse.quote(log_id)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        if len(data) < 64:
            return None
        fd, path = tempfile.mkstemp(suffix=".ulg", prefix="goose_stream_")
        os.write(fd, data)
        os.close(fd)
        return path
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _analyze(log_path: str, entry: dict) -> dict:
    """Parse + analyze one log. Returns result dict for DB insertion."""
    result: dict = {
        "log_id":           entry["log_id"],
        "analyzed_at":      datetime.now(timezone.utc).isoformat(),
        "date":             entry.get("date"),
        "vehicle_type_api": entry.get("vehicle_type"),
        "airframe":         entry.get("airframe"),
        "hardware_api":     entry.get("hardware"),
        "firmware_api":     entry.get("firmware"),
        "duration_api":     entry.get("duration"),
        "rating":           entry.get("rating"),
        "mode_api":         entry.get("mode"),
        "ok":               0,
        "error":            None,
        "duration_sec":     None,
        "vehicle_type":     None,
        "hardware":         None,
        "firmware":         None,
        "primary_mode":     None,
        "crashed":          None,
        "crash_confidence": None,
        "crash_signals":    None,
        "score":            None,
        "critical_count":   0,
        "warning_count":    0,
        "info_count":       0,
        "has_gps":          0,
        "has_attitude":     0,
        "has_battery":      0,
        "has_motors":       0,
        "has_vibration":    0,
        "signal_streams":   0,
    }
    try:
        from goose.parsers.ulog import ULogParser
        from goose.plugins.registry import load_plugins
        from goose.core.scoring import compute_overall_score

        pr = ULogParser().parse(log_path)
        if pr is None or pr.flight is None:
            result["error"] = "parse returned None"
            return result

        flight = pr.flight
        meta = flight.metadata

        result["duration_sec"]  = round(meta.duration_sec, 1)
        result["vehicle_type"]  = meta.vehicle_type
        result["hardware"]      = meta.hardware or meta.autopilot
        result["firmware"]      = meta.firmware_version
        result["primary_mode"]  = flight.primary_mode
        result["has_gps"]       = int(not flight.gps.empty)
        result["has_attitude"]  = int(not flight.attitude.empty)
        result["has_battery"]   = int(not flight.battery.empty)
        result["has_motors"]    = int(not flight.motors.empty)
        result["has_vibration"] = int(not flight.vibration.empty)

        ca = flight.crash_assessment()
        result["crashed"]          = int(ca["crashed"])
        result["crash_confidence"] = ca["confidence"]
        result["crash_signals"]    = "; ".join(ca["signals"]) if ca["signals"] else ""

        if pr.diagnostics:
            result["signal_streams"] = len(pr.diagnostics.stream_coverage)

        # Run plugins
        plugins = load_plugins()
        findings = []
        for p in plugins:
            try:
                findings.extend(p.analyze(flight, {}))
            except Exception:
                pass

        result["score"]          = compute_overall_score(findings)
        result["critical_count"] = sum(1 for f in findings if f.severity == "critical")
        result["warning_count"]  = sum(1 for f in findings if f.severity == "warning")
        result["info_count"]     = sum(1 for f in findings if f.severity == "info")
        result["ok"] = 1

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    return result

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _already_done(conn: sqlite3.Connection, log_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM analyzed_logs WHERE log_id = ?", (log_id,)).fetchone()
    return row is not None


def _insert(conn: sqlite3.Connection, r: dict) -> None:
    cols = list(r.keys())
    placeholders = ", ".join("?" * len(cols))
    sql = f"INSERT OR REPLACE INTO analyzed_logs ({', '.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, [r[c] for c in cols])
    conn.commit()


def _print_stats(conn: sqlite3.Connection, db_path: Path = DB_PATH) -> None:
    total = conn.execute("SELECT COUNT(*) FROM analyzed_logs").fetchone()[0]
    ok    = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE ok=1").fetchone()[0]
    crash = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE crashed=1").fetchone()[0]
    hi    = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE crash_confidence >= 0.80").fetchone()[0]
    med   = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE crash_confidence >= 0.60 AND crash_confidence < 0.80").fetchone()[0]
    low   = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE crash_confidence > 0 AND crash_confidence < 0.60").fetchone()[0]
    avg_score = conn.execute("SELECT AVG(score) FROM analyzed_logs WHERE ok=1").fetchone()[0]
    rated_crash = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE rating IN ('crash','not ok','fail')").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"  Stream analysis DB: {db_path}")
    print(f"{'='*60}")
    print(f"  Total analyzed  : {total:,}")
    print(f"  Parse OK        : {ok:,} ({ok/total*100:.0f}%)" if total else "  Parse OK        : 0")
    print(f"  Human-rated crash: {rated_crash:,}")
    print(f"  Crash detected  : {crash:,}")
    print(f"    high (>=80%)  : {hi:,}")
    print(f"    medium (60-79%): {med:,}")
    print(f"    signal evidence: {low:,}")
    print(f"  Avg score       : {avg_score:.0f}" if avg_score else "  Avg score       : n/a")
    print(f"{'='*60}\n")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _export_csv(conn: sqlite3.Connection, path: str) -> None:
    import csv
    rows = conn.execute("SELECT * FROM analyzed_logs ORDER BY analyzed_at").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM analyzed_logs LIMIT 0").description]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    print(f"Exported {len(rows):,} rows to {path}")

# ---------------------------------------------------------------------------
# Main stream loop
# ---------------------------------------------------------------------------

_shutdown = False

def _handle_signal(sig, frame):
    global _shutdown
    print("\n[interrupt] Finishing current log then stopping...")
    _shutdown = True


def stream_analyze(
    limit: int,
    resume: bool,
    rated_crashes_only: bool,
    offset_start: int = 0,
    db_path: Path = DB_PATH,
) -> None:
    conn = _open_db(db_path)
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    total_done = conn.execute("SELECT COUNT(*) FROM analyzed_logs").fetchone()[0]
    print(f"\nGoose Stream Analyzer")
    print(f"  DB         : {db_path}")
    print(f"  Already done: {total_done:,}")
    print(f"  Target      : {limit} new logs")
    print(f"  Offset start: {offset_start}")
    print(f"  Filter      : {'rated-crashes-only' if rated_crashes_only else 'all public logs'}")
    print()

    processed = 0
    skipped = 0
    offset = offset_start
    t0 = time.time()

    while processed < limit and not _shutdown:
        # Fetch a page of log listings
        fetch = min(PAGE_SIZE, limit - processed + skipped + 20)
        url = _build_browse_url(offset, fetch, rated_crashes_only)
        try:
            data = _fetch_json(url)
        except urllib.error.URLError as exc:
            print(f"  [listing error] {exc} — retrying in 5s")
            time.sleep(5)
            continue

        rows = data.get("data", [])
        if not rows:
            print("  [done] No more logs in listing.")
            break

        total_available = data.get("recordsTotal", "?")

        for row in rows:
            if processed >= limit or _shutdown:
                break

            entry = _parse_row(row)
            log_id = entry.get("log_id")
            if not log_id:
                skipped += 1
                continue

            if _already_done(conn, log_id):
                skipped += 1
                continue

            # Download
            t_dl = time.time()
            tmp = _download_to_temp(log_id)
            dl_sec = time.time() - t_dl

            if tmp is None:
                result = {
                    "log_id": log_id,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "date": entry.get("date"),
                    "vehicle_type_api": entry.get("vehicle_type"),
                    "airframe": entry.get("airframe"),
                    "hardware_api": entry.get("hardware"),
                    "firmware_api": entry.get("firmware"),
                    "duration_api": entry.get("duration"),
                    "rating": entry.get("rating"),
                    "mode_api": entry.get("mode"),
                    "ok": 0,
                    "error": "download failed",
                    "duration_sec": None, "vehicle_type": None, "hardware": None,
                    "firmware": None, "primary_mode": None,
                    "crashed": None, "crash_confidence": None, "crash_signals": None,
                    "score": None, "critical_count": 0, "warning_count": 0, "info_count": 0,
                    "has_gps": 0, "has_attitude": 0, "has_battery": 0, "has_motors": 0,
                    "has_vibration": 0, "signal_streams": 0,
                }
                _insert(conn, result)
                processed += 1
                elapsed = time.time() - t0
                rate = processed / elapsed * 60
                print(f"[{processed:>4}/{limit}] FAIL  {log_id[:8]}  download failed  ({rate:.0f}/min)")
                time.sleep(RATE_LIMIT_SEC)
                continue

            # Analyze
            t_an = time.time()
            try:
                result = _analyze(tmp, entry)
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            an_sec = time.time() - t_an

            _insert(conn, result)
            processed += 1

            elapsed = time.time() - t0
            rate = processed / elapsed * 60

            if result["ok"]:
                conf = result.get("crash_confidence") or 0.0
                if conf >= 0.60:
                    crash_tag = f"CRASH({conf:.0%})"
                elif conf > 0.0:
                    crash_tag = f"sig({conf:.0%})"
                else:
                    crash_tag = "ok"
                score = f"s={result['score']}" if result['score'] is not None else "s=?"
                hw = (result.get("hardware") or entry.get("hardware") or "?")[:16]
                print(f"[{processed:>4}/{limit}] {crash_tag:<12} {log_id[:8]}  {hw:<17} {score}  dl={dl_sec:.0f}s an={an_sec:.0f}s  {rate:.0f}/min")
            else:
                err = (result.get("error") or "?")[:50]
                print(f"[{processed:>4}/{limit}] ERR          {log_id[:8]}  {err}  {rate:.0f}/min")

            time.sleep(RATE_LIMIT_SEC)

        offset += len(rows)

    # Summary
    elapsed = time.time() - t0
    print(f"\n{'-'*60}")
    print(f"Done: {processed} analyzed, {skipped} skipped (already done or no id)")
    print(f"Time: {elapsed:.0f}s  Rate: {processed/elapsed*60:.0f}/min avg")
    _print_stats(conn, db_path)
    conn.close()

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Stream-analyze PX4 public logs into SQLite")
    p.add_argument("--limit", type=int, default=100, help="Max new logs to analyze (default: 100)")
    p.add_argument("--resume", action="store_true", help="Skip logs already in DB (default behavior)")
    p.add_argument("--offset", type=int, default=0, help="Start at this offset in the logs.px4.io listing")
    p.add_argument("--rated-crashes-only", action="store_true", help="Only fetch logs with explicit crash rating")
    p.add_argument("--stats", action="store_true", help="Print DB stats and exit")
    p.add_argument("--export", metavar="CSV", help="Export DB to CSV and exit")
    p.add_argument("--db", metavar="PATH", help=f"SQLite DB path (default: {DB_PATH})")
    args = p.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH

    conn = _open_db(db_path)

    if args.stats:
        _print_stats(conn, db_path)
        conn.close()
        return

    if args.export:
        _export_csv(conn, args.export)
        conn.close()
        return

    conn.close()

    stream_analyze(
        limit=args.limit,
        resume=True,
        rated_crashes_only=args.rated_crashes_only,
        offset_start=args.offset,
        db_path=db_path,
    )


if __name__ == "__main__":
    main()
