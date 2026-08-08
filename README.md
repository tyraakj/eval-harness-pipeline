# Glyph

**Know exactly what changed in your agent, why, and whether it is safe to ship.**

- **Records what your agent did** — every tool call, output, and timing measurement, permanently, for each version you run.
- **Change your evaluation without re-running your agent** — when Glyph runs your agent, it records the complete output: every tool call with its arguments and return value, the final response, timing, and token usage. That record is written to a JSONL file on your disk and, if you are using the web UI, also to your own database. Graders never call your agent — they read that record. Adding a new grader, tightening a threshold, or running a security check means running a different function against the same record. No API call, no model invocation, no tokens spent. The only thing that costs tokens is the agent execution itself, which happens once per agent version. Everything after — grading, re-grading, security checks, comparisons, release decisions — is local computation on the record you already have.
- **Case-level regressions, not just scores** — see exactly which tests got worse, with the specific reason each one failed. Not "pass rate dropped 4%" — "these 3 tests regressed, here is what the agent did in each one."
- **Security built into the run** — deterministic checks for prompt injection, credential exposure, excessive actions, SSRF, path traversal, and jailbreak attempts run on the same recording your graders already used. No separate tool, no extra API calls, covers [OWASP LLM Top 10 (2025)](https://owasp.org/www-project-top-10-for-large-language-model-applications/).
- **One reproducible decision** — every result file records the dataset hash, target version, model ID, and grader versions. Two engineers running the same file get the same release decision. No drift, no "it passed on my machine."
- **Your data, your files, your server** — the JSONL result files live on your disk. The web UI runs on your own machine via `glyph serve` and talks to a SQLite database by default — no account, no cloud service, nothing leaving your environment. If you want a team setup, you point it at your own Postgres and Redis. Glyph does not operate any server you connect to. There is no `app.glyph.io`.
- **Works without instrumenting your code** — start from a CSV, a pytest file, or a production failure log. You do not need to add an SDK to your agent to get your first evaluation running.
- **Fits alongside LangSmith and Braintrust, not instead of them** — LangSmith and Braintrust are observability platforms: production monitoring, prompt playgrounds, annotation queues. Glyph is the evaluation and release-gating layer that runs locally and owns the release decision. Use them together: Glyph for the verdict, LangSmith for the trace explorer.

---

## Before you start

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install --editable . --force
```

`glyph` is now available in your terminal. Run `glyph doctor` to confirm everything is set up.

---

## Step 1 — Get your test cases

You need a test library before you can run anything. The fastest path depends on what you already have.

**Have production failures or a staging log?**
These become regression tests immediately — no generation needed.

```bash
glyph datasets convert --from production-failures.jsonl --suite regression
```

**Have tests in CSV, JSON, a pytest file, or a LangSmith export?**

```bash
glyph datasets convert --from tests/agent_tests.csv
glyph datasets convert --from tests/test_agent.py
```

Glyph detects the format, maps the columns, flags anything that looks like a
secret, and shows you exactly what it mapped before writing anything.

Supported formats: CSV, Excel, JSON arrays, OpenAI evals JSONL, LangSmith exports,
pytest `parametrize` files, and plain text.

**Starting from scratch?**
Write cases by hand — each one is a single line of JSON:

```json
{"id": "password-reset-001", "input": {"question": "How do I reset my password?"}, "expected": {"contains": ["reset link"]}, "suite": "regression", "tags": ["auth"]}
```

See `datasets/example.jsonl` for more examples and the full set of supported fields.

**No tests at all?**
Generate a starting set from a seed phrase using your own LLM API key:

```bash
glyph generation create \
  --seed "password-reset customer-support agent" \
  --generator examples.synthetic_generator:create_generator \
  --output datasets/drafts/password-reset-v1.jsonl \
  --count 100

# Review and approve each generated case
glyph generation review \
  --draft datasets/drafts/password-reset-v1.jsonl \
  --case-id generated-001 --reviewer alice --decision approved

# Promote approved cases to a real test library
glyph generation promote \
  --draft datasets/drafts/password-reset-v1.jsonl \
  --output datasets/password-reset-v1.jsonl
```

Every generated case requires a human review and approval before it can be used.
Glyph does not pay for generation — it uses your configured LLM provider.

---

## Step 2 — Define how your agent is tested

Write a Python factory function that connects Glyph to your agent. Keep it in your
repo alongside your agent code.

```python
from glyph.core.domain_models import Budget, SandboxRequirements
from glyph.evaluation.definition import EvaluationDefinition
from glyph.grading.graders import ContainsAllGrader, ToolPolicyGrader
from glyph.targets.langgraph_target import LangGraphTarget


def create_evaluation() -> EvaluationDefinition:
    return EvaluationDefinition(
        target=LangGraphTarget(
            build_graph(),
            version="support-agent@2.3.0",
            model_name="provider/pinned-model",
            input_builder=lambda case: {"messages": [("user", case.input["question"])]},
            output_builder=lambda state: {"answer": state["messages"][-1].content},
        ),
        graders=(
            ContainsAllGrader(),
            ToolPolicyGrader(frozenset({"search_docs", "lookup_order"})),
        ),
        budget=Budget(timeout_seconds=60, max_tool_calls=8, max_concurrency=4),
        sandbox_provider=build_evaluation_sandbox(),
        sandbox_requirements=SandboxRequirements(
            capabilities=frozenset({"filesystem"})
        ),
    )
```

The `graders` tell Glyph what a passing response looks like. The `budget` sets the
limits per test. The `sandbox_provider` gives each test a clean, isolated environment.

Before running, check that everything wires up correctly:

```bash
glyph run --check \
  --factory my_app.evaluation:create_evaluation \
  --dataset datasets/support-v1.jsonl
```

This validates your setup without running any tests.

---

## Step 3 — Run your tests

```bash
glyph run \
  --factory my_app.evaluation:create_evaluation \
  --dataset datasets/support-v1.jsonl \
  --output artifacts/candidate.jsonl
```

You will see a live progress bar as tests complete. When done, Glyph prints a summary
and lists any tests that failed with the specific reason each one failed — no need to
dig through a separate log file.

Save the first passing run as your baseline:

```bash
cp artifacts/candidate.jsonl artifacts/baseline.jsonl
```

---

## Step 4 — See what changed

After making changes to your agent and running again:

```bash
glyph compare \
  --candidate artifacts/candidate.jsonl \
  --baseline  artifacts/baseline.jsonl
```

Output shows:
- Which tests got better
- Which tests got worse — listed by name, with exactly what changed
- The overall pass rate delta

To test two agent versions at the same time:

```bash
glyph compare-targets \
  --factory my_app.evaluation:create_evaluation \
  --target-a my_app.agents:build_v1 \
  --target-b my_app.agents:build_v2 \
  --dataset datasets/support-v1.jsonl
```

Both run in parallel. The comparison table appears automatically when both finish.

---

## Step 5 — Decide if it is safe to ship

```bash
glyph release \
  --deterministic artifacts/candidate.jsonl \
  --baseline      artifacts/baseline.jsonl \
  --policy staging
```

Four built-in policies to choose from:

| Policy | When to use | Pass rate required |
|---|---|---|
| `development` | While still building | 70% |
| `default` | Routine releases | 90% |
| `staging` | Before releasing to users | 95%, no regressions |
| `strict` | Security-sensitive releases | 100%, no regressions |

The output is a clear allowed or blocked verdict with a checklist of exactly
what passed and what failed.

---

## Security checks

Glyph checks what your agent actually did after every test — no separate security
tool required. Add `--workers` to any run:

```bash
glyph run --workers \
  --factory my_app.evaluation:create_evaluation \
  --dataset datasets/support-v1.jsonl
```

Or audit any completed results file:

```bash
glyph security audit --results artifacts/candidate.jsonl
```

Checks cover: prompt injection (direct and indirect), exposed credentials,
output injection, excessive or irreversible actions, system prompt leakage,
private network access, path traversal, jailbreak attempts, and sandbox escape.

All checks run on the recording Glyph already made during the run — no extra
API calls. Coverage aligns with [OWASP Top 10 for LLMs 2025](https://owasp.org/www-project-top-10-for-large-language-model-applications/).
See [docs/SECURITY.md](docs/SECURITY.md) to configure checks for your deployment.

---

## Web console

The CLI is the right tool for CI, scripting, and automation. The web console is the right tool
for live monitoring, investigation, and team review.

**Solo use:** run `glyph serve` on your laptop. SQLite is the default database — no setup needed.
Only you can reach it, which is fine for local development.

**Team use:** run `glyph serve` on a shared internal server, point it at a shared Postgres
database and Redis instance, and teammates connect to that server's URL in their browser.
The web console is a Next.js app that talks to whatever server you point it at via
`NEXT_PUBLIC_API_URL`. Glyph does not operate any cloud server — you host it.

```bash
# Solo
glyph serve --host 127.0.0.1 --port 8000
glyph open

# Team — after setting DATABASE_URL and CELERY_BROKER_URL in .env
docker compose -f docker-compose.dev.yml up -d
glyph serve --host 0.0.0.0 --port 8000
glyph worker --concurrency 2
```

What the web console adds over the CLI:

- **Runs** — watch individual test results stream in live as they complete. Cancel a run mid-flight.
- **Results** — click through a regression to see the exact agent output, tool calls, and grade reason in one view without running separate commands.
- **Compare** — see improved and regressed tests side by side. Copy a markdown summary for a pull request.
- **Release check** — a shareable verdict page. Point a teammate at the URL instead of sending them a JSONL file.
- **Tests** — import cases, validate coverage, see which security attack types are covered.

The command guide panel (Terminal icon in the sidebar) shows the full CLI reference,
always in sync with the installed version.

---

## Isolation

Every test runs in a sandbox. Glyph provisions one per test and cleans it up when
the test finishes.

| Provider | What it does |
|---|---|
| `NoopSandboxProvider` | No isolation. Use only for local graphs with no side effects. |
| `FilesystemSandboxProvider` | Real temp-dir isolation, OS-backed. Can run commands and read/write files inside the trial directory. |
| `NetworkSandboxProvider` | Records egress policy in metadata only. Does not block traffic at the OS level. |

For agents that make network calls or write to disk in production, implement a
container-backed provider. See [docs/SANDBOX_PROVIDERS.md](docs/SANDBOX_PROVIDERS.md).

---

## All commands

Run `glyph guide` for the full reference in your terminal. The web console has
the same reference in the sidebar.

| What you want to do | Command |
|---|---|
| Check your setup | `glyph doctor` |
| Start a new project | `glyph init my-evaluation` |
| Validate a test library | `glyph datasets validate --dataset datasets/example.jsonl` |
| Import tests from an existing file | `glyph datasets convert --from my_tests.csv` |
| Check config without running | `glyph run --check --factory ... --dataset ...` |
| Run your tests | `glyph run --factory ... --dataset ...` |
| Run with security and quality checks | `glyph run --workers --factory ... --dataset ...` |
| Test two agent versions at once | `glyph compare-targets --factory ... --target-a ... --target-b ...` |
| See what changed | `glyph compare --candidate ... --baseline ...` |
| Decide if safe to ship | `glyph release --deterministic ... --baseline ...` |
| Audit a results file for security issues | `glyph security audit --results artifacts/results.jsonl` |
| Inspect a specific test result | `glyph artifacts trial --artifact artifacts/results.jsonl --case-id case-001` |
| Watch a running job | `glyph status RUN_ID --watch` |
| Open the web dashboard | `glyph open` |

Every command supports `--help`. `glyph --version` prints the installed version.

---

## Output formats

```bash
--format rich        # default — live progress bar and tables
--format json        # machine-readable single object, good for CI
--format json-stream # one event per line as they happen
--format rpc         # for pipe integrations
--format pr-comment  # markdown summary to paste into a pull request
```

---

## What costs tokens and what does not

**Costs tokens (your API key):**
- Running your agent — always. Your agent calls an LLM. Glyph invokes it once per test per agent version.
- Model judges — optional. Only if you configure a `CalibratedModelJudge` as a grader. Off by default. Glyph enforces a cost ceiling you declare before making the call.
- Case generation — optional. Only when you run `glyph generation create`. You opt in, you pay.

**Costs zero tokens:**
- All deterministic graders (`ExactMatchGrader`, `ContainsAllGrader`, `ToolPolicyGrader`, and the rest) — pure Python functions that read the recording.
- All six analysis workers (`--workers`) — security checks, performance, tool use, output quality, graph structure, retrieval quality — all deterministic post-hoc analysis on the recording. No API calls.
- Re-grading, comparison, release decisions — local computation on files you already have.
- The web UI, API, and CLI — all local.

The background job workers (`glyph worker`) are Celery workers that run evaluation tasks in the background. They are not LLM-calling workers — the word "worker" is a job queue term, not an AI term.

```bash
uv sync --extra web      # web console and background jobs
uv sync --extra otel     # OpenTelemetry tracing and metrics
uv sync --extra langsmith # LangSmith export
```

**OpenTelemetry:**
Set `LANGGRAPH_EVAL_OTEL_ENABLED=true` to emit spans and metrics to your OTLP
collector. The `observability/` directory has a local Docker Compose stack with
Prometheus, Grafana, Tempo, and a pre-built evaluation dashboard.

**LangSmith:**
Set `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT` for automatic
LangGraph tracing. The `LangSmithExporter` sends sanitized cases and feedback after
a local result file is written. A LangSmith outage cannot change a local result.

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — how Glyph works under the hood.
- [Security](docs/SECURITY.md) — OWASP coverage, adding checks, configuring policies.
- [Sandbox providers](docs/SANDBOX_PROVIDERS.md) — built-in providers and the production contract.
- [User guide](docs/USER_GUIDE.md) — graders, prompts, DSPy, LangSmith, human review.
- [Data flow](docs/DATA_FLOW.md) — execution lifecycle and release gate in detail.
- [Task organization](docs/TASK_ORGANIZATION.md) — tags, categories, and metadata.
- [Web API](docs/WEB_API.md) — running the server and workers.
- [Module reference](docs/MODULE_REFERENCE.md) — package map.

---

## Development

```bash
uv run pytest
uv run ruff check .
uv run mypy
uv build
```

---

## License

MIT.

## Optional extras

Install only what you need:

```bash
uv sync --extra web      # web console and background jobs
uv sync --extra otel     # OpenTelemetry tracing and metrics
uv sync --extra langsmith # LangSmith export
```

**OpenTelemetry:**
Set `LANGGRAPH_EVAL_OTEL_ENABLED=true` to emit spans and metrics to your OTLP
collector. The `observability/` directory has a local Docker Compose stack with
Prometheus, Grafana, Tempo, and a pre-built evaluation dashboard.

**LangSmith:**
Set `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT` for automatic
LangGraph tracing. The `LangSmithExporter` sends sanitized cases and feedback after
a local result file is written. A LangSmith outage cannot change a local result.

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — how Glyph works under the hood.
- [Security](docs/SECURITY.md) — OWASP coverage, adding checks, configuring policies.
- [Sandbox providers](docs/SANDBOX_PROVIDERS.md) — built-in providers and the production contract.
- [User guide](docs/USER_GUIDE.md) — graders, prompts, DSPy, LangSmith, human review.
- [Data flow](docs/DATA_FLOW.md) — execution lifecycle and release gate in detail.
- [Task organization](docs/TASK_ORGANIZATION.md) — tags, categories, and metadata.
- [Web API](docs/WEB_API.md) — running the server and workers.
- [Module reference](docs/MODULE_REFERENCE.md) — package map.

---

## Development

```bash
uv run pytest
uv run ruff check .
uv run mypy
uv build
```

---

## License

MIT.
