from __future__ import annotations

from pathlib import Path

import pytest

from glyph.utils.prompts import PromptRegistry


def test_prompt_registry_verifies_and_renders_version(tmp_path: Path) -> None:
    directory = tmp_path / "answer" / "1.0.0"
    directory.mkdir(parents=True)
    template = "Answer {question} using {context}."
    (directory / "prompt.txt").write_text(template, encoding="utf-8")
    (directory / "manifest.json").write_text(
        PromptRegistry.create_manifest("answer", "1.0.0", "prompt.txt", template),
        encoding="utf-8",
    )

    rendered = PromptRegistry(tmp_path).render(
        "answer", "1.0.0", {"question": "Q", "context": "C"}
    )
    assert rendered.text == "Answer Q using C."
    assert rendered.template_hash.startswith("sha256:")
    assert rendered.rendered_hash != rendered.template_hash


def test_prompt_registry_rejects_modified_released_prompt(tmp_path: Path) -> None:
    directory = tmp_path / "answer" / "1.0.0"
    directory.mkdir(parents=True)
    (directory / "prompt.txt").write_text("Original {question}", encoding="utf-8")
    manifest = PromptRegistry.create_manifest(
        "answer", "1.0.0", "prompt.txt", "Original {question}"
    )
    (directory / "manifest.json").write_text(manifest, encoding="utf-8")
    (directory / "prompt.txt").write_text("Changed {question}", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        PromptRegistry(tmp_path).load("answer", "1.0.0")
