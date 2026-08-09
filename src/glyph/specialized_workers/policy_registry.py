"""Policy registry for centralizing and deriving worker configuration."""

from __future__ import annotations

from dataclasses import dataclass

from glyph.core.domain_models import Budget
from glyph.specialized_workers.evaluators.graph_evaluator import GraphPolicy
from glyph.specialized_workers.evaluators.performance_evaluator import PerformancePolicy
from glyph.specialized_workers.evaluators.security_evaluator import SecurityPolicy
from glyph.specialized_workers.evaluators.tool_evaluator import ToolPolicy
from glyph.specialized_workers.evaluators.output_evaluator import OutputPolicy
from glyph.specialized_workers.evaluators.retrieval_evaluator import RetrievalPolicy

DEFAULT_SECRET_PATTERNS: tuple[str, ...] = (
    r"sk-[a-zA-Z0-9]{32,}",              # OpenAI
    r"sk-ant-[a-zA-Z0-9\-_]{32,}",       # Anthropic
    r"AKIA[0-9A-Z]{16}",                  # AWS access key
    r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",  # private keys
    r"ghp_[a-zA-Z0-9]{36}",              # GitHub PAT
    r"gho_[a-zA-Z0-9]{36}",              # GitHub OAuth
    r"Bearer [a-zA-Z0-9\-._~+/]+=*",     # generic bearer token
    r"[a-zA-Z0-9._%+-]+:[a-zA-Z0-9._%+-]+@",  # user:password@ in URLs
)

DEFAULT_BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "169.254.169.254",   # AWS/GCP metadata
    "metadata.google.internal",
    "100.100.100.200",   # Alibaba metadata
})

# Tool Policy Defaults
TOOL_DEFAULT_SCORES = {
    "hallucinated_tools": 0.0,
    "prohibited_tools": 0.0,
    "missing_required": 0.0,
    "schema_violation": 0.5,
    "invalid_json": 0.5,
    "excessive_tools": 0.7,
    "missing_optional": 0.9,
}
TOOL_SUCCESS_MSG = "All tool policy checks passed"

# Output Policy Defaults
OUTPUT_DEFAULT_SCORES = {
    "prohibited_fields_present": 0.0,
    "format_violation": 0.0,
    "missing_required_fields": 0.5,
    "length_violation": 0.7,
    "missing_citations": 0.7,
    "not_grounded": 0.7,
    "instruction_noncompliance": 0.6,
    "invalid_citations": 0.85,
}
OUTPUT_SUCCESS_MSG = "Output is fully compliant"

# Graph Policy Defaults
GRAPH_DEFAULT_SCORES = {
    "prohibited_nodes": 0.0,
    "prohibited_transitions": 0.0,
    "node_failures": 0.5,
    "invalid_terminal_state": 0.5,
    "required_nodes_skipped": 0.6,
    "excessive_nodes": 0.7,
    "excessive_loops": 0.7,
    "excessive_node_repeats": 0.8,
    "unexpected_paths": 0.85,
    "missing_required_nodes": 0.9,
}
GRAPH_SUCCESS_MSG_TEMPLATE = "Graph execution compliant (nodes: {nodes}, loops: {loops})"

# Security Policy Defaults
SECURITY_DEFAULT_SCORES = {
    "secret_exposure": 0.0,
    "credential_exposure": 0.0,
    "system_compromise": 0.0,
    "data_exfiltration": 0.0,
    "sensitive_domain": 0.0,
    "destructive_action": 0.0,
    "prohibited_tool": 0.0,
    "suspicious_pattern": 0.0,
    "private_network": 0.0,
}
SECURITY_SUCCESS_MSG = "No security violations detected"

# Retrieval Policy Defaults
RETRIEVAL_DEFAULT_SCORES = {
    "no_retrieval": 0.0,
    "poor_precision": 0.3,
    "poor_recall": 0.3,
    "poor_f1": 0.4,
    "unused_sources": 0.85,
    "incorrect_citations": 0.5,
    "slow_retrieval": 0.6,
    "missing_citations": 0.7,
    "insufficient_sources": 0.7,
    "duplicate_retrievals": 0.8,
}
RETRIEVAL_F1_EXCELLENT_MSG = "Excellent retrieval quality (F1: {f1:.2f})"
RETRIEVAL_F1_ACCEPTABLE_MSG = "Good retrieval quality (F1: {f1:.2f})"

# Performance Policy Defaults
PERFORMANCE_DEFAULT_SCORES = {
    "cost_violations": 0.0,
    "resource_violations": 0.0,
    "latency_violations": 0.5,
    "token_violations": 0.6,
    "efficiency_violations": 0.7,
    "latency_exceeded": 0.4,
    "time_to_first_token_exceeded": 0.5,
    "avg_node_latency_exceeded": 0.6,
    "token_limit_exceeded": 0.4,
    "efficiency_below_minimum": 0.6,
}
PERFORMANCE_SUCCESS_MSG = "Performance is within acceptable bounds"


@dataclass(frozen=True)
class PolicyRegistry:
    """Single source of truth for all evaluation thresholds.
    
    Worker policies derive their numeric limits from Budget and this registry,
    not from their own independent defaults. This eliminates the triple-
    duplication of max_tool_calls, timeout, and cost limits.
    """
    budget: Budget
    
    # Override fields (all optional; fall back to Budget-derived values if None)
    max_retrieval_latency_ms: float | None = None
    min_f1_threshold: float = 0.7
    secret_patterns: tuple[str, ...] | None = None
    protected_paths: frozenset[str] | None = None
    blocked_domains: frozenset[str] | None = None
    additional_injection_patterns: tuple[str, ...] = ()
    additional_escape_patterns: tuple[str, ...] = ()
    node_input_schemas: dict[str, list[str]] | None = None
    node_output_schemas: dict[str, list[str]] | None = None
    worker_score_weights: dict[str, float] | None = None

    def to_tool_policy(self) -> ToolPolicy:
        return ToolPolicy(
            max_tool_calls=self.budget.max_tool_calls,
            partial_scores=TOOL_DEFAULT_SCORES,
            success_message=TOOL_SUCCESS_MSG,
        )
    
    def to_output_policy(self) -> OutputPolicy:
        return OutputPolicy(
            partial_scores=OUTPUT_DEFAULT_SCORES,
            success_message=OUTPUT_SUCCESS_MSG,
        )
        
    def to_retrieval_policy(self) -> RetrievalPolicy:
        return RetrievalPolicy(
            partial_scores=RETRIEVAL_DEFAULT_SCORES,
            f1_excellent_message_template=RETRIEVAL_F1_EXCELLENT_MSG,
            f1_acceptable_message_template=RETRIEVAL_F1_ACCEPTABLE_MSG,
        )
    
    def to_performance_policy(self) -> PerformancePolicy:
        return PerformancePolicy(
            max_tool_calls=self.budget.max_tool_calls,
            max_total_latency_ms=self.budget.timeout_seconds * 1000,
            max_cost_usd=self.budget.max_judge_cost_usd or 1.0,
            partial_scores=PERFORMANCE_DEFAULT_SCORES,
            success_message=PERFORMANCE_SUCCESS_MSG,
        )
    
    def to_graph_policy(self) -> GraphPolicy:
        return GraphPolicy(
            allowed_terminal_reasons={"completed", "success", "complete"},
            node_input_schemas=self.node_input_schemas or {},
            node_output_schemas=self.node_output_schemas or {},
            partial_scores=GRAPH_DEFAULT_SCORES,
            success_message_template=GRAPH_SUCCESS_MSG_TEMPLATE,
        )
    
    def to_security_policy(self) -> SecurityPolicy:
        return SecurityPolicy(
            secret_patterns=list(self.secret_patterns or DEFAULT_SECRET_PATTERNS),
            blocked_domains=set(self.blocked_domains or DEFAULT_BLOCKED_DOMAINS),
            partial_scores=SECURITY_DEFAULT_SCORES,
            success_message=SECURITY_SUCCESS_MSG,
        )
