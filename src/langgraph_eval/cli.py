from __future__ import annotations

import asyncio
import importlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, cast

import typer

from langgraph_eval.comparison import compare as compare_runs
from langgraph_eval.datasets import load_jsonl
from langgraph_eval.definition import EvaluationDefinition
from langgraph_eval.models import RunSummary
from langgraph_eval.observability import configure_otel_from_env
from langgraph_eval.release_gate import ReleaseGate
from langgraph_eval.runner import EvaluationRunner

app = typer.Typer(no_args_is_help=True, help="LangGraph-native evaluation harness")


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


@app.command()
def run(
    factory: Annotated[str, typer.Option(help="Evaluation factory as module:function")],
    dataset: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option(dir_okay=False)] = Path("artifacts/results.jsonl"),
    minimum_pass_rate: Annotated[float, typer.Option(min=0.0, max=1.0)] = 1.0,
    run_id: Annotated[str | None, typer.Option()] = None,
    overwrite: Annotated[bool, typer.Option(help="Replace an existing artifact file")] = False,
) -> None:
    """Run a dataset and return a CI-friendly exit code."""
    definition = _load_factory(factory)()
    if not isinstance(definition, EvaluationDefinition):
        raise typer.BadParameter("Factory must return EvaluationDefinition")
    cases = load_jsonl(dataset)
    otel_runtime = configure_otel_from_env()
    try:
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
            ).run(cases, run_id=run_id)
        )
    finally:
        if otel_runtime is not None:
            otel_runtime.shutdown()
    typer.echo(summary.model_dump_json(indent=2))
    if summary.errors or summary.timeouts or summary.pass_rate < minimum_pass_rate:
        raise typer.Exit(code=1)


@app.command("compare")
def compare_command(
    candidate: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    baseline: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    max_regressions: Annotated[int, typer.Option(min=0)] = 0,
    minimum_delta: Annotated[float, typer.Option(min=-1.0, max=1.0)] = 0.0,
) -> None:
    """Compare candidate and baseline artifacts by stable case ID."""
    result = compare_runs(candidate, baseline)
    typer.echo(json.dumps({
        "common_cases": result.common_cases,
        "improved": result.improved,
        "regressed": result.regressed,
        "unchanged": result.unchanged,
        "candidate_pass_rate": result.candidate_pass_rate,
        "baseline_pass_rate": result.baseline_pass_rate,
        "pass_rate_delta": result.pass_rate_delta,
    }, indent=2))
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
) -> None:
    """Evaluate whether a release should be allowed based on evaluation results."""
    from langgraph_eval.models import ReleasePolicy
    
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
    
    # Output decision
    typer.echo(decision.model_dump_json(indent=2))
    
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
