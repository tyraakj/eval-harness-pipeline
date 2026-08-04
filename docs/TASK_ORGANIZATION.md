# Task Organization Guide

This guide explains how to organize evaluation tasks using tags, separate evaluation runs, and metadata.

## Using Tags for Task Grouping

Tags provide a flexible way to categorize and filter tasks within a single evaluation suite.

### Example: Tagging Tasks by Domain

```jsonl
{"id": "search-001", "input": {"query": "find documents about AI"}, "expected": {"results_count": ">0"}, "tags": ["search", "information-retrieval"], "suite": "capability"}
{"id": "search-002", "input": {"query": "weather in Tokyo"}, "expected": {"results_count": ">0"}, "tags": ["search", "weather"], "suite": "capability"}
{"id": "calc-001", "input": {"expression": "2+2"}, "expected": {"result": 4}, "tags": ["calculation", "math"], "suite": "capability"}
{"id": "calc-002", "input": {"expression": "10*5"}, "expected": {"result": 50}, "tags": ["calculation", "math"], "suite": "capability"}
```

### Filtering by Tags in Analysis

After running evaluations, you can filter results by tags:

```python
import json

# Load results
with open('artifacts/results.jsonl', 'r') as f:
    results = [json.loads(line) for line in f if line.strip()]

# Filter by tag
search_tasks = [r for r in results if 'search' in r.get('tags', [])]
calc_tasks = [r for r in results if 'calculation' in r.get('tags', [])]

# Calculate pass rates by tag
search_pass_rate = sum(1 for r in search_tasks if r['status'] == 'passed') / len(search_tasks)
calc_pass_rate = sum(1 for r in calc_tasks if r['status'] == 'passed') / len(calc_tasks)
```

### Tag Naming Conventions

Use consistent tag patterns:
- **Domain tags**: `search`, `calculation`, `reasoning`, `code-generation`
- **Complexity tags**: `simple`, `medium`, `complex`, `multi-step`
- **Feature tags**: `rag`, `tools`, `memory`, `streaming`
- **Priority tags**: `critical`, `high`, `medium`, `low`

## Creating Separate Evaluation Runs for Different Task Groups

For distinct workflows or requirements, create separate evaluation runs with different suite configurations.

### Example: Separate Runs by Domain

**File: `datasets/search_tasks.jsonl`**
```jsonl
{"id": "search-001", "input": {"query": "find documents about AI"}, "expected": {"results_count": ">0"}, "suite": "capability"}
{"id": "search-002", "input": {"query": "weather in Tokyo"}, "expected": {"results_count": ">0"}, "suite": "capability"}
```

**File: `datasets/calculation_tasks.jsonl`**
```jsonl
{"id": "calc-001", "input": {"expression": "2+2"}, "expected": {"result": 4}, "suite": "capability"}
{"id": "calc-002", "input": {"expression": "10*5"}, "expected": {"result": 50}, "suite": "capability"}
```

**Run evaluations separately:**
```bash
# Search evaluation
uv run glyph run \
  --factory your_module:create_search_evaluation \
  --dataset datasets/search_tasks.jsonl \
  --output artifacts/search-results.jsonl

# Calculation evaluation
uv run glyph run \
  --factory your_module:create_calc_evaluation \
  --dataset datasets/calculation_tasks.jsonl \
  --output artifacts/calc-results.jsonl
```

### Example: Separate Runs by Environment

**Development evaluation** (lenient thresholds):
```python
def create_dev_evaluation():
    return EvaluationDefinition(
        target=your_target,
        suite=EvaluationSuite(
            id="dev-suite",
            version="1.0.0",
            default_graders=frozenset({"exact_match"}),
        ),
        grader_policy=GraderPolicy(pass_threshold=0.7),
    )
```

**Production evaluation** (strict thresholds):
```python
def create_prod_evaluation():
    return EvaluationDefinition(
        target=your_target,
        suite=EvaluationSuite(
            id="prod-suite",
            version="1.0.0",
            default_graders=frozenset({"exact_match", "tool_policy"}),
        ),
        grader_policy=GraderPolicy(
            pass_threshold=0.95,
            required=frozenset({"tool_policy"})
        ),
    )
```

### Benefits of Separate Runs

- **Different configurations** per task group
- **Independent release decisions** for different domains
- **Parallel execution** of unrelated evaluations
- **Focused debugging** when issues arise

## Using Metadata for Task-Specific Requirements

Metadata allows you to document task-specific requirements, constraints, and context.

### Example: Metadata for Different Task Types

```jsonl
{
  "id": "rag-001",
  "input": {"question": "What is the capital of France?"},
  "expected": {"answer": "Paris"},
  "suite": "capability",
  "metadata": {
    "domain": "geography",
    "requires_rag": true,
    "min_retrieval_sources": 2,
    "max_latency_ms": 1000,
    "priority": "high",
    "author": "team-geo",
    "created_date": "2024-01-15"
  }
}
```

```jsonl
{
  "id": "tool-001",
  "input": {"action": "search_database", "query": "user data"},
  "expected": {"results": "[]"},
  "suite": "security",
  "metadata": {
    "security_level": "critical",
    "prohibited_tools": ["delete", "drop", "truncate"],
    "required_controls": ["read-only"],
    "attack_vector": "sql-injection",
    "mitigation": "parameterized-queries"
  }
}
```

### Example: Metadata for Requirements Tracking

```jsonl
{
  "id": "feature-001",
  "input": {"request": summarize this document"},
  "expected": {"summary_length": "<500"},
  "suite": "capability",
  "metadata": {
    "requirement_id": "REQ-123",
    "requirement_type": "functional",
    "acceptance_criteria": "Summary under 500 characters",
    "test_case_origin": "user-story-456",
    "verification_method": "automated"
  }
}
```

### Using Metadata in Custom Graders

```python
class MetadataAwareGrader:
    def grade(self, case, result):
        # Check task-specific requirements from metadata
        max_latency = case.metadata.get("max_latency_ms", 5000)
        actual_latency = result.usage.duration_ms
        
        if actual_latency > max_latency:
            return Grade(
                grader="latency_check",
                version="1.0.0",
                passed=False,
                score=0.0,
                reason=f"Latency {actual_latency}ms exceeds max {max_latency}ms"
            )
        
        return Grade(
            grader="latency_check",
            version="1.0.0",
            passed=True,
            score=1.0,
            reason=f"Latency {actual_latency}ms within limits"
        )
```

### Metadata Schema Recommendations

Standardize metadata fields for consistency:

**Common fields:**
- `domain`: Task domain (e.g., "search", "calculation")
- `priority`: Task priority (e.g., "critical", "high", "medium", "low")
- `author`: Team or person who created the task
- `created_date`: When the task was created

**Performance fields:**
- `max_latency_ms`: Maximum acceptable latency
- `max_cost_usd`: Maximum acceptable cost
- `min_accuracy`: Minimum accuracy threshold

**Security fields:**
- `security_level`: Security classification (e.g., "critical", "high", "medium")
- `prohibited_tools`: Tools that must not be used
- `required_controls`: Security controls that must be present

**RAG-specific fields:**
- `requires_rag`: Whether RAG is required
- `min_retrieval_sources`: Minimum sources to retrieve
- `expected_retrieval_accuracy`: Expected retrieval quality

## Combined Approach Example

Use all three approaches together for comprehensive organization:

```jsonl
{
  "id": "customer-support-001",
  "input": {"query": "How do I reset my password?"},
  "expected": {"answer": "includes reset link"},
  "suite": "capability",
  "tags": ["support", "authentication", "high-priority"],
  "graders": ["exact_match", "tool_policy"],
  "tracked_metrics": ["latency", "tokens", "tool_calls"],
  "metadata": {
    "domain": "customer-support",
    "priority": "high",
    "requires_rag": true,
    "max_latency_ms": 2000,
    "min_retrieval_sources": 1,
    "requirement_id": "REQ-SUPPORT-001",
    "author": "support-team",
    "created_date": "2024-01-15"
  }
}
```

## Best Practices

1. **Use tags for runtime filtering** - Quick categorization and analysis
2. **Use separate runs for different configurations** - When graders, budgets, or policies differ
3. **Use metadata for documentation and custom logic** - Requirements tracking and specialized grading
4. **Maintain consistency** - Use standardized tag names and metadata schemas
5. **Document your conventions** - Create a team-wide guide for tag and metadata usage
6. **Review and update** - Regularly audit tags and metadata for accuracy

## CLI Filtering (Future Enhancement)

Consider adding CLI commands to filter by tags and metadata:

```bash
# Run only tasks with specific tags
uv run glyph run --dataset tasks.jsonl --filter-tags search,rag

# Run only high-priority tasks
uv run glyph run --dataset tasks.jsonl --filter-metadata priority=high

# Combine filters
uv run glyph run --dataset tasks.jsonl --filter-tags security --filter-metadata security_level=critical
```
