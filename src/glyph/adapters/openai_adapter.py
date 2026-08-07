"""OpenAI GPT adapter for evaluation targets."""

from __future__ import annotations

from typing import Any

from glyph.core.domain_models import EvalCase, TargetResult
from glyph.security.contracts import Target
from glyph.security.live_sandbox import RunContext


def create_openai_target(
    model: str,
    api_key: str | None = None,
    system_prompt: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    **kwargs: Any,
) -> Target:
    """Create a Target for OpenAI GPT API.
    
    Args:
        model: Model identifier (e.g., gpt-4o, gpt-4-turbo)
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        system_prompt: System prompt for the model
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature
        **kwargs: Additional OpenAI API parameters
        
    Returns:
        Target instance configured for OpenAI
    """
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError(
            "OpenAI SDK not installed. Install with: pip install openai"
        )
    
    client = AsyncOpenAI(api_key=api_key)
    
    class OpenAITarget(Target):
        """OpenAI GPT target implementation."""
        
        @property
        def version(self) -> str:
            return f"openai:{model}"
        
        async def execute(self, case: EvalCase, context: RunContext) -> TargetResult:
            """Invoke OpenAI GPT API."""
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": str(case.input)})
            
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            
            return TargetResult(
                output={
                    "content": response.choices[0].message.content,
                    "model": model,
                    "usage": {
                        "input_tokens": response.usage.prompt_tokens,
                        "output_tokens": response.usage.completion_tokens,
                    },
                },
                trajectory=[],
                outcomes=[],
                retrievals=[],
            )
    
    return OpenAITarget()
