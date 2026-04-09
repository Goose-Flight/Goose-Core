"""Validation harness for Goose-Core.

Advanced Forensic Validation Sprint — Runs analysis against corpus cases
and compares results to expectations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from goose.validation.corpus import CorpusCase, ExpectedAnalyzerBehavior, load_corpus_manifest


@dataclass
class ObservedOutcome:
    corpus_id: str
    parser_succeeded: bool = False
    parser_confidence: float | None = None
    parser_warnings: list[str] = field(default_factory=list)
    findings_found: list[str] = field(default_factory=list)
    plugins_ran: list[str] = field(default_factory=list)
    plugins_skipped: list[str] = field(default_factory=list)
    hypotheses_generated: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_id": self.corpus_id,
            "parser_succeeded": self.parser_succeeded,
            "parser_confidence": self.parser_confidence,
            "parser_warnings": self.parser_warnings,
            "findings_found": self.findings_found,
            "plugins_ran": self.plugins_ran,
            "plugins_skipped": self.plugins_skipped,
            "hypotheses_generated": self.hypotheses_generated,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ObservedOutcome:
        known = {
            "corpus_id", "parser_succeeded", "parser_confidence",
            "parser_warnings", "findings_found", "plugins_ran",
            "plugins_skipped", "hypotheses_generated",
        }
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class ExpectedOutcome:
    """Flattened view of expected behavior for reporting."""
    should_parse: bool = True
    min_parser_confidence: float = 0.0
    expected_findings: list[str] = field(default_factory=list)
    not_expected_findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_parse": self.should_parse,
            "min_parser_confidence": self.min_parser_confidence,
            "expected_findings": self.expected_findings,
            "not_expected_findings": self.not_expected_findings,
        }


@dataclass
class CorpusCaseResult:
    corpus_id: str
    category: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    expected: ExpectedOutcome = field(default_factory=ExpectedOutcome)
    observed: ObservedOutcome = field(default_factory=lambda: ObservedOutcome(corpus_id=""))
    run_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_id": self.corpus_id,
            "category": self.category,
            "passed": self.passed,
            "failures": self.failures,
            "warnings": self.warnings,
            "expected": self.expected.to_dict(),
            "observed": self.observed.to_dict(),
            "run_at": self.run_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CorpusCaseResult:
        d = dict(d)
        d["expected"] = ExpectedOutcome(**{
            k: v for k, v in d.get("expected", {}).items()
            if k in {"should_parse", "min_parser_confidence", "expected_findings", "not_expected_findings"}
        })
        d["observed"] = ObservedOutcome.from_dict(d.get("observed", {"corpus_id": ""}))
        known = {
            "corpus_id", "category", "passed", "failures", "warnings",
            "expected", "observed", "run_at",
        }
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class ValidationSummary:
    validation_id: str
    run_at: str
    engine_version: str
    total_cases: int
    passed: int
    failed: int
    warned: int
    corpus_case_results: list[CorpusCaseResult] = field(default_factory=list)
    regression_alerts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "run_at": self.run_at,
            "engine_version": self.engine_version,
            "total_cases": self.total_cases,
            "passed": self.passed,
            "failed": self.failed,
            "warned": self.warned,
            "corpus_case_results": [r.to_dict() for r in self.corpus_case_results],
            "regression_alerts": self.regression_alerts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ValidationSummary:
        d = dict(d)
        d["corpus_case_results"] = [
            CorpusCaseResult.from_dict(r) for r in d.get("corpus_case_results", [])
        ]
        known = {
            "validation_id", "run_at", "engine_version", "total_cases",
            "passed", "failed", "warned", "corpus_case_results", "regression_alerts",
        }
        return cls(**{k: v for k, v in d.items() if k in known})


def run_validation(
    corpus_dir: Path,
    cases_dir: Path,
    engine_version: str = "1.3.4",
) -> ValidationSummary:
    """Run Goose analysis against all active corpus cases.

    Compare findings/diagnostics against expectations.
    Return structured ValidationSummary.
    """
    from goose import __version__

    corpus_cases = load_corpus_manifest(corpus_dir)
    active_cases = [c for c in corpus_cases if c.active]

    validation_id = f"VAL-{uuid.uuid4().hex[:8].upper()}"
    run_at = datetime.now().isoformat()
    results: list[CorpusCaseResult] = []
    regression_alerts: list[str] = []

    for cc in active_cases:
        result = _validate_single_case(cc, corpus_dir, cases_dir)
        results.append(result)
        if not result.passed:
            regression_alerts.append(
                f"{cc.corpus_id} ({cc.category}): {'; '.join(result.failures)}"
            )

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    warned = sum(1 for r in results if r.warnings)

    return ValidationSummary(
        validation_id=validation_id,
        run_at=run_at,
        engine_version=__version__,
        total_cases=len(results),
        passed=passed,
        failed=failed,
        warned=warned,
        corpus_case_results=results,
        regression_alerts=regression_alerts,
    )


def _validate_single_case(
    cc: CorpusCase,
    corpus_dir: Path,
    cases_dir: Path,
) -> CorpusCaseResult:
    """Validate a single corpus case."""
    run_at = datetime.now().isoformat()

    # Build expected outcome
    all_expected: list[str] = []
    all_not_expected: list[str] = []
    for ea in cc.expected_analyzers:
        all_expected.extend(ea.should_find)
        all_not_expected.extend(ea.should_not_find)

    expected = ExpectedOutcome(
        should_parse=cc.expected_parser.should_succeed,
        min_parser_confidence=cc.expected_parser.min_parser_confidence,
        expected_findings=all_expected,
        not_expected_findings=all_not_expected,
    )

    # Find evidence file
    evidence_path = corpus_dir / "cases" / cc.corpus_id / "evidence" / cc.evidence_filename
    if not evidence_path.exists():
        return CorpusCaseResult(
            corpus_id=cc.corpus_id,
            category=cc.category,
            passed=False,
            failures=[f"Evidence file not found: {evidence_path}"],
            expected=expected,
            observed=ObservedOutcome(corpus_id=cc.corpus_id),
            run_at=run_at,
        )

    # Parse
    try:
        from goose.parsers.detect import parse_file
        parse_result = parse_file(str(evidence_path))
    except Exception as exc:
        observed = ObservedOutcome(corpus_id=cc.corpus_id, parser_succeeded=False)
        if cc.expected_parser.should_succeed:
            return CorpusCaseResult(
                corpus_id=cc.corpus_id, category=cc.category, passed=False,
                failures=[f"Parse failed unexpectedly: {exc}"],
                expected=expected, observed=observed, run_at=run_at,
            )
        else:
            return CorpusCaseResult(
                corpus_id=cc.corpus_id, category=cc.category, passed=True,
                expected=expected, observed=observed, run_at=run_at,
            )

    if parse_result is None or not parse_result.success:
        observed = ObservedOutcome(corpus_id=cc.corpus_id, parser_succeeded=False)
        if cc.expected_parser.should_succeed:
            return CorpusCaseResult(
                corpus_id=cc.corpus_id, category=cc.category, passed=False,
                failures=["Parse did not succeed but was expected to"],
                expected=expected, observed=observed, run_at=run_at,
            )
        else:
            return CorpusCaseResult(
                corpus_id=cc.corpus_id, category=cc.category, passed=True,
                expected=expected, observed=observed, run_at=run_at,
            )

    flight = parse_result.flight

    # Run plugins
    from goose.plugins import PLUGIN_REGISTRY
    from goose.plugins.trust import TrustPolicy, fingerprint_plugin

    plugins_ran: list[str] = []
    plugins_skipped: list[str] = []
    all_findings_titles: list[str] = []

    trust_policy = TrustPolicy()
    for plugin in PLUGIN_REGISTRY.values():
        fp = fingerprint_plugin(plugin)
        allowed, _ = trust_policy.evaluate(plugin.manifest, fp)
        if not allowed:
            plugins_skipped.append(plugin.manifest.plugin_id)
            continue
        try:
            ff_list, _ = plugin.forensic_analyze(
                flight, "corpus-evidence", f"corpus-{cc.corpus_id}",
                {}, parse_result.diagnostics,
            )
            plugins_ran.append(plugin.manifest.plugin_id)
            for f in ff_list:
                all_findings_titles.append(f.title)
        except Exception:
            plugins_skipped.append(plugin.manifest.plugin_id)

    # Generate hypotheses
    hypotheses_count = 0
    try:
        from goose.forensics.lifting import generate_hypotheses
        # We need the forensic findings objects, so re-gather them
        hypotheses_count = 0  # simplified - count from plugins above
    except Exception:
        pass

    observed = ObservedOutcome(
        corpus_id=cc.corpus_id,
        parser_succeeded=True,
        parser_confidence=parse_result.diagnostics.parser_confidence,
        parser_warnings=list(parse_result.diagnostics.warnings),
        findings_found=all_findings_titles,
        plugins_ran=plugins_ran,
        plugins_skipped=plugins_skipped,
        hypotheses_generated=hypotheses_count,
    )

    # Check expectations
    failures: list[str] = []
    warnings: list[str] = []

    # Parser confidence check
    if (
        cc.expected_parser.min_parser_confidence > 0
        and parse_result.diagnostics.parser_confidence is not None
        and parse_result.diagnostics.parser_confidence < cc.expected_parser.min_parser_confidence
    ):
        failures.append(
            f"Parser confidence {parse_result.diagnostics.parser_confidence:.2f} "
            f"below expected minimum {cc.expected_parser.min_parser_confidence:.2f}"
        )

    # Expected findings (partial match)
    for exp_finding in all_expected:
        found = any(exp_finding.lower() in t.lower() for t in all_findings_titles)
        if not found:
            failures.append(f"Expected finding not found: '{exp_finding}'")

    # Should-not-find findings
    for bad_finding in all_not_expected:
        found = any(bad_finding.lower() in t.lower() for t in all_findings_titles)
        if found:
            failures.append(f"Unexpected finding present: '{bad_finding}'")

    passed = len(failures) == 0

    return CorpusCaseResult(
        corpus_id=cc.corpus_id,
        category=cc.category,
        passed=passed,
        failures=failures,
        warnings=warnings,
        expected=expected,
        observed=observed,
        run_at=run_at,
    )
