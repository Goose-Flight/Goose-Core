"""Launch multiple stream_analyze workers as detached Windows processes.

Each worker gets a high --limit so it runs for hours, not just 100 logs.
Workers skip already-done log IDs via PRIMARY KEY, so offset partitioning
avoids redundant downloads — but overlaps are safe.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYTHON = r"C:\Python314\python.exe"
SCRIPT = str(ROOT / "scripts" / "stream_analyze.py")
LOGS = ROOT / "logs"

# All 4 workers covering 371K public logs. --resume skips already-done IDs.
workers = [
    {"offset": 0,      "limit": 93000,  "log": "worker_0k"},
    {"offset": 93000,  "limit": 100000, "log": "worker_93k"},
    {"offset": 186000, "limit": 100000, "log": "worker_186k"},
    {"offset": 279000, "limit": 100000, "log": "worker_279k"},
]

CREATION_FLAGS = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

for w in workers:
    cmd = [
        PYTHON, "-u", SCRIPT,
        "--resume",
        "--offset", str(w["offset"]),
        "--limit",  str(w["limit"]),
    ]

    stdout = open(LOGS / f"{w['log']}.log", "w", buffering=1)
    stderr = open(LOGS / f"{w['log']}_err.log", "w", buffering=1)

    proc = subprocess.Popen(
        cmd,
        stdout=stdout,
        stderr=stderr,
        cwd=str(ROOT),
        creationflags=CREATION_FLAGS,
        close_fds=True,
    )
    print(f"Launched {w['log']} (offset={w['offset']} limit={w['limit']}) PID={proc.pid}")
