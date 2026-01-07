#!/usr/bin/env python3
"""Test the git_commit tool.

This script demonstrates how to use the git_commit tool to checkpoint agent work.
"""

import asyncio
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")

from skillfs.agents import Agent
from skillfs.sandboxes import E2BSandbox, SandboxConfig
from skillfs.storage.local import LocalBundleStore
from skillfs.runners.types.main import MainRunner
from skillfs.runners.providers.anthropic import AnthropicProvider


async def main():
    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Set ANTHROPIC_API_KEY environment variable")

    # Create sandbox
    print("Creating sandbox...")
    sandbox = E2BSandbox.create(config=SandboxConfig(timeout=300))

    # Local storage for bundles
    store = LocalBundleStore(directory="/tmp/test-git-commit", prefix="agents/")

    # Create provider
    provider = AnthropicProvider(api_key=api_key, model="claude-sonnet-4-20250514")

    # Create agent with git_commit enabled
    print("Creating agent...")
    agent = Agent(
        agent_id="git-commit-test",
        sandbox=sandbox,
        store=store,
        provider=provider,
        runner=MainRunner,
        runner_config={
            "name": "test_runner",
            "description": "Test runner with git_commit",
            "system_prompt": """You are a helpful assistant with access to a sandbox.
You can create files, edit them, and use git_commit to save your work.
When you make changes, use git_commit to checkpoint your progress.""",
            "tools": ["glob", "read_file", "write_file", "run_command"],
            "max_turns": 10,
        },
        enable_git_commit=True,  # <-- This injects the git_commit tool
    )

    # Load agent (initializes repo, injects tools)
    print("Loading agent...")
    await agent.load()

    print(f"\nAgent loaded. Runner tools: {[t['name'] for t in agent.runner.tools]}")

    # Run a task that creates files and commits
    print("\n--- Running task ---")
    result = await agent.run(
        "Create a file called hello.py with a simple hello world function, "
        "then use git_commit to save your work."
    )

    print(f"\n--- Result ---")
    print(f"Success: {result.success}")
    print(f"Message: {result.message}")

    # Check what happened
    print("\n--- Checking repo state ---")
    log_result = sandbox.run_command("cd /home/user/repo && git log --oneline -3")
    print(f"Git log:\n{log_result.logs}")

    status_result = sandbox.run_command("cd /home/user/repo && git status")
    print(f"Git status:\n{status_result.logs}")

    # Cleanup
    print("\nClosing sandbox...")
    sandbox.close()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
