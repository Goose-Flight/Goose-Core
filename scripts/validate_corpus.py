"""Standalone CLI to run the Goose validation harness against the seeded corpus.

Usage:
    python scripts/validate_corpus.py

Prints a human-readable summary and returns a non-zero exit code if any
corpus case fails.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the goose package importable when run from repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from goose import __version__  # noqa: E402
from goose.validation.harness import run_validation  # noqa: E402
from goose.validation.quality import compute_quality_report  # noqa: E402


def main() -> int:
    corpus_dir = REPO_ROOT / "tests" / "corpus"
    cases_dir = REPO_ROOT / "cases"

    if not corpus_dir.exists():
        print(f"ERROR: corpus dir not found: {corpus_dir}")
        return 2

    print(f"Goose v{__version__} — running corpus validation")
    print(f"Corpus dir: {corpus_dir}")
    print("-" * 70)

    summary = run_validation(corpus_dir, cases_dir, engine_version=__version__)

    print(f"Validation ID: {summary.validation_id}")
    print(f"Total cases:   {summary.total_cases}")
    print(f"  Passed:      {summary.passed}")
    print(f"  Failed:      {summary.failed}")
    print(f"  Warned:      {summary.warned}")
    print()

    for result in summary.corpus_case_results:
        badge = "PASS" if result.passed else "FAIL"
        print(f"  [{badge}] {result.corpus_id} ({result.category})")
        for failure in result.failures:
            print(f"         - {failure}")

    if summary.regression_alerts:
        print()
        print("REGRESSION ALERTS:")
        for alert in summary.regression_alerts:
            print(f"  * {alert}")

    print()
    print("-" * 70)
    quality = compute_quality_report(summary)
    print(f"Quality report: {quality.summary}")
    for snap in quality.analyzers:
        if snap.true_positives or snap.false_positives or snap.false_negatives:
            print(
                f"  {snap.plugin_id}: TP={snap.true_positives} FP={snap.false_positives} "
                f"FN={snap.false_negatives} precision={snap.precision} recall={snap.recall}"
            )

    # Also write a JSON artifact for CI consumption
    artifact = REPO_ROOT / "validation_results" / "corpus_validation.json"
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(
        json.dumps({
            "summary": summary.to_dict(),
            "quality_report": quality.to_dict(),
        }, indent=2),
        encoding="utf-8",
    )
    print(f"Artifact: {artifact}")

    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
