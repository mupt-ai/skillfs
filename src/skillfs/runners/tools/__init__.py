"""Shared tool definitions for runners.

Tools can be easily composed into runner configurations:

    from skillfs.runners.tools import glob, grep, read_file

    tools = [glob.SCHEMA, grep.SCHEMA, read_file.SCHEMA]
    handlers = {
        "glob": glob.build_handler(sandbox),
        "grep": grep.build_handler(sandbox),
        "read_file": read_file.build_handler(sandbox),
    }

Or use the registry for bulk operations:

    from skillfs.runners.tools import TOOL_REGISTRY, build_handlers

    tools = [TOOL_REGISTRY[name].SCHEMA for name in ["glob", "grep"]]
    handlers = build_handlers(sandbox, ["glob", "grep"])
"""

from typing import Any, Callable, Dict, List
from types import ModuleType

from skillfs.runners.tools.base import ToolModule
from skillfs.runners.tools import (
    glob,
    grep,
    read_file,
    write_file,
    edit_file,
    run_command,
    subrunner,
    load_skill,
)

from skillfs.sandboxes.base import SandboxConnection

# Registry of available tool modules
TOOL_REGISTRY: Dict[str, ModuleType] = {
    "glob": glob,
    "grep": grep,
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "run_command": run_command,
}

# Re-export subrunner helpers
create_subrunner_tool = subrunner.create_subrunner_tool

# Re-export load_skill helpers
create_load_skill_tool = load_skill.create_load_skill_tool


def _validate_tool_names(tool_names: List[str]) -> None:
    """Validate that all tool names exist in the registry.

    Args:
        tool_names: List of tool names to validate.

    Raises:
        ValueError: If any tool name is not in TOOL_REGISTRY.
    """
    unknown = set(tool_names) - set(TOOL_REGISTRY.keys())
    if unknown:
        available = list(TOOL_REGISTRY.keys())
        raise ValueError(f"Unknown tool(s): {sorted(unknown)}. Available: {available}")


def get_schemas(tool_names: List[str]) -> List[Dict[str, Any]]:
    """Get tool schemas for the specified tools.

    Args:
        tool_names: List of tool names (e.g., ["glob", "grep"])

    Returns:
        List of tool schema dicts for the Anthropic API.

    Raises:
        ValueError: If any tool name is not in TOOL_REGISTRY.
    """
    _validate_tool_names(tool_names)
    return [TOOL_REGISTRY[name].SCHEMA for name in tool_names]


def build_handlers(
    sandbox: SandboxConnection,
    tool_names: List[str],
) -> Dict[str, Callable[..., Any]]:
    """Build handlers for the specified tools.

    Args:
        sandbox: The sandbox connection to use.
        tool_names: List of tool names (e.g., ["glob", "grep"])

    Returns:
        Dict mapping tool names to handler functions.

    Raises:
        ValueError: If any tool name is not in TOOL_REGISTRY.
    """
    _validate_tool_names(tool_names)
    return {name: TOOL_REGISTRY[name].build_handler(sandbox) for name in tool_names}


__all__ = [
    # Protocol
    "ToolModule",
    # Registry and helpers
    "TOOL_REGISTRY",
    "get_schemas",
    "build_handlers",
    "create_subrunner_tool",
    "create_load_skill_tool",
    # Built-in tool modules
    "glob",
    "grep",
    "read_file",
    "write_file",
    "edit_file",
    "run_command",
    "subrunner",
    "load_skill",
]
