from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
)
from rich.table import Table
from rich.theme import Theme

if TYPE_CHECKING:
    from glyph.core.domain_models import EvalCase, ReleaseDecision, RunSummary, TrialRecord
    from glyph.grading.comparison import Comparison


# â”€â”€â”€ Theme â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Soft, terminal-native palette â€” avoids neon; feels at home on dark backgrounds.

_THEME = Theme(
    {
        "glyph.brand": "bold cyan",
        "glyph.muted": "dim",
        "glyph.success": "green",
        "glyph.warning": "yellow",
        "glyph.danger": "red",
        "glyph.value": "bold white",
        "glyph.header": "bold white",
        "glyph.dim_sep": "dim white",
    }
)

console = Console(theme=_THEME, highlight=False)


def _flush_console() -> None:
    """Flush after event lines so real terminals do not wait for process exit."""
    try:
        console.file.flush()
    except (AttributeError, OSError):
        return


# â”€â”€â”€ Constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_RULE_CHAR = "-"
_CHECK = "[PASS]"
_CROSS = "[FAIL]"
_BULLET = ">"
_WIDTH = 72


class OutputFormat:
    """Output format options for CLI commands."""
    RICH = "rich"
    JSON = "json"
    JSON_STREAM = "json-stream"  # Pi Agent-style event stream
    RPC = "rpc"  # Pi Agent-style live pipe
    PR_COMMENT = "pr-comment"


# â”€â”€â”€ Utilities â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _rule(title: str = "", style: str = "dim") -> None:
    """Print a thin horizontal rule with an optional centred title."""
    if title:
        pad = (_WIDTH - len(title) - 2) // 2
        line = f"{_RULE_CHAR * pad} {title} {_RULE_CHAR * pad}"
        # fix odd widths
        if len(line) < _WIDTH:
            line += _RULE_CHAR
        console.print(f"[{style}]{line}[/{style}]")
    else:
        console.print(f"[{style}]{_RULE_CHAR * _WIDTH}[/{style}]")


def _kv(key: str, value: str, *, indent: int = 2, key_width: int = 22) -> None:
    """Print a key-value pair with aligned columns."""
    pad = " " * indent
    k = key.ljust(key_width)
    console.print(f"{pad}[glyph.muted]{k}[/glyph.muted] [glyph.value]{value}[/glyph.value]")


def _status_icon(passed: bool) -> str:
    return f"[glyph.success]{_CHECK}[/glyph.success]" if passed else f"[glyph.danger]{_CROSS}[/glyph.danger]"


# â”€â”€â”€ Status bar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def print_status_bar(*, cases: int | None = None, duration: str | None = None) -> None:
    """Print a dim footer line with context â€” like agent CLIs."""
    parts: list[str] = ["glyph 0.1.0"]
    if cases is not None:
        parts.append(f"{cases} cases")
    if duration is not None:
        parts.append(duration)

    cwd = os.path.basename(os.getcwd())
    line1 = " | ".join(parts)
    console.print()
    console.print(f"  [glyph.muted]{line1}[/glyph.muted]")
    console.print(f"  [glyph.muted]~/{cwd}[/glyph.muted]")
    _flush_console()


# â”€â”€â”€ Command header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def print_command_start(command: str, *, detail: str, run_id: str | None = None) -> None:
    """Render a compact, terminal-native command header for interactive use."""
    console.print()
    console.print(f"[glyph.brand]glyph[/glyph.brand] [glyph.header]{command}[/glyph.header]")
    console.print(f"  [glyph.muted]{detail}[/glyph.muted]")
    if run_id:
        console.print(f"  [glyph.muted]run[/glyph.muted] [glyph.value]{run_id}[/glyph.value]")
    _flush_console()


# â”€â”€â”€ Live trial stream â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def print_trial_start(case: EvalCase, repetition_index: int) -> None:
    """Print the point at which a queued trial starts consuming execution capacity."""
    suffix = f" (repetition {repetition_index + 1})" if repetition_index else ""
    console.print(f"[glyph.brand]glyph[/glyph.brand] test {case.id}{suffix}")
    console.print(f"  [glyph.muted]running {case.suite.value} check...[/glyph.muted]")
    _flush_console()


def print_trial_event(record: TrialRecord, output_format: str = OutputFormat.RICH) -> None:
    """Print one completed trial in a compact, agent-style event stream."""
    if output_format == OutputFormat.JSON_STREAM:
        _print_trial_event_json_stream(record)
        return
    
    if output_format == OutputFormat.RPC:
        _print_trial_event_rpc(record)
        return

    status = record.status.value.upper()
    status_style = {
        "PASSED": "glyph.success",
        "FAILED": "glyph.danger",
        "ERROR": "glyph.danger",
        "TIMEOUT": "glyph.warning",
        "BUDGET_EXCEEDED": "glyph.warning",
    }.get(status, "glyph.muted")
    tools = record.result.usage.tool_calls if record.result is not None else 0
    tokens = (
        record.result.usage.input_tokens + record.result.usage.output_tokens
        if record.result is not None
        else 0
    )
    console.print(
        f"  [{status_style}][{status}][/{status_style}] "
        f"{record.case_id} [glyph.dim_sep]|[/glyph.dim_sep] "
        f"score {record.score:.2f} [glyph.dim_sep]|[/glyph.dim_sep] "
        f"{record.duration_ms}ms [glyph.dim_sep]|[/glyph.dim_sep] "
        f"{tools} tools [glyph.dim_sep]|[/glyph.dim_sep] "
        f"{tokens} tokens"
    )
    _flush_console()


def _print_trial_event_json_stream(record: TrialRecord) -> None:
    """Print trial event as a single JSON line for streaming (Pi Agent style)."""
    import json
    event = {
        "event": "trial_complete",
        "timestamp": record.finished_at.isoformat(),
        "case_id": record.case_id,
        "trial_id": record.trial_id,
        "status": record.status.value,
        "score": record.score,
        "duration_ms": record.duration_ms,
        "suite": record.suite.value,
        "repetition": record.repetition_index,
        "usage": {
            "tool_calls": record.result.usage.tool_calls if record.result else 0,
            "input_tokens": record.result.usage.input_tokens if record.result else 0,
            "output_tokens": record.result.usage.output_tokens if record.result else 0,
            "cost_usd": record.result.usage.cost_usd if record.result else None,
        } if record.result else None,
        "grades": [
            {
                "grader": grade.grader,
                "passed": grade.passed,
                "score": grade.score,
                "reason": grade.reason,
            }
            for grade in record.grades
        ],
    }
    console.print(json.dumps(event))
    _flush_console()


def _print_trial_event_rpc(record: TrialRecord) -> None:
    """Print trial event in RPC format for live pipe integration (Pi Agent style)."""
    import json
    rpc_event = {
        "jsonrpc": "2.0",
        "method": "trial.complete",
        "params": {
            "case_id": record.case_id,
            "trial_id": record.trial_id,
            "status": record.status.value,
            "score": record.score,
            "duration_ms": record.duration_ms,
            "result": record.result.model_dump(mode="json") if record.result else None,
        },
    }
    console.print(json.dumps(rpc_event))
    _flush_console()


# â”€â”€â”€ Run summary formatters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def format_cli_output(summary: RunSummary, output_format: str = OutputFormat.RICH) -> None:
    """Format and display CLI output."""
    format_run_summary(summary, output_format)


def format_markdown_table(data: list[dict[str, str]]) -> str:
    """Format data as a Markdown table."""
    if not data:
        return ""

    headers = list(data[0].keys())
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "|" + "|".join(["---"] * len(headers)) + "|"

    rows = []
    for item in data:
        row = "| " + " | ".join(str(item.get(h, "")) for h in headers) + " |"
        rows.append(row)

    return "\n".join([header_row, separator_row] + rows)


def format_summary(summary: RunSummary) -> str:
    """Format a summary as text."""
    return f"""
Run Summary
-----------
Run ID: {summary.run_id}
Total Tests: {summary.total}
Tests: {summary.cases}
Repetitions: {summary.repetitions}
Passed: {summary.passed}
Failed: {summary.failed}
Errors: {summary.errors}
Timeouts: {summary.timeouts}
Pass Rate: {summary.pass_rate:.1%}
Average Score: {summary.average_score:.2f}
"""


def format_run_summary(summary: RunSummary, output_format: str = OutputFormat.RICH) -> None:
    """Format and display a run summary."""
    if output_format == OutputFormat.JSON:
        console.print(summary.model_dump_json(indent=2))
        return

    if output_format == OutputFormat.JSON_STREAM:
        _format_run_summary_json_stream(summary)
        return

    if output_format == OutputFormat.RPC:
        _format_run_summary_rpc(summary)
        return

    if output_format == OutputFormat.PR_COMMENT:
        _format_run_summary_pr_comment(summary)
        return

    _format_run_summary_rich(summary)


def _format_run_summary_rich(summary: RunSummary) -> None:
    """Format a compact completion report â€” clean, indented, no heavy borders."""
    blocked = bool(summary.errors or summary.timeouts)
    status = "BLOCKED" if blocked else "EVALUATION COMPLETE"
    style = "glyph.danger" if blocked else "glyph.muted"

    console.print()
    _rule(status, style=style)
    console.print()

    _kv("run", summary.run_id)
    _kv("tests", str(summary.total))
    _kv("tests x reps", f"{summary.cases} x {summary.repetitions}")

    pass_style = "glyph.success" if summary.passed else "glyph.muted"
    fail_style = "glyph.danger" if summary.failed else "glyph.muted"
    console.print(
        f"  {'passed'.ljust(22)}[{pass_style}]{summary.passed}[/{pass_style}]"
        f"  [glyph.dim_sep]|[/glyph.dim_sep]  "
        f"[{fail_style}]{summary.failed} failed[/{fail_style}]"
    )
    if summary.errors:
        _kv("errors", f"[glyph.danger]{summary.errors}[/glyph.danger]")
    if summary.timeouts:
        _kv("timeouts", f"[glyph.warning]{summary.timeouts}[/glyph.warning]")

    rate_style = "glyph.success" if summary.pass_rate >= 0.9 else "glyph.danger"
    _kv("pass rate", f"[{rate_style}]{summary.pass_rate:.1%}[/{rate_style}]")
    _kv("avg score", f"{summary.average_score:.2f}")
    duration_seconds = (summary.finished_at - summary.started_at).total_seconds()
    _kv("duration", f"{duration_seconds:.1f}s")
    _kv("results file", summary.artifact_path)

    console.print()
    _rule()

    # Suite breakdown â€” lightweight table
    if summary.suites:
        console.print()
        suite_table = Table(
            title="Category Breakdown",
            show_header=True,
            header_style="bold",
            box=box.SIMPLE_HEAD,
            padding=(0, 2),
            title_style="glyph.muted",
        )
        suite_table.add_column("Category", style="dim")
        suite_table.add_column("Total", justify="right")
        suite_table.add_column("Passed", justify="right")
        suite_table.add_column("Failed", justify="right")
        suite_table.add_column("Pass Rate", justify="right")

        for suite_type, suite in summary.suites.items():
            pass_rate = suite.pass_rate
            rate_str = f"{pass_rate:.1%}"
            style = "green" if pass_rate >= 0.9 else "red"
            suite_table.add_row(
                suite_type.value,
                str(suite.trials),
                str(suite.passed),
                str(suite.failed),
                f"[{style}]{rate_str}[/{style}]",
            )

        console.print(suite_table)


def _format_run_summary_json_stream(summary: RunSummary) -> None:
    """Format run summary as JSON event stream (Pi Agent style)."""
    import json
    event = {
        "event": "run_complete",
        "timestamp": summary.finished_at.isoformat(),
        "run_id": summary.run_id,
        "evaluation_suite_id": summary.evaluation_suite_id,
        "evaluation_suite_version": summary.evaluation_suite_version,
        "total": summary.total,
        "cases": summary.cases,
        "repetitions": summary.repetitions,
        "passed": summary.passed,
        "failed": summary.failed,
        "errors": summary.errors,
        "timeouts": summary.timeouts,
        "pass_rate": summary.pass_rate,
        "average_score": summary.average_score,
        "pass_at_k": summary.pass_at_k,
        "pass_power_k": summary.pass_power_k,
        "duration_seconds": (summary.finished_at - summary.started_at).total_seconds(),
        "artifact_path": summary.artifact_path,
        "suites": {
            suite_type.value: {
                "trials": suite.trials,
                "passed": suite.passed,
                "failed": suite.failed,
                "errors": suite.errors,
                "pass_rate": suite.pass_rate,
                "average_score": suite.average_score,
            }
            for suite_type, suite in summary.suites.items()
        },
    }
    console.print(json.dumps(event))
    _flush_console()


def _format_run_summary_rpc(summary: RunSummary) -> None:
    """Format run summary as RPC event (Pi Agent style)."""
    import json
    rpc_event = {
        "jsonrpc": "2.0",
        "method": "run.complete",
        "params": {
            "run_id": summary.run_id,
            "status": "complete",
            "summary": summary.model_dump(mode="json"),
        },
    }
    console.print(json.dumps(rpc_event))
    _flush_console()


def _format_run_summary_pr_comment(summary: RunSummary) -> None:
    """Format run summary as GitHub PR comment (Markdown)."""
    output = []
    output.append("## Evaluation Results")
    output.append("")
    output.append("| Metric | Value |")
    output.append("|--------|-------|")
    output.append(f"| Run ID | {summary.run_id} |")
    output.append(f"| Total Trials | {summary.total} |")
    output.append(f"| Cases | {summary.cases} |")
    output.append(f"| Repetitions | {summary.repetitions} |")
    output.append(f"| Passed | {summary.passed} |")
    output.append(f"| Failed | {summary.failed} |")
    output.append(f"| Errors | {summary.errors} |")
    output.append(f"| Timeouts | {summary.timeouts} |")
    output.append(f"| Pass Rate | {summary.pass_rate:.1%} |")
    output.append(f"| Average Score | {summary.average_score:.2f} |")

    duration_seconds = (summary.finished_at - summary.started_at).total_seconds()
    output.append(f"| Duration | {duration_seconds:.2f}s |")

    if summary.suites:
        output.append("")
        output.append("### Category Breakdown")
        output.append("")
        output.append("| Category | Total | Passed | Failed | Errors | Pass Rate |")
        output.append("|-------|-------|--------|--------|--------|-----------|")
        for suite_type, suite in summary.suites.items():
            pass_rate = suite.pass_rate
            output.append(f"| {suite_type.value} | {suite.trials} | {suite.passed} | {suite.failed} | {suite.errors} | {pass_rate:.1%} |")

    console.print("\n".join(output))


# ——— Comparison formatters —————————————————————————————————————————————————————

def format_comparison(comparison: Comparison, output_format: str = OutputFormat.RICH) -> None:
    """Format and display a comparison between candidate and baseline."""
    if output_format == OutputFormat.JSON:
        import json
        console.print(json.dumps({
            "common_cases": comparison.common_cases,
            "improved": comparison.improved,
            "regressed": comparison.regressed,
            "unchanged": comparison.unchanged,
            "candidate_pass_rate": comparison.candidate_pass_rate,
            "baseline_pass_rate": comparison.baseline_pass_rate,
            "pass_rate_delta": comparison.pass_rate_delta,
        }, indent=2))
        return

    if output_format == OutputFormat.PR_COMMENT:
        _format_comparison_pr_comment(comparison)
        return

    _format_comparison_rich(comparison)


def _format_comparison_rich(comparison: Comparison) -> None:
    """Format comparison — clean indented output, no heavy panels."""
    has_regressions = bool(comparison.regressed)
    title = "REGRESSIONS DETECTED" if has_regressions else "BASELINE COMPARISON"
    style = "glyph.danger" if has_regressions else "glyph.muted"

    console.print()
    _rule(title, style=style)
    console.print()

    _kv("common tests", str(comparison.common_cases))

    delta = comparison.pass_rate_delta
    delta_sym = "+" if delta > 0 else ""
    delta_style = "glyph.success" if delta > 0 else "glyph.danger" if delta < 0 else "glyph.muted"

    console.print()
    console.print(f"  [glyph.muted]{'baseline'.ljust(22)}[/glyph.muted]{comparison.baseline_pass_rate:.1%}")
    console.print(
        f"  [glyph.muted]{'candidate'.ljust(22)}[/glyph.muted]"
        f"[glyph.value]{comparison.candidate_pass_rate:.1%}[/glyph.value]  "
        f"[{delta_style}]{delta_sym}{delta:.1%}[/{delta_style}]"
    )
    console.print()

    improved = len(comparison.improved)
    regressed = len(comparison.regressed)
    unchanged = len(comparison.unchanged)

    console.print(
        f"  {_status_icon(not has_regressions)} "
        f"[glyph.success]{improved} improved[/glyph.success]  "
        f"[glyph.dim_sep]|[/glyph.dim_sep]  "
        f"{'[glyph.danger]' if regressed else '[glyph.muted]'}{regressed} regressed"
        f"{'[/glyph.danger]' if regressed else '[/glyph.muted]'}  "
        f"[glyph.dim_sep]|[/glyph.dim_sep]  "
        f"[glyph.muted]{unchanged} unchanged[/glyph.muted]"
    )

    console.print()
    _rule()

    # Detail table for changed cases
    if comparison.improved or comparison.regressed:
        console.print()
        console.print("  [bold]Tests that got worse[/bold]")
        detail_table = Table(
            show_header=False,
            box=None,
            padding=(0, 2),
        )
        detail_table.add_column("Test ID", style="cyan")
        detail_table.add_column("Reason", style="dim")
        detail_table.add_column("Score", style="dim")

        for change in comparison.improved:
            if hasattr(change, "case_id"):
                detail_table.add_row(f"  {change.case_id}", "failed before · passed now", f"(score {change.old_score:.2f} -> {change.new_score:.2f})")
            else:
                detail_table.add_row(f"  {change}", "failed before · passed now", "")

        for change in comparison.regressed:
            if hasattr(change, "case_id"):
                detail_table.add_row(f"  {change.case_id}", "passed before · failed now", f"(score {change.old_score:.2f} -> {change.new_score:.2f})")
            else:
                detail_table.add_row(f"  {change}", "passed before · failed now", "")

        console.print(detail_table)


def _format_comparison_pr_comment(comparison: Comparison) -> None:
    """Format comparison as GitHub PR comment (Markdown)."""
    output = []
    output.append("## Comparison Results")
    output.append("")
    output.append("| Metric | Value |")
    output.append("|--------|-------|")
    output.append(f"| Common Tests | {comparison.common_cases} |")
    output.append(f"| Improved | {len(comparison.improved)} |")
    output.append(f"| Regressed | {len(comparison.regressed)} |")
    output.append(f"| Unchanged | {len(comparison.unchanged)} |")
    output.append(f"| Baseline Pass Rate | {comparison.baseline_pass_rate:.1%} |")
    output.append(f"| Candidate Pass Rate | {comparison.candidate_pass_rate:.1%} |")

    delta = comparison.pass_rate_delta
    delta_symbol = "+" if delta > 0 else ""
    output.append(f"| Pass Rate Delta | {delta_symbol}{delta:.1%} |")

    if comparison.improved or comparison.regressed:
        output.append("")
        output.append("### Test Changes")
        output.append("")
        for change in comparison.improved:
            case_id = getattr(change, "case_id", str(change))
            output.append(f"- {case_id}: UP")
        for change in comparison.regressed:
            case_id = getattr(change, "case_id", str(change))
            output.append(f"- {case_id}: DOWN")

    console.print("\n".join(output))


# â”€â”€â”€ Release decision formatters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def format_release_decision(decision: ReleaseDecision, output_format: str = OutputFormat.RICH) -> None:
    """Format and display a release decision."""
    if output_format == OutputFormat.JSON:
        console.print(decision.model_dump_json(indent=2))
        return

    if output_format == OutputFormat.PR_COMMENT:
        _format_release_decision_pr_comment(decision)
        return

    _format_release_decision_rich(decision)


def _format_release_decision_rich(decision: ReleaseDecision) -> None:
    """Format release decision â€” clean checklist, no nested panels."""
    verdict = "RELEASE ALLOWED" if decision.allowed else "RELEASE BLOCKED"
    style = "glyph.success" if decision.allowed else "glyph.danger"

    console.print()
    _rule(verdict, style=style)
    console.print()

    # Checklist
    checks = [
        ("Deterministic evaluation", decision.deterministics_passed, decision.deterministics_rationale),
        ("Regression check", decision.regression_passed, decision.regression_rationale),
        ("Judge evaluation", decision.judge_passed, decision.judge_rationale),
    ]
    for label, passed, rationale in checks:
        icon = _status_icon(passed)
        console.print(f"  {icon} {label}")
        if rationale and rationale != "N/A":
            console.print(f"      [glyph.muted]{rationale}[/glyph.muted]")

    # Summary metrics
    console.print()
    _kv("overall pass rate", f"{decision.overall_pass_rate:.1%}")
    _kv("capability", f"{decision.capability_pass_rate:.1%}")
    _kv("regression", f"{decision.regression_pass_rate:.1%}")
    _kv("security", f"{decision.security_pass_rate:.1%}")
    _kv("error rate", f"{decision.error_rate:.1%}")
    _kv("regressions", str(decision.regression_count))

    if decision.pass_rate_delta:
        delta = decision.pass_rate_delta
        sym = "+" if delta > 0 else ""
        _kv("pass rate delta", f"{sym}{delta:.1%}")

    if decision.judge_cost_usd:
        _kv("judge cost", f"${decision.judge_cost_usd:.2f}")

    console.print()
    _rule()


def _format_release_decision_pr_comment(decision: ReleaseDecision) -> None:
    """Format release decision as GitHub PR comment (Markdown)."""
    output = []

    if decision.allowed:
        output.append("## RELEASE ALLOWED")
    else:
        output.append("## RELEASE BLOCKED")

    output.append("")
    output.append(f"**Rationale:** {decision.reason}")
    output.append("")

    output.append("### Policy Checklist")
    output.append("")
    output.append("| Check | Requirement | Status | Details |")
    output.append("|-------|-------------|--------|---------|")

    det_status = "PASS" if decision.deterministics_passed else "FAIL"
    output.append(f"| {det_status} | Deterministic Evaluation | {det_status} | {decision.deterministics_rationale} |")

    reg_status = "PASS" if decision.regression_passed else "FAIL"
    output.append(f"| {reg_status} | Regression Check | {reg_status} | {decision.regression_rationale} |")

    judge_status = "PASS" if decision.judge_passed else "FAIL"
    output.append(f"| {judge_status} | Judge Evaluation | {judge_status} | {decision.judge_rationale} |")

    output.append("")
    output.append("### Summary Metrics")
    output.append("")
    output.append("| Metric | Value |")
    output.append("|--------|-------|")
    output.append(f"| Overall Pass Rate | {decision.overall_pass_rate:.1%} |")
    output.append(f"| Capability Pass Rate | {decision.capability_pass_rate:.1%} |")
    output.append(f"| Regression Pass Rate | {decision.regression_pass_rate:.1%} |")
    output.append(f"| Security Pass Rate | {decision.security_pass_rate:.1%} |")
    output.append(f"| Error Rate | {decision.error_rate:.1%} |")
    output.append(f"| Regression Count | {decision.regression_count} |")
    output.append(f"| Pass Rate Delta | {decision.pass_rate_delta:.1%} |")
    output.append(f"| Judge Score | {decision.judge_score:.1%} |")
    output.append(f"| Judge Cost USD | ${decision.judge_cost_usd:.2f} |")

    console.print("\n".join(output))


# â”€â”€â”€ Trial detail formatters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def format_trial_detail(record: TrialRecord, output_format: str = OutputFormat.RICH) -> None:
    """Format and display a single trial record."""
    if output_format == OutputFormat.JSON:
        console.print(record.model_dump_json(indent=2))
        return

    if output_format == OutputFormat.PR_COMMENT:
        _format_trial_detail_pr_comment(record)
        return

    _format_trial_detail_rich(record)


def _format_trial_detail_rich(record: TrialRecord) -> None:
    """Format trial detail â€” clean indented layout."""
    status = record.status.value.upper()
    status_style = {
        "PASSED": "glyph.success",
        "FAILED": "glyph.danger",
        "ERROR": "glyph.danger",
        "TIMEOUT": "glyph.warning",
        "BUDGET_EXCEEDED": "glyph.warning",
    }.get(status, "glyph.muted")

    console.print()
    console.print(
        f"  [{status_style}]{_BULLET} {status}[/{status_style}]  "
        f"[glyph.value]{record.case_id}[/glyph.value]"
    )
    console.print()

    _kv("test result id", record.trial_id)
    _kv("repetition", str(record.repetition_index))
    _kv("category", record.suite.value if hasattr(record.suite, "value") else str(record.suite))
    _kv("duration", f"{record.duration_ms}ms")
    _kv("score", f"{record.score:.2f}")

    if record.sandbox is not None:
        isolation_type = "network blocking: off" if record.sandbox.isolation == "egress_metadata_only" else ("can run commands" if record.sandbox.isolation == "run_exec" else record.sandbox.isolation)
        _kv("isolation", f"{record.sandbox.provider} ({isolation_type})")
        cleanup = f"[glyph.success]{_CHECK}[/glyph.success]" if record.sandbox_cleanup.succeeded else "[glyph.warning]not verified[/glyph.warning]"
        _kv("cleanup", cleanup)

    # Grades
    if record.grades:
        console.print()
        for grade in record.grades:
            icon = _status_icon(grade.passed)
            console.print(
                f"  {icon} [glyph.muted]{grade.grader.ljust(22)}[/glyph.muted]"
                f"{grade.score:.2f}"
            )

    console.print()
    _rule()


def _format_trial_detail_pr_comment(record: TrialRecord) -> None:
    """Format trial detail as GitHub PR comment (Markdown)."""
    output = []
    output.append(f"## Trial Detail: {record.case_id}")
    output.append("")
    output.append(f"**Status:** {record.status.value.upper()}")
    output.append("")
    output.append("| Field | Value |")
    output.append("|-------|-------|")
    output.append(f"| Test Result ID | {record.trial_id} |")
    output.append(f"| Repetition | {record.repetition_index} |")
    output.append(f"| Category | {record.suite} |")
    output.append(f"| Duration | {record.duration_ms}ms |")
    output.append(f"| Score | {record.score:.2f} |")

    if record.grades:
        output.append("")
        output.append("### Grades")
        output.append("")
        output.append("| Check | Score | Status |")
        output.append("|--------|-------|--------|")
        for grade in record.grades:
            status = "PASS" if grade.passed else "FAIL"
            output.append(f"| {grade.grader} | {grade.score:.2f} | {status} |")

    console.print("\n".join(output))


# â”€â”€â”€ Progress bar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def create_progress_callback(total_trials: int) -> tuple[Progress, Callable[[TrialRecord], None], list[TrialRecord]]:
    """Create a progress bar and callback function for trial updates."""
    progress = Progress(
        TextColumn("Running"),
        BarColumn(bar_width=16),
        TextColumn("{task.completed} / {task.total} tests"),
        TextColumn("  [glyph.success]{task.fields[passed]} passed[/glyph.success] · "
                   "[glyph.danger]{task.fields[failed]} failed[/glyph.danger] · "
                   "[glyph.warning]{task.fields[errors]} error[/glyph.warning]"),
        console=console,
        transient=False,
    )

    task = progress.add_task("", total=total_trials, passed=0, failed=0, errors=0)

    completed_trials: list[TrialRecord] = []

    def callback(record: TrialRecord) -> None:
        """Update progress bar after each trial completes."""
        completed_trials.append(record)
        passed = sum(1 for t in completed_trials if t.status.value == "passed")
        failed = sum(1 for t in completed_trials if t.status.value in ("failed", "timeout", "budget_exceeded"))
        errors = sum(1 for t in completed_trials if t.status.value == "error")
        progress.update(task, advance=1, passed=passed, failed=failed, errors=errors)

    return progress, callback, completed_trials


def print_failed_tests_inline(completed_trials: list[TrialRecord]) -> None:
    """Print a compact summary of failed tests."""
    failed = [t for t in completed_trials if t.status.value in ("failed", "timeout", "budget_exceeded", "error")]
    if not failed:
        return
    console.print()
    console.print("  [bold]Failed tests[/bold]")
    table = Table(box=None, padding=(0, 2), show_header=False)
    table.add_column("Test ID", style="cyan")
    table.add_column("Reason", style="dim")
    table.add_column("Score", justify="right")
    
    for t in failed:
        reason = "unknown"
        if t.status.value == "error":
            reason = "execution error"
        elif t.status.value == "timeout":
            reason = "timed out"
        elif t.status.value == "budget_exceeded":
            reason = "budget exceeded"
        elif t.grades:
            for g in t.grades:
                if not g.passed:
                    reason = g.reason
                    break
        table.add_row(f"  {t.case_id}", reason, f"score {t.score:.2f}")
    
    console.print(table)

