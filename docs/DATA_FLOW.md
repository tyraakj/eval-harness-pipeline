# Glyphuation Harness - Data Flow & Architecture

## System Overview

The Glyphuation Harness is a production-oriented evaluation system for AI applications supporting multiple execution frameworks. It executes versioned tasks against AI targets, captures bounded evidence, grades observable outcomes, and produces reproducible release decisions.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Evaluation Harness System                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │   CLI Layer   │───▶│   Runner     │───▶│   Artifacts   │                  │
│  │   (cli.py)    │    │  (runner.py) │    │  (jsonl)      │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│         │                   │                     │                          │
│         │                   │                     │                          │
│         ▼                   ▼                     ▼                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │   Dataset    │    │   Target     │    │   Exporters  │                  │
│  │  (jsonl)      │    │  (AI Target)  │    │  (LangSmith) │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│                             │                     │                          │
│                             │                     │                          │
│                             ▼                     ▼                          │
│                    ┌──────────────┐    ┌──────────────┐                     │
│                    │   Graders    │    │   Telemetry  │                     │
│                    │ (deterministic│    │  (OpenTelemetry)│                  │
│                    │   + model)   │    │              │                     │
│                    └──────────────┘    └──────────────┘                     │
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │   Web API    │───▶│   Services   │───▶│   Database   │                  │
│  │ (FastAPI)    │    │ (Celery/CQRS)│    │ (PostgreSQL) │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. CLI Layer (`cli.py`)
**Entry point:** `glyph` command-line interface

**Responsibilities:**
- Parse command-line arguments
- Load evaluation factory functions
- Initialize evaluation runner
- Configure OpenTelemetry runtime
- Display results and handle exit codes

**Key Functions:**
- `run()` - Main execution command
- `compare()` - Baseline comparison command
- `_load_factory()` - Dynamic factory loading

### 2. Evaluation Runner (`runner.py`)
**Core orchestrator:** `EvaluationRunner` class

**Responsibilities:**
- Coordinate entire evaluation lifecycle
- Manage trial execution with concurrency control
- Enforce budget constraints (time, cost, limits)
- Handle sandbox provisioning and cleanup
- Collect and aggregate results
- Write JSONL artifacts
- Dispatch export jobs

**Key Methods:**
- `run()` - Main evaluation loop
- `_run_trial()` - Single trial execution
- `_provision_sandbox()` - Sandbox setup
- `_apply_graders()` - Grading pipeline
- `_shielded_cleanup()` - Safe sandbox cleanup

### 3. Target Adapter (`target.py`)
**Framework integration:** Target adapter protocol

**Responsibilities:**
- Wrap AI applications (LangGraph, custom frameworks)
- Install callback handlers for observation (when supported)
- Convert case inputs to application inputs
- Extract normalized outputs
- Capture trajectory events
- Enforce budget limits during execution
- Generate loop and retrieval observations (when supported)

**Key Components:**
- `TrajectoryCallback` - Callback handler for event capture (framework-dependent)
- `LangGraphTarget` - LangGraph-specific target adapter
- Budget enforcement during execution

### 4. Grading System (`graders.py`)
**Deterministic evaluation:** Multiple grader implementations

**Available Graders:**
- `ExactMatchGrader` - Exact value comparison
- `ContainsAllGrader` - Substring/content inclusion
- `ToolPolicyGrader` - Tool usage validation
- `OutcomeStateGrader` - Final state verification
- `TrajectorySubsequenceGrader` - Path validation
- `LoopEfficiencyGrader` - Loop iteration limits
- `RetrievalMetricsGrader` - RAG quality metrics

**Model Judges** (`judges.py`):
- `CalibratedModelJudge` - Optional LLM-based grading with cost controls

### 5. Data Models (`models.py`)
**Immutable data structures:** Pydantic FrozenModel classes

**Core Models:**
- `EvalCase` - Evaluation task definition
- `EvaluationSuite` - Suite configuration
- `Budget` - Resource limits
- `TargetResult` - Execution output
- `Grade` - Grading result
- `TrialRecord` - Complete trial record
- `RunSummary` - Aggregated results
- `Provenance` - Version tracking

### 6. Export System (`exporting.py`)
**Async export dispatcher:** `ExportDispatcher` class

**Responsibilities:**
- Queue-based export processing
- Retry logic with exponential backoff
- Idempotency key generation
- Error recording and telemetry
- Concurrent worker management

**Export Destinations:**
- LangSmith (optional)
- Custom exporters via `EvaluationExporter` protocol

### 7. Telemetry (`telemetry.py`, `observability.py`)
**Observability layer:** OpenTelemetry integration

**Capabilities:**
- Span tracing for operations
- RED metrics (Rate, Errors, Duration)
- Trial-level metrics
- Export queue monitoring
- Error status recording

### 8. Sandbox System (`sandbox.py`, contracts)
**Isolation layer:** `SandboxProvider` protocol

**Responsibilities:**
- Capability declaration and validation
- Session provisioning per trial
- Reset for potential reuse
- Shielded cleanup with timeout
- Metadata recording

**Default:** `NoopSandboxProvider` for deterministic graphs

## Detailed Data Flow

### Phase 1: Initialization

```
User Command
    │
    ▼
CLI parses arguments
    │
    ▼
Load evaluation factory
    │
    ▼
Create EvaluationDefinition
    │
    ├── Target (AI application adapter)
    ├── Graders (deterministic + optional model)
    ├── Budget (time, cost, limits)
    ├── Suite (default graders, metrics)
    ├── Sandbox requirements
    ├── Export policy
    └── Telemetry configuration
    │
    ▼
Initialize EvaluationRunner
    │
    ├── Validate grader names
    ├── Validate suite defaults
    ├── Create artifact writer
    ├── Initialize export dispatcher
    └── Setup telemetry
```

### Phase 2: Dataset Loading

```
JSONL Dataset File
    │
    ▼
Load and validate each line
    │
    ├── Parse JSON
    ├── Validate EvalCase schema
    ├── Check duplicate case IDs
    └── Validate grader/metric references
    │
    ▼
Compute dataset hash
    │
    ▼
Return validated cases
```

### Phase 3: Trial Execution Loop

```
For each case × repetitions:
    │
    ▼
Acquire concurrency semaphore
    │
    ▼
Start telemetry span (evaluation.trial)
    │
    ▼
┌─────────────────────────────────────┐
│ Sandbox Provisioning                │
│ ├── Check requirements              │
│ ├── Validate capabilities           │
│ ├── Call provider.provision()       │
│ └── Record session metadata         │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Target Execution                    │
│ ├── Build RunContext                │
│ ├── Convert case input              │
│ ├── Invoke AI application with callbacks │
│ ├── Enforce budget limits           │
│ ├── Capture trajectory events       │
│ ├── Capture loop observations       │
│ ├── Capture retrieval observations  │
│ ├── Extract normalized output       │
│ └── Handle errors/timeouts          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Outcome Collection                  │
│ ├── For each OutcomeCollector       │
│ ├── Inspect environment state       │
│ ├── Capture sanitized observations  │
│ └── Attach to TargetResult          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Grading Pipeline                    │
│ ├── Select applicable graders        │
│ ├── Reserve judge cost (if model)    │
│ ├── Execute each grader             │
│ ├── Collect grades                  │
│ ├── Apply grader policy             │
│ ├── Calculate weighted score        │
│ └── Determine pass/fail status      │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Shielded Cleanup                    │
│ ├── bounded timeout task            │
│ ├── Call provider.destroy()         │
│ ├── Record cleanup status           │
│ └── Handle cleanup failures         │
└─────────────────────────────────────┘
    │
    ▼
Create TrialRecord
    │
    ├── Provenance (versions, hashes)
    ├── Target result
    ├── Grades
    ├── Status (passed/failed/error/timeout)
    ├── Duration and usage
    └── Sandbox session info
    │
    ▼
Append to JSONL artifact
    │
    ▼
Submit to export dispatcher
    │
    ▼
Record telemetry metrics
    │
    ▼
End telemetry span
    │
    ▼
Release semaphore
```

### Phase 4: Result Aggregation

```
All trials complete
    │
    ▼
Compute RunSummary
    │
    ├── Count passed/failed/errors/timeouts
    ├── Calculate pass rate
    ├── Group by suite type
    ├── Compute pass@k metrics
    ├── Compute pass^k metrics
    ├── Aggregate metrics per case
    └── Include provenance
    │
    ▼
Write summary to artifact
    │
    ▼
Submit summary to exporters
    │
    ▼
Drain export queue
    │
    ▼
Close export dispatcher
    │
    ▼
Return RunSummary to CLI
```

### Phase 5: Export Processing (Async)

```
Export Dispatcher Workers
    │
    ▼
Pull job from queue
    │
    ▼
Generate idempotency key
    │
    ▼
For each attempt (with retry):
    │
    ├── Start telemetry operation
    ├── Apply timeout
    ├── Call exporter.export_trial() or export_summary()
    ├── Handle success → return
    ├── Handle failure → retry with backoff
    └── Record telemetry metrics
    │
    ▼
Record errors if max attempts exceeded
    │
    ▼
Mark queue task done
```

### Phase 6: Baseline Comparison (Optional)

```
Compare command invoked
    │
    ▼
Load candidate artifact JSONL
    │
    ▼
Load baseline artifact JSONL
    │
    ▼
Find common case IDs
    │
    ▼
Compare pass/fail status per case
    │
    ├── Improved: failed→passed
    ├── Regressed: passed→failed
    └── Unchanged: same status
    │
    ▼
Calculate pass rate delta
    │
    ▼
Return comparison result
    │
    ▼
CLI exits with code if thresholds exceeded
```

### Phase 7: Web API (Optional)

```
HTTP Request (POST /api/runs)
    │
    ▼
FastAPI Router
    │
    ▼
EvaluationService (CQRS Command)
    │
    ├── Create Run in Database (PostgreSQL)
    └── Submit Celery Task
    │
    ▼
Return 202 Accepted (Run ID)

... asynchronously ...

Celery Worker
    │
    ├── Load Factory & Configuration
    ├── Initialize EvaluationRunner
    ├── Execute Trials (Phase 3)
    └── Save Results to DB
```

## Key Data Structures

### EvalCase Flow
```
JSONL Line → EvalCase Model → Trial Execution → Grade Computation → Result Summary
```

### TargetResult Flow
```
AI Application Execution → Callback Capture (if supported) → Sanitization → TargetResult Model → Grading
```

### TrialRecord Flow
```
Trial Execution → Provenance Attachment → JSONL Serialization → Artifact Storage → Export
```

### Grade Flow
```
Grader Execution → Score Calculation → Policy Application → TrialRecord Attachment → Aggregation
```

## Concurrency Model

### Trial Execution
- **Semaphore-controlled concurrency** (max_concurrency from Budget)
- Each trial runs independently
- Bounded by overall budget limits
- Sandbox isolation per trial

### Export Processing
- **Queue-based worker pool** (worker_count from ExportPolicy)
- Non-blocking trial execution
- Retry logic with exponential backoff
- Bounded queue capacity

### Budget Enforcement
- **Global judge cost reservation** (max_judge_cost_usd)
- Per-trial tool call limits
- Per-trial output size limits
- Global timeout per trial

## Error Handling Strategy

### Trial Errors
- Caught and recorded in TrialRecord
- Trial marked as ERROR status
- Does not abort other trials
- Error type and message sanitized

### System Errors
- Validation errors fail fast (before execution)
- Export errors recorded but don't block trials
- Sandbox cleanup failures → trial error
- Budget exceeded → trial termination

### Timeout Handling
- Absolute deadline per trial
- Tool call timeout via asyncio
- Export call timeout per attempt
- Sandbox cleanup timeout (bounded)

## Security & Isolation

### Sandbox Lifecycle
1. **Preflight validation** - capabilities checked before artifact creation
2. **Provisioning** - one session per trial
3. **Execution** - target receives session via RunContext
4. **Cleanup** - shielded task with timeout
5. **Failure handling** - cleanup failure → trial error

### Security Cases
- Cannot opt out of isolation
- Must use sandbox with required capabilities
- Grade both blocked outcome and prohibited trajectory
- Default-deny transcript capture

### Data Sanitization
- Sensitive content minimized before persistence
- Tool payloads captured only if allowlisted
- Event payloads truncated by byte limits
- Transcript truncated when total bytes exceeded

## Observability Integration

### Span Hierarchy
```
evaluation.run (root)
├── evaluation.trial (per trial)
│   ├── sandbox.provision
│   ├── target.execute
│   │   ├── node_start/end
│   │   ├── tool_start/end
│   │   └── retrieval events
│   ├── outcome.collect
│   ├── grader.execute (per grader)
│   └── sandbox.destroy
└── evaluation.export (per export job)
```

### Metrics Collected
- `evaluation.trials` - trial count with attributes
- `evaluation.trial.errors` - system error count
- `evaluation.trial.duration` - trial duration histogram
- `evaluation.export.requests` - export attempt count
- `evaluation.export.errors` - export failure count
- `evaluation.export.duration` - export duration histogram

## Extensibility Points

### Custom Targets
Implement `Target` protocol:
```python
class Target(Protocol):
    @property
    def version(self) -> str: ...
    
    async def execute(self, case: EvalCase, context: RunContext) -> TargetResult: ...
```

### Custom Graders
Implement `Grader` protocol:
```python
class Grader(Protocol):
    @property
    def name(self) -> str: ...
    
    @property
    def version(self) -> str: ...
    
    async def grade(self, case: EvalCase, result: TargetResult) -> Grade: ...
```

### Custom Sandbox Providers
Implement `SandboxProvider` protocol:
```python
class SandboxProvider(Protocol):
    @property
    def name(self) -> str: ...
    
    @property
    def capabilities(self) -> frozenset[str]: ...
    
    async def provision(self, case: EvalCase, context: RunContext) -> SandboxSession: ...
    
    async def reset(self, session: SandboxSession) -> None: ...
    
    async def destroy(self, session: SandboxSession) -> None: ...
```

### Custom Exporters
Implement `EvaluationExporter` protocol:
```python
class EvaluationExporter(Protocol):
    @property
    def name(self) -> str: ...
    
    async def export_trial(self, case: EvalCase, record: TrialRecord, *, idempotency_key: str) -> None: ...
    
    async def export_summary(self, summary: RunSummary, *, idempotency_key: str) -> None: ...
```

### Custom Outcome Collectors
Implement `OutcomeCollector` protocol:
```python
class OutcomeCollector(Protocol):
    @property
    def name(self) -> str: ...
    
    @property
    def version(self) -> str: ...
    
    async def collect(self, case: EvalCase, result: TargetResult, context: RunContext) -> JsonValue | OutcomeObservation: ...
```

## Configuration Flow

### EvaluationDefinition Composition
```
Factory Function
    │
    ├── Build LangGraphTarget
    │   ├── Compiled graph
    │   ├── Version string
    │   ├── Model name
    │   ├── Input builder
    │   └── Output builder
    │
    ├── Select Graders
    │   ├── Deterministic graders
    │   └── Optional model judges
    │
    ├── Define Budget
    │   ├── Timeout
    │   ├── Tool call limit
    │   ├── Output size limit
    │   ├── Concurrency limit
    │   └── Judge cost limit
    │
    ├── Configure Suite
    │   ├── ID and version
    │   ├── Default graders
    │   └──── Tracked metrics
    │
    ├── Set Grader Policy
    │   ├── Weights
    │   ├── Required graders
    │   └── Pass threshold
    │
    ├── Sandbox Configuration
    │   ├── Provider
    │   └── Requirements
    │
    └── Optional Components
        ├── Outcome collectors
        ├── Exporters
        ├── Export policy
        ├── Prompt hashes
        └── Telemetry
```

## Performance Considerations

### Bottlenecks
1. **Target execution** - LangGraph invocation (unavoidable)
2. **Model judges** - LLM API calls (costly, optional)
3. **Sandbox provisioning** - External resource creation
4. **Export operations** - Network calls to external services

### Optimizations
- **Concurrency control** - Parallel trial execution
- **Async export** - Non-blocking export processing
- **Budget preflight** - Fail fast on invalid configuration
- **Idempotency keys** - Safe retry without duplication
- **Bounded evidence** - Prevent runaway artifact growth

### Resource Limits
- **Per-trial timeout** - Prevents hanging trials
- **Tool call budget** - Prevents infinite loops
- **Output size limits** - Prevents memory exhaustion
- **Artifact byte limits** - Prevents disk overflow
- **Queue capacity** - Prevents unbounded memory growth

## Failure Mode Analysis

### Trial Failure Modes
1. **Target error** - Application exception → ERROR status
2. **Timeout** - Deadline exceeded → TIMEOUT status
3. **Budget exceeded** - Tool/cost limits → BUDGET_EXCEEDED status
4. **Grading failure** - Grader exception → ERROR status
5. **Sandbox failure** - Provision/cleanup error → ERROR status

### System Failure Modes
1. **Validation error** - Invalid configuration → fails before execution
2. **Dataset error** - Invalid JSONL → fails before execution
3. **Artifact error** - Write failure → run abort
4. **Export error** - Network/timeout → recorded, continues

### Recovery Strategies
- **Trial failures** - Continue with other trials
- **Export failures** - Retry with backoff, record errors
- **Validation failures** - User must fix configuration
- **Sandbox failures** - Mark trial error, attempt cleanup

## Production Deployment

### CI Integration
```bash
# Run evaluation
glyph run \
    --factory examples.simple_graph:create_evaluation \
    --dataset datasets/example.jsonl \
    --output artifacts/example.jsonl \
    --minimum-pass-rate 1.0

# Compare with baseline
glyph compare \
    --candidate artifacts/candidate.jsonl \
    --baseline artifacts/baseline.jsonl \
    --max-regressions 0 \
    --minimum-delta 0
```

### Observability Stack
- **OpenTelemetry Collector** - Central telemetry processing
- **Prometheus** - Metrics storage
- **Grafana** - Dashboard visualization
- **Tempo** - Distributed tracing

### Environment Variables
- `LANGGRAPH_EVAL_OTEL_ENABLED` - Enable OpenTelemetry
- `OTEL_SERVICE_NAME` - Service name for telemetry
- `OTEL_EXPORTER_OTLP_ENDPOINT` - OTLP endpoint
- `OTEL_RESOURCE_ENVIRONMENT` - Environment label
- `GIT_COMMIT` - Code revision for provenance

## Release Gate Pattern

### Overview

The Release Gate pattern (inspired by waku's `release_gate.py`) provides a unified release decision system that coordinates multiple evaluation types before allowing a release. It combines deterministic evaluations, regression checks, and optional judge evaluations into a single release decision with a detailed audit trail.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Release Gate System                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │  Deterministic│   │  Regression  │    │  Judge       │                  │
│  │  Evaluation   │───▶│  Check       │───▶│  Evaluation  │                  │
│  │  (run)        │    │  (compare)   │    │  (optional)  │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│         │                   │                     │                          │
│         │                   │                     │                          │
│         └───────────────────┴─────────────────────┘                          │
│                             │                                                 │
│                             ▼                                                 │
│                    ┌──────────────┐                                          │
│                    │ ReleaseGate  │                                          │
│                    │ Coordinator  │                                          │
│                    └──────────────┘                                          │
│                             │                                                 │
│                             ▼                                                 │
│                    ┌──────────────┐                                          │
│                    │ ReleasePolicy│                                          │
│                    │ (Rules)      │                                          │
│                    └──────────────┘                                          │
│                             │                                                 │
│                             ▼                                                 │
│                    ┌──────────────┐                                          │
│                    │ ReleaseDecision│                                         │
│                    │ (allowed + rationale)                                   │
│                    └──────────────┘                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Release Gate Flow

```
Evaluation Runs Complete
    │
    ├── Deterministic Evaluation (always required)
    │   ├── Run evaluation dataset
    │   ├── Calculate pass rates per suite
    │   ├── Check error rates
    │   └── Generate RunSummary
    │
    ├── Regression Check (optional)
    │   ├── Load baseline artifact
    │   ├── Compare with candidate
    │   ├── Identify regressions/improvements
    │   └── Generate Comparison
    │
    └── Judge Evaluation (optional)
        ├── Run model-based evaluation
        ├── Score responses with LLM judge
        ├── Track judge costs
        └── Generate RunSummary
    │
    ▼
ReleaseGate.evaluate_release()
    │
    ├── Apply ReleasePolicy rules
    │   ├── Check deterministic thresholds
    │   │   ├── Overall pass rate
    │   │   ├── Capability pass rate
    │   │   ├── Regression pass rate
    │   │   ├── Security pass rate
    │   │   └── Error rate
    │   ├── Check regression limits
    │   │   ├── Maximum regression count
    │   │   └── Minimum pass rate delta
    │   └── Check judge thresholds
    │       ├── Minimum judge score
    │       └── Maximum judge cost
    │
    ├── Generate ReleaseDecision
    │   ├── allowed (bool)
    │   ├── reason (detailed rationale)
    │   ├── Individual check results
    │   └── Summary metrics
    │
    └── Return decision with audit trail
```

### Release Policy Types

#### Strict Policy (Production)
```python
ReleasePolicy(
    require_deterministic=True,
    require_regression_check=True,
    require_judge=False,
    minimum_overall_pass_rate=1.0,
    minimum_capability_pass_rate=1.0,
    minimum_regression_pass_rate=1.0,
    minimum_security_pass_rate=1.0,
    maximum_error_rate=0.0,
    maximum_regressions=0,
    minimum_pass_rate_delta=0.0,
)
```

#### Development Policy
```python
ReleasePolicy(
    require_deterministic=True,
    require_regression_check=False,
    require_judge=False,
    minimum_overall_pass_rate=0.8,
    minimum_capability_pass_rate=0.7,
    minimum_regression_pass_rate=0.9,
    minimum_security_pass_rate=1.0,
    maximum_error_rate=0.1,
    maximum_regressions=5,
    minimum_pass_rate_delta=-0.1,
)
```

#### Staging Policy
```python
ReleasePolicy(
    require_deterministic=True,
    require_regression_check=True,
    require_judge=False,
    minimum_overall_pass_rate=0.95,
    minimum_capability_pass_rate=0.9,
    minimum_regression_pass_rate=0.95,
    minimum_security_pass_rate=1.0,
    maximum_error_rate=0.05,
    maximum_regressions=2,
    minimum_pass_rate_delta=0.0,
)
```

### CLI Commands

The CLI provides commands for running evaluations, comparing artifacts, release gating, and serving the web layer.

```bash
# Basic release check with deterministic evaluation only
glyph release \
    --deterministic artifacts/results.jsonl \
    --policy strict

# Release check with regression comparison
glyph release \
    --deterministic artifacts/candidate.jsonl \
    --baseline artifacts/baseline.jsonl \
    --policy staging

# Release check with judge evaluation
glyph release \
    --deterministic artifacts/deterministic.jsonl \
    --baseline artifacts/baseline.jsonl \
    --judge artifacts/judge.jsonl \
    --policy development

# Custom policy thresholds
glyph release \
    --deterministic artifacts/results.jsonl \
    --baseline artifacts/baseline.jsonl \
    --minimum-overall-pass-rate 0.95 \
    --maximum-regressions 2 \
    --minimum-pass-rate-delta 0.0

# Start the FastAPI web server
glyph serve --host 127.0.0.1 --port 8000

# Start a Celery background worker
glyph worker --concurrency 2

# Scaffold a new evaluation project
glyph init my-evaluation
```

### Release Decision Output

```json
{
  "allowed": true,
  "reason": "Release allowed: all required evaluation checks passed",
  "deterministics_passed": true,
  "deterministics_rationale": "All deterministic checks passed",
  "regression_passed": true,
  "regression_rationale": "Regression check passed",
  "judge_passed": true,
  "judge_rationale": "Judge evaluation not required",
  "overall_pass_rate": 0.98,
  "capability_pass_rate": 0.97,
  "regression_pass_rate": 1.0,
  "security_pass_rate": 1.0,
  "error_rate": 0.0,
  "regression_count": 0,
  "pass_rate_delta": 0.02,
  "judge_score": 0.0,
  "judge_cost_usd": 0.0
}
```

### Benefits

1. **Unified Release Decisions** - Single point of decision-making combining multiple evaluation dimensions
2. **Configurable Policies** - Pre-defined policies for different environments (strict, development, staging)
3. **Detailed Audit Trail** - Complete rationale for release decisions with per-check breakdown
4. **CI Integration** - Exit code 1 for blocked releases, easy integration into CI/CD pipelines
5. **Flexible Requirements** - Optional regression checks and judge evaluations based on policy
6. **Suite-Aware Thresholds** - Different pass rate requirements for capability, regression, and security suites
7. **Cost Controls** - Maximum judge cost limits to prevent expensive evaluation runs

### Integration with Existing Architecture

The Release Gate pattern integrates seamlessly with the existing evaluation harness:

- **Uses existing outputs** - Consumes RunSummary from `run` command and Comparison from `compare` command
- **Leverages existing models** - Builds on ReleasePolicy and ReleaseDecision models in `models.py`
- **Follows existing patterns** - Uses the same async patterns and frozen model design
- **Extends CLI naturally** - New `release` command alongside `run` and `compare`
- **Maintains separation** - Release decisions are separate from evaluation execution

## Summary

The Glyphuation Harness provides a comprehensive, production-ready evaluation system with:

- **Typed, immutable data models** for reproducibility
- **LangGraph-native integration** with automatic observation
- **Flexible grading system** with deterministic and model-based options
- **Sandbox isolation** for safe execution
- **Async export processing** for external integrations
- **OpenTelemetry observability** for monitoring
- **Baseline comparison** for regression detection
- **Release gate pattern** for unified release decisions
- **CI-friendly exit codes** for automation

The architecture emphasizes local control, deterministic behavior where possible, and clear separation between the evaluation harness and the agent system under evaluation.
