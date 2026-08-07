"""Optional AI-powered analysis for workers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class AIAnalysisRequest(BaseModel):
    """Request for AI-powered analysis."""
    task_id: str
    domain: str
    analysis_type: str
    data: dict[str, Any]
    context: dict[str, Any] = {}
    confidence_threshold: float = 0.7


class AIAnalysisResponse(BaseModel):
    """Response from AI-powered analysis."""
    task_id: str
    success: bool
    analysis: dict[str, Any]
    confidence: float
    model_used: str
    tokens_used: int = 0
    cost_usd: float = 0.0
    error_message: str | None = None


class AIAnalyzer(ABC):
    """Abstract base class for AI analyzers."""

    @abstractmethod
    async def analyze(self, request: AIAnalysisRequest) -> AIAnalysisResponse:
        """Perform AI-powered analysis."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the name of the AI model being used."""
        pass

    @abstractmethod
    def estimate_cost(self, request: AIAnalysisRequest) -> float:
        """Estimate the cost of the analysis in USD."""
        pass


class NoOpAIAnalyzer(AIAnalyzer):
    """No-op analyzer that provides deterministic fallback."""

    async def analyze(self, request: AIAnalysisRequest) -> AIAnalysisResponse:
        """Return deterministic analysis without AI."""
        return AIAnalysisResponse(
            task_id=request.task_id,
            success=True,
            analysis=self._deterministic_analysis(request),
            confidence=1.0,
            model_used="deterministic",
            tokens_used=0,
            cost_usd=0.0,
        )

    def get_model_name(self) -> str:
        return "deterministic"

    def estimate_cost(self, request: AIAnalysisRequest) -> float:
        return 0.0

    def _deterministic_analysis(self, request: AIAnalysisRequest) -> dict[str, Any]:
        """Perform deterministic analysis based on rules."""
        analysis = {
            "method": "deterministic",
            "findings": [],
            "recommendations": [],
        }

        # Domain-specific deterministic analysis
        if request.domain == "code_execution":
            analysis["findings"].append("Code execution completed")
            if "error" in request.data:
                analysis["findings"].append(f"Error detected: {request.data['error']}")
        elif request.domain == "web_navigation":
            analysis["findings"].append("Web navigation traced")
            if "pages_visited" in request.data:
                analysis["findings"].append(f"Pages visited: {len(request.data['pages_visited'])}")
        elif request.domain == "security":
            analysis["findings"].append("Security checks performed")
            if "vulnerabilities" in request.data:
                analysis["findings"].append(f"Vulnerabilities found: {len(request.data['vulnerabilities'])}")

        return analysis


class AnthropicAIAnalyzer(AIAnalyzer):
    """Anthropic Claude-based AI analyzer for complex analysis."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022") -> None:
        self.api_key = api_key
        self.model = model
        self._client = None  # Would initialize Anthropic client

    async def analyze(self, request: AIAnalysisRequest) -> AIAnalysisResponse:
        """Perform AI-powered analysis using Anthropic Claude."""
        if not self._client:
            # Initialize client lazily
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
            except ImportError:
                return AIAnalysisResponse(
                    task_id=request.task_id,
                    success=False,
                    analysis={},
                    confidence=0.0,
                    model_used="none",
                    error_message="Anthropic package not installed",
                )

        try:
            prompt = self._build_prompt(request)
            response = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            analysis = self._parse_response(response)
            return AIAnalysisResponse(
                task_id=request.task_id,
                success=True,
                analysis=analysis,
                confidence=0.8,  # Would extract from response if available
                model_used=self.model,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                cost_usd=self._calculate_cost(response.usage),
            )
        except Exception as e:
            return AIAnalysisResponse(
                task_id=request.task_id,
                success=False,
                analysis={},
                confidence=0.0,
                model_used=self.model,
                error_message=str(e),
            )

    def get_model_name(self) -> str:
        return self.model

    def estimate_cost(self, request: AIAnalysisRequest) -> float:
        """Estimate cost based on input size."""
        # Rough estimation: $3 per million input tokens, $15 per million output tokens
        estimated_input_tokens = len(str(request.data)) // 4  # Rough estimate
        estimated_output_tokens = 500  # Average response
        input_cost = (estimated_input_tokens / 1_000_000) * 3.0
        output_cost = (estimated_output_tokens / 1_000_000) * 15.0
        return input_cost + output_cost

    def _build_prompt(self, request: AIAnalysisRequest) -> str:
        """Build analysis prompt based on domain and type."""
        prompts = {
            "code_execution": self._code_analysis_prompt,
            "web_navigation": self._web_analysis_prompt,
            "security": self._security_analysis_prompt,
            "data_analysis": self._data_analysis_prompt,
        }

        prompt_builder = prompts.get(request.domain, self._general_analysis_prompt)
        return prompt_builder(request)

    def _code_analysis_prompt(self, request: AIAnalysisRequest) -> str:
        return f"""Analyze this code execution for quality, correctness, and potential issues:

Context: {request.context}
Data: {request.data}

Provide:
1. Code quality assessment
2. Potential bugs or issues
3. Performance considerations
4. Security concerns
5. Recommendations for improvement"""

    def _web_analysis_prompt(self, request: AIAnalysisRequest) -> str:
        return f"""Analyze this web navigation execution:

Context: {request.context}
Data: {request.data}

Provide:
1. Navigation efficiency
2. Potential issues with page interactions
3. Error handling assessment
4. Recommendations for improvement"""

    def _security_analysis_prompt(self, request: AIAnalysisRequest) -> str:
        return f"""Analyze this security execution for vulnerabilities:

Context: {request.context}
Data: {request.data}

Provide:
1. Security vulnerability assessment
2. Authorization checks
3. Data exposure risks
4. Recommendations for improvement"""

    def _data_analysis_prompt(self, request: AIAnalysisRequest) -> str:
        return f"""Analyze this data analysis execution:

Context: {request.context}
Data: {request.data}

Provide:
1. Data quality assessment
2. Analysis correctness
3. Potential biases
4. Recommendations for improvement"""

    def _general_analysis_prompt(self, request: AIAnalysisRequest) -> str:
        return f"""Analyze this execution in domain {request.domain}:

Context: {request.context}
Data: {request.data}

Provide:
1. Execution quality assessment
2. Potential issues
3. Recommendations for improvement"""

    def _parse_response(self, response: Any) -> dict[str, Any]:
        """Parse AI response into structured analysis."""
        content = response.content[0].text
        # Simple parsing - would be more sophisticated in production
        return {
            "raw_analysis": content,
            "structured": self._extract_structured_insights(content),
        }

    def _extract_structured_insights(self, text: str) -> dict[str, list[str]]:
        """Extract structured insights from AI response."""
        # Simple extraction based on numbered lists
        insights = {
            "issues": [],
            "recommendations": [],
            "assessments": [],
        }

        lines = text.split("\n")
        for line in lines:
            if line.strip().startswith(("1.", "2.", "3.", "4.", "5.")):
                insights["assessments"].append(line.strip())
            elif "recommend" in line.lower():
                insights["recommendations"].append(line.strip())
            elif "issue" in line.lower() or "bug" in line.lower() or "error" in line.lower():
                insights["issues"].append(line.strip())

        return insights

    def _calculate_cost(self, usage: Any) -> float:
        """Calculate cost based on token usage."""
        input_cost = (usage.input_tokens / 1_000_000) * 3.0
        output_cost = (usage.output_tokens / 1_000_000) * 15.0
        return input_cost + output_cost


class HybridAIAnalyzer(AIAnalyzer):
    """Hybrid analyzer that uses AI when beneficial, falls back to deterministic."""

    def __init__(self, ai_analyzer: AIAnalyzer | None = None, cost_threshold: float = 0.01) -> None:
        self.ai_analyzer = ai_analyzer or NoOpAIAnalyzer()
        self.cost_threshold = cost_threshold

    async def analyze(self, request: AIAnalysisRequest) -> AIAnalysisResponse:
        """Use AI if cost-effective, otherwise use deterministic."""
        estimated_cost = self.ai_analyzer.estimate_cost(request)

        if estimated_cost > self.cost_threshold and request.confidence_threshold < 0.9:
            # Use AI for complex analysis
            return await self.ai_analyzer.analyze(request)
        else:
            # Use deterministic for simple/cheap analysis
            fallback = NoOpAIAnalyzer()
            return await fallback.analyze(request)

    def get_model_name(self) -> str:
        return f"hybrid({self.ai_analyzer.get_model_name()})"

    def estimate_cost(self, request: AIAnalysisRequest) -> float:
        return min(self.ai_analyzer.estimate_cost(request), self.cost_threshold)
