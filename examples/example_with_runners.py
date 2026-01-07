#!/usr/bin/env python3
"""Example of using Agent with integrated runner.

This shows the simplest way to create a working agent:
1. Create Agent with provider, runner class, and runner config
2. Call agent.load() - this sets up everything including skill injection
3. Call agent.run() - delegates to the configured runner

The example demonstrates:
- MainRunner as the orchestrator agent
- SearchRunner as a subrunner (specialized for codebase search)
- Subrunner configuration options (class directly, dict with class, dict with provider override)
"""

import asyncio
import logging
import os

from skillfs.agents import Agent
from skillfs.sandboxes import E2BSandbox, SandboxConfig
from skillfs.storage.local import LocalBundleStore
from skillfs.runners.providers.anthropic import AnthropicProvider
from skillfs.runners.types import MainRunner, SearchRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


async def main():
    """Run a simple agent example."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    # Create sandbox and storage
    sandbox = E2BSandbox.create(config=SandboxConfig(timeout=300))
    store = LocalBundleStore(directory="/tmp/runner-example")

    try:
        # Create provider - this is shared by main runner and subrunners by default
        # Subrunners can override the provider if needed (see subrunners config below)
        provider = AnthropicProvider(
            api_key=api_key,
            model="claude-sonnet-4-5-20250929",
        )

        # Create agent with everything configured upfront
        agent = Agent(
            agent_id="example-agent",
            sandbox=sandbox,
            store=store,
            # Provider (can be overridden in runner_config or per-subrunner)
            provider=provider,
            # Runner class to use
            runner=MainRunner,
            # Runner configuration
            runner_config={
                "name": "main",
                "description": "Main assistant agent",
                "system_prompt": """You are a helpful assistant that can explore codebases.
Use the available tools to find and read files. If skills are available,
use load_skill to get detailed instructions for specific tasks.""",
                "tools": ["glob", "grep", "read_file", "write_file"],
                # Subrunners can be configured in three ways:
                # 1. Class directly: {"search": SearchRunner}
                #    - Inherits provider from parent
                # 2. Dict with class: {"search": {"class": SearchRunner}}
                #    - Also inherits provider from parent
                # 3. Dict with provider override:
                #    {"search": {"class": SearchRunner, "provider": haiku_provider}}
                #    - Uses the specified provider instead
                "subrunners": {"search": SearchRunner},
            },
            # Optional: load skills from local paths
            # skills={"local": "/path/to/skills"},
            # load_skills=True,
        )

        # Load agent - this:
        # 1. Restores state from storage (or initializes fresh)
        # 2. Sets up MCP servers (if configured)
        # 3. Uploads skills (if configured)
        # 4. Scans for skills and creates skill_catalog
        # 5. Instantiates the runner with auto-injected load_skill tool
        print("Loading agent...")
        await agent.load()

        print(f"Agent loaded: {agent}")
        print(f"Skills discovered: {len(agent.skill_catalog) if agent.skill_catalog else 0}")
        print(f"Runner: {agent.runner}")

        # Run a task - delegates to the configured runner
        # The runner can use tools directly or delegate to subrunners
        print("\nRunning task...")
        result = await agent.run("List all Python files in the repository")

        print(f"\nSuccess: {result.success}")
        print(f"Message: {result.message[:500] if result.message else 'No message'}...")

        # Save state
        print("\nSaving agent state...")
        agent.save(commit_message="Example task completed")

    finally:
        sandbox.close()


if __name__ == "__main__":
    asyncio.run(main())