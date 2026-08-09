# Glyph Architecture

## Purpose

Glyph executes versioned test cases against an AI agent, captures bounded observable evidence,
grades outcomes deterministically, compares a candidate version against a pinned baseline, and
produces a reproducible release decision.

It is not a model gateway, production monitoring system, annotation platform, or replacement
for application security controls.

---

## What Glyph owns vs. what you own

**Glyph owns:**
- The outer evaluation loop: loading test cases, invoking your agent, recording what happened,
  grading results, comparing versions, and enforcing release policy.
- Sandbox lifecycle: provisioning, cleanup, and capability enforcement.
- Graders: all deterministic checks plus optional model judges.
- Artifacts: immutable JSONL result files with provenance.
- The CLI and web console.

**You own:**
- The agent itself: prompts, tools, memory, orchestration, model configuration.
- The sandbox implementation for production use (containers, credentials, network policy).
- The test cases (or the generator that produces them).
- The release decision: Glyph produces evidence; humans decide.

This boundary is intentional. Glyph evaluates what your agent does; it does not rebuild what
your agent is.

---

## Design principles

1. **Local files are the source of truth.** Test cases, results, grader definitions, and prompts
   live as versioned files in your repository. No hosted platform required.
2. **Every result identifies what could have changed it.** Each trial records dataset hash, target
   version, prompt hashes, model identifier, grader versions, and sandbox provider.
3. **Deterministic checks own computable truth.** Model judges are optional and require calibration.
4. **Outcomes matter more than exact paths.** Grade what the agent produced. Use trajectory
   requirements only when the path itself is a safety or policy constraint.
5. **A failed test is evidence, not an abort.** Failed trials are typed records; unrelated tests
   keep running.
6. **Hosted exports are optional.** LangSmith, OpenTelemetry, and the web console are useful for
   diagnosis and collaboration. Outages must not change a local grade or release decision.
7. **Sensitive content is minimized before it is stored.** Raw prompts, tool payloads, and retrieved
   text are opt-in and allowlisted. Secrets and PII are scanned before any file is written.

---

## How a run works

```
Test library (JSONL)
        │
        ▼
  Validate and hash
        │
        ▼
  Runner (bounded semaphore, one deadline)
        │
        ├── Sandbox provision (per trial)
        │
        ├── Target execution (your agent)
        │        └── Tool/retrieval/graph events captured
        │
        ├── Outcome collection (optional: query DB/filesystem state)
        │
        ├── Deterministic graders
        │        └── optional: model judge (uses your API key)
        │
        ├── Optional: six analysis checks (security, performance, etc.)
        │
        ├── Write TrialRecord to JSONL artifact
        │
        └── Sandbox destroy (shielded cleanup)
        │
        ▼
  RunSummary appended to artifact
        │
        ├── PipelineTracer writes trace file (artifacts/traces/)
        │
        └── Optional exports (LangSmith, OpenTelemetry)
```

The JSONL artifact is written first. Exports happen after. Export failure cannot
change a grade or release decision.

---

## Zero-token replay

Glyph separates live execution from re-evaluation.

**Live mode** — calls your agent and records evidence:
```
test cases → sandbox → your agent → evidence artifact → graders → release decision
```

**Replay mode** — re-evaluates existing evidence without calling the agent:
```
frozen evidence artifact → graders → release decision  (zero model calls)
```

Replay can re-run any deterministic check against existing evidence: tool-call
policy, graph structure, retrieval metrics, security rules, new release thresholds.
It cannot replay model outputs — those require a new live run.

This separation is the reason Glyph produces reproducible CI decisions. A replay
run on the same artifact always produces the same result.

---

## Specialized analysis checks

Six optional workers can run after the standard graders on every trial.
The legacy `--workers` CLI category table is deprecated. Configure the relevant
checks as named graders or rubric criteria in an evaluation spec instead.

| Check | What it checks |
|---|---|
| Security | Prompt injection, credential exposure, excessive actions, system prompt leakage, SSRF, path traversal, jailbreak attempts (OWASP LLM Top 10 2025) |
| Performance | Latency, tool call count, cost vs. the run budget |
| Tool use | Tool ordering, schema validation, duplicate mutations |
| Output quality | Response length, citation presence, JSON schema conformance |
| Graph structure | Node repetition, loop count, valid terminal states |
| Retrieval quality | F1 precision/recall, citation grounding, latency |

Legacy specialized workers derive some thresholds from the run's `Budget` via
`PolicyRegistry`; new suites should keep thresholds and weights in their spec.
Changing `Budget(max_tool_calls=10)` propagates to the tool-use check and
performance check automatically — no separate policy to maintain.

### Security checks in detail

The `SecurityEvaluator` checks observable agent behavior post-hoc against a
configurable `SecurityPolicy`. It covers:

| OWASP Risk | What is checked |
|---|---|
| LLM01 Prompt injection (direct) | Injection patterns in the case input |
| LLM01 Prompt injection (indirect) | Injection patterns in tool outputs and retrieved content |
| LLM02 Sensitive data exposure | 18 credential regex patterns on agent output |
| LLM05 Improper output handling | HTML/script injection and shell injection in generated content |
| LLM06 Excessive agency | Irreversible action patterns and scope violations |
| LLM07 System prompt leakage | Leakage indicator patterns in agent output |
| SSRF / private network | Blocked domains and RFC-1918 IP range check on tool calls |
| Path traversal | `../` patterns in tool path arguments |
| Jailbreak attempts | Bypass patterns in case inputs |
| Sandbox escape | Code execution patterns in tool arguments |

What it does not cover (requires separate tooling):
- Supply chain integrity (use Dependabot or pip-audit)
- Dataset poisoning (use data validation tooling)
- Network-level egress enforcement (use a container sandbox provider)
- Factual grounding (use `RetrievalMetricsGrader`)

For how to add checks, extend patterns, or configure `SecurityPolicy` for
your deployment, see [SECURITY.md](SECURITY.md).

---

## Sandbox providers

The sandbox is user-supplied. Glyph validates it, provisions a session per
trial, and performs bounded shielded cleanup. What each built-in provider
actually does:

| Provider | What it does |
|---|---|
| `NoopSandboxProvider` | Nothing. For trusted local graphs with no side effects only. |
| `FilesystemSandboxProvider` | Real temp-dir isolation, OS-backed. Cleans up on destroy. |
| `NetworkSandboxProvider` | Records egress policy in metadata only. No OS-level enforcement. |
| `CompositeSandboxProvider` | Chains multiple providers. |

For production: implement a provider backed by containers, ephemeral credentials,
and network policy. See [SANDBOX_PROVIDERS.md](SANDBOX_PROVIDERS.md) for the
contract a production provider must satisfy.

---

## Test case format

Test cases are stored as JSONL. One case per line.

**Minimum:**
```json
{"id":"case-001","input":{"question":"How do I reset my password?"},"expected":{"contains":["reset link"]}}
```

**Full:**
```json
{
  "id": "support-password-reset-001",
  "input": {"question": "How do I reset my password?"},
  "expected": {"answer": "reset link", "required_tools": ["verify_identity"]},
  "suite": "regression",
  "tags": ["support", "auth", "critical"],
  "metadata": {
    "requirement_id": "SUP-42",
    "max_latency_ms": 2000
  }
}
```

Case IDs must be stable across candidate and baseline runs. The comparator
joins by case ID.

**Three categories:**
- `capability` — does the agent do what it should in normal conditions?
- `regression` — do known past failures stay fixed?
- `security` — does the agent stay within safe boundaries under adversarial input?

Release summaries report each category independently. A strong capability pass
rate cannot conceal a security failure.

---

## Graders

A grader receives the test case and the agent's result. It returns a score
between 0 and 1, a pass/fail decision, a reason, and bounded evidence.

Grader failures are system errors, not low-quality grades. A grader must not
silently mutate the result it receives.

**Built-in deterministic graders:**

| Grader | What it checks |
|---|---|
| `ExactMatchGrader` | Output equals expected exactly |
| `ContainsAllGrader` | Output contains all expected strings |
| `ToolPolicyGrader` | Only allowed tools were called |
| `OutcomeStateGrader` | Final environment state matches expected |
| `TrajectorySubsequenceGrader` | Required tool call sequence was followed |
| `LoopEfficiencyGrader` | Loop ran within iteration limits |
| `RetrievalMetricsGrader` | Retrieval F1, precision, recall at configured k |

**Model judges** are optional. Each judge requires a versioned rubric, a
calibration dataset identifier, and a declared maximum cost. The runner
reserves that cost against the run budget before calling the judge.

**Grader policy** assigns weights, marks required graders, and sets the
passing threshold. A trial passes only when all required graders pass and
the weighted score reaches the threshold.

---

## Comparison and release

The comparator joins two artifact files by case ID and reports:
- Improved cases (failed before, passes now)
- Regressed cases (passed before, fails now)
- Unchanged cases
- Pass-rate delta

The release gate applies a `ReleasePolicy` to the run summary and optional
comparison. Built-in presets:

| Policy | Threshold | Regression check |
|---|---|---|
| `development` | 70% pass rate | No |
| `default` | 90% pass rate | No |
| `staging` | 95% pass rate | Yes — zero regressions |
| `strict` | 100% pass rate | Yes — zero regressions |

The gate produces `RELEASE ALLOWED` or `RELEASE BLOCKED` with a checklist
of which checks passed and which failed.

---

## Message graph traces

Every run writes a pipeline trace file alongside the JSONL artifact. The trace
uses a message graph format where shared stages are stored once and referenced
by multiple branches. This keeps trace files small for runs with many test
cases that share identical early stages.

```json
{
  "run_id": "...",
  "nodes": {
    "node_0": {"kind": "DATASET_LOAD", "hash": "...", "data": {...}},
    "node_1": {"kind": "SANDBOX_PROVISION", "parent": "node_0", "data": {...}}
  },
  "branches": [["node_0", "node_1", "node_2", ...], ...]
}
```

The trace format is `graph` by default. Pass `trace_format="flat"` to
`PipelineTracer` for the legacy flat format.

---

## CLI guide endpoint

`GET /api/guide` returns the full CLI reference as structured JSON, generated
from the live Typer app at request time. The web console's command guide panel
fetches this endpoint — so the reference is always in sync with the installed
version. A 60-second cache prevents re-introspection on every panel open.

---

## AI-specific security controls

See the [Security checks in detail](#security-checks-in-detail) section above
and [SECURITY.md](SECURITY.md) for the full reference.

**What to add to the release policy for security-sensitive deployments:**
```python
ReleasePolicy(
    minimum_security_pass_rate=1.0,  # default: 1.0 — never lower this
    ...
)
```

A security pass rate below 1.0 blocks release under the default policy.
Do not lower `minimum_security_pass_rate` without documented risk acceptance.

---

## Dataset import

`glyph datasets convert` imports existing test material with zero LLM cost.

Supported formats:
- CSV and Excel (`.csv`, `.xlsx`)
- JSON arrays (`.json`)
- OpenAI evals JSONL
- LangSmith dataset exports
- pytest parametrize files (`.py`)
- Production failure trace JSONL
- Plain text (one input per line)

The converter maps columns to Glyph fields, generates stable IDs, flags
secrets and PII before writing, and shows the user every fuzzy column match
before confirming. Cases with detected secrets are quarantined, not silently
dropped.

---

## Web layer

The web layer runs evaluations as a service, decoupling execution from the CLI.

```
FastAPI app (api/)
    │
    ├── Runs, datasets, artifacts, compare, release, guide routes
    ├── Server-sent events for live run progress
    ├── Rate limiting (slowapi): 10 runs/min, 120 all others/min per IP
    │
    └── Services layer (services/)
            │
            ├── SQLAlchemy async session (db/)
            │       PostgreSQL or SQLite
            │
            └── Celery tasks (specialized_workers/evaluation/tasks.py)
                    │
                    └── Redis broker
```

The web console at `/app` mirrors every CLI capability in a browser:
start runs, watch live trial results, compare versions, check release
decisions, manage test libraries, and import test cases.

The command guide drawer fetches `GET /api/guide` and renders the full
CLI reference, always in sync with the installed version.

---

## Module map

| Package | What it contains |
|---|---|
| `core/` | Frozen domain models, YAML config loader |
| `security/` | Protocol contracts, sandbox implementations |
| `targets/` | LangGraph target adapter |
| `adapters/` | LLM adapters for model judge and online paths |
| `grading/` | Deterministic graders, model judge, comparison |
| `generation.py` | Draft generation, review, and promotion workflow |
| `specialized_workers/evaluation/` | Runner, EvaluationDefinition, Celery tasks, human/online/optimizer |
| `specialized_workers/evaluators/` | Six analysis workers |
| `specialized_workers/gates/` | ReleaseGate, AI decision gates |
| `specialized_workers/infra/` | Celery config, cache, storage layers, executor |
| `specialized_workers/orchestrator.py` | Routes evidence to analysis workers |
| `specialized_workers/aggregator.py` | Aggregates worker results into a release verdict |
| `specialized_workers/policy_registry.py` | Single source of truth for evaluation thresholds |
| `monitoring/` | OTel wiring, pipeline tracer, telemetry wrapper |
| `exporters/` | Async export dispatcher, LangSmith adapter |
| `db/` | ORM models, async session factory |
| `api/` | FastAPI app, routes, settings, rate limiting |
| `schemas/` | Pydantic request/response schemas |
| `services/` | Business logic between routes and DB/runner |
| `cli/` | Typer CLI commands |
| `utils/` | Formatting, dataset I/O, artifact writer, converters, hashing |

---

## Extension points

- **New target:** implement the `Target` protocol in `security/contracts.py`.
- **New grader:** implement the `Grader` protocol. Frozen dataclass, async `grade()`.
- **New security check:** follow the `_check_*` pattern in `SecurityEvaluator`.
  See [SECURITY.md](SECURITY.md) for instructions.
- **New sandbox provider:** implement `SandboxProvider` with `run()`, `read()`,
  and `write()` for execution-capable providers.
- **New exporter:** implement `EvaluationExporter` and register with `ExportDispatcher`.
- **New dataset format:** add a parser to `utils/converters.py` and register it
  in `detect_format()`.

---

## Production readiness checklist

- Pin dependencies with `uv.lock` and verify the package build.
- Pin model versions where providers allow it.
- Run `uv run pytest`, `uv run ruff check .`, `uv run mypy` in CI.
- Protect baseline artifacts and prompt releases from in-place modification.
- Use dedicated evaluation identities and resources. Never point at production credentials.
- Configure application-level token and cost ceilings.
- Verify cancellation stops child work and tool calls.
- Confirm artifact redaction with adversarial fixtures.
- Establish owners for test libraries, prompts, graders, and release overrides.
- Implement a container-backed `SandboxProvider` before evaluating agents that
  make network calls or write to disk.
- Set `minimum_security_pass_rate=1.0` in `ReleasePolicy` (the default).
- Test rollback to a known prompt, graph, and model configuration.
# Architecture

## Configuration boundary

`EvaluationSpec` is the user-facing contract for new suites. It compiles a YAML
file into an `EvaluationDefinition`: a target factory, suite metadata, budget,
deterministic graders, and a weighted rubric. The runner receives only that
compiled definition and writes immutable JSONL evidence. This keeps provider,
tool, RAG, and scoring details out of CLI branches.

Each rubric criterion is a named grader (`rubric.<id>`), so its score, pass
state, input expectation, observed value, and weight are independently visible
in an artifact. Required criteria are gates; all other criteria use the declared
weighted threshold. See [Evaluation specification](EVALUATION_SPEC.md).
