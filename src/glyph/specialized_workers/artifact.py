"""Immutable evaluation artifact for zero-token replay evaluation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionMode(StrEnum):
    """Execution mode for the artifact."""
    LIVE = "live"
    REPLAY = "replay"


class ArtifactStatus(StrEnum):
    """Status of the artifact."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelManifest(BaseModel):
    """Manifest for model configuration."""
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    parameters_hash: str = Field(min_length=1)  # sha256 hash of parameters
    
    def compute_hash(self) -> str:
        """Compute hash of the manifest for cache key generation."""
        manifest_str = f"{self.provider}:{self.model_id}:{self.parameters_hash}"
        return hashlib.sha256(manifest_str.encode()).hexdigest()


class UsageMetrics(BaseModel):
    """Token usage and cost metrics."""
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost: float = Field(ge=0.0)
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class EvaluationArtifact(BaseModel):
    """
    Immutable artifact containing bounded, sanitized evidence for replay evaluation.
    
    This is the central object in the zero-token replay architecture. Once created,
    an artifact is immutable and can be reused for deterministic grading without
    calling the model again.
    """
    # Identification
    artifact_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    mode: ExecutionMode
    case_id: str = Field(min_length=1)
    trial_id: str = Field(min_length=1)
    
    # Target information
    target_version: str = Field(min_length=1)  # git:abc123 or version identifier
    model_manifest: ModelManifest
    
    # Hashes for cache validation
    dataset_hash: str = Field(min_length=1)
    sandbox_hash: str = Field(min_length=1)
    fixture_hash: str = Field(min_length=1)
    
    # Bounded, sanitized evidence (no hidden chain-of-thought)
    events: list[dict[str, Any]] = Field(default_factory=list)
    final_output: dict[str, Any] = Field(default_factory=dict)
    outcome_observations: list[dict[str, Any]] = Field(default_factory=list)
    
    # Usage metrics
    usage: UsageMetrics
    
    # Status and timing
    status: ArtifactStatus = ArtifactStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    
    # Artifact integrity
    artifact_hash: str = Field(min_length=1)
    
    class Config:
        # Make the model immutable (frozen)
        frozen = True
        use_enum_values = True
    
    @classmethod
    def create(
        cls,
        run_id: str,
        mode: ExecutionMode,
        case_id: str,
        trial_id: str,
        target_version: str,
        model_manifest: ModelManifest,
        dataset_hash: str,
        sandbox_hash: str,
        fixture_hash: str,
        events: list[dict[str, Any]],
        final_output: dict[str, Any],
        outcome_observations: list[dict[str, Any]],
        usage: UsageMetrics,
    ) -> "EvaluationArtifact":
        """Create a new artifact with generated IDs and hashes."""
        import uuid
        
        # Generate artifact ID
        artifact_id = f"artifact_{uuid.uuid4().hex[:12].upper()}"
        
        # Create artifact without hash first
        artifact_data = {
            "artifact_id": artifact_id,
            "run_id": run_id,
            "mode": mode,
            "case_id": case_id,
            "trial_id": trial_id,
            "target_version": target_version,
            "model_manifest": model_manifest,
            "dataset_hash": dataset_hash,
            "sandbox_hash": sandbox_hash,
            "fixture_hash": fixture_hash,
            "events": events,
            "final_output": final_output,
            "outcome_observations": outcome_observations,
            "usage": usage,
            "status": ArtifactStatus.COMPLETED,
            "completed_at": datetime.now(UTC),
            "artifact_hash": "",  # Will be computed
        }
        
        # Compute artifact hash from all fields except the hash itself
        artifact_dict = {k: v for k, v in artifact_data.items() if k != "artifact_hash"}
        artifact_json = json.dumps(artifact_dict, sort_keys=True, default=str)
        artifact_hash = f"sha256:{hashlib.sha256(artifact_json.encode()).hexdigest()}"
        
        artifact_data["artifact_hash"] = artifact_hash
        
        return cls(**artifact_data)
    
    def compute_cache_key(self) -> str:
        """
        Compute cache key for content-addressed caching.
        
        The cache key includes all dependencies that affect execution:
        - case_hash (derived from case_id and dataset)
        - target_version
        - model_manifest_hash
        - tool_contract_hash (if present in events)
        - retriever_hash (if present in events)
        - fixture_hash
        - sandbox_hash
        """
        # Extract hashes from events for tool/retrieval contracts
        tool_contract_hash = self._extract_tool_contract_hash()
        retriever_hash = self._extract_retriever_hash()
        
        # Combine all dependency hashes
        key_parts = [
            self.case_id,
            self.dataset_hash,
            self.target_version,
            self.model_manifest.compute_hash(),
            tool_contract_hash,
            retriever_hash,
            self.fixture_hash,
            self.sandbox_hash,
        ]
        
        key_string = ":".join(str(part) for part in key_parts if part)
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    def _extract_tool_contract_hash(self) -> str:
        """Extract tool contract hash from events."""
        for event in self.events:
            if event.get("event_type") == "tool_contract":
                return event.get("contract_hash", "")
        return ""
    
    def _extract_retriever_hash(self) -> str:
        """Extract retriever hash from events."""
        for event in self.events:
            if event.get("event_type") == "retrieval_config":
                return event.get("retriever_hash", "")
        return ""
    
    def is_replayable(self) -> bool:
        """Check if this artifact can be used for replay evaluation."""
        return (
            self.status == ArtifactStatus.COMPLETED and
            self.mode == ExecutionMode.LIVE and
            len(self.events) > 0
        )
    
    def get_sanitized_events(self) -> list[dict[str, Any]]:
        """
        Get sanitized events suitable for replay.
        
        This ensures no hidden chain-of-thought or sensitive data is exposed.
        """
        sanitized = []
        
        for event in self.events:
            # Remove any hidden reasoning
            if "hidden_reasoning" in event:
                event = {k: v for k, v in event.items() if k != "hidden_reasoning"}
            
            # Hash sensitive payloads
            if "sensitive_payload" in event:
                payload = event["sensitive_payload"]
                event["sensitive_payload_hash"] = hashlib.sha256(
                    json.dumps(payload, sort_keys=True).encode()
                ).hexdigest()
                del event["sensitive_payload"]
            
            sanitized.append(event)
        
        return sanitized
    
    def to_replay_bundle(self) -> dict[str, Any]:
        """
        Create a replay bundle containing all data needed for zero-token replay.
        
        The bundle includes:
        - artifact
        - dataset case (if available)
        - fixture snapshot
        - tool responses
        - retrieval snapshot
        - sandbox manifest
        - grader configuration
        - runtime manifest
        """
        return {
            "artifact": self.model_dump(),
            "sanitized_events": self.get_sanitized_events(),
            "final_output": self.final_output,
            "usage": self.usage.model_dump(),
            "cache_key": self.compute_cache_key(),
            "is_replayable": self.is_replayable(),
        }
    
    def validate_integrity(self) -> bool:
        """Validate that the artifact hash matches its content."""
        artifact_dict = self.model_dump()
        stored_hash = artifact_dict.pop("artifact_hash")
        
        artifact_json = json.dumps(artifact_dict, sort_keys=True, default=str)
        computed_hash = f"sha256:{hashlib.sha256(artifact_json.encode()).hexdigest()}"
        
        return stored_hash == computed_hash


class ReplayBundle(BaseModel):
    """Complete bundle for zero-token replay evaluation."""
    artifact: EvaluationArtifact
    dataset_case: dict[str, Any] = Field(default_factory=dict)
    fixture_snapshot: dict[str, Any] = Field(default_factory=dict)
    tool_responses: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_snapshot: dict[str, Any] = Field(default_factory=dict)
    sandbox_manifest: dict[str, Any] = Field(default_factory=dict)
    grader_configuration: dict[str, Any] = Field(default_factory=dict)
    runtime_manifest: dict[str, Any] = Field(default_factory=dict)
    
    def get_replay_metadata(self) -> dict[str, Any]:
        """Get metadata about replay availability and mode."""
        return {
            "replay_available": self.artifact.is_replayable(),
            "replay_mode": "zero-token deterministic",
            "external_model_replay": "unavailable",
            "artifact_id": self.artifact.artifact_id,
            "cache_key": self.artifact.compute_cache_key(),
        }