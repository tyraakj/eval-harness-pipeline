from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from glyph.core.domain_models import (
    ReleaseDecision,
    ReleasePolicy,
    RunSummary,
    SuiteType,
)
from glyph.grading.comparison import Comparison, compare


@dataclass(frozen=True, slots=True)
class ReleaseGate:
    """Coordinate multiple evaluation types before allowing release.
    
    This class implements the release gate pattern inspired by waku's release_gate.py,
    combining deterministic evaluations, regression checks, and optional judge evaluations
    into a unified release decision with detailed audit trail.
    """
    
    policy: ReleasePolicy = field(default_factory=ReleasePolicy)
    
    async def evaluate_release(
        self,
        deterministic_summary: RunSummary,
        *,
        comparison_baseline: Path | None = None,
        judge_summary: RunSummary | None = None,
    ) -> ReleaseDecision:
        """Evaluate whether a release should be allowed based on all available evidence.
        
        Args:
            deterministic_summary: Results from deterministic evaluation runs
            comparison_baseline: Optional path to baseline artifact for regression check
            judge_summary: Optional results from model judge evaluation
            
        Returns:
            ReleaseDecision with detailed rationale and audit trail
        """
        # Evaluate deterministic results
        det_passed, det_rationale = self._evaluate_deterministic(deterministic_summary)
        
        # Evaluate regression check if baseline provided
        reg_passed = True
        reg_rationale = "Regression check not required"
        regression_count = 0
        pass_rate_delta = 0.0
        
        if comparison_baseline is not None and self.policy.require_regression_check:
            comparison = compare(Path(deterministic_summary.artifact_path), comparison_baseline)
            reg_passed, reg_rationale = self._evaluate_regression(comparison)
            regression_count = len(comparison.regressed)
            pass_rate_delta = comparison.pass_rate_delta
        
        # Evaluate judge results if provided
        judge_passed = True
        judge_rationale = "Judge evaluation not required"
        judge_score = 0.0
        judge_cost = 0.0
        
        if judge_summary is not None and self.policy.require_judge:
            judge_passed, judge_rationale = self._evaluate_judge(judge_summary)
            judge_score = judge_summary.average_score
            judge_cost = judge_summary.judge_cost_usd
        
        # Calculate suite-specific pass rates
        suite_summaries = deterministic_summary.suites
        capability_summary = suite_summaries.get(SuiteType.CAPABILITY)
        capability_pass_rate = (
            capability_summary.pass_rate if capability_summary is not None else 0.0
        )
        regression_summary = suite_summaries.get(SuiteType.REGRESSION)
        regression_pass_rate = (
            regression_summary.pass_rate if regression_summary is not None else 0.0
        )
        security_summary = suite_summaries.get(SuiteType.SECURITY)
        security_pass_rate = (
            security_summary.pass_rate if security_summary is not None else 0.0
        )
        
        # Calculate overall error rate
        total_trials = deterministic_summary.total
        error_rate = (
            deterministic_summary.errors / total_trials if total_trials > 0 else 0.0
        )
        
        # Make final decision
        all_required_passed = (
            (not self.policy.require_deterministic or det_passed) and
            (not self.policy.require_regression_check or reg_passed) and
            (not self.policy.require_judge or judge_passed)
        )
        
        if all_required_passed:
            reason = "Release allowed: all required evaluation checks passed"
        else:
            reasons = []
            if self.policy.require_deterministic and not det_passed:
                reasons.append(f"deterministic evaluation failed: {det_rationale}")
            if self.policy.require_regression_check and not reg_passed:
                reasons.append(f"regression check failed: {reg_rationale}")
            if self.policy.require_judge and not judge_passed:
                reasons.append(f"judge evaluation failed: {judge_rationale}")
            reason = "Release blocked: " + "; ".join(reasons)
        
        return ReleaseDecision(
            allowed=all_required_passed,
            reason=reason,
            deterministics_passed=det_passed,
            deterministics_rationale=det_rationale,
            regression_passed=reg_passed,
            regression_rationale=reg_rationale,
            judge_passed=judge_passed,
            judge_rationale=judge_rationale,
            overall_pass_rate=deterministic_summary.pass_rate,
            capability_pass_rate=capability_pass_rate,
            regression_pass_rate=regression_pass_rate,
            security_pass_rate=security_pass_rate,
            error_rate=error_rate,
            regression_count=regression_count,
            pass_rate_delta=pass_rate_delta,
            judge_score=judge_score,
            judge_cost_usd=judge_cost,
        )
    
    def _evaluate_deterministic(self, summary: RunSummary) -> tuple[bool, str]:
        """Evaluate deterministic evaluation results against policy."""
        failures = []
        
        # Check overall pass rate
        if summary.pass_rate < self.policy.minimum_overall_pass_rate:
            failures.append(
                f"overall pass rate {summary.pass_rate:.2%} below threshold "
                f"{self.policy.minimum_overall_pass_rate:.2%}"
            )
        
        # Check suite-specific pass rates (only if suite is present in results)
        suite_summaries = summary.suites
        
        # Only check suites that actually have data in this run
        for suite_type, threshold in [
            (SuiteType.CAPABILITY, self.policy.minimum_capability_pass_rate),
            (SuiteType.REGRESSION, self.policy.minimum_regression_pass_rate),
            (SuiteType.SECURITY, self.policy.minimum_security_pass_rate),
        ]:
            if suite_type in suite_summaries:
                suite_rate = suite_summaries[suite_type].pass_rate
                if suite_rate < threshold:
                    failures.append(
                        f"{suite_type.value} pass rate {suite_rate:.2%} below threshold "
                        f"{threshold:.2%}"
                    )
        
        # Check error rate
        total_trials = summary.total
        error_rate = summary.errors / total_trials if total_trials > 0 else 0.0
        if error_rate > self.policy.maximum_error_rate:
            failures.append(
                f"error rate {error_rate:.2%} exceeds threshold "
                f"{self.policy.maximum_error_rate:.2%}"
            )
        
        if failures:
            return False, "; ".join(failures)
        return True, "All deterministic checks passed"
    
    def _evaluate_regression(self, comparison: Comparison) -> tuple[bool, str]:
        """Evaluate regression check results against policy."""
        failures = []
        
        # Check regression count
        if len(comparison.regressed) > self.policy.maximum_regressions:
            failures.append(
                f"{len(comparison.regressed)} regressions exceed maximum "
                f"{self.policy.maximum_regressions}"
            )
        
        # Check pass rate delta
        if comparison.pass_rate_delta < self.policy.minimum_pass_rate_delta:
            failures.append(
                f"pass rate delta {comparison.pass_rate_delta:+.2%} below minimum "
                f"{self.policy.minimum_pass_rate_delta:+.2%}"
            )
        
        if failures:
            return False, "; ".join(failures)
        return True, "Regression check passed"
    
    def _evaluate_judge(self, summary: RunSummary) -> tuple[bool, str]:
        """Evaluate model judge results against policy."""
        failures = []
        
        # Check judge score
        if summary.average_score < self.policy.minimum_judge_score:
            failures.append(
                f"judge score {summary.average_score:.2%} below threshold "
                f"{self.policy.minimum_judge_score:.2%}"
            )
        
        # Check judge cost
        if summary.judge_cost_usd > self.policy.maximum_judge_cost_usd:
            failures.append(
                f"judge cost ${summary.judge_cost_usd:.2f} exceeds maximum "
                f"${self.policy.maximum_judge_cost_usd:.2f}"
            )
        
        if failures:
            return False, "; ".join(failures)
        return True, "Judge evaluation passed"
    
    def create_strict_policy(self) -> ReleasePolicy:
        """Create a strict release policy for production releases."""
        return ReleasePolicy(
            require_deterministic=True,
            require_regression_check=True,
            require_judge=False,
            minimum_overall_pass_rate=1.0,
            minimum_capability_pass_rate=1.0,
            minimum_regression_pass_rate=1.0,
            minimum_security_pass_rate=1.0,
            maximum_error_rate=0.0,
            maximum_regressions=0,
            minimum_pass_rate_delta=0.0,
        )
    
    def create_development_policy(self) -> ReleasePolicy:
        """Create a lenient release policy for development iterations."""
        return ReleasePolicy(
            require_deterministic=True,
            require_regression_check=False,
            require_judge=False,
            minimum_overall_pass_rate=0.8,
            minimum_capability_pass_rate=0.7,
            minimum_regression_pass_rate=0.9,
            minimum_security_pass_rate=1.0,
            maximum_error_rate=0.1,
            maximum_regressions=5,
            minimum_pass_rate_delta=-0.1,
        )
    
    def create_staging_policy(self) -> ReleasePolicy:
        """Create a balanced release policy for staging environments."""
        return ReleasePolicy(
            require_deterministic=True,
            require_regression_check=True,
            require_judge=False,
            minimum_overall_pass_rate=0.95,
            minimum_capability_pass_rate=0.9,
            minimum_regression_pass_rate=0.95,
            minimum_security_pass_rate=1.0,
            maximum_error_rate=0.05,
            maximum_regressions=2,
            minimum_pass_rate_delta=0.0,
        )
