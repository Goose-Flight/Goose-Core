#!/usr/bin/env python3
"""Download public PX4 flight logs from logs.px4.io.

Scrapes the DataTables API used by the browse page to list public logs,
then downloads .ulg files directly.

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
import re
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

LOGS_BASE = "https://logs.px4.io"
# DataTables server-side endpoint (same one the /browse page uses)
BROWSE_URL = f"{LOGS_BASE}/browse_data_retrieval"
# Download endpoint: GET /download?log=<uuid>
DOWNLOAD_URL = f"{LOGS_BASE}/download"

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


def _build_browse_url(start: int, length: int, search: str = "") -> str:
    """Build the DataTables server-side request URL."""
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
        "order[0][column]": "1",
        "order[0][dir]": "desc",
    }
    if search:
        params["search[value]"] = search
        params["search[regex]"] = "false"
    return BROWSE_URL + "?" + urllib.parse.urlencode(params)


def _extract_log_id(html_cell: str) -> str | None:
    """Extract UUID log_id from the HTML link in column 1.

    Example: '<a href="plot_app?log=c9b12267-58a9-4a48-a2f7-ca63bdefc23f">2026-04-07</a>'
    """
    match = re.search(r'log=([0-9a-f-]{36})', html_cell)
    return match.group(1) if match else None


def _extract_date(html_cell: str) -> str:
    """Extract date text from the HTML link."""
    match = re.search(r'>([^<]+)<', html_cell)
    return match.group(1).strip() if match else "unknown"


def _parse_entry(row: list) -> dict:
    """Parse a DataTables row array into a structured dict.

    Row format: [index, date_link, image_html, vehicle_type, airframe, hardware, firmware, duration, rating, mode]
    """
    log_id = _extract_log_id(str(row[1])) if len(row) > 1 else None
    return {
        "log_id": log_id,
        "date": _extract_date(str(row[1])) if len(row) > 1 else None,
        "vehicle_type": row[3] if len(row) > 3 else None,
        "airframe": row[4] if len(row) > 4 else None,
        "hardware": row[5] if len(row) > 5 else None,
        "firmware_version": row[6] if len(row) > 6 else None,
        "duration": row[7] if len(row) > 7 else None,
        "rating": row[8] if len(row) > 8 else None,
        "mode": row[9] if len(row) > 9 else None,
    }


def list_public_logs(limit: int = 50, browse_start: int = 0, search: str = "") -> list[dict]:
    """Return up to *limit* public log entries from logs.px4.io, paginating as needed.

    browse_start: row offset in the DataTables API (useful for parallel workers).
    search: optional search string passed to the DataTables API (e.g. "crash").
    """
    PAGE_SIZE = 100
    entries: list[dict] = []
    total_announced = None
    offset = browse_start

    while len(entries) < limit:
        fetch = min(PAGE_SIZE, limit - len(entries))
        url = _build_browse_url(offset, fetch, search=search)
        try:
            data = _fetch_json(url)
        except urllib.error.URLError as exc:
            print(f"  [warn] Could not reach logs.px4.io: {exc}", file=sys.stderr)
            break

        if total_announced is None:
            total_announced = data.get("recordsFiltered", data.get("recordsTotal", 0))
            print(f"  Database has {total_announced:,} matching logs (start={browse_start}).")

        rows = data.get("data", [])
        if not rows:
            break

        batch = [_parse_entry(row) for row in rows]
        batch = [e for e in batch if e["log_id"]]
        entries.extend(batch)
        offset += len(rows)

        if offset >= (total_announced or 0):
            break

    return entries[:limit]


def download_log(log_id: str, dest_path: str | Path) -> bool:
    """Download a single .ulg file to *dest_path*.

    Returns True on success, False on failure.
    """
    url = f"{DOWNLOAD_URL}?log={urllib.parse.quote(str(log_id))}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
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
    "crash", "fail", "failsafe", "emergency",
    "flip", "lost", "error", "brownout",
])


def _is_crash(entry: dict) -> bool:
    """Heuristic: return True if this log looks like a crash/anomaly."""
    rating = str(entry.get("rating", "") or "").lower()
    if rating in ("crash", "not ok", "fail"):
        return True

    desc = " ".join(str(v) for v in entry.values() if v).lower()
    return any(kw in desc for kw in _CRASH_KEYWORDS)


def _safe_filename_part(text: str, maxlen: int = 24) -> str:
    """Sanitize *text* for use inside a filename."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(text))[:maxlen]


def _build_filename(entry: dict, prefix: str, index: int) -> str:
    """Build a deterministic filename for a log entry."""
    log_id = entry.get("log_id", f"unknown_{index}")
    hw = _safe_filename_part(entry.get("hardware", "") or "")
    parts = [prefix, str(index).zfill(3)]
    if hw:
        parts.append(hw)
    parts.append(str(log_id)[:8])
    return "_".join(p for p in parts if p) + ".ulg"


def _build_metadata(entry: dict) -> dict:
    """Build a JSON-serialisable metadata sidecar dict."""
    return {
        "log_id": entry.get("log_id"),
        "date": entry.get("date"),
        "vehicle_type": entry.get("vehicle_type"),
        "airframe": entry.get("airframe"),
        "hardware": entry.get("hardware"),
        "firmware_version": entry.get("firmware_version"),
        "duration": entry.get("duration"),
        "rating": entry.get("rating"),
        "mode": entry.get("mode"),
        "is_crash_heuristic": _is_crash(entry),
        "download_url": f"{DOWNLOAD_URL}?log={entry.get('log_id')}",
        "view_url": f"{LOGS_BASE}/plot_app?log={entry.get('log_id')}",
    }


# ---------------------------------------------------------------------------
# Core download logic
# ---------------------------------------------------------------------------

def download_logs(
    limit: int,
    crashes_only: bool,
    output_dir: str | Path,
    dry_run: bool = False,
    browse_start: int = 0,
    index_start: int = 1,
) -> int:
    """Download up to *limit* public logs and save them under *output_dir*.

    browse_start: row offset in the DataTables API for splitting work across parallel workers.
    index_start: starting number for filename index (avoids collisions across workers).
    """
    output_dir = Path(output_dir)
    crashes_dir = output_dir / CRASHES_SUBDIR
    good_dir = output_dir / GOOD_FLIGHTS_SUBDIR

    if not dry_run:
        crashes_dir.mkdir(parents=True, exist_ok=True)
        good_dir.mkdir(parents=True, exist_ok=True)

    # When fetching crash logs, use the API search filter to pre-filter results
    # so browse_start is meaningful as a crash-relative offset.
    if crashes_only:
        search = "crash"
        fetch_count = limit
        label = "crash"
    else:
        search = ""
        fetch_count = limit
        label = "all"

    print(f"Fetching log listing from {LOGS_BASE} (start={browse_start}, search={search!r}) ...")
    entries = list_public_logs(limit=fetch_count, browse_start=browse_start, search=search)

    if not entries:
        print("No logs returned.  Check your internet connection.")
        return 0

    print(f"  Retrieved {len(entries)} entries.  Selecting up to {limit} ...")

    if crashes_only and not search:
        # No server-side filter — apply heuristic locally
        selected = [e for e in entries if _is_crash(e)]
    else:
        # Server already filtered (search="crash") or no filter needed
        selected = entries

    selected = selected[:limit]
    print(f"  Selected {len(selected)} {label} logs.\n")

    downloaded = 0
    crash_count = 0
    good_count = 0

    for idx, entry in enumerate(selected, start=index_start):
        log_id = entry.get("log_id")
        if not log_id:
            print(f"  [skip] entry {idx} has no log_id")
            continue

        is_crash = _is_crash(entry)
        dest_dir = crashes_dir if is_crash else good_dir
        prefix = "crash" if is_crash else "good"
        filename = _build_filename(entry, prefix, idx)
        filepath = dest_dir / filename
        meta_path = filepath.with_suffix(".json")

        info = f"{entry.get('vehicle_type', '?')} / {entry.get('airframe', '?')} / {entry.get('duration', '?')}"
        print(f"[{idx}/{len(selected)}] {log_id[:8]}...  {info}")

        if filepath.exists():
            print(f"  [skip] already exists")
            downloaded += 1
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
                meta = _build_metadata(entry)
                meta_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

        if idx < len(selected):
            time.sleep(RATE_LIMIT_SEC)

    print(f"\nDone.  {downloaded}/{len(selected)} logs processed.")
    if not dry_run:
        print(f"  crashes:      {crash_count}  -> {crashes_dir}")
        print(f"  good flights: {good_count}   -> {good_dir}")
    return downloaded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Download public PX4 flight logs from logs.px4.io",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--limit", type=int, default=10, metavar="N",
        help="Maximum number of logs to download (default: 10)",
    )
    p.add_argument(
        "--crashes-only", action="store_true", default=False,
        help="Only download logs classified as crashes",
    )
    p.add_argument(
        "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR, metavar="DIR",
        help=f"Root output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    p.add_argument(
        "--dry-run", action="store_true", default=False,
        help="List what would be downloaded without actually downloading",
    )
    p.add_argument(
        "--browse-start", type=int, default=0, metavar="N",
        help="Row offset in the DataTables API — use with parallel workers (default: 0)",
    )
    p.add_argument(
        "--index-start", type=int, default=1, metavar="N",
        help="Starting index for output filenames (default: 1)",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")

    print(f"Goose PX4 Log Downloader")
    print(f"  source      : {LOGS_BASE}")
    print(f"  limit       : {args.limit}")
    print(f"  mode        : {'crashes only' if args.crashes_only else 'all public logs'}")
    print(f"  browse-start: {args.browse_start}")
    print(f"  index-start : {args.index_start}")
    print(f"  output      : {args.output_dir}")
    if args.dry_run:
        print(f"  [DRY RUN]")
    print()

    count = download_logs(
        limit=args.limit,
        crashes_only=args.crashes_only,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        browse_start=args.browse_start,
        index_start=args.index_start,
    )

    if count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
