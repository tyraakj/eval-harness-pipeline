"""Portable evaluation specification loader and compiler."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from glyph.core.domain_models import Budget, EvaluationSuite, GraderPolicy, SandboxRequirements
from glyph.evaluation.definition import EvaluationDefinition
from glyph.grading.graders import (
    ContainsAllGrader,
    ExactMatchGrader,
    LoopEfficiencyGrader,
    OutcomeStateGrader,
    RetrievalMetricsGrader,
    ToolPolicyGrader,
    TrajectorySubsequenceGrader,
)
from glyph.grading.judges import CalibratedModelJudge
from glyph.grading.rubric import RubricCriterionGrader


class SpecError(ValueError):
    pass


_GRADERS = {
    "exact_match": ExactMatchGrader,
    "contains_all": ContainsAllGrader,
    "tool_policy": ToolPolicyGrader,
    "outcome_state": OutcomeStateGrader,
    "trajectory_subsequence": TrajectorySubsequenceGrader,
    "loop_efficiency": LoopEfficiencyGrader,
    "retrieval_metrics": RetrievalMetricsGrader,
}


@dataclass(frozen=True)
class EvaluationSpec:
    path: Path
    suite: EvaluationSuite
    dataset: Path
    target_factory: str
    artifact: Path
    graders: tuple[dict[str, Any], ...] = ()
    rubric: dict[str, Any] | None = None
    model_judge: dict[str, Any] | None = None
    budget: Budget = field(default_factory=Budget)
    repetitions: int = 1
    sandbox_required: bool = False
    specialized_policy: dict[str, Any] | None = None

    def definition(self) -> EvaluationDefinition:
        target = _load_target(self.target_factory)
        graders = [_build_grader(item) for item in self.graders]
        weights: dict[str, float] = {}
        required: set[str] = set()
        threshold = 1.0
        if self.rubric:
            threshold = float(self.rubric.get("pass_threshold", 1.0))
            for raw in self.rubric.get("criteria", []):
                if not isinstance(raw, dict) or "id" not in raw or "assertion" not in raw:
                    raise SpecError("Each rubric criterion requires id and assertion")
                grader = RubricCriterionGrader(
                    criterion_id=str(raw["id"]),
                    description=str(raw.get("description", raw["id"])),
                    assertion=str(raw["assertion"]),
                    output_path=str(raw.get("output_path", "answer")),
                    expected_path=raw.get("expected_path"),
                    expected=raw.get("expected"),
                    case_sensitive=bool(raw.get("case_sensitive", False)),
                )
                graders.append(grader)
                weights[grader.name] = float(raw.get("weight", 1.0))
                if raw.get("required", False):
                    required.add(grader.name)
        if self.model_judge:
            judge = self.model_judge
            evaluator = _load_callable(str(judge.get("evaluator", "")), "model_judge.evaluator")
            grader = CalibratedModelJudge(
                evaluate=evaluator,
                calibration_id=str(judge.get("calibration_id", "")),
                maximum_cost_usd=float(judge.get("maximum_cost_usd", 0)),
                minimum_score=float(judge.get("minimum_score", 0.5)),
                name=str(judge.get("name", "model_judge")),
                version=str(judge.get("version", "1.0.0")),
            )
            graders.append(grader)
            weights[grader.name] = float(judge.get("weight", 1.0))
            if judge.get("required", False):
                required.add(grader.name)
        if not graders:
            raise SpecError("The spec must define at least one grader or rubric criterion")
        return EvaluationDefinition(
            target=target,
            graders=tuple(graders),
            suite=self.suite,
            budget=self.budget,
            repetitions=self.repetitions,
            grader_policy=GraderPolicy(
                weights=weights, required=frozenset(required), pass_threshold=threshold
            ),
            sandbox_requirements=SandboxRequirements(required=self.sandbox_required),
            specialized_policy=self.specialized_policy,
        )


def load_evaluation_spec(path: Path) -> EvaluationSpec:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SpecError(f"Spec file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise SpecError(f"Invalid YAML: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise SpecError("spec requires schema_version: 1")
    suite_data, target_data = raw.get("suite"), raw.get("target")
    if (
        not isinstance(suite_data, dict)
        or not isinstance(target_data, dict)
        or not target_data.get("factory")
    ):
        raise SpecError("spec requires suite and target.factory")
    root = path.parent.resolve()
    try:
        suite = EvaluationSuite.model_validate(suite_data)
        budget = Budget.model_validate(raw.get("budget", {}))
    except Exception as exc:
        raise SpecError(f"Invalid suite or budget: {exc}") from exc
    rubric = raw.get("rubric")
    if rubric is not None and not isinstance(rubric, dict):
        raise SpecError("rubric must be a mapping")
    model_judge = raw.get("model_judge")
    if model_judge is not None:
        if not isinstance(model_judge, dict) or not model_judge.get("evaluator"):
            raise SpecError("model_judge requires evaluator")
    specialized_policy = raw.get("specialized_policy")
    if isinstance(specialized_policy, str):
        policy_path = root / specialized_policy
        try:
            specialized_policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise SpecError(f"Cannot read specialized_policy: {policy_path}") from exc
    if specialized_policy is not None and not isinstance(specialized_policy, dict):
        raise SpecError("specialized_policy must be a mapping or YAML path")
    graders = raw.get("graders", [])
    if not isinstance(graders, list):
        raise SpecError("graders must be a list")
    for item in graders:
        if not isinstance(item, dict) or item.get("type") not in _GRADERS:
            raise SpecError(
                f"Unknown grader: {item.get('type') if isinstance(item, dict) else item}"
            )
    dataset = root / str(raw.get("dataset", "datasets/evaluation.jsonl"))
    artifact = root / str(raw.get("artifact", "artifacts/results.jsonl"))
    return EvaluationSpec(
        path.resolve(),
        suite,
        dataset,
        str(target_data["factory"]),
        artifact,
        tuple(graders),
        rubric,
        model_judge,
        budget,
        int(raw.get("repetitions", 1)),
        bool(raw.get("sandbox", {}).get("required", False)),
        specialized_policy,
    )


def _build_grader(spec: dict[str, Any]) -> Any:
    values = dict(spec)
    kind = values.pop("type")
    values.pop("name", None)
    kwargs = values.pop("kwargs", {})
    if values:
        kwargs = {**kwargs, **values}
    if kind == "tool_policy" and "allowed_tools" in kwargs:
        kwargs["allowed_tools"] = frozenset(kwargs["allowed_tools"])
    if kind == "trajectory_subsequence" and "expected" in kwargs:
        kwargs["expected"] = tuple(kwargs["expected"])
    return _GRADERS[kind](**kwargs)


def _load_target(reference: str) -> Any:
    factory = _load_callable(reference, "target.factory")
    try:
        target = factory()
    except TypeError as exc:
        raise SpecError(f"Could not load target.factory {reference}: {exc}") from exc
    if not hasattr(target, "execute") or not hasattr(target, "version"):
        raise SpecError("target.factory must return a Glyph Target")
    return target


def _load_callable(reference: str, field_name: str) -> Any:
    if ":" not in reference:
        raise SpecError(f"{field_name} must use module:function syntax")
    module_name, function_name = reference.split(":", 1)
    working_directory = str(Path.cwd())
    if working_directory not in sys.path:
        sys.path.insert(0, working_directory)
    try:
        callable_object = getattr(importlib.import_module(module_name), function_name)
    except (ImportError, AttributeError, TypeError) as exc:
        raise SpecError(f"Could not load {field_name} {reference}: {exc}") from exc
    if not callable(callable_object):
        raise SpecError(f"{field_name} must be callable")
    return callable_object
