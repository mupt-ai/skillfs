"""Specialized runner types for specific tasks.

Runner types are provider-agnostic - they define the system prompts,
tools, and behavior, but can be used with any LLM provider.

Each runner type has:
- NAME: Unique identifier for registration
- DESCRIPTION: What the runner does
- A runner class that accepts a provider

MainRunner is a configurable template that can be customized at
instantiation without subclassing.
"""

from skillfs.runners.types.search import SearchRunner, SearchResult, SearchMatch
from skillfs.runners.types.main import MainRunner, create_runner

# Registry of built-in runner types
# MainRunner is not included since it's configured per-instance
RUNNER_REGISTRY = {
    "search": SearchRunner,
}

__all__ = [
    # Search runner
    "SearchRunner",
    "SearchResult",
    "SearchMatch",
    # Main/template runner
    "MainRunner",
    "create_runner",
    # Registry
    "RUNNER_REGISTRY",
]
