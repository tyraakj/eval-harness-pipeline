# Glyph Security Guide

Glyph implements comprehensive, OWASP LLM Top 10 (2025) and MITRE ATLAS aligned security evaluations for agentic outputs, structured events, and tool usage. The security framework ensures fail-closed critical defenses before outputs reach the end-user.

## OWASP Top 10 for LLMs (2025) Coverage

The `SecurityEvaluator` maps directly to several key OWASP threats via the `SecurityPolicy` configuration and `SecurityAnalysis` extraction. Results are aggregated in the `security_audit` key on the output finding.

| Threat | Description | Glyph Evaluator Check |
|---|---|---|
| **LLM01: Prompt Injection** | Both direct and indirect (via retrieved content) prompt injections. | `_check_prompt_injection`, `_check_indirect_injection` |
| **LLM02: Sensitive Information** | LLMs inadvertently disclosing sensitive data or secrets. | `_check_secret_exposure`, `_check_credential_exposure` |
| **LLM05: Output Handling** | XSS, SSRF, or shell injection derived from the model's output. | `_check_output_injection`, `_check_unauthorized_tools`, `_check_network_access` |
| **LLM06: Excessive Agency** | Agent autonomously taking irreversible or unauthorized actions. | `_check_excessive_agency` (scope violations & irreversible actions) |
| **LLM07: System Prompt Leakage** | The model disclosing its base instructions to the user. | `_check_system_prompt_leakage` |

## MITRE ATLAS Coverage

In addition to OWASP, Glyph provides coverage for MITRE ATLAS techniques:

| Threat | Description | Glyph Evaluator Check |
|---|---|---|
| **AML.T0054: Jailbreak** | Attempting to circumvent the safety rules or behavioral restrictions. | `_check_jailbreak_attempts` |

## Configuring Security Policies

All detection thresholds, block lists, regex patterns, and string templates are defined in `src/glyph/specialized_workers/policy_registry.py`. **Do not hardcode strings inside the evaluator**.

To extend or adjust patterns for your environment, modify the relevant constants in `policy_registry.py`:

- `SYSTEM_PROMPT_LEAK_INDICATORS`
- `IRREVERSIBLE_ACTION_INDICATORS`
- `SCOPE_VIOLATION_INDICATORS`
- `HTML_INJECTION_PATTERNS`
- `SHELL_INJECTION_PATTERNS`
- `JAILBREAK_PATTERNS`
- `PATH_TRAVERSAL_PATTERNS`
- `DEFAULT_SECRET_PATTERNS`
- `DEFAULT_BLOCKED_DOMAINS`

The message outputted by the CLI and Web UI uses `SECURITY_FAILURE_TEMPLATES` for customizable user feedback without touching the core evaluation logic.

## Modifying Checks

When you add a new security check to `SecurityEvaluator`, remember to:
1. Update `SecurityPolicy` with its toggle flag (default to `True` for security) and patterns list.
2. Add a new `_check_*` method.
3. Update `SecurityAnalysis` with the new fields.
4. Call it inside `_analyze_security` and add the findings to `_aggregate_findings` and `security_audit.owasp_coverage`.
5. Adjust `_compute_result` to check the flag and return a localized template string from `self.policy.failure_message_templates`.
