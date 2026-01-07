#!/usr/bin/env python3
"""Browser automation with persistent workspace.

Workspace handles persistence. Runner handles the LLM loop.
Runner has git_commit tool to checkpoint progress.
"""

import asyncio
import os

from skillfs.workspaces import Workspace
from skillfs.sandboxes import E2BSandbox, SandboxConfig
from skillfs.storage import LocalBundleStore
from skillfs.runners import AnthropicProvider, MainRunner


async def main():
    workspace_id = "browser-workspace-001"

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError("Set ANTHROPIC_API_KEY environment variable")
    if not os.environ.get("E2B_API_KEY"):
        raise ValueError("Set E2B_API_KEY environment variable")

    print(f"Creating workspace: {workspace_id}")

    sandbox = E2BSandbox.create(config=SandboxConfig(timeout=600, metadata={"template": "5zyyp525hzjfs85z2ov8"}))

    store = LocalBundleStore(directory="/tmp/skillfs-workspaces")

    # Workspace: persistence + MCP setup
    workspace = Workspace(
        workspace_id=workspace_id,
        sandbox=sandbox,
        store=store,
        mcp_servers={
            "playwright": {
                "command": "npx",
                "args": ["@playwright/mcp@latest"],
            }
        },
        generate_mcp_tools=True,
    )

    print("Loading workspace...")
    await workspace.load()
    print(f"Workspace loaded. Repo at: {workspace.repo_root}")

    # Runner: LLM loop
    provider = AnthropicProvider(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        model="claude-sonnet-4-5-20250929",
    )

    runner = MainRunner(
        name="browser",
        description="Browser automation agent",
        system_prompt=f"""You are a browser automation agent with access to Playwright.

Your workspace is a persistent git repository at {workspace.repo_root}.

MCP servers are available at src/servers/. To use Playwright:
1. Write a Python script that imports from src.servers.playwright
2. Run it with: uv run python your_script.py

Use git_commit to save your progress after completing significant work.
""",
        sandbox=sandbox,
        provider=provider,
        tools=["glob", "grep", "read_file", "write_file", "edit_file", "run_command"],
    )

    # Add commit tool from workspace
    runner.add_tool(workspace.get_commit_tool())

    # Task
    task = """
    Check if a Hacker News scraper script already exists in the repo.

    If it does, just run it and show me the results.

    If it doesn't exist, create a script that:
    1. Opens https://news.ycombinator.com
    2. Takes a snapshot of the page
    3. Extracts the top 5 story titles
    4. Saves them to hn_top_stories.txt

    Then run the script, show me the results, and commit your work.
    """

    print("\nRunning task...")
    result = await runner.run(task)

    print(f"\n{'='*60}")
    print("RESULT:")
    print(f"{'='*60}")
    print(result.message)

    sandbox.close()


if __name__ == "__main__":
    asyncio.run(main())
