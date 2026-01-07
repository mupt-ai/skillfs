"""Main runner - configurable template for orchestrator agents.

MainRunner provides a flexible way to create custom agents by specifying:
- Name and description
- System prompt
- Which tools to use
- Which sub-runners can be called
"""

from typing import Any, Callable, Dict, List, Optional

from skillfs.runners.base import AgentResult, RunnerProvider
from skillfs.runners.tools import get_schemas, build_handlers
from skillfs.runners.tools.subrunner import build_schema as build_subrunner_schema
from skillfs.runners.tools.subrunner import _normalize_runner_config, SubrunnerConfig
from skillfs.sandboxes.base import SandboxConnection


class MainRunner:
    """A configurable runner that can be customized at instantiation.

    MainRunner is a template that lets you create custom runners by
    specifying the system prompt, tools, and available sub-runners.

    Example:
        >>> # Create a main orchestrator agent
        >>> main = MainRunner(
        ...     name="orchestrator",
        ...     description="Main agent that delegates to specialists",
        ...     system_prompt="You are a helpful assistant that can delegate tasks...",
        ...     sandbox=sandbox,
        ...     provider=provider,
        ...     tools=["glob", "grep", "read_file"],
        ...     subrunners={"search": SearchRunner},
        ... )
        >>> result = await main.run("Find and summarize auth code")
        >>>
        >>> # Inject additional tools after construction
        >>> main.tools.append(custom_tool_schema)
        >>> main.handlers["custom_tool"] = custom_handler
        >>>
        >>> # Inject tools that will be passed to subrunners too
        >>> main.subrunner_extra_tools.append(skill_schema)
        >>> main.subrunner_extra_handlers["load_skill"] = skill_handler
    """

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        sandbox: SandboxConnection,
        provider: RunnerProvider,
        tools: Optional[List[str]] = None,
        subrunners: Optional[Dict[str, SubrunnerConfig]] = None,
        max_turns: int = 50,
        output_schema: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the main runner.

        Args:
            name: Unique name/ID for this runner.
            description: What this runner does (shown in sub-runner tool).
            system_prompt: System instructions for the agent.
            sandbox: Active sandbox connection for file operations.
            provider: RunnerProvider for creating the underlying agent.
            tools: List of tool names to enable (e.g., ["glob", "grep"]).
                  If None, no sandbox tools are added.
            subrunners: Dict mapping names to runner configs. Config can be:
                       - A runner class: {"search": SearchRunner}
                       - A dict with class: {"search": {"class": SearchRunner}}
                       - A dict with provider override:
                         {"search": {"class": SearchRunner, "provider": haiku_provider}}
                       If provider is not specified, subrunner inherits parent's provider.
            max_turns: Maximum conversation turns.
            output_schema: Optional JSON schema for structured output. When provided,
                          the agent's final response will conform to this schema.

        After initialization, these are available for modification:
            self.tools: Tool schemas for the main runner
            self.handlers: Tool handlers for the main runner
            self.subrunner_extra_tools: Extra tool schemas to inject into subrunners
            self.subrunner_extra_handlers: Extra handlers to inject into subrunners
        """
        self.runner_name = name
        self.description = description
        self.system_prompt = system_prompt
        self.sandbox = sandbox
        self.provider = provider
        self.tool_names = tools or []
        self.subrunner_classes = subrunners or {}
        self.max_turns = max_turns
        self.output_schema = output_schema

        # Build tools and handlers eagerly
        self.tools: List[Dict[str, Any]] = []
        self.handlers: Dict[str, Callable] = {}

        # Extra tools/handlers to inject into subrunners (can be modified after init)
        self.subrunner_extra_tools: List[Dict[str, Any]] = []
        self.subrunner_extra_handlers: Dict[str, Callable] = {}

        # Add sandbox tools
        if self.tool_names:
            self.tools.extend(get_schemas(self.tool_names))
            self.handlers.update(build_handlers(self.sandbox, self.tool_names))

        # Add sub-runner tool if sub-runners are configured
        if self.subrunner_classes:
            # Build schema (static)
            subrunner_schema = build_subrunner_schema(self.subrunner_classes)
            self.tools.append(subrunner_schema)
            # Build handler that references self for dynamic extra tools
            self.handlers["call_subrunner"] = self._build_subrunner_handler()

    def _build_subrunner_handler(self) -> Callable[..., Any]:
        """Build a subrunner handler that dynamically references self for extra tools.

        This allows extra_tools/handlers to be added after construction and still
        be passed to subrunners when they're invoked.
        """
        async def handle_subrunner(
            runner: str,
            task: str,
            **_: Any,
        ) -> Dict[str, Any]:
            """Call a sub-runner with the given task."""
            if runner not in self.subrunner_classes:
                return {
                    "error": f"Unknown runner: {runner}. Available: {list(self.subrunner_classes.keys())}"
                }

            config = self.subrunner_classes[runner]
            runner_class, provider_override = _normalize_runner_config(config)

            # Use override provider if specified, otherwise default
            runner_provider = provider_override or self.provider

            try:
                # Instantiate the sub-runner
                sub_runner = runner_class(sandbox=self.sandbox, provider=runner_provider)

                # Inject extra tools if the runner exposes tools/handlers
                # Reference self.subrunner_extra_* dynamically so changes after init are reflected
                if self.subrunner_extra_tools or self.subrunner_extra_handlers:
                    if hasattr(sub_runner, "tools") and hasattr(sub_runner, "handlers"):
                        sub_runner.tools.extend(self.subrunner_extra_tools)
                        sub_runner.handlers.update(self.subrunner_extra_handlers)

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

    # Class-level attributes for registration (set per instance)
    @property
    def name(self) -> str:
        return self.runner_name

    def add_tool(self, tool: tuple[Dict[str, Any], Callable]) -> None:
        """Add a tool to this runner.

        Args:
            tool: Tuple of (schema, handler) from a tool provider.

        Example:
            >>> commit_tool = workspace.get_commit_tool()
            >>> runner.add_tool(commit_tool)
        """
        schema, handler = tool
        self.tools.append(schema)
        self.handlers[schema["name"]] = handler

    async def run(self, task: str) -> AgentResult:
        """Run the agent with the given task.

        Args:
            task: The task or query for the agent.

        Returns:
            AgentResult with the response and conversation history.
        """
        # Create runner via provider using pre-built tools/handlers
        runner = self.provider.create_runner(
            system_prompt=self.system_prompt,
            tools=self.tools,
            tool_handlers=self.handlers,
            max_turns=self.max_turns,
            output_schema=self.output_schema,
        )

        # Execute
        return await runner.run(task)

    def __repr__(self) -> str:
        return (
            f"MainRunner(name={self.runner_name}, "
            f"tools={self.tool_names}, "
            f"subrunners={list(self.subrunner_classes.keys())})"
        )


# Factory function for easier creation
def create_runner(
    name: str,
    description: str,
    system_prompt: str,
    sandbox: SandboxConnection,
    provider: RunnerProvider,
    tools: Optional[List[str]] = None,
    subrunners: Optional[Dict[str, SubrunnerConfig]] = None,
    max_turns: int = 50,
    output_schema: Optional[Dict[str, Any]] = None,
) -> MainRunner:
    """Create a MainRunner with the given configuration.

    This is a convenience function that creates a MainRunner instance.
    Use this when you want to quickly configure a custom runner without
    subclassing.

    Example:
        >>> from skillfs.runners.types.main import create_runner
        >>> from skillfs.runners.types import SearchRunner
        >>>
        >>> main = create_runner(
        ...     name="main",
        ...     description="Main orchestrator agent",
        ...     system_prompt="You are a helpful assistant...",
        ...     sandbox=sandbox,
        ...     provider=provider,
        ...     tools=["glob", "grep"],
        ...     subrunners={"search": SearchRunner},
        ... )
    """
    return MainRunner(
        name=name,
        description=description,
        system_prompt=system_prompt,
        sandbox=sandbox,
        provider=provider,
        tools=tools,
        subrunners=subrunners,
        max_turns=max_turns,
        output_schema=output_schema,
    )
