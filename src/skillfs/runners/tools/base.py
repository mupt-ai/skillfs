"""Protocol for runner tools.

Tools are modules that provide:
- SCHEMA: Tool definition dict with name, description, and input_schema
- build_handler: Function that creates the handler for a sandbox

Example:
    # my_tool.py
    SCHEMA = {
        "name": "my_tool",
        "description": "Does something useful...",
        "input_schema": {
            "type": "object",
            "properties": {"arg": {"type": "string"}},
            "required": ["arg"],
        },
    }

    def build_handler(sandbox: SandboxConnection) -> Callable[..., Any]:
        def handler(arg: str, **_) -> Dict[str, Any]:
            # Do something with sandbox
            return {"result": "..."}
            # On error, return {"error": "message"} - runner will set is_error flag
        return handler

    # Then register it:
    from skillfs.runners.tools import TOOL_REGISTRY
    TOOL_REGISTRY["my_tool"] = my_tool
"""

from typing import Any, Callable, Dict, Protocol

from skillfs.sandboxes.base import SandboxConnection


class ToolModule(Protocol):
    """Protocol for tool modules (documentation and type checking)."""

    SCHEMA: Dict[str, Any]
    """Tool schema with name, description, and input_schema."""

    def build_handler(sandbox: SandboxConnection) -> Callable[..., Any]:
        """Build the handler function for this tool.

        Args:
            sandbox: The sandbox connection to use for operations.

        Returns:
            A callable that handles tool invocations.
            Should accept **kwargs to ignore unknown parameters.
            Return {"error": "message"} to signal errors.
        """
        ...
