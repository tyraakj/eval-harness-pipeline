from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Protocol, cast

from pydantic import Field, JsonValue

from langgraph_eval.models import EvalCase, FrozenModel
from langgraph_eval.utils import canonical_json, content_hash, sanitize


class OptimizationCandidate(FrozenModel):
    candidate_id: str = Field(
        min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    optimizer: str
    optimizer_version: str
    training_dataset_hash: str
    program_hash: str
    program_state: JsonValue
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    candidate: OptimizationCandidate
    program: Any


class Optimizer(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def optimize(self, cases: Sequence[EvalCase]) -> OptimizationResult: ...


DSpyFactory = Callable[[ModuleType], Any]
DSpyExampleBuilder = Callable[[EvalCase, ModuleType], Any]
ProgramStateExtractor = Callable[[Any], Any]


@dataclass(frozen=True, slots=True)
class DSpyOptimizerAdapter:
    candidate_id: str
    program_factory: DSpyFactory
    optimizer_factory: DSpyFactory
    example_builder: DSpyExampleBuilder
    state_extractor: ProgramStateExtractor | None = None
    max_training_cases: int = 1_000
    max_program_state_chars: int = 1_000_000
    metadata: dict[str, JsonValue] | None = None
    name: str = "dspy"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if self.max_training_cases < 1:
            raise ValueError("max_training_cases must be at least one")
        if self.max_program_state_chars < 1:
            raise ValueError("max_program_state_chars must be at least one")

    async def optimize(self, cases: Sequence[EvalCase]) -> OptimizationResult:
        if not cases:
            raise ValueError("DSPy optimization requires at least one training case")
        if len(cases) > self.max_training_cases:
            raise ValueError(
                f"Training case limit exceeded ({len(cases)} > {self.max_training_cases})"
            )
        return await asyncio.to_thread(self._compile, tuple(cases))

    def _compile(self, cases: tuple[EvalCase, ...]) -> OptimizationResult:
        try:
            dspy = importlib.import_module("dspy")
        except ImportError as error:
            raise RuntimeError(
                "DSPy optimization requires the optional 'dspy' extra"
            ) from error

        program = self.program_factory(dspy)
        optimizer = self.optimizer_factory(dspy)
        trainset = [self.example_builder(case, dspy) for case in cases]
        compile_method = getattr(optimizer, "compile", None)
        if not callable(compile_method):
            raise TypeError("DSPy optimizer must provide a callable compile method")
        compiled_program = compile_method(program, trainset=trainset)
        raw_state = self._extract_state(compiled_program)
        program_state = cast(JsonValue, sanitize(raw_state))
        if len(canonical_json(program_state)) > self.max_program_state_chars:
            raise ValueError(
                f"Compiled program state exceeds {self.max_program_state_chars} characters"
            )
        candidate = OptimizationCandidate(
            candidate_id=self.candidate_id,
            optimizer=self.name,
            optimizer_version=self.version,
            training_dataset_hash=content_hash(
                [case.model_dump(mode="json") for case in cases]
            ),
            program_hash=content_hash(program_state),
            program_state=program_state,
            metadata=self.metadata or {},
        )
        return OptimizationResult(candidate=candidate, program=compiled_program)

    def _extract_state(self, program: Any) -> Any:
        if self.state_extractor is not None:
            return self.state_extractor(program)
        dump_state = getattr(program, "dump_state", None)
        if callable(dump_state):
            return dump_state()
        raise TypeError(
            "Compiled DSPy program does not expose dump_state; provide state_extractor"
        )