"""Guide API routes."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Request
from collections import defaultdict
import typer
from typer.core import TyperCommand, TyperGroup

from glyph.schemas.guide import CommandArgument, CommandInfo, GuideSection, GuideResponse
from glyph.api.rate_limit import limiter

router = APIRouter()


def _get_commands_from_group(group: TyperGroup, prefix: str = "") -> list[tuple[str, TyperCommand]]:
    commands = []
    for name, cmd in group.commands.items():
        if isinstance(cmd, TyperGroup):
            commands.extend(_get_commands_from_group(cmd, prefix=f"{prefix}{name} "))
        elif isinstance(cmd, TyperCommand):
            commands.append((f"{prefix}{name}", cmd))
    return commands


@router.get("", response_model=GuideResponse)
@limiter.limit("60/minute")
async def get_guide(request: Request) -> GuideResponse:
    """Get CLI command guide dynamically introspected from Typer."""
    sections_map = defaultdict(list)
    
    try:
        from glyph.cli.cli import app, _GUIDE_SECTIONS
        
        # Typer apps need to be converted to click commands to inspect them easily
        click_app = typer.main.get_command(app)
        
        if isinstance(click_app, TyperGroup):
            commands = _get_commands_from_group(click_app)
            
            for cmd_name, cmd in commands:
                args = []
                for param in cmd.params:
                    # Determine type string
                    type_name = getattr(param.type, "name", "string")
                    
                    # Extract options vs arguments
                    param_name = param.opts[0] if param.opts else param.name
                    
                    args.append(CommandArgument(
                        name=param_name,
                        required=param.required,
                        help=getattr(param, "help", None),
                        type_name=type_name
                    ))
                
                info = CommandInfo(
                    name=f"glyph {cmd_name}",
                    help=cmd.help,
                    arguments=args
                )
                
                # Determine section
                # Try exact match, then base command match
                base_cmd = cmd_name.split()[0]
                section_title = _GUIDE_SECTIONS.get(cmd_name) or _GUIDE_SECTIONS.get(base_cmd) or "Other"
                
                sections_map[section_title].append(info)
                
    except Exception as e:
        # Fallback to empty if introspection fails
        import logging
        logging.error(f"Failed to introspect CLI: {e}")
        pass
        
    sections = []
    for title, cmds in sections_map.items():
        sections.append(GuideSection(title=title, commands=cmds))
        
    return GuideResponse(sections=sections)
