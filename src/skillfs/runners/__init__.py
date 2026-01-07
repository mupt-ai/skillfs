"""Runners module - LLM agent runners with tool calling support.

This module provides:

Base classes and protocols:
- AgentRunner: Abstract base for agentic loops
- AgentResult: Structured result from agent runs
- RunnerProvider: Factory for creating runners with provider config
- RunnerType: Protocol defining what runner types must implement

Providers (in runners.providers):
- AnthropicAgentRunner: Anthropic/Claude implementation
- AnthropicProvider: Factory for Anthropic runners

Runner types (in runners.types):
- SearchRunner: Intelligent codebase search
- MainRunner: Configurable template for orchestrator agents

Tools (in runners.tools):
- Shared tool definitions (glob, grep, read_file)
- ToolModule: Protocol for creating custom tools

Example:
    >>> from skillfs.runners.providers import AnthropicProvider
    >>> from skillfs.runners.types import SearchRunner
    >>>
    >>> provider = AnthropicProvider(api_key="sk-ant-...", model="claude-sonnet-4-5-20250929")
    >>> search = SearchRunner(sandbox=sandbox, provider=provider)
    >>> result = await search.run("Find authentication code")
"""

from skillfs.runners.base import AgentResult, AgentRunner, RunnerProvider, RunnerType
from skillfs.runners.providers import AnthropicAgentRunner, AnthropicProvider
from skillfs.runners.types import (
    SearchRunner,
    SearchResult,
    SearchMatch,
    MainRunner,
    create_runner,
    RUNNER_REGISTRY,
)

__all__ = [
    # Base classes and protocols
    "AgentResult",
    "AgentRunner",
    "RunnerProvider",
    "RunnerType",
    # Providers
    "AnthropicAgentRunner",
    "AnthropicProvider",
    # Runner types
    "SearchRunner",
    "SearchResult",
    "SearchMatch",
    "MainRunner",
    "create_runner",
    "RUNNER_REGISTRY",
]
