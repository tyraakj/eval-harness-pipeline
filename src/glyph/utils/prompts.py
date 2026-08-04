from __future__ import annotations

import hashlib
import json
from pathlib import Path
from string import Formatter

from pydantic import BaseModel, ConfigDict, Field


def content_hash(value: str | dict | list | tuple) -> str:
    """Compute SHA256 hash of a string, dict, list, or tuple."""
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True)
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class PromptManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: str
    template_file: str
    sha256: str
    required_variables: frozenset[str] = Field(default_factory=frozenset)


class RenderedPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: str
    template_hash: str
    rendered_hash: str
    text: str


class PromptRegistry:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def load(self, prompt_id: str, version: str) -> tuple[PromptManifest, str]:
        directory = self._root / prompt_id / version
        manifest = PromptManifest.model_validate_json(
            (directory / "manifest.json").read_text("utf-8")
        )
        if manifest.id != prompt_id or manifest.version != version:
            raise ValueError("Prompt path and manifest identity differ")
        template_path = (directory / manifest.template_file).resolve()
        if directory.resolve() not in template_path.parents:
            raise ValueError("Prompt template must remain inside its version directory")
        template = template_path.read_text("utf-8")
        if content_hash(template) != manifest.sha256:
            raise ValueError(f"Prompt content hash mismatch for {prompt_id}@{version}")
        return manifest, template

    def render(self, prompt_id: str, version: str, variables: dict[str, object]) -> RenderedPrompt:
        manifest, template = self.load(prompt_id, version)
        discovered = {name for _, name, _, _ in Formatter().parse(template) if name}
        required = set(manifest.required_variables) | discovered
        missing = required - variables.keys()
        if missing:
            raise ValueError(f"Missing prompt variables: {', '.join(sorted(missing))}")
        text = template.format_map(variables)
        return RenderedPrompt(
            id=prompt_id,
            version=version,
            template_hash=manifest.sha256,
            rendered_hash=content_hash(text),
            text=text,
        )

    @staticmethod
    def create_manifest(prompt_id: str, version: str, template_file: str, template: str) -> str:
        variables = sorted({name for _, name, _, _ in Formatter().parse(template) if name})
        manifest = PromptManifest(
            id=prompt_id,
            version=version,
            template_file=template_file,
            sha256=content_hash(template),
            required_variables=frozenset(variables),
        )
        return json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def get_prompt_hash(prompt: str) -> str:
    """Get the hash of a prompt string."""
    return content_hash(prompt)


def render_prompt(template: str, variables: dict[str, object]) -> str:
    """Render a prompt template with variables."""
    discovered = {name for _, name, _, _ in Formatter().parse(template) if name}
    missing = discovered - variables.keys()
    if missing:
        raise ValueError(f"Missing prompt variables: {', '.join(sorted(missing))}")
    return template.format_map(variables)


class PromptRenderer:
    """Simple prompt renderer for backwards compatibility."""
    
    def __init__(self, template: str):
        self.template = template
    
    def render(self, variables: dict[str, object]) -> str:
        return render_prompt(self.template, variables)
