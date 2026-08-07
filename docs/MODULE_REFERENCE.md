# Module Reference

This document maps the `src/glyph` package structure, providing a high-level overview of each module's responsibility.

## Top-Level Packages

- `api/`: FastAPI web layer and dependency injection.
- `cli/`: Typer-based command-line interface.
- `core/`: Immutable data models, configuration loaders, and core contracts.
- `db/`: SQLAlchemy models, migrations, and database session management.
- `evaluation/`: The core evaluation loop, human review, and online evaluator.
- `exporters/`: Async dispatchers for external data export (e.g., LangSmith).
- `grading/`: Implementations of deterministic and heuristic graders.
- `monitoring/`: OpenTelemetry tracing and RED metrics.
- `schemas/`: Pydantic schemas for API and data validation.
- `security/`: Sandbox provider implementations and security contracts.
- `services/`: Business logic mediating between the API/CLI and core runner.
- `targets/`: Adapters connecting evaluation tasks to external AI frameworks.
- `utils/`: Reusable utilities and helper classes.

## Detailed Module Map

### `api/` (Web Layer)
- `dependencies.py`: FastAPI dependency injection (e.g., getting DB sessions, Redis clients).
- `routes/`: FastAPI endpoints.
  - `runs.py`: Endpoints for triggering and listing evaluation runs.
  - `health.py`: Liveness and readiness checks.

### `cli/` (Command Line)
- `cli.py`: The main `glyph` entrypoint defining `run`, `compare`, `release`, `serve`, `worker`, and `init` commands.
- `formatters.py`: Rich console formatting for CLI output.

### `core/` (Data & Contracts)
- `models.py`: Immutable data structures (`EvalCase`, `TrialRecord`, `RunSummary`, `ReleasePolicy`, etc.).
- `config.py`: YAML-driven evaluation configuration loading and validation.
- `contracts.py`: Foundational `Protocol` definitions (if separated from models).

### `db/` (Persistence)
- `session.py`: Async SQLAlchemy engine and session factory setup.
- `models/`: SQLAlchemy declarative base and ORM models for runs, trials, and metrics.
- `alembic/`: Database migrations.

### `evaluation/` (Execution Loop)
- `runner.py`: The `EvaluationRunner` orchestrating sandbox, target, and graders.
- `release_gate.py`: Logic for applying `ReleasePolicy` to generate a `ReleaseDecision`.
- `human.py`: Asynchronous `HumanEvaluationLedger` and adjudication rules.
- `online.py`: `OnlineEvaluator` for production trace evaluation with cost and sampling controls.
- `optimizers.py`: DSPy optimizer integration logic.
- `specialized_workers/`: Zero-token replay evaluation architecture.
  - `artifact.py`: Immutable `EvaluationArtifact` for frozen evidence storage.
  - `cache.py`: Content-addressed cache system with dependency-based cache keys.
  - `executors.py`: Live and replay executors for separated execution modes.
  - `storage_layers.py`: Three-tier storage (PostgreSQL, Object Storage, Redis).
  - `baseline.py`: Baseline and candidate services for comparative evaluation.
  - `grader_router.py`: Selective evaluation with AI judge escalation.
  - `dataset_service.py`: Dataset versioning with zero-token generation modes.
  - `base.py`: Base classes for workers and artifact processing.
  - `tool_evaluator.py`: Tool policy evaluation (standard and artifact modes).
  - `retrieval_evaluator.py`: Retrieval quality evaluation (standard and artifact modes).
  - `graph_evaluator.py`: Graph compliance evaluation (standard and artifact modes).
  - `output_evaluator.py`: Output quality evaluation (standard and artifact modes).
  - `security_evaluator.py`: Security evaluation (standard and artifact modes).
  - `performance_evaluator.py`: Performance evaluation (standard and artifact modes).
  - `orchestrator.py`: Evaluation orchestrator for routing evidence to workers.
  - `aggregator.py`: Result aggregation and release decision generation.
  - `storage.py`: Worker result storage with idempotency handling.
  - `celery_config.py`: Celery queue configuration for specialized workers.
  - `tasks.py`: Celery tasks for distributed worker execution.

### `exporters/` (Data Export)
- `exporting.py`: The `ExportDispatcher` and base export queue logic.
- `langsmith_exporter.py`: Implementation of `EvaluationExporter` for LangSmith integration.

### `grading/` (Graders)
- `graders.py`: Deterministic graders (`ExactMatchGrader`, `ContainsAllGrader`, `ToolPolicyGrader`, etc.).
- `heuristics.py`: Heuristic graders (`SimilarityGrader`, `LengthGrader`, `KeywordPresenceGrader`, etc.).
- `judges.py`: `CalibratedModelJudge` for LLM-as-a-judge execution with cost control.

### `monitoring/` (Observability)
- `telemetry.py`: Abstractions for spanning, tracing, and metric collection.
- `observability.py`: OpenTelemetry setup (OTLP over HTTP exporter configuration).

### `schemas/` (API Validation)
- `api_models.py`: Pydantic schemas separating API request/response shape from core models.

### `security/` (Isolation)
- `sandbox.py`: `SandboxProvider` protocol and standard implementations (`NoopSandboxProvider`).
- `capabilities.py`: Definitions of isolation capabilities (network, filesystem, etc.).

### `services/` (Business Logic)
- `evaluation_service.py`: Service bridging the FastAPI/Celery layer to the core `EvaluationRunner`.
- `worker.py`: Celery worker setup and task definitions.

### `targets/` (Framework Adapters)
- `target.py`: Base `Target` protocol definition.
- `langgraph_target.py`: specific adapter for executing and observing compiled LangGraph applications.

### `utils/` (Shared Utilities)
- `prompts.py`: `PromptRegistry` for loading, hashing, and rendering immutable prompt releases.
- `hashing.py`: SHA-256 and content-hashing utilities for provenance tracking.
