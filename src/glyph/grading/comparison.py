from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from glyph.core.domain_models import TrialRecord


@dataclass(frozen=True, slots=True)
class Comparison:
    common_cases: int
    improved: tuple[str, ...]
    regressed: tuple[str, ...]
    unchanged: tuple[str, ...]
    candidate_pass_rate: float
    baseline_pass_rate: float

    @property
    def pass_rate_delta(self) -> float:
        return self.candidate_pass_rate - self.baseline_pass_rate


def load_trials(path: Path) -> dict[str, TrialRecord]:
    trials: dict[str, TrialRecord] = {}
    for line_number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if "trial_id" not in payload:
            continue
        record = TrialRecord.model_validate(payload)
        if record.case_id in trials:
            raise ValueError(f"Duplicate case {record.case_id!r} at {path}:{line_number}")
        trials[record.case_id] = record
    return trials


def compare(candidate_path: Path, baseline_path: Path) -> Comparison:
    candidate = load_trials(candidate_path)
    baseline = load_trials(baseline_path)
    common = sorted(candidate.keys() & baseline.keys())
    if not common:
        raise ValueError("Candidate and baseline have no common case IDs")

    def passed(record: TrialRecord) -> bool:
        return record.status.value == "passed"

    improved = tuple(
        case_id
        for case_id in common
        if passed(candidate[case_id]) and not passed(baseline[case_id])
    )
    regressed = tuple(
        case_id
        for case_id in common
        if not passed(candidate[case_id]) and passed(baseline[case_id])
    )
    unchanged = tuple(
        case_id
        for case_id in common
        if passed(candidate[case_id]) == passed(baseline[case_id])
    )
    return Comparison(
        common_cases=len(common),
        improved=improved,
        regressed=regressed,
        unchanged=unchanged,
        candidate_pass_rate=sum(passed(candidate[case_id]) for case_id in common) / len(common),
        baseline_pass_rate=sum(passed(baseline[case_id]) for case_id in common) / len(common),
    )
