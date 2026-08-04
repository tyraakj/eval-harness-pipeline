from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from langgraph_eval.core.models import EvalCase


@dataclass
class Dataset:
    path: Path
    cases: list[EvalCase]


def load_jsonl(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = EvalCase.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"Invalid evaluation case at {path}:{line_number}: {error}") from error
        if case.id in seen:
            raise ValueError(f"Duplicate case ID {case.id!r} at {path}:{line_number}")
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise ValueError(f"Dataset is empty: {path}")
    return cases


def load_dataset(path: Path) -> Dataset:
    cases = load_jsonl(path)
    return Dataset(path=path, cases=cases)
