"""Anthropic-specific implementation of AgentRunner.

This module provides AnthropicAgentRunner, which implements the agentic loop
using the Anthropic API (Claude models).
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import anthropic

from skillfs.runners.base import AgentResult, AgentRunner, RunnerProvider, ToolHandler

logger = logging.getLogger(__name__)


class AnthropicAgentRunner(AgentRunner):
    """AgentRunner implementation using the Anthropic API.

    Implements the agentic loop for Claude models. Handles:
    - Anthropic message format
    - Tool use blocks and tool_result responses
    - Stop reason detection (tool_use vs end_turn)

    Example:
        >>> runner = AnthropicAgentRunner(
        ...     client=anthropic.Anthropic(),
        ...     model="claude-sonnet-4-5-20250929",
        ...     system_prompt="You are a helpful assistant...",
        ...     tools=[{
        ...         "name": "search",
        ...         "description": "Search for files",
        ...         "input_schema": {"type": "object", "properties": {...}}
        ...     }],
        ...     tool_handlers={"search": lambda **kw: do_search(**kw)},
        ... )
        >>> result = await runner.run("Find all config files")
    """

    # Beta header for structured outputs
    STRUCTURED_OUTPUTS_BETA = "structured-outputs-2025-11-13"

    def __init__(
        self,
        client: anthropic.Anthropic,
        model: str,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        tool_handlers: Dict[str, ToolHandler],
        max_turns: int = 50,
        max_tokens: int = 4096,
        output_schema: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the Anthropic agent runner.

        Args:
            client: Anthropic API client instance.
            model: Model ID (e.g., "claude-sonnet-4-5-20250929").
            system_prompt: System instructions for the agent.
            tools: List of Anthropic tool definitions with name, description, input_schema.
            tool_handlers: Dict mapping tool names to handler functions.
            max_turns: Maximum conversation turns before stopping.
            max_tokens: Maximum tokens per response.
            output_schema: Optional JSON schema for structured output.
                          When provided, uses Anthropic's structured outputs beta
                          to guarantee valid JSON matching the schema.
        """
        super().__init__(
            system_prompt=system_prompt,
            tools=tools,
            tool_handlers=tool_handlers,
            max_turns=max_turns,
        )
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.output_schema = output_schema

    async def run(
        self,
        task: str,
        *,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentResult:
        """Run the agent loop with the given task.

        Args:
            task: The task or query for the agent to process.
            initial_messages: Optional existing conversation to continue from.

        Returns:
            AgentResult with the final response and conversation history.
        """
        # Initialize conversation
        if initial_messages:
            messages = list(initial_messages)
            messages.append({"role": "user", "content": task})
        else:
            messages = [{"role": "user", "content": task}]

        turns_used = 0
        tools_called: List[str] = []
        timing_stats: Dict[str, List[float]] = {"llm_calls": [], "tool_calls": {}}

        for turn in range(self.max_turns):
            turns_used = turn + 1

            try:
                # Run sync client in thread pool to avoid blocking event loop
                llm_start = time.time()
                if self.output_schema:
                    # Use beta endpoint for structured outputs
                    response = await asyncio.to_thread(
                        self.client.beta.messages.create,
                        model=self.model,
                        max_tokens=self.max_tokens,
                        system=self.system_prompt,
                        tools=self.tools,
                        messages=messages,
                        betas=[self.STRUCTURED_OUTPUTS_BETA],
                        output_format={
                            "type": "json_schema",
                            "schema": self.output_schema,
                        },
                    )
                else:
                    response = await asyncio.to_thread(
                        self.client.messages.create,
                        model=self.model,
                        max_tokens=self.max_tokens,
                        system=self.system_prompt,
                        tools=self.tools,
                        messages=messages,
                    )
            except anthropic.APIError as e:
                logger.error(f"API error on turn {turn}: {e}")
                return AgentResult(
                    success=False,
                    message=f"API error: {e}",
                    errors=[str(e)],
                    metadata={"turns_used": turns_used, "tools_called": tools_called},
                    messages=messages,
                )

            llm_time = time.time() - llm_start
            timing_stats["llm_calls"].append(llm_time)
            print(f"[TIMING] Turn {turn + 1} LLM call: {llm_time:.2f}s")

            # Check if we're done (no more tool calls)
            if response.stop_reason != "tool_use":
                return self._extract_final_result(
                    response,
                    messages,
                    turns_used,
                    tools_called,
                )

            # Process tool calls
            assistant_content = []
            tool_results = []

            for block in response.content:
                assistant_content.append(block)

                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tools_called.append(tool_name)

                    logger.debug(f"Turn {turn}: calling tool {tool_name}")

                    # Execute the tool handler
                    tool_start = time.time()
                    is_error = False
                    try:
                        handler = self.tool_handlers.get(tool_name)
                        if handler:
                            result = await self._call_handler(handler, tool_input)
                            # Check if handler returned an error dict
                            if isinstance(result, dict) and "error" in result:
                                is_error = True
                        else:
                            result = f"Unknown tool: {tool_name}"
                            is_error = True
                            logger.warning(f"Unknown tool requested: {tool_name}")
                    except Exception as e:
                        logger.error(f"Tool {tool_name} failed: {e}")
                        result = str(e)
                        is_error = True

                    tool_time = time.time() - tool_start
                    if tool_name not in timing_stats["tool_calls"]:
                        timing_stats["tool_calls"][tool_name] = []
                    timing_stats["tool_calls"][tool_name].append(tool_time)
                    print(f"[TIMING] Tool {tool_name}: {tool_time:.2f}s")

                    # Collect tool result with is_error flag per Anthropic API spec
                    tool_result_block: Dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": self._serialize_result(result),
                    }
                    if is_error:
                        tool_result_block["is_error"] = True
                    tool_results.append(tool_result_block)

            # Add assistant message with all content (serialize for JSON compatibility)
            messages.append({"role": "assistant", "content": self._serialize_content(assistant_content)})

            # Add tool results as user message
            messages.append({"role": "user", "content": tool_results})

        # Hit max turns
        logger.warning(f"Agent hit max_turns limit ({self.max_turns})")
        return AgentResult(
            success=False,
            message=f"Agent stopped after {self.max_turns} turns without completing",
            metadata={"turns_used": turns_used, "tools_called": tools_called},
            messages=messages,
        )

    def _serialize_result(self, result: Any) -> str:
        """Serialize a tool result for the Anthropic API."""
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, default=str)
        except (TypeError, ValueError):
            return str(result)

    def _content_block_to_dict(self, block: Any) -> Dict[str, Any]:
        """Convert an Anthropic ContentBlock to a serializable dict.

        Handles TextBlock and ToolUseBlock from the Anthropic SDK.
        This ensures messages are JSON-serializable for logging and fine-tuning.

        TextBlock structure: {type: "text", text: str}
        ToolUseBlock structure: {type: "tool_use", id: str, name: str, input: dict}

        Note: We explicitly extract only the expected fields because model_dump()
        may include extra fields (like 'caller') that the API rejects.

        See: https://github.com/anthropics/anthropic-sdk-python
        """
        # Get block type (works for both dict and object)
        if isinstance(block, dict):
            block_type = block.get("type", "unknown")
        else:
            block_type = getattr(block, "type", "unknown")

        # Extract only the fields the API expects for each block type
        if block_type == "text":
            text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
            return {"type": "text", "text": text}

        elif block_type == "tool_use":
            if isinstance(block, dict):
                return {
                    "type": "tool_use",
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "input": block.get("input", {}),
                }
            else:
                return {
                    "type": "tool_use",
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}),
                }

        # Fallback for unknown block types
        if isinstance(block, dict):
            return block
        elif hasattr(block, "model_dump"):
            return block.model_dump()
        elif hasattr(block, "dict"):
            return block.dict()
        else:
            return {"type": block_type}

    def _serialize_content(self, content: List[Any]) -> List[Dict[str, Any]]:
        """Convert a list of ContentBlocks to serializable dicts."""
        return [self._content_block_to_dict(block) for block in content]

    def _extract_final_result(
        self,
        response: anthropic.types.Message,
        messages: List[Dict[str, Any]],
        turns_used: int,
        tools_called: List[str],
    ) -> AgentResult:
        """Extract the final result from a completed response."""
        # Collect text content
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)

        final_text = "\n".join(text_parts)

        # Add final assistant message to history (serialize for JSON compatibility)
        messages.append({"role": "assistant", "content": self._serialize_content(response.content)})

        return AgentResult(
            success=True,
            message=final_text,
            metadata={
                "turns_used": turns_used,
                "tools_called": tools_called,
                "stop_reason": response.stop_reason,
            },
            messages=messages,
        )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"AnthropicAgentRunner(model={self.model}, "
            f"tools={[t['name'] for t in self.tools]}, "
            f"max_turns={self.max_turns})"
        )


class AnthropicProvider(RunnerProvider):
    """RunnerProvider implementation for Anthropic/Claude models.

    Creates AnthropicAgentRunner instances with pre-configured client and model.

    Example:
        >>> provider = AnthropicProvider(
        ...     api_key="sk-ant-...",
        ...     model="claude-sonnet-4-5-20250929",
        ... )
        >>> # Now use this provider with any runner type
        >>> search = SearchRunner(sandbox=sandbox, provider=provider)
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
    ):
        """Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key.
            model: Model ID to use for all runners.
            max_tokens: Maximum tokens per response.
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def create_runner(
        self,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        tool_handlers: Dict[str, ToolHandler],
        max_turns: int = 50,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> AnthropicAgentRunner:
        """Create an AnthropicAgentRunner with the given configuration.

        Args:
            system_prompt: System instructions for the agent.
            tools: List of Anthropic tool definitions.
            tool_handlers: Dict mapping tool names to handler functions.
            max_turns: Maximum conversation turns before stopping.
            output_schema: Optional JSON schema for structured output.

        Returns:
            Configured AnthropicAgentRunner instance.
        """
        return AnthropicAgentRunner(
            client=self.client,
            model=self.model,
            system_prompt=system_prompt,
            tools=tools,
            tool_handlers=tool_handlers,
            max_turns=max_turns,
            max_tokens=self.max_tokens,
            output_schema=output_schema,
        )

    def __repr__(self) -> str:
        return f"AnthropicProvider(model={self.model})"
