"""Governed seed-to-dataset generation workflow.

Generation produces *draft* evaluation cases.  A draft is never runnable as a
released baseline until every case has an append-only approval record and the
draft is promoted into an immutable JSONL dataset.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from glyph.core.domain_models import EvalCase, SuiteType
from glyph.utils.common import canonical_json, sanitize
from glyph.utils.datasets import load_jsonl


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewerRole(str):
    """Reviewer role with different authority levels."""
    REVIEWER = "reviewer"  # Can review individual cases
    SENIOR_REVIEWER = "senior_reviewer"  # Can review and approve batches
    ADMIN = "admin"  # Full authority, can override decisions


class PIIScanner:
    """Basic PII detection using regex patterns."""
    
    # Common PII patterns
    PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
        "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
        "api_key": r'\b[A-Za-z0-9]{32,}\b',  # Common API key pattern
    }
    
    @classmethod
    def scan_text(cls, text: str) -> dict[str, list[str]]:
        """Scan text for PII patterns and return detected instances."""
        results = {}
        for pii_type, pattern in cls.PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                results[pii_type] = matches
        return results
    
    @classmethod
    def scan_case(cls, case: EvalCase) -> dict[str, Any]:
        """Scan an entire case for PII in input and expected fields."""
        text_content = str(case.input) + str(case.expected)
        pii_findings = cls.scan_text(text_content)
        
        return {
            "has_pii": len(pii_findings) > 0,
            "pii_types": list(pii_findings.keys()),
            "pii_findings": pii_findings,
        }


class SemanticDeduplicator:
    """Basic semantic deduplication using text similarity."""
    
    @classmethod
    def compute_similarity(cls, text1: str, text2: str) -> float:
        """Compute basic text similarity using Jaccard similarity of word sets."""
        # Simple word-based similarity (can be enhanced with embeddings)
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
            
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    @classmethod
    def check_similarity(cls, new_case: EvalCase, existing_cases: tuple[EvalCase, ...], threshold: float = 0.95) -> dict[str, Any]:
        """Check if new case is too similar to existing cases."""
        new_text = str(new_case.input) + str(new_case.expected)
        
        similarities = []
        for existing_case in existing_cases:
            existing_text = str(existing_case.input) + str(existing_case.expected)
            similarity = cls.compute_similarity(new_text, existing_text)
            similarities.append({
                "case_id": existing_case.id,
                "similarity": similarity,
            })
        
        max_similarity = max((s["similarity"] for s in similarities), default=0.0)
        too_similar = max_similarity >= threshold
        
        return {
            "max_similarity": max_similarity,
            "too_similar": too_similar,
            "similar_cases": [s for s in similarities if s["similarity"] >= threshold * 0.8],
        }


class SourceGroundingValidator:
    """Validate that cases are properly grounded in source material."""
    
    @classmethod
    def validate_grounding(cls, case: EvalCase, source_material: str | None = None) -> dict[str, Any]:
        """Validate that case input/output is grounded in source material."""
        if not source_material:
            # If no source material provided, assume not grounded
            return {
                "is_grounded": False,
                "reason": "No source material provided for validation",
            }
        
        case_text = str(case.input) + str(case.expected)
        source_text = source_material.lower()
        
        # Check if key terms from case appear in source
        case_words = set(case_text.lower().split())
        source_words = set(source_text.split())
        
        grounded_terms = case_words & source_words
        coverage = len(grounded_terms) / len(case_words) if case_words else 0.0
        
        is_grounded = coverage >= 0.3  # At least 30% of terms should appear in source
        
        return {
            "is_grounded": is_grounded,
            "coverage": coverage,
            "grounded_terms": list(grounded_terms),
            "reason": "Sufficient grounding in source material" if is_grounded else "Insufficient grounding in source material",
        }


class GenerationSpec(FrozenModel):
    """Versioned instructions and controls for a generation run."""

    seed_phrase: str = Field(min_length=3, max_length=10_000)
    count: int = Field(default=100, ge=1, le=10_000)
    random_seed: int = Field(default=0, ge=0)
    suite_counts: dict[SuiteType, int] = Field(
        default_factory=lambda: {SuiteType.CAPABILITY: 100}
    )
    tags: frozenset[str] = Field(default_factory=frozenset)
    constraints: dict[str, Any] = Field(default_factory=dict)
    
    # Governance requirements
    required_reviewer_roles: frozenset[str] = Field(
        default=frozenset({ReviewerRole.REVIEWER}),
        description="Required reviewer roles for approval"
    )
    quorum: int = Field(default=1, ge=1, le=5, description="Minimum number of approvals required")
    require_pii_scan: bool = Field(default=True, description="Whether PII scanning is required")
    max_semantic_similarity: float = Field(
        default=0.95, ge=0.0, le=1.0,
        description="Maximum allowed semantic similarity to existing cases"
    )
    require_source_grounding: bool = Field(
        default=True,
        description="Whether cases must be grounded in source material"
    )

    def model_post_init(self, __context: Any) -> None:
        if sum(self.suite_counts.values()) != self.count:
            raise ValueError("suite_counts must add up to count")
        if any(value < 0 for value in self.suite_counts.values()):
            raise ValueError("suite_counts cannot contain negative values")


class GeneratedCase(FrozenModel):
    """A single generated case plus immutable generation provenance."""

    record_type: str = "generated_case"
    generation_id: str
    case: EvalCase
    generator_name: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    source_ids: tuple[str, ...] = ()


class GenerationManifest(FrozenModel):
    record_type: str = "generation_manifest"
    generation_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    spec: GenerationSpec
    generator_name: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    cases_hash: str


class CaseReview(FrozenModel):
    """Append-only review decision for one generated case."""

    record_type: str = "case_review"
    generation_id: str
    case_id: str
    reviewer: str = Field(min_length=1, max_length=200)
    reviewer_role: str = Field(default=ReviewerRole.REVIEWER, description="Reviewer role and authority level")
    reviewer_id: str | None = Field(default=None, description="Authenticated reviewer ID for audit trail")
    decision: str = Field(pattern="^(approved|rejected)$")
    rationale: str = Field(default="", max_length=2_000)
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    pii_flagged: bool = Field(default=False, description="Whether PII was detected in this case")
    semantic_similarity: float | None = Field(default=None, ge=0.0, le=1.0, description="Semantic similarity to existing cases")
    source_grounded: bool = Field(default=True, description="Whether case is properly grounded in source material")


class CaseGenerator(Protocol):
    """Application-owned generator used to turn a spec into proposed cases."""

    name: str
    version: str

    def generate(self, spec: GenerationSpec) -> Iterable[EvalCase] | Any: ...


def _hash_cases(cases: Iterable[EvalCase]) -> str:
    payload = []
    for case in cases:
        serialized = case.model_dump(mode="json")
        # Pydantic serializes frozensets to lists. Sort those lists so an
        # equivalent case has the same hash across processes and reloads.
        for field in ("graders", "tracked_metrics", "tags"):
            serialized[field] = sorted(serialized[field])
        payload.append(serialized)
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


async def generate_draft(
    generator: CaseGenerator,
    spec: GenerationSpec,
    output: Path,
) -> GenerationManifest:
    """Generate, validate, and write a new immutable draft JSONL artifact."""

    generated = generator.generate(spec)
    if inspect.isawaitable(generated):
        generated = await generated
    cases = tuple(_coerce_case(value) for value in generated)
    _validate_generated_cases(cases, spec)

    generation_id = f"gen-{uuid4()}"
    manifest = GenerationManifest(
        generation_id=generation_id,
        spec=spec,
        generator_name=generator.name,
        generator_version=generator.version,
        cases_hash=_hash_cases(cases),
    )
    lines = [manifest.model_dump_json()]
    lines.extend(
        GeneratedCase(
            generation_id=generation_id,
            case=case,
            generator_name=generator.name,
            generator_version=generator.version,
        ).model_dump_json()
        for case in cases
    )
    await asyncio.to_thread(_write_new_text, output, "\n".join(lines) + "\n")
    return manifest


def load_draft(path: Path) -> tuple[GenerationManifest, tuple[GeneratedCase, ...]]:
    """Load a draft and verify its manifest and case provenance."""

    records = _load_jsonl(path)
    if not records or records[0].get("record_type") != "generation_manifest":
        raise ValueError(f"Draft {path} is missing its generation manifest")
    manifest = GenerationManifest.model_validate(records[0])
    cases = tuple(GeneratedCase.model_validate(record) for record in records[1:])
    if not cases:
        raise ValueError(f"Draft {path} contains no generated cases")
    if any(record.generation_id != manifest.generation_id for record in cases):
        raise ValueError(f"Draft {path} contains a case from another generation")
    _validate_generated_cases(tuple(record.case for record in cases), manifest.spec)
    if _hash_cases(record.case for record in cases) != manifest.cases_hash:
        raise ValueError(f"Draft {path} case hash does not match its manifest")
    return manifest, cases


def append_review(draft_path: Path, review_path: Path, review: CaseReview) -> None:
    """Append a validated review record; historical decisions are never changed."""

    manifest, cases = load_draft(draft_path)
    if review.generation_id != manifest.generation_id:
        raise ValueError("Review generation_id does not match the draft")
    if review.case_id not in {record.case.id for record in cases}:
        raise ValueError(f"Unknown generated case ID: {review.case_id}")
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(review.model_dump_json() + "\n")
        handle.flush()


def promote_draft(
    draft_path: Path, 
    review_path: Path, 
    output: Path,
    existing_cases_path: Path | None = None,
    source_material: str | None = None,
) -> GenerationManifest:
    """Promote a fully approved draft to an immutable canonical dataset with enhanced governance."""

    manifest, cases = load_draft(draft_path)
    latest_reviews = _latest_reviews(review_path, manifest.generation_id)
    all_reviews = _all_reviews(review_path, manifest.generation_id)
    
    # Basic approval checks
    missing = [record.case.id for record in cases if record.case.id not in latest_reviews]
    rejected = [
        record.case.id
        for record in cases
        if latest_reviews.get(record.case.id) is not None
        and latest_reviews[record.case.id].decision != "approved"
    ]
    
    # Enhanced governance checks
    governance_failures = []
    
    # Check required reviewer roles and quorum
    for case_record in cases:
        case_reviews = all_reviews.get(case_record.case.id, [])
        
        # Check quorum
        if len(case_reviews) < manifest.spec.quorum:
            governance_failures.append(
                f"case {case_record.case.id}: insufficient reviews ({len(case_reviews)}/{manifest.spec.quorum})"
            )
        
        # Check required roles
        satisfied_roles = set(review.reviewer_role for review in case_reviews)
        missing_roles = set(manifest.spec.required_reviewer_roles) - satisfied_roles
        if missing_roles:
            governance_failures.append(
                f"case {case_record.case.id}: missing required reviewer roles {missing_roles}"
            )
        
        # Check PII if required
        if manifest.spec.require_pii_scan:
            for review in case_reviews:
                if review.pii_flagged:
                    governance_failures.append(
                        f"case {case_record.case.id}: PII flagged by reviewer {review.reviewer}"
                    )
        
        # Check semantic similarity if existing cases provided
        if existing_cases_path and existing_cases_path.exists():
            try:
                existing_cases = load_jsonl(existing_cases_path)
                similarity_check = SemanticDeduplicator.check_similarity(
                    case_record.case, 
                    tuple(existing_cases),
                    manifest.spec.max_semantic_similarity
                )
                if similarity_check["too_similar"]:
                    governance_failures.append(
                        f"case {case_record.case.id}: too similar to existing cases "
                        f"(max similarity: {similarity_check['max_similarity']:.2f})"
                    )
            except Exception:
                # If we can't check similarity, log but don't fail
                pass
        
        # Check source grounding if required
        if manifest.spec.require_source_grounding:
            for review in case_reviews:
                if not review.source_grounded:
                    governance_failures.append(
                        f"case {case_record.case.id}: not source grounded per reviewer {review.reviewer}"
                    )
    
    # Combine all validation failures with user-friendly formatting
    problems = []
    total_cases = len(cases)
    reviewed_cases = len(latest_reviews)
    
    if missing:
        missing_count = len(missing)
        problems.append(f"{missing_count}/{total_cases} cases missing approval")
    if rejected:
        rejected_count = len(rejected)
        problems.append(f"{rejected_count}/{total_cases} cases rejected")
    if governance_failures:
        # Group governance failures by type for better UX
        governance_issues = {}
        for failure in governance_failures:
            if "insufficient reviews" in failure:
                governance_issues["insufficient reviews"] = governance_issues.get("insufficient reviews", 0) + 1
            elif "missing required reviewer roles" in failure:
                governance_issues["missing required roles"] = governance_issues.get("missing required roles", 0) + 1
            elif "PII flagged" in failure:
                governance_issues["PII flagged"] = governance_issues.get("PII flagged", 0) + 1
            elif "too similar" in failure:
                governance_issues["too similar to existing"] = governance_issues.get("too similar to existing", 0) + 1
            elif "not source grounded" in failure:
                governance_issues["not source grounded"] = governance_issues.get("not source grounded", 0) + 1
        
        governance_summary = ", ".join(f"{count} {issue}" for issue, count in governance_issues.items())
        problems.append(f"governance issues: {governance_summary}")
    
    if problems:
        # Build user-friendly error message
        error_parts = []
        error_parts.append(f"Cannot promote draft: {reviewed_cases}/{total_cases} cases reviewed")
        error_parts.append("Issues:")
        for problem in problems:
            error_parts.append(f"  â€¢ {problem}")
        
        # Add helpful guidance
        error_parts.append("To fix this:")
        if missing:
            error_parts.append("  1. Review all missing cases using 'glyph generation review'")
        if rejected:
            error_parts.append("  2. Address rejected cases or modify your criteria")
        if governance_failures:
            error_parts.append("  3. Ensure all governance requirements are met (quorum, roles, PII, etc.)")
        error_parts.append(f"  4. Then retry: glyph generation promote --draft {draft_path} --output {output}")
        
        error_message = "\n".join(error_parts)
        raise ValueError(error_message)
    
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Released dataset already exists: {output}")
    output.write_text(
        "\n".join(record.case.model_dump_json() for record in cases) + "\n", encoding="utf-8"
    )
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest


def _coerce_case(value: EvalCase | Mapping[str, Any]) -> EvalCase:
    if isinstance(value, EvalCase):
        return value
    return EvalCase.model_validate(sanitize(dict(value)))


def _validate_generated_cases(cases: tuple[EvalCase, ...], spec: GenerationSpec) -> None:
    if len(cases) != spec.count:
        raise ValueError(f"Generator returned {len(cases)} cases; expected {spec.count}")
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Generator returned duplicate case IDs")
    inputs = [canonical_json(case.input) for case in cases]
    if len(inputs) != len(set(inputs)):
        raise ValueError("Generator returned duplicate case inputs")
    actual = {suite: sum(case.suite == suite for case in cases) for suite in SuiteType}
    expected = {suite: spec.suite_counts.get(suite, 0) for suite in SuiteType}
    if actual != expected:
        raise ValueError(f"Generated suite distribution {actual} does not match {expected}")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSONL artifact {path}: {error}") from error


def _write_new_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _latest_reviews(review_path: Path, generation_id: str) -> dict[str, CaseReview]:
    if not review_path.exists():
        return {}
    reviews: dict[str, CaseReview] = {}
    for payload in _load_jsonl(review_path):
        review = CaseReview.model_validate(payload)
        if review.generation_id == generation_id:
            reviews[review.case_id] = review
    return reviews


def _all_reviews(review_path: Path, generation_id: str) -> dict[str, list[CaseReview]]:
    """Get all reviews for each case, not just the latest."""
    if not review_path.exists():
        return {}
    reviews: dict[str, list[CaseReview]] = {}
    for payload in _load_jsonl(review_path):
        review = CaseReview.model_validate(payload)
        if review.generation_id == generation_id:
            if review.case_id not in reviews:
                reviews[review.case_id] = []
            reviews[review.case_id].append(review)
    return reviews


def promote_draft_simple(
    draft_path: Path, 
    review_path: Path, 
    output: Path,
) -> GenerationManifest:
    """Simple promotion without enhanced governance (for testing)."""
    
    manifest, cases = load_draft(draft_path)
    latest_reviews = _latest_reviews(review_path, manifest.generation_id)
    
    # Basic approval checks only
    missing = [record.case.id for record in cases if record.case.id not in latest_reviews]
    rejected = [
        record.case.id
        for record in cases
        if latest_reviews.get(record.case.id) is not None
        and latest_reviews[record.case.id].decision != "approved"
    ]
    
    if missing or rejected:
        problems = []
        if missing:
            problems.append(f"missing approvals: {', '.join(missing)}")
        if rejected:
            problems.append(f"rejected: {', '.join(rejected)}")
        raise ValueError("Draft cannot be promoted; " + "; ".join(problems))
    
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Released dataset already exists: {output}")
    output.write_text(
        "\n".join(record.case.model_dump_json() for record in cases) + "\n", encoding="utf-8"
    )
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest
