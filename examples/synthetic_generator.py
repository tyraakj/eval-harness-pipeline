"""A deterministic example generator for exercising the review workflow.

It deliberately creates drafts only. Replace it with an application-owned LLM
or grounded generator before promoting cases for a real evaluation.
"""

from glyph.core.domain_models import EvalCase
from glyph.generation import GenerationSpec


class ExampleSyntheticGenerator:
    name = "example-template-generator"
    version = "1.0.0"

    def generate(self, spec: GenerationSpec) -> list[EvalCase]:
        suites = [suite for suite, count in spec.suite_counts.items() for _ in range(count)]
        return [
            EvalCase(
                id=f"generated-{index + 1:03d}",
                input={"request": f"{spec.seed_phrase} â€” scenario {index + 1}"},
                expected={"review_required": True},
                suite=suite,
                tags=spec.tags | frozenset({"synthetic", suite.value}),
                metadata={"generation_index": index + 1, "random_seed": spec.random_seed},
            )
            for index, suite in enumerate(suites)
        ]


def create_generator() -> ExampleSyntheticGenerator:
    return ExampleSyntheticGenerator()
