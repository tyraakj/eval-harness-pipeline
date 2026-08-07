"""Output quality evaluator for specialized evaluation."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from glyph.evaluation.specialized_workers.base import (
    BaseArtifactWorker,
    BaseSpecializedWorker,
    EvaluationEvidence,
    GraderMode,
    Severity,
    WorkerResult,
    WorkerType,
)
from glyph.evaluation.specialized_workers.artifact import EvaluationArtifact


@dataclass
class OutputPolicy:
    """Policy configuration for output evaluation."""
    require_json_schema: bool = False
    json_schema: dict[str, Any] | None = None
    required_fields: set[str] = field(default_factory=set)
    prohibited_fields: set[str] = field(default_factory=set)
    require_citations: bool = False
    require_grounding: bool = False
    max_length: int = 100_000
    min_length: int = 1
    allow_markdown: bool = True
    strict_instruction_compliance: bool = True


@dataclass
class OutputAnalysis:
    """Analysis of output quality."""
    is_valid_json: bool
    schema_valid: bool
    required_fields_present: bool
    prohibited_fields_absent: bool
    has_citations: bool
    citations_valid: bool
    is_grounded: bool
    length_compliant: bool
    instruction_compliant: bool
    missing_fields: list[str]
    prohibited_fields_found: list[str]
    schema_errors: list[str]
    validation_errors: list[str]


class OutputEvaluator(BaseSpecializedWorker):
    """Evaluates output quality and schema compliance."""
    
    def __init__(self, version: str = "1.0.0", policy: OutputPolicy | None = None):
        super().__init__(version)
        self.policy = policy or OutputPolicy()
    
    def _get_worker_type(self) -> WorkerType:
        return WorkerType.OUTPUT_QUALITY
    
    def can_evaluate(self, evidence: EvaluationEvidence) -> bool:
        """Can evaluate if there is final output in the evidence."""
        return bool(evidence.final_output)
    
    def evaluate(self, evidence: EvaluationEvidence) -> WorkerResult:
        """Evaluate output quality."""
        evaluation_id = str(uuid.uuid4())
        started_at = time.monotonic()
        
        # Analyze output
        analysis = self._analyze_output(evidence)
        
        # Aggregate findings
        findings = self._aggregate_findings(analysis, evidence)
        
        # Determine overall score and pass/fail
        score, passed, severity, reason_code, reason_message = self._compute_result(
            analysis, findings
        )
        
        # Generate evidence references
        evidence_refs = ["final_output"]
        
        evaluation_duration_ms = int((time.monotonic() - started_at) * 1000)
        
        # Determine grader mode (could be hybrid if AI is used for semantic checks)
        grader_mode = GraderMode.DETERMINISTIC
        
        return self.create_result(
            evaluation_id=evaluation_id,
            trial_id=evidence.trial_id,
            score=score,
            passed=passed,
            severity=severity,
            reason_code=reason_code,
            reason_message=reason_message,
            grader_mode=grader_mode,
            confidence=1.0,
            evidence_refs=evidence_refs,
            findings=findings,
            evaluation_duration_ms=evaluation_duration_ms,
        )
    
    def _analyze_output(self, evidence: EvaluationEvidence) -> OutputAnalysis:
        """Analyze output quality."""
        output = evidence.final_output
        
        # Check if output is valid JSON (if required)
        is_valid_json = True
        schema_valid = True
        schema_errors = []
        
        if self.policy.require_json_schema:
            try:
                if isinstance(output, str):
                    json.loads(output)
                elif isinstance(output, dict):
                    json.dumps(output)
                else:
                    is_valid_json = False
                    schema_errors.append("Output is not a valid JSON-serializable type")
                
                # Validate against schema if provided
                if self.policy.json_schema and is_valid_json:
                    schema_valid, schema_errors = self._validate_json_schema(
                        output, self.policy.json_schema
                    )
            except (json.JSONDecodeError, TypeError) as e:
                is_valid_json = False
                schema_errors.append(f"JSON validation error: {str(e)}")
        
        # Check required fields
        missing_fields = []
        required_fields_present = True
        if self.policy.required_fields:
            if isinstance(output, dict):
                missing_fields = [
                    field for field in self.policy.required_fields
                    if field not in output
                ]
                required_fields_present = len(missing_fields) == 0
            else:
                required_fields_present = False
                missing_fields = list(self.policy.required_fields)
        
        # Check prohibited fields
        prohibited_fields_found = []
        prohibited_fields_absent = True
        if self.policy.prohibited_fields:
            if isinstance(output, dict):
                prohibited_fields_found = [
                    field for field in self.policy.prohibited_fields
                    if field in output
                ]
                prohibited_fields_absent = len(prohibited_fields_found) == 0
            else:
                prohibited_fields_absent = True  # Can't have fields if not a dict
        
        # Check citations
        has_citations = self._has_citations(output)
        citations_valid = self._check_citations_valid(output)
        
        # Check grounding
        is_grounded = self._check_grounding(output, evidence)
        
        # Check length compliance
        output_text = str(output.get("text", output.get("content", ""))) if isinstance(output, dict) else str(output)
        length_compliant = self.policy.min_length <= len(output_text) <= self.policy.max_length
        
        # Check instruction compliance
        instruction_compliant = self._check_instruction_compliance(output, evidence)
        
        # Collect validation errors
        validation_errors = []
        if not is_valid_json:
            validation_errors.append("Invalid JSON format")
        if not required_fields_present:
            validation_errors.append(f"Missing required fields: {missing_fields}")
        if not prohibited_fields_absent:
            validation_errors.append(f"Prohibited fields found: {prohibited_fields_found}")
        if not length_compliant:
            validation_errors.append(f"Length not compliant: {len(output_text)} chars")
        if not has_citations and self.policy.require_citations:
            validation_errors.append("Missing required citations")
        if not is_grounded and self.policy.require_grounding:
            validation_errors.append("Output not grounded in evidence")
        
        return OutputAnalysis(
            is_valid_json=is_valid_json,
            schema_valid=schema_valid,
            required_fields_present=required_fields_present,
            prohibited_fields_absent=prohibited_fields_absent,
            has_citations=has_citations,
            citations_valid=citations_valid,
            is_grounded=is_grounded,
            length_compliant=length_compliant,
            instruction_compliant=instruction_compliant,
            missing_fields=missing_fields,
            prohibited_fields_found=prohibited_fields_found,
            schema_errors=schema_errors,
            validation_errors=validation_errors,
        )
    
    def _validate_json_schema(
        self, output: Any, schema: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Validate output against JSON schema (simplified)."""
        # In production, use jsonschema library for full validation
        errors = []
        
        if not isinstance(output, dict):
            return False, ["Output is not a dictionary"]
        
        # Check required fields in schema
        if "required" in schema:
            required = schema["required"]
            missing = [field for field in required if field not in output]
            if missing:
                errors.append(f"Missing required fields: {missing}")
        
        # Check field types
        if "properties" in schema:
            properties = schema["properties"]
            for field, field_schema in properties.items():
                if field in output:
                    expected_type = field_schema.get("type")
                    if expected_type:
                        actual_type = type(output[field]).__name__
                        # Simple type mapping
                        type_map = {
                            "string": str,
                            "integer": int,
                            "number": (int, float),
                            "boolean": bool,
                            "array": list,
                            "object": dict,
                        }
                        expected_python_type = type_map.get(expected_type, str)
                        if not isinstance(output[field], expected_python_type):
                            errors.append(
                                f"Field '{field}' has wrong type: expected {expected_type}, got {actual_type}"
                            )
        
        return len(errors) == 0, errors
    
    def _has_citations(self, output: Any) -> bool:
        """Check if output contains citations."""
        output_text = str(output.get("text", output.get("content", ""))) if isinstance(output, dict) else str(output)
        
        # Simple citation detection
        return "[" in output_text or "source" in output_text.lower() or "cite" in output_text.lower()
    
    def _check_citations_valid(self, output: Any) -> bool:
        """Check if citations are valid (simplified)."""
        output_text = str(output.get("text", output.get("content", ""))) if isinstance(output, dict) else str(output)
        
        # Check for malformed citations
        import re
        citations = re.findall(r'\[(\d+)\]', output_text)
        
        # Cititions should be properly formatted
        for citation in citations:
            try:
                idx = int(citation)
                if idx < 1:
                    return False
            except ValueError:
                return False
        
        return True
    
    def _check_grounding(self, output: Any, evidence: EvaluationEvidence) -> bool:
        """Check if output is grounded in evidence."""
        # If no retrieval evidence, assume grounded
        if not evidence.retrieval_events:
            return True
        
        # Check if output references retrieved sources
        output_text = str(output.get("text", output.get("content", ""))) if isinstance(output, dict) else str(output)
        
        # Simple grounding check - look for source references
        source_ids = set()
        for event in evidence.retrieval_events:
            source_ids.update(event.get("source_ids", []))
        
        # Check if any source IDs appear in output
        for source_id in source_ids:
            if source_id.lower() in output_text.lower():
                return True
        
        # If citations are present, consider it grounded
        if self._has_citations(output):
            return True
        
        return False
    
    def _check_instruction_compliance(self, output: Any, evidence: EvaluationEvidence) -> bool:
        """Check if output complies with instructions (simplified)."""
        # In production, this might use AI for semantic understanding
        # For now, check basic constraints
        
        # Check if output is empty when it shouldn't be
        output_text = str(output.get("text", output.get("content", ""))) if isinstance(output, dict) else str(output)
        
        if not output_text.strip():
            return False
        
        # Check for requested format in metadata
        requested_format = evidence.metadata.get("requested_format")
        if requested_format:
            if requested_format == "json" and not self._is_json_like(output):
                return False
            elif requested_format == "markdown" and not self._is_markdown_like(output):
                return False
        
        return True
    
    def _is_json_like(self, output: Any) -> bool:
        """Check if output is JSON-like."""
        return isinstance(output, dict)
    
    def _is_markdown_like(self, output: Any) -> bool:
        """Check if output is markdown-like."""
        output_text = str(output.get("text", output.get("content", ""))) if isinstance(output, dict) else str(output)
        markdown_indicators = ["#", "##", "###", "**", "*", "- ", "1.", "```"]
        return any(indicator in output_text for indicator in markdown_indicators)
    
    def _aggregate_findings(
        self, analysis: OutputAnalysis, evidence: EvaluationEvidence
    ) -> dict[str, Any]:
        """Aggregate output analysis findings."""
        output_text = str(evidence.final_output.get("text", evidence.final_output.get("content", ""))) if isinstance(evidence.final_output, dict) else str(evidence.final_output)
        
        return {
            "is_valid_json": analysis.is_valid_json,
            "schema_valid": analysis.schema_valid,
            "required_fields_present": analysis.required_fields_present,
            "prohibited_fields_absent": analysis.prohibited_fields_absent,
            "has_citations": analysis.has_citations,
            "citations_valid": analysis.citations_valid,
            "is_grounded": analysis.is_grounded,
            "length_compliant": analysis.length_compliant,
            "instruction_compliant": analysis.instruction_compliant,
            "output_length": len(output_text),
            "missing_fields": analysis.missing_fields,
            "prohibited_fields_found": analysis.prohibited_fields_found,
            "schema_errors": analysis.schema_errors,
            "validation_errors": analysis.validation_errors,
            "output_type": type(evidence.final_output).__name__,
        }
    
    def _compute_result(
        self, analysis: OutputAnalysis, findings: dict[str, Any]
    ) -> tuple[float, bool, Severity, str, str]:
        """Compute overall score and pass/fail result."""
        # Critical failures
        if not analysis.prohibited_fields_absent:
            return (
                0.0,
                False,
                Severity.CRITICAL,
                "prohibited_fields_present",
                f"Prohibited fields found: {', '.join(analysis.prohibited_fields_found)}"
            )
        
        # High severity failures
        if self.policy.require_json_schema and not analysis.is_valid_json:
            return (
                0.0,
                False,
                Severity.ERROR,
                "invalid_json",
                f"Output is not valid JSON: {', '.join(analysis.schema_errors)}"
            )
        
        if self.policy.require_json_schema and self.policy.json_schema and not analysis.schema_valid:
            return (
                0.0,
                False,
                Severity.ERROR,
                "schema_violation",
                f"Output violates schema: {', '.join(analysis.schema_errors)}"
            )
        
        if not analysis.required_fields_present:
            return (
                0.5,
                False,
                Severity.ERROR,
                "missing_required_fields",
                f"Missing required fields: {', '.join(analysis.missing_fields)}"
            )
        
        # Medium severity failures
        if not analysis.length_compliant:
            return (
                0.7,
                False,
                Severity.WARNING,
                "length_violation",
                f"Output length {findings['output_length']} not compliant with limits"
            )
        
        if self.policy.require_citations and not analysis.has_citations:
            return (
                0.7,
                False,
                Severity.WARNING,
                "missing_citations",
                "Output missing required citations"
            )
        
        if self.policy.require_grounding and not analysis.is_grounded:
            return (
                0.7,
                False,
                Severity.WARNING,
                "not_grounded",
                "Output not grounded in evidence"
            )
        
        if self.policy.strict_instruction_compliance and not analysis.instruction_compliant:
            return (
                0.6,
                False,
                Severity.WARNING,
                "instruction_noncompliance",
                "Output does not comply with instructions"
            )
        
        # Low severity issues
        if analysis.has_citations and not analysis.citations_valid:
            return (
                0.85,
                False,
                Severity.INFO,
                "invalid_citations",
                "Citations present but invalid format"
            )
        
        # All checks passed
        return (
            1.0,
            True,
            Severity.INFO,
            "output_compliant",
            f"Output compliant (length: {findings['output_length']} chars)"
        )


class ArtifactOutputEvaluator(BaseArtifactWorker, OutputEvaluator):
    """Output quality evaluator that works with immutable artifacts."""
    
    def __init__(self, version: str = "1.0.0", policy: OutputPolicy | None = None):
        BaseArtifactWorker.__init__(self, version)
        OutputEvaluator.__init__(self, version, policy)
    
    def _get_worker_type(self) -> WorkerType:
        return WorkerType.OUTPUT_QUALITY
    
    def can_evaluate_artifact(self, artifact: EvaluationArtifact) -> bool:
        """Can evaluate if artifact has final output."""
        return bool(artifact.final_output)
    
    def evaluate_artifact(self, artifact: EvaluationArtifact) -> WorkerResult:
        """Evaluate artifact by extracting evidence and delegating to base evaluator."""
        evidence = self.extract_evidence_from_artifact(artifact)
        return self.evaluate(evidence)
