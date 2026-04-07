#!/usr/bin/env python3
"""Download public PX4 flight logs from the Flight Review API (https://review.px4.io).

Based on the PX4 Flight Review download_logs.py pattern.
API reference: https://review.px4.io/api/list_public_logs

Usage:
    python scripts/download_public_logs.py --limit 10
    python scripts/download_public_logs.py --limit 5 --crashes-only
    python scripts/download_public_logs.py --limit 20 --output-dir /tmp/mylogs
    python scripts/download_public_logs.py --limit 3 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REVIEW_BASE = "https://review.px4.io"
# The canonical public-log listing endpoint used by PX4 Flight Review.
# Returns a JSON array of log-entry objects.
LIST_URL = f"{REVIEW_BASE}/api/list_public_logs"
# Log download endpoint: GET /download_log?log=<log_id>
DOWNLOAD_URL = f"{REVIEW_BASE}/download_log"

DEFAULT_OUTPUT_DIR = os.path.join("logs", "px4")
CRASHES_SUBDIR = "crashes"
GOOD_FLIGHTS_SUBDIR = "good_flights"

USER_AGENT = "goose-flight/1.0 (https://github.com/Goose-Flight/Goose-Core)"
RATE_LIMIT_SEC = 1.0  # seconds between requests — be polite


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _fetch_json(url: str) -> Any:
    """Fetch JSON from a URL.  Raises urllib.error.URLError on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw.decode("utf-8"))


def list_public_logs(limit: int = 50) -> list[dict]:
    """Return up to *limit* public log entries from Flight Review.

    Each entry is a dict with at minimum:
        log_id, vehicle_name, firmware_version, airframe_name,
        num_logged_errors, num_logged_warnings, description, upload_date
    """
    url = f"{LIST_URL}?limit={limit}"
    try:
        data = _fetch_json(url)
    except urllib.error.URLError as exc:
        print(f"  [warn] Could not reach Flight Review API: {exc}", file=sys.stderr)
        return []

    # The endpoint may return {"logs": [...]} or a bare list
    if isinstance(data, dict):
        logs = data.get("logs", data.get("data", []))
    elif isinstance(data, list):
        logs = data
    else:
        logs = []

    return logs[:limit]


def download_log(log_id: str, dest_path: str | Path) -> bool:
    """Download a single .ulg file to *dest_path*.

    Returns True on success, False on failure.
    """
    url = f"{DOWNLOAD_URL}?log={urllib.parse.quote(str(log_id))}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        # Validate we actually got binary ULog data (magic: ULog\x00\x00)
        if len(data) < 16:
            print(f"  [warn] Response for {log_id} too small ({len(data)} bytes) — skipping")
            return False
        dest_path = Path(dest_path)
        dest_path.write_bytes(data)
        size_kb = len(data) / 1024
        print(f"  [ok]   {dest_path.name}  ({size_kb:.0f} KB)")
        return True
    except urllib.error.URLError as exc:
        print(f"  [fail] log_id={log_id}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

_CRASH_KEYWORDS = frozenset([
    "crash", "crashed", "fail", "failsafe", "emergency",
    "land", "flip", "flipped", "lost control", "lost gps",
    "error", "fall", "fell", "brown", "brownout", "motor",
])


def _is_crash(entry: dict) -> bool:
    """Heuristic: return True if this log looks like a crash/anomaly log."""
    # Some API responses include an explicit crash/error flag
    if entry.get("has_public_logs") is False:
        return False

    num_errors = int(entry.get("num_logged_errors", 0) or 0)
    if num_errors > 0:
        return True

    # Check description for crash keywords
    desc = (entry.get("description", "") or "").lower()
    if any(kw in desc for kw in _CRASH_KEYWORDS):
        return True

    # Some responses include an explicit boolean
    if entry.get("is_crash") or entry.get("crash"):
        return True

    return False


def _log_id(entry: dict) -> str | None:
    """Extract the log ID from an entry dict, handling different key names."""
    for key in ("log_id", "id", "logId"):
        val = entry.get(key)
        if val is not None:
            return str(val)
    return None


def _safe_filename_part(text: str, maxlen: int = 24) -> str:
    """Sanitize *text* for use inside a filename."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)[:maxlen]


def _build_filename(entry: dict, prefix: str, index: int) -> str:
    """Build a deterministic filename for a log entry."""
    log_id = _log_id(entry) or f"unknown_{index}"
    vehicle = _safe_filename_part(entry.get("vehicle_name", "") or "")
    fw = _safe_filename_part(entry.get("firmware_version", "") or "")
    parts = [prefix, str(index).zfill(3)]
    if vehicle:
        parts.append(vehicle)
    if fw:
        parts.append(fw)
    parts.append(log_id)
    return "_".join(p for p in parts if p) + ".ulg"


def _build_metadata(entry: dict) -> dict:
    """Build a JSON-serialisable metadata sidecar dict for an entry."""
    return {
        "log_id": _log_id(entry),
        "vehicle_name": entry.get("vehicle_name"),
        "firmware_version": entry.get("firmware_version"),
        "airframe_name": entry.get("airframe_name"),
        "description": entry.get("description"),
        "upload_date": entry.get("upload_date") or entry.get("date"),
        "num_logged_errors": entry.get("num_logged_errors"),
        "num_logged_warnings": entry.get("num_logged_warnings"),
        "rating": entry.get("rating"),
        "is_crash_heuristic": _is_crash(entry),
        "source_url": f"{DOWNLOAD_URL}?log={_log_id(entry)}",
    }


# ---------------------------------------------------------------------------
# Core download logic
# ---------------------------------------------------------------------------

def download_logs(
    limit: int,
    crashes_only: bool,
    output_dir: str | Path,
    dry_run: bool = False,
) -> int:
    """Download up to *limit* public logs and save them under *output_dir*.

    Organises files into:
        <output_dir>/crashes/          — logs classified as crashes
        <output_dir>/good_flights/     — all other logs

    Returns the number of logs successfully saved.
    """
    output_dir = Path(output_dir)
    crashes_dir = output_dir / CRASHES_SUBDIR
    good_dir = output_dir / GOOD_FLIGHTS_SUBDIR

    if not dry_run:
        crashes_dir.mkdir(parents=True, exist_ok=True)
        good_dir.mkdir(parents=True, exist_ok=True)

    # Fetch more than we need so we can filter
    fetch_count = limit * 3 if crashes_only else limit * 2
    print(f"Fetching log listing from {LIST_URL} ...")
    entries = list_public_logs(limit=min(fetch_count, 500))

    if not entries:
        print("No logs returned by the API.  Check your internet connection.")
        return 0

    print(f"API returned {len(entries)} entries.  Selecting up to {limit} ...")

    # Filter if crashes_only
    if crashes_only:
        selected = [e for e in entries if _is_crash(e)]
        label = "crash"
    else:
        selected = entries
        label = "all"

    selected = selected[:limit]
    print(f"Selected {len(selected)} {label} logs to download.\n")

    downloaded = 0
    crash_count = 0
    good_count = 0

    for idx, entry in enumerate(selected, start=1):
        log_id = _log_id(entry)
        if not log_id:
            print(f"  [skip] entry {idx} has no log_id — skipping")
            continue

        is_crash = _is_crash(entry)
        dest_dir = crashes_dir if is_crash else good_dir
        prefix = "crash" if is_crash else "good"
        filename = _build_filename(entry, prefix, idx)
        filepath = dest_dir / filename
        meta_path = filepath.with_suffix(".json")

        print(f"[{idx}/{len(selected)}] log_id={log_id}  crash={is_crash}  -> {filepath.relative_to(output_dir)}")

        if filepath.exists():
            print(f"  [skip] already exists")
            downloaded += 1
            (crash_count if is_crash else good_count)  # just for counting
            if is_crash:
                crash_count += 1
            else:
                good_count += 1
            continue

        if dry_run:
            print(f"  [dry]  would download to {filepath}")
            downloaded += 1
        else:
            ok = download_log(log_id, filepath)
            if ok:
                downloaded += 1
                if is_crash:
                    crash_count += 1
                else:
                    good_count += 1
                # Write JSON sidecar
                meta = _build_metadata(entry)
                meta_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

        # Rate limit — be polite to the server
        if idx < len(selected):
            time.sleep(RATE_LIMIT_SEC)

    print(f"\nDone.  {downloaded}/{len(selected)} logs downloaded.")
    print(f"  crashes:      {crash_count}  -> {crashes_dir}")
    print(f"  good flights: {good_count}   -> {good_dir}")
    return downloaded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Download public PX4 flight logs from https://review.px4.io",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--limit",
        type=int,
        default=10,
        metavar="N",
        help="Maximum number of logs to download (default: 10)",
    )
    p.add_argument(
        "--crashes-only",
        action="store_true",
        default=False,
        help="Only download logs that appear to be crashes or have logged errors",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Root output directory (default: {DEFAULT_OUTPUT_DIR}). "
             f"Logs are organised into crashes/ and good_flights/ subdirectories.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List what would be downloaded without actually downloading",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")

    print(f"PX4 Flight Review Log Downloader")
    print(f"  API base : {REVIEW_BASE}")
    print(f"  limit    : {args.limit}")
    print(f"  mode     : {'crashes only' if args.crashes_only else 'all public logs'}")
    print(f"  output   : {args.output_dir}")
    if args.dry_run:
        print(f"  [DRY RUN — no files will be written]")
    print()

    count = download_logs(
        limit=args.limit,
        crashes_only=args.crashes_only,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )

    if count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
