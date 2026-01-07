"""Base infrastructure for running agents with tool calling.

This module provides:
- AgentRunner: Abstract class for agentic loops (provider implementations inherit)
- RunnerProvider: Factory for creating runners with provider-specific config
- AgentResult: Structured result from agent runs
- RunnerType: Protocol defining what runner types must implement

The pattern is:
1. System prompt + tools setup
2. Send messages to LLM API
3. While tool calls needed: process tools, execute handlers, loop
4. Return result when done
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from skillfs.sandboxes.base import SandboxConnection

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result from an agent run.

    Provider-agnostic structure for agent outputs including
    success/failure status, data payload, and conversation history.
    """

    success: bool
    """Whether the agent completed successfully."""

    data: Any = None
    """Primary result data (type depends on the agent)."""

    message: Optional[str] = None
    """Human-readable summary or final response."""

    errors: List[str] = field(default_factory=list)
    """List of errors encountered during execution."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional context (turns used, tools called, etc.)."""

    messages: List[Dict[str, Any]] = field(default_factory=list)
    """Full conversation history (for debugging or continuation)."""

    def to_tool_result(self) -> Dict[str, Any]:
        """Convert to a dict suitable for tool_result content.

        Automatically converts dataclasses in `data` to dicts for JSON serialization.
        This is used when returning sub-runner results as tool outputs.
        """
        result: Dict[str, Any] = {
            "success": self.success,
            "message": self.message,
        }
        if self.data is not None:
            # Convert dataclasses to dicts for JSON serialization
            if is_dataclass(self.data) and not isinstance(self.data, type):
                result["data"] = asdict(self.data)
            else:
                result["data"] = self.data
        if self.errors:
            result["errors"] = self.errors
        return result

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.success


# Type alias for tool handlers
ToolHandler = Callable[..., Any]


class AgentRunner(ABC):
    """Abstract base class for running agents with tool calling.

    This class defines the interface for agentic loops. Concrete implementations
    handle provider-specific API interactions while sharing this common interface.

    Subclasses must implement:
    - run(): Execute the agent loop with the given task

    Example:
        >>> # Using the Anthropic implementation
        >>> runner = AnthropicAgentRunner(
        ...     client=anthropic.Anthropic(),
        ...     model="...",
        ...     system_prompt="You are a search assistant...",
        ...     tools=[glob_tool, grep_tool],
        ...     tool_handlers={"glob": ..., "grep": ...},
        ... )
        >>> result = await runner.run("Find all Python files")
    """

    def __init__(
        self,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        tool_handlers: Dict[str, ToolHandler],
        max_turns: int = 50,
    ):
        """Initialize the agent runner.

        Args:
            system_prompt: System instructions for the agent.
            tools: List of tool definitions (format may vary by provider).
            tool_handlers: Dict mapping tool names to handler functions.
                          Handlers receive tool input as kwargs and return results.
            max_turns: Maximum conversation turns before stopping.
        """
        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_handlers = tool_handlers
        self.max_turns = max_turns

    @abstractmethod
    async def run(
        self,
        task: str,
        *,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentResult:
        """Run the agent loop with the given task.

        The agent will process the task, calling tools as needed, until it
        produces a final response or hits the max_turns limit.

        Args:
            task: The task or query for the agent to process.
            initial_messages: Optional existing conversation to continue from.

        Returns:
            AgentResult with the final response and conversation history.
        """
        pass

    async def _call_handler(
        self,
        handler: ToolHandler,
        tool_input: Dict[str, Any],
    ) -> Any:
        """Call a tool handler, handling both sync and async handlers."""
        import asyncio

        result = handler(**tool_input)

        # If the handler returns a coroutine, await it
        if asyncio.iscoroutine(result):
            result = await result

        return result

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"{self.__class__.__name__}("
            f"tools={[t.get('name', 'unknown') for t in self.tools]}, "
            f"max_turns={self.max_turns})"
        )


class RunnerProvider(ABC):
    """Factory for creating AgentRunner instances with provider-specific config.

    RunnerProvider abstracts away the provider details (Anthropic, OpenAI, etc.)
    so that runner types can work with any provider by just accepting a provider.

    Example:
        >>> # Create a provider with Anthropic config
        >>> provider = AnthropicProvider(api_key="sk-ant-...", model="claude-sonnet-4-5-20250929")
        >>>
        >>> # Use it to create runners (provider-agnostic)
        >>> search = SearchRunner(sandbox=sandbox, provider=provider)
        >>>
        >>> # Easy to swap providers
        >>> provider = OpenAIProvider(client=client, model="gpt-4o-mini")
        >>> search = SearchRunner(sandbox=sandbox, provider=provider)
    """

    @abstractmethod
    def create_runner(
        self,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        tool_handlers: Dict[str, ToolHandler],
        max_turns: int = 50,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> AgentRunner:
        """Create an AgentRunner with the given configuration.

        Args:
            system_prompt: System instructions for the agent.
            tools: List of tool definitions.
            tool_handlers: Dict mapping tool names to handler functions.
            max_turns: Maximum conversation turns.
            output_schema: Optional JSON schema for structured output.
                          When provided, the agent will return valid JSON
                          matching the schema (provider-dependent).

        Returns:
            A configured AgentRunner instance.
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


@runtime_checkable
class RunnerType(Protocol):
    """Protocol defining what a runner type must implement.

    Runner types are provider-agnostic agents that perform specific tasks
    (search, cleanup, code review, etc.). They accept a sandbox and provider,
    then use provider.create_runner() internally.

    Example:
        class MyRunner:
            name = "my_runner"
            description = "Does something useful"

            def __init__(
                self,
                sandbox: "SandboxConnection",
                provider: RunnerProvider,
                max_turns: int = 20,
            ):
                self.sandbox = sandbox
                self.provider = provider
                self.max_turns = max_turns

            async def run(self, task: str) -> AgentResult:
                # Build tools, create runner via provider, execute
                runner = self.provider.create_runner(...)
                return await runner.run(task)

    Then register it:
        from skillfs.runners.types import RUNNER_REGISTRY
        RUNNER_REGISTRY["my_runner"] = MyRunner
    """

    name: str
    """Unique identifier for this runner type."""

    description: str
    """Human-readable description of what this runner does."""

    def __init__(
        self,
        sandbox: "SandboxConnection",
        provider: RunnerProvider,
        **kwargs: Any,
    ) -> None:
        """Initialize the runner with sandbox and provider.

        Args:
            sandbox: Active sandbox connection for file operations.
            provider: RunnerProvider for creating the underlying agent.
            **kwargs: Additional runner-specific options (e.g., max_turns).
        """
        ...

    async def run(self, task: str) -> AgentResult:
        """Run the agent with the given task.

        Args:
            task: The task or query to process.

        Returns:
            AgentResult (or a subclass like SearchResult).
        """
        ...