"""Search runner - specialized agent for codebase search tasks.

SearchRunner extends MainRunner with:
- Fixed configuration (name, tools, system prompt, output schema)
- Structured output parsing (JSON -> SearchResult dataclass)

This demonstrates how to create specialized runners by extending MainRunner
with domain-specific configuration and result handling.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from skillfs.runners.base import AgentResult, RunnerProvider
from skillfs.runners.types.main import MainRunner
from skillfs.runners.types.search.system_prompt import SYSTEM_PROMPT
from skillfs.sandboxes.base import SandboxConnection

# Runner metadata (class-level constants)
NAME = "search"
DESCRIPTION = "Searches codebase for files and patterns, returns annotated results with relevance explanations"

# Tools this runner uses
TOOLS = ["glob", "grep", "read_file"]

# JSON schema for structured output
OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "description": "List of file matches with relevance explanations",
            "items": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file",
                    },
                    "relevance": {
                        "type": "string",
                        "description": "Brief explanation of why this file is relevant",
                    },
                    "line_numbers": {
                        "type": ["array", "null"],
                        "description": "Specific line numbers of interest (optional)",
                        "items": {"type": "integer"},
                    },
                    "snippet": {
                        "type": ["string", "null"],
                        "description": "Code snippet or excerpt (optional)",
                    },
                },
                "required": ["path", "relevance", "line_numbers", "snippet"],
                "additionalProperties": False,
            },
        },
        "summary": {
            "type": "string",
            "description": "Brief summary of what was found",
        },
    },
    "required": ["matches", "summary"],
    "additionalProperties": False,
}


@dataclass
class SearchMatch:
    """A search result with relevance annotation."""

    path: str
    """Absolute path to the file."""

    relevance: str
    """Description of why this file is relevant to the query."""

    line_numbers: Optional[List[int]] = None
    """Specific line numbers of interest (optional)."""

    snippet: Optional[str] = None
    """Code snippet or excerpt (optional)."""


@dataclass
class SearchResult:
    """Structured search results from SearchRunner."""

    matches: List[SearchMatch]
    """Files/locations that match the search query."""

    summary: str
    """Brief summary of what was found."""

    query: str
    """The original search query."""


class SearchRunner(MainRunner):
    """A specialized runner for intelligent codebase search.

    SearchRunner extends MainRunner with fixed configuration for search tasks:
    - Uses glob, grep, and read_file tools
    - Returns structured JSON output matching OUTPUT_SCHEMA
    - Parses results into SearchResult dataclass

    The run() method is overridden to parse the JSON response into
    a typed SearchResult object stored in AgentResult.data.

    Example:
        >>> from skillfs.runners.providers import AnthropicProvider
        >>> provider = AnthropicProvider(api_key="sk-ant-...", model="claude-sonnet-4-5-20250929")
        >>> search = SearchRunner(sandbox=sandbox, provider=provider)
        >>> result = await search.run("Find all authentication handlers")
        >>> if result.success:
        ...     for match in result.data.matches:
        ...         print(f"{match.path}: {match.relevance}")
    """

    # Class-level metadata for registration
    name = NAME
    description = DESCRIPTION

    def __init__(
        self,
        sandbox: SandboxConnection,
        provider: RunnerProvider,
        max_turns: int = 20,
    ):
        """Initialize the search runner.

        Args:
            sandbox: Active sandbox connection for file operations.
            provider: RunnerProvider for creating the underlying agent.
            max_turns: Maximum turns for search (default: 20).
        """
        # Initialize MainRunner with fixed search configuration
        super().__init__(
            name=NAME,
            description=DESCRIPTION,
            system_prompt=SYSTEM_PROMPT,
            sandbox=sandbox,
            provider=provider,
            tools=TOOLS,
            subrunners=None,
            max_turns=max_turns,
            output_schema=OUTPUT_SCHEMA,
        )

    async def run(self, query: str) -> AgentResult:
        """Search the codebase based on the query.

        Overrides MainRunner.run() to parse the JSON response into
        a SearchResult dataclass stored in AgentResult.data.

        Args:
            query: Natural language search query (e.g., "Find authentication handlers")

        Returns:
            AgentResult with SearchResult in `data` field containing matches and summary.
        """
        # Run the parent's run() to execute the search
        result = await super().run(query)

        # Parse and return structured result
        return self._parse_result(result, query)

    def _parse_result(self, result: AgentResult, query: str) -> AgentResult:
        """Parse the agent's JSON response into AgentResult with SearchResult.

        With structured outputs enabled, result.message contains valid JSON
        matching OUTPUT_SCHEMA. Falls back to raw message if JSON parsing fails.
        """
        if not result.success:
            return AgentResult(
                success=False,
                message=result.message,
                data=SearchResult(
                    matches=[],
                    summary=f"Search failed: {result.message}",
                    query=query,
                ),
                errors=result.errors,
                metadata=result.metadata,
                messages=result.messages,
            )

        message = result.message or ""

        # With structured outputs, message is valid JSON
        try:
            data = json.loads(message)
            matches = [
                SearchMatch(
                    path=m.get("path", ""),
                    relevance=m.get("relevance", ""),
                    line_numbers=m.get("line_numbers"),
                    snippet=m.get("snippet"),
                )
                for m in data.get("matches", [])
            ]
            search_result = SearchResult(
                matches=matches,
                summary=data.get("summary", "Search completed"),
                query=query,
            )
            return AgentResult(
                success=True,
                message=search_result.summary,
                data=search_result,
                metadata=result.metadata,
                messages=result.messages,
            )
        except json.JSONDecodeError:
            # Fallback: return the raw message as summary
            return AgentResult(
                success=True,
                message=message,
                data=SearchResult(
                    matches=[],
                    summary=message,
                    query=query,
                ),
                metadata=result.metadata,
                messages=result.messages,
            )