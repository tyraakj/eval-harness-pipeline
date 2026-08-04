from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.table import Table

if TYPE_CHECKING:
    from langgraph_eval.grading.comparison import Comparison
    from langgraph_eval.core.models import ReleaseDecision, RunSummary, TrialRecord

console = Console()


class OutputFormat:
    """Output format options for CLI commands."""
    RICH = "rich"
    JSON = "json"
    PR_COMMENT = "pr-comment"


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
    """Format run summary with rich tables and panels."""
    summary_table = Table(title="Run Summary", show_header=True, header_style="bold cyan")
    summary_table.add_column("Metric", style="dim")
    summary_table.add_column("Value", justify="right")
    
    summary_table.add_row("Run ID", summary.run_id)
    summary_table.add_row("Total Trials", str(summary.total))
    summary_table.add_row("Cases", str(summary.cases))
    summary_table.add_row("Repetitions", str(summary.repetitions))
    summary_table.add_row("Passed", str(summary.passed), style="green")
    summary_table.add_row("Failed", str(summary.failed), style="red")
    summary_table.add_row("Errors", str(summary.errors), style="red")
    summary_table.add_row("Timeouts", str(summary.timeouts), style="yellow")
    summary_table.add_row("Pass Rate", f"{summary.pass_rate:.1%}", 
                         style="green" if summary.pass_rate >= 0.9 else "red")
    summary_table.add_row("Average Score", f"{summary.average_score:.2f}")
    
    duration_seconds = (summary.finished_at - summary.started_at).total_seconds()
    summary_table.add_row("Duration", f"{duration_seconds:.2f}s")
    
    console.print(Panel(summary_table, title="[bold]Evaluation Results[/bold]", border_style="cyan"))
    
    if summary.suites:
        suite_table = Table(title="Suite Breakdown", show_header=True, header_style="bold cyan")
        suite_table.add_column("Suite", style="dim")
        suite_table.add_column("Total", justify="right")
        suite_table.add_column("Passed", justify="right")
        suite_table.add_column("Failed", justify="right")
        suite_table.add_column("Errors", justify="right")
        suite_table.add_column("Pass Rate", justify="right")
        
        for suite_type, suite in summary.suites.items():
            pass_rate = suite.pass_rate
            style = "green" if pass_rate >= 0.9 else "red"
            suite_table.add_row(
                suite_type.value,
                str(suite.trials),
                str(suite.passed),
                str(suite.failed),
                str(suite.errors),
                f"{pass_rate:.1%}",
                style=style
            )
        
        console.print()
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
    """Format comparison with rich tables."""
    summary_table = Table(title="Comparison Summary", show_header=True, header_style="bold cyan")
    summary_table.add_column("Metric", style="dim")
    summary_table.add_column("Value", justify="right")
    
    summary_table.add_row("Common Cases", str(comparison.common_cases))
    summary_table.add_row("Improved", str(len(comparison.improved)), style="green")
    summary_table.add_row("Regressed", str(len(comparison.regressed)), style="red")
    summary_table.add_row("Unchanged", str(len(comparison.unchanged)))
    summary_table.add_row("Baseline Pass Rate", f"{comparison.baseline_pass_rate:.1%}")
    summary_table.add_row("Candidate Pass Rate", f"{comparison.candidate_pass_rate:.1%}")
    
    delta = comparison.pass_rate_delta
    delta_style = "green" if delta > 0 else "red" if delta < 0 else "dim"
    delta_symbol = "+" if delta > 0 else ""
    summary_table.add_row("Pass Rate Delta", f"{delta_symbol}{delta:.1%}", style=delta_style)
    
    console.print(Panel(summary_table, title="[bold]Comparison Results[/bold]", border_style="cyan"))
    
    if comparison.improved or comparison.regressed:
        detail_table = Table(title="Case Changes", show_header=True, header_style="bold cyan")
        detail_table.add_column("Case ID", style="dim")
        detail_table.add_column("Change", justify="center")
        
        for case_id in comparison.improved:
            detail_table.add_row(case_id, "[green]UP[/green]")
        
        for case_id in comparison.regressed:
            detail_table.add_row(case_id, "[red]DOWN[/red]")
        
        console.print()
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
    """Format release decision with rich checklist."""
    if decision.allowed:
        banner = Panel("[bold green]RELEASE ALLOWED[/bold green]", border_style="green")
    else:
        banner = Panel("[bold red]RELEASE BLOCKED[/bold red]", border_style="red")
    console.print(banner)
    
    console.print()
    console.print(Panel(decision.reason, title="[bold]Rationale[/bold]", border_style="cyan"))
    
    checklist_table = Table(title="Policy Checklist", show_header=True, header_style="bold cyan")
    checklist_table.add_column("Check", justify="center")
    checklist_table.add_column("Requirement", style="dim")
    checklist_table.add_column("Status", justify="center")
    checklist_table.add_column("Details")
    
    checkmark = "[green]✓[/green]" if decision.deterministics_passed else "[red]✗[/red]"
    checklist_table.add_row(
        checkmark,
        "Deterministic Evaluation",
        "PASS" if decision.deterministics_passed else "FAIL",
        decision.deterministics_rationale
    )
    
    checkmark = "[green]✓[/green]" if decision.regression_passed else "[red]✗[/red]"
    checklist_table.add_row(
        checkmark,
        "Regression Check",
        "PASS" if decision.regression_passed else "FAIL",
        decision.regression_rationale
    )
    
    checkmark = "[green]✓[/green]" if decision.judge_passed else "[red]✗[/red]"
    checklist_table.add_row(
        checkmark,
        "Judge Evaluation",
        "PASS" if decision.judge_passed else "FAIL",
        decision.judge_rationale
    )
    
    console.print()
    console.print(checklist_table)
    
    metrics_table = Table(title="Summary Metrics", show_header=True, header_style="bold cyan")
    metrics_table.add_column("Metric", style="dim")
    metrics_table.add_column("Value", justify="right")
    
    metrics_table.add_row("Overall Pass Rate", f"{decision.overall_pass_rate:.1%}")
    metrics_table.add_row("Capability Pass Rate", f"{decision.capability_pass_rate:.1%}")
    metrics_table.add_row("Regression Pass Rate", f"{decision.regression_pass_rate:.1%}")
    metrics_table.add_row("Security Pass Rate", f"{decision.security_pass_rate:.1%}")
    metrics_table.add_row("Error Rate", f"{decision.error_rate:.1%}")
    metrics_table.add_row("Regression Count", str(decision.regression_count))
    metrics_table.add_row("Pass Rate Delta", f"{decision.pass_rate_delta:.1%}")
    metrics_table.add_row("Judge Score", f"{decision.judge_score:.1%}")
    metrics_table.add_row("Judge Cost USD", f"${decision.judge_cost_usd:.2f}")
    
    console.print()
    console.print(metrics_table)


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
    output.append(f"| {'✓' if decision.deterministics_passed else '✗'} | Deterministic Evaluation | {det_status} | {decision.deterministics_rationale} |")
    
    reg_status = "PASS" if decision.regression_passed else "FAIL"
    output.append(f"| {'✓' if decision.regression_passed else '✗'} | Regression Check | {reg_status} | {decision.regression_rationale} |")
    
    judge_status = "PASS" if decision.judge_passed else "FAIL"
    output.append(f"| {'✓' if decision.judge_passed else '✗'} | Judge Evaluation | {judge_status} | {decision.judge_rationale} |")
    
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
    """Format trial detail with rich panels."""
    status_style = {
        "passed": "green",
        "failed": "red",
        "error": "red",
        "timeout": "yellow",
        "budget_exceeded": "yellow"
    }.get(record.status.value, "dim")
    
    header = Panel(
        f"[bold]Case:[/bold] {record.case_id} | [bold]Status:[/bold] [{status_style}]{record.status.value.upper()}[/{status_style}]",
        border_style=status_style
    )
    console.print(header)
    
    info_table = Table(show_header=False)
    info_table.add_column("Field", style="dim")
    info_table.add_column("Value")
    
    info_table.add_row("Trial ID", record.trial_id)
    info_table.add_row("Repetition", str(record.repetition_index))
    info_table.add_row("Suite", record.suite)
    info_table.add_row("Duration", f"{record.duration_ms}ms")
    info_table.add_row("Score", f"{record.score:.2f}")
    
    console.print(info_table)
    
    if record.grades:
        grades_table = Table(title="Grades", show_header=True, header_style="bold cyan")
        grades_table.add_column("Grader", style="dim")
        grades_table.add_column("Score", justify="right")
        grades_table.add_column("Status", justify="center")
        
        for grade in record.grades:
            status = "PASS" if grade.passed else "FAIL"
            style = "green" if grade.passed else "red"
            grades_table.add_row(grade.grader, f"{grade.score:.2f}", f"[{style}]{status}[/{style}]")
        
        console.print()
        console.print(grades_table)


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
