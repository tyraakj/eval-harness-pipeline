"""Tests for offline sandbox providers."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from glyph.core.domain_models import EvalCase, SuiteType
from glyph.security.offline_sandbox import (
    CompositeSandboxProvider,
    FilesystemSandboxConfig,
    FilesystemSandboxProvider,
    NetworkSandboxConfig,
    NetworkSandboxProvider,
)
from glyph.security.live_sandbox import RunContext


@pytest.mark.asyncio
async def test_filesystem_sandbox_provision():
    """Test filesystem sandbox provisioning."""
    config = FilesystemSandboxConfig(base_dir=Path(tempfile.gettempdir()) / "glyph-test")
    provider = FilesystemSandboxProvider(config)
    
    case = EvalCase(id="test-1", input={"question": "test"}, suite=SuiteType.CAPABILITY)
    context = RunContext(run_id="run-1", trial_id="trial-1", budget=None)
    
    session = await provider.provision(case, context)
    
    assert session.provider == "filesystem"
    assert session.isolation == "filesystem"
    assert "trial_dir" in session.metadata
    assert Path(session.metadata["trial_dir"]).exists()
    
    # Cleanup
    await provider.destroy(session)


@pytest.mark.asyncio
async def test_filesystem_sandbox_reset():
    """Test filesystem sandbox reset between repetitions."""
    config = FilesystemSandboxConfig(base_dir=Path(tempfile.gettempdir()) / "glyph-test-reset")
    provider = FilesystemSandboxProvider(config)
    
    case = EvalCase(id="test-2", input={"question": "test"}, suite=SuiteType.CAPABILITY)
    context = RunContext(run_id="run-2", trial_id="trial-2", budget=None)
    
    session = await provider.provision(case, context)
    trial_dir = Path(session.metadata["trial_dir"])
    
    # Create some test files
    (trial_dir / "test.txt").write_text("test content")
    (trial_dir / "subdir").mkdir()
    (trial_dir / "subdir" / "file.txt").write_text("more content")
    
    # Reset should clean contents but keep directory
    await provider.reset(session)
    
    assert trial_dir.exists()
    assert not (trial_dir / "test.txt").exists()
    assert not (trial_dir / "subdir").exists()
    
    await provider.destroy(session)


@pytest.mark.asyncio
async def test_network_sandbox_provision():
    """Test network sandbox provisioning."""
    config = NetworkSandboxConfig(
        allowed_hosts=frozenset(["localhost", "127.0.0.1"]),
        block_external=True,
    )
    provider = NetworkSandboxProvider(config)
    
    case = EvalCase(id="test-3", input={"question": "test"}, suite=SuiteType.CAPABILITY)
    context = RunContext(run_id="run-3", trial_id="trial-3", budget=None)
    
    session = await provider.provision(case, context)
    
    assert session.provider == "network"
    assert session.isolation == "network"
    assert session.metadata["block_external"] is True
    assert "localhost" in session.metadata["allowed_hosts"]


@pytest.mark.asyncio
async def test_composite_sandbox():
    """Test composite sandbox combining multiple providers."""
    fs_config = FilesystemSandboxConfig(base_dir=Path(tempfile.gettempdir()) / "glyph-test-composite")
    network_config = NetworkSandboxConfig(block_external=False)
    
    fs_provider = FilesystemSandboxProvider(fs_config)
    network_provider = NetworkSandboxProvider(network_config)
    
    composite = CompositeSandboxProvider([fs_provider, network_provider])
    
    assert "filesystem" in composite.capabilities
    assert "network" in composite.capabilities
    assert "temp_files" in composite.capabilities
    assert "egress_control" in composite.capabilities
    
    case = EvalCase(id="test-4", input={"question": "test"}, suite=SuiteType.CAPABILITY)
    context = RunContext(run_id="run-4", trial_id="trial-4", budget=None)
    
    session = await composite.provision(case, context)
    
    assert session.provider == "composite"
    assert session.isolation == "composite"
    assert len(session.metadata["providers"]) == 2
    
    await composite.destroy(session)
