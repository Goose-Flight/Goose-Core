"""Download a few small ULG files from logs.px4.io for website testing.

Targets logs with short durations (likely under 10MB).
Saves to logs/test_files/
"""
import urllib.request
import urllib.parse
import json
import os
import sys

import re

LOGS_BASE = "https://logs.px4.io"
BROWSE_URL = f"{LOGS_BASE}/browse_data_retrieval"
DOWNLOAD_URL = f"{LOGS_BASE}/download"
UA = "goose-flight/1.0 (research; test-download)"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "logs", "test_files")
os.makedirs(DEST, exist_ok=True)

TARGET_COUNT = 5
MAX_SIZE_MB = 10
downloaded = 0
checked = 0


def _build_browse_url(start: int, length: int) -> str:
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
    return BROWSE_URL + "?" + urllib.parse.urlencode(params)


def _extract_log_id(html_cell: str) -> str | None:
    m = re.search(r'log=([0-9a-f-]{36})', html_cell)
    return m.group(1) if m else None


def _extract_text(html_cell: str) -> str:
    m = re.search(r'>([^<]+)<', html_cell)
    return m.group(1).strip() if m else str(html_cell).strip()


def _parse_duration_sec(duration_str: str) -> int:
    """Parse durations like '24s', '2m42s', '1h5m', '0:02:42'."""
    try:
        s = str(duration_str).strip()
        # Format: Xh Ym Zs
        total = 0
        m = re.search(r'(\d+)h', s)
        if m:
            total += int(m.group(1)) * 3600
        m = re.search(r'(\d+)m', s)
        if m:
            total += int(m.group(1)) * 60
        m = re.search(r'(\d+)s', s)
        if m:
            total += int(m.group(1))
        if total > 0:
            return total
        # Fallback: colon-separated
        parts = s.split(":")
        return sum(int(p) * (60 ** (len(parts) - 1 - i)) for i, p in enumerate(parts))
    except Exception:
        return 9999


print(f"Saving test ULG files to: {DEST}")
print(f"Target: {TARGET_COUNT} files under {MAX_SIZE_MB}MB each")
print()

start = 0
PAGE_SIZE = 100

while downloaded < TARGET_COUNT and start < 2000:
    url = _build_browse_url(start, PAGE_SIZE)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"Browse start={start} failed: {e}")
        break

    rows = data.get("data", [])
    if not rows:
        break

    for row in rows:
        log_id = _extract_log_id(str(row[1])) if len(row) > 1 else None
        if not log_id:
            continue

        duration = str(row[7]) if len(row) > 7 else ""
        hw = _extract_text(str(row[5])) if len(row) > 5 else "unknown"

        # Skip long flights (likely large files)
        if _parse_duration_sec(duration) > 90:
            continue

        checked += 1
        dl_url = f"{DOWNLOAD_URL}?log={urllib.parse.quote(log_id)}"
        req2 = urllib.request.Request(dl_url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req2, timeout=60) as r:
                data_bytes = r.read()
        except Exception as e:
            print(f"  SKIP {log_id[:8]}  download error: {e}")
            continue

        size_mb = len(data_bytes) / (1024 * 1024)
        if size_mb > MAX_SIZE_MB:
            print(f"  SKIP {log_id[:8]}  {size_mb:.1f}MB (too large)")
            continue
        if len(data_bytes) < 1024:
            print(f"  SKIP {log_id[:8]}  too small (corrupt?)")
            continue

        hw_safe = hw.replace("/", "_").replace(" ", "_")[:20]
        fname = f"test_{downloaded+1:02d}_{hw_safe}_{log_id[:8]}.ulg"
        fpath = os.path.join(DEST, fname)
        with open(fpath, "wb") as f:
            f.write(data_bytes)

        downloaded += 1
        print(f"  [{downloaded}/{TARGET_COUNT}] saved {fname}  ({size_mb:.2f}MB)")
        if downloaded >= TARGET_COUNT:
            break

    start += PAGE_SIZE

print()
print(f"Done: {downloaded} files saved, {checked} candidates checked.")
