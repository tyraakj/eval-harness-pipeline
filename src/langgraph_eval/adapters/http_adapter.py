"""HTTP adapter for evaluation targets.

This adapter allows evaluating against any HTTP endpoint that accepts
JSON input and returns JSON output.
"""

from __future__ import annotations

from typing import Any

import httpx
from langgraph_eval.security.contracts import Target


def create_http_target(
    url: str,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    **kwargs: Any,
) -> Target:
    """Create a Target for HTTP endpoint.
    
    Args:
        url: HTTP endpoint URL
        method: HTTP method (GET, POST, etc.)
        headers: HTTP headers to include
        timeout: Request timeout in seconds
        **kwargs: Additional parameters to include in request body
        
    Returns:
        Target instance configured for HTTP endpoint
    """
    class HTTPTarget(Target):
        """HTTP endpoint target implementation."""
        
        @property
        def version(self) -> str:
            return f"http:{url}"
        
        async def __call__(self, input: dict[str, Any]) -> dict[str, Any]:
            """Invoke HTTP endpoint."""
            async with httpx.AsyncClient(timeout=timeout) as client:
                request_kwargs = {
                    "method": method,
                    "url": url,
                    "headers": headers or {},
                }
                
                if method.upper() in ["POST", "PUT", "PATCH"]:
                    request_kwargs["json"] = {**kwargs, **input}
                else:
                    request_kwargs["params"] = {**kwargs, **input}
                
                response = await client.request(**request_kwargs)
                response.raise_for_status()
                
                return response.json()
    
    return HTTPTarget()
