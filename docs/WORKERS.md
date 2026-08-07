# Workers Systems

This document describes the two worker systems in Glyph:

1. **Specialized Evaluation Workers** (`glyph.evaluation.specialized_workers`) - The new, recommended system for multi-dimensional trace-level evaluation
2. **Domain Workers** (`glyph.workers`) - The legacy system for general domain expertise

## Specialized Evaluation Workers (Recommended)

The specialized worker system provides multi-dimensional, trace-level evaluation of AI agent executions. This is the recommended system for evaluation use cases.

### Overview

Specialized workers are evaluator services with strict contracts that analyze different aspects of AI agent executions:

- **Tool Policy Worker**: Evaluates tool call compliance (authorization, schema validation, confirmation)
- **Retrieval Quality Worker**: Evaluates retrieval quality (recall/precision, citations, grounding)
- **Graph Compliance Worker**: Evaluates LangGraph execution (nodes, edges, state transitions)
- **Output Quality Worker**: Evaluates output quality (schema validation, required fields)
- **Security Worker**: Evaluates security compliance (fail-closed for critical violations)
- **Performance Worker**: Evaluates performance metrics (latency, cost, resource usage)

### Key Characteristics

- **Deterministic-First**: Deterministic checks own computable truth; AI judges are optional
- **Fail-Closed Security**: Security workers are fail-closed for critical violations
- **Aggregator-Driven**: Workers produce evidence; aggregator makes release decisions
- **Versioned Contracts**: Every worker, result, and policy is versioned
- **Celery Integration**: Distributed processing with specialized queues

### Quick Start

```python
from glyph.evaluation.specialized_workers import (
    EvaluationOrchestrator,
    OrchestratorConfig,
    EvaluationEvidence,
    ResultAggregator,
    AggregationPolicy,
)

# Create orchestrator
orchestrator = EvaluationOrchestrator(OrchestratorConfig())

# Create evidence from trial
evidence = EvaluationEvidence(
    trial_id="trial_123",
    run_id="run_456",
    case_id="case_789",
    tool_calls=[...],
    retrieval_events=[...],
    graph_nodes=[...],
    final_output={...},
)

# Orchestrate evaluation
orchestrated_result = orchestrator.orchestrate(evidence)

# Aggregate results for release decision
aggregator = ResultAggregator(AggregationPolicy())
final_decision = aggregator.aggregate(
    orchestrated_result.worker_results,
    evidence.trial_id
)
```

### Documentation

For detailed documentation on specialized evaluation workers, see [SPECIALIZED_WORKERS.md](SPECIALIZED_WORKERS.md).

## Domain Workers (Legacy)

The domain worker system provides general domain expertise for AI agent capabilities. This system is maintained for compatibility but is not recommended for new evaluation use cases.

### Overview

Domain workers are designed to provide expertise in specific domains:

- **Code Execution**: Python interpreter expertise
- **Web Navigation**: Browser automation expertise
- **Data Analysis**: Pandas analysis expertise
- **API Integration**: HTTP client expertise
- **Security**: Security scanning expertise

### Core Components

1. **Worker Models** (`glyph.workers.models`)
   - `WorkerDomain`: Domains like code execution, web navigation, security, etc.
   - `WorkerCapability`: Specific skills within domains
   - `WorkerExpertise`: Complete worker profile with tools, metadata schemas, and analysis criteria
   - `WorkerTask/Result/Routing`: Task execution models

2. **Worker Coordinator** (`glyph.workers.coordinator`)
   - Registers and manages workers
   - Routes tasks to best-matched workers based on capability scoring
   - Coordinates concurrent execution with queue management
   - Combines deterministic and AI analysis

3. **Worker Registry** (`glyph.workers.registry`)
   - Loads worker definitions from configuration
   - Creates default workers for common domains
   - Manages worker lifecycle

4. **LangGraph Integration** (`glyph.workers.langgraph_integration`)
   - Traces LangGraph node/edge executions
   - Extracts tool calls and metadata patterns
   - Provides execution analysis for workers

5. **AI Analysis** (`glyph.workers.ai_analysis`)
   - Optional AI-powered analysis for complex evaluations
   - Hybrid analyzer that uses AI when beneficial
   - Fallback to deterministic analysis for simple tasks

## Worker Domains

### Available Domains

- `CODE_EXECUTION`: Code generation, debugging, refactoring
- `WEB_NAVIGATION`: Web scraping, form filling, navigation
- `DATA_ANALYSIS`: Data cleaning, transformation, visualization
- `API_INTEGRATION`: Authentication, rate limiting, error handling
- `FILESYSTEM`: File reading, writing, validation
- `SECURITY`: Vulnerability scanning, authorization checking
- `RETRIEVAL`: Semantic search, hybrid search, deduplication
- `REASONING`: Multi-step reasoning, tool selection, composition
- `TOOL_USE`: Tool selection and composition
- `GENERAL`: General-purpose evaluation

### Default Workers

The system includes 5 pre-configured workers:

1. **code-execution-worker**: Python interpreter expertise
2. **web-navigation-worker**: Browser automation expertise
3. **data-analysis-worker**: Pandas analysis expertise
4. **api-integration-worker**: HTTP client expertise
5. **security-worker**: Security scanning expertise

## Hybrid AI Approach

### Deterministic Routing

Task routing uses deterministic algorithms:
- **Capability matching** (40% weight): Required capabilities vs worker capabilities
- **Tool expertise** (30% weight): Tool-specific expertise levels
- **Metadata schema match** (20% weight): Metadata requirements vs schemas
- **Node analysis match** (10% weight): Node analysis criteria

### AI-Powered Analysis

AI is used selectively based on:
- **Domain complexity**: Security, reasoning, and general domains
- **Confidence threshold**: High thresholds (>0.8) trigger AI
- **Context richness**: Tasks with >1000 characters of context

### Analysis Combination

Results combine both approaches:
```python
{
    "deterministic": { ... },  # Rule-based analysis
    "ai_enhanced": { ... },     # AI insights when used
    "method": "hybrid"
}
```

## Usage

### Basic Setup

```python
from glyph.workers import WorkerCoordinator, WorkerRegistry

# Create registry and default workers
registry = WorkerRegistry()
expertises = registry.create_default_workers()

# Create coordinator (deterministic only)
coordinator = WorkerCoordinator()
for expertise in expertises:
    coordinator.register_worker(expertise)
```

### With AI Analysis

```python
from glyph.workers.ai_analysis import HybridAIAnalyzer

# Create coordinator with AI analyzer
ai_analyzer = HybridAIAnalyzer()
coordinator = WorkerCoordinator(ai_analyzer=ai_analyzer)
```

### Task Submission

```python
from glyph.workers import WorkerTask, WorkerDomain, WorkerCapability

task = WorkerTask(
    task_id="eval-001",
    domain=WorkerDomain.CODE_EXECUTION,
    required_capabilities=frozenset([
        WorkerCapability.CODE_GENERATION,
        WorkerCapability.CODE_DEBUGGING,
    ]),
    target_tools=frozenset(["python_interpreter"]),
    context={"code": "def example(): pass"},
)

result = await coordinator.submit_task(task)
```

### LangGraph Integration

```python
from glyph.workers import LangGraphTracer, LangGraphWorkerAdapter

tracer = LangGraphTracer()
adapter = LangGraphWorkerAdapter(tracer)

# Start execution tracing
execution = tracer.start_execution("exec-001")

# Track nodes
tracer.start_node("node-1", "tool_call", {"tool": "python_interpreter"})
tracer.end_node("node-1", {"result": "success"})

# Analyze execution
analysis = tracer.analyze_execution("exec-001")
worker_task = adapter.create_worker_task_from_execution("exec-001", "code_execution")
```

## Worker Expertise

### Tool Expertise

Workers define expertise with specific tools:

```python
ToolExpertise(
    tool_name="python_interpreter",
    expertise_level=0.9,  # 0-1 score
    supported_operations={"execute", "validate", "debug"},
    known_limitations={"no_network", "limited_memory"},
    best_practices=["validate_syntax", "handle_errors", "timeout_protection"],
)
```

### Metadata Schemas

Workers can analyze specific metadata structures:

```python
MetadataSchema(
    schema_name="execution_trace",
    required_fields={"timestamp", "node_id", "action"},
    optional_fields={"duration_ms", "error"},
    validation_rules={"timestamp": "iso8601"},
)
```

### Node Analysis Criteria

Workers can analyze LangGraph nodes:

```python
NodeAnalysisCriteria(
    node_types={"tool_call", "decision"},
    required_inputs={"context", "state"},
    expected_outputs={"result", "next_action"},
    performance_thresholds={"duration_ms": 1000},
)
```

## AI Analyzer Options

### NoOpAIAnalyzer

Deterministic-only analysis with no AI:

```python
from glyph.workers.ai_analysis import NoOpAIAnalyzer

analyzer = NoOpAIAnalyzer()
coordinator = WorkerCoordinator(ai_analyzer=analyzer)
```

### AnthropicAIAnalyzer

Uses Anthropic Claude for complex analysis:

```python
from glyph.workers.ai_analysis import AnthropicAIAnalyzer

analyzer = AnthropicAIAnalyzer(
    api_key="your-api-key",
    model="claude-3-5-sonnet-20241022"
)
coordinator = WorkerCoordinator(ai_analyzer=analyzer)
```

### HybridAIAnalyzer

Automatically chooses between AI and deterministic:

```python
from glyph.workers.ai_analysis import HybridAIAnalyzer, AnthropicAIAnalyzer

ai_analyzer = AnthropicAIAnalyzer(api_key="your-api-key")
hybrid = HybridAIAnalyzer(ai_analyzer=ai_analyzer, cost_threshold=0.01)
coordinator = WorkerCoordinator(ai_analyzer=hybrid)
```

## Worker Results

Results include:

```python
WorkerResult(
    task_id="eval-001",
    worker_id="code-execution-worker",
    domain=WorkerDomain.CODE_EXECUTION,
    success=True,
    confidence=0.85,
    findings={ ... },
    tool_analysis={ ... },
    metadata_analysis={ ... },
    node_analysis={ ... },
    recommendations=[ ... ],
    execution_time_ms=150,
    ai_analysis_used=True,
    ai_model="claude-3-5-sonnet-20241022",
    ai_confidence=0.8,
)
```

## Integration with Evaluation Runner

Workers can be integrated into the evaluation pipeline:

```python
from glyph.workers import WorkerCoordinator, WorkerRegistry
from glyph.evaluation import EvaluationRunner

# Setup workers
registry = WorkerRegistry()
expertises = registry.create_default_workers()
coordinator = WorkerCoordinator()

# Create custom outcome collector that uses workers
class WorkerOutcomeCollector(OutcomeCollector):
    def __init__(self, coordinator: WorkerCoordinator):
        self.coordinator = coordinator
    
    async def collect(self, case: EvalCase, result: TargetResult, context: RunContext) -> OutcomeObservation:
        # Create worker task based on case and result
        task = create_worker_task_from_evaluation(case, result)
        worker_result = await self.coordinator.submit_task(task)
        
        return OutcomeObservation(
            key="worker_analysis",
            value=worker_result.model_dump(),
        )

# Use in evaluation
runner = EvaluationRunner(
    target=definition.target,
    graders=definition.graders,
    budget=definition.budget,
    outcome_collectors=[WorkerOutcomeCollector(coordinator)],
    # ... other parameters
)
```

## Benefits

1. **Domain Expertise**: Each worker specializes in specific evaluation domains
2. **Scalable**: Parallel execution with queue management
3. **Flexible**: Optional AI for complex analysis, deterministic for reliability
4. **Observable**: Detailed analysis of tools, metadata, and execution patterns
5. **LangGraph Integration**: Deep analysis of node/edge executions
6. **Cost-Effective**: AI used only when beneficial

## Design Principles

- **Deterministic Core**: Routing and basic analysis are deterministic for reliability
- **Optional AI**: AI enhances analysis where beneficial but isn't required
- **Domain-Specific**: Workers have deep expertise in their domains
- **Observable**: All analysis is captured and reported
- **Composable**: Workers can be combined and extended
- **Cost-Aware**: AI usage is gated by cost thresholds and complexity
