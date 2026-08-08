from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

import pytest

from glyph.core.domain_models import EvalCase
from glyph.evaluation.optimizers import DSpyOptimizerAdapter


class CompiledProgram:
    def dump_state(self) -> dict[str, Any]:
        return {"instruction": "Answer precisely", "demos": [{"question": "Q"}]}


class FakeOptimizer:
    def compile(self, program: object, *, trainset: list[object]) -> CompiledProgram:
        assert program == "student"
        assert trainset == [{"question": "Q", "answer": "A"}]
        return CompiledProgram()


@pytest.mark.asyncio
async def test_dspy_adapter_compiles_and_records_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_dspy = ModuleType("dspy")
    monkeypatch.setattr(
        "importlib.import_module", lambda name: fake_dspy
    )
    adapter = DSpyOptimizerAdapter(
        candidate_id="support-prompt-2",
        program_factory=lambda dspy: "student",
        optimizer_factory=lambda dspy: FakeOptimizer(),
        example_builder=lambda case, dspy: {
            "question": case.input["question"],
            "answer": case.expected["answer"],
        },
    )

    result = await adapter.optimize(
        [EvalCase(id="one", input={"question": "Q"}, expected={"answer": "A"})]
    )

    assert isinstance(result.program, CompiledProgram)
    assert result.candidate.optimizer == "dspy"
    assert result.candidate.training_dataset_hash.startswith("sha256:")
    assert result.candidate.program_hash.startswith("sha256:")
    assert result.candidate.program_state == {
        "instruction": "Answer precisely",
        "demos": [{"question": "Q"}],
    }


@pytest.mark.asyncio
async def test_dspy_adapter_enforces_training_case_limit() -> None:
    adapter = DSpyOptimizerAdapter(
        candidate_id="candidate",
        program_factory=lambda dspy: object(),
        optimizer_factory=lambda dspy: object(),
        example_builder=lambda case, dspy: object(),
        max_training_cases=1,
    )

    with pytest.raises(ValueError, match="limit exceeded"):
        await adapter.optimize([EvalCase(id="one", input={}), EvalCase(id="two", input={})])


@pytest.mark.asyncio
async def test_dspy_adapter_bounds_serialized_candidate_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "importlib.import_module", lambda name: ModuleType("dspy")
    )
    adapter = DSpyOptimizerAdapter(
        candidate_id="candidate",
        program_factory=lambda dspy: "student",
        optimizer_factory=lambda dspy: FakeOptimizer(),
        example_builder=lambda case, dspy: {
            "question": case.input["question"],
            "answer": case.expected["answer"],
        },
        max_program_state_chars=10,
    )

    with pytest.raises(ValueError, match="program state exceeds"):
        await adapter.optimize(
            [EvalCase(id="one", input={"question": "Q"}, expected={"answer": "A"})]
        )