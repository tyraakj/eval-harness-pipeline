"""YAML configuration loader for evaluation definitions.

This module provides functionality to load evaluation configurations from YAML files,
supporting both factory-based and adapter-based target configurations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigLoadError(Exception):
    """Raised when config file cannot be loaded or is invalid."""
    pass


class UnknownGraderError(Exception):
    """Raised when config references an unknown grader type."""
    pass


@dataclass
class GraderConfig:
    """Grader configuration from YAML."""
    type: str
    kwargs: dict[str, Any] | None = None


@dataclass
class BudgetConfig:
    """Budget configuration from YAML."""
    timeout_seconds: float = 60.0
    max_tool_calls: int | None = None
    max_output_chars: int | None = None
    max_concurrency: int = 4
    max_judge_cost_usd: float | None = None
    http_timeout_seconds: float = 1.0
    call_timeout_seconds: float = 10.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.25
    max_recorded_errors: int = 100


@dataclass
class SuiteConfig:
    """Suite configuration from YAML."""
    id: str
    version: str
    description: str | None = None
    default_graders: list[str] | None = None
    tracked_metrics: list[str] | None = None


@dataclass
class GraderPolicyConfig:
    """Grader policy configuration from YAML."""
    weights: dict[str, float] | None = None
    required: list[str] | None = None
    pass_threshold: float = 0.8


@dataclass
class EvaluationConfig:
    """Complete evaluation configuration from YAML."""
    suite: SuiteConfig
    target: dict[str, Any]
    dataset: str
    output: str | None = None
    graders: list[GraderConfig] | None = None
    budget: BudgetConfig | None = None
    repetitions: int = 1
    grader_policy: GraderPolicyConfig | None = None


# Built-in grader registry
_BUILTIN_GRADERS = {
    "exact_match": "Exact string match between expected and actual output",
    "contains_all": "Check that actual output contains all expected items",
    "tool_policy": "Validate tool call policy compliance",
    "outcome_state": "Check that the outcome state matches expected",
    "trajectory_subsequence": "Verify trajectory contains expected subsequence",
    "loop_efficiency": "Check for efficient loop usage (no unnecessary loops)",
    "retrieval_metrics": "Evaluate retrieval quality metrics",
}


def list_available_graders() -> dict[str, str]:
    """List all built-in grader types with descriptions."""
    return _BUILTIN_GRADERS.copy()


def load_config(path: Path) -> EvaluationConfig:
    """Load evaluation configuration from YAML file.
    
    Args:
        path: Path to YAML config file
        
    Returns:
        EvaluationConfig instance
        
    Raises:
        ConfigLoadError: If config is invalid
        UnknownGraderError: If config references unknown grader type
    """
    if not path.exists():
        raise ConfigLoadError(f"Config file not found: {path}")
    
    try:
        config_data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ConfigLoadError(f"Invalid YAML: {e}")
    
    if not isinstance(config_data, dict):
        raise ConfigLoadError("Config must be a dictionary")
    
    try:
        return _build_evaluation_config(config_data, path.parent)
    except KeyError as e:
        raise ConfigLoadError(f"Missing required field: {e}")
    except (ValueError, TypeError) as e:
        raise ConfigLoadError(f"Invalid config: {e}")


def _build_evaluation_config(data: dict[str, Any], config_dir: Path) -> EvaluationConfig:
    """Build EvaluationConfig from parsed YAML data."""
    # Parse suite
    suite_data = data["suite"]
    suite = SuiteConfig(
        id=suite_data["id"],
        version=suite_data["version"],
        description=suite_data.get("description"),
        default_graders=suite_data.get("default_graders"),
        tracked_metrics=suite_data.get("tracked_metrics"),
    )
    
    # Parse target
    target = data["target"]
    
    # Parse graders
    graders = []
    if "graders" in data:
        for grader_data in data["graders"]:
            grader_type = grader_data["type"]
            if grader_type not in _BUILTIN_GRADERS:
                raise UnknownGraderError(f"Unknown grader type: {grader_type}")
            graders.append(GraderConfig(
                type=grader_type,
                kwargs=grader_data.get("kwargs"),
            ))
    
    # Parse budget
    budget = None
    if "budget" in data:
        budget_data = data["budget"]
        budget = BudgetConfig(
            timeout_seconds=budget_data.get("timeout_seconds", 60.0),
            max_tool_calls=budget_data.get("max_tool_calls"),
            max_output_chars=budget_data.get("max_output_chars"),
            max_concurrency=budget_data.get("max_concurrency", 4),
            max_judge_cost_usd=budget_data.get("max_judge_cost_usd"),
            http_timeout_seconds=budget_data.get("http_timeout_seconds", 1.0),
            call_timeout_seconds=budget_data.get("call_timeout_seconds", 10.0),
            max_attempts=budget_data.get("max_attempts", 3),
            retry_backoff_seconds=budget_data.get("retry_backoff_seconds", 0.25),
            max_recorded_errors=budget_data.get("max_recorded_errors", 100),
        )
    
    # Parse grader policy
    grader_policy = None
    if "grader_policy" in data:
        policy_data = data["grader_policy"]
        grader_policy = GraderPolicyConfig(
            weights=policy_data.get("weights"),
            required=policy_data.get("required"),
            pass_threshold=policy_data.get("pass_threshold", 0.8),
        )
    
    return EvaluationConfig(
        suite=suite,
        target=target,
        dataset=data["dataset"],
        output=data.get("output"),
        graders=graders if graders else None,
        budget=budget,
        repetitions=data.get("repetitions", 1),
        grader_policy=grader_policy,
    )


def create_sample_config(output_path: Path) -> None:
    """Create a sample configuration file.
    
    Args:
        output_path: Path where to write the sample config
    """
    sample_config = """
suite:
  id: my-evaluation
  version: 1.0.0
  description: Example evaluation suite
  default_graders:
    - exact_match
  tracked_metrics:
    - latency
    - cost

target:
  adapter: anthropic
  kwargs:
    model: claude-3-5-sonnet-20240620
    system_prompt: "You are a helpful assistant."

dataset: datasets/example.jsonl
output: artifacts/results.jsonl

graders:
  - type: exact_match
  - type: tool_policy
    allowed_tools:
      - search_docs
      - lookup_order

budget:
  timeout_seconds: 60
  max_tool_calls: 8
  max_concurrency: 4

repetitions: 3

grader_policy:
  weights:
    exact_match: 0.7
    tool_policy: 0.3
  required:
    - tool_policy
  pass_threshold: 0.8
"""
    output_path.write_text(sample_config)
