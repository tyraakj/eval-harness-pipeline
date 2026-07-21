# LangGraph Evaluation Harness

A personal, production-oriented evaluation harness for LangGraph applications. It keeps prompts, datasets, graders, provenance, and JSONL evidence under local control while allowing optional LangSmith tracing.

## Included

- Typed and immutable task, result, grade, provenance, and summary models.
- Native compiled-LangGraph adapter with isolated trial thread IDs.
- Fail-closed user-supplied sandbox contract with capability preflight and shielded cleanup.
- Automatic typed LangGraph loop-iteration and retrieval observations.
- One absolute provision/target/outcome/grading deadline plus concurrency and evidence budgets.
- Repeated trials with stable repetition indexes, empirical `pass@k`, and `pass^k`.
- Named, versioned evaluation suites plus capability, regression, and security summaries.
- Per-task grader and tracked-metric selection with validated suite defaults.
- Post-execution outcome collectors for database, filesystem, browser, or API state.
- Default-deny transcript capture with timestamps, run hierarchy, duration, and byte limits.
- Required and weighted grader policies with partial-credit summaries.
- Deterministic exact-match, state, trajectory-subsequence, tool-policy, and RAG graders.
- Recall@$k$, Precision@$k$, and MRR over unique ranked retrieval source IDs.
- Optional calibrated model judges with pre-call run cost reservation.
- Optional DSPy optimizer adapter with candidate and training-dataset provenance.
- Optional OpenTelemetry traces and RED metrics for trials and operation boundaries.
- Bounded asynchronous LangSmith export with timeouts, retries, and idempotency keys.
- Executable online evaluator enforcing privacy, sampling, retention, project, timeout, and cost controls.
- Immutable prompt manifests with template and rendered hashes.
- Validated JSONL datasets and durable JSONL result artifacts.
- Candidate-to-baseline comparison and CI-friendly exit codes.
- Provider-neutral target and grader protocols.
- Focused tests and a runnable deterministic graph example.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system boundaries and production guidance.

## Setup with uv

```powershell
cd C:\Users\Tyra\personal-evaluation-harness
uv sync --all-extras
uv lock
```

No paid model or hosted account is needed for the included example.

## Run the example

```powershell
uv run lg-eval run `
	--factory examples.simple_graph:create_evaluation `
	--dataset datasets/example.jsonl `
	--output artifacts/example.jsonl `
	--minimum-pass-rate 1.0
```

Artifact paths are exclusive by default. Use a new path for each run or pass `--overwrite` deliberately.

Compare a candidate against a protected baseline:

```powershell
uv run lg-eval compare `
	--candidate artifacts/candidate.jsonl `
	--baseline artifacts/baseline.jsonl `
	--max-regressions 0 `
	--minimum-delta 0
```

Run quality checks:

```powershell
uv run pytest
uv run ruff check .
uv run mypy
uv build
```

## Connect your graph

Create a Python factory that returns `EvaluationDefinition`:

```python
from langgraph_eval.definition import EvaluationDefinition
from langgraph_eval.graders import ContainsAllGrader, ToolPolicyGrader
from langgraph_eval.langgraph_target import LangGraphTarget
from langgraph_eval.models import (
		Budget,
		EvaluationSuite,
		GraderPolicy,
		SandboxRequirements,
)


def create_evaluation() -> EvaluationDefinition:
		graph = build_your_compiled_graph()
		target = LangGraphTarget(
				graph,
				version="support-agent@2.3.0",
				model_name="provider/immutable-model-id",
				input_builder=lambda case: {"messages": [("user", case.input["question"])]},
				output_builder=lambda state: {"answer": state["messages"][-1].content},
		)
		return EvaluationDefinition(
				target=target,
				suite=EvaluationSuite(
						id="support-quality",
						version="1.0.0",
						default_graders=frozenset({"contains_all", "tool_policy"}),
						tracked_metrics=frozenset({"latency", "tokens", "tool_calls"}),
				),
				graders=(
						ContainsAllGrader(),
						ToolPolicyGrader(frozenset({"search_docs", "lookup_order"})),
				),
				budget=Budget(timeout_seconds=60, max_tool_calls=8, max_concurrency=4),
				repetitions=3,
				grader_policy=GraderPolicy(
						weights={"contains_all": 0.7, "tool_policy": 0.3},
						required=frozenset({"tool_policy"}),
						pass_threshold=0.8,
				),
				prompt_hashes={"support-system@2.1.0": "sha256:..."},
				sandbox_provider=build_your_sandbox_provider(),
				sandbox_requirements=SandboxRequirements(
						capabilities=frozenset({"filesystem", "network"})
				),
		)
```

Keep this factory close to the application adapter, while keeping canonical evaluation cases and released prompts reviewable.

Each case may set `suite` to `capability`, `regression`, or `security`. The included [security dataset](datasets/security.jsonl) supplies prompt-injection, unsafe-tool-use, excessive-agency, SSRF, and SQL-injection contract cases. Adapt their inputs to your graph and grade both the blocked outcome and prohibited tool trajectory.

Cases may also set `graders` and `tracked_metrics`. Empty task selections inherit suite defaults; empty suite defaults select all configured graders and the standard metric set. Required graders are always added and cannot be bypassed by a task. Unknown names fail before target execution.

Implement `OutcomeCollector` for authoritative post-execution checks such as database rows, files, browser state, or downstream API state. Collectors run after the LangGraph target and before graders. Their sanitized snapshots are attached to `TargetResult.outcomes`; configure `OutcomeStateGrader(outcome_collector="database")` to grade the collected state instead of the agent's claimed output.

## Sandbox lifecycle

`EvaluationRunner` requires a user-supplied `SandboxProvider` by default, validates its declared capabilities before creating the artifact, provisions one `SandboxSession` per trial, and calls `destroy` through a bounded shielded task. Cleanup failure changes the trial to `error`. Security cases cannot opt out of isolation.

Implement `SandboxProvider` for Docker, Kubernetes jobs, hosted sandboxes, or disposable application fixtures. Put only non-secret resource identifiers and policy versions in session metadata. The provider owns filesystem, process, network, credential, browser, database, checkpoint, and child-process isolation. `reset` is available for provider-managed reuse, but the runner currently provisions and destroys each trial to favor isolation.

Configure it through `EvaluationDefinition(sandbox_provider=..., sandbox_requirements=...)`. Targets and outcome collectors receive the provisioned session through `RunContext.sandbox`. Deterministic graphs with no external effects may explicitly use `SandboxRequirements(required=False)`; the included example does this rather than silently claiming isolation.

The absolute trial deadline covers provisioning, target execution, outcome collection, and grading together. Cleanup has its own timeout and remains outside the trial deadline.

## LangGraph loop and retrieval contracts

LangGraph is the package's execution backbone, not an optional integration. `LangGraphTarget` always installs callback capture and emits a typed `LoopObservation` with node outcomes, state hashes, durations, and a terminal reason. Retriever callbacks automatically emit typed `RetrievalObservation` records with a query hash, ranked source IDs, and duration.

The subsystem data is naturally conditional: a graph without a retriever has an empty `retrievals` tuple, and custom non-LangGraph `Target` implementations may leave `loop` unset. No feature flag is required for LangGraph applications. Use `LoopEfficiencyGrader` and `RetrievalMetricsGrader` when the corresponding behavior is relevant to a suite.

## Optional model judges and telemetry

`CalibratedModelJudge` accepts an async provider adapter returning a structured `JudgeDecision`. It requires a calibration ID and a declared maximum call cost. Set `Budget(max_judge_cost_usd=...)`; the runner reserves the declared amount before each call, preventing concurrent trials from starting calls beyond the run budget.

OpenTelemetry is opt-in:

```powershell
uv sync --extra otel
```

Set `telemetry=EvaluationTelemetry(enabled=True)` on `EvaluationDefinition`, or pass it to `EvaluationRunner` directly. Configure SDK tracer and meter providers plus exporters in the host application. The harness emits run, trial, target, outcome, grader, and export spans; uncaught operation exceptions and caught terminal trial errors set span error status.

RED instruments include `evaluation.trials`, `evaluation.trial.errors`, and `evaluation.trial.duration`, plus `.requests`, `.errors`, and `.duration` instruments under `evaluation.target`, `evaluation.outcome`, `evaluation.grader`, and `evaluation.export`. Durations use seconds. Metric attributes are deliberately bounded and never contain run, trial, or case IDs; those identifiers remain trace attributes.

The repository includes a free, self-hosted local stack under `observability/`: OpenTelemetry Collector receives OTLP, Prometheus stores metrics and evaluates alerts, Tempo stores traces, and Grafana provisions both datasources plus the `LangGraph Evaluation RED` dashboard. Enable CLI export with `LANGGRAPH_EVAL_OTEL_ENABLED=true`; the CLI flushes providers before exit. See `observability/README.md` for secure local startup, verification, retention, and cleanup commands. The software has no usage fee, but hosting resources may have a cost.

## Optional DSPy optimization

DSPy proposes candidates; it does not replace LangGraph execution, prompt releases, datasets, graders, or JSONL evidence.

```powershell
uv sync --extra dspy
```

Use Python 3.11-3.13 for the current DSPy 3.x dependency stack. On Python 3.14, its current LiteLLM/PyO3 dependency may require an upstream release with Python 3.14 support.

Create a `DSpyOptimizerAdapter` with factories for the DSPy student program, optimizer, and conversion from `EvalCase` to `dspy.Example`. Calling `optimize(training_cases)` returns the compiled runtime program plus an immutable `OptimizationCandidate` containing the optimizer version, training-dataset hash, sanitized program state, and program hash.

Use the compiled program inside a candidate LangGraph node, assign the graph a new target version, and evaluate it with `EvaluationRunner`. Persist the candidate manifest with the experiment evidence, then promote approved instructions or demonstrations into a new immutable prompt/program release rather than mutating an existing release.

Training cases must be separate from protected regression and test cases. Do not optimize directly against release-gate results: that leaks the test set and produces misleading scores. Set training-case and serialized-state limits, use non-sensitive examples, and enforce model-call and monetary budgets in the DSPy optimizer or language-model adapter.

## Prompt releases

Prompts use this layout:

```text
prompts/
	answer-with-context/
		1.0.0/
			manifest.json
			prompt.txt
```

Load and verify a released prompt:

```python
from pathlib import Path
from langgraph_eval.prompts import PromptRegistry

registry = PromptRegistry(Path("prompts"))
prompt = registry.render(
		"answer-with-context",
		"1.0.0",
		{"context": "Paris is the capital of France.", "question": "What is the capital?"},
)
```

Never edit a released prompt directory. Create a new semantic version and compare it against the pinned baseline.

## Optional LangSmith tracing

LangGraph honors normal LangSmith environment configuration:

```powershell
$env:LANGSMITH_TRACING = "true"
$env:LANGSMITH_API_KEY = "..."
$env:LANGSMITH_PROJECT = "personal-evaluations"
uv run lg-eval run --factory your_module:create_evaluation --dataset datasets/your-cases.jsonl
```

Enter secrets directly in your shell or secret manager; do not commit them. Local artifacts remain the canonical release evidence, so LangSmith availability does not control pass/fail behavior.

For datasets, grader feedback, and review workflows, install the optional integration and add an exporter:

```python
from langgraph_eval.langsmith_exporter import LangSmithExporter

exporter = LangSmithExporter(
		dataset_name="support-quality-1.0.0",
		annotation_queue_id="queue-id-for-failures",
)

definition = EvaluationDefinition(
		# target, graders, and other local configuration...
		exporters=(exporter,),
)
```

Cases are mirrored with sanitized inputs and expected outputs. Each local run becomes a dataset-linked LangSmith experiment project; its trials are lightweight experiment runs correlated to the original LangGraph trace, and local grades are attached as feedback. Configured failure statuses are routed to the annotation queue using the original trace. After human review, call `promote_trace_to_dataset(trace_id, metadata=...)` to create a regression example from the hosted trace.

Hosted work uses a bounded queue after durable local trial persistence. `ExportPolicy` controls worker count, queue capacity, enqueue and call timeouts, attempts, backoff, and recorded-error limits. Stable trial/run keys drive deterministic LangSmith run, example, and feedback IDs. Export failures appear in `RunSummary.export_errors` and never alter pass/fail.

## Human evaluation

Human evaluation is asynchronous and append-only. It references an immutable trial rather than modifying its automated grades. A rubric represents one review dimension; use separate tasks for correctness, safety, tone, or other dimensions. Reviewer assignments intentionally omit other reviewers' decisions.

```python
from pathlib import Path

from langgraph_eval import (
	HumanEvaluationLedger,
	HumanReleasePolicy,
	HumanReviewRubric,
	HumanReviewTask,
)

ledger = HumanEvaluationLedger(Path("artifacts/human-reviews.jsonl"), resume=True)
await ledger.initialize()
task = HumanReviewTask(
	trial_id=trial.trial_id,
	case_id=trial.case_id,
	trace_id=trial.result.trace_id if trial.result else None,
	rubric=HumanReviewRubric(
		id="correctness",
		version="1.0.0",
		dimension="Outcome correctness",
		instructions="Judge only the observable final outcome.",
	),
)
await ledger.create_task(task)
assignment = ledger.assignment(task.task_id)
```

Submit typed `HumanGrade` records from local reviewers or implement the `HumanGrader` protocol. The default policy requires two substantive reviews. Disagreement produces `needs_adjudication`; a `HumanAdjudication` references the active grade IDs and appends the reconciled decision. Reviewer revisions must explicitly name the grade they supersede. `evaluate_release(...)` fails closed for missing, pending, disagreeing, or failing required rubrics and can enforce paired-reviewer Cohen's kappa.

For LangSmith, annotation feedback must use key `human.<rubric-id>` and provide an explicit `pass`, `fail`, or `abstain` value plus a rationale. Its `source_info` must contain `reviewer_pseudonym`, matching `rubric_version`, `confidence`, and optional object-valued `evidence`. Import completed annotations with `LangSmithExporter.import_human_reviews(...)`; stable feedback IDs make repeated synchronization idempotent. Human artifacts remain local canonical evidence, while annotation queues remain a hosted review interface.

## Online evaluation

`OnlineEvaluator` consumes `OnlineEvaluationPolicy` and returns a typed decision for every trace. It rejects the wrong project and expired or future observations, samples deterministically by privacy review and trace ID, reserves declared grader cost against a monthly ledger, bounds grader execution, and sanitizes returned grades.

```python
from langgraph_eval.models import OnlineEvaluationPolicy
from langgraph_eval.online import OnlineEvaluator

online = OnlineEvaluator(
		policy=OnlineEvaluationPolicy(
			enabled=True,
			privacy_review_id="privacy-2026-07",
			sampling_rate=0.05,
			retention_days=30,
			maximum_monthly_cost_usd=50,
			allowed_project="production-evals",
		),
		graders=(your_online_grader,),
		cost_ledger=your_durable_cost_ledger,
)
decision = await online.evaluate(
		trace_id=trace_id,
		project="production-evals",
		observed_at=observed_at,
		case=case,
		result=result,
)
```

`InMemoryOnlineCostLedger` is suitable only for local development. Production hosts must inject a durable, atomic ledger shared by all evaluator processes.

## CI policy

The `run` command exits nonzero for errors, timeouts, or a pass rate below the configured threshold. The `compare` command exits nonzero when regressions or pass-rate degradation exceed policy. Start with deterministic critical cases before adding model judges.

This package provides execution controls, not a full security sandbox. Use dedicated test identities and resources, database-enforced read-only roles, mocked destructive tools, and blocked production endpoints.
