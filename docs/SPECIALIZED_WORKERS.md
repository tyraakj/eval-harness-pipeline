# Specialized Evaluation Workers

> New suites must configure worker thresholds, score maps, patterns, and release
> behavior through `specialized_policy` in an evaluation spec. The Python policy
> constructors below remain a compatibility API; their defaults are not the
> project policy source of truth.

## Overview

Glyph's specialized worker system provides multi-dimensional, trace-level evaluation of AI agent executions with **zero-token replay** capabilities. Unlike generic evaluation systems that only compare final answers, this architecture evaluates the entire execution trace: tool calls, retrieval, node transitions, state changes, latency, cost, and final outcomes.

The system now supports two execution modes:
- **Live Mode**: Executes the target with real model calls, creating immutable evidence artifacts
- **Replay Mode**: Reuses frozen evidence artifacts for zero-token deterministic evaluation

## Architecture

### Core Design Principles

1. **Specialized Evaluator Services**: Workers are specialized evaluator services with strict contracts, not autonomous AI sub-agents.
2. **Deterministic-First**: Deterministic checks own computable truth; model judges are optional and used selectively for complex interpretation.
3. **Fail-Closed Security**: Security workers are fail-closed for critical violations; an AI judge should never silently override a deterministic safety failure.
4. **Aggregator-Driven Decisions**: Workers produce evidence; the aggregator normalizes scores and applies policy; only the aggregator produces final release decisions.
5. **Versioned Contracts**: Every worker, result, and policy is versioned for reproducibility and traceability.
6. **Immutable Evidence**: Artifacts are frozen after live execution and reused for replay evaluation without model calls.
7. **Content-Addressed Caching**: Cache keys include all execution dependencies for change-aware testing.
8. **AI Judge Decision Gates**: Comprehensive validation gates before, during, and after AI judge invocation for fail-closed safety.

### System Architecture

```
                 ┌───────────────────┐
                 │ Evaluation Orchestrator │
                 │ live/replay routing     │
                 └─────────┬─────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼────────┐ ┌───────▼────────┐ ┌───────▼────────┐
│ Tool Worker    │ │ Retrieval Worker│ │ Graph Worker   │
│ calls/policies │ │ sources/quality │ │ nodes/edges    │
│ (artifact mode)│ │ (artifact mode)│ │ (artifact mode)│
└───────┬────────┘ └───────┬────────┘ └───────┬────────┘
        │                  │                  │
┌───────▼────────┐ ┌───────▼────────┐ ┌───────▼────────┐
│ Output Worker  │ │ Security Worker   │ │ Performance    │
│ schema/quality │ │ auth/risk       │ │ latency/cost   │
│ (artifact mode)│ │ (artifact mode)│ │ (artifact mode)│
└────────────────┘ └────────────────┘ └────────────────┘
                           │
                 ┌─────────▼─────────┐
                 │ Aggregator/Policy │
                 │ release decision  │
                 └───────────────────┘
```

### Zero-Token Replay Architecture

```
Live Execution:
dataset → baseline/candidate → sandbox → model execution → frozen artifact → deterministic grading → release decision

Replay Execution:
frozen artifact → replay executor → deterministic graders → baseline comparison → release decision (zero tokens)
```

## Worker Specializations

### Tool Policy Worker

Evaluates tool call compliance with deterministic checks:

- **Authorization**: Whether the selected tool was allowed
- **Schema Validation**: Whether arguments matched the schema
- **Confirmation**: Whether required confirmation occurred
- **Rate Limiting**: Whether the tool was called too many times
- **Destructive Operations**: Whether a destructive tool was invoked
- **Result Usage**: Whether the result was used correctly
- **Retry Detection**: Whether retries or duplicate mutations occurred

**Policy Configuration**:
```python
from glyph.evaluation.specialized_workers import ToolEvaluator, ToolPolicy

policy = ToolPolicy(
    allowed_tools={"python_interpreter", "web_browser"},
    prohibited_tools={"system_shell", "file_deleter"},
    tools_requiring_confirmation={"file_writer", "database_mutator"},
    destructive_tools={"file_deleter", "database_dropper"},
    max_tool_calls=20,
    max_retries=3,
    require_schema_validation=True,
)

evaluator = ToolEvaluator(version="1.0.0", policy=policy)
```

### Retrieval Quality Worker

Evaluates retrieval quality and citation correctness:

- **Recall/Precision**: Of relevant source IDs
- **Ranking Quality**: Order and relevance of retrieved sources
- **Duplicate Detection**: Whether duplicate retrieval occurred
- **Latency**: Retrieval performance
- **Evidence Usage**: Whether the final answer used retrieved evidence
- **Citation Correctness**: Whether citations are valid and grounded
- **Domain Compliance**: Whether the agent answered outside available evidence

**Policy Configuration**:
```python
from glyph.evaluation.specialized_workers import RetrievalEvaluator, RetrievalPolicy

policy = RetrievalPolicy(
    require_citations=True,
    allow_hallucination=False,
    max_latency_ms=5000,
    min_relevant_sources=1,
    require_source_grounding=True,
    deduplicate_sources=True,
)

evaluator = RetrievalEvaluator(version="1.0.0", policy=policy)
```

### Graph Compliance Worker

Evaluates LangGraph execution compliance:

- **Node Execution**: Nodes entered and exited correctly
- **Edge Decisions**: Correct transitions between nodes
- **Loop Count**: Limit on repeated-node loops
- **Terminal State**: Proper termination reason
- **State Transitions**: Valid state changes
- **Failed/Skipped Nodes**: Detection of execution issues
- **Unexpected Paths**: Deviations from expected graph paths
- **Policy Requirements**: Required transitions and node visits

**Policy Configuration**:
```python
from glyph.evaluation.specialized_workers import GraphEvaluator, GraphPolicy

policy = GraphPolicy(
    required_nodes={"data_fetcher", "processor", "output_generator"},
    prohibited_nodes={"debug_node", "test_node"},
    required_transitions={("data_fetcher", "processor")},
    prohibited_transitions={("processor", "debug_node")},
    max_node_repeats=3,
    max_total_nodes=50,
    max_loops=10,
    require_terminal_state=True,
    allowed_terminal_reasons={"success", "complete"},
)

evaluator = GraphEvaluator(version="1.0.0", policy=policy)
```

### Output Quality Worker

Evaluates output quality with deterministic checks:

- **JSON/Schema Validation**: Structure and schema compliance
- **Required Fields**: Presence of mandatory fields
- **Prohibited Fields**: Absence of forbidden fields
- **Citation Presence**: Required citations included
- **Grounding**: Output grounded in evidence
- **Length Compliance**: Within size limits
- **Instruction Compliance**: Follows task instructions

**Policy Configuration**:
```python
from glyph.evaluation.specialized_workers import OutputEvaluator, OutputPolicy

policy = OutputPolicy(
    require_json_schema=True,
    json_schema={"type": "object", "required": ["answer", "confidence"]},
    required_fields={"answer", "confidence"},
    prohibited_fields={"internal_state", "debug_info"},
    require_citations=True,
    require_grounding=True,
    max_length=100_000,
    min_length=1,
    strict_instruction_compliance=True,
)

evaluator = OutputEvaluator(version="1.0.0", policy=policy)
```

### Security Worker

Evaluates security compliance with fail-closed critical violations:

- **Tool Authorization**: Unauthorized tool access attempts
- **Secret Exposure**: Detection of exposed credentials/secrets
- **Filesystem Protection**: Access to protected paths
- **Network Protection**: Unauthorized network access
- **Prompt Injection**: Detection of injection attempts
- **Sandbox Escape**: Attempts to escape execution environment
- **Destructive Operations**: Unauthorized destructive actions
- **Credential Exposure**: Credential exposure in logs/auth

**Policy Configuration**:
```python
from glyph.evaluation.specialized_workers import SecurityEvaluator, SecurityPolicy

policy = SecurityPolicy(
    unauthorized_tool_block=True,
    prohibited_tools={"system_shell", "network_scanner"},
    block_secret_exposure=True,
    secret_patterns=[
        r"sk-[a-zA-Z0-9]{32}",  # OpenAI API key
        r"AKIA[0-9A-Z]{16}",   # AWS access key
    ],
    protected_paths={"/etc/passwd", "/etc/shadow"},
    allow_file_modification=False,
    block_prompt_injection=True,
    block_sandbox_escape=True,
    fail_closed_critical=True,
)

evaluator = SecurityEvaluator(version="1.0.0", policy=policy)
```

### Performance Worker

Evaluates performance metrics deterministically:

- **Latency**: Total execution time and time-to-first-token
- **Token Usage**: Input/output/total token counts
- **Cost**: Total cost and cost-per-token
- **Resource Usage**: Tool calls, retries, memory usage
- **Efficiency**: Tokens-per-second and cost efficiency

**Policy Configuration**:
```python
from glyph.evaluation.specialized_workers import PerformanceEvaluator, PerformancePolicy

policy = PerformancePolicy(
    max_total_latency_ms=30000,
    max_time_to_first_token_ms=5000,
    max_input_tokens=100_000,
    max_output_tokens=10_000,
    max_cost_usd=1.0,
    max_tool_calls=20,
    max_retries=3,
    min_tokens_per_second=10.0,
)

evaluator = PerformanceEvaluator(version="1.0.0", policy=policy)
```

## AI Judge Decision Gates

The grader router includes comprehensive decision gates for fail-closed AI-based evaluation. These gates validate conditions before, during, and after AI judge invocation to ensure safety and quality.

### Decision Gate Types

**Pre-Invocation Gates** (before calling AI judge):
- **Artifact Suitability**: Validate artifact has sufficient data and valid state
- **AI Availability**: Check if AI judge service is available
- **Budget Constraints**: Verify spending limits are not exceeded
- **Rate Limiting**: Ensure API rate limits are respected
- **Case Criticality**: Validate case is critical enough to warrant AI evaluation

**Post-Result Gates** (after AI judge returns):
- **Result Structure**: Validate AI judge output has required fields
- **Confidence Threshold**: Ensure AI judge confidence meets minimum requirements
- **Reason Code Validation**: Block prohibited reason codes (e.g., hallucination detection)
- **Required Fields**: Ensure result contains debugging information
- **Fallback Mechanism**: Use deterministic evaluation if AI judge fails

**Cost Control Gates**:
- **Total Budget**: Prevent exceeding total spending limits
- **Per-Case Budget**: Prevent excessive spending on individual cases
- **Alert Threshold**: Warn when approaching spending limits
- **Spending Tracking**: Track spending per case and overall

**Quality Control Gates**:
- **Suspicious Pattern Detection**: Identify generic or placeholder results
- **Result Consistency**: Validate AI results align with deterministic findings
- **Output Validation**: Ensure AI judge output meets quality standards

**Confidence Control Gates**:
- **Minimum Confidence**: Require minimum confidence levels
- **Overconfidence Detection**: Warn on extremely high confidence (potential calibration issues)

### Decision Gate Configuration

```python
from glyph.evaluation.specialized_workers import (
    AIJudgeGateChain,
    AIJudgeInvocationConfig,
    PreInvocationGate,
    PostResultGate,
    CostControlGate,
    QualityControlGate,
    ConfidenceControlGate,
)

# Configure AI judge invocation
config = AIJudgeInvocationConfig(
    model="gpt-4",
    max_tokens=1000,
    temperature=0.0,
    max_cost_per_call_usd=0.05,
    max_total_cost_usd=1.0,
    min_confidence=0.7,
    require_structured_output=True,
    calls_per_minute=10,
    calls_per_hour=100,
)

# Create individual gates
pre_invocation_gate = PreInvocationGate("pre_invocation", enabled=True)
post_result_gate = PostResultGate("post_result", enabled=True)
cost_control_gate = CostControlGate(
    "cost_control",
    enabled=True,
    max_total_spending_usd=10.0,
    max_per_case_spending_usd=0.5,
    alert_threshold_usd=5.0,
)
quality_control_gate = QualityControlGate("quality_control", enabled=True)
confidence_control_gate = ConfidenceControlGate("confidence_control", enabled=True)

# Create gate chain
gate_chain = AIJudgeGateChain(
    pre_invocation_gate=pre_invocation_gate,
    post_result_gate=post_result_gate,
    cost_control_gate=cost_control_gate,
    quality_control_gate=quality_control_gate,
    confidence_control_gate=confidence_control_gate,
)

# Use with grader router
from glyph.evaluation.specialized_workers import GraderRouter

router = GraderRouter(
    deterministic_workers=[...],
    ai_judge_available=True,
    gate_chain=gate_chain,
)
```

### Gate Decision Types

- **PROCEED**: Allow the operation to proceed
- **BLOCK**: Block the operation (fail-closed)
- **FALLBACK**: Use fallback mechanism (deterministic evaluation)
- **RETRY**: Retry with different parameters
- **SKIP**: Skip this operation

### Fail-Closed Safety Model

The decision gates implement a fail-closed safety model:
- When gates block, the system uses deterministic evaluation rather than proceeding
- When gates fallback, the system uses deterministic evaluation with appropriate logging
- Critical security gates are always fail-closed
- AI judge results are only accepted after passing all post-result gates

This ensures that AI-based evaluation never produces unsafe or unreliable results.

## Evaluation Orchestration

### Orchestrator Configuration

The orchestrator routes evidence to appropriate workers:

```python
from glyph.evaluation.specialized_workers import (
    EvaluationOrchestrator,
    OrchestratorConfig,
    EvaluationEvidence,
)

config = OrchestratorConfig(
    enable_tool_evaluator=True,
    enable_retrieval_evaluator=True,
    enable_graph_evaluator=True,
    enable_output_evaluator=True,
    enable_security_evaluator=True,
    enable_performance_evaluator=True,
    parallel_execution=True,
    fail_fast_on_critical=True,
)

orchestrator = EvaluationOrchestrator(config)

# Create evidence from trial execution
evidence = EvaluationEvidence(
    trial_id="trial_123",
    run_id="run_456",
    case_id="case_789",
    tool_calls=[...],
    retrieval_events=[...],
    graph_nodes=[...],
    final_output={...},
    security_events=[...],
    latency_ms=5000.0,
    token_usage={"input_tokens": 1000, "output_tokens": 500},
    cost_usd=0.05,
)

# Orchestrate evaluation
result = orchestrator.orchestrate(evidence)
```

### Result Aggregation

The aggregator combines worker results and applies policy:

```python
from glyph.evaluation.specialized_workers import (
    ResultAggregator,
    AggregationPolicy,
    ReleaseDecision,
)

policy = AggregationPolicy(
    minimum_overall_score=0.8,
    minimum_tool_score=0.9,
    minimum_retrieval_score=0.7,
    minimum_graph_score=0.8,
    minimum_output_score=0.8,
    minimum_performance_score=0.6,
    block_on_critical_security=True,
    block_on_critical_tool=True,
    block_on_critical_graph=True,
    tool_weight=0.2,
    retrieval_weight=0.15,
    graph_weight=0.15,
    output_weight=0.25,
    security_weight=0.15,
    performance_weight=0.1,
    max_non_critical_failures=2,
    allow_conditional_approval=True,
)

aggregator = ResultAggregator(policy=policy)
aggregated = aggregator.aggregate(result.worker_results, evidence.trial_id)

if aggregated.release_decision == ReleaseDecision.APPROVED:
    print("Release approved:", aggregated.release_rationale)
elif aggregated.release_decision == ReleaseDecision.BLOCKED:
    print("Release blocked:", aggregated.release_rationale)
elif aggregated.release_decision == ReleaseDecision.CONDITIONAL:
    print("Conditional approval:", aggregated.release_rationale)
```

## Celery Integration

### Queue Configuration

Workers are distributed across specialized Celery queues:

```python
from glyph.evaluation.specialized_workers.celery_config import (
    celery_app,
    get_queue_for_worker_type,
)

# Queue mappings:
# - eval.orchestration: Orchestration tasks (high priority)
# - eval.deterministic: Tool, retrieval, graph, output workers (high concurrency)
# - eval.security: Security worker (isolated, fail-closed)
# - eval.performance: Performance worker (resource-aware)
# - eval.semantic: AI judge tasks (rate-limited, expensive)
# - eval.export: Export tasks (low priority)
```

### Task Execution

Execute workers as Celery tasks:

```python
from glyph.evaluation.specialized_workers.tasks import (
    orchestrate_evaluation,
    tool_evaluation,
    security_evaluation,
    aggregate_results,
)

# Orchestrate full evaluation
orchestration_result = orchestrate_evaluation.delay(
    evidence_dict=evidence.model_dump(),
    config_dict=config.model_dump(),
)

# Individual worker evaluation
tool_result = tool_evaluation.delay(
    evidence_dict=evidence.model_dump(),
    policy_dict=policy.model_dump(),
)

# Aggregate results
aggregated_result = aggregate_results.delay(
    worker_results_dict={...},
    trial_id=evidence.trial_id,
    policy_dict=policy.model_dump(),
)
```

## Result Storage

### Idempotency Handling

Each worker evaluation uses idempotency keys to prevent duplicate grades:

```python
from glyph.evaluation.specialized_workers.storage import (
    WorkerResultStorage,
    get_storage,
)

storage = get_storage()

# Create attempt with idempotency
attempt = storage.create_attempt(
    trial_id="trial_123",
    run_id="run_456",
    worker_type=WorkerType.TOOL_POLICY,
    worker_version="1.0.0",
)

# If a completed attempt with the same idempotency key exists,
# it will be returned instead of creating a new one
```

### Result Lookup

Retrieve results by various keys:

```python
# Get result by evaluation ID
result = storage.get_result(evaluation_id="eval_123")

# Get all results for a trial
results = storage.get_results_for_trial(trial_id="trial_123")

# Get valid result for a specific worker
valid_result = storage.get_valid_result(
    trial_id="trial_123",
    worker_type=WorkerType.SECURITY,
    worker_version="1.0.0",
)
```

## Worker Result Format

All workers return versioned, structured results:

```python
{
    "evaluation_id": "eval_123",
    "worker_type": "tool_policy",
    "worker_version": "1.0.0",
    "trial_id": "trial_456",
    "score": 0.8,
    "passed": false,
    "severity": "error",
    "reason_code": "unauthorized_mutation",
    "reason_message": "Unauthorized tool call: file_deleter",
    "evidence_refs": ["tool_call_3", "tool_call_7"],
    "grader_mode": "deterministic",
    "confidence": 1.0,
    "findings": {
        "total_tool_calls": 8,
        "unauthorized_calls": ["file_deleter"],
        "schema_violations": [],
        # ... additional findings
    },
    "evaluated_at": "2024-01-01T00:00:00Z",
    "evaluation_duration_ms": 150,
}
```

## Zero-Token Replay Architecture

### Immutable Evidence Artifacts

The central object in the zero-token replay architecture is the `EvaluationArtifact`, an immutable record of execution:

```python
from glyph.evaluation.specialized_workers import (
    EvaluationArtifact,
    ModelManifest,
    UsageMetrics,
    ExecutionMode,
)

model_manifest = ModelManifest(
    provider="openai",
    model_id="gpt-4",
    parameters_hash="sha256:abc123"
)

usage = UsageMetrics(
    input_tokens=100,
    output_tokens=50,
    estimated_cost=0.01
)

artifact = EvaluationArtifact.create(
    run_id="run_001",
    mode=ExecutionMode.LIVE,
    case_id="case_001",
    trial_id="trial_001",
    target_version="git:abc123",
    model_manifest=model_manifest,
    dataset_hash="sha256:def456",
    sandbox_hash="sha256:ghi789",
    fixture_hash="sha256:jkl012",
    events=[],  # Bounded, sanitized evidence
    final_output={"answer": "test"},
    outcome_observations=[],
    usage=usage,
)
```

**Key properties**:
- **Immutable**: Frozen Pydantic model that cannot be modified after creation
- **Bounded Evidence**: Contains only observable events (no hidden chain-of-thought)
- **Content-Addressed**: Cache key includes all execution dependencies
- **Integrity Validated**: Artifact hash ensures data hasn't been tampered with

### Content-Addressed Cache

The cache system implements change-aware testing:

```python
from glyph.evaluation.specialized_workers import (
    ContentAddressedCache,
    CacheRouter,
)

cache = ContentAddressedCache()

# Compute cache key from all dependencies
cache_key = cache.compute_cache_key(
    case_hash="case_123",
    target_version="v1.0",
    model_manifest_hash="model_456",
    tool_contract_hash="tool_789",
    retriever_hash="retriever_012",
    fixture_hash="fixture_345",
    sandbox_hash="sandbox_678",
)

# Store artifact after live execution
cache.store(artifact, case_hash="case_123")

# Route execution based on cache
router = CacheRouter(cache)
mode, cached_artifact, lookup_result = router.route_execution(
    case_hash="case_123",
    target_version="v1.0",
    model_manifest_hash="model_456",
    # ... other dependencies
)

if mode == ExecutionMode.REPLAY:
    # Use cached artifact, zero tokens
    pass
else:
    # Execute live, create new artifact
    pass
```

**Change-aware testing matrix**:

| Change | Re-execute target? |
|---|---:|
| Grader implementation changed | No |
| Release threshold changed | No |
| Dashboard filter changed | No |
| Prompt changed | Yes |
| Model version changed | Yes |
| Tool contract changed | Usually |
| Retrieval index changed | Yes |
| Deterministic grader changed | No |
| Sandbox policy changed | Depends on policy |
| Application code changed | Usually |

### Live and Replay Executors

Separate executors handle the two execution modes:

```python
from glyph.evaluation.specialized_workers import (
    LiveExecutor,
    ReplayExecutor,
    ExecutionContext,
    ExecutionMode,
)

# Live executor - creates new artifacts
live_executor = LiveExecutor()
context = ExecutionContext(
    case_id="case_001",
    trial_id="trial_001",
    run_id="run_001",
    target_version="v1.0",
    dataset_hash="sha256:def456",
    sandbox_hash="sha256:ghi789",
    fixture_hash="sha256:jkl012",
    model_manifest=model_manifest,
)

result = await live_executor.execute(context, case_data)
# result.target_tokens_used > 0
# result.execution_mode == ExecutionMode.LIVE

# Replay executor - reuses existing artifacts
replay_executor = ReplayExecutor()
result = await replay_executor.execute(context, case_data, cached_artifact)
# result.target_tokens_used == 0  # Zero tokens!
# result.execution_mode == ExecutionMode.REPLAY
```

### Artifact Workers

All specialized workers now support artifact-based evaluation:

```python
from glyph.evaluation.specialized_workers import (
    ArtifactToolEvaluator,
    ArtifactRetrievalEvaluator,
    ArtifactGraphEvaluator,
    ArtifactOutputEvaluator,
    ArtifactSecurityEvaluator,
    ArtifactPerformanceEvaluator,
)

# Create artifact-specific evaluator
tool_evaluator = ArtifactToolEvaluator(policy=tool_policy)

# Evaluate artifact directly (zero tokens)
result = tool_evaluator.evaluate_artifact(artifact)

# Extract evidence internally if needed
evidence = tool_evaluator.extract_evidence_from_artifact(artifact)
```

### Three-Tier Storage

The architecture uses three storage layers:

```python
from glyph.evaluation.specialized_workers import StorageManager

storage = StorageManager(
    postgresql_storage=PostgreSQLStorage(),  # Metadata
    object_storage=ObjectStorage(),            # Artifacts
    redis_storage=RedisStorage(),              # Queues/Events
)

# Store run metadata
storage.store_run_metadata(run_metadata)

# Store immutable artifact
storage.store_artifact(artifact)

# Publish progress event
storage.publish_progress(progress_event)
```

**Storage responsibilities**:
- **PostgreSQL**: Run metadata, users, projects, statuses, summaries, indexes
- **Object Storage**: Immutable evidence artifacts, replay bundles, transcripts
- **Redis**: Queues, short-lived locks, progress events, cancellation signals

### Baseline and Candidate Comparison

```python
from glyph.evaluation.specialized_workers import (
    BaselineService,
    CandidateService,
    BaselineComparator,
)

# Create baseline (executed once in live mode)
baseline_service = BaselineService(storage)
baseline = baseline_service.create_baseline(
    run_id="baseline_001",
    target_version="v1.0",
    dataset_version="v1",
    artifact_ids=["artifact_001", "artifact_002"],
)

# Create candidate (can use replay mode)
candidate_service = CandidateService(storage)
candidate = candidate_service.create_candidate(
    run_id="candidate_001",
    target_version="v2.0",
    dataset_version="v1",  # Same dataset version
    mode="replay",
    artifact_ids=["artifact_003", "artifact_004"],
    cache_hits=2,
    cache_misses=0,
)

# Compare against baseline
comparator = BaselineComparator(baseline_service, candidate_service)
comparison = comparator.compare("baseline_001", "candidate_001")

# Check decision
if comparison.decision == ComparisonResult.PASSED:
    print("Candidate approved")
elif comparison.decision == ComparisonResult.BLOCKED:
    print(f"Blocked: {comparison.reason_codes}")
```

### Grader Router for Selective Evaluation

```python
from glyph.evaluation.specialized_workers import (
    GraderRouter,
    RoutingCriteria,
    SelectiveEvaluationPipeline,
)

# Create router with selective evaluation
router = GraderRouter(
    deterministic_workers=[tool_eval, retrieval_eval, graph_eval],
    ai_judge_available=True,
    small_judge_cost_usd=0.01,
    strong_judge_cost_usd=0.05,
)

# Route trial for evaluation
result = router.route_trial(artifact)

# Decisions:
# - BLOCK: Critical security violation
# - FAIL_DETERMINISTIC: Schema/policy failure
# - USE_CACHED: No behavioral change
# - INVOKE_SMALL_JUDGE: Semantic difference
# - INVOKE_STRONG_JUDGE: Critical case
# - SAMPLE_MONITORING: Quality monitoring
```

### Dataset Service with Versioning

```python
from glyph.evaluation.specialized_workers import (
    DatasetService,
    GenerationConfig,
    GenerationMode,
)

storage = StorageManager()
dataset_service = DatasetService(storage)

# Create dataset with zero-token generation
config = GenerationConfig(
    mode=GenerationMode.ZERO_TOKEN,
    target_case_count=50,
    use_templates=True,
    templates=[...],
    use_combinatorial=True,
    parameters={...},
)

dataset = dataset_service.create_dataset(
    dataset_name="my_dataset",
    version="v1",
    config=config,
)

# Generate cases (zero tokens)
dataset = dataset_service.generate_cases(dataset.version_id)

# Approve and freeze
dataset = dataset_service.approve_dataset(dataset.version_id)
# Now immutable for all evaluations
```

## AI Judge Integration

AI judges are used selectively for complex interpretation:

### When to Use AI Judges

**Good uses**:
- "Is this customer-support answer helpful and complete?"
- "Does this answer satisfy the rubric?"
- "Did the agent correctly interpret an ambiguous request?"
- "Is the retrieved evidence sufficient to support the answer?"

**Bad uses**:
- Whether a tool was authorized (deterministic)
- Whether JSON is valid (deterministic)
- Whether latency exceeded a limit (deterministic)
- Whether a required node was executed (deterministic)

### Hybrid Approach

```python
# Deterministic checks first
deterministic_result = deterministic_worker.evaluate(evidence)

# Identify ambiguous cases
if deterministic_result.confidence < 0.8:
    # Send bounded evidence to domain judge
    ai_result = ai_judge.evaluate(evidence)
    
    # Validate structured judge output
    if ai_result.confidence > 0.9:
        # Apply calibration and confidence rules
        final_result = combine_results(deterministic_result, ai_result)
    else:
        # Fallback to conservative decision
        final_result = deterministic_result
```

## Release Decision Process

The aggregator follows this decision process matching the architecture:

1. **Critical Failures**: Block immediately on critical security/tool/graph failures
2. **Score Thresholds**: Block if any domain score below minimum
3. **Overall Score**: Block if overall weighted score below minimum
4. **Failure Tolerance**: Mark as inconclusive if too many non-critical failures
5. **Full Approval**: All checks passed

### Release Decision Types

The architecture supports four decision types:

- **PASSED**: All policy checks passed, safe to release
- **BLOCKED**: Critical security or behavioral regression detected
- **INCONCLUSIVE**: Non-critical failures or insufficient data
- **NOT_COMPARABLE**: Baseline incompatible or incomplete data

### Example Decision Flow

```
Security worker: critical failure
→ BLOCKED
Reason: critical_security_regression

Tool worker: 0.91 (passed)
Retrieval worker: 0.84 (passed)
Graph worker: 0.95 (passed)
Output worker: 0.88 (passed)
Performance worker: passed
→ No critical failures
→ All scores above thresholds
→ Overall score: 0.89 (above 0.8 minimum)
→ PASSED
Reason: all_policy_checks_passed
```

### Architecture-Compliant Release Decision

```python
{
    "decision": "blocked",
    "reason_codes": [
        "critical_security_regression",
        "p95_latency_regression"
    ],
    "baseline_run": "run_baseline_001",
    "candidate_run": "run_candidate_019",
    "dataset_version": "dataset_v1",
    "deterministic_grades": {
        "passed": 108,
        "failed": 12
    },
    "ai_grades": {
        "evaluated": 14,
        "skipped": 106
    },
    "token_usage": {
        "live_tokens": 0,
        "evaluation_tokens": 0,
        "mode": "replay"
    },
    "blocking_trials": [
        "trial_014_00",
        "trial_021_00"
    ]
}
```

## User-Facing Workflow

The interface makes the distinction between live and replay modes clear:

```
Run 019 — Candidate v42
Mode: Replay
Model tokens: 0
Evaluator tokens: 0
Cases checked: 120
Cached traces reused: 120
Deterministic graders: 8
AI judges: 0
Decision: BLOCKED
```

For a live run:

```
Run 020 — Candidate v43
Mode: Live
Estimated target tokens: 1.4M
Budget cap: 1.8M
Cases requiring live execution: 18
Cases replayed: 102
Decision: PASSED
```

## Migration from Old Worker System

The new specialized worker system now includes zero-token replay capabilities:

### Key Differences

1. **Purpose**: Specialized evaluation with zero-token replay vs. general domain expertise
2. **Artifacts**: Immutable evidence artifacts vs. ephemeral execution data
3. **Execution Modes**: Live/replay separation vs. single execution mode
4. **Caching**: Content-addressed cache vs. no caching
5. **Contracts**: Strict versioned results vs. informal responses
6. **Decision Making**: Aggregator-driven vs. worker-autonomous
7. **AI Usage**: Selective hybrid vs. default AI analysis
8. **Security**: Fail-closed deterministic vs. AI-assisted

### Migration Path

1. **Keep Old System**: The old `glyph.workers` system remains for compatibility
2. **Adopt New Artifacts**: Use `EvaluationArtifact` for new evaluations
3. **Implement Replay**: Add replay executors for cached evaluation
4. **Update Policies**: Update aggregation policies for new decision types
5. **Migrate Workers**: Use artifact-specific evaluators for zero-token replay

## Best Practices

1. **Version Everything**: Always specify worker and policy versions
2. **Use Replay When Possible**: Leverage cached artifacts to save tokens
3. **Deterministic First**: Use deterministic checks before AI judges
4. **Security First**: Always run security evaluator with fail-closed
5. **Monitor Costs**: Track AI judge costs and set appropriate limits
6. **Calibrate Judges**: Regularly calibrate AI judges against human review
7. **Store Evidence**: Keep artifact references for traceability
8. **Review Failures**: Regularly review failures and update policies
9. **Test Policies**: Test policy changes in staging before production
10. **Cache Awareness**: Understand which changes require re-execution

## Zero-Token Replay Benefits

The new architecture provides significant benefits:

### Token Savings

- **Replay Mode**: Zero model tokens for cached traces
- **Selective AI**: Only use AI judges for ambiguous cases
- **Change-Aware**: Only re-execute when dependencies change

### Faster Evaluation

- **Deterministic Grading**: Fast checks without model calls
- **Parallel Processing**: Multiple deterministic workers run concurrently
- **Cache Hits**: Instant results for unchanged components

### Better Reproducibility

- **Immutable Artifacts**: Frozen evidence for consistent evaluation
- **Versioned Datasets**: Same dataset versions across all runs
- **Content-Addressed Cache**: Deterministic cache behavior

### Improved Quality

- **Baseline Comparison**: Compare against known-good baselines
- **Behavioral Analysis**: Detect subtle regressions
- **Comprehensive Coverage**: Test with deterministic and AI graders

## Troubleshooting

### Workers Not Running

- Check that workers are enabled in `OrchestratorConfig`
- Verify that evidence contains required data for each worker
- Review worker logs for initialization errors

### Inconsistent Results

- Verify idempotency keys are correctly generated
- Check for concurrent execution conflicts
- Review storage for duplicate attempts

### Performance Issues

- Adjust Celery worker concurrency per queue
- Review queue priorities and routing
- Monitor AI judge costs and latency

### Security False Positives

- Review security policy patterns
- Update secret patterns as needed
- Adjust fail-closed settings if appropriate

## Future Enhancements

- [ ] Additional specialized workers (e.g., Bias, Ethics)
- [ ] Advanced AI judge integration with calibration
- [ ] Real-time monitoring dashboards
- [ ] Automated policy tuning based on historical data
- [ ] Integration with external security scanners
- [ ] Distributed tracing integration
