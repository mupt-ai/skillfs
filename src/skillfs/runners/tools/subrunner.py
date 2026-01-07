"""Sub-runner tool - call specialized sub-agents as a tool.

This tool allows a main runner to delegate tasks to specialized sub-runners
(like search, cleanup, etc.) and receive their results.

Subrunners can be configured in three ways:
1. Simple: {"search": SearchRunner} - inherits provider from parent
2. Dict without provider: {"search": {"class": SearchRunner}} - also inherits provider
3. Dict with provider: {"search": {"class": SearchRunner, "provider": AnthropicProvider}}

Extra tools (like load_skill) can be passed and will be injected into
subrunners that expose tools/handlers attributes.
"""

from typing import Any, Callable, Dict, List, Optional, Type, Union

from skillfs.runners.base import AgentResult, RunnerProvider
from skillfs.sandboxes.base import SandboxConnection

# Type for subrunner config: either a class or a dict with class + optional provider
SubrunnerConfig = Union[Type, Dict[str, Any]]


def _normalize_runner_config(
    config: SubrunnerConfig,
) -> tuple[Type, Optional[RunnerProvider]]:
    """Normalize subrunner config to (class, optional_provider).

    Args:
        config: Runner configuration in one of three forms:
                - RunnerClass (class directly)
                - {"class": RunnerClass} (dict without provider)
                - {"class": RunnerClass, "provider": SomeProvider} (dict with provider)

    Returns:
        Tuple of (runner_class, provider_or_none). Provider is None if not
        specified, meaning the subrunner should inherit the parent's provider.
    """
    if isinstance(config, dict):
        return config["class"], config.get("provider")
    return config, None


def build_schema(available_runners: Dict[str, SubrunnerConfig]) -> Dict[str, Any]:
    """Build the tool schema with available runner options.

    Args:
        available_runners: Dict mapping runner names to runner configs.
                          Config can be a class or {"class": ..., "provider": ...}.

    Returns:
        Tool schema dict for the Anthropic API.
    """
    runner_descriptions = []
    for name, config in available_runners.items():
        runner_class, _ = _normalize_runner_config(config)
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
    default_provider: RunnerProvider,
    available_runners: Dict[str, SubrunnerConfig],
    extra_tools: Optional[List[Dict[str, Any]]] = None,
    extra_handlers: Optional[Dict[str, Callable]] = None,
) -> Callable[..., Any]:
    """Build a handler that calls sub-runners.

    Args:
        sandbox: The sandbox connection for sub-runner file operations.
        default_provider: Default RunnerProvider for sub-runners (can be overridden per-runner).
        available_runners: Dict mapping runner names to configs.
                          Config can be a class or {"class": ..., "provider": ...}.
        extra_tools: Optional list of extra tool schemas to inject into subrunners.
        extra_handlers: Optional dict of extra handlers to inject into subrunners.

    Returns:
        Async handler function for the call_subrunner tool.
    """
    _extra_tools = extra_tools or []
    _extra_handlers = extra_handlers or {}

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

        config = available_runners[runner]
        runner_class, provider_override = _normalize_runner_config(config)

        # Use override provider if specified, otherwise default
        runner_provider = provider_override or default_provider

        try:
            # Instantiate the sub-runner
            sub_runner = runner_class(sandbox=sandbox, provider=runner_provider)

            # Inject extra tools if the runner exposes tools/handlers
            if _extra_tools or _extra_handlers:
                if hasattr(sub_runner, "tools") and hasattr(sub_runner, "handlers"):
                    sub_runner.tools.extend(_extra_tools)
                    sub_runner.handlers.update(_extra_handlers)

            # Run the task
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


def create_subrunner_tool(
    sandbox: SandboxConnection,
    provider: RunnerProvider,
    available_runners: Dict[str, SubrunnerConfig],
    extra_tools: Optional[List[Dict[str, Any]]] = None,
    extra_handlers: Optional[Dict[str, Callable]] = None,
) -> tuple[Dict[str, Any], Callable[..., Any]]:
    """Create the sub-runner tool schema and handler.

    Args:
        sandbox: The sandbox connection.
        provider: Default RunnerProvider for sub-runners.
        available_runners: Dict mapping runner names to configs.
                          Simple: {"search": SearchRunner}
                          With override: {"search": {"class": SearchRunner, "provider": ...}}
        extra_tools: Optional list of extra tool schemas to inject into subrunners.
                    These are injected into subrunners that expose tools/handlers attributes.
        extra_handlers: Optional dict of extra handlers to inject into subrunners.

    Returns:
        Tuple of (schema, handler).

    Example:
        >>> # Simple usage
        >>> schema, handler = create_subrunner_tool(
        ...     sandbox=sandbox,
        ...     provider=provider,
        ...     available_runners={"search": SearchRunner},
        ... )
        >>>
        >>> # With extra tools (e.g., load_skill)
        >>> schema, handler = create_subrunner_tool(
        ...     sandbox=sandbox,
        ...     provider=provider,
        ...     available_runners={"search": SearchRunner},
        ...     extra_tools=[load_skill_schema],
        ...     extra_handlers={"load_skill": load_skill_handler},
        ... )
        >>>
        >>> # With per-subrunner provider override
        >>> schema, handler = create_subrunner_tool(
        ...     sandbox=sandbox,
        ...     provider=default_provider,
        ...     available_runners={
        ...         "search": {"class": SearchRunner, "provider": anthropic_provider},
        ...     },
        ... )
    """
    schema = build_schema(available_runners)
    handler = build_handler(
        sandbox=sandbox,
        default_provider=provider,
        available_runners=available_runners,
        extra_tools=extra_tools,
        extra_handlers=extra_handlers,
    )
    return schema, handler
