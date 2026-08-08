"""Pydantic schemas for guide API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CommandArgument(BaseModel):
    """Schema for a command argument/option."""
    name: str = Field(description="Name of the argument or option")
    required: bool = Field(description="Whether the argument is required")
    help: str | None = Field(None, description="Help text for the argument")
    type_name: str | None = Field(None, description="Type of the argument")


class CommandInfo(BaseModel):
    """Schema for a CLI command."""
    name: str = Field(description="Command name")
    help: str | None = Field(None, description="Command docstring/help text")
    arguments: list[CommandArgument] = Field(default_factory=list, description="List of arguments/options")


class GuideSection(BaseModel):
    """Schema for a section of commands."""
    title: str = Field(description="Section title")
    commands: list[CommandInfo] = Field(description="Commands in this section")


class GuideResponse(BaseModel):
    """Response schema for the guide API."""
    sections: list[GuideSection] = Field(description="Sections of commands")
