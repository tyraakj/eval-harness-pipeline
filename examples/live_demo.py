"""A local delayed target for verifying Glyph's live terminal event stream."""

from __future__ import annotations

import asyncio
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from glyph.core.domain_models import Budget, SandboxRequirements
from glyph.evaluation.definition import EvaluationDefinition
from glyph.grading.graders import ContainsAllGrader
from glyph.targets.langgraph_target import LangGraphTarget


class State(TypedDict, total=False):
    question: str
    answer: str


async def answer(state: State) -> State:
    await asyncio.sleep(1)
    return {"answer": f"Processed: {state['question']}"}


def create_evaluation() -> EvaluationDefinition:
    builder = StateGraph(State)
    builder.add_node("answer", answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    return EvaluationDefinition(
        target=LangGraphTarget(
            builder.compile(),
            version="live-demo@1.0.0",
            output_builder=lambda state: {"answer": state["answer"]},
        ),
        graders=(ContainsAllGrader(),),
        budget=Budget(timeout_seconds=10, max_concurrency=1),
        sandbox_requirements=SandboxRequirements(required=False),
    )
