"""Anthropic Claude adapter for evaluation targets."""

from __future__ import annotations

from typing import Any

from glyph.core.domain_models import EvalCase, TargetResult
from glyph.security.contracts import Target
from glyph.security.live_sandbox import RunContext


def create_anthropic_target(
    model: str,
    api_key: str | None = None,
    system_prompt: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    **kwargs: Any,
) -> Target:
    """Create a Target for Anthropic Claude API.
    
    Args:
        model: Model identifier (e.g., claude-3-5-sonnet-20240620)
        api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        system_prompt: System prompt for the model
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature
        **kwargs: Additional Anthropic API parameters
        
    Returns:
        Target instance configured for Anthropic
    """
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        raise ImportError(
            "Anthropic SDK not installed. Install with: pip install anthropic"
        )
    
    client = AsyncAnthropic(api_key=api_key)
    
    class AnthropicTarget(Target):
        """Anthropic Claude target implementation."""
        
        @property
        def version(self) -> str:
            return f"anthropic:{model}"
        
        async def execute(self, case: EvalCase, context: RunContext) -> TargetResult:
            """Invoke Anthropic Claude API."""
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": str(case.input)}],
                **kwargs,
            )
            
            return TargetResult(
                output={
                    "content": response.content[0].text,
                    "model": model,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    },
                },
                trajectory=[],
                outcomes=[],
                retrievals=[],
            )
    
    return AnthropicTarget()
