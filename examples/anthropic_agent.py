#!/usr/bin/env python3
"""Example of using an Agent with Anthropic API.

This script demonstrates how to:
- Initialize an agent with a sandbox and storage
- Expose the agent's run_command as a tool to Claude
- Have Claude execute commands in the sandbox
"""

import asyncio
import logging
import os
from pathlib import Path
from skillfs.storage.local import LocalBundleStore

import anthropic

# Configure logging to see skillfs messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
from skillfs.agents import Agent
from skillfs.sandboxes import E2BSandbox, SandboxConfig
from skillfs.skills import SkillCatalog
# import asyncio
# sandbox = E2BSandbox.create(config=SandboxConfig(timeout=3000))
# store = GCSBundleStore(bucket="dari_dev_test_bucket", prefix="agents/")

# agent = Agent(
#     agent_id="example-agent-001",
#     sandbox=sandbox,
#     store=store,
#     mcp_servers={
#         "playwright": {
#             "command": "npx",
#             "args": ["@playwright/mcp@latest"]
#         }
#     },
#     generate_mcp_tools=True,
# )
# asyncio.run(agent.load())


async def main():
    """Run the Anthropic agent example."""
    # Ensure API keys are set
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    # Initialize the Anthropic client
    client = anthropic.Anthropic(api_key=anthropic_api_key)

    # Create sandbox with environment variables
    print("Creating sandbox...")
    sandbox = E2BSandbox.create(config=SandboxConfig(
        timeout=6000,
        envs={
            'BROWSER_USE_API_KEY': os.environ.get('BROWSER_USE_API_KEY', ''),
            'CDP_ENDPOINT': 'wss://proxy.iad-elated-ellis.onkernel.com:8443/browser/cdp?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3OTc1NzMzNTAsInNlc3Npb24iOnsiaWQiOiJ1bm85bTJlMDUzcnVwczE3dWJ0Y3JpbnYiLCJjZHBQb3J0Ijo5MjIyLCJjZHBXc1BhdGgiOiIiLCJpbnN0YW5jZU5hbWUiOiJicm93c2VyLXN0ZWFsdGgtcHJvZHVjdGlvbi05OTAtYmVjb21pbmctd29sdmVyaW5lLTk3MzIiLCJmcWRuIjoiZmFsbGluZy1sZWFmLXhkdXFwMzlzLnByb2QtaWFkLXVuaWtyYWZ0LTQub25rZXJuZWwuYXBwIiwibWV0cm8iOiJodHRwczovL2FwaS5wcm9kLWlhZC11bmlrcmFmdC00Lm9ua2VybmVsLnJ1bi92MSIsInVzZXJJZCI6InpoOTE4dXlxM3ZtenIxMG14ZHhjanY5biIsIm9yZ0lkIjoib280bnEzZ2I4N2Q5bjYxMnBnaHUzaTBuIiwic3RlYWx0aCI6dHJ1ZSwiaGVhZGxlc3MiOmZhbHNlLCJyZXBsYXlQcmVmaXgiOiJzMzovL2tlcm5lbC1hcGktcHJvZC9zZXNzaW9ucmVwbGF5cy9vbzRucTNnYjg3ZDluNjEycGdodTNpMG4vdW5vOW0yZTA1M3J1cHMxN3VidGNyaW52Iiwia2VybmVsSHR0cFNlcnZlclBvcnQiOjQ0NCwidGltZW91dFNlY29uZHMiOjYwLCJjcmVhdGVkQXQiOiIyMDI1LTEyLTE4VDA1OjU1OjUwLjY5NTQ4ODMzWiIsImltYWdlIjoib25rZXJuZWwva2VybmVsLWN1LXYyNDo0MDhiY2QxIiwic3RlYWx0aFByb3h5SWRlbnRpZmllciI6Ijg3NTY1X25YREZGQDE0MC4yMzMuMjI4Ljg0OjYxMjM0IiwibGl2ZVNsdWciOiJtZUpBYWppRHJHME8iLCJwcml2YXRlSVAiOiIxNzIuMTYuNS40MSJ9fQ.Vo0sizoLxKNxc34ILVHKcaEzylw1VQoxB3snOkYySuU',
        }
    ))

    # Setup storage backend (you can replace this with LocalBundleStore)
    store = LocalBundleStore(directory="/tmp/agent-bundles4", prefix="agents/")

    # Create and load agent
    print("Initializing agent...")
    agent = Agent(
        agent_id="example-agent-009",
        sandbox=sandbox,
        store=store,
        mcp_servers={
            "playwright": {
                "command": "npx",
                "args": [
                    "@playwright/mcp@latest",
                    "--cdp-endpoint",
                    "$CDP_ENDPOINT"
                ]
            },
            "browser-use": {
                "command": "npx",
                "args": [
                    "mcp-remote",
                    "https://api.browser-use.com/mcp",
                    "--header",
                    "X-Browser-Use-API-Key: $BROWSER_USE_API_KEY"
                ]
            }
        },
        generate_mcp_tools=True,
        skills={
            "github": [
                "https://github.com/agentskills/agentskills",
                {
                    "url": "https://github.com/anthropics/claude-cookbooks",
                    "path": "skills/custom_skills/creating-financial-models"
                },
                {
                    "url": "https://github.com/anthropics/claude-cookbooks",
                    "ref": "pedram/fix-notebook-standards",
                    "path": "skills/custom_skills/applying-brand-guidelines"
                }
            ]
        },
        load_skills=True,
    )
    await agent.load()

    print(f"Agent loaded: {agent}")

    # Test skill catalog discovery
    print("\n=== Testing Skill Catalog ===")
    catalog = SkillCatalog(sandbox=sandbox)
    num_skills = await catalog.scan()
    print(f"Discovered {num_skills} skills")

    # Print discovered skills
    for skill in catalog.list_skills():
        print(f"  - {skill.name}: {skill.description}")
        if skill.short_description:
            print(f"    (short: {skill.short_description})")
        print(f"    location: {skill.location}")

    # Print formatted tool description
    print("\n=== Tool Description Format ===")
    print(catalog.format_for_tool_description())

    # Test loading full skill content
    if catalog.list_skills():
        test_skill_name = catalog.list_skills()[0].name
        print(f"\n=== Loading Full Skill: {test_skill_name} ===")
        full_content = catalog.get_skill(test_skill_name)
        if full_content:
            # Show first 500 chars to verify it loaded
            print(f"Content length: {len(full_content)} chars")
            print(f"Preview:\n{full_content[:500]}...")
        else:
            print("Failed to load skill content")

    print("=== End Skill Catalog Test ===\n")

    # Define the tool schema for Claude
    tools = [
        {
            "name": "run_command",
            "description": "Execute a shell command in the agent's sandbox environment. Returns stdout, stderr, and exit code.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute (e.g., 'ls -la', 'cat file.txt', 'python script.py')",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory for the command",
                    },
                },
                "required": ["command"],
            },
        },
    ]

    # System prompt that explains the agent's capabilities and context
    repo_root = agent.repo_root
    system_prompt = f"""You are an AI assistant with access to a persistent sandbox environment through the SkillFS agent framework.

ENVIRONMENT SETUP:
- You have access to a live E2B sandbox (cloud-based Linux container)
- The sandbox has a Git repository initialized at {repo_root}
- The repo is set up with uv (Python package manager) and has a virtual environment
- MCP servers are set up and their tools are available at src/servers/
- The skillfs package is installed and available for imports
- All your work is automatically versioned and can persist across sessions

CRITICAL: ALWAYS USE UV TO RUN PYTHON
- ALWAYS run Python code with: uv run python ...
- ALWAYS run Python modules with: uv run python -m <module>
- NEVER use bare `python` or `python3` commands - they won't have the right environment
- The virtual environment is managed by uv, so all commands must go through it

CAPABILITIES:
- You can execute ANY shell command via the run_command tool
- You have full read/write access to the filesystem
- You can install packages with: uv add <package>
- Python, Node.js, and common dev tools are pre-installed
- MCP tools are available as Python modules in src/servers/

WORKING DIRECTORY STRUCTURE:
{repo_root}/
├── src/
│   ├── skills/          # Custom agent skills/capabilities
│   ├── servers/         # MCP server tool wrappers (e.g., playwright, browser_use)
│   └── __init__.py
├── pyproject.toml       # Project config - managed by uv
└── .venv/               # Virtual environment - managed by uv

IMPORTING MCP SERVERS:
MCP server tools are in src/servers/<server_name>/. To use them:
1. Import the server module: from src.servers.<server_name> import connect_<server_name>, disconnect_<server_name>, <tool_name>
2. Connect first: await connect_<server_name>()
3. Use tools: result = await <tool_name>(...)
4. Disconnect when done: await disconnect_<server_name>()

Note: Each server has its own connect/disconnect functions (e.g., connect_playwright, connect_browser_use)
so you can use multiple MCP servers in the same script without naming conflicts.

EXAMPLES:
- List files: run_command("ls -la {repo_root}/src/servers")
- Run a Python script: run_command("cd {repo_root} && uv run python my_script.py")
- Run a module: run_command("cd {repo_root} && uv run python -m src.skills.my_skill")
- Add a package: run_command("cd {repo_root} && uv add requests")
- Test MCP server: run_command("cd {repo_root} && uv run python -c 'from src.servers.playwright import connect_playwright; print(connect_playwright)'")

REQUIREMENTS:
- When you are writing new scripts, write them in skills/ and import server stuff as from src.servers.xxx import ...
- When the user asks you to do a task which requires tools, check the servers you have access to and the skills you have access to. If you don't see the necessary tools, tell that to the user. Do not ever try to download new packages or install new packages.
- Do things incrementally. For instance do not just write one mega script - do it in line Python first, make sure it works, and THEN save the script to skills/

BEST PRACTICES:
1. ALWAYS use `uv run python` to run Python code
2. Use run_command to explore before making changes (ls, cat, etc.)
3. Import using absolute paths: from src.servers.xxx import ...
4. The repo is a Git repository - all changes are tracked

When the session ends, all your work will be committed to the Git repo and saved to persistent storage."""

    # Initialize conversation with system prompt
    messages = []

    print("\n=== Agent Ready ===")
    print("Claude has access to the sandbox environment.")
    print("Type your requests (or 'quit' to exit)\n")
    print(f"System context: Persistent E2B sandbox with Git repo at {repo_root}")
    print("Available: Python, Node.js, MCP servers (Playwright), run_command tool\n")

    while True:
        # Get user input
        user_input = input("You: ").strip()
        if user_input.lower() in ["quit", "exit", "q"]:
            break

        if not user_input:
            continue

        # Add user message (include system prompt on first turn)
        if len(messages) == 0:
            messages.append({"role": "user", "content": f"{system_prompt}\n\nUser request: {user_input}"})
        else:
            messages.append({"role": "user", "content": user_input})

        # Call Claude API and handle tool loop
        print("\nClaude: ", end="", flush=True)

        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            tools=tools,
            messages=messages,
        )

        # Keep processing tool calls until we get a final text response
        while response.stop_reason == "tool_use":
            # Collect all content blocks from this response
            assistant_content = []
            tool_results = []

            for block in response.content:
                assistant_content.append(block)

                if block.type == "text":
                    print(block.text, end="", flush=True)
                elif block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    if tool_name == "run_command":
                        command = tool_input.get("command")
                        cwd = tool_input.get("cwd")

                        print(f"\n[Executing: {command}]", flush=True)

                        # Run the command in the agent's sandbox
                        result = agent.run_command(command, cwd=cwd)

                        # Prepare tool result
                        tool_result = {
                            "stdout": result.logs,
                            "stderr": result.error or "",
                            "exit_code": result.exit_code,
                        }

                        print(f"[Exit code: {result.exit_code}]", flush=True)
                        if result.logs:
                            print(f"[Output preview: {result.logs[:200]}...]", flush=True)

                        # Collect tool result
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(tool_result),
                        })

            # Add assistant message with all content (text + tool uses)
            messages.append({"role": "assistant", "content": assistant_content})

            # Add all tool results as a single user message
            messages.append({"role": "user", "content": tool_results})

            # Get next response from Claude
            print("\nClaude: ", end="", flush=True)
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                tools=tools,
                messages=messages,
            )

        # Process final text response (no more tool calls)
        final_content = []
        for block in response.content:
            final_content.append(block)
            if block.type == "text":
                print(block.text, flush=True)

        # Add final assistant message
        messages.append({"role": "assistant", "content": final_content})
        print()

    # Save agent state
    print("\nSaving agent state...")
    agent.save(commit_message="Session completed")

    # Cleanup
    print("Closing sandbox...")
    sandbox.close()

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
