from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import Field, JsonValue

from langgraph_eval.models import EvalCase, FrozenModel, Grade, TargetResult


class JudgeDecision(FrozenModel):
    score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    cost_usd: float = Field(default=0, ge=0)
    evidence: dict[str, JsonValue] = Field(default_factory=dict)


JudgeCallable = Callable[[EvalCase, TargetResult], Awaitable[JudgeDecision]]


@dataclass(frozen=True, slots=True)
class CalibratedModelJudge:
    evaluate: JudgeCallable
    calibration_id: str
    maximum_cost_usd: float
    minimum_score: float = 0.5
    name: str = "model_judge"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.calibration_id:
            raise ValueError("A model judge requires a calibration ID")
        if self.maximum_cost_usd < 0:
            raise ValueError("maximum_cost_usd cannot be negative")
        if not 0 <= self.minimum_score <= 1:
            raise ValueError("minimum_score must be between zero and one")

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        decision = await self.evaluate(case, result)
        passed = decision.score >= self.minimum_score
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=decision.score,
            reason=decision.reason,
            evidence={"calibration_id": self.calibration_id, **decision.evidence},
            cost_usd=decision.cost_usd,
        )