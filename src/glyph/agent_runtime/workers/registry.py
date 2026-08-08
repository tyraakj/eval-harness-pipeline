"""Worker registry for managing specialized evaluation workers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from glyph.agent_runtime.worker_models import (
    NodeAnalysisCriteria,
    ToolExpertise,
    WorkerCapability,
    WorkerDomain,
    WorkerExpertise,
)
from pydantic import BaseModel


class WorkerDefinition(BaseModel):
    """Definition of a worker loaded from configuration."""
    worker_id: str
    domain: WorkerDomain
    capabilities: list[WorkerCapability]
    tool_expertise: list[dict[str, Any]] = []
    metadata_schemas: list[dict[str, Any]] = []
    node_analysis_criteria: list[dict[str, Any]] = []
    confidence_threshold: float = 0.7
    max_concurrent_tasks: int = 5


class WorkerRegistry:
    """Registry for managing worker definitions and creating expertise profiles."""

    def __init__(self) -> None:
        self._definitions: dict[str, WorkerDefinition] = {}

    def register_from_dict(self, definition: dict[str, Any]) -> WorkerExpertise:
        """Register a worker from a dictionary definition."""
        worker_def = WorkerDefinition(**definition)
        self._definitions[worker_def.worker_id] = worker_def
        return self._create_expertise(worker_def)

    def register_from_file(self, path: Path) -> WorkerExpertise:
        """Register a worker from a YAML/JSON file."""
        import json

        with path.open() as f:
            definition = json.load(f)
        return self.register_from_dict(definition)

    def _create_expertise(self, definition: WorkerDefinition) -> WorkerExpertise:
        """Create a WorkerExpertise from a WorkerDefinition."""
        tool_expertise = {
            te["tool_name"]: ToolExpertise(**te)
            for te in definition.tool_expertise
        }

        metadata_schemas = {}
        for ms in definition.metadata_schemas:
            from glyph.agent_runtime.worker_models import MetadataSchema
            metadata_schemas[ms["schema_name"]] = MetadataSchema(**ms)

        node_analysis_criteria = {}
        for nac in definition.node_analysis_criteria:
            node_analysis_criteria[nac.get("node_type", "default")] = NodeAnalysisCriteria(**nac)

        return WorkerExpertise(
            worker_id=definition.worker_id,
            domain=definition.domain,
            capabilities=frozenset(definition.capabilities),
            tool_expertise=tool_expertise,
            metadata_schemas=metadata_schemas,
            node_analysis_criteria=node_analysis_criteria,
            confidence_threshold=definition.confidence_threshold,
            max_concurrent_tasks=definition.max_concurrent_tasks,
        )

    def get_definition(self, worker_id: str) -> WorkerDefinition | None:
        """Get a worker definition by ID."""
        return self._definitions.get(worker_id)

    def list_workers(self, domain: WorkerDomain | None = None) -> list[str]:
        """List registered workers, optionally filtered by domain."""
        if domain is None:
            return list(self._definitions.keys())
        return [
            worker_id
            for worker_id, definition in self._definitions.items()
            if definition.domain == domain
        ]

    def create_default_workers(self) -> list[WorkerExpertise]:
        """Create default workers for common domains."""
        default_definitions = [
            {
                "worker_id": "code-execution-worker",
                "domain": WorkerDomain.CODE_EXECUTION,
                "capabilities": [
                    WorkerCapability.CODE_GENERATION,
                    WorkerCapability.CODE_DEBUGGING,
                    WorkerCapability.CODE_REFACTORING,
                ],
                "tool_expertise": [
                    {
                        "tool_name": "python_interpreter",
                        "expertise_level": 0.9,
                        "supported_operations": {"execute", "validate", "debug"},
                        "known_limitations": {"no_network", "limited_memory"},
                        "best_practices": ["validate_syntax", "handle_errors", "timeout_protection"],
                    }
                ],
                "confidence_threshold": 0.8,
                "max_concurrent_tasks": 3,
            },
            {
                "worker_id": "web-navigation-worker",
                "domain": WorkerDomain.WEB_NAVIGATION,
                "capabilities": [
                    WorkerCapability.WEB_SCRAPING,
                    WorkerCapability.WEB_FORM_FILLING,
                    WorkerCapability.WEB_NAVIGATION,
                ],
                "tool_expertise": [
                    {
                        "tool_name": "browser_automation",
                        "expertise_level": 0.85,
                        "supported_operations": {"navigate", "click", "fill_form", "extract"},
                        "known_limitations": {"dynamic_content", "captcha"},
                        "best_practices": ["wait_for_load", "handle_timeouts", "validate_elements"],
                    }
                ],
                "confidence_threshold": 0.75,
                "max_concurrent_tasks": 2,
            },
            {
                "worker_id": "data-analysis-worker",
                "domain": WorkerDomain.DATA_ANALYSIS,
                "capabilities": [
                    WorkerCapability.DATA_VISUALIZATION,
                    WorkerCapability.DATA_CLEANING,
                    WorkerCapability.DATA_TRANSFORMATION,
                ],
                "tool_expertise": [
                    {
                        "tool_name": "pandas_analyzer",
                        "expertise_level": 0.9,
                        "supported_operations": {"clean", "transform", "aggregate", "visualize"},
                        "known_limitations": {"large_datasets", "memory_intensive"},
                        "best_practices": ["validate_types", "handle_missing", "optimize_memory"],
                    }
                ],
                "confidence_threshold": 0.8,
                "max_concurrent_tasks": 4,
            },
            {
                "worker_id": "api-integration-worker",
                "domain": WorkerDomain.API_INTEGRATION,
                "capabilities": [
                    WorkerCapability.API_AUTHENTICATION,
                    WorkerCapability.API_RATE_LIMITING,
                    WorkerCapability.API_ERROR_HANDLING,
                ],
                "tool_expertise": [
                    {
                        "tool_name": "http_client",
                        "expertise_level": 0.95,
                        "supported_operations": {"get", "post", "put", "delete", "authenticate"},
                        "known_limitations": {"rate_limits", "timeout"},
                        "best_practices": ["retry_logic", "error_handling", "auth_caching"],
                    }
                ],
                "confidence_threshold": 0.85,
                "max_concurrent_tasks": 5,
            },
            {
                "worker_id": "security-worker",
                "domain": WorkerDomain.SECURITY,
                "capabilities": [
                    WorkerCapability.VULNERABILITY_SCANNING,
                    WorkerCapability.AUTHORIZATION_CHECKING,
                ],
                "tool_expertise": [
                    {
                        "tool_name": "security_scanner",
                        "expertise_level": 0.8,
                        "supported_operations": {"scan", "validate", "check_permissions"},
                        "known_limitations": {"false_positives", "context_awareness"},
                        "best_practices": ["validate_scope", "check_permissions", "log_findings"],
                    }
                ],
                "confidence_threshold": 0.9,
                "max_concurrent_tasks": 2,
            },
        ]

        expertises = []
        for definition in default_definitions:
            expertise = self.register_from_dict(definition)
            expertises.append(expertise)

        return expertises
