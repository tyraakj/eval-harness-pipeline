from __future__ import annotations

from langgraph_eval.utils import sanitize


def test_sanitize_redacts_common_secrets_and_email() -> None:
    value = sanitize({"header": "Authorization: Bearer abc123", "email": "person@example.com"})
    assert "abc123" not in str(value)
    assert "person@example.com" not in str(value)
    assert "[REDACTED]" in str(value)
