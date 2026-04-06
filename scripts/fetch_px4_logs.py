#!/usr/bin/env python3
"""Fetch sample PX4 ULog files from the public PX4 Flight Review database.

Usage:
    python scripts/fetch_px4_logs.py --good 10 --crash 10
    python scripts/fetch_px4_logs.py --good 20 --output logs/px4/good_flights
    python scripts/fetch_px4_logs.py --crash 10 --output logs/px4/crashes
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

REVIEW_API = "https://review.px4.io/api"
GOOD_FLIGHTS_DIR = os.path.join("logs", "px4", "good_flights")
CRASHES_DIR = os.path.join("logs", "px4", "crashes")


def fetch_json(url: str) -> list | dict:
    """Fetch JSON from a URL with basic error handling."""
    req = urllib.request.Request(url, headers={"User-Agent": "goose-flight/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def search_logs(search_term: str = "", limit: int = 20) -> list[dict]:
    """Search the PX4 Flight Review for logs matching a term."""
    url = f"{REVIEW_API}/logs?search={urllib.request.quote(search_term)}&limit={limit}"
    try:
        return fetch_json(url)
    except urllib.error.URLError as e:
        print(f"  Warning: Could not search PX4 Flight Review: {e}")
        return []


def get_recent_public_logs(limit: int = 50) -> list[dict]:
    """Get recent public logs from PX4 Flight Review."""
    url = f"{REVIEW_API}/logs?limit={limit}"
    try:
        return fetch_json(url)
    except urllib.error.URLError as e:
        print(f"  Warning: Could not fetch recent logs: {e}")
        return []


def download_log(log_id: str, output_path: str) -> bool:
    """Download a single ULog file by its Flight Review ID."""
    url = f"{REVIEW_API}/upload/{log_id}/log"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "goose-flight/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            with open(output_path, "wb") as f:
                f.write(data)
            size_kb = len(data) / 1024
            print(f"  Downloaded {output_path} ({size_kb:.0f} KB)")
            return True
    except urllib.error.URLError as e:
        print(f"  Failed to download {log_id}: {e}")
        return False


def is_crash_log(log_meta: dict) -> bool:
    """Heuristic: check if a log entry likely represents a crash."""
    desc = (log_meta.get("description", "") or "").lower()
    crash_keywords = ["crash", "fail", "emergency", "land", "flip", "lost", "error", "fall"]
    return any(kw in desc for kw in crash_keywords)


def fetch_good_flights(count: int, output_dir: str) -> int:
    """Fetch logs that appear to be normal/good flights."""
    os.makedirs(output_dir, exist_ok=True)
    print(f"\nSearching for {count} good flight logs...")

    logs = get_recent_public_logs(limit=count * 3)
    good_logs = [log for log in logs if not is_crash_log(log)][:count]

    downloaded = 0
    for log in good_logs:
        log_id = log.get("id", log.get("log_id", ""))
        if not log_id:
            continue
        filename = f"good_flight_{downloaded + 1}_{log_id}.ulg"
        filepath = os.path.join(output_dir, filename)
        if os.path.exists(filepath):
            print(f"  Skipping {filename} (already exists)")
            downloaded += 1
            continue
        if download_log(str(log_id), filepath):
            downloaded += 1
            time.sleep(1)  # Rate limit
        if downloaded >= count:
            break

    print(f"Downloaded {downloaded}/{count} good flight logs to {output_dir}")
    return downloaded


def fetch_crash_logs(count: int, output_dir: str) -> int:
    """Fetch logs that appear to contain crashes or anomalies."""
    os.makedirs(output_dir, exist_ok=True)
    print(f"\nSearching for {count} crash logs...")

    crash_logs: list[dict] = []
    for term in ["crash", "failsafe", "emergency landing", "flip", "lost control"]:
        if len(crash_logs) >= count:
            break
        results = search_logs(term, limit=count)
        crash_logs.extend(results)

    # Deduplicate by ID
    seen: set[str] = set()
    unique_logs: list[dict] = []
    for log in crash_logs:
        log_id = str(log.get("id", log.get("log_id", "")))
        if log_id and log_id not in seen:
            seen.add(log_id)
            unique_logs.append(log)

    downloaded = 0
    for log in unique_logs[:count]:
        log_id = str(log.get("id", log.get("log_id", "")))
        if not log_id:
            continue
        desc = (log.get("description", "") or "unknown").replace(" ", "_")[:30]
        filename = f"crash_{downloaded + 1}_{desc}_{log_id}.ulg"
        # Sanitize filename
        filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
        filepath = os.path.join(output_dir, filename)
        if os.path.exists(filepath):
            print(f"  Skipping {filename} (already exists)")
            downloaded += 1
            continue
        if download_log(log_id, filepath):
            downloaded += 1
            time.sleep(1)  # Rate limit
        if downloaded >= count:
            break

    print(f"Downloaded {downloaded}/{count} crash logs to {output_dir}")
    return downloaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch sample PX4 flight logs")
    parser.add_argument("--good", type=int, default=0, help="Number of good flight logs to fetch")
    parser.add_argument("--crash", type=int, default=0, help="Number of crash logs to fetch")
    parser.add_argument("--output", type=str, default=None, help="Override output directory")
    args = parser.parse_args()

    if args.good == 0 and args.crash == 0:
        print("Specify --good N and/or --crash N")
        sys.exit(1)

    total = 0
    if args.good > 0:
        out = args.output or GOOD_FLIGHTS_DIR
        total += fetch_good_flights(args.good, out)

    if args.crash > 0:
        out = args.output or CRASHES_DIR
        total += fetch_crash_logs(args.crash, out)

    print(f"\nTotal: {total} logs downloaded")


if __name__ == "__main__":
    main()
