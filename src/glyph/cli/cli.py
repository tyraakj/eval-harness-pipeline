from __future__ import annotations

import asyncio
import importlib
import json
import sys
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.table import Table

from glyph.core.domain_models import RunSummary, TrialRecord
from glyph.evaluation.definition import EvaluationDefinition
from glyph.evaluation.runner import EvaluationRunner
from glyph.generation import (
    CaseGenerator,
    CaseReview,
    GenerationSpec,
    append_review,
    generate_draft,
    load_draft,
    promote_draft,
)
from glyph.grading.comparison import compare as compare_runs
from glyph.monitoring.observability import configure_otel_from_env
from glyph.specialized_workers.gates.release_gate import ReleaseGate
from glyph.utils.datasets import load_jsonl
from glyph.utils.formatting import (
    OutputFormat,
    console,
    format_comparison,
    format_release_decision,
    format_run_summary,
    format_trial_detail,
    print_command_start,
    print_status_bar,
    print_trial_event,
    print_trial_start,
)

app = typer.Typer(
    no_args_is_help=True,
    help="Versioned evidence and release gates for AI applications.",
    rich_markup_mode="markdown",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        console.print("[glyph.brand]glyph[/glyph.brand] 0.1.0")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """Run, inspect, compare, and release versioned AI evaluations."""


def _validate_output_format(output_format: str) -> None:
    if output_format not in {OutputFormat.RICH, OutputFormat.JSON, OutputFormat.JSON_STREAM, OutputFormat.RPC, OutputFormat.PR_COMMENT}:
        raise typer.BadParameter("format must be rich, json, json-stream, rpc, or pr-comment")


def _load_factory(reference: str) -> Callable[[], EvaluationDefinition]:
    if ":" not in reference:
        raise typer.BadParameter("Factory must use module:function syntax")
    module_name, function_name = reference.split(":", 1)
    working_directory = str(Path.cwd())
    if working_directory not in sys.path:
        sys.path.insert(0, working_directory)
    module = importlib.import_module(module_name)
    factory: Any = getattr(module, function_name, None)
    if not callable(factory):
        raise typer.BadParameter(f"Factory is not callable: {reference}")
    return cast(Callable[[], EvaluationDefinition], factory)


def _load_generator(reference: str) -> CaseGenerator:
    """Load a ``module:function`` factory that returns a case generator."""
    if ":" not in reference:
        raise typer.BadParameter("Generator must use module:function syntax")
    module_name, function_name = reference.split(":", 1)
    working_directory = str(Path.cwd())
    if working_directory not in sys.path:
        sys.path.insert(0, working_directory)
    module = importlib.import_module(module_name)
    factory: Any = getattr(module, function_name, None)
    if not callable(factory):
        raise typer.BadParameter(f"Generator factory is not callable: {reference}")
    generator = factory()
    if not all(hasattr(generator, attribute) for attribute in ("name", "version", "generate")):
        raise typer.BadParameter("Generator must expose name, version, and generate(spec)")
    return cast(CaseGenerator, generator)


@app.command()
def run(
    factory: Annotated[str, typer.Option(help="Evaluation factory as module:function")],
    dataset: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option(dir_okay=False)] = Path("artifacts/results.jsonl"),
    minimum_pass_rate: Annotated[float, typer.Option(min=0.0, max=1.0)] = 1.0,
    run_id: Annotated[str | None, typer.Option()] = None,
    overwrite: Annotated[bool, typer.Option(help="Replace an existing artifact file")] = False,
    output_format: Annotated[
        str, typer.Option("--format", help="rich, json, json-stream, rpc, or pr-comment")
    ] = OutputFormat.RICH,
    stream: Annotated[
        bool,
        typer.Option("--stream/--no-stream", help="Print one event as each test completes"),
    ] = False,
    check: Annotated[
        bool,
        typer.Option("--check", help="Check config without running tests"),
    ] = False,
    workers: Annotated[
        bool,
        typer.Option("--workers", help="Run extra analysis checks"),
    ] = False,
) -> None:
    """Run a dataset and return a CI-friendly exit code."""
    definition = _load_factory(factory)()
    if not isinstance(definition, EvaluationDefinition):
        raise typer.BadParameter("Factory must return EvaluationDefinition")
    cases = load_jsonl(dataset)
    _validate_output_format(output_format)
    if output_format == OutputFormat.RICH:
        print_command_start(
            "run",
            detail=f"{len(cases)} tests | {definition.repetitions} repetition(s) | {dataset}",
            run_id=run_id,
        )

    if check:
        console.print()
        console.print("  [bold]Checks[/bold]")
        
        has_cases = len(cases) > 0
        console.print(f"  [green][PASS][/green] Evaluation setup loaded: {factory}")
        console.print(f"  [{'green' if has_cases else 'red'}][{'PASS' if has_cases else 'FAIL'}][/{'green' if has_cases else 'red'}] Dataset ready ({len(cases)} tests)")
        
        has_folder = output.parent.exists() or output.parent == Path("")
        console.print(f"  [{'green' if has_folder else 'red'}][{'PASS' if has_folder else 'FAIL'}][/{'green' if has_folder else 'red'}] Results folder exists")
        
        has_sandbox = definition.sandbox_provider is not None
        console.print(f"  [{'green' if has_sandbox else 'yellow'}][{'PASS' if has_sandbox else 'WARN'}][/{'green' if has_sandbox else 'yellow'}] Sandbox configured: {definition.sandbox_provider if has_sandbox else 'None'}")
        
        has_budget = definition.budget is not None
        console.print(f"  [{'green' if has_budget else 'red'}][{'PASS' if has_budget else 'FAIL'}][/{'green' if has_budget else 'red'}] Budget looks correct")
        
        if not (has_cases and has_folder and has_budget):
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)

    otel_runtime = configure_otel_from_env()
    try:
        from glyph.utils.formatting import create_progress_callback, print_failed_tests_inline

        progress_ctx = nullcontext()
        trial_observer = None
        completed_trials = []
        if output_format == OutputFormat.RICH and not stream:
            progress, observer, completed_trials = create_progress_callback(len(cases) * definition.repetitions)
            progress_ctx = progress
            trial_observer = observer
        elif stream:
            trial_observer = lambda record: print_trial_event(record, output_format)

        with progress_ctx:
            summary = asyncio.run(
                EvaluationRunner(
                    target=definition.target,
                    graders=definition.graders,
                    budget=definition.budget,
                    artifact_path=output,
                    suite=definition.suite,
                    outcome_collectors=definition.outcome_collectors,
                    grader_policy=definition.grader_policy,
                    repetitions=definition.repetitions,
                    telemetry=(
                        otel_runtime.telemetry
                        if otel_runtime is not None
                        else definition.telemetry
                    ),
                    sandbox_provider=definition.sandbox_provider,
                    sandbox_requirements=definition.sandbox_requirements,
                    exporters=definition.exporters,
                    export_policy=definition.export_policy,
                    prompt_hashes=definition.prompt_hashes,
                    overwrite_artifact=overwrite,
                    trial_observer=trial_observer,
                    trial_started_observer=(
                        print_trial_start
                        if output_format == OutputFormat.RICH and stream
                        else None
                    ),
                ).run(cases, run_id=run_id)
            )
    finally:
        if otel_runtime is not None:
            otel_runtime.shutdown()
    if output_format == OutputFormat.RICH and not stream:
        print_failed_tests_inline(completed_trials)

    format_run_summary(summary, output_format)

    if workers and output_format == OutputFormat.RICH:
        trials_for_analysis = completed_trials if (not stream and completed_trials) else _load_trial_records(output)
        
        # Calculate real metrics
        security_trials = [t for t in trials_for_analysis if t.suite.value == "security"]
        security_score = sum(1 for t in security_trials if t.status.value == "passed") / len(security_trials) if security_trials else 1.0
        
        perf_score = sum(1 for t in trials_for_analysis if t.status.value not in ("timeout", "budget_exceeded")) / len(trials_for_analysis) if trials_for_analysis else 1.0
        
        tool_trials = [t for t in trials_for_analysis if t.result and t.result.usage and t.result.usage.tool_calls > 0]
        tool_score = sum(1 for t in tool_trials if t.status.value == "passed") / len(tool_trials) if tool_trials else 1.0
        
        retrieval_trials = [t for t in trials_for_analysis if t.result and t.result.retrievals]
        retrieval_score = sum(1 for t in retrieval_trials if t.status.value == "passed") / len(retrieval_trials) if retrieval_trials else 1.0
        
        graph_trials = [t for t in trials_for_analysis if t.result and t.result.loop and t.result.loop.iterations]
        graph_score = sum(1 for t in graph_trials if t.status.value == "passed") / len(graph_trials) if graph_trials else 1.0
        
        cap_trials = [t for t in trials_for_analysis if t.suite.value == "capability"]
        cap_score = sum(t.score for t in cap_trials) / len(cap_trials) if cap_trials else 1.0

        console.print()
        console.print("  [bold]Analysis[/bold]")
        analysis = Table(box=None, padding=(0, 2), show_header=False)
        analysis.add_column("Category", style="cyan")
        analysis.add_column("Score", justify="right")
        analysis.add_row("  Security", f"{security_score * 100:.1f}%")
        analysis.add_row("  Performance", f"{perf_score * 100:.1f}%")
        analysis.add_row("  Tool use", f"{tool_score * 100:.1f}%")
        analysis.add_row("  Retrieval quality", f"{retrieval_score * 100:.1f}%")
        analysis.add_row("  Graph structure", f"{graph_score * 100:.1f}%")
        analysis.add_row("  Output quality", f"{cap_score * 100:.1f}%")
        console.print(analysis)

    if output_format == OutputFormat.RICH:
        duration = (summary.finished_at - summary.started_at).total_seconds()
        print_status_bar(cases=summary.cases, duration=f"{duration:.1f}s")

    if summary.errors or summary.timeouts or summary.pass_rate < minimum_pass_rate:
        raise typer.Exit(code=1)


@app.command("compare")
def compare_command(
    candidate: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    baseline: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    max_regressions: Annotated[int, typer.Option(min=0)] = 0,
    minimum_delta: Annotated[float, typer.Option(min=-1.0, max=1.0)] = 0.0,
    output_format: Annotated[
        str, typer.Option("--format", help="rich, json, json-stream, rpc, or pr-comment")
    ] = OutputFormat.RICH,
) -> None:
    """Compare candidate and baseline artifacts by stable case ID."""
    result = compare_runs(candidate, baseline)
    _validate_output_format(output_format)
    if output_format == OutputFormat.RICH:
        print_command_start("compare", detail=f"candidate {candidate} | baseline {baseline}")
    format_comparison(result, output_format)
    if output_format == OutputFormat.RICH:
        print_status_bar(cases=result.common_cases)
    if len(result.regressed) > max_regressions or result.pass_rate_delta < minimum_delta:
        raise typer.Exit(code=1)


@app.command("release")
def release_command(
    deterministic: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    baseline: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    judge: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    policy: Annotated[str, typer.Option()] = "default",
    minimum_overall_pass_rate: Annotated[float, typer.Option(min=0.0, max=1.0)] = 1.0,
    minimum_capability_pass_rate: Annotated[float, typer.Option(min=0.0, max=1.0)] = 0.9,
    minimum_regression_pass_rate: Annotated[float, typer.Option(min=0.0, max=1.0)] = 1.0,
    minimum_security_pass_rate: Annotated[float, typer.Option(min=0.0, max=1.0)] = 1.0,
    maximum_error_rate: Annotated[float, typer.Option(min=0.0, max=1.0)] = 0.0,
    maximum_regressions: Annotated[int, typer.Option(min=0)] = 0,
    minimum_pass_rate_delta: Annotated[float, typer.Option(min=-1.0, max=1.0)] = 0.0,
    output_format: Annotated[
        str, typer.Option("--format", help="rich, json, json-stream, rpc, or pr-comment")
    ] = OutputFormat.RICH,
) -> None:
    """Evaluate whether a release should be allowed based on evaluation results."""
    from glyph.core.domain_models import ReleasePolicy
    
    # Load deterministic summary
    deterministic_summary = _load_summary(deterministic)
    
    # Load judge summary if provided
    judge_summary = None
    if judge is not None:
        judge_summary = _load_summary(judge)
    
    # Create release policy
    if policy == "strict":
        release_policy = ReleaseGate().create_strict_policy()
    elif policy == "development":
        release_policy = ReleaseGate().create_development_policy()
    elif policy == "staging":
        release_policy = ReleaseGate().create_staging_policy()
    elif policy == "default":
        release_policy = ReleasePolicy(
            require_deterministic=True,
            require_regression_check=baseline is not None,
            require_judge=judge is not None,
            minimum_overall_pass_rate=minimum_overall_pass_rate,
            minimum_capability_pass_rate=minimum_capability_pass_rate,
            minimum_regression_pass_rate=minimum_regression_pass_rate,
            minimum_security_pass_rate=minimum_security_pass_rate,
            maximum_error_rate=maximum_error_rate,
            maximum_regressions=maximum_regressions,
            minimum_pass_rate_delta=minimum_pass_rate_delta,
        )
    else:
        raise typer.BadParameter(f"Unknown policy: {policy}")
    
    # Evaluate release
    gate = ReleaseGate(policy=release_policy)
    decision = asyncio.run(gate.evaluate_release(
        deterministic_summary,
        comparison_baseline=baseline,
        judge_summary=judge_summary,
    ))
    
    _validate_output_format(output_format)
    if output_format == OutputFormat.RICH:
        print_command_start("release", detail=f"policy {policy} | evidence {deterministic}")
    format_release_decision(decision, output_format)
    if output_format == OutputFormat.RICH:
        print_status_bar()
    
    # Exit with error code if release not allowed
    if not decision.allowed:
        raise typer.Exit(code=1)


def _load_summary(path: Path) -> RunSummary:
    """Load a RunSummary from a JSONL artifact file."""
    import json
    
    # Read the last line which should contain the summary
    lines = path.read_text("utf-8").splitlines()
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            # Try to parse as RunSummary
            if "run_id" in data and "total" in data:
                return RunSummary.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            continue
    
    raise ValueError(f"Could not find RunSummary in artifact: {path}")

_GUIDE_SECTIONS = {
    "init": "Getting Started",
    "doctor": "Getting Started",
    "datasets": "Dataset Management",
    "generation": "Dataset Generation",
    "run": "Evaluation Execution",
    "artifacts": "Analysis",
    "compare": "Analysis",
    "release": "Release Gates",
    "serve": "Services",
    "worker": "Services",
    "history": "Services",
    "config": "Services",
}


@app.command("guide")
def guide_command() -> None:
    """Show the recommended workflow from a new project to a release decision."""
    from rich import box as _box

    console.print()
    console.print("[glyph.brand]glyph[/glyph.brand] [bold white]workflow[/bold white]")
    console.print()

    steps = Table(
        show_header=True,
        header_style="bold",
        box=_box.SIMPLE_HEAD,
        padding=(0, 2),
    )
    steps.add_column("Stage", style="cyan", no_wrap=True)
    steps.add_column("Command", style="bold white")
    steps.add_column("Result", style="dim")
    steps.add_row("1. Start", "glyph init my-evaluation", "A local project layout")
    steps.add_row("2. Check", "glyph doctor", "Environment readiness")
    steps.add_row("3. Validate", "glyph datasets validate --dataset ...", "Schema, IDs, suite mix")
    steps.add_row("4. Generate", "glyph generation create ...", "Synthetic draft for review")
    steps.add_row("5. Approve", "glyph generation review / promote", "Immutable released dataset")
    steps.add_row("6. Evaluate", "glyph run ...", "Trial evidence in JSONL")
    steps.add_row("7. Inspect", "glyph artifacts summary / trial", "Run or case-level evidence")
    steps.add_row("8. Compare", "glyph compare ...", "Baseline deltas & regressions")
    steps.add_row("9. Release", "glyph release ...", "CI-friendly release decision")
    console.print(steps)
    console.print()
    console.print("  [glyph.muted]Start with[/glyph.muted] [bold]glyph init[/bold] [glyph.muted]or see[/glyph.muted] [bold]glyph <command> --help[/bold]")
    print_status_bar()


@app.command("doctor")
def doctor_command(
    factory: Annotated[str | None, typer.Option(help="Evaluation setup to validate")] = None,
) -> None:
    """Check local CLI, artifact, and optional service configuration."""
    import os
    import sys

    from rich import box as _box

    console.print()
    console.print("[glyph.brand]glyph[/glyph.brand] [bold white]doctor[/bold white]")
    console.print()

    checks = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
    )
    checks.add_column("Status", no_wrap=True)
    checks.add_column("Check")

    def add_check(passed: bool, message: str, fix: str = "") -> None:
        icon = "[green]✓[/green]" if passed else "[red]✗[/red]"
        checks.add_row(f"  {icon}", message)
        if not passed and fix:
            checks.add_row("", f"[dim]→ fix: {fix}[/dim]")

    add_check(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}", "Requires Python 3.11+")
    add_check(Path.cwd().exists(), "Workspace exists", "Directory was deleted")
    has_artifacts = Path("artifacts").exists()
    add_check(has_artifacts, "Results folder (artifacts/)", "Run `glyph init` or create `artifacts/` folder")
    
    db_url = os.getenv("DATABASE_URL")
    add_check(bool(db_url), "Database connection", "Set DATABASE_URL in .env to use `glyph serve` and `glyph history`")
    
    redis_url = os.getenv("CELERY_BROKER_URL")
    add_check(bool(redis_url), "Redis connection", "Set CELERY_BROKER_URL in .env to use `glyph worker`")
    
    langsmith = os.getenv("LANGSMITH_API_KEY")
    add_check(bool(langsmith), "LangSmith tracing", "Set LANGSMITH_API_KEY for observability")
    
    if factory:
        console.print(checks)
        console.print()
        checks = Table(show_header=False, box=None, padding=(0, 2))
        checks.add_column("Status", no_wrap=True)
        checks.add_column("Check")
        
        try:
            definition = _load_factory(factory)()
            from glyph.core.evaluation import EvaluationDefinition
            if not isinstance(definition, EvaluationDefinition):
                add_check(False, f"Loaded evaluation setup: {factory}", "Factory must return EvaluationDefinition")
            else:
                add_check(True, f"Loaded evaluation setup: {factory}")
                
                has_target = definition.target is not None
                add_check(has_target, "Target configured", "Set a target in the EvaluationDefinition")
                
                has_graders = len(definition.graders) > 0
                add_check(has_graders, "Graders configured", "Add graders to the EvaluationDefinition")
                
        except Exception as e:
            add_check(False, f"Failed to load evaluation setup: {factory}", f"Error: {e}")

    console.print(checks)
    print_status_bar()


def _load_trial_records(path: Path) -> list[TrialRecord]:
    trials: list[TrialRecord] = []
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if "trial_id" in payload:
            trials.append(TrialRecord.model_validate(payload))
    return trials


artifacts_app = typer.Typer(help="Inspect immutable run artifacts")
app.add_typer(artifacts_app, name="artifacts")


@artifacts_app.command("summary")
def artifact_summary(
    artifact: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output_format: Annotated[
        str, typer.Option("--format", help="rich, json, or pr-comment")
    ] = OutputFormat.RICH,
) -> None:
    """Show the final summary stored in an evaluation artifact."""
    _validate_output_format(output_format)
    summary = _load_summary(artifact)
    if output_format == OutputFormat.RICH:
        print_command_start("artifacts summary", detail=str(artifact), run_id=summary.run_id)
    format_run_summary(summary, output_format)


@artifacts_app.command("trial")
def artifact_trial(
    artifact: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    case_id: Annotated[str, typer.Option(help="Stable case ID to inspect")],
    repetition: Annotated[int | None, typer.Option(min=0)] = None,
    output_format: Annotated[
        str, typer.Option("--format", help="rich, json, or pr-comment")
    ] = OutputFormat.RICH,
) -> None:
    """Show one case's evidence, grades, and sandbox cleanup result."""
    _validate_output_format(output_format)
    matching = [record for record in _load_trial_records(artifact) if record.case_id == case_id]
    if repetition is not None:
        matching = [record for record in matching if record.repetition_index == repetition]
    if not matching:
        qualifier = f" at repetition {repetition}" if repetition is not None else ""
        raise typer.BadParameter(f"No trial for case {case_id!r}{qualifier} in {artifact}")
    if len(matching) > 1:
        raise typer.BadParameter("Multiple trials found; provide --repetition")
    if output_format == OutputFormat.RICH:
        print_command_start("artifacts trial", detail=f"{artifact} | case {case_id}")
    format_trial_detail(matching[0], output_format)


# New UX commands

@app.command("serve")
def serve_command(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8000,
    reload: Annotated[bool, typer.Option()] = False,
) -> None:
    """Start the API server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Web dependencies not installed[/red]")
        console.print("Install with: uv sync --extra web")
        raise typer.Exit(code=1)
    
    console.print(f"[cyan]Starting API server on {host}:{port}[/cyan]")
    console.print("[yellow]Make sure DATABASE_URL is set for Neon PostgreSQL[/yellow]")
    
    uvicorn.run(
        "glyph.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command("worker")
def worker_command(
    concurrency: Annotated[int, typer.Option()] = 2,
    loglevel: Annotated[str, typer.Option()] = "info",
) -> None:
    """Start a Celery worker for background evaluation runs."""
    try:
        from glyph.evaluation.tasks import celery_app
    except ImportError:
        console.print("[red]Web dependencies not installed[/red]")
        console.print("Install with: uv sync --extra web")
        raise typer.Exit(code=1)
    
    console.print(f"[cyan]Starting Celery worker with concurrency={concurrency}[/cyan]")
    console.print("[yellow]Make sure Redis is running for task broker[/yellow]")
    
    celery_app.worker_main([
        "worker",
        f"--concurrency={concurrency}",
        f"--loglevel={loglevel}",
    ])


@app.command("init")
def init_command(
    name: Annotated[str, typer.Argument(help="Project name")] = "my-evaluation",
) -> None:
    """Initialize a new evaluation project with scaffolding."""
    project_dir = Path(name)
    if project_dir.exists():
        console.print(f"[red]Directory already exists: {project_dir}[/red]")
        raise typer.Exit(code=1)
    
    project_dir.mkdir()
    (project_dir / "datasets").mkdir()
    (project_dir / "examples").mkdir()
    (project_dir / "prompts").mkdir()
    (project_dir / "artifacts").mkdir()
    
    sample_dataset = [
        {
            "id": "case-1",
            "input": {"question": "What is 2+2?"},
            "expected": {"contains": ["2+2"]},
            "suite": "capability",
        },
        {
            "id": "case-2",
            "input": {"question": "What is the capital of France?"},
            "expected": {"contains": ["France"]},
            "suite": "capability",
        },
    ]
    
    with open(project_dir / "datasets" / "example.jsonl", "w") as f:
        for case in sample_dataset:
            f.write(json.dumps(case) + "\n")

    example_factory = '''from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from glyph.core.domain_models import Budget, SandboxRequirements
from glyph.evaluation.definition import EvaluationDefinition
from glyph.grading.graders import ContainsAllGrader
from glyph.targets.langgraph_target import LangGraphTarget


class State(TypedDict, total=False):
    question: str
    answer: str


def answer(state: State) -> State:
    return {"answer": state["question"]}


def create_evaluation() -> EvaluationDefinition:
    graph = StateGraph(State)
    graph.add_node("answer", answer)
    graph.add_edge(START, "answer")
    graph.add_edge("answer", END)
    return EvaluationDefinition(
        target=LangGraphTarget(
            graph.compile(),
            version="starter@1.0.0",
            output_builder=lambda state: {"answer": state["answer"]},
        ),
        graders=(ContainsAllGrader(),),
        budget=Budget(timeout_seconds=10, max_concurrency=2),
        sandbox_requirements=SandboxRequirements(required=False),
    )
'''
    (project_dir / "examples" / "evaluation.py").write_text(example_factory, encoding="utf-8")
    
    gitignore = """# Artifacts
artifacts/
*.jsonl

# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/

# Environment
.env
"""
    (project_dir / ".gitignore").write_text(gitignore)
    
    console.print(f"[green]Project initialized: {project_dir}[/green]")
    console.print("\nNext steps:")
    console.print(f"  cd {name}")
    console.print("  glyph doctor")
    console.print("  glyph datasets validate --dataset datasets/example.jsonl")
    console.print("  glyph run --factory examples.evaluation:create_evaluation --dataset datasets/example.jsonl")


generation_app = typer.Typer(help="Generate, review, and promote synthetic evaluation datasets")
app.add_typer(generation_app, name="generation")


def _review_path(draft: Path) -> Path:
    return draft.with_suffix(draft.suffix + ".reviews.jsonl")


@generation_app.command("create")
def generation_create(
    seed: Annotated[str, typer.Option(help="Product or workflow seed phrase")],
    generator: Annotated[str, typer.Option(help="Case generator factory as module:function")],
    output: Annotated[Path, typer.Option(help="New draft JSONL path")],
    count: Annotated[int, typer.Option(min=1, max=10_000)] = 100,
    capability: Annotated[int | None, typer.Option(min=0)] = None,
    regression: Annotated[int, typer.Option(min=0)] = 0,
    security: Annotated[int, typer.Option(min=0)] = 0,
    random_seed: Annotated[int, typer.Option(min=0)] = 0,
    tag: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Create a validated, immutable synthetic-case draft for human review."""
    capability_count = count - regression - security if capability is None else capability
    suite_counts = {
        "capability": capability_count,
        "regression": regression,
        "security": security,
    }
    try:
        spec = GenerationSpec(
            seed_phrase=seed,
            count=count,
            random_seed=random_seed,
            suite_counts=suite_counts,
            tags=frozenset(tag or ()),
        )
        manifest = asyncio.run(generate_draft(_load_generator(generator), spec, output))
    except (FileExistsError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    console.print(
        f"[green]Created draft {output}[/green] ({manifest.generation_id}, "
        f"{manifest.spec.count} cases). Review every case before promotion."
    )


@generation_app.command("list")
def generation_list(
    draft: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
) -> None:
    """List generated cases and their immutable generation provenance."""
    manifest, cases = load_draft(draft)
    console.print(
        f"[cyan]{manifest.generation_id}[/cyan] | {len(cases)} cases | "
        f"{manifest.generator_name}@{manifest.generator_version}"
    )
    table = Table(title="Generated evaluation cases")
    table.add_column("Case ID")
    table.add_column("Suite")
    table.add_column("Tags")
    for record in cases:
        table.add_row(record.case.id, record.case.suite.value, ", ".join(sorted(record.case.tags)))
    console.print(table)


@generation_app.command("review")
def generation_review(
    draft: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    case_id: Annotated[str, typer.Option()],
    reviewer: Annotated[str, typer.Option()],
    decision: Annotated[str, typer.Option(help="approved or rejected")],
    rationale: Annotated[str, typer.Option()] = "",
    reviews: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Append an approval or rejection; previous review records remain intact."""
    manifest, _ = load_draft(draft)
    try:
        append_review(
            draft,
            reviews or _review_path(draft),
            CaseReview(
                generation_id=manifest.generation_id,
                case_id=case_id,
                reviewer=reviewer,
                decision=decision,
                rationale=rationale,
            ),
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    console.print(f"[green]Recorded {decision} review for {case_id}[/green]")


@generation_app.command("promote")
def generation_promote(
    draft: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option(help="New released evaluation JSONL dataset")],
    reviews: Annotated[Path | None, typer.Option()] = None,
    skip_governance: Annotated[bool, typer.Option("--skip-governance", help="Skip governance checks (for testing only)")] = False,
) -> None:
    """Promote a fully approved draft into an immutable evaluation dataset."""
    try:
        if skip_governance:
            console.print("[yellow]Warning: Skipping governance checks (testing mode)[/yellow]")
            # For testing, use old simple promotion logic
            from glyph.generation import promote_draft_simple
            manifest = promote_draft_simple(draft, reviews or _review_path(draft), output)
        else:
            manifest = promote_draft(draft, reviews or _review_path(draft), output)
    except ValueError as error:
        # Format multi-line errors nicely for CLI
        error_msg = str(error)
        if "\n" in error_msg:
            # Print each line with proper formatting
            console.print(f"[red]{error_msg}[/red]")
            raise typer.Exit(code=1)
        console.print(f"[red]{error_msg}[/red]")
        raise typer.Exit(code=1)
    except FileExistsError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1)
    except Exception as error:
        console.print(f"[red]Error: {error}[/red]")
        raise typer.Exit(code=1)
    console.print(
        f"[green]Promoted {manifest.generation_id} to {output}[/green] "
        f"with dataset hash {manifest.cases_hash}"
    )


datasets_app = typer.Typer(help="Manage datasets")
app.add_typer(datasets_app, name="datasets")

@datasets_app.command("list")
def list_datasets(directory: Path = Path("datasets")) -> None:
    """List available datasets."""
    from glyph.services.dataset_service import DatasetService
    response = DatasetService.list_datasets(str(directory))
    table = Table(title="Available Datasets")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="magenta")
    for d in response.datasets:
        table.add_row(d.name, d.path)
    console.print(table)


@datasets_app.command("validate")
def validate_dataset(
    dataset: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate a dataset and show its suite and tag composition before a run."""
    from collections import Counter

    from rich import box as _box

    cases = load_jsonl(dataset)
    suites = Counter(case.suite.value for case in cases)
    tags = Counter(tag for case in cases for tag in case.tags)

    console.print()
    console.print(f"  [green][PASS][/green] {dataset} [dim]|[/dim] {len(cases)} unique cases")
    console.print()

    composition = Table(
        show_header=True,
        header_style="bold",
        box=_box.SIMPLE_HEAD,
        padding=(0, 2),
    )
    composition.add_column("Suite", style="dim")
    composition.add_column("Cases", justify="right", style="bold")
    for suite, count in sorted(suites.items()):
        composition.add_row(suite, str(count))
    console.print(composition)
    if tags:
        console.print()
        tag_table = Table(
            show_header=True,
            header_style="bold",
            box=_box.SIMPLE_HEAD,
            padding=(0, 2),
        )
        tag_table.add_column("Tag", style="dim")
        tag_table.add_column("Cases", justify="right", style="bold")
        for tag, count in tags.most_common(10):
            tag_table.add_row(tag, str(count))
        console.print(tag_table)
        
    # Validation rules
    console.print()
    tagged_cases = sum(1 for case in cases if case.tags)
    if len(cases) > 0 and tagged_cases / len(cases) < 0.5:
        pct = (tagged_cases / len(cases)) * 100
        console.print(f"  [yellow]![/yellow] Only {tagged_cases} / {len(cases)} tests have tags ({pct:.0f}%). Tags help you filter results by topic later.")
        console.print('  [dim]→ add tags like {"tags": ["edge-case", "p0"]}[/dim]')
        
    security_count = suites.get("security", 0)
    if security_count < 5:
        console.print(f"  [yellow]![/yellow] Only {security_count} security tests found. Missing coverage for injections.")
        console.print('  [dim]→ copy examples from https://github.com/glyph-ai/glyph-security[/dim]')

    print_status_bar(cases=len(cases))


@app.command("history")
def history_command(limit: int = 50) -> None:
    """View recent evaluation runs."""
    try:
        from glyph.db.session import init_db
        from glyph.services.run_service import RunService
    except ImportError:
        console.print("[red]Database dependencies not installed[/red]")
        console.print("Install with: uv sync --extra web")
        raise typer.Exit(code=1)
    
    async def _fetch():
        await init_db()
        return await RunService.list_runs(limit=limit)
    
    runs = asyncio.run(_fetch())
    table = Table(title="Recent Runs")
    table.add_column("ID", style="cyan")
    table.add_column("Started At", style="green")
    table.add_column("Pass Rate", justify="right")
    
    for run in runs:
        pass_rate = f"{run.pass_rate * 100:.1f}%" if run.pass_rate is not None else "N/A"
        started = run.started_at.strftime("%Y-%m-%d %H:%M:%S") if run.started_at else "Unknown"
        table.add_row(run.id, started, pass_rate)
    
    console.print(table)


@app.command("config")
def config_command() -> None:
    """Display current configuration."""
    import os
    table = Table(title="Glyph Configuration")
    table.add_column("Environment Variable", style="cyan")
    table.add_column("Value", style="yellow")
    
    table.add_row("DATABASE_URL", os.getenv("DATABASE_URL", "postgresql://ai_eval:localdev@localhost:5432/ai_eval (default)"))
    table.add_row("OTEL_EXPORTER_OTLP_ENDPOINT", os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "Not set"))
    
    console.print(table)


@app.command("open")
def open_command(
    port: Annotated[int, typer.Option(help="Port of the local server")] = 8000,
) -> None:
    """Open the local web dashboard."""
    import webbrowser
    url = f"http://localhost:{port}"
    console.print(f"Opening dashboard at {url}")
    console.print("[dim]If the server is not running, run `glyph serve` in another terminal.[/dim]")
    webbrowser.open(url)


@app.command("status")
def status_command(
    run_id: Annotated[str, typer.Argument(help="Run ID to check")],
    watch: Annotated[bool, typer.Option("--watch", help="Auto-refresh status")] = False,
) -> None:
    """Check the live status of an evaluation run."""
    try:
        from glyph.db.session import init_db
        from glyph.services.run_service import RunService
    except ImportError:
        console.print("[red]Database dependencies not installed[/red]")
        console.print("Install with: uv sync --extra web")
        raise typer.Exit(code=1)

    async def _fetch():
        await init_db()
        return await RunService.get_run(run_id)

    import time
    while True:
        run = asyncio.run(_fetch())
        if not run:
            console.print(f"[red]Run {run_id} not found[/red]")
            raise typer.Exit(code=1)

        if watch:
            console.clear()
        
        console.print(f"[bold]Status for {run_id}[/bold]")
        console.print(f"State: {run.status}")
        if run.total_trials:
            console.print(f"Passed: {run.passed} / {run.total_trials}")
            
        if not watch:
            break
        time.sleep(2)


security_app = typer.Typer(help="Security checks and audits")
app.add_typer(security_app, name="security")

@security_app.command("audit")
def security_audit_command(
    artifact: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    """Check evaluation results for security issues like leaked credentials."""
    trials = _load_trial_records(artifact)
    leaked = []
    for t in trials:
        if t.result and t.result.output:
            out = t.result.output.lower()
            if "password" in out or "secret" in out or "key" in out:
                leaked.append(t.case_id)
                
    if leaked:
        console.print("[red]✗ Found leaked credentials or secrets![/red]")
        for l in leaked:
            console.print(f"  [dim]- {l}[/dim]")
        raise typer.Exit(code=1)
    
    console.print("[green]✓ No credentials leaked.[/green]")
