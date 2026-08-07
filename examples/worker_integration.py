"""Example integration of specialized workers with evaluation runner."""

from glyph.agent_runtime import (
    WorkerCapability,
    WorkerCoordinator,
    WorkerDomain,
    WorkerRegistry,
    WorkerTask,
)
from glyph.agent_runtime.ai_analysis import HybridAIAnalyzer, NoOpAIAnalyzer


def setup_worker_system(use_ai: bool = False):
    """Set up the worker system with default workers."""
    # Create registry and register default workers
    registry = WorkerRegistry()
    expertises = registry.create_default_workers()
    
    # Create coordinator with optional AI analyzer
    ai_analyzer = HybridAIAnalyzer() if use_ai else NoOpAIAnalyzer()
    coordinator = WorkerCoordinator(ai_analyzer=ai_analyzer)
    
    for expertise in expertises:
        coordinator.register_worker(expertise)
    
    return coordinator, registry


async def evaluate_with_workers(target_result, case):
    """Evaluate a target result using specialized workers."""
    coordinator, registry = setup_worker_system()
    
    # Determine domain from case metadata or target result
    domain = determine_domain_from_case(case)
    
    # Create worker task based on domain
    task = create_worker_task(case, target_result, domain)
    
    # Submit to coordinator for routing and execution
    result = await coordinator.submit_task(task)
    
    return result


def determine_domain_from_case(case):
    """Determine the appropriate worker domain from case metadata."""
    # Check case metadata for domain hints
    if "domain" in case.metadata:
        domain_str = case.metadata["domain"]
        try:
            return WorkerDomain(domain_str)
        except ValueError:
            pass
    
    # Infer from suite type
    if case.suite.value == "security":
        return WorkerDomain.SECURITY
    
    # Infer from tags
    if "code" in case.tags:
        return WorkerDomain.CODE_EXECUTION
    if "web" in case.tags:
        return WorkerDomain.WEB_NAVIGATION
    if "api" in case.tags:
        return WorkerDomain.API_INTEGRATION
    if "data" in case.tags:
        return WorkerDomain.DATA_ANALYSIS
    
    # Default to general
    return WorkerDomain.GENERAL


def create_worker_task(case, target_result, domain):
    """Create a worker task from evaluation case and result."""
    # Extract required capabilities based on domain
    capabilities = get_capabilities_for_domain(domain)
    
    # Extract tool calls from target result
    tool_calls = []
    if target_result and hasattr(target_result, 'transcript'):
        # Parse tool calls from transcript
        tool_calls = extract_tool_calls_from_transcript(target_result.transcript)
    
    # Extract metadata requirements
    metadata_requirements = set()
    if target_result and hasattr(target_result, 'outcome_observations'):
        for obs in target_result.outcome_observations:
            metadata_requirements.update(obs.keys())
    
    return WorkerTask(
        task_id=f"{case.id}-worker-eval",
        domain=domain,
        required_capabilities=frozenset(capabilities),
        target_tools=frozenset(tool_calls),
        metadata_requirements=frozenset(metadata_requirements),
        context={
            "case_id": case.id,
            "case_input": case.input,
            "case_expected": case.expected,
        },
    )


def get_capabilities_for_domain(domain):
    """Get required capabilities for a domain."""
    domain_capabilities = {
        WorkerDomain.CODE_EXECUTION: [
            WorkerCapability.CODE_GENERATION,
            WorkerCapability.CODE_DEBUGGING,
        ],
        WorkerDomain.WEB_NAVIGATION: [
            WorkerCapability.WEB_SCRAPING,
            WorkerCapability.WEB_NAVIGATION,
        ],
        WorkerDomain.DATA_ANALYSIS: [
            WorkerCapability.DATA_CLEANING,
            WorkerCapability.DATA_TRANSFORMATION,
        ],
        WorkerDomain.API_INTEGRATION: [
            WorkerCapability.API_AUTHENTICATION,
            WorkerCapability.API_ERROR_HANDLING,
        ],
        WorkerDomain.SECURITY: [
            WorkerCapability.VULNERABILITY_SCANNING,
            WorkerCapability.AUTHORIZATION_CHECKING,
        ],
        WorkerDomain.GENERAL: [
            WorkerCapability.TOOL_SELECTION,
            WorkerCapability.TOOL_COMPOSITION,
        ],
    }
    return domain_capabilities.get(domain, [])


def extract_tool_calls_from_transcript(transcript):
    """Extract tool calls from execution transcript."""
    tool_calls = []
    if not transcript:
        return tool_calls
    
    # Parse transcript for tool calls
    # This is a simplified example - actual implementation would depend on transcript format
    for event in transcript:
        if isinstance(event, dict) and "tool" in event:
            tool_calls.append(event["tool"])
    
    return tool_calls


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def main():
        coordinator, registry = setup_worker_system()
        
        # Print worker status
        print("Registered workers:")
        for worker_id, status in coordinator.get_all_workers_status().items():
            print(f"  {worker_id}: {status['domain']} - {status['capabilities']}")
        
        # Create a sample task
        task = WorkerTask(
            task_id="test-task-001",
            domain=WorkerDomain.CODE_EXECUTION,
            required_capabilities=frozenset([WorkerCapability.CODE_GENERATION]),
            target_tools=frozenset(["python_interpreter"]),
            context={"test": True},
        )
        
        # Route the task
        routing = coordinator.route_task(task)
        print(f"\nTask routing: {routing.selected_worker_id}")
        print(f"Routing reason: {routing.routing_reason}")
        print(f"Confidence: {routing.confidence:.2f}")
    
    asyncio.run(main())
