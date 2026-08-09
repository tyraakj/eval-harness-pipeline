# Evaluation specification

An evaluation spec is the source of truth for a suite: target integration,
dataset, budget, deterministic checks, and release rubric. Keep it beside the
dataset and review it like code. Run it with:

```bash
glyph run --spec evaluations/support.yaml
glyph run --spec evaluations/support.yaml --check
```

`target.factory` is the sole integration boundary. It is a Python
`module:function` that returns a Glyph `Target`. This keeps the CLI independent
of LangGraph, RAG stacks, tool names, LLM vendors, and custom agent frameworks.

```yaml
schema_version: 1
suite:
  id: support-agent
  version: 1.0.0
target:
  factory: my_agent.evaluation:build_target
dataset: datasets/support.jsonl
artifact: artifacts/support.jsonl
budget:
  timeout_seconds: 30
  max_tool_calls: 6
graders:
  - type: contains_all
rubric:
  pass_threshold: 0.8
  criteria:
    - id: correct-answer
      description: Required answer facts are present
      assertion: contains
      expected_path: contains
      weight: 0.7
      required: true
```

Supported deterministic rubric assertions are `equals`, `contains`, `exists`,
and `tool_allowed`. Each criterion is emitted as a separate grade named
`rubric.<id>`, with evidence in the artifact. `weight` controls its contribution
to the score; `required: true` makes it a non-negotiable gate. Case data stays
in the JSONL `expected` object, so a rubric can be reused across cases.

## Model judge

Use a model judge for semantic evaluation that cannot honestly be reduced to an
observable contract: factual correctness, groundedness, answer quality, or a
multi-part business rubric. It is explicit and opt-in:

```yaml
budget:
  max_judge_cost_usd: 5.00  # total budget for the run
model_judge:
  evaluator: my_app.judges:evaluate_support_answer
  calibration_id: support-quality-v3
  version: 3.0.0
  maximum_cost_usd: 0.02   # declared maximum per decision
  minimum_score: 0.80
  weight: 0.35
  required: false
```

`evaluator` is an async `module:function` accepting `(EvalCase, TargetResult)`
and returning `JudgeDecision(score, reason, cost_usd, evidence)`. It owns the
provider SDK, prompt, structured-output validation, and redaction appropriate
to your environment. Glyph reserves `maximum_cost_usd` before each call and
enforces the run-level `budget.max_judge_cost_usd`; it records the calibration
ID, returned evidence, cost, and score in the same artifact as deterministic
grades. Make a judge `required` only when it must pass for release.

Use the regular `graders` list for reusable built-in checks such as
`retrieval_metrics` and `trajectory_subsequence`. Keep deterministic checks for
agents, RAG, graphs, nodes, tools, retrieval, budgets, and safety contracts;
add a model judge for semantic quality. Do not disguise a heuristic as a
deterministic score.

## Specialized-worker policy migration

The legacy specialized workers now load their compatibility score tables and
thresholds from `src/glyph/specialized_workers/default_policy.yaml`, rather than
from Python constants. Treat that file as an example only: copy it into your
project, version it with the suite, and construct `PolicyRegistry` with the
loaded mapping. Full `specialized_workers:` spec compilation is the remaining
migration step; see [Feature status](FEATURE_STATUS.md).

The legacy `glyph run --factory ... --dataset ...` command still works, but new
suites should use `--spec`. The former `--workers` summary was removed because
it derived category scores from incidental trial properties instead of declared
criteria.
