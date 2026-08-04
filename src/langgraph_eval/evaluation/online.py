from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

from langgraph_eval.security.contracts import Grader, OnlineCostLedger
from langgraph_eval.core.models import (
    EvalCase,
    OnlineEvaluationDecision,
    OnlineEvaluationPolicy,
    OnlineEvaluationStatus,
    TargetResult,
)
from langgraph_eval.utils.utils import sanitize, sanitize_text


class InMemoryOnlineCostLedger:
    """Process-local ledger for development; production hosts should inject durable storage."""

    def __init__(self) -> None:
        self._reserved: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def try_reserve(self, period: str, amount_usd: float, limit_usd: float) -> bool:
        async with self._lock:
            current = self._reserved.get(period, 0.0)
            if current + amount_usd > limit_usd:
                return False
            self._reserved[period] = current + amount_usd
            return True


class OnlineEvaluator:
    def __init__(
        self,
        *,
        policy: OnlineEvaluationPolicy,
        graders: tuple[Grader, ...],
        cost_ledger: OnlineCostLedger | None = None,
    ) -> None:
        if policy.enabled and not graders:
            raise ValueError("Enabled online evaluation requires at least one grader")
        self.policy = policy
        self.graders = graders
        self.cost_ledger = cost_ledger or InMemoryOnlineCostLedger()

    async def evaluate(
        self,
        *,
        trace_id: str,
        project: str,
        observed_at: datetime,
        case: EvalCase,
        result: TargetResult,
    ) -> OnlineEvaluationDecision:
        if not self.policy.enabled:
            return self._decision(
                trace_id, OnlineEvaluationStatus.DISABLED, False, "Online evaluation is disabled"
            )
        if project != self.policy.allowed_project:
            return self._decision(
                trace_id,
                OnlineEvaluationStatus.REJECTED,
                False,
                "Project is not permitted by online evaluation policy",
            )
        normalized_observed_at = (
            observed_at.replace(tzinfo=UTC)
            if observed_at.tzinfo is None
            else observed_at.astimezone(UTC)
        )
        now = datetime.now(UTC)
        retention_days = self.policy.retention_days
        if retention_days is None or normalized_observed_at < now - timedelta(days=retention_days):
            return self._decision(
                trace_id,
                OnlineEvaluationStatus.REJECTED,
                False,
                "Observation is outside the approved retention window",
            )
        if normalized_observed_at > now + timedelta(minutes=5):
            return self._decision(
                trace_id,
                OnlineEvaluationStatus.REJECTED,
                False,
                "Observation timestamp is in the future",
            )
        if not self._sampled(trace_id):
            return self._decision(
                trace_id,
                OnlineEvaluationStatus.NOT_SAMPLED,
                False,
                "Trace was not selected by deterministic sampling",
            )

        reserved_cost = sum(
            max(0.0, float(getattr(grader, "maximum_cost_usd", 0.0)))
            for grader in self.graders
        )
        monthly_limit = self.policy.maximum_monthly_cost_usd
        if monthly_limit is None:
            return self._decision(
                trace_id,
                OnlineEvaluationStatus.REJECTED,
                True,
                "Monthly cost policy is missing",
            )
        period = normalized_observed_at.strftime("%Y-%m")
        if not await self.cost_ledger.try_reserve(period, reserved_cost, monthly_limit):
            return OnlineEvaluationDecision(
                trace_id=trace_id,
                status=OnlineEvaluationStatus.BUDGET_EXCEEDED,
                sampled=True,
                reason="Monthly online evaluation cost budget would be exceeded",
                reserved_cost_usd=reserved_cost,
            )
        try:
            async with asyncio.timeout(self.policy.evaluator_timeout_seconds):
                grades = tuple(
                    await asyncio.gather(
                        *(grader.grade(case, result) for grader in self.graders)
                    )
                )
        except TimeoutError:
            return OnlineEvaluationDecision(
                trace_id=trace_id,
                status=OnlineEvaluationStatus.ERROR,
                sampled=True,
                reason="Online evaluation timed out",
                reserved_cost_usd=reserved_cost,
            )
        except Exception as error:
            return OnlineEvaluationDecision(
                trace_id=trace_id,
                status=OnlineEvaluationStatus.ERROR,
                sampled=True,
                reason=sanitize_text(f"{type(error).__name__}: {error}")[:2_000],
                reserved_cost_usd=reserved_cost,
            )
        sanitized_grades = tuple(
            grade.model_copy(
                update={
                    "reason": sanitize_text(grade.reason)[:2_000],
                    "evidence": sanitize(grade.evidence),
                }
            )
            for grade in grades
        )
        return OnlineEvaluationDecision(
            trace_id=trace_id,
            status=OnlineEvaluationStatus.EVALUATED,
            sampled=True,
            reason="Online evaluation completed",
            grades=sanitized_grades,
            reserved_cost_usd=reserved_cost,
        )

    def _sampled(self, trace_id: str) -> bool:
        review_id = self.policy.privacy_review_id or ""
        digest = hashlib.sha256(f"{review_id}:{trace_id}".encode()).digest()
        fraction = int.from_bytes(digest, "big") / (1 << (len(digest) * 8))
        return fraction < self.policy.sampling_rate

    @staticmethod
    def _decision(
        trace_id: str,
        status: OnlineEvaluationStatus,
        sampled: bool,
        reason: str,
    ) -> OnlineEvaluationDecision:
        return OnlineEvaluationDecision(
            trace_id=trace_id, status=status, sampled=sampled, reason=reason
        )