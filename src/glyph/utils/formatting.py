from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.theme import Theme

if TYPE_CHECKING:
    from glyph.grading.comparison import Comparison
    from glyph.core.models import EvalCase, ReleaseDecision, RunSummary, TrialRecord


# ─── Theme ────────────────────────────────────────────────────────────────────
# Soft, terminal-native palette — avoids neon; feels at home on dark backgrounds.

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


# ─── Constants ────────────────────────────────────────────────────────────────

_RULE_CHAR = "-"
_CHECK = "[PASS]"
_CROSS = "[FAIL]"
_BULLET = ">"
_WIDTH = 72


class OutputFormat:
    """Output format options for CLI commands."""
    RICH = "rich"
    JSON = "json"
    PR_COMMENT = "pr-comment"


# ─── Utilities ────────────────────────────────────────────────────────────────

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


# ─── Status bar ───────────────────────────────────────────────────────────────

def print_status_bar(*, cases: int | None = None, duration: str | None = None) -> None:
    """Print a dim footer line with context — like agent CLIs."""
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


# ─── Command header ──────────────────────────────────────────────────────────

def print_command_start(command: str, *, detail: str, run_id: str | None = None) -> None:
    """Render a compact, terminal-native command header for interactive use."""
    console.print()
    console.print(f"[glyph.brand]glyph[/glyph.brand] [glyph.header]{command}[/glyph.header]")
    console.print(f"  [glyph.muted]{detail}[/glyph.muted]")
    if run_id:
        console.print(f"  [glyph.muted]run[/glyph.muted] [glyph.value]{run_id}[/glyph.value]")
    _flush_console()


# ─── Live trial stream ────────────────────────────────────────────────────────

def print_trial_start(case: EvalCase, repetition_index: int) -> None:
    """Print the point at which a queued trial starts consuming execution capacity."""
    suffix = f" (trial {repetition_index + 1})" if repetition_index else ""
    console.print(f"[glyph.brand]glyph[/glyph.brand] eval {case.id}{suffix}")
    console.print(f"  [glyph.muted]running {case.suite.value} evaluation...[/glyph.muted]")
    _flush_console()


def print_trial_event(record: TrialRecord) -> None:
    """Print one completed trial in a compact, agent-style event stream."""
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


# ─── Run summary formatters ──────────────────────────────────────────────────

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
Total Trials: {summary.total}
Cases: {summary.cases}
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
        import json
        console.print(summary.model_dump_json(indent=2))
        return

    if output_format == OutputFormat.PR_COMMENT:
        _format_run_summary_pr_comment(summary)
        return

    _format_run_summary_rich(summary)


def _format_run_summary_rich(summary: RunSummary) -> None:
    """Format a compact completion report — clean, indented, no heavy borders."""
    blocked = bool(summary.errors or summary.timeouts)
    status = "BLOCKED" if blocked else "EVALUATION COMPLETE"
    style = "glyph.danger" if blocked else "glyph.muted"

    console.print()
    _rule(status, style=style)
    console.print()

    _kv("run", summary.run_id)
    _kv("trials", str(summary.total))
    _kv("cases x reps", f"{summary.cases} x {summary.repetitions}")

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
    _kv("artifact", summary.artifact_path)

    console.print()
    _rule()

    # Suite breakdown — lightweight table
    if summary.suites:
        console.print()
        suite_table = Table(
            title="Suite Breakdown",
            show_header=True,
            header_style="bold",
            box=box.SIMPLE_HEAD,
            padding=(0, 2),
            title_style="glyph.muted",
        )
        suite_table.add_column("Suite", style="dim")
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
        output.append("### Suite Breakdown")
        output.append("")
        output.append("| Suite | Total | Passed | Failed | Errors | Pass Rate |")
        output.append("|-------|-------|--------|--------|--------|-----------|")
        for suite_type, suite in summary.suites.items():
            pass_rate = suite.pass_rate
            output.append(f"| {suite_type.value} | {suite.trials} | {suite.passed} | {suite.failed} | {suite.errors} | {pass_rate:.1%} |")

    console.print("\n".join(output))


# ─── Comparison formatters ────────────────────────────────────────────────────

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

    _kv("common cases", str(comparison.common_cases))

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
        detail_table = Table(
            show_header=True,
            header_style="bold",
            box=box.SIMPLE_HEAD,
            padding=(0, 2),
        )
        detail_table.add_column("Case ID", style="dim")
        detail_table.add_column("Change", justify="center")

        for case_id in comparison.improved:
            detail_table.add_row(case_id, "[green]▲ improved[/green]")

        for case_id in comparison.regressed:
            detail_table.add_row(case_id, "[red]▼ regressed[/red]")

        console.print(detail_table)


def _format_comparison_pr_comment(comparison: Comparison) -> None:
    """Format comparison as GitHub PR comment (Markdown)."""
    output = []
    output.append("## Comparison Results")
    output.append("")
    output.append("| Metric | Value |")
    output.append("|--------|-------|")
    output.append(f"| Common Cases | {comparison.common_cases} |")
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
        output.append("### Case Changes")
        output.append("")
        for case_id in comparison.improved:
            output.append(f"- {case_id}: UP")
        for case_id in comparison.regressed:
            output.append(f"- {case_id}: DOWN")

    console.print("\n".join(output))


# ─── Release decision formatters ─────────────────────────────────────────────

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
    """Format release decision — clean checklist, no nested panels."""
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


# ─── Trial detail formatters ─────────────────────────────────────────────────

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
    """Format trial detail — clean indented layout."""
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

    _kv("trial id", record.trial_id)
    _kv("repetition", str(record.repetition_index))
    _kv("suite", record.suite)
    _kv("duration", f"{record.duration_ms}ms")
    _kv("score", f"{record.score:.2f}")

    if record.sandbox is not None:
        _kv("sandbox", f"{record.sandbox.provider} ({record.sandbox.isolation})")
        cleanup = f"[glyph.success]{_CHECK}[/glyph.success]" if record.sandbox_cleanup.succeeded else f"[glyph.warning]not verified[/glyph.warning]"
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
    output.append(f"| Trial ID | {record.trial_id} |")
    output.append(f"| Repetition | {record.repetition_index} |")
    output.append(f"| Suite | {record.suite} |")
    output.append(f"| Duration | {record.duration_ms}ms |")
    output.append(f"| Score | {record.score:.2f} |")

    if record.grades:
        output.append("")
        output.append("### Grades")
        output.append("")
        output.append("| Grader | Score | Status |")
        output.append("|--------|-------|--------|")
        for grade in record.grades:
            status = "PASS" if grade.passed else "FAIL"
            output.append(f"| {grade.grader} | {grade.score:.2f} | {status} |")

    console.print("\n".join(output))


# ─── Progress bar ─────────────────────────────────────────────────────────────

def create_progress_callback(total_trials: int) -> tuple[Progress, Callable[[TrialRecord], None]]:
    """Create a progress bar and callback function for trial updates."""
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console
    )

    task = progress.add_task("[cyan]Running trials...", total=total_trials)

    completed_trials: list[TrialRecord] = []

    def callback(record: TrialRecord) -> None:
        """Update progress bar after each trial completes."""
        completed_trials.append(record)
        progress.update(task, advance=1)
        completed = len(completed_trials)
        passed = sum(1 for trial in completed_trials if trial.status.value == "passed")
        pass_rate = passed / completed if completed > 0 else 0
        progress.update(task, description=f"[cyan]Running trials... ({pass_rate:.0%} passing)")

    return progress, callback
