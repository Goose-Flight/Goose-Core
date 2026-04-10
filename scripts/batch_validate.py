#!/usr/bin/env python3
"""Batch validation runner — push every log through Goose and report results.

Usage:
    python scripts/batch_validate.py                          # all logs
    python scripts/batch_validate.py --dir logs/px4/crashes  # crashes only
    python scripts/batch_validate.py --limit 50              # first 50
    python scripts/batch_validate.py --profile research      # specific profile
    python scripts/batch_validate.py --out results.csv       # save CSV
    python scripts/batch_validate.py --workers 4             # parallel workers
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _analyze_one(log_path: Path, profile: str) -> dict:
    """Parse + analyze a single log. Returns a result dict."""
    start = time.time()
    result: dict = {
        "file": log_path.name,
        "path": str(log_path),
        "size_mb": round(log_path.stat().st_size / 1_048_576, 1),
        "profile": profile,
        "ok": False,
        "parse_ok": False,
        "duration_sec": None,
        "vehicle_type": None,
        "hardware": None,
        "firmware": None,
        "primary_mode": None,
        "crashed": None,
        "score": None,
        "findings_total": 0,
        "critical": 0,
        "warning": 0,
        "info": 0,
        "hypotheses": 0,
        "signal_streams": 0,
        "has_gps": False,
        "has_attitude": False,
        "has_battery": False,
        "has_motors": False,
        "has_vibration": False,
        "error": None,
        "elapsed_sec": None,
    }

    try:
        from goose.parsers.ulog import ULogParser
        parser = ULogParser()
        parse_result = parser.parse(str(log_path))

        if parse_result is None or parse_result.flight is None:
            result["error"] = "parse returned None"
            return result

        result["parse_ok"] = True
        flight = parse_result.flight
        meta = flight.metadata

        result["duration_sec"] = round(meta.duration_sec, 1)
        result["vehicle_type"] = meta.vehicle_type
        result["hardware"] = meta.hardware or meta.autopilot
        result["firmware"] = meta.firmware_version
        result["primary_mode"] = flight.primary_mode
        result["crashed"] = flight.crashed

        result["has_gps"] = not flight.gps.empty
        result["has_attitude"] = not flight.attitude.empty
        result["has_battery"] = not flight.battery.empty
        result["has_motors"] = not flight.motors.empty
        result["has_vibration"] = not flight.vibration.empty

        # Run plugins
        from goose.plugins.registry import load_plugins
        from goose.core.scoring import compute_overall_score
        from goose.forensics.profiles import get_profile

        try:
            cfg = get_profile(profile)
            plugin_ids = set(cfg.plugin_ids) if cfg.plugin_ids else None
        except Exception:
            plugin_ids = None

        all_plugins = load_plugins()
        plugins = [p for p in all_plugins if plugin_ids is None or p.name in plugin_ids]

        thin_findings = []
        for plugin in plugins:
            try:
                findings = plugin.analyze(flight, {})
                thin_findings.extend(findings)
            except Exception:
                pass

        score = compute_overall_score(thin_findings)
        result["score"] = score
        result["findings_total"] = len(thin_findings)
        result["critical"] = sum(1 for f in thin_findings if f.severity == "critical")
        result["warning"] = sum(1 for f in thin_findings if f.severity == "warning")
        result["info"] = sum(1 for f in thin_findings if f.severity == "info")

        # Signal quality
        if parse_result.diagnostics:
            result["signal_streams"] = len(parse_result.diagnostics.stream_coverage)

        result["ok"] = True

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["error_trace"] = traceback.format_exc()[-400:]

    result["elapsed_sec"] = round(time.time() - start, 2)
    return result


def _collect_logs(dirs: list[Path], limit: int | None) -> list[Path]:
    logs = []
    for d in dirs:
        logs.extend(sorted(d.glob("*.ulg")))
        logs.extend(sorted(d.glob("*.bin")))
    if limit:
        logs = logs[:limit]
    return logs


def _print_row(r: dict, idx: int, total: int) -> None:
    status = "OK" if r["ok"] else "ERR"
    crash = "CRASH" if r.get("crashed") else ("ok" if r.get("parse_ok") else "?")
    score = f"score={r['score']}" if r["score"] is not None else "no score"
    findings = f"C{r['critical']}/W{r['warning']}/I{r['info']}"
    err = f"  ERR: {r['error'][:60]}" if r.get("error") else ""
    print(f"[{idx:>3}/{total}] {status} {r['file'][:45]:<46} {crash:<6} {score:<10} {findings}{err}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-analyze flight logs through Goose")
    parser.add_argument("--dir", nargs="+", help="Directories to scan (default: logs/px4)")
    parser.add_argument("--limit", type=int, default=None, help="Max logs to process")
    parser.add_argument("--profile", default="default", help="Analysis profile")
    parser.add_argument("--out", default=None, help="CSV output path")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers (careful with memory)")
    parser.add_argument("--failures-only", action="store_true", help="Only print failures/errors")
    args = parser.parse_args()

    scan_dirs = []
    if args.dir:
        scan_dirs = [Path(d) for d in args.dir]
    else:
        default = ROOT / "logs" / "px4"
        for sub in ("crashes", "good_flights"):
            p = default / sub
            if p.exists():
                scan_dirs.append(p)

    logs = _collect_logs(scan_dirs, args.limit)
    if not logs:
        print("No .ulg/.bin files found.")
        return

    total = len(logs)
    print(f"\nGoose Batch Validator")
    print(f"  logs    : {total}")
    print(f"  profile : {args.profile}")
    print(f"  workers : {args.workers}")
    print(f"  dirs    : {[str(d) for d in scan_dirs]}")
    print()

    results = []
    t0 = time.time()

    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(_analyze_one, log, args.profile): (i+1, log) for i, log in enumerate(logs)}
            done = 0
            for fut in as_completed(futures):
                idx, log = futures[fut]
                done += 1
                r = fut.result()
                results.append(r)
                if not args.failures_only or not r["ok"]:
                    _print_row(r, done, total)
    else:
        for i, log in enumerate(logs):
            r = _analyze_one(log, args.profile)
            results.append(r)
            if not args.failures_only or not r["ok"]:
                _print_row(r, i + 1, total)

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    crashed = [r for r in ok if r.get("crashed")]
    scores = [r["score"] for r in ok if r["score"] is not None]

    print(f"\n{'-'*70}")
    print(f"Results: {len(ok)}/{total} parsed successfully  |  {len(failed)} errors  |  {elapsed:.0f}s total")
    if scores:
        avg = sum(scores) / len(scores)
        print(f"Score:   avg={avg:.0f}  min={min(scores)}  max={max(scores)}")
    if ok:
        crash_rate = len(crashed) / len(ok) * 100
        print(f"Crashes: {len(crashed)}/{len(ok)} detected ({crash_rate:.0f}%)")
        c_tot = sum(r["critical"] for r in ok)
        w_tot = sum(r["warning"] for r in ok)
        print(f"Findings: {c_tot} critical, {w_tot} warning across {len(ok)} logs")

    if failed:
        print(f"\nErrors ({len(failed)}):")
        for r in failed[:20]:
            print(f"  {r['file']}: {r.get('error','?')[:80]}")

    # ── CSV ───────────────────────────────────────────────────────────────────
    if args.out:
        out_path = Path(args.out)
        fields = [
            "file", "size_mb", "profile", "ok", "parse_ok", "duration_sec",
            "vehicle_type", "hardware", "firmware", "primary_mode", "crashed",
            "score", "findings_total", "critical", "warning", "info",
            "hypotheses", "signal_streams",
            "has_gps", "has_attitude", "has_battery", "has_motors", "has_vibration",
            "elapsed_sec", "error",
        ]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(results)
        print(f"\nCSV saved: {out_path} ({len(results)} rows)")


if __name__ == "__main__":
    main()
