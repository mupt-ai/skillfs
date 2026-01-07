"""Sub-runner tool - call specialized sub-agents as a tool.

This tool allows a main runner to delegate tasks to specialized sub-runners
(like search, cleanup, etc.) and receive their results.
"""

from typing import Any, Callable, Dict, Type

from skillfs.runners.base import AgentResult, RunnerProvider
from skillfs.sandboxes.base import SandboxConnection


def build_schema(available_runners: Dict[str, Type]) -> Dict[str, Any]:
    """Build the tool schema with available runner options.

    Args:
        available_runners: Dict mapping runner names to runner classes.
                          Each class should have 'name' and 'description' attributes.

    Returns:
        Tool schema dict for the Anthropic API.
    """
    runner_descriptions = []
    for name, runner_class in available_runners.items():
        desc = getattr(runner_class, "description", "No description")
        runner_descriptions.append(f"- {name}: {desc}")

    runners_doc = "\n".join(runner_descriptions)

    return {
        "name": "call_subrunner",
        "description": f"""Delegate a task to a specialized sub-agent for focused execution.

Use this tool when a task is better handled by a specialist agent. Each sub-runner has its own
tools and expertise. The sub-runner executes autonomously and returns structured results.
This allows complex tasks to be broken down and delegated to the most appropriate specialist.

Available sub-runners:
{runners_doc}

Choose the runner best suited for the task and provide a clear, specific task description.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "runner": {
                    "type": "string",
                    "enum": list(available_runners.keys()),
                    "description": "Name of the sub-runner to call",
                },
                "task": {
                    "type": "string",
                    "description": "Task or query for the sub-runner",
                },
            },
            "required": ["runner", "task"],
        },
    }


def build_handler(
    sandbox: SandboxConnection,
    provider: RunnerProvider,
    available_runners: Dict[str, Type],
) -> Callable[..., Any]:
    """Build a handler that calls sub-runners.

    Args:
        sandbox: The sandbox connection for sub-runner file operations.
        provider: The RunnerProvider for sub-runner LLM calls.
        available_runners: Dict mapping runner names to runner classes.

    Returns:
        Async handler function for the call_subrunner tool.
    """

    async def handle_subrunner(
        runner: str,
        task: str,
        **_: Any,
    ) -> Dict[str, Any]:
        """Call a sub-runner with the given task."""
        if runner not in available_runners:
            return {
                "error": f"Unknown runner: {runner}. Available: {list(available_runners.keys())}"
            }

        runner_class = available_runners[runner]

        try:
            # Instantiate and run the sub-runner
            sub_runner = runner_class(sandbox=sandbox, provider=provider)
            result = await sub_runner.run(task)

            # All runners return AgentResult - use to_tool_result() for serialization
            if isinstance(result, AgentResult):
                return result.to_tool_result()
            else:
                # Fallback for non-standard runners
                return {"success": True, "result": str(result)}

        except Exception as e:
            return {"error": f"Sub-runner failed: {str(e)}"}

    return handle_subrunner


# Helper to get both schema and handler together
def create_subrunner_tool(
    sandbox: SandboxConnection,
    provider: RunnerProvider,
    available_runners: Dict[str, Type],
) -> tuple[Dict[str, Any], Callable[..., Any]]:
    """Create the sub-runner tool schema and handler.

    Args:
        sandbox: The sandbox connection.
        provider: The RunnerProvider for sub-runners.
        available_runners: Dict mapping runner names to runner classes.

    Returns:
        Tuple of (schema, handler).

    Example:
        >>> from skillfs.runners.types import RUNNER_REGISTRY
        >>> schema, handler = create_subrunner_tool(
        ...     sandbox=sandbox,
        ...     provider=provider,
        ...     available_runners={"search": SearchRunner},
        ... )
    """
    schema = build_schema(available_runners)
    handler = build_handler(sandbox, provider, available_runners)
    return schema, handler
