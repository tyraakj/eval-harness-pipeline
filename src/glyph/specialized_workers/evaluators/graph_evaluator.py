"""Graph compliance evaluator for specialized evaluation."""

from __future__ import annotations

import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from glyph.specialized_workers.artifact import EvaluationArtifact
from glyph.specialized_workers.base import (
    BaseArtifactWorker,
    BaseSpecializedWorker,
    EvaluationEvidence,
    GraderMode,
    Severity,
    WorkerResult,
    WorkerType,
)


@dataclass
class GraphPolicy:
    """Policy configuration for graph evaluation."""
    partial_scores: dict[str, float]
    success_message_template: str

    required_nodes: set[str] = field(default_factory=set)
    prohibited_nodes: set[str] = field(default_factory=set)
    required_transitions: set[tuple[str, str]] = field(default_factory=set)
    prohibited_transitions: set[tuple[str, str]] = field(default_factory=set)
    max_node_repeats: int = 3
    max_total_nodes: int = 50
    max_loops: int = 10
    require_terminal_state: bool = True
    allowed_terminal_reasons: set[str] = field(default_factory=lambda: {"success", "completed", "complete"})
    node_input_schemas: dict[str, list[str]] = field(default_factory=dict)
    node_output_schemas: dict[str, list[str]] = field(default_factory=dict)

@dataclass
class NodeAnalysis:
    """Analysis of a single graph node."""
    node_id: str
    node_type: str
    entered: bool
    exited: bool
    duration_ms: float
    error: str | None
    repeat_count: int
    required_inputs_present: bool
    expected_outputs_present: bool


@dataclass
class EdgeAnalysis:
    """Analysis of a single graph edge."""
    from_node: str
    to_node: str
    condition: str | None
    taken: bool
    allowed: bool
    unexpected: bool


@dataclass
class GraphAnalysis:
    """Analysis of overall graph execution."""
    total_nodes: int
    total_edges: int
    terminal_reason: str
    loop_count: int
    required_nodes_visited: set[str]
    prohibited_nodes_visited: set[str]
    required_transitions_taken: set[tuple[str, str]]
    prohibited_transitions_taken: set[tuple[str, str]]
    repeated_nodes: dict[str, int]
    failed_nodes: list[str]
    skipped_nodes: list[str]
    unexpected_paths: list[tuple[str, str]]


class GraphEvaluator(BaseSpecializedWorker):
    """Evaluates LangGraph execution compliance."""
    
    def __init__(self, version: str = "1.0.0", policy: GraphPolicy | None = None):
        super().__init__(version)
        if policy is None:
            raise ValueError("GraphPolicy must be provided")
        self.policy = policy
    
    def _get_worker_type(self) -> WorkerType:
        return WorkerType.GRAPH_COMPLIANCE
    
    def can_evaluate(self, evidence: EvaluationEvidence) -> bool:
        """Can evaluate if there are graph nodes in the evidence."""
        return len(evidence.graph_nodes) > 0
    
    def evaluate(self, evidence: EvaluationEvidence) -> WorkerResult:
        """Evaluate graph execution compliance."""
        evaluation_id = str(uuid.uuid4())
        started_at = time.monotonic()
        
        # Analyze nodes
        node_analyses = self._analyze_nodes(evidence)
        
        # Analyze edges
        edge_analyses = self._analyze_edges(evidence)
        
        # Analyze overall graph execution
        graph_analysis = self._analyze_graph_execution(evidence, node_analyses, edge_analyses)
        
        # Aggregate findings
        findings = self._aggregate_findings(node_analyses, edge_analyses, graph_analysis)
        
        # Determine overall score and pass/fail
        score, passed, severity, reason_code, reason_message = self._compute_result(
            node_analyses, edge_analyses, graph_analysis, findings
        )
        
        # Generate evidence references
        evidence_refs = []
        for i, node in enumerate(evidence.graph_nodes):
            evidence_refs.append(f"node_{node.get('node_id', i)}")
        for i, edge in enumerate(evidence.graph_edges):
            evidence_refs.append(f"edge_{i}")
        
        evaluation_duration_ms = int((time.monotonic() - started_at) * 1000)
        
        return self.create_result(
            evaluation_id=evaluation_id,
            trial_id=evidence.trial_id,
            score=score,
            passed=passed,
            severity=severity,
            reason_code=reason_code,
            reason_message=reason_message,
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=1.0,
            evidence_refs=evidence_refs,
            findings=findings,
            evaluation_duration_ms=evaluation_duration_ms,
        )
    
    def _analyze_nodes(self, evidence: EvaluationEvidence) -> list[NodeAnalysis]:
        """Analyze individual graph nodes."""
        node_counts = Counter(node.get("node_id") for node in evidence.graph_nodes)
        
        analyses = []
        for node in evidence.graph_nodes:
            node_id = node.get("node_id", "unknown")
            node_type = node.get("node_type", "unknown")
            
            # Check if node was entered and exited
            entered = node.get("entered", True)
            exited = node.get("exited", True)
            
            # Get duration
            duration_ms = node.get("duration_ms", 0)
            
            # Check for errors
            error = node.get("error")
            
            # Count repeats
            repeat_count = node_counts[node_id] - 1
            
            # Check required inputs
            inputs = node.get("inputs", {})
            required_inputs_present = self._check_required_inputs(node_type, inputs)
            
            # Check expected outputs
            outputs = node.get("outputs", {})
            expected_outputs_present = self._check_expected_outputs(node_type, outputs)
            
            analyses.append(NodeAnalysis(
                node_id=node_id,
                node_type=node_type,
                entered=entered,
                exited=exited,
                duration_ms=duration_ms,
                error=error,
                repeat_count=repeat_count,
                required_inputs_present=required_inputs_present,
                expected_outputs_present=expected_outputs_present,
            ))
        
        return analyses
    
    def _analyze_edges(self, evidence: EvaluationEvidence) -> list[EdgeAnalysis]:
        """Analyze graph edges."""
        analyses = []
        for edge in evidence.graph_edges:
            from_node = edge.get("from_node", "unknown")
            to_node = edge.get("to_node", "unknown")
            condition = edge.get("condition")
            
            # Check if edge was taken
            taken = edge.get("taken", True)
            
            # Check if transition is allowed
            transition = (from_node, to_node)
            allowed = transition not in self.policy.prohibited_transitions
            if self.policy.required_transitions:
                allowed = (allowed and transition in self.policy.required_transitions) or not self.policy.required_transitions
            
            # Check if transition is unexpected
            unexpected = transition not in self.policy.required_transitions if self.policy.required_transitions else False
            
            analyses.append(EdgeAnalysis(
                from_node=from_node,
                to_node=to_node,
                condition=condition,
                taken=taken,
                allowed=allowed,
                unexpected=unexpected,
            ))
        
        return analyses
    
    def _analyze_graph_execution(
        self,
        evidence: EvaluationEvidence,
        node_analyses: list[NodeAnalysis],
        edge_analyses: list[EdgeAnalysis],
    ) -> GraphAnalysis:
        """Analyze overall graph execution."""
        total_nodes = len(evidence.graph_nodes)
        total_edges = len(evidence.graph_edges)
        
        # Get terminal reason from metadata
        terminal_reason = evidence.metadata.get("terminal_reason", "unknown")
        
        # Count loops (same node visited multiple times)
        loop_count = sum(a.repeat_count for a in node_analyses)
        
        # Check required nodes
        visited_nodes = {a.node_id for a in node_analyses}
        required_nodes_visited = self.policy.required_nodes & visited_nodes
        prohibited_nodes_visited = self.policy.prohibited_nodes & visited_nodes
        
        # Check transitions
        taken_transitions = {
            (a.from_node, a.to_node)
            for a in edge_analyses if a.taken
        }
        required_transitions_taken = self.policy.required_transitions & taken_transitions
        prohibited_transitions_taken = self.policy.prohibited_transitions & taken_transitions
        
        # Count repeated nodes
        repeated_nodes = {
            a.node_id: a.repeat_count
            for a in node_analyses if a.repeat_count > 0
        }
        
        # Find failed nodes
        failed_nodes = [a.node_id for a in node_analyses if a.error]
        
        # Find skipped nodes (required but not visited)
        skipped_nodes = list(self.policy.required_nodes - visited_nodes)
        
        # Find unexpected paths
        unexpected_paths = [
            (a.from_node, a.to_node)
            for a in edge_analyses if a.unexpected
        ]
        
        return GraphAnalysis(
            total_nodes=total_nodes,
            total_edges=total_edges,
            terminal_reason=terminal_reason,
            loop_count=loop_count,
            required_nodes_visited=required_nodes_visited,
            prohibited_nodes_visited=prohibited_nodes_visited,
            required_transitions_taken=required_transitions_taken,
            prohibited_transitions_taken=prohibited_transitions_taken,
            repeated_nodes=repeated_nodes,
            failed_nodes=failed_nodes,
            skipped_nodes=skipped_nodes,
            unexpected_paths=unexpected_paths,
        )
    
    def _check_required_inputs(self, node_type: str, inputs: dict[str, Any]) -> bool:
        """Check if required inputs are present for a node type."""
        # Use policy schemas if configured, else default to old hardcoded schemas for backward compat
        required_inputs = self.policy.node_input_schemas or {
            "tool_call": ["tool_name", "arguments"],
            "decision": ["context"],
            "action": ["type"],
        }
        
        if node_type not in required_inputs:
            return True
        
        return all(key in inputs for key in required_inputs[node_type])
    
    def _check_expected_outputs(self, node_type: str, outputs: dict[str, Any]) -> bool:
        """Check if expected outputs are present for a node type."""
        # Use policy schemas if configured, else default to old hardcoded schemas for backward compat
        expected_outputs = self.policy.node_output_schemas or {
            "tool_call": ["result"],
            "decision": ["next_action"],
            "action": ["status"],
        }
        
        if node_type not in expected_outputs:
            return True
        
        return all(key in outputs for key in expected_outputs[node_type])
    
    def _aggregate_findings(
        self,
        node_analyses: list[NodeAnalysis],
        edge_analyses: list[EdgeAnalysis],
        graph_analysis: GraphAnalysis,
    ) -> dict[str, Any]:
        """Aggregate graph analysis findings."""
        return {
            "total_nodes": graph_analysis.total_nodes,
            "total_edges": graph_analysis.total_edges,
            "terminal_reason": graph_analysis.terminal_reason,
            "loop_count": graph_analysis.loop_count,
            "required_nodes_visited": list(graph_analysis.required_nodes_visited),
            "prohibited_nodes_visited": list(graph_analysis.prohibited_nodes_visited),
            "required_transitions_taken": list(graph_analysis.required_transitions_taken),
            "prohibited_transitions_taken": list(graph_analysis.prohibited_transitions_taken),
            "repeated_nodes": graph_analysis.repeated_nodes,
            "failed_nodes": graph_analysis.failed_nodes,
            "skipped_nodes": graph_analysis.skipped_nodes,
            "unexpected_paths": graph_analysis.unexpected_paths,
            "node_details": [
                {
                    "node_id": a.node_id,
                    "node_type": a.node_type,
                    "entered": a.entered,
                    "exited": a.exited,
                    "duration_ms": a.duration_ms,
                    "error": a.error,
                    "repeat_count": a.repeat_count,
                    "required_inputs_present": a.required_inputs_present,
                    "expected_outputs_present": a.expected_outputs_present,
                }
                for a in node_analyses
            ],
            "edge_details": [
                {
                    "from_node": a.from_node,
                    "to_node": a.to_node,
                    "condition": a.condition,
                    "taken": a.taken,
                    "allowed": a.allowed,
                    "unexpected": a.unexpected,
                }
                for a in edge_analyses
            ]
        }
    
    def _compute_result(
        self,
        node_analyses: list[NodeAnalysis],
        edge_analyses: list[EdgeAnalysis],
        graph_analysis: GraphAnalysis,
        findings: dict[str, Any],
    ) -> tuple[float, bool, Severity, str, str]:
        """Compute overall score and pass/fail result."""
        # Critical failures
        if findings["prohibited_nodes_visited"]:
            return (
                self.policy.partial_scores["prohibited_nodes"],
                False,
                Severity.CRITICAL,
                "prohibited_nodes_visited",
                f"Prohibited nodes visited: {', '.join(findings['prohibited_nodes_visited'])}"
            )
        
        if findings["prohibited_transitions_taken"]:
            return (
                self.policy.partial_scores["prohibited_transitions"],
                False,
                Severity.CRITICAL,
                "prohibited_transitions_taken",
                f"Prohibited transitions taken: {', '.join(str(t) for t in findings['prohibited_transitions_taken'])}"
            )
        
        # High severity failures
        if findings["failed_nodes"]:
            return (
                self.policy.partial_scores["node_failures"],
                False,
                Severity.ERROR,
                "node_failures",
                f"Nodes failed: {', '.join(findings['failed_nodes'])}"
            )
        
        if findings["skipped_nodes"]:
            return (
                self.policy.partial_scores["required_nodes_skipped"],
                False,
                Severity.ERROR,
                "required_nodes_skipped",
                f"Required nodes skipped: {', '.join(findings['skipped_nodes'])}"
            )
        
        # Check terminal state
        if self.policy.require_terminal_state:
            if graph_analysis.terminal_reason not in self.policy.allowed_terminal_reasons:
                return (
                    self.policy.partial_scores["invalid_terminal_state"],
                    False,
                    Severity.ERROR,
                    "invalid_terminal_state",
                    f"Invalid terminal reason: {graph_analysis.terminal_reason}"
                )
        
        # Medium severity failures
        if findings["total_nodes"] > self.policy.max_total_nodes:
            return (
                self.policy.partial_scores["excessive_nodes"],
                False,
                Severity.WARNING,
                "excessive_nodes",
                f"Exceeded maximum nodes: {findings['total_nodes']} > {self.policy.max_total_nodes}"
            )
        
        if graph_analysis.loop_count > self.policy.max_loops:
            return (
                self.policy.partial_scores["excessive_loops"],
                False,
                Severity.WARNING,
                "excessive_loops",
                f"Exceeded maximum loops: {graph_analysis.loop_count} > {self.policy.max_loops}"
            )
        
        # Check for excessive node repeats
        excessive_repeats = {
            node: count
            for node, count in findings["repeated_nodes"].items()
            if count > self.policy.max_node_repeats
        }
        if excessive_repeats:
            return (
                self.policy.partial_scores["excessive_node_repeats"],
                False,
                Severity.WARNING,
                "excessive_node_repeats",
                f"Excessive node repeats: {excessive_repeats}"
            )
        
        # Low severity issues
        if findings["unexpected_paths"]:
            return (
                self.policy.partial_scores["unexpected_paths"],
                False,
                Severity.INFO,
                "unexpected_paths",
                f"Unexpected execution paths: {', '.join(str(p) for p in findings['unexpected_paths'])}"
            )
        
        # Check if all required nodes were visited
        if len(findings["required_nodes_visited"]) < len(self.policy.required_nodes):
            missing = self.policy.required_nodes - set(findings["required_nodes_visited"])
            return (
                self.policy.partial_scores["missing_required_nodes"],
                False,
                Severity.WARNING,
                "missing_required_nodes",
                f"Missing required nodes: {', '.join(missing)}"
            )
        
        # All checks passed
        return (
            1.0,
            True,
            Severity.INFO,
            "graph_compliant",
            self.policy.success_message_template.format(
                nodes=findings['total_nodes'], loops=graph_analysis.loop_count
            ) or "graph_compliant"
        )


class ArtifactGraphEvaluator(BaseArtifactWorker, GraphEvaluator):
    """Graph compliance evaluator that works with immutable artifacts."""
    
    def __init__(self, version: str = "1.0.0", policy: GraphPolicy | None = None):
        BaseArtifactWorker.__init__(self, version)
        GraphEvaluator.__init__(self, version, policy)
    
    def _get_worker_type(self) -> WorkerType:
        return WorkerType.GRAPH_COMPLIANCE
    
    def can_evaluate_artifact(self, artifact: EvaluationArtifact) -> bool:
        """Can evaluate if artifact has graph node events."""
        graph_events = [
            event for event in artifact.events
            if event.get("event_type") == "graph_node"
        ]
        return len(graph_events) > 0
    
    def evaluate_artifact(self, artifact: EvaluationArtifact) -> WorkerResult:
        """Evaluate artifact by extracting evidence and delegating to base evaluator."""
        evidence = self.extract_evidence_from_artifact(artifact)
        return self.evaluate(evidence)
