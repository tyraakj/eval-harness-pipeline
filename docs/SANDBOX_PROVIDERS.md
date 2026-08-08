# Sandbox Providers

Glyph provides several sandbox providers for evaluation isolation:

## NoopSandboxProvider

No isolation — for trusted local graphs only. Does not provide any sandboxing and should only be used in development or when you fully trust the graph being evaluated.

## FilesystemSandboxProvider

Provides real temp-dir isolation with OS-backed filesystem isolation. Creates temporary directories for each trial and cleans them up after evaluation. Suitable for offline evaluation where you need file system isolation but don't require network restrictions.

## NetworkSandboxProvider

Metadata-only network policy recording. Records egress policy in session metadata but does not enforce it at the OS level. For production use, consider a container-based provider that can actually block network egress. Use this when you want to track network policy but don't require actual network blocking.

## CompositeSandboxProvider

Chains multiple providers together for comprehensive isolation. Combines capabilities from all child providers and coordinates their lifecycle (provision, reset, destroy). Use this when you need multiple isolation mechanisms (e.g., filesystem + network policy).

## Production Provider Requirements

A production sandbox provider should implement:
- OS-level resource isolation (CPU, memory, disk)
- Network egress blocking at the OS level
- File system isolation with proper cleanup
- Timeout enforcement
- Resource limits and quotas

Container-based providers (Docker, Kubernetes) are recommended for production use.