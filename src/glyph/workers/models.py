"""Specialized worker models for domain-specific evaluations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WorkerDomain(StrEnum):
    """Domains that specialized workers can evaluate."""
    CODE_EXECUTION = "code_execution"
    WEB_NAVIGATION = "web_navigation"
    DATA_ANALYSIS = "data_analysis"
    API_INTEGRATION = "api_integration"
    FILESYSTEM = "filesystem"
    SECURITY = "security"
    RETRIEVAL = "retrieval"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    GENERAL = "general"


class WorkerCapability(StrEnum):
    """Specific capabilities within a domain."""
    CODE_GENERATION = "code_generation"
    CODE_DEBUGGING = "code_debugging"
    CODE_REFACTORING = "code_refactoring"
    WEB_SCRAPING = "web_scraping"
    WEB_FORM_FILLING = "web_form_filling"
    WEB_NAVIGATION = "web_navigation"
    DATA_VISUALIZATION = "data_visualization"
    DATA_CLEANING = "data_cleaning"
    DATA_TRANSFORMATION = "data_transformation"
    API_AUTHENTICATION = "api_authentication"
    API_RATE_LIMITING = "api_rate_limiting"
    API_ERROR_HANDLING = "api_error_handling"
    FILE_READING = "file_reading"
    FILE_WRITING = "file_writing"
    FILE_VALIDATION = "file_validation"
    VULNERABILITY_SCANNING = "vulnerability_scanning"
    AUTHORIZATION_CHECKING = "authorization_checking"
    SEMANTIC_SEARCH = "semantic_search"
    HYBRID_SEARCH = "hybrid_search"
    DEDUPLICATION = "deduplication"
    MULTI_STEP_REASONING = "multi_step_reasoning"
    TOOL_SELECTION = "tool_selection"
    TOOL_COMPOSITION = "tool_composition"


@dataclass
class ToolExpertise:
    """Defines a worker's expertise with specific tools."""
    tool_name: str
    expertise_level: float = Field(ge=0.0, le=1.0, description="0-1 score of expertise")
    supported_operations: set[str] = field(default_factory=set)
    known_limitations: set[str] = field(default_factory=set)
    best_practices: list[str] = field(default_factory=list)


@dataclass
class MetadataSchema:
    """Defines metadata structure a worker can analyze."""
    schema_name: str
    required_fields: set[str] = field(default_factory=set)
    optional_fields: set[str] = field(default_factory=set)
    validation_rules: dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeAnalysisCriteria:
    """Criteria for analyzing LangGraph nodes."""
    node_types: set[str] = field(default_factory=set)
    required_inputs: set[str] = field(default_factory=set)
    expected_outputs: set[str] = field(default_factory=set)
    performance_thresholds: dict[str, float] = field(default_factory=dict)


class WorkerExpertise(BaseModel):
    """Defines a worker's domain expertise and capabilities."""
    worker_id: str
    domain: WorkerDomain
    capabilities: frozenset[WorkerCapability] = Field(default_factory=frozenset)
    tool_expertise: dict[str, ToolExpertise] = Field(default_factory=dict)
    metadata_schemas: dict[str, MetadataSchema] = Field(default_factory=dict)
    node_analysis_criteria: dict[str, NodeAnalysisCriteria] = Field(default_factory=dict)
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    max_concurrent_tasks: int = Field(default=5, ge=1)


class WorkerTask(BaseModel):
    """A task assigned to a specialized worker."""
    task_id: str
    domain: WorkerDomain
    required_capabilities: frozenset[WorkerCapability] = Field(default_factory=frozenset)
    target_tools: frozenset[str] = Field(default_factory=frozenset)
    metadata_requirements: frozenset[str] = Field(default_factory=frozenset)
    node_analysis_requirements: frozenset[str] = Field(default_factory=frozenset)
    priority: int = Field(default=0, ge=0)
    context: dict[str, Any] = Field(default_factory=dict)


class WorkerResult(BaseModel):
    """Result from a specialized worker evaluation."""
    task_id: str
    worker_id: str
    domain: WorkerDomain
    success: bool
    confidence: float = Field(ge=0.0, le=1.0)
    findings: dict[str, Any] = Field(default_factory=dict)
    tool_analysis: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metadata_analysis: dict[str, Any] = Field(default_factory=dict)
    node_analysis: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    execution_time_ms: int = Field(ge=0)
    error_message: str | None = None
    ai_analysis_used: bool = False
    ai_model: str | None = None
    ai_confidence: float | None = None


class WorkerRouting(BaseModel):
    """Routing decision for worker assignment."""
    task_id: str
    selected_worker_id: str
    routing_reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    alternative_workers: list[str] = Field(default_factory=list)
