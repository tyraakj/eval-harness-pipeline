"""Integration with LangGraph for node/edge tracing and analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class LangGraphNode:
    """Represents a node in a LangGraph execution."""
    node_id: str
    node_type: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LangGraphEdge:
    """Represents an edge in a LangGraph execution."""
    from_node: str
    to_node: str
    condition: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LangGraphExecution:
    """Complete execution trace of a LangGraph."""
    execution_id: str
    nodes: list[LangGraphNode] = field(default_factory=list)
    edges: list[LangGraphEdge] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    total_duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LangGraphTracer:
    """Traces LangGraph executions for worker analysis."""

    def __init__(self) -> None:
        self._executions: dict[str, LangGraphExecution] = {}
        self._current_execution: LangGraphExecution | None = None

    def start_execution(self, execution_id: str, metadata: dict[str, Any] | None = None) -> LangGraphExecution:
        """Start tracing a new execution."""
        execution = LangGraphExecution(
            execution_id=execution_id,
            metadata=metadata or {}
        )
        self._executions[execution_id] = execution
        self._current_execution = execution
        return execution

    def end_execution(self, execution_id: str) -> LangGraphExecution | None:
        """End tracing for an execution."""
        if execution_id not in self._executions:
            return None

        execution = self._executions[execution_id]
        execution.finished_at = datetime.now(UTC)
        if execution.started_at:
            execution.total_duration_ms = (
                (execution.finished_at - execution.started_at).total_seconds() * 1000
            )

        if self._current_execution and self._current_execution.execution_id == execution_id:
            self._current_execution = None

        return execution

    def add_node(
        self,
        node_id: str,
        node_type: str,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LangGraphNode:
        """Add a node to the current execution."""
        if not self._current_execution:
            raise RuntimeError("No active execution")

        node = LangGraphNode(
            node_id=node_id,
            node_type=node_type,
            inputs=inputs or {},
            outputs=outputs or {},
            metadata=metadata or {},
        )
        self._current_execution.nodes.append(node)
        return node

    def start_node(self, node_id: str, node_type: str, inputs: dict[str, Any] | None = None) -> LangGraphNode:
        """Start tracking a node execution."""
        node = self.add_node(node_id, node_type, inputs)
        node.started_at = datetime.now(UTC)
        return node

    def end_node(
        self,
        node_id: str,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> LangGraphNode | None:
        """End tracking a node execution."""
        if not self._current_execution:
            return None

        for node in self._current_execution.nodes:
            if node.node_id == node_id:
                node.finished_at = datetime.now(UTC)
                if node.started_at:
                    node.duration_ms = (
                        (node.finished_at - node.started_at).total_seconds() * 1000
                    )
                node.outputs = outputs or {}
                node.error = error
                return node

        return None

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        condition: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LangGraphEdge:
        """Add an edge to the current execution."""
        if not self._current_execution:
            raise RuntimeError("No active execution")

        edge = LangGraphEdge(
            from_node=from_node,
            to_node=to_node,
            condition=condition,
            metadata=metadata or {},
        )
        self._current_execution.edges.append(edge)
        return edge

    def get_execution(self, execution_id: str) -> LangGraphExecution | None:
        """Get an execution by ID."""
        return self._executions.get(execution_id)

    def get_current_execution(self) -> LangGraphExecution | None:
        """Get the current active execution."""
        return self._current_execution

    def analyze_execution(self, execution_id: str) -> dict[str, Any]:
        """Analyze an execution for worker insights."""
        execution = self._executions.get(execution_id)
        if not execution:
            return {}

        analysis = {
            "execution_id": execution_id,
            "total_nodes": len(execution.nodes),
            "total_edges": len(execution.edges),
            "total_duration_ms": execution.total_duration_ms,
            "node_types": {},
            "error_nodes": [],
            "slow_nodes": [],
            "tool_calls": [],
            "metadata_patterns": {},
        }

        # Analyze node types
        for node in execution.nodes:
            node_type = node.node_type
            analysis["node_types"][node_type] = analysis["node_types"].get(node_type, 0) + 1

            # Track errors
            if node.error:
                analysis["error_nodes"].append({
                    "node_id": node.node_id,
                    "node_type": node_type,
                    "error": node.error,
                })

            # Track slow nodes (> 1 second)
            if node.duration_ms and node.duration_ms > 1000:
                analysis["slow_nodes"].append({
                    "node_id": node.node_id,
                    "node_type": node_type,
                    "duration_ms": node.duration_ms,
                })

            # Extract tool calls from metadata
            if "tool_calls" in node.metadata:
                analysis["tool_calls"].extend(node.metadata["tool_calls"])

            # Extract metadata patterns
            for key, value in node.metadata.items():
                if key not in analysis["metadata_patterns"]:
                    analysis["metadata_patterns"][key] = set()
                analysis["metadata_patterns"][key].add(type(value).__name__)

        # Convert sets to lists for JSON serialization
        analysis["metadata_patterns"] = {
            k: list(v) for k, v in analysis["metadata_patterns"].items()
        }

        return analysis


class LangGraphWorkerAdapter:
    """Adapts LangGraph executions for worker analysis."""

    def __init__(self, tracer: LangGraphTracer) -> None:
        self.tracer = tracer

    def create_worker_task_from_execution(
        self,
        execution_id: str,
        domain: str,
    ) -> dict[str, Any]:
        """Create a worker task from a LangGraph execution."""
        execution = self.tracer.get_execution(execution_id)
        if not execution:
            return {}

        analysis = self.tracer.analyze_execution(execution_id)

        return {
            "execution_id": execution_id,
            "domain": domain,
            "analysis": analysis,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "inputs": node.inputs,
                    "outputs": node.outputs,
                    "duration_ms": node.duration_ms,
                    "error": node.error,
                    "metadata": node.metadata,
                }
                for node in execution.nodes
            ],
            "edges": [
                {
                    "from_node": edge.from_node,
                    "to_node": edge.to_node,
                    "condition": edge.condition,
                    "metadata": edge.metadata,
                }
                for edge in execution.edges
            ],
        }

    def extract_tool_calls(self, execution_id: str) -> list[dict[str, Any]]:
        """Extract all tool calls from an execution."""
        execution = self.tracer.get_execution(execution_id)
        if not execution:
            return []

        tool_calls = []
        for node in execution.nodes:
            if "tool_calls" in node.metadata:
                for call in node.metadata["tool_calls"]:
                    tool_calls.append({
                        "node_id": node.node_id,
                        "node_type": node.node_type,
                        "tool_name": call.get("tool_name"),
                        "tool_args": call.get("tool_args"),
                        "tool_result": call.get("tool_result"),
                        "timestamp": node.finished_at.isoformat() if node.finished_at else None,
                    })

        return tool_calls

    def extract_metadata_patterns(self, execution_id: str) -> dict[str, list[str]]:
        """Extract metadata patterns from an execution."""
        analysis = self.tracer.analyze_execution(execution_id)
        return analysis.get("metadata_patterns", {})
