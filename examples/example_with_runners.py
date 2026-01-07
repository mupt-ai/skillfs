#!/usr/bin/env python3
"""Using runners alongside a persistent workspace.

Workspace handles persistence. Runner handles the LLM loop.
They share the same sandbox but are separate concerns.
"""

import asyncio
import logging
import os

from skillfs.workspaces import Workspace
from skillfs.sandboxes import E2BSandbox, SandboxConfig
from skillfs.storage import LocalBundleStore
from skillfs.runners import AnthropicProvider, MainRunner, SearchRunner

logging.basicConfig(level=logging.INFO)


async def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    sandbox = E2BSandbox.create(config=SandboxConfig(timeout=300))
    store = LocalBundleStore(directory="/tmp/runner-example")

    try:
        # Workspace: persistence
        workspace = Workspace(
            workspace_id="runner-example",
            sandbox=sandbox,
            store=store,
        )
        await workspace.load()

        # Runner: LLM loop (uses same sandbox)
        provider = AnthropicProvider(api_key=api_key, model="claude-sonnet-4-5-20250929")
        runner = MainRunner(
            name="assistant",
            description="Helpful assistant",
            system_prompt="You are a helpful assistant.",
            sandbox=sandbox,
            provider=provider,
            tools=["glob", "grep", "read_file", "write_file"],
            subrunners={"search": SearchRunner},
        )

        # Run task
        result = await runner.run("List all files and create summary.txt")
        print(f"Result: {result.message[:200]}...")

        # Save workspace
        workspace.save(commit_message="Task completed")

    finally:
        sandbox.close()


if __name__ == "__main__":
    asyncio.run(main())
