from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from langchain_core.runnables import RunnableConfig

from glyph.security.contracts import RunContext
from glyph.core.models import (
    EvalCase,
    LoopIteration,
    LoopObservation,
    RetrievalObservation,
    TargetResult,
    TrajectoryEvent,
    TranscriptCapturePolicy,
    Usage,
)
from glyph.utils import canonical_json, content_hash, sanitize


class BudgetExceededError(RuntimeError):
    pass


class TrajectoryCallback(AsyncCallbackHandler):
    raise_error = True

    def __init__(
        self,
        max_tool_calls: int,
        capture_policy: TranscriptCapturePolicy | None = None,
    ) -> None:
        self.events: list[TrajectoryEvent] = []
        self.tool_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.max_tool_calls = max_tool_calls
        self.capture_policy = capture_policy or TranscriptCapturePolicy()
        self.trace_id: str | None = None
        self.transcript_truncated = False
        self._captured_bytes = 0
        self.loop_iterations: list[LoopIteration] = []
        self.retrievals: list[RetrievalObservation] = []
        self._node_starts: dict[UUID, tuple[str, float]] = {}
        self._tool_starts: dict[UUID, float] = {}
        self._model_starts: dict[UUID, float] = {}
        self._first_token_seen: set[UUID] = set()
        self._retrieval_starts: dict[UUID, tuple[str | None, str, float]] = {}

    def _add(
        self,
        kind: str,
        name: str | None,
        data: Mapping[str, Any] | None = None,
        *,
        run_id: UUID | None = None,
        parent_run_id: UUID | None = None,
        duration_ms: int | None = None,
    ) -> None:
        payload = sanitize(data or {})
        payload_bytes = len(canonical_json(payload).encode("utf-8"))
        if payload_bytes > self.capture_policy.max_event_bytes:
            payload = {
                "content_hash": content_hash(canonical_json(payload)),
                "omitted": "event_payload_limit",
                "original_bytes": payload_bytes,
            }
        event = TrajectoryEvent(
            sequence=len(self.events),
            kind=kind,
            name=name,
            duration_ms=duration_ms,
            run_id=str(run_id) if run_id else None,
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            data=payload,
        )
        event_bytes = len(event.model_dump_json().encode("utf-8"))
        if self._captured_bytes + event_bytes > self.capture_policy.max_total_bytes:
            self.transcript_truncated = True
            return
        self.events.append(event)
        self._captured_bytes += event_bytes

    def _tool_payload_allowed(self, name: str | None) -> bool:
        return name is not None and name in self.capture_policy.tool_payload_allowlist

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.max_tool_calls:
            raise BudgetExceededError(f"Tool-call budget exceeded ({self.max_tool_calls})")
        name = serialized.get("name")
        self._tool_starts[run_id] = time.monotonic()
        data = (
            {"input": input_str}
            if self.capture_policy.capture_tool_inputs and self._tool_payload_allowed(name)
            else {"input_hash": content_hash(input_str)}
        )
        self._add(
            "tool_start",
            name,
            data,
            run_id=run_id,
            parent_run_id=kwargs.get("parent_run_id"),
        )

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        name = kwargs.get("name")
        started_at = self._tool_starts.pop(run_id, time.monotonic())
        data = (
            {"output": output}
            if self.capture_policy.capture_tool_outputs and self._tool_payload_allowed(name)
            else {"output_hash": content_hash(canonical_json(sanitize(output)))}
        )
        self._add(
            "tool_end",
            name,
            data,
            run_id=run_id,
            parent_run_id=kwargs.get("parent_run_id"),
            duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
        )

    async def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        started_at = self._tool_starts.pop(run_id, time.monotonic())
        self._add(
            "tool_error",
            kwargs.get("name"),
            {"error_type": type(error).__name__},
            run_id=run_id,
            parent_run_id=kwargs.get("parent_run_id"),
            duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
        )

    async def on_retriever_end(self, documents: Any, *, run_id: UUID, **kwargs: Any) -> None:
        identifiers = []
        for document in documents if isinstance(documents, list) else []:
            metadata = getattr(document, "metadata", {})
            identifiers.append(metadata.get("id") or metadata.get("source") or "unknown")
        self._add(
            "retrieval",
            kwargs.get("name"),
            {"source_ids": identifiers},
            run_id=run_id,
            parent_run_id=kwargs.get("parent_run_id"),
        )
        name, query_hash, started_at = self._retrieval_starts.pop(
            run_id, (kwargs.get("name"), content_hash("unknown"), time.monotonic())
        )
        self.retrievals.append(
            RetrievalObservation(
                name=name,
                query_hash=query_hash,
                source_ids=tuple(str(identifier) for identifier in identifiers),
                duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
            )
        )

    async def on_retriever_start(
        self,
        serialized: dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._retrieval_starts[run_id] = (
            serialized.get("name") or kwargs.get("name"),
            content_hash(query),
            time.monotonic(),
        )

    async def on_retriever_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        name, query_hash, started_at = self._retrieval_starts.pop(
            run_id, (kwargs.get("name"), content_hash("unknown"), time.monotonic())
        )
        self._add(
            "retrieval_error",
            name,
            {"error_type": type(error).__name__, "query_hash": query_hash},
            run_id=run_id,
            parent_run_id=kwargs.get("parent_run_id"),
            duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
        )

    async def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        if self.trace_id is None and kwargs.get("parent_run_id") is None:
            self.trace_id = str(run_id)
        metadata = kwargs.get("metadata") or {}
        node = metadata.get("langgraph_node")
        if node:
            self._node_starts[run_id] = (str(node), time.monotonic())
            self._add(
                "node_start",
                str(node),
                run_id=run_id,
                parent_run_id=kwargs.get("parent_run_id"),
            )

    async def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        started = self._node_starts.pop(run_id, None)
        if started is None:
            return
        node, started_at = started
        self.loop_iterations.append(
            LoopIteration(
                index=len(self.loop_iterations),
                node=node,
                outcome="completed",
                state_hash=content_hash(canonical_json(sanitize(outputs))),
                duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
            )
        )
        self._add(
            "node_end",
            node,
            {"state_hash": self.loop_iterations[-1].state_hash},
            run_id=run_id,
            parent_run_id=kwargs.get("parent_run_id"),
            duration_ms=self.loop_iterations[-1].duration_ms,
        )

    async def on_chain_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        started = self._node_starts.pop(run_id, None)
        if started is None:
            return
        node, started_at = started
        self.loop_iterations.append(
            LoopIteration(
                index=len(self.loop_iterations),
                node=node,
                outcome="error",
                duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
            )
        )
        self._add(
            "node_error",
            node,
            {"error_type": type(error).__name__},
            run_id=run_id,
            parent_run_id=kwargs.get("parent_run_id"),
            duration_ms=self.loop_iterations[-1].duration_ms,
        )

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._model_starts[run_id] = time.monotonic()
        data: dict[str, Any] = {}
        if self.capture_policy.capture_messages:
            data["messages"] = [
                {"role": message.type, "content": message.content}
                for batch in messages
                for message in batch
            ]
        self._add(
            "model_start",
            serialized.get("name") or kwargs.get("name"),
            data,
            run_id=run_id,
            parent_run_id=kwargs.get("parent_run_id"),
        )

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        provider_usage = (response.llm_output or {}).get("token_usage") or (
            response.llm_output or {}
        ).get("usage", {})
        self.input_tokens += int(
            provider_usage.get("input_tokens", provider_usage.get("prompt_tokens", 0)) or 0
        )
        self.output_tokens += int(
            provider_usage.get("output_tokens", provider_usage.get("completion_tokens", 0)) or 0
        )
        data: dict[str, Any] = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }
        if self.capture_policy.capture_messages:
            data["messages"] = [
                {
                    "role": getattr(getattr(generation, "message", None), "type", "assistant"),
                    "content": getattr(
                        getattr(generation, "message", None),
                        "content",
                        getattr(generation, "text", ""),
                    ),
                }
                for batch in response.generations
                for generation in batch
            ]
        self._add(
            "model_end",
            kwargs.get("name"),
            data,
            run_id=run_id,
            parent_run_id=kwargs.get("parent_run_id"),
            duration_ms=max(
                0,
                int((time.monotonic() - self._model_starts.pop(run_id, time.monotonic())) * 1000),
            ),
        )
        self._first_token_seen.discard(run_id)

    async def on_llm_new_token(
        self,
        token: str | list[str | dict[str, Any]],
        *,
        chunk: Any | None = None,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        if run_id not in self._first_token_seen:
            self._first_token_seen.add(run_id)
            started_at = self._model_starts.get(run_id, time.monotonic())
            self._add(
                "model_first_token",
                kwargs.get("name"),
                run_id=run_id,
                parent_run_id=parent_run_id,
                duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
            )
        if self.capture_policy.capture_streaming_chunks:
            self._add(
                "model_chunk",
                kwargs.get("name"),
                {"content": token},
                run_id=run_id,
                parent_run_id=parent_run_id,
            )

    async def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        started_at = self._model_starts.pop(run_id, time.monotonic())
        self._first_token_seen.discard(run_id)
        self._add(
            "model_error",
            kwargs.get("name"),
            {"error_type": type(error).__name__},
            run_id=run_id,
            parent_run_id=kwargs.get("parent_run_id"),
            duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
        )


class LangGraphTarget:
    def __init__(
        self,
        graph: Any,
        *,
        version: str,
        input_builder: Callable[[EvalCase], dict[str, Any]] | None = None,
        output_builder: Callable[[Any], Any] | None = None,
        model_name: str | None = None,
        capture_policy: TranscriptCapturePolicy | None = None,
    ) -> None:
        self._graph = graph
        self._version = version
        self._input_builder = input_builder or (lambda case: dict(case.input))
        self._output_builder = output_builder or (lambda output: output)
        self.model_name = model_name
        self.capture_policy = capture_policy or TranscriptCapturePolicy()

    @property
    def version(self) -> str:
        return self._version

    async def execute(self, case: EvalCase, context: RunContext) -> TargetResult:
        callback = TrajectoryCallback(context.budget.max_tool_calls, self.capture_policy)
        config: RunnableConfig = {
            "callbacks": [callback],
            "configurable": {"thread_id": context.trial_id},
            "metadata": {
                "eval_run_id": context.run_id,
                "eval_trial_id": context.trial_id,
                "eval_case_id": case.id,
                "target_version": self.version,
            },
            "tags": ["evaluation", *sorted(case.tags)],
        }
        output = await self._graph.ainvoke(self._input_builder(case), config=config)
        sanitized_output = sanitize(self._output_builder(output))
        if len(str(sanitized_output)) > context.budget.max_output_chars:
            raise BudgetExceededError(
                f"Output budget exceeded ({context.budget.max_output_chars} characters)"
            )
        return TargetResult(
            output=sanitized_output,
            trajectory=tuple(callback.events),
            transcript_truncated=callback.transcript_truncated,
            loop=LoopObservation(
                iterations=tuple(callback.loop_iterations), terminal_reason="completed"
            ),
            retrievals=tuple(callback.retrievals),
            usage=Usage(
                input_tokens=callback.input_tokens,
                output_tokens=callback.output_tokens,
                tool_calls=callback.tool_calls,
            ),
            trace_id=callback.trace_id,
        )
