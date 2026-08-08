# Glyph — Full System Repair & Web Console

## Overview

This spec covers six parts in strict implementation order. Each part unblocks
the next. Do not start a later part until the earlier one is verified green.

---

## Part 1 — Fix broken `glyph.evaluation` import layer

### Problem
`src/glyph/evaluation/` contains only `.gitkeep`. The entire codebase imports
`glyph.evaluation.definition`, `glyph.evaluation.runner`, etc. — all of which
fail at import time. Nothing runs.

### Real module locations

| Broken import | Real location |
|---|---|
| `glyph.evaluation.definition` | `glyph.specialized_workers.evaluation.task_definitions` |
| `glyph.evaluation.runner` | `glyph.specialized_workers.evaluation.runner` |
| `glyph.evaluation.human` | `glyph.specialized_workers.evaluation.human_evaluation` |
| `glyph.evaluation.online` | `glyph.specialized_workers.evaluation.online_evaluation` |
| `glyph.evaluation.optimizers` | `glyph.specialized_workers.evaluation.optimizers` |
| `glyph.evaluation.tasks` | `glyph.specialized_workers.evaluation.tasks` |

### Work

1. Delete `.gitkeep`. Add `src/glyph/evaluation/__init__.py` (empty marker).
2. Add one shim per broken import — each file re-exports from its real home
   with an explicit `__all__`. No logic, no copies.
3. Fix `EvaluationRunner._harness_version()`: change the package lookup from
   `"langgraph-eval-harness"` to `"glyph"`.
4. Fix `.github/workflows/ci.yml` security-scan job: change `lg-eval` to `glyph`.
5. Run `uv run pytest`, `uv run ruff check .`, `uv run mypy` — all green.

### Acceptance criteria
- `from glyph.evaluation.runner import EvaluationRunner` resolves without error.
- `uv run pytest` exits 0.
- `uv run mypy` exits 0.


---

## Part 2 — Fix broken sandbox layer

### Problems
1. `CompositeSandboxProvider.provision()` passes `child_sessions=sessions` to
   `SandboxSession`, which has no such field — instant `ValidationError` at
   runtime.
2. `NetworkSandboxProvider` claims to block egress in its metadata but does
   nothing at the OS level. The claim is misleading.

### Work

**2a — Fix `CompositeSandboxProvider`**
- Remove `child_sessions=sessions` from the `SandboxSession(...)` constructor
  call inside `provision()`.
- Store child sessions as `self._child_sessions: dict[str, list[SandboxSession]]`
  keyed by the composite session ID so `reset()` and `destroy()` can look them
  up correctly.
- Add a test that provisions, resets, and destroys a composite session.

**2b — Make `NetworkSandboxProvider` honest**
- Add a `WARNING` log on `provision()`:
  `"NetworkSandboxProvider records egress policy in metadata only — OS-level
  enforcement requires a container-based provider."`
- Rename the capability from `"egress_control"` to `"egress_metadata_only"` so
  callers cannot accidentally declare a `SandboxRequirements(capabilities=
  frozenset({"egress_control"}))` and believe they have real isolation.
- Update all docstrings.

**2c — Add `docs/SANDBOX_PROVIDERS.md`**
A short reference (under 60 lines) explaining:
- What `NoopSandboxProvider` does (nothing — for trusted local graphs only).
- What `FilesystemSandboxProvider` does (real temp-dir isolation, OS-backed).
- What `NetworkSandboxProvider` does (metadata-only, no real enforcement).
- What `CompositeSandboxProvider` does (chains providers).
- What a production provider must implement.

### Acceptance criteria
- Creating a `CompositeSandboxProvider` and calling `.provision()` on it does
  not raise `ValidationError`.
- `NetworkSandboxProvider.capabilities` does not contain `"egress_control"`.
- `docs/SANDBOX_PROVIDERS.md` exists.


---

## Part 3 — Fix and complete the Celery worker layer

### Problems
1. `asyncio.run()` inside a Celery task body fails when the worker is started
   inside an already-running event loop (common with some Celery pool configs).
2. `celery_config.py` has `task_routes` pointing to task functions that do not
   exist (`orchestrate_evaluation`, `replay_evaluation`, etc.) — Celery silently
   fails to route these, masking the missing implementations.
3. `run_evaluation` task never writes `Trial` rows to the DB, so
   `GET /api/runs/{id}/trials` would always return empty.
4. There is no way to cancel a queued or running job from the API.

### Work

**3a — Fix `asyncio.run()` pattern**
Replace both `asyncio.run(...)` calls in `tasks.py` with a safe helper:
```python
def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
```
Use `_run_async(...)` everywhere `asyncio.run(...)` appears in the task body.

**3b — Trim phantom queue routes**
In `celery_config.py`, remove every `task_routes` entry that points to a
function not defined anywhere in the codebase. Leave only the route for
`glyph.specialized_workers.evaluation.tasks.run_evaluation`. Add a `# TODO`
comment block listing each removed route so they are easy to restore when the
missing tasks are implemented.

**3c — Add `Trial` row writes via `trial_observer`**
In `_execute_and_save_run`, pass a `trial_observer` to `EvaluationRunner` that
writes a `Trial` ORM row to the DB after each trial completes. The observer
must be non-blocking — wrap the DB write in `asyncio.create_task` so a slow DB
write never delays the next trial.

**3d — Add `task_id` to `Run` ORM and store it**
- Add `task_id: Mapped[str | None]` column to `Run` in `db/orm_models.py`.
- In `RunService.trigger_run`, after `run_evaluation.delay(...)`, retrieve
  `task.id` and update the DB row: `UPDATE runs SET task_id = ? WHERE id = ?`.

**3e — Wire cancellation**
Add `RunService.cancel_run(run_id)`:
- Load the `Run` row. If `task_id` is None or status is already terminal,
  return an error.
- Call `celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")`.
- Update the DB row status to `"cancelled"`.

### Acceptance criteria
- Starting a Celery worker with `--pool=prefork` and `--pool=solo` both work
  without "Event loop is already running" errors.
- After a run completes, `Trial` rows exist in the DB for every trial.
- `RunService.cancel_run` calls `revoke` and sets status to `"cancelled"`.


---

## Part 4a — API internals hardening

### Problems (none require moving files — the structure is correct)
1. `RunService` uses static methods — untestable without module patching, no DI.
2. `DatasetService.list_datasets` hardcodes `"datasets"` path relative to CWD.
3. `RunResponse` and `RunListItem` duplicate all 14 fields — drift-prone.
4. `GET /api/health` returns hardcoded `"healthy"` even if the DB is down.
5. `Run.finished_at` is non-nullable but is set to `now()` at queue time, so
   any duration display shows nonsense for running or queued jobs.
6. Services call `get_session()` directly — sessions are not tied to the
   FastAPI request lifecycle, and the `trigger_run` DB write + Celery dispatch
   are not atomic.

### Work

**4a-1 — Introduce `Settings`**
Add `src/glyph/api/settings.py`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///glyph.db"
    datasets_dir: str = "datasets"
    artifacts_dir: str = "artifacts"
    celery_broker_url: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```
Use `lru_cache` to get a singleton. Wire into `create_app` lifespan and pass
into services via `Depends`.

**4a-2 — Convert services to instance methods with `Depends()`**
Change `RunService`, `DatasetService`, `GraderService` from classes with
`@staticmethod` methods to classes initialised with settings:
```python
class RunService:
    def __init__(self, settings: Settings = Depends(get_settings)): ...
    async def list_runs(self, ...) -> list[RunListItem]: ...
```
Route handlers receive the service via `Depends(RunService)`.

**4a-3 — Extract `RunBase` schema**
```python
class RunBase(BaseModel):
    id: str
    suite_id: str
    suite_version: str
    status: str
    started_at: datetime
    finished_at: datetime | None   # nullable
    ...

class RunListItem(RunBase): pass
class RunResponse(RunBase):
    summary: dict[str, Any] | None = None
```

**4a-4 — Make `Run.finished_at` nullable**
Change `finished_at: Mapped[datetime]` → `finished_at: Mapped[datetime | None]`
in `db/orm_models.py`. Update `trigger_run` to pass `finished_at=None`.

**4a-5 — Real health check**
`GET /api/health` probes the DB with `SELECT 1` and returns:
```json
{
  "status": "healthy" | "degraded" | "unhealthy",
  "db": "ok" | "error",
  "broker": "ok" | "unconfigured" | "error"
}
```
If the DB probe raises, status is `"unhealthy"` and HTTP 503 is returned.

### Acceptance criteria
- `RunService` can be instantiated in a test with a mock `Settings` without
  patching any module-level globals.
- `GET /api/health` returns HTTP 503 when the DB URL is unreachable.
- `Run.finished_at` is NULL for queued and running rows.


---

## Part 4b — Rate limiting

### Work
Add `slowapi>=0.1.9` to `[project.optional-dependencies] web` in `pyproject.toml`.

Configure `SlowAPI` as middleware in `create_app()`. Per-IP limits:

| Endpoint | Limit |
|---|---|
| `POST /api/runs` | 10 / minute |
| `POST /api/datasets` | 5 / minute |
| `GET /api/runs/{run_id}/stream` | 20 / minute |
| `POST /api/compare` | 30 / minute |
| `POST /api/release` | 30 / minute |
| All other endpoints | 120 / minute |

On limit exceeded return HTTP 429 with `Retry-After: <seconds>` header.
Add a `GET /api/health` exemption (no rate limit — used for polling).

### Acceptance criteria
- Sending 11 `POST /api/runs` requests within one minute from the same IP
  returns HTTP 429 on the 11th with a `Retry-After` header.
- `GET /api/health` is never rate-limited.

---

## Part 4c — New API routes: runs

All routes are added to `src/glyph/api/routes/runs.py` and wired in `main.py`.

```
GET  /api/runs/{run_id}/trials
     Query: status, suite, limit (default 50), offset (default 0)
     Response: list[TrialListItem]
     Returns Trial rows from DB. If run is still in progress, returns
     whatever rows exist so far (allows live polling from UI).

GET  /api/runs/{run_id}/stream
     Response: text/event-stream
     Streams SSE events while the run is in progress.
     Event shape matches --format json-stream output:
       data: {"event":"trial_complete","case_id":"...","status":"passed",...}
       data: {"event":"run_complete","run_id":"...","pass_rate":0.98,...}
     Implementation: poll Run.summary JSON column for new trial events every
     500ms. Emit each new event once. Close stream when status is terminal.

DELETE /api/runs/{run_id}
     Calls RunService.cancel_run(run_id).
     Returns 200 {cancelled: true} or 409 if already terminal.

POST /api/runs/{run_id}/rerun
     Reads the original config from Run.summary["config"].
     Creates a new Run row with a new ID.
     Dispatches run_evaluation.delay with the same config.
     Returns TriggerRunResponse with the new job_id.

POST /api/runs/validate
     Body: TriggerRunRequest (same as POST /api/runs)
     Validates that config contains "factory" and "dataset" keys,
     that the dataset file exists and is valid JSONL.
     Does NOT dispatch any task.
     Returns 200 {valid: true} or 422 with validation errors.
```

New schemas needed in `src/glyph/schemas/runs.py`:
- `TrialListItem`: `id, run_id, case_id, suite, status, score, duration_ms, started_at`
- `ValidateRunResponse`: `valid: bool, errors: list[str]`

### Acceptance criteria
- `GET /api/runs/{id}/trials` returns an empty list for a brand-new queued run
  and a non-empty list after the run completes.
- `GET /api/runs/{id}/stream` responds with `Content-Type: text/event-stream`.
- `DELETE /api/runs/{id}` on a completed run returns HTTP 409.
- `POST /api/runs/validate` with a missing dataset returns 422.


---

## Part 4d — New API routes: compare, release, datasets CRUD, artifacts

### Compare & Release
New file: `src/glyph/api/routes/compare.py`

```
POST /api/compare
     Body: {candidate_path: str, baseline_path: str}
     Calls glyph.grading.comparison.compare(candidate, baseline).
     Returns ComparisonResponse:
       common_cases, improved, regressed, unchanged,
       candidate_pass_rate, baseline_pass_rate, pass_rate_delta

POST /api/release
     Body: {artifact_path: str, policy: str, baseline_path?: str}
     policy is one of: "default", "staging", "strict", "development"
     Loads RunSummary from artifact_path JSONL (last line).
     Instantiates ReleaseGate with the named policy preset.
     Calls gate.evaluate_release(summary, comparison_baseline=baseline_path).
     Returns ReleaseDecisionResponse (mirrors ReleaseDecision domain model).
```

New file: `src/glyph/schemas/compare.py` with `ComparisonRequest`,
`ComparisonResponse`, `ReleaseRequest`, `ReleaseDecisionResponse`.

### Datasets
Extend `src/glyph/api/routes/datasets.py`:

```
GET  /api/datasets
     Existing — add case_count to DatasetItem response.

GET  /api/datasets/{name}/cases
     Query: limit (default 50), offset (default 0)
     Returns paginated list of EvalCase objects from the JSONL file.
     404 if dataset not found.

POST /api/datasets
     Body: multipart/form-data with a "file" field (.jsonl).
     Validates the file is valid JSONL with unique case IDs.
     Saves to settings.datasets_dir/{filename}.
     Returns DatasetItem.

DELETE /api/datasets/{name}
     Deletes datasets_dir/{name}.jsonl.
     Returns 404 if not found.

GET  /api/datasets/{name}/validate
     Runs the same checks as `glyph datasets validate`:
     - All cases parse as EvalCase
     - No duplicate IDs
     - Suite distribution
     - Tag coverage warning (< 50% tagged)
     Returns DatasetValidationResponse:
       valid: bool, case_count: int, suite_counts: dict,
       errors: list[str], warnings: list[str]
```

### Artifacts
New file: `src/glyph/api/routes/artifacts.py`

```
GET  /api/artifacts
     Lists all .jsonl files in settings.artifacts_dir (non-recursive).
     Returns list[ArtifactItem]: name, path, size_bytes, modified_at.

GET  /api/artifacts/{name}/summary
     Reads the last valid RunSummary line from the file.
     Returns RunSummary fields as ArtifactSummaryResponse.
     404 if file not found or no summary present.

GET  /api/artifacts/{name}/trials
     Query: status, suite, limit (default 50), offset (default 0)
     Streams through the JSONL file, collects TrialRecord lines.
     Returns paginated list[TrialListItem].

GET  /api/artifacts/{name}/trial/{case_id}
     Returns the single TrialRecord for case_id.
     404 if not found.
```

New file: `src/glyph/api/routes/artifacts.py`.
New schemas in `src/glyph/schemas/artifacts.py`.

Wire all new routers in `main.py`.

### Acceptance criteria
- `POST /api/compare` with valid artifact paths returns a `ComparisonResponse`
  with correct `pass_rate_delta`.
- `POST /api/release` with policy `"strict"` returns `allowed: false` when the
  artifact pass_rate is below 1.0.
- `POST /api/datasets` with a valid JSONL file creates the file on disk and
  returns 200.
- `POST /api/datasets` with a file containing duplicate case IDs returns 422.
- `GET /api/artifacts/{name}/trials` returns trial records parsed from the file.


---

## Part 4e — Extend health endpoint

Already covered in Part 4a-5. No additional work needed beyond what is
specified there. The health route lives in `src/glyph/api/routes/health.py`
and must probe both the DB and the Celery broker URL.

---

## Part 5 — CLI polish

All changes are in `src/glyph/cli/cli.py` and `src/glyph/utils/formatting.py`.
No new files needed.

### `glyph run` additions
- Add `--dry-run` flag. When set: load the factory, validate the dataset
  schema and sandbox requirements, print a summary of what would run, then
  exit 0 (or exit 1 if validation fails). No trials are executed.
- In `--format rich` mode (default), show a live progress bar using the
  existing `create_progress_callback` helper from `formatting.py` (currently
  unused). Display alongside the streaming trial events.
- After all trials, if `summary.failed > 0`, print a compact failure table:
  case ID | first failed grade | score. Users should not need a follow-up
  `glyph artifacts trial` command for routine failures.

### `glyph doctor` additions
For every failing check, print a one-line "→ fix:" hint below the status icon.
Examples:
- Artifacts missing → `→ fix: mkdir artifacts`
- Database not configured → `→ fix: export DATABASE_URL=...`
- Redis not configured → `→ fix: export CELERY_BROKER_URL=redis://localhost:6379/0`

### `glyph datasets validate` additions
- Error (exit 1) on duplicate case IDs.
- Warning (still exit 0) when fewer than 50% of cases have tags.
- Suggestion to run `glyph generation create` when fewer than 5 cases.

### `glyph compare` additions
When regressions exist, list each regressed case ID inline below the summary
table (not just a count). Keep it compact: one line per case.

### New: `glyph open`
```
glyph open [--port PORT]
```
Opens `http://localhost:{PORT}/app` (default 8000) in the system browser using
`webbrowser.open`. If the server is not reachable (quick `httpx.get` with 1s
timeout), prints: `Server not running. Start it with: glyph serve`

### New: `glyph status <run_id>`
```
glyph status RUN_ID [--poll] [--format FORMAT]
```
Calls `GET /api/runs/{run_id}`. With `--poll`, refreshes every 3 seconds
using Rich's `Live` display until the run reaches a terminal status. Without
`--poll`, prints once and exits. Supports `--format json`.

### Acceptance criteria
- `glyph run --dry-run --factory examples.simple_graph:create_evaluation
  --dataset datasets/example.jsonl` exits 0 and prints "dry run — 2 cases"
  without creating any artifact file.
- `glyph doctor` prints a `→ fix:` line for every check that fails.
- `glyph open` opens the browser when the server is running, or prints the
  startup instruction when it is not.


---

## Part 6 — Web console

### Guiding constraints
- The marketing landing page at `/` is left exactly as-is.
- No new npm packages beyond what is already installed unless strictly
  unavoidable. All data fetching uses native `fetch` + `useEffect`.
  SSE uses the native `EventSource` API.
- Follow the existing inline-style + CSS modules pattern throughout.
  No Tailwind, no styled-components.
- API base URL: `NEXT_PUBLIC_API_URL` env var, default `http://localhost:8000`.
- All interactive elements have accessible `aria-label` attributes.
- Page transitions use `framer-motion` `AnimatePresence` (already installed).

### Route structure
```
/                        existing landing page — untouched
/app                     redirects to /app/runs
/app/runs                run list
/app/runs/new            trigger run form
/app/runs/[id]           live run detail with SSE
/app/datasets            dataset list
/app/datasets/[name]     case table viewer
/app/artifacts           artifact list
/app/artifacts/[name]    artifact detail
/app/compare             comparison form + result
/app/release             release gate form + decision
```

### Part 6a — AppShell layout

New file: `web/src/app/app/layout.tsx`
New file: `web/src/components/AppShell.tsx`
New file: `web/src/components/AppShell.module.css`
New file: `web/src/components/CliGuideDrawer.tsx`
New file: `web/src/components/CliGuideDrawer.module.css`

**Sidebar (52px icon rail, collapsible to 200px with labels)**
Background `#0f172a` — identical to `DashboardPreview` sidebar.
Nav items and their routes:

| Icon | Label | Route |
|---|---|---|
| Grid | Runs | /app/runs |
| Database | Datasets | /app/datasets |
| Archive | Artifacts | /app/artifacts |
| GitCompare | Compare | /app/compare |
| Shield | Release | /app/release |
| Terminal | CLI Guide | opens drawer |

Active route item highlighted with `rgba(99,102,241,0.25)` background,
matching `DashboardPreview` exactly.

**Top header bar (44px)**
- Left: breadcrumb of current page path.
- Center: "glyph" wordmark.
- Right: API connection indicator dot (green = `GET /api/health` 200, red
  = unreachable, polled every 10s) + "New Run" button → `/app/runs/new`.

**CLI Guide drawer**
A 420px panel that slides in from the right over the content (not a route).
Contains a scrollable, structured reference of every CLI command with
real copy-pasteable examples. Sections:
`Run · Compare · Release · Artifacts · Datasets · Generation · Init · Doctor`
Each command shows the flag summary and one realistic example.
This is the single in-app answer to "I can't remember the command syntax".

### Part 6b — `/app/runs` and `/app/runs/new`

**`/app/runs`**
Data: `GET /api/runs` (poll every 5s while any run has status `running`).
Display: table or cards.
Columns: run ID (truncated + copy button), suite, started (relative time),
duration, pass rate (color-coded: green ≥ 90%, yellow ≥ 70%, red < 70%),
status badge.
Filter bar: status dropdown, suite ID text input. Filters applied client-side.
Click row → `/app/runs/[id]`.
Empty state: clear message + "Trigger your first run" button.

**`/app/runs/new`**
Two-panel form:

Left — *What to run*:
- Dataset picker: dropdown from `GET /api/datasets`. Shows name + case count.
- Factory input: text field `module:function`. Placeholder shows format.
  "Validate" button calls `POST /api/runs/validate` inline.
- Output path: pre-filled `artifacts/{timestamp}.jsonl`, editable.

Right — *Budget & policy*:
- Timeout (seconds) — default 60
- Max tool calls — default 20
- Max concurrency — default 4
- Run ID override — empty = auto-generated

"Run Evaluation" submits `POST /api/runs`. On success redirects to
`/app/runs/[id]`. Inline validation errors shown under each field.

### Part 6c — `/app/runs/[id]` live detail

Data sources:
- `GET /api/runs/{id}` polled every 3s until terminal status.
- `EventSource` on `GET /api/runs/{id}/stream` for real-time events.

Layout (three sections):

**Top — run metadata strip**
Suite badge, status badge (live), started time, elapsed duration (counting
up while running), total / passed / failed / errors counters updating live.
Cancel button (shown while queued or running) → `DELETE /api/runs/{id}` with
confirmation dialog.

**Middle — grader progress**
One horizontal bar per grader. Pass count / total, percentage, colour
(green ≥ 90%, yellow ≥ 70%, red < 70%). Updates as SSE `trial_complete`
events arrive. Uses the same bar layout as `DashboardPreview` grader matrix.

**Bottom — trial event table**
Columns: case ID, suite badge, status icon (✓/✗/⏱/⚠), score, duration (ms),
grade summary (one dot per grader: green = passed, red = failed).
Rows append in real time. Clicking a row expands inline to show full grade
list: grader name, score, reason text.

**Action bar (shown once run is complete)**
- "Compare to baseline" → pre-fills `/app/compare` candidate field.
- "Gate release" → pre-fills `/app/release` artifact field.
- "Download artifact" → `GET /api/artifacts/{name}` raw JSONL download.

**Error banner (shown when errors > 0)**
Red banner: "N errors — error_type_1 (x), error_type_2 (y)".
"Filter to errors" toggle narrows the trial table.


### Part 6d — `/app/datasets` and `/app/datasets/[name]`

**`/app/datasets`**
Data: `GET /api/datasets`.
Display: grid of cards. Each card: dataset name, case count, suite
distribution as three coloured pills (capability / regression / security),
path. "Upload Dataset" button opens native file picker → `POST /api/datasets`
multipart. Upload progress shown inline. "Validate" button per card →
`GET /api/datasets/{name}/validate`, result shown in an inline toast.
Click card → `/app/datasets/[name]`.

**`/app/datasets/[name]`**
Data: `GET /api/datasets/{name}/cases` (paginated, 25/page).
Summary bar: total cases, suite distribution, top-10 tags as pills.
Cases table: case ID, suite badge, tags, input preview (first 80 chars).
Pagination controls: previous / next / page number.
"Validate" button: runs validate endpoint, shows issues inline.
"Run on this dataset" → `/app/runs/new` with dataset pre-selected.
"Delete dataset" → `DELETE /api/datasets/{name}` with confirmation dialog.

### Part 6e — `/app/artifacts` and `/app/artifacts/[name]`

**`/app/artifacts`**
Data: `GET /api/artifacts`.
Cards: artifact name, run ID (from summary), total cases, pass rate
(colour-coded), started time, file size. If no RunSummary found, show
"incomplete artifact" label.

**`/app/artifacts/[name]`**
Data: `GET /api/artifacts/{name}/summary` + `GET /api/artifacts/{name}/trials`.

Top section (summary panel):
- KPI row: pass rate, average score, total cases, duration. With sparkline
  dots for each suite (matching `DashboardPreview` tab-0 KPI row style).
- Grader matrix table: grader name, pass bar, passed/total. Identical layout
  to `DashboardPreview` grader matrix card, populated from real data.
- Suite breakdown: capability / regression / security pass rates.

Bottom section (trial table):
- Paginated, 25/page.
- Columns: case ID, suite, status icon, score, duration.
- Click to expand inline: full grade list with reasons.
- Status filter dropdown.

"Download" button: serves the raw JSONL via `GET /api/artifacts/{name}/raw`
(add this one endpoint to return the file with `Content-Disposition: attachment`).
"Compare to another artifact" link → pre-fills `/app/compare`.

### Part 6f — `/app/compare` and `/app/release`

**`/app/compare`**
Two dropdowns: "Candidate artifact" and "Baseline artifact", both populated
from `GET /api/artifacts`. Can also type a path manually.
"Compare" button → `POST /api/compare`.

Result section (shown after response):
- Regression analysis table matching `DashboardPreview` tab-3 layout:
  metric | baseline | candidate | delta columns, real data.
- Improved / regressed / unchanged counts with coloured badges.
- Regressed case IDs listed as links (if they exist in the candidate artifact,
  link to `/app/artifacts/{name}/trial/{case_id}`).
- "Copy as PR comment" button: formats result as Markdown matching
  `--format pr-comment` output and copies to clipboard.

**`/app/release`**
Three inputs:
1. "Evaluation artifact" dropdown (required) — from `GET /api/artifacts`.
2. "Baseline artifact" dropdown (optional) — enables regression check.
3. "Policy" selector: `default / staging / strict / development` with a
   one-line description of each visible below the selector.

"Evaluate Release" → `POST /api/release`.

Result section:
- Large banner: green "RELEASE ALLOWED" or red "RELEASE BLOCKED" with the
  reason string. Same visual weight as the CLI rule output.
- Three-row checklist: Deterministic / Regression / Judge — pass/fail icon
  + rationale text. Matches `_format_release_decision_rich` layout.
- Metrics grid: overall / capability / regression / security pass rates,
  error rate, regression count.
- Composite score donut using the `MiniDonut` component already in
  `DashboardPreview.tsx` (reuse it directly).
- "Copy as PR comment" button.

---

## Implementation order

Execute parts strictly in this sequence. Verify acceptance criteria before
moving to the next part.

1. Part 1 — import shims (unblocks everything)
2. Part 2 — sandbox fixes
3. Part 3 — Celery fixes
4. Part 4a — API internals hardening
5. Part 4b — rate limiting
6. Part 4c — new run routes
7. Part 4d — compare / release / datasets / artifacts routes
8. Part 4e — health probe (covered in 4a)
9. Part 5 — CLI polish
10. Part 6a — AppShell + CLI Guide drawer
11. Part 6b — runs list + new run form
12. Part 6c — live run detail with SSE
13. Part 6d — datasets pages
14. Part 6e — artifacts pages
15. Part 6f — compare + release pages

---

## Files changed per part (summary)

| Part | New files | Modified files |
|---|---|---|
| 1 | `evaluation/__init__.py`, `evaluation/definition.py`, `evaluation/runner.py`, `evaluation/human.py`, `evaluation/online.py`, `evaluation/optimizers.py`, `evaluation/tasks.py` | `specialized_workers/evaluation/runner.py`, `.github/workflows/ci.yml` |
| 2 | `docs/SANDBOX_PROVIDERS.md` | `security/offline_sandbox.py` |
| 3 | — | `specialized_workers/evaluation/tasks.py`, `specialized_workers/infra/celery_config.py`, `db/orm_models.py`, `services/run_service.py` |
| 4a | `api/settings.py` | `api/main.py`, `api/routes/health.py`, `schemas/runs.py`, `services/run_service.py`, `services/dataset_service.py`, `db/orm_models.py` |
| 4b | — | `api/main.py`, `pyproject.toml` |
| 4c | — | `api/routes/runs.py`, `schemas/runs.py`, `services/run_service.py` |
| 4d | `api/routes/compare.py`, `api/routes/artifacts.py`, `schemas/compare.py`, `schemas/artifacts.py` | `api/routes/datasets.py`, `api/main.py`, `services/dataset_service.py` |
| 5 | — | `cli/cli.py`, `utils/formatting.py` |
| 6a | `web/src/app/app/layout.tsx`, `web/src/components/AppShell.tsx`, `web/src/components/AppShell.module.css`, `web/src/components/CliGuideDrawer.tsx`, `web/src/components/CliGuideDrawer.module.css` | — |
| 6b | `web/src/app/app/runs/page.tsx`, `web/src/app/app/runs/page.module.css`, `web/src/app/app/runs/new/page.tsx`, `web/src/app/app/runs/new/page.module.css` | — |
| 6c | `web/src/app/app/runs/[id]/page.tsx`, `web/src/app/app/runs/[id]/page.module.css` | — |
| 6d | `web/src/app/app/datasets/page.tsx`, `web/src/app/app/datasets/[name]/page.tsx` + css | — |
| 6e | `web/src/app/app/artifacts/page.tsx`, `web/src/app/app/artifacts/[name]/page.tsx` + css | — |
| 6f | `web/src/app/app/compare/page.tsx`, `web/src/app/app/release/page.tsx` + css | — |
