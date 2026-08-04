# ⚡ Glyph

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

**A production-grade evaluation harness for AI applications.** 

Glyph keeps your prompts, datasets, graders, and test artifacts strictly under local control, enabling fast, reproducible, and secure agent evaluations directly in your CI pipeline. 

## 🚀 Why Glyph?

Evaluating Agentic workflows shouldn't require complex cloud infrastructure or leaking proprietary test data. Glyph gives you a robust, fail-closed testing environment that feels like standard unit testing.

* **🎯 Framework-Agnostic:** Built with native LangGraph support, but easily adaptable to any framework.
* **🛡️ Secure Sandboxing:** Run evaluations in isolated environments (Docker, K8s) with capability preflights and shielded cleanup.
* **🧪 Deterministic Grading:** Ensure correctness with Exact Match, Heuristic, State, and Tool Policy graders.
* **🧠 Calibrated Model Judges:** Use AI-as-a-judge with pre-call budget constraints.
* **📊 Robust Telemetry:** Opt-in OpenTelemetry tracing and RED metrics for all trials and graders.
* **🔒 Local-First Evidence:** Uses immutable JSONL artifacts for reliable Candidate-vs-Baseline comparisons.

---

## 🏃‍♀️ Quick Start

### 1. Install Glyph

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/tyraakj/eval-harness-pipeline/main/install.ps1 | iex
```

**macOS/Linux:**
```bash
curl -LsSf https://raw.githubusercontent.com/tyraakj/eval-harness-pipeline/main/install.sh | bash
```

Alternatively, install from source:
```bash
uv sync --all-extras
```

### 2. Initialize a Project
Create a new evaluation workspace with scaffolding (datasets, examples, and prompts):
```bash
uv run glyph init my-evaluation
cd my-evaluation
```

### 3. Run Your First Evaluation
Run an evaluation suite against a dataset:
```bash
uv run glyph run \
	--factory examples.simple_graph:create_evaluation \
	--dataset datasets/example.jsonl \
	--output artifacts/results.jsonl
```

Compare a new candidate against a baseline:
```bash
uv run glyph compare \
	--candidate artifacts/results.jsonl \
	--baseline artifacts/baseline.jsonl \
	--max-regressions 0
```

---

## 📚 Documentation & Deep Dives

To keep this README clean, we've broken our extensive documentation into focused guides:

| Guide | Description |
|---|---|
| [**User Guide**](docs/USER_GUIDE.md) | The complete manual: Connecting graphs, Heuristic Graders, Task Metadata, Sandboxing, Model Judges, DSPy, and LangSmith. |
| [**Architecture**](docs/ARCHITECTURE.md) | System boundaries, production guidance, and internal module design. |
| [**Data Flow**](docs/DATA_FLOW.md) | Detailed trace of how data moves from targets to graders to artifacts. |
| [**Web API & Workers**](docs/WEB_API.md) | Setting up the FastAPI server, Celery background workers, and PostgreSQL. |
| [**Module Reference**](docs/MODULE_REFERENCE.md) | Complete map of the internal `glyph` codebase. |

---

## 📦 Distribution (Standalone Binaries)

If you want to distribute Glyph to users who don't have Python installed, you can build a standalone executable using [PyInstaller](https://pyinstaller.org/).

First, install PyInstaller:
```bash
uv add --dev pyinstaller
```

Then, run the build command from the root of the project:
```bash
uv run pyinstaller --name glyph --onefile src/glyph/__main__.py
```

This generates a standalone executable in the `dist/` folder (e.g., `dist/glyph.exe`). Users can run this directly:
```bash
./glyph run --factory examples.simple_graph:create_evaluation --dataset datasets/example.jsonl
```

---

## 💻 CLI Command Reference

| Command | Description |
|---------|-------------|
| `glyph run` | Run an evaluation dataset and return a CI-friendly exit code |
| `glyph compare` | Compare candidate and baseline artifacts by stable case ID |
| `glyph release` | Evaluate whether a release should be allowed based on policy |
| `glyph serve` | Start the FastAPI web server |
| `glyph worker` | Start a Celery background worker |
| `glyph init` | Scaffold a new evaluation project |
| `glyph datasets list`| View available evaluation datasets |
| `glyph history` | View recent local evaluation runs |
| `glyph config` | Display current environment configuration |

---

## 🏗️ Testing & CI Policy

Glyph runs seamlessly in CI pipelines. 

The `run` command exits nonzero for errors, timeouts, or a pass rate below the configured threshold. The `compare` command exits nonzero when regressions or pass-rate degradation exceed policy. 

To run internal quality checks on the Glyph codebase itself:
```bash
uv run pytest
uv run ruff check .
uv run mypy
uv build
```
