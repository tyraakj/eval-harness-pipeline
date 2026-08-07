"""Tests for zero-token replay evaluation architecture."""

import pytest
from datetime import UTC, datetime

from glyph.specialized_workers.artifact import (
    ArtifactStatus,
    EvaluationArtifact,
    ExecutionMode,
    ModelManifest,
    ReplayBundle,
    UsageMetrics,
)
from glyph.specialized_workers.infra.cache import (
    CacheEntry,
    CacheLookupResult,
    CacheRouter,
    ContentAddressedCache,
)
from glyph.specialized_workers.infra.executors import (
    ExecutionContext,
    ExecutionResult,
    LiveExecutor,
    ReplayExecutor,
    RunOrchestrator,
)
from glyph.specialized_workers.infra.storage_interface_layers import (
    InMemoryObjectStorage,
    InMemoryPostgreSQLStorage,
    InMemoryRedisStorage,
    ProgressEvent,
    RunMetadata,
    StorageManager,
)
from glyph.specialized_workers.evaluators.baseline_evaluator import (
    BaselineComparator,
    BaselineRun,
    BaselineService,
    CandidateRun,
    CandidateService,
    ComparisonResult,
)
from glyph.specialized_workers.grader_router import (
    GraderRouter,
    RoutingCriteria,
    RoutingDecision,
    SelectiveEvaluationPipeline,
)
from glyph.specialized_workers.worker_dataset_service import (
    Case,
    DatasetGenerator,
    DatasetService,
    DatasetStatus,
    DatasetVersion,
    GenerationConfig,
    GenerationMode,
)
from glyph.specialized_workers.gates.ai_decision_gates import (
    AIJudgeGateChain,
    AIJudgeInvocationConfig,
    AIJudgeResult,
    ConfidenceControlGate,
    CostControlGate,
    DecisionGate,
    GateDecision,
    GateResult,
    GateType,
    PostResultGate,
    PreInvocationGate,
    QualityControlGate,
)


class TestEvaluationArtifact:
    """Tests for immutable EvaluationArtifact."""
    
    def test_create_artifact(self):
        """Test creating an immutable artifact."""
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="git:abc123",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        assert artifact.artifact_id.startswith("artifact_")
        assert artifact.mode == ExecutionMode.LIVE
        assert artifact.status == ArtifactStatus.COMPLETED
        assert artifact.usage.total_tokens == 150
    
    def test_artifact_immutability(self):
        """Test that artifacts are immutable."""
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="git:abc123",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        # Attempting to modify should fail due to frozen model
        with pytest.raises(Exception):  # ValidationError or similar
            artifact.case_id = "new_case"
    
    def test_artifact_integrity_validation(self):
        """Test artifact integrity validation."""
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="git:abc123",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        assert artifact.validate_integrity() is True
    
    def test_artifact_replayable(self):
        """Test artifact replayability check."""
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="git:abc123",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[{"event_type": "tool_call"}],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        assert artifact.is_replayable() is True


class TestContentAddressedCache:
    """Tests for content-addressed cache."""
    
    def test_cache_key_generation(self):
        """Test cache key generation from dependencies."""
        cache = ContentAddressedCache()
        
        cache_key = cache.compute_cache_key(
            case_hash="case_123",
            target_version="v1.0",
            model_manifest_hash="model_456",
            tool_contract_hash="tool_789",
            retriever_hash="retriever_012",
            fixture_hash="fixture_345",
            sandbox_hash="sandbox_678",
        )
        
        assert isinstance(cache_key, str)
        assert len(cache_key) == 64  # SHA256 hex length
    
    def test_cache_hit_compatible(self):
        """Test cache hit with compatible artifact."""
        cache = ContentAddressedCache()
        
        # Create and store an artifact
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="v1.0",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        cache.store(artifact, "case_123")
        
        # Lookup with same dependencies
        result = cache.lookup(
            cache_key=artifact.compute_cache_key(),
            target_version="v1.0",
            model_manifest_hash=model_manifest.compute_hash(),
            tool_contract_hash="",
            retriever_hash="",
            fixture_hash="sha256:jkl012",
            sandbox_hash="sha256:ghi789",
        )
        
        assert result.hit is True
        assert result.compatible is True
        assert result.artifact is not None
    
    def test_cache_hit_incompatible(self):
        """Test cache hit with incompatible dependencies."""
        cache = ContentAddressedCache()
        
        # Create and store an artifact
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="v1.0",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        cache.store(artifact, "case_123")
        
        # Lookup with different target version
        result = cache.lookup(
            cache_key=artifact.compute_cache_key(),
            target_version="v2.0",  # Different version
            model_manifest_hash=model_manifest.compute_hash(),
            tool_contract_hash="",
            retriever_hash="",
            fixture_hash="sha256:jkl012",
            sandbox_hash="sha256:ghi789",
        )
        
        assert result.hit is True
        assert result.compatible is False
        assert "target_version" in result.changed_dependencies


class TestExecutors:
    """Tests for live and replay executors."""
    
    def test_live_executor_execution(self):
        """Test live executor creates new artifact."""
        executor = LiveExecutor()
        
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        
        context = ExecutionContext(
            case_id="case_001",
            trial_id="trial_001",
            run_id="run_001",
            target_version="v1.0",
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            model_manifest=model_manifest,
        )
        
        case_data = {"input": "test", "expected_output": {"answer": "test"}}
        
        import asyncio
        result = asyncio.run(executor.execute(context, case_data))
        
        assert result.success is True
        assert result.execution_mode == ExecutionMode.LIVE
        assert result.artifact is not None
        assert result.artifact.mode == ExecutionMode.LIVE
        assert result.target_tokens_used > 0
    
    def test_replay_executor_execution(self):
        """Test replay executor reuses existing artifact."""
        executor = ReplayExecutor()
        
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        # Create an artifact
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="v1.0",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[{"event_type": "tool_call"}],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        context = ExecutionContext(
            case_id="case_001",
            trial_id="trial_001",
            run_id="run_002",
            target_version="v1.0",
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
        )
        
        case_data = {"input": "test", "expected_output": {"answer": "test"}}
        
        import asyncio
        result = asyncio.run(executor.execute(context, case_data, artifact))
        
        assert result.success is True
        assert result.execution_mode == ExecutionMode.REPLAY
        assert result.artifact is not None
        assert result.artifact.mode == ExecutionMode.REPLAY
        assert result.target_tokens_used == 0  # Zero tokens in replay mode
        assert result.cache_hit is True


class TestStorageLayers:
    """Tests for three-tier storage architecture."""
    
    def test_postgresql_storage(self):
        """Test PostgreSQL storage for metadata."""
        storage = InMemoryPostgreSQLStorage()
        
        metadata = RunMetadata(
            run_id="run_001",
            project_id="project_001",
            user_id="user_001",
            target_version="v1.0",
            dataset_version="v1",
            mode="live",
            status="pending",
            created_at=datetime.now(UTC),
        )
        
        storage.store_run_metadata(metadata)
        retrieved = storage.get_run_metadata("run_001")
        
        assert retrieved is not None
        assert retrieved.run_id == "run_001"
        assert retrieved.status == "pending"
    
    def test_object_storage(self):
        """Test object storage for artifacts."""
        storage = InMemoryObjectStorage()
        
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="v1.0",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        storage_key = storage.store_artifact(artifact)
        retrieved = storage.get_artifact(artifact.artifact_id)
        
        assert retrieved is not None
        assert retrieved.artifact_id == artifact.artifact_id
        assert storage.artifact_exists(artifact.artifact_id) is True
    
    def test_redis_storage(self):
        """Test Redis storage for queues and events."""
        storage = InMemoryRedisStorage()
        
        # Test task queuing
        task_data = {"task_type": "evaluation", "data": "test"}
        task_id = storage.enqueue_task("eval.deterministic", task_data)
        
        assert task_id is not None
        
        # Test task dequeuing
        dequeued = storage.dequeue_task("eval.deterministic")
        assert dequeued is not None
        assert dequeued["task_id"] == task_id
        
        # Test progress events
        event = ProgressEvent(
            run_id="run_001",
            trial_id="trial_001",
            event_type="started",
            message="Evaluation started",
        )
        storage.publish_progress_event(event)
        
        events = storage.get_progress_events("run_001")
        assert len(events) == 1
        assert events[0].event_type == "started"
    
    def test_storage_manager(self):
        """Test unified storage manager."""
        manager = StorageManager()
        
        # Test PostgreSQL storage
        metadata = RunMetadata(
            run_id="run_001",
            project_id="project_001",
            user_id="user_001",
            target_version="v1.0",
            dataset_version="v1",
            mode="live",
            status="pending",
            created_at=datetime.now(UTC),
        )
        manager.store_run_metadata(metadata)
        
        # Test object storage
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="v1.0",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        manager.store_artifact(artifact)
        
        # Test Redis storage
        event = ProgressEvent(
            run_id="run_001",
            trial_id="trial_001",
            event_type="started",
            message="Evaluation started",
        )
        manager.publish_progress(event)
        
        # Verify all storage layers work
        assert manager.get_run_metadata("run_001") is not None
        assert manager.get_artifact(artifact.artifact_id) is not None
        assert len(manager.get_progress("run_001")) == 1


class TestBaselineComparison:
    """Tests for baseline and candidate comparison."""
    
    def test_baseline_creation(self):
        """Test creating a baseline run."""
        storage = StorageManager()
        service = BaselineService(storage)
        
        baseline = service.create_baseline(
            run_id="baseline_001",
            target_version="v1.0",
            dataset_version="v1",
            artifact_ids=["artifact_001", "artifact_002"],
            overall_score=0.95,
        )
        
        assert baseline.run_id == "baseline_001"
        assert baseline.mode == "live"
        assert baseline.overall_score == 0.95
    
    def test_candidate_creation(self):
        """Test creating a candidate run."""
        storage = StorageManager()
        service = CandidateService(storage)
        
        candidate = service.create_candidate(
            run_id="candidate_001",
            target_version="v2.0",
            dataset_version="v1",
            mode="replay",
            artifact_ids=["artifact_003", "artifact_004"],
            target_tokens_used=0,
            evaluator_tokens_used=0,
            cache_hits=2,
            cache_misses=0,
        )
        
        assert candidate.run_id == "candidate_001"
        assert candidate.mode == "replay"
        assert candidate.cache_hits == 2
    
    def test_baseline_comparison(self):
        """Test comparing candidate against baseline."""
        storage = StorageManager()
        baseline_service = BaselineService(storage)
        candidate_service = CandidateService(storage)
        
        # Create baseline
        baseline = baseline_service.create_baseline(
            run_id="baseline_001",
            target_version="v1.0",
            dataset_version="v1",
            artifact_ids=["artifact_001"],
            overall_score=0.95,
        )
        
        # Create candidate
        candidate = candidate_service.create_candidate(
            run_id="candidate_001",
            target_version="v2.0",
            dataset_version="v1",
            mode="replay",
            artifact_ids=["artifact_002"],
        )
        
        # Compare
        comparator = BaselineComparator(baseline_service, candidate_service)
        comparison = comparator.compare("baseline_001", "candidate_001")
        
        assert comparison.baseline_run.run_id == "baseline_001"
        assert comparison.candidate_run.run_id == "candidate_001"
        assert comparison.decision in [
            ComparisonResult.PASSED,
            ComparisonResult.BLOCKED,
            ComparisonResult.INCONCLUSIVE,
            ComparisonResult.NOT_COMPARABLE,
        ]


class TestGraderRouter:
    """Tests for grader router and selective evaluation."""
    
    def test_route_security_violation(self):
        """Test routing critical security violations to block."""
        cache = ContentAddressedCache()
        router = GraderRouter(
            deterministic_workers=[],
            ai_judge_available=True,
        )
        
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="v1.0",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[{"event_type": "security", "severity": "critical"}],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        result = router.route_trial(artifact)
        
        assert result.decision == RoutingDecision.BLOCK
        assert result.requires_model_call is False
    
    def test_route_semantic_difference(self):
        """Test routing semantic differences to AI judge."""
        cache = ContentAddressedCache()
        router = GraderRouter(
            deterministic_workers=[],
            ai_judge_available=True,
        )
        
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="v1.0",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        criteria = RoutingCriteria(
            behavioral_change_detected=True,
            semantic_difference_score=0.8,  # High difference
        )
        
        result = router.route_trial(artifact, criteria)
        
        assert result.decision == RoutingDecision.INVOKE_SMALL_JUDGE
        assert result.requires_model_call is True


class TestDatasetService:
    """Tests for dataset service with versioning."""
    
    def test_dataset_creation(self):
        """Test creating a dataset version."""
        storage = StorageManager()
        service = DatasetService(storage)
        
        config = GenerationConfig(
            mode=GenerationMode.ZERO_TOKEN,
            target_case_count=10,
            use_templates=True,
            templates=[
                {
                    "case_data": {"input": "test {{i}}", "expected_output": "result {{i}}"}
                }
            ],
        )
        
        dataset = service.create_dataset(
            dataset_name="test_dataset",
            version="v1",
            config=config,
        )
        
        assert dataset.dataset_name == "test_dataset"
        assert dataset.version == "v1"
        assert dataset.status == DatasetStatus.DRAFT
    
    def test_zero_token_generation(self):
        """Test zero-token dataset generation."""
        storage = StorageManager()
        service = DatasetService(storage)
        
        config = GenerationConfig(
            mode=GenerationMode.ZERO_TOKEN,
            target_case_count=5,
            use_combinatorial=True,
            parameters={
                "param1": ["a", "b"],
                "param2": [1, 2],
            },
        )
        
        dataset = service.create_dataset(
            dataset_name="test_dataset",
            version="v1",
            config=config,
        )
        
        dataset = service.generate_cases(dataset.version_id)
        
        assert dataset.status == DatasetStatus.READY
        assert len(dataset.cases) > 0
        assert dataset.total_cases == len(dataset.cases)
    
    def test_dataset_approval(self):
        """Test dataset approval and freezing."""
        storage = StorageManager()
        service = DatasetService(storage)
        
        config = GenerationConfig(
            mode=GenerationMode.ZERO_TOKEN,
            target_case_count=5,
            use_templates=True,
            templates=[
                {"case_data": {"input": "test", "expected_output": "result"}}
            ],
        )
        
        dataset = service.create_dataset(
            dataset_name="test_dataset",
            version="v1",
            config=config,
        )
        
        dataset = service.generate_cases(dataset.version_id)
        dataset = service.approve_dataset(dataset.version_id)
        
        assert dataset.status == DatasetStatus.APPROVED
        assert dataset.approved_at is not None
        
        approved = service.get_approved_version("test_dataset")
        assert approved is not None
        assert approved.version_id == dataset.version_id


class TestAIDecisionGates:
    """Tests for AI judge decision gates."""
    
    def test_pre_invocation_gate_proceed(self):
        """Test pre-invocation gate with valid conditions."""
        gate = PreInvocationGate("test_pre_invocation")
        
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="v1.0",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        config = AIJudgeInvocationConfig()
        routing_criteria = RoutingCriteria(
            is_critical_case=True,
            semantic_difference_score=0.8,
        )
        
        context = {
            "ai_judge_available": True,
            "estimated_cost_usd": 0.01,
            "case_id": "case_001",
            "total_spent_usd": 0.0,
            "max_budget_usd": 1.0,
            "calls_this_minute": 0,
            "max_calls_per_minute": 10,
        }
        
        result = gate.evaluate({
            "artifact": artifact,
            "config": config,
            "routing_criteria": routing_criteria,
            **context,
        })
        
        assert result.decision == GateDecision.PROCEED
        assert result.gate_type == GateType.PRE_INVOCATION
        assert result.is_blocking is False
    
    def test_pre_invocation_gate_fallback_no_ai(self):
        """Test pre-invocation gate fallback when AI unavailable."""
        gate = PreInvocationGate("test_pre_invocation")
        
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="v1.0",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        context = {
            "ai_judge_available": False,  # AI unavailable
            "artifact": artifact,
        }
        
        result = gate.evaluate(context)
        
        assert result.decision == GateDecision.FALLBACK
        assert "use_deterministic" in result.fallback_data
        assert result.reason == "AI judge not available"
    
    def test_pre_invocation_gate_block_budget(self):
        """Test pre-invocation gate blocks on budget exceeded."""
        gate = PreInvocationGate("test_pre_invocation")
        
        context = {
            "ai_judge_available": True,
            "total_spent_usd": 0.95,
            "max_budget_usd": 1.0,
            "estimated_cost_usd": 0.1,  # Would exceed budget
        }
        
        result = gate.evaluate(context)
        
        assert result.decision == GateDecision.BLOCK
        assert result.is_blocking is True
        assert "budget" in result.reason.lower()
    
    def test_cost_control_gate_proceed(self):
        """Test cost control gate allows within limits."""
        gate = CostControlGate(
            max_total_spending_usd=10.0,
            max_per_case_spending_usd=0.5,
        )
        
        context = {
            "estimated_cost_usd": 0.01,
            "case_id": "case_001",
        }
        
        decision, result = gate.evaluate_cost_control(0.01, "case_001", context)
        
        assert decision == GateDecision.PROCEED
        assert result.decision == GateDecision.PROCEED
    
    def test_cost_control_gate_block_total(self):
        """Test cost control gate blocks on total budget exceeded."""
        gate = CostControlGate(max_total_spending_usd=1.0)
        
        # Record some spending
        gate.record_spending("case_001", 0.8)
        
        context = {
            "estimated_cost_usd": 0.3,  # Would exceed total
            "case_id": "case_002",
        }
        
        decision, result = gate.evaluate_cost_control(0.3, "case_002", context)
        
        assert decision == GateDecision.BLOCK
        assert result.is_blocking is True
    
    def test_cost_control_gate_fallback_per_case(self):
        """Test cost control gate fallback on per-case limit."""
        gate = CostControlGate(max_per_case_spending_usd=0.1)
        
        # Record spending for this case
        gate.record_spending("case_001", 0.08)
        
        context = {
            "estimated_cost_usd": 0.05,  # Would exceed per-case
            "case_id": "case_001",
        }
        
        decision, result = gate.evaluate_cost_control(0.05, "case_001", context)
        
        assert decision == GateDecision.FALLBACK
        assert "use_deterministic" in result.fallback_data
    
    def test_post_result_gate_validate_success(self):
        """Test post-result gate validates successful AI result."""
        gate = PostResultGate("test_post_result")
        
        ai_result = AIJudgeResult(
            success=True,
            worker_result=None,  # Would be actual WorkerResult
            model_used="gpt-4",
            tokens_used=500,
            cost_usd=0.01,
            latency_ms=2000,
            confidence=0.8,
            output_valid=True,
            fallback_used=False,
        )
        
        config = AIJudgeInvocationConfig(min_confidence=0.7)
        
        context = {
            "ai_result": ai_result,
            "config": config,
        }
        
        result = gate.evaluate(context)
        
        assert result.decision == GateDecision.PROCEED
        assert result.gate_type == GateType.POST_RESULT
    
    def test_post_result_gate_fallback_low_confidence(self):
        """Test post-result gate fallback on low confidence."""
        gate = PostResultGate("test_post_result")
        
        ai_result = AIJudgeResult(
            success=True,
            worker_result=None,
            model_used="gpt-4",
            tokens_used=500,
            cost_usd=0.01,
            latency_ms=2000,
            confidence=0.5,  # Below threshold
            output_valid=True,
            fallback_used=False,
        )
        
        config = AIJudgeInvocationConfig(min_confidence=0.7)
        
        context = {
            "ai_result": ai_result,
            "config": config,
        }
        
        result = gate.evaluate(context)
        
        assert result.decision == GateDecision.FALLBACK
        assert "confidence" in result.reason.lower()
    
    def test_post_result_gate_block_prohibited_reason(self):
        """Test post-result gate blocks on prohibited reason codes."""
        gate = PostResultGate("test_post_result")
        
        # Create a WorkerResult with prohibited reason code
        from glyph.specialized_workers.base import WorkerResult, WorkerType, GraderMode, Severity
        
        worker_result = WorkerResult(
            evaluation_id="eval_123",
            worker_type=WorkerType.OUTPUT_QUALITY,
            worker_version="1.0.0",
            trial_id="trial_123",
            score=0.9,
            passed=True,
            severity=Severity.INFO,
            reason_code="hallucination_detected",  # Prohibited
            reason_message="Test",
            grader_mode=GraderMode.MODEL_JUDGE,
            confidence=0.8,
        )
        
        ai_result = AIJudgeResult(
            success=True,
            worker_result=worker_result,
            model_used="gpt-4",
            tokens_used=500,
            cost_usd=0.01,
            latency_ms=2000,
            confidence=0.8,
            output_valid=True,
            fallback_used=False,
        )
        
        config = AIJudgeInvocationConfig(
            min_confidence=0.7,
            prohibited_reason_codes={"hallucination_detected"},
        )
        
        context = {
            "ai_result": ai_result,
            "config": config,
        }
        
        result = gate.evaluate(context)
        
        assert result.decision == GateDecision.BLOCK
        assert result.is_blocking is True
    
    def test_quality_control_gate_suspicious_patterns(self):
        """Test quality control gate detects suspicious patterns."""
        gate = QualityControlGate("test_quality")
        
        # Create AI result with suspicious pattern
        from glyph.specialized_workers.base import WorkerResult, WorkerType, GraderMode, Severity
        
        worker_result = WorkerResult(
            evaluation_id="eval_123",
            worker_type=WorkerType.OUTPUT_QUALITY,
            worker_version="1.0.0",
            trial_id="trial_123",
            score=0.0,
            passed=True,
            severity=Severity.INFO,
            reason_code="unknown",  # Suspicious
            reason_message="Test",
            grader_mode=GraderMode.MODEL_JUDGE,
            confidence=0.8,
            findings={},  # Empty findings
        )
        
        ai_result = AIJudgeResult(
            success=True,
            worker_result=worker_result,
            model_used="gpt-4",
            tokens_used=500,
            cost_usd=0.01,
            latency_ms=2000,
            confidence=0.8,
            output_valid=True,
            fallback_used=False,
        )
        
        context = {
            "ai_result": ai_result,
        }
        
        result = gate.evaluate(context)
        
        assert result.decision == GateDecision.FALLBACK
        assert "suspicious" in result.reason.lower()
    
    def test_confidence_control_gate_very_high(self):
        """Test confidence control gate warns on very high confidence."""
        gate = ConfidenceControlGate("test_confidence")
        
        ai_result = AIJudgeResult(
            success=True,
            worker_result=None,
            model_used="gpt-4",
            tokens_used=500,
            cost_usd=0.01,
            latency_ms=2000,
            confidence=0.99,  # Very high
            output_valid=True,
            fallback_used=False,
        )
        
        config = AIJudgeInvocationConfig(min_confidence=0.7)
        
        context = {
            "ai_result": ai_result,
            "config": config,
        }
        
        result = gate.evaluate(context)
        
        assert result.decision == GateDecision.PROCEED  # Still proceeds, but logs warning
        assert result.gate_type == GateType.CONFIDENCE_CONTROL
    
    def test_ai_judge_gate_chain_pre_invocation(self):
        """Test AI judge gate chain for pre-invocation."""
        gate_chain = AIJudgeGateChain()
        
        model_manifest = ModelManifest(
            provider="openai",
            model_id="gpt-4",
            parameters_hash="sha256:abc123"
        )
        usage = UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01
        )
        
        artifact = EvaluationArtifact.create(
            run_id="run_001",
            mode=ExecutionMode.LIVE,
            case_id="case_001",
            trial_id="trial_001",
            target_version="v1.0",
            model_manifest=model_manifest,
            dataset_hash="sha256:def456",
            sandbox_hash="sha256:ghi789",
            fixture_hash="sha256:jkl012",
            events=[],
            final_output={"answer": "test"},
            outcome_observations=[],
            usage=usage,
        )
        
        config = AIJudgeInvocationConfig()
        routing_criteria = RoutingCriteria(is_critical_case=True)
        
        context = {
            "ai_judge_available": True,
            "estimated_cost_usd": 0.01,
            "case_id": "case_001",
        }
        
        import asyncio
        decision, result = asyncio.run(
            gate_chain.evaluate_pre_invocation(
                artifact, config, routing_criteria, context
            )
        )
        
        assert decision == GateDecision.PROCEED
        assert result.gate_type == GateType.PRE_INVOCATION
    
    def test_ai_judge_gate_chain_post_result(self):
        """Test AI judge gate chain for post-result validation."""
        gate_chain = AIJudgeGateChain()
        
        ai_result = AIJudgeResult(
            success=True,
            worker_result=None,
            model_used="gpt-4",
            tokens_used=500,
            cost_usd=0.01,
            latency_ms=2000,
            confidence=0.8,
            output_valid=True,
            fallback_used=False,
        )
        
        config = AIJudgeInvocationConfig(min_confidence=0.7)
        
        context = {
            "ai_result": ai_result,
            "config": config,
        }
        
        import asyncio
        decision, result = asyncio.run(
            gate_chain.evaluate_post_result(ai_result, config, context)
        )
        
        assert decision == GateDecision.PROCEED
        assert result.gate_type in (GateType.POST_RESULT, GateType.QUALITY_CONTROL, GateType.CONFIDENCE_CONTROL)
    
    def test_ai_judge_gate_chain_spending_tracking(self):
        """Test AI judge gate chain tracks spending."""
        gate_chain = AIJudgeGateChain()
        
        # Record some spending
        gate_chain.record_actual_spending("case_001", 0.05)
        gate_chain.record_actual_spending("case_002", 0.03)
        
        summary = gate_chain.get_spending_summary()
        
        assert summary["total_spent_usd"] == 0.08
        assert summary["case_spending"]["case_001"] == 0.05
        assert summary["case_spending"]["case_002"] == 0.03


if __name__ == "__main__":
    pytest.main([__file__, "-v"])