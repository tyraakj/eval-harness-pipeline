from __future__ import annotations

from pathlib import Path

import pytest

from glyph.core.config import (
    EvaluationConfig,
    create_sample_config,
    list_available_graders,
    load_config,
)


@pytest.fixture
def sample_config_path(tmp_path: Path) -> Path:
    """Create a sample config file for testing."""
    config_content = """
suite:
  id: test-suite
  version: 1.0.0
  description: Test evaluation suite
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
    config_file = tmp_path / "eval.yaml"
    config_file.write_text(config_content)
    return config_file


def test_load_config_success(sample_config_path: Path):
    """Test successful config loading."""
    config = load_config(sample_config_path)
    
    assert isinstance(config, EvaluationConfig)
    assert config.suite.id == "test-suite"
    assert config.suite.version == "1.0.0"
    assert config.repetitions == 3
    assert len(config.graders) == 2
    assert config.budget.timeout_seconds == 60
    assert config.budget.max_concurrency == 4


def test_load_config_file_not_found(tmp_path: Path):
    """Test loading config from non-existent file."""
    from glyph.core.config import ConfigLoadError
    
    nonexistent = tmp_path / "nonexistent.yaml"
    with pytest.raises(ConfigLoadError, match="Config file not found"):
        load_config(nonexistent)


def test_load_config_invalid_yaml(tmp_path: Path):
    """Test loading config with invalid YAML."""
    from glyph.core.config import ConfigLoadError
    
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("invalid: yaml: content: [unclosed")
    
    with pytest.raises(ConfigLoadError, match="Invalid YAML"):
        load_config(invalid_yaml)


def test_load_config_missing_required_field(tmp_path: Path):
    """Test loading config with missing required field."""
    from glyph.core.config import ConfigLoadError
    
    incomplete_config = tmp_path / "incomplete.yaml"
    incomplete_config.write_text("suite:\n  id: test\n# Missing target")
    
    with pytest.raises(ConfigLoadError, match="Missing required field"):
        load_config(incomplete_config)


def test_load_config_unknown_grader(tmp_path: Path):
    """Test loading config with unknown grader type."""
    from glyph.core.config import UnknownGraderError
    
    config_content = """
suite:
  id: test
  version: 1.0.0

target:
  adapter: anthropic
  kwargs:
    model: claude-3-5-sonnet-20240620

dataset: datasets/example.jsonl

graders:
  - type: unknown_grader
"""
    config_file = tmp_path / "unknown_grader.yaml"
    config_file.write_text(config_content)
    
    with pytest.raises(UnknownGraderError, match="Unknown grader type"):
        load_config(config_file)


def test_load_config_default_values(tmp_path: Path):
    """Test that config loading uses sensible defaults."""
    minimal_config = """
suite:
  id: test
  version: 1.0.0

target:
  adapter: anthropic
  kwargs:
    model: claude-3-5-sonnet-20240620

dataset: datasets/example.jsonl

graders:
  - type: exact_match
"""
    config_file = tmp_path / "minimal.yaml"
    config_file.write_text(minimal_config)
    
    config = load_config(config_file)
    
    # Check defaults
    assert config.repetitions == 1
    assert config.budget is None


def test_list_available_graders():
    """Test that list_available_graders returns expected graders."""
    graders = list_available_graders()
    
    assert isinstance(graders, dict)
    assert "exact_match" in graders
    assert "contains_all" in graders
    assert "tool_policy" in graders
    assert "outcome_state" in graders
    assert "trajectory_subsequence" in graders
    assert "loop_efficiency" in graders
    assert "retrieval_metrics" in graders
    
    # Check that descriptions are strings
    for grader_type, description in graders.items():
        assert isinstance(grader_type, str)
        assert isinstance(description, str)
        assert len(description) > 0


def test_create_sample_config(tmp_path: Path):
    """Test creating a sample config file."""
    output_path = tmp_path / "sample_eval.yaml"
    create_sample_config(output_path)
    
    assert output_path.exists()
    
    # Load and verify the created config
    config = load_config(output_path)
    assert config.suite.id == "my-evaluation"
    assert config.suite.version == "1.0.0"
    assert len(config.graders) >= 1
