from __future__ import annotations

import asyncio

import pytest

from glyph.core.domain_models import EvalCase, SuiteType
from glyph.generation import (
    CaseReview,
    GenerationSpec,
    ReviewerRole,
    append_review,
    generate_draft,
    load_draft,
    promote_draft,
)


class FixedGenerator:
    name = "fixed"
    version = "1.0"

    def generate(self, spec: GenerationSpec) -> list[EvalCase]:
        return [
            EvalCase(id="case-1", input={"request": "safe"}, suite=SuiteType.CAPABILITY),
            EvalCase(id="case-2", input={"request": "unsafe"}, suite=SuiteType.SECURITY),
        ]


def test_draft_requires_review_before_promotion(tmp_path) -> None:
    draft = tmp_path / "draft.jsonl"
    reviews = tmp_path / "reviews.jsonl"
    released = tmp_path / "released.jsonl"
    spec = GenerationSpec(
        seed_phrase="support agent",
        count=2,
        suite_counts={SuiteType.CAPABILITY: 1, SuiteType.SECURITY: 1},
    )

    manifest = asyncio.run(generate_draft(FixedGenerator(), spec, draft))
    loaded_manifest, cases = load_draft(draft)
    assert loaded_manifest.generation_id == manifest.generation_id
    assert [record.case.id for record in cases] == ["case-1", "case-2"]

    with pytest.raises(ValueError, match="Cannot promote draft"):
        promote_draft(draft, reviews, released)

    for case in cases:
        append_review(
            draft,
            reviews,
            CaseReview(
                generation_id=manifest.generation_id,
                case_id=case.case.id,
                reviewer="reviewer",
                decision="approved",
            ),
        )
    promote_draft(draft, reviews, released)
    assert [line for line in released.read_text("utf-8").splitlines() if line]
    assert released.with_suffix(".jsonl.manifest.json").exists()


def test_enhanced_governance_with_quorum(tmp_path) -> None:
    """Test that quorum requirements are enforced during promotion."""
    draft = tmp_path / "draft.jsonl"
    reviews = tmp_path / "reviews.jsonl"
    released = tmp_path / "released.jsonl"
    spec = GenerationSpec(
        seed_phrase="support agent",
        count=2,
        suite_counts={SuiteType.CAPABILITY: 1, SuiteType.SECURITY: 1},
        quorum=2,  # Require 2 approvals per case
    )

    manifest = asyncio.run(generate_draft(FixedGenerator(), spec, draft))
    loaded_manifest, cases = load_draft(draft)
    
    # Only one approval per case (insufficient for quorum of 2)
    for case in cases:
        append_review(
            draft,
            reviews,
            CaseReview(
                generation_id=manifest.generation_id,
                case_id=case.case.id,
                reviewer="reviewer1",
                reviewer_role=ReviewerRole.REVIEWER,
                decision="approved",
            ),
        )
    
    with pytest.raises(ValueError, match="Cannot promote draft"):
        promote_draft(draft, reviews, released)
    
    # Add second approval for each case
    for case in cases:
        append_review(
            draft,
            reviews,
            CaseReview(
                generation_id=manifest.generation_id,
                case_id=case.case.id,
                reviewer="reviewer2",
                reviewer_role=ReviewerRole.REVIEWER,
                decision="approved",
            ),
        )
    
    # Now promotion should succeed
    promote_draft(draft, reviews, released)
    assert released.exists()


def test_enhanced_governance_with_required_roles(tmp_path) -> None:
    """Test that required reviewer roles are enforced."""
    draft = tmp_path / "draft.jsonl"
    reviews = tmp_path / "reviews.jsonl"
    released = tmp_path / "released.jsonl"
    spec = GenerationSpec(
        seed_phrase="support agent",
        count=2,
        suite_counts={SuiteType.CAPABILITY: 1, SuiteType.SECURITY: 1},
        required_reviewer_roles=frozenset({ReviewerRole.REVIEWER, ReviewerRole.SENIOR_REVIEWER}),
    )

    manifest = asyncio.run(generate_draft(FixedGenerator(), spec, draft))
    loaded_manifest, cases = load_draft(draft)
    
    # Only regular reviewer approval for both cases (missing senior reviewer)
    for case in cases:
        append_review(
            draft,
            reviews,
            CaseReview(
                generation_id=manifest.generation_id,
                case_id=case.case.id,
                reviewer="reviewer1",
                reviewer_role=ReviewerRole.REVIEWER,
                decision="approved",
            ),
        )
    
    with pytest.raises(ValueError, match=r"Cannot promote draft|governance issues"):
        promote_draft(draft, reviews, released)
    
    # Add senior reviewer approval for both cases
    for case in cases:
        append_review(
            draft,
            reviews,
            CaseReview(
                generation_id=manifest.generation_id,
                case_id=case.case.id,
                reviewer="senior_reviewer",
                reviewer_role=ReviewerRole.SENIOR_REVIEWER,
                decision="approved",
            ),
        )
    
    # Now promotion should succeed
    promote_draft(draft, reviews, released)
    assert released.exists()


def test_pii_scanning_prevents_promotion(tmp_path) -> None:
    """Test that PII-flagged cases prevent promotion when required."""
    draft = tmp_path / "draft_pii.jsonl"
    reviews = tmp_path / "reviews_pii.jsonl"
    released = tmp_path / "released_pii.jsonl"
    spec = GenerationSpec(
        seed_phrase="support agent",
        count=2,
        suite_counts={SuiteType.CAPABILITY: 1, SuiteType.SECURITY: 1},
        require_pii_scan=True,
    )

    manifest = asyncio.run(generate_draft(FixedGenerator(), spec, draft))
    loaded_manifest, cases = load_draft(draft)
    
    # Reviewer flags PII for first case
    append_review(
        draft,
        reviews,
        CaseReview(
            generation_id=manifest.generation_id,
            case_id=cases[0].case.id,
            reviewer="reviewer1",
            reviewer_role=ReviewerRole.REVIEWER,
            decision="approved",
            pii_flagged=True,
        ),
    )
    
    # Add normal approval for second case
    append_review(
        draft,
        reviews,
        CaseReview(
            generation_id=manifest.generation_id,
            case_id=cases[1].case.id,
            reviewer="reviewer1",
            reviewer_role=ReviewerRole.REVIEWER,
            decision="approved",
            pii_flagged=False,
        ),
    )
    
    with pytest.raises(ValueError, match=r"Cannot promote draft|PII flagged"):
        promote_draft(draft, reviews, released)
    
    # Test with PII requirement disabled
    draft2 = tmp_path / "draft_no_pii.jsonl"
    reviews2 = tmp_path / "reviews_no_pii.jsonl"
    released2 = tmp_path / "released_no_pii.jsonl"
    spec_no_pii = GenerationSpec(
        seed_phrase="support agent",
        count=2,
        suite_counts={SuiteType.CAPABILITY: 1, SuiteType.SECURITY: 1},
        require_pii_scan=False,  # Disable PII requirement
    )
    manifest2 = asyncio.run(generate_draft(FixedGenerator(), spec_no_pii, draft2))
    loaded_manifest2, cases2 = load_draft(draft2)
    
    # Add approvals with PII flag but requirement disabled
    for case in cases2:
        append_review(
            draft2,
            reviews2,
            CaseReview(
                generation_id=manifest2.generation_id,
                case_id=case.case.id,
                reviewer="reviewer1",
                reviewer_role=ReviewerRole.REVIEWER,
                decision="approved",
                pii_flagged=True,  # Flagged but requirement disabled
            ),
        )
    
    # Now promotion should succeed with PII requirement disabled
    promote_draft(draft2, reviews2, released2)
    assert released2.exists()
