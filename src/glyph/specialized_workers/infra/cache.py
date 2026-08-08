"""Content-addressed cache for zero-token replay evaluation."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from glyph.specialized_workers.artifact import (
    EvaluationArtifact,
    ExecutionMode,
)

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Entry in the content-addressed cache."""
    cache_key: str
    artifact_id: str
    artifact: EvaluationArtifact
    
    # Dependency hashes
    case_hash: str
    target_version: str
    model_manifest_hash: str
    tool_contract_hash: str
    retriever_hash: str
    fixture_hash: str
    sandbox_hash: str
    
    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    access_count: int = field(default=0)
    last_accessed_at: datetime | None = None
    
    def record_access(self) -> None:
        """Record an access to this cache entry."""
        self.access_count += 1
        self.last_accessed_at = datetime.now(UTC)
    
    def is_compatible_with(
        self,
        target_version: str,
        model_manifest_hash: str,
        tool_contract_hash: str,
        retriever_hash: str,
        fixture_hash: str,
        sandbox_hash: str,
    ) -> bool:
        """
        Check if this cache entry is compatible with the requested execution.
        
        Returns True if all dependency hashes match, meaning the cached
        artifact can be safely reused without re-execution.
        """
        return (
            self.target_version == target_version and
            self.model_manifest_hash == model_manifest_hash and
            self.tool_contract_hash == tool_contract_hash and
            self.retriever_hash == retriever_hash and
            self.fixture_hash == fixture_hash and
            self.sandbox_hash == sandbox_hash
        )


@dataclass
class CacheLookupResult:
    """Result of a cache lookup."""
    hit: bool
    artifact: EvaluationArtifact | None = None
    cache_key: str = ""
    reason: str = ""
    
    # If hit, whether it's compatible
    compatible: bool = False
    
    # If miss or incompatible, what changed
    changed_dependencies: list[str] = field(default_factory=list)


class ContentAddressedCache:
    """
    Content-addressed cache for zero-token replay evaluation.
    
    This cache implements change-aware testing by:
    1. Computing cache keys from all execution dependencies
    2. Storing immutable artifacts by their cache keys
    3. Checking compatibility before reusing cached artifacts
    4. Tracking which dependencies changed to inform execution decisions
    """
    
    def __init__(self):
        # In-memory storage for demonstration
        # In production, this would use Redis or similar
        self._entries: dict[str, CacheEntry] = {}  # cache_key -> CacheEntry
        self._artifact_index: dict[str, str] = {}  # artifact_id -> cache_key
    
    def compute_cache_key(
        self,
        case_hash: str,
        target_version: str,
        model_manifest_hash: str,
        tool_contract_hash: str = "",
        retriever_hash: str = "",
        fixture_hash: str = "",
        sandbox_hash: str = "",
    ) -> str:
        """
        Compute cache key from execution dependencies.
        
        The cache key includes all components that affect execution:
        - case_hash: The test case being executed
        - target_version: Version of the target being tested
        - model_manifest_hash: Model configuration
        - tool_contract_hash: Tool interface definitions
        - retriever_hash: Retrieval system configuration
        - fixture_hash: Test fixtures
        - sandbox_hash: Sandbox environment configuration
        """
        key_parts = [
            case_hash,
            target_version,
            model_manifest_hash,
            tool_contract_hash,
            retriever_hash,
            fixture_hash,
            sandbox_hash,
        ]
        
        # Filter out empty parts and join
        key_string = ":".join(str(part) for part in key_parts if part)
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    def lookup(
        self,
        cache_key: str,
        target_version: str,
        model_manifest_hash: str,
        tool_contract_hash: str = "",
        retriever_hash: str = "",
        fixture_hash: str = "",
        sandbox_hash: str = "",
    ) -> CacheLookupResult:
        """
        Look up an artifact in the cache.
        
        Returns:
            CacheLookupResult with hit status and compatibility information
        """
        entry = self._entries.get(cache_key)
        
        if entry is None:
            return CacheLookupResult(
                hit=False,
                cache_key=cache_key,
                reason="Cache miss: no entry found for this cache key",
            )
        
        # Check compatibility
        is_compatible = entry.is_compatible_with(
            target_version=target_version,
            model_manifest_hash=model_manifest_hash,
            tool_contract_hash=tool_contract_hash,
            retriever_hash=retriever_hash,
            fixture_hash=fixture_hash,
            sandbox_hash=sandbox_hash,
        )
        
        if not is_compatible:
            # Identify what changed
            changed = []
            if entry.target_version != target_version:
                changed.append("target_version")
            if entry.model_manifest_hash != model_manifest_hash:
                changed.append("model_manifest")
            if entry.tool_contract_hash != tool_contract_hash:
                changed.append("tool_contract")
            if entry.retriever_hash != retriever_hash:
                changed.append("retriever")
            if entry.fixture_hash != fixture_hash:
                changed.append("fixture")
            if entry.sandbox_hash != sandbox_hash:
                changed.append("sandbox")
            
            return CacheLookupResult(
                hit=True,
                artifact=entry.artifact,
                cache_key=cache_key,
                compatible=False,
                reason="Cache hit but incompatible: dependencies changed",
                changed_dependencies=changed,
            )
        
        # Cache hit and compatible
        entry.record_access()
        return CacheLookupResult(
            hit=True,
            artifact=entry.artifact,
            cache_key=cache_key,
            compatible=True,
            reason="Cache hit: compatible artifact found",
        )
    
    def store(
        self,
        artifact: EvaluationArtifact,
        case_hash: str,
        tool_contract_hash: str = "",
        retriever_hash: str = "",
    ) -> str:
        """
        Store an artifact in the cache.
        
        Returns:
            The cache key for the stored artifact
        """
        # Compute cache key from artifact
        cache_key = artifact.compute_cache_key()
        
        # Create cache entry
        entry = CacheEntry(
            cache_key=cache_key,
            artifact_id=artifact.artifact_id,
            artifact=artifact,
            case_hash=case_hash,
            target_version=artifact.target_version,
            model_manifest_hash=artifact.model_manifest.compute_hash(),
            tool_contract_hash=tool_contract_hash,
            retriever_hash=retriever_hash,
            fixture_hash=artifact.fixture_hash,
            sandbox_hash=artifact.sandbox_hash,
        )
        
        # Store entry
        self._entries[cache_key] = entry
        self._artifact_index[artifact.artifact_id] = cache_key
        
        logger.info(
            f"Stored artifact {artifact.artifact_id} in cache with key {cache_key}"
        )
        
        return cache_key
    
    def get_by_artifact_id(self, artifact_id: str) -> EvaluationArtifact | None:
        """Get an artifact by its ID."""
        cache_key = self._artifact_index.get(artifact_id)
        if cache_key:
            entry = self._entries.get(cache_key)
            if entry:
                entry.record_access()
                return entry.artifact
        return None
    
    def invalidate_by_artifact_id(self, artifact_id: str) -> bool:
        """Invalidate a cache entry by artifact ID."""
        cache_key = self._artifact_index.get(artifact_id)
        if cache_key and cache_key in self._entries:
            del self._entries[cache_key]
            del self._artifact_index[artifact_id]
            logger.info(f"Invalidated cache entry for artifact {artifact_id}")
            return True
        return False
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self._entries)
        total_accesses = sum(entry.access_count for entry in self._entries.values())
        
        return {
            "total_entries": total_entries,
            "total_accesses": total_accesses,
            "avg_access_per_entry": total_accesses / total_entries if total_entries > 0 else 0,
        }
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._entries.clear()
        self._artifact_index.clear()
        logger.info("Cleared all cache entries")


class CacheRouter:
    """
    Routes execution requests based on cache lookup results.
    
    Implements the change-aware testing logic from the architecture:
    - Cache hit + compatible artifact â†’ replay mode
    - Cache miss or changed dependency â†’ live execution
    """
    
    def __init__(self, cache: ContentAddressedCache):
        self.cache = cache
    
    def route_execution(
        self,
        case_hash: str,
        target_version: str,
        model_manifest_hash: str,
        tool_contract_hash: str = "",
        retriever_hash: str = "",
        fixture_hash: str = "",
        sandbox_hash: str = "",
    ) -> tuple[ExecutionMode, EvaluationArtifact | None, CacheLookupResult]:
        """
        Route execution to live or replay mode based on cache.
        
        Returns:
            (mode, artifact, lookup_result)
        """
        # Compute cache key
        cache_key = self.cache.compute_cache_key(
            case_hash=case_hash,
            target_version=target_version,
            model_manifest_hash=model_manifest_hash,
            tool_contract_hash=tool_contract_hash,
            retriever_hash=retriever_hash,
            fixture_hash=fixture_hash,
            sandbox_hash=sandbox_hash,
        )
        
        # Look up in cache
        lookup_result = self.cache.lookup(
            cache_key=cache_key,
            target_version=target_version,
            model_manifest_hash=model_manifest_hash,
            tool_contract_hash=tool_contract_hash,
            retriever_hash=retriever_hash,
            fixture_hash=fixture_hash,
            sandbox_hash=sandbox_hash,
        )
        
        # Route based on lookup result
        if lookup_result.hit and lookup_result.compatible:
            # Cache hit with compatible artifact â†’ replay mode
            return ExecutionMode.REPLAY, lookup_result.artifact, lookup_result
        else:
            # Cache miss or incompatible â†’ live execution
            return ExecutionMode.LIVE, None, lookup_result
    
    def should_reexecute_on_change(
        self,
        change_type: str,
    ) -> bool:
        """
        Determine if a change type requires re-execution.
        
        Based on the architecture's change-aware testing table:
        - Grader implementation changed: No
        - Release threshold changed: No
        - Dashboard filter changed: No
        - Prompt changed: Yes
        - Model version changed: Yes
        - Tool contract changed: Usually
        - Retrieval index changed: Yes
        - Deterministic grader changed: No
        - Sandbox policy changed: Depends on policy
        - Application code changed: Usually
        """
        reexecute_on_change = {
            # Changes that do NOT require re-execution
            "grader_implementation": False,
            "release_threshold": False,
            "dashboard_filter": False,
            "deterministic_grader": False,
            
            # Changes that DO require re-execution
            "prompt": True,
            "model_version": True,
            "retrieval_index": True,
            
            # Changes that usually require re-execution
            "tool_contract": True,  # Usually yes
            "application_code": True,  # Usually yes
            
            # Changes that depend on policy
            "sandbox_policy": None,  # Depends on policy
        }
        
        return reexecute_on_change.get(change_type, True)  # Default to re-execute