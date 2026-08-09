"""Dataset service with versioning and zero-token generation support."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class GenerationMode(StrEnum):
    """Mode for dataset generation."""
    ZERO_TOKEN = "zero_token"  # Templates, grammars, combinatorial
    LLM_BASED = "llm_based"  # LLM-based generation
    HYBRID = "hybrid"  # Combination of both


class DatasetStatus(StrEnum):
    """Status of a dataset."""
    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    APPROVED = "approved"
    FROZEN = "frozen"


@dataclass
class Case:
    """A single test case in a dataset."""
    case_id: str
    case_data: dict[str, Any]
    
    # Metadata
    generation_method: str = "manual"
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    
    # Quality metrics
    complexity_score: float = 0.5  # 0-1
    coverage_tags: list[str] = field(default_factory=list)
    
    # Validation
    is_valid: bool = True
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class DatasetVersion:
    """A versioned dataset."""
    version_id: str
    dataset_name: str
    version: str  # e.g., "v1", "v2"
    
    # Content
    cases: list[Case] = field(default_factory=list)
    
    # Generation
    generation_mode: GenerationMode = GenerationMode.ZERO_TOKEN
    generation_config: dict[str, Any] = field(default_factory=dict)
    
    # Status and timing
    status: DatasetStatus = DatasetStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    generated_at: datetime | None = None
    approved_at: datetime | None = None
    
    # Hash for integrity
    dataset_hash: str = ""
    
    # Metadata
    total_cases: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Cost tracking (for LLM-based generation)
    generation_cost_usd: float = 0.0
    generation_tokens: int = 0
    
    def compute_hash(self) -> str:
        """Compute hash of the dataset for integrity."""
        # Sort cases by case_id for consistent hashing
        sorted_cases = sorted(self.cases, key=lambda c: c.case_id)
        
        dataset_dict = {
            "version_id": self.version_id,
            "dataset_name": self.dataset_name,
            "version": self.version,
            "cases": [
                {
                    "case_id": case.case_id,
                    "case_data": case.case_data,
                }
                for case in sorted_cases
            ],
        }
        
        dataset_json = json.dumps(dataset_dict, sort_keys=True, default=str)
        return f"sha256:{hashlib.sha256(dataset_json.encode()).hexdigest()}"


@dataclass
class GenerationConfig:
    """Configuration for dataset generation."""
    # Generation mode
    mode: GenerationMode = GenerationMode.ZERO_TOKEN
    
    # Zero-token generation settings
    use_templates: bool = True
    use_grammars: bool = False
    use_combinatorial: bool = True
    use_mutation: bool = False
    
    # Template settings
    templates: list[dict[str, Any]] = field(default_factory=list)
    
    # Combinatorial settings
    parameters: dict[str, list[Any]] = field(default_factory=dict)
    
    # Mutation settings
    base_cases: list[str] = field(default_factory=list)
    mutation_rate: float = 0.1
    
    # LLM-based settings
    llm_model: str = "gpt-4"
    llm_prompt_template: str = ""
    max_llm_cases: int = 100
    
    # Quality settings
    target_case_count: int = 50
    deduplicate: bool = True
    validate_schema: bool = True
    
    # Coverage requirements
    required_coverage_tags: list[str] = field(default_factory=list)


class DatasetGenerator:
    """Base class for dataset generation."""
    
    def __init__(self, config: GenerationConfig):
        self.config = config
    
    def generate(self, seed_phrase: str = "") -> list[Case]:
        """Generate test cases based on configuration."""
        if self.config.mode == GenerationMode.ZERO_TOKEN:
            return self._generate_zero_token(seed_phrase)
        elif self.config.mode == GenerationMode.LLM_BASED:
            return self._generate_llm_based(seed_phrase)
        else:
            return self._generate_hybrid(seed_phrase)
    
    def _generate_zero_token(self, seed_phrase: str) -> list[Case]:
        """Generate cases using zero-token methods."""
        cases = []
        
        if self.config.use_templates:
            cases.extend(self._generate_from_templates())
        
        if self.config.use_combinatorial:
            cases.extend(self._generate_combinatorial())
        
        if self.config.use_mutation:
            cases.extend(self._generate_mutations())
        
        return cases
    
    def _generate_from_templates(self) -> list[Case]:
        """Generate cases from templates."""
        cases = []
        
        for i, template in enumerate(self.config.templates):
            case_id = f"template_case_{i}"
            case_data = self._apply_template(template)
            
            cases.append(Case(
                case_id=case_id,
                case_data=case_data,
                generation_method="template",
                generation_metadata={"template": template},
            ))
        
        logger.info(f"Generated {len(cases)} cases from templates")
        return cases
    
    def _apply_template(self, template: dict[str, Any]) -> dict[str, Any]:
        """Apply a template to generate case data."""
        # Simple template substitution
        # In production, would use a proper template engine
        return template.get("case_data", {})
    
    def _generate_combinatorial(self) -> list[Case]:
        """Generate cases using combinatorial parameter generation."""
        import itertools
        
        cases = []
        param_names = list(self.config.parameters.keys())
        param_values = list(self.config.parameters.values())
        
        for i, combination in enumerate(itertools.product(*param_values)):
            case_id = f"combinatorial_case_{i}"
            case_data = dict(zip(param_names, combination))
            
            cases.append(Case(
                case_id=case_id,
                case_data=case_data,
                generation_method="combinatorial",
                generation_metadata={"combination": combination},
            ))
        
        logger.info(f"Generated {len(cases)} combinatorial cases")
        return cases
    
    def _generate_mutations(self) -> list[Case]:
        """Generate cases by mutating existing cases."""
        cases = []
        
        for base_case_id in self.config.base_cases:
            # In production, would load the base case and mutate it
            # For now, create placeholder
            case_id = f"mutation_of_{base_case_id}"
            case_data = {"base_case": base_case_id, "mutated": True}
            
            cases.append(Case(
                case_id=case_id,
                case_data=case_data,
                generation_method="mutation",
                generation_metadata={"base_case": base_case_id},
            ))
        
        logger.info(f"Generated {len(cases)} mutated cases")
        return cases
    
    def _generate_llm_based(self, seed_phrase: str) -> list[Case]:
        """Generate cases using LLM."""
        # TODO: Implement actual LLM-based generation
        # This would call an LLM to generate diverse test cases
        
        logger.warning("LLM-based generation not yet implemented")
        return []
    
    def _generate_hybrid(self, seed_phrase: str) -> list[Case]:
        """Generate cases using hybrid approach."""
        zero_token_cases = self._generate_zero_token(seed_phrase)
        llm_cases = self._generate_llm_based(seed_phrase)
        
        return zero_token_cases + llm_cases


class DatasetService:
    """
    Service for managing versioned datasets.
    
    The dataset service:
    1. Generates cases only when requested
    2. Supports zero-token generation modes
    3. Creates immutable dataset versions
    4. Validates and deduplicates cases
    5. Provides coverage analysis
    """
    
    def __init__(self, storage_manager):
        self.storage = storage_manager
        self._datasets: dict[str, DatasetVersion] = {}  # version_id -> DatasetVersion
        self._approved_datasets: dict[str, str] = {}  # dataset_name -> version_id
    
    def create_dataset(
        self,
        dataset_name: str,
        version: str,
        config: GenerationConfig,
    ) -> DatasetVersion:
        """Create a new dataset version."""
        import uuid
        
        version_id = f"{dataset_name}_{version}_{uuid.uuid4().hex[:8]}"
        
        dataset = DatasetVersion(
            version_id=version_id,
            dataset_name=dataset_name,
            version=version,
            generation_mode=config.mode,
            generation_config=asdict(config),
            status=DatasetStatus.DRAFT,
        )
        
        self._datasets[version_id] = dataset
        
        logger.info(
            f"Created dataset {dataset_name} version {version} "
            f"(version_id={version_id})"
        )
        
        return dataset
    
    def generate_cases(
        self,
        version_id: str,
        seed_phrase: str = "",
    ) -> DatasetVersion:
        """Generate cases for a dataset version."""
        dataset = self._datasets.get(version_id)
        if not dataset:
            raise ValueError(f"Dataset version {version_id} not found")
        
        dataset.status = DatasetStatus.GENERATING
        
        # Create generator
        config = GenerationConfig(**dataset.generation_config)
        generator = DatasetGenerator(config)
        
        # Generate cases
        cases = generator.generate(seed_phrase)
        
        # Validate and deduplicate
        if config.validate_schema:
            cases = self._validate_cases(cases)
        
        if config.deduplicate:
            cases = self._deduplicate_cases(cases)
        
        # Update dataset
        dataset.cases = cases
        dataset.total_cases = len(cases)
        dataset.generated_at = datetime.now(UTC)
        dataset.dataset_hash = dataset.compute_hash()
        dataset.status = DatasetStatus.READY
        
        # Analyze coverage
        coverage = self._analyze_coverage(cases)
        dataset.metadata["coverage"] = coverage
        
        logger.info(
            f"Generated {len(cases)} cases for dataset {version_id}"
        )
        
        return dataset
    
    def approve_dataset(self, version_id: str) -> DatasetVersion:
        """Approve a dataset version, making it immutable."""
        dataset = self._datasets.get(version_id)
        if not dataset:
            raise ValueError(f"Dataset version {version_id} not found")
        
        if dataset.status != DatasetStatus.READY:
            raise ValueError(
                f"Dataset must be in READY status to approve, "
                f"current status: {dataset.status}"
            )
        
        dataset.status = DatasetStatus.APPROVED
        dataset.approved_at = datetime.now(UTC)
        
        # Register as approved for this dataset name
        self._approved_datasets[dataset.dataset_name] = version_id
        
        logger.info(f"Approved dataset version {version_id}")
        
        return dataset
    
    def freeze_dataset(self, version_id: str) -> DatasetVersion:
        """Freeze a dataset version (immutable after approval)."""
        dataset = self.approve_dataset(version_id)
        dataset.status = DatasetStatus.FROZEN
        
        logger.info(f"Froze dataset version {version_id}")
        
        return dataset
    
    def get_approved_version(self, dataset_name: str) -> DatasetVersion | None:
        """Get the approved version for a dataset name."""
        version_id = self._approved_datasets.get(dataset_name)
        if version_id:
            return self._datasets.get(version_id)
        return None
    
    def get_dataset(self, version_id: str) -> DatasetVersion | None:
        """Get a dataset version by ID."""
        return self._datasets.get(version_id)
    
    def get_case(self, version_id: str, case_id: str) -> Case | None:
        """Get a specific case from a dataset."""
        dataset = self.get_dataset(version_id)
        if not dataset:
            return None
        
        for case in dataset.cases:
            if case.case_id == case_id:
                return case
        
        return None
    
    def _validate_cases(self, cases: list[Case]) -> list[Case]:
        """Validate cases against schema."""
        # Simple validation - check required fields
        valid_cases = []
        
        for case in cases:
            case_data = case.case_data
            
            # Check if case has required fields
            if "input" in case_data and "expected_output" in case_data:
                case.is_valid = True
                valid_cases.append(case)
            else:
                case.is_valid = False
                case.validation_errors.append("Missing required fields")
        
        logger.info(
            f"Validated {len(valid_cases)}/{len(cases)} cases"
        )
        
        return valid_cases
    
    def _deduplicate_cases(self, cases: list[Case]) -> list[Case]:
        """Remove duplicate cases."""
        seen = set()
        unique_cases = []
        
        for case in cases:
            # Create a signature for the case
            case_signature = json.dumps(case.case_data, sort_keys=True)
            
            if case_signature not in seen:
                seen.add(case_signature)
                unique_cases.append(case)
        
        logger.info(
            f"Deduplicated {len(unique_cases)}/{len(cases)} cases"
        )
        
        return unique_cases
    
    def _analyze_coverage(self, cases: list[Case]) -> dict[str, Any]:
        """Analyze coverage of the dataset."""
        coverage = {
            "total_cases": len(cases),
            "coverage_tags": {},
            "complexity_distribution": {
                "low": 0,
                "medium": 0,
                "high": 0,
            },
        }
        
        # Count coverage tags
        for case in cases:
            for tag in case.coverage_tags:
                coverage["coverage_tags"][tag] = (
                    coverage["coverage_tags"].get(tag, 0) + 1
                )
            
            # Categorize complexity
            if case.complexity_score < 0.33:
                coverage["complexity_distribution"]["low"] += 1
            elif case.complexity_score < 0.66:
                coverage["complexity_distribution"]["medium"] += 1
            else:
                coverage["complexity_distribution"]["high"] += 1
        
        return coverage
    
    def list_versions(self, dataset_name: str) -> list[DatasetVersion]:
        """List all versions for a dataset."""
        return [
            dataset for dataset in self._datasets.values()
            if dataset.dataset_name == dataset_name
        ]