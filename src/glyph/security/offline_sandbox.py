"""Concrete sandbox providers for offline evaluation with proper isolation."""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from glyph.core.domain_models import EvalCase, SandboxSession, SandboxRunResult
from glyph.security.live_sandbox import RunContext


@dataclass(frozen=True, slots=True)
class FilesystemSandboxConfig:
    """Configuration for filesystem-based isolation."""
    base_dir: Path
    ephemeral: bool = True
    cleanup_on_destroy: bool = True


class FilesystemSandboxProvider:
    """Provides filesystem isolation for offline evaluation using temporary directories."""

    name = "filesystem"
    capabilities: frozenset[str] = frozenset({"filesystem", "temp_files", "run_exec"})

    def __init__(self, config: FilesystemSandboxConfig) -> None:
        self.config = config
        self._temp_dirs: dict[str, Path] = {}

    async def provision(self, case: EvalCase, context: RunContext) -> SandboxSession:
        """Create an isolated temporary directory for this trial."""
        trial_dir = self.config.base_dir / context.trial_id
        
        if self.config.ephemeral:
            # Use system temp directory for true isolation
            temp_root = Path(tempfile.gettempdir()) / "glyph-eval" / context.run_id
            temp_root.mkdir(parents=True, exist_ok=True)
            trial_dir = temp_root / context.trial_id
        
        trial_dir.mkdir(parents=True, exist_ok=True)
        self._temp_dirs[context.trial_id] = trial_dir

        return SandboxSession(
            id=context.trial_id,
            provider=self.name,
            isolation="filesystem",
            metadata={
                "case_id": case.id,
                "trial_dir": str(trial_dir),
                "ephemeral": self.config.ephemeral,
            },
        )

    async def reset(self, session: SandboxSession) -> None:
        """Reset the sandbox to a clean state between repetitions."""
        trial_dir = Path(session.metadata.get("trial_dir", ""))
        if trial_dir.exists():
            # Remove all contents but keep the directory
            for item in trial_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

    async def destroy(self, session: SandboxSession) -> None:
        """Clean up the sandbox after trial completion."""
        if not self.config.cleanup_on_destroy:
            return

        trial_dir = Path(session.metadata.get("trial_dir", ""))
        if trial_dir in self._temp_dirs.values():
            if trial_dir.exists():
                shutil.rmtree(trial_dir, ignore_errors=True)
            del self._temp_dirs[session.id]

    async def run(
        self,
        session: SandboxSession,
        argv: list[str],
        env: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> SandboxRunResult:
        import asyncio
        import time

        trial_dir = Path(session.metadata.get("trial_dir", ""))
        
        start_time = time.monotonic()
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(trial_dir),
                env=env or {},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return SandboxRunResult(
                exit_code=process.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_ms=duration_ms,
                timed_out=False,
            )
        except asyncio.TimeoutError:
            if process:
                process.kill()
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return SandboxRunResult(
                exit_code=-1,
                stdout="",
                stderr="Execution timed out.",
                duration_ms=duration_ms,
                timed_out=True,
            )

    async def read(
        self,
        session: SandboxSession,
        path: str,
    ) -> bytes:
        trial_dir = Path(session.metadata.get("trial_dir", ""))
        file_path = trial_dir / path
        if not file_path.resolve().is_relative_to(trial_dir.resolve()):
            raise ValueError("Path traversal detected")
        return file_path.read_bytes()

    async def write(
        self,
        session: SandboxSession,
        path: str,
        data: bytes,
    ) -> None:
        trial_dir = Path(session.metadata.get("trial_dir", ""))
        file_path = trial_dir / path
        if not file_path.resolve().is_relative_to(trial_dir.resolve()):
            raise ValueError("Path traversal detected")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data)


@dataclass(frozen=True, slots=True)
class NetworkSandboxConfig:
    """Configuration for network isolation."""
    allowed_hosts: frozenset[str] = frozenset()
    block_external: bool = True
    mock_apis: dict[str, Any] | None = None


class NetworkSandboxProvider:
    """Provides network isolation metadata for offline evaluation.
    
    Note: This provider records egress policy in metadata only — OS-level
    enforcement requires a container-based provider. For production use,
    consider a container-based sandbox provider that can actually block
    network egress at the OS level.
    """

    name = "network"
    capabilities: frozenset[str] = frozenset({"network", "egress_metadata_only"})

    def __init__(self, config: NetworkSandboxConfig) -> None:
        self.config = config

    async def provision(self, case: EvalCase, context: RunContext) -> SandboxSession:
        """Establish network isolation metadata for this trial.
        
        Warning: This only records the egress policy in metadata — OS-level
        enforcement requires a container-based provider.
        """
        logger.warning(
            "NetworkSandboxProvider records egress policy in metadata only — "
            "OS-level enforcement requires a container-based provider."
        )
        return SandboxSession(
            id=context.trial_id,
            provider=self.name,
            isolation="network",
            metadata={
                "case_id": case.id,
                "allowed_hosts": list(self.config.allowed_hosts),
                "block_external": self.config.block_external,
                "has_mock_apis": self.config.mock_apis is not None,
            },
        )

    async def reset(self, session: SandboxSession) -> None:
        """Reset network state between repetitions."""
        pass

    async def destroy(self, session: SandboxSession) -> None:
        """Clean up network isolation."""
        pass

    async def run(
        self,
        session: SandboxSession,
        argv: list[str],
        env: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> SandboxRunResult:
        raise NotImplementedError

    async def read(self, session: SandboxSession, path: str) -> bytes:
        raise NotImplementedError

    async def write(self, session: SandboxSession, path: str, data: bytes) -> None:
        raise NotImplementedError


class CompositeSandboxProvider:
    """Combines multiple sandbox providers for comprehensive isolation."""

    name = "composite"
    capabilities: frozenset[str]

    def __init__(self, providers: list[Any]) -> None:
        self.providers = providers
        self.capabilities = frozenset(
            cap for provider in providers for cap in provider.capabilities
        )
        self._child_sessions: dict[str, list[Any]] = {}

    async def provision(self, case: EvalCase, context: RunContext) -> SandboxSession:
        """Provision all child providers."""
        sessions = []
        metadata = {"case_id": case.id, "providers": []}

        for provider in self.providers:
            session = await provider.provision(case, context)
            sessions.append(session)
            metadata["providers"].append({
                "name": provider.name,
                "isolation": session.isolation,
            })
            metadata.update(session.metadata)

        # Store child sessions keyed by the composite session ID
        self._child_sessions[context.trial_id] = sessions

        return SandboxSession(
            id=context.trial_id,
            provider=self.name,
            isolation="composite",
            metadata=metadata,
        )

    async def reset(self, session: SandboxSession) -> None:
        """Reset all child providers."""
        child_sessions = self._child_sessions.get(session.id, [])
        for child in child_sessions:
            # Find the original provider and reset
            for provider in self.providers:
                if provider.name == child.provider:
                    await provider.reset(child)
                    break

    async def destroy(self, session: SandboxSession) -> None:
        """Destroy all child providers in reverse order."""
        child_sessions = self._child_sessions.get(session.id, [])
        for child in reversed(child_sessions):
            for provider in self.providers:
                if provider.name == child.provider:
                    await provider.destroy(child)
                    break
        # Clean up stored sessions
        if session.id in self._child_sessions:
            del self._child_sessions[session.id]

    async def run(
        self,
        session: SandboxSession,
        argv: list[str],
        env: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> SandboxRunResult:
        child_sessions = self._child_sessions.get(session.id, [])
        for child in child_sessions:
            for provider in self.providers:
                if provider.name == child.provider and "run_exec" in provider.capabilities:
                    return await provider.run(child, argv, env, timeout_seconds)
        raise NotImplementedError("No composite provider supports run_exec")

    async def read(self, session: SandboxSession, path: str) -> bytes:
        child_sessions = self._child_sessions.get(session.id, [])
        for child in child_sessions:
            for provider in self.providers:
                if provider.name == child.provider and "filesystem" in provider.capabilities:
                    return await provider.read(child, path)
        raise NotImplementedError("No composite provider supports read")

    async def write(self, session: SandboxSession, path: str, data: bytes) -> None:
        child_sessions = self._child_sessions.get(session.id, [])
        for child in child_sessions:
            for provider in self.providers:
                if provider.name == child.provider and "filesystem" in provider.capabilities:
                    return await provider.write(child, path, data)
        raise NotImplementedError("No composite provider supports write")
