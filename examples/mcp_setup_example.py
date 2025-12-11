"""Example: Setting up an agent with MCP servers.

This example demonstrates how to create an agent and configure it with
MCP (Model Context Protocol) servers. The agent will automatically generate
Python wrapper files for all tools provided by the configured servers.
"""

import asyncio
import logging
from pathlib import Path

from skillfs.agents import Agent
from skillfs.sandboxes import E2BSandbox
from skillfs.storage import GCSBundleStore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Main example function demonstrating MCP server setup."""

    # Define MCP server configuration
    # This will setup the Playwright MCP server
    mcp_servers = {
        "playwright": {
            "command": "npx",
            "args": ["@playwright/mcp@latest"]
        }
    }

    # Create sandbox connection
    logger.info("Creating E2B sandbox...")
    sandbox = E2BSandbox.create()

    try:
        # Create storage backend
        # Replace with your actual GCS bucket or use a different storage backend
        store = GCSBundleStore(bucket="dari_dev_test_bucket", prefix="dev/")

        # Create agent with MCP server configurations
        logger.info("Creating agent with MCP server configurations...")
        agent = Agent(
            agent_id="test-agent-123",
            sandbox=sandbox,
            store=store,
            mcp_servers=mcp_servers,  # Pass MCP servers config
            generate_mcp_tools=True   # Enable MCP tool generation
        )

        # Load agent state
        # This will:
        # 1. Load or initialize the agent's Git repository
        # 2. Fetch tools from the Playwright MCP server
        # 3. Generate Python wrapper files in src/servers/playwright/
        logger.info("Loading agent state and setting up MCP servers...")
        await agent.load()

        logger.info("Agent loaded successfully!")
        logger.info(f"MCP server tools are now available in {agent.repo_root}/src/servers/")

        # List the generated files
        result = sandbox.run_command(f"ls -la {agent.repo_root}/src/servers/playwright/")
        logger.info("Generated Playwright tool files:")
        logger.info(result.logs)

        # Show the __init__.py to see what tools are exported
        result = sandbox.run_command(f"cat {agent.repo_root}/src/servers/playwright/__init__.py")
        logger.info("Playwright module exports:")
        logger.info(result.logs)

        # Save the agent state with all generated MCP tool files
        logger.info("Saving agent state...")
        agent.save(commit_message="Added Playwright MCP server tool wrappers")

        logger.info("Example completed successfully!")

    finally:
        # Cleanup
        logger.info("Cleaning up sandbox...")
        sandbox.close()


if __name__ == "__main__":
    asyncio.run(main())
