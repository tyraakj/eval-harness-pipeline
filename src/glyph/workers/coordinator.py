"""Worker coordinator for domain-specific evaluation routing."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from glyph.workers.ai_analysis import AIAnalyzer, AIAnalysisRequest, HybridAIAnalyzer, NoOpAIAnalyzer
from glyph.workers.models import (
    ToolExpertise,
    WorkerDomain,
    WorkerExpertise,
    WorkerResult,
    WorkerRouting,
    WorkerTask,
)


class WorkerCoordinator:
    """Coordinates specialized workers for domain-specific evaluations."""

    def __init__(self, ai_analyzer: AIAnalyzer | None = None) -> None:
        self._workers: dict[str, WorkerExpertise] = {}
        self._worker_queues: dict[str, asyncio.Queue[WorkerTask]] = {}
        self._worker_tasks: dict[str, asyncio.Task[None]] = {}
        self._ai_analyzer = ai_analyzer or HybridAIAnalyzer()

    def register_worker(self, expertise: WorkerExpertise) -> None:
        """Register a worker with its expertise profile."""
        self._workers[expertise.worker_id] = expertise
        self._worker_queues[expertise.worker_id] = asyncio.Queue(
            maxsize=expertise.max_concurrent_tasks
        )

    def unregister_worker(self, worker_id: str) -> None:
        """Unregister a worker."""
        if worker_id in self._workers:
            del self._workers[worker_id]
        if worker_id in self._worker_queues:
            del self._worker_queues[worker_id]
        if worker_id in self._worker_tasks:
            task = self._worker_tasks[worker_id]
            task.cancel()
            del self._worker_tasks[worker_id]

    def route_task(self, task: WorkerTask) -> WorkerRouting:
        """Route a task to the most appropriate worker."""
        candidates = self._find_candidates(task)
        if not candidates:
            raise ValueError(f"No workers available for task {task_id} in domain {task.domain}")

        # Score each candidate based on capability match and expertise
        scored = self._score_candidates(task, candidates)
        best = max(scored, key=lambda x: x[1])
        selected_worker_id, confidence = best

        # Get alternative workers
        alternatives = [wid for wid, _ in scored[:3] if wid != selected_worker_id]

        return WorkerRouting(
            task_id=task.task_id,
            selected_worker_id=selected_worker_id,
            routing_reason=f"Best match with {confidence:.2f} confidence",
            confidence=confidence,
            alternative_workers=alternatives,
        )

    async def submit_task(self, task: WorkerTask) -> WorkerResult:
        """Submit a task to the routed worker and await result."""
        routing = self.route_task(task)
        worker_id = routing.selected_worker_id

        queue = self._worker_queues.get(worker_id)
        if not queue:
            raise ValueError(f"Worker {worker_id} not available")

        await queue.put(task)

        # Start worker task if not already running
        if worker_id not in self._worker_tasks or self._worker_tasks[worker_id].done():
            self._worker_tasks[worker_id] = asyncio.create_task(
                self._worker_loop(worker_id)
            )

        # Wait for result (simplified - in production would use futures/callbacks)
        result = await self._wait_for_result(task.task_id, worker_id)
        return result

    def _find_candidates(self, task: WorkerTask) -> list[str]:
        """Find workers that can handle the task."""
        candidates = []
        for worker_id, expertise in self._workers.items():
            if expertise.domain != task.domain:
                continue

            # Check capability match
            if not task.required_capabilities.issubset(expertise.capabilities):
                continue

            # Check tool expertise
            if task.target_tools:
                has_tool_expertise = any(
                    tool in expertise.tool_expertise for tool in task.target_tools
                )
                if not has_tool_expertise:
                    continue

            candidates.append(worker_id)

        return candidates

    def _score_candidates(
        self, task: WorkerTask, candidates: list[str]
    ) -> list[tuple[str, float]]:
        """Score candidates based on task match."""
        scored = []
        for worker_id in candidates:
            expertise = self._workers[worker_id]
            score = 0.0

            # Capability match score
            if task.required_capabilities:
                match_ratio = len(
                    task.required_capabilities & expertise.capabilities
                ) / len(task.required_capabilities)
                score += match_ratio * 0.4

            # Tool expertise score
            if task.target_tools:
                tool_scores = [
                    expertise.tool_expertise.get(tool, ToolExpertise(tool_name=tool)).expertise_level
                    for tool in task.target_tools
                    if tool in expertise.tool_expertise
                ]
                if tool_scores:
                    score += sum(tool_scores) / len(tool_scores) * 0.3

            # Metadata schema match
            if task.metadata_requirements:
                schema_match = len(
                    task.metadata_requirements & set(expertise.metadata_schemas.keys())
                ) / len(task.metadata_requirements)
                score += schema_match * 0.2

            # Node analysis match
            if task.node_analysis_requirements:
                node_match = len(
                    task.node_analysis_requirements & set(expertise.node_analysis_criteria.keys())
                ) / len(task.node_analysis_requirements)
                score += node_match * 0.1

            scored.append((worker_id, score))

        return scored

    async def _worker_loop(self, worker_id: str) -> None:
        """Worker processing loop."""
        queue = self._worker_queues[worker_id]
        expertise = self._workers[worker_id]

        while True:
            try:
                task = await queue.get()
                result = await self._execute_task(task, expertise)
                # Store result (simplified - would use proper result storage)
                queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error and continue
                print(f"Worker {worker_id} error: {e}")

    async def _execute_task(
        self, task: WorkerTask, expertise: WorkerExpertise
    ) -> WorkerResult:
        """Execute a task with the worker's expertise, optionally using AI."""
        import time

        started_at = time.monotonic()

        # Perform deterministic analysis first
        deterministic_findings = self._deterministic_analysis(task, expertise)

        # Determine if AI analysis would be beneficial
        use_ai = self._should_use_ai(task, expertise)

        ai_analysis = None
        ai_model = None
        ai_confidence = None

        if use_ai:
            ai_request = AIAnalysisRequest(
                task_id=task.task_id,
                domain=expertise.domain.value,
                analysis_type="evaluation",
                data=task.context,
                context={"expertise": expertise.domain.value},
                confidence_threshold=expertise.confidence_threshold,
            )
            ai_response = await self._ai_analyzer.analyze(ai_request)
            ai_analysis = ai_response.analysis
            ai_model = ai_response.model_used
            ai_confidence = ai_response.confidence

        # Combine deterministic and AI analysis
        combined_findings = self._combine_analysis(
            deterministic_findings, ai_analysis, use_ai
        )

        execution_time_ms = int((time.monotonic() - started_at) * 1000)

        return WorkerResult(
            task_id=task.task_id,
            worker_id=expertise.worker_id,
            domain=expertise.domain,
            success=True,
            confidence=ai_confidence if use_ai else expertise.confidence_threshold,
            findings=combined_findings,
            tool_analysis=self._analyze_tools(task, expertise),
            metadata_analysis=self._analyze_metadata(task, expertise),
            node_analysis=self._analyze_nodes(task, expertise),
            recommendations=self._generate_recommendations(combined_findings, expertise),
            execution_time_ms=execution_time_ms,
            ai_analysis_used=use_ai,
            ai_model=ai_model,
            ai_confidence=ai_confidence,
        )

    def _deterministic_analysis(self, task: WorkerTask, expertise: WorkerExpertise) -> dict[str, Any]:
        """Perform deterministic analysis based on rules and expertise."""
        analysis = {
            "method": "deterministic",
            "domain": expertise.domain.value,
            "capabilities_matched": list(task.required_capabilities & expertise.capabilities),
            "tools_available": list(task.target_tools & set(expertise.tool_expertise.keys())),
        }

        # Domain-specific deterministic rules
        if expertise.domain == WorkerDomain.CODE_EXECUTION:
            analysis["code_checks"] = self._code_deterministic_checks(task)
        elif expertise.domain == WorkerDomain.SECURITY:
            analysis["security_checks"] = self._security_deterministic_checks(task)
        elif expertise.domain == WorkerDomain.WEB_NAVIGATION:
            analysis["navigation_checks"] = self._navigation_deterministic_checks(task)

        return analysis

    def _should_use_ai(self, task: WorkerTask, expertise: WorkerExpertise) -> bool:
        """Determine if AI analysis would be beneficial."""
        # Use AI for complex domains or when confidence threshold is high
        complex_domains = {
            WorkerDomain.SECURITY,
            WorkerDomain.REASONING,
            WorkerDomain.GENERAL,
        }

        # Use AI if:
        # 1. Domain is complex
        # 2. High confidence threshold required
        # 3. Task has rich context data
        is_complex = expertise.domain in complex_domains
        high_threshold = expertise.confidence_threshold > 0.8
        rich_context = len(str(task.context)) > 1000

        return is_complex or (high_threshold and rich_context)

    def _combine_analysis(
        self, deterministic: dict[str, Any], ai: dict[str, Any] | None, ai_used: bool
    ) -> dict[str, Any]:
        """Combine deterministic and AI analysis."""
        if not ai_used or not ai:
            return deterministic

        combined = {
            "deterministic": deterministic,
            "ai_enhanced": ai,
            "method": "hybrid",
        }

        # Merge findings
        if "findings" in deterministic and "assessments" in ai:
            combined["findings"] = deterministic["findings"] + ai["assessments"]

        # Add AI recommendations
        if "recommendations" in ai:
            combined["ai_recommendations"] = ai["recommendations"]

        return combined

    def _analyze_tools(self, task: WorkerTask, expertise: WorkerExpertise) -> dict[str, dict[str, Any]]:
        """Analyze tool usage based on expertise."""
        tool_analysis = {}
        for tool in task.target_tools:
            if tool in expertise.tool_expertise:
                tool_exp = expertise.tool_expertise[tool]
                tool_analysis[tool] = {
                    "expertise_level": tool_exp.expertise_level,
                    "supported_operations": list(tool_exp.supported_operations),
                    "known_limitations": list(tool_exp.known_limitations),
                }
        return tool_analysis

    def _analyze_metadata(self, task: WorkerTask, expertise: WorkerExpertise) -> dict[str, Any]:
        """Analyze metadata based on expertise."""
        return {
            "schemas_available": list(expertise.metadata_schemas.keys()),
            "requirements_matched": list(
                task.metadata_requirements & set(expertice.metadata_schemas.keys())
            ),
        }

    def _analyze_nodes(self, task: WorkerTask, expertise: WorkerExpertise) -> dict[str, Any]:
        """Analyze node requirements based on expertise."""
        return {
            "criteria_available": list(expertise.node_analysis_criteria.keys()),
            "requirements_matched": list(
                task.node_analysis_requirements & set(expertise.node_analysis_criteria.keys())
            ),
        }

    def _generate_recommendations(
        self, findings: dict[str, Any], expertise: WorkerExpertise
    ) -> list[str]:
        """Generate recommendations based on findings."""
        recommendations = []

        # Add domain-specific best practices
        for tool_exp in expertise.tool_expertise.values():
            recommendations.extend(tool_exp.best_practices)

        # Add AI recommendations if available
        if "ai_recommendations" in findings:
            recommendations.extend(findings["ai_recommendations"])

        return recommendations[:10]  # Limit to top 10

    def _code_deterministic_checks(self, task: WorkerTask) -> dict[str, Any]:
        """Deterministic checks for code execution."""
        return {
            "syntax_valid": True,  # Would actually check
            "has_error_handling": "error" in task.context.get("code", "").lower(),
            "has_timeout": "timeout" in task.context,
        }

    def _security_deterministic_checks(self, task: WorkerTask) -> dict[str, Any]:
        """Deterministic checks for security."""
        return {
            "has_auth": "auth" in task.context or "token" in task.context,
            "has_validation": "validate" in task.context,
            "has_sanitization": "sanitize" in task.context,
        }

    def _navigation_deterministic_checks(self, task: WorkerTask) -> dict[str, Any]:
        """Deterministic checks for web navigation."""
        return {
            "has_wait": "wait" in task.context,
            "has_error_handling": "error" in task.context,
            "has_timeout": "timeout" in task.context,
        }

    async def _wait_for_result(self, task_id: str, worker_id: str) -> WorkerResult:
        """Wait for a task result (simplified)."""
        # In production, would use proper async result handling
        await asyncio.sleep(0.1)
        return WorkerResult(
            task_id=task_id,
            worker_id=worker_id,
            domain=WorkerDomain.GENERAL,
            success=True,
            confidence=0.8,
            findings={"status": "completed"},
            execution_time_ms=100,
        )

    def get_worker_status(self, worker_id: str) -> dict[str, Any]:
        """Get status of a specific worker."""
        if worker_id not in self._workers:
            return {"status": "not_found"}

        expertise = self._workers[worker_id]
        queue = self._worker_queues[worker_id]
        task = self._worker_tasks.get(worker_id)

        return {
            "worker_id": worker_id,
            "domain": expertise.domain,
            "capabilities": list(expertise.capabilities),
            "queue_size": queue.qsize(),
            "max_concurrent": expertise.max_concurrent_tasks,
            "is_running": task is not None and not task.done(),
        }

    def get_all_workers_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all registered workers."""
        return {
            worker_id: self.get_worker_status(worker_id)
            for worker_id in self._workers
        }
