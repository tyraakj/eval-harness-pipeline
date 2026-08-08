from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from glyph.core.domain_models import Budget, SandboxRequirements
from glyph.evaluation.definition import EvaluationDefinition
from glyph.grading.graders import ContainsAllGrader
from glyph.targets.langgraph_target import LangGraphTarget


class State(TypedDict, total=False):
    question: str
    answer: str


def answer(state: State) -> State:
    return {"answer": f"Deterministic response: {state['question']}"}


def build_graph():
    builder = StateGraph(State)
    builder.add_node("answer", answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    return builder.compile()


def create_evaluation() -> EvaluationDefinition:
    return EvaluationDefinition(
        target=LangGraphTarget(build_graph(), version="simple-graph@1.0.0"),
        graders=(ContainsAllGrader(),),
        budget=Budget(timeout_seconds=10, max_concurrency=2),
        sandbox_requirements=SandboxRequirements(required=False),
    )
