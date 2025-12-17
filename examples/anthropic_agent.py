#!/usr/bin/env python3
"""Example of using an Agent with Anthropic API.

This script demonstrates how to:
- Initialize an agent with a sandbox and storage
- Expose the agent's run_command as a tool to Claude
- Have Claude execute commands in the sandbox
"""

import asyncio
import os
from pathlib import Path
from skillfs.storage.local import LocalBundleStore

import anthropic
from skillfs.agents import Agent
from skillfs.sandboxes import E2BSandbox, SandboxConfig
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

    # Create sandbox
    print("Creating sandbox...")
    sandbox = E2BSandbox.create(config=SandboxConfig(timeout=3000))

    # Setup storage backend (you can replace this with LocalBundleStore)
    store = LocalBundleStore(directory="/tmp/agent-bundles2", prefix="agents/")

    # Create and load agent
    print("Initializing agent...")
    agent = Agent(
        agent_id="example-agent-001",
        sandbox=sandbox,
        store=store,
        mcp_servers={
            "playwright": {
                "command": "npx",
                "args": [
                    "@playwright/mcp@latest",
                    "--cdp-endpoint",
                    "wss://proxy.iad-elated-ellis.onkernel.com:8443/browser/cdp?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3OTc0NTg3MTYsInNlc3Npb24iOnsiaWQiOiJsdDRhNDZvbHU5bGNydXlhNXpjMnZrZ3MiLCJjZHBQb3J0Ijo5MjIyLCJjZHBXc1BhdGgiOiIiLCJpbnN0YW5jZU5hbWUiOiJicm93c2VyLXN0ZWFsdGgtcHJvZHVjdGlvbi0xOTY5LW1heGltdW0tZ2FyZ2FudGEtMTAzNyIsImZxZG4iOiJ0aHJvYmJpbmctd2F0ZXItdGRmaGpjMG4ucHJvZC1pYWQtdW5pa3JhZnQtNC5vbmtlcm5lbC5hcHAiLCJtZXRybyI6Imh0dHBzOi8vYXBpLnByb2QtaWFkLXVuaWtyYWZ0LTQub25rZXJuZWwucnVuL3YxIiwidXNlcklkIjoiemg5MTh1eXEzdm16cjEwbXhkeGNqdjluIiwib3JnSWQiOiJvbzRucTNnYjg3ZDluNjEycGdodTNpMG4iLCJzdGVhbHRoIjp0cnVlLCJoZWFkbGVzcyI6ZmFsc2UsInJlcGxheVByZWZpeCI6InMzOi8va2VybmVsLWFwaS1wcm9kL3Nlc3Npb25yZXBsYXlzL29vNG5xM2diODdkOW42MTJwZ2h1M2kwbi9sdDRhNDZvbHU5bGNydXlhNXpjMnZrZ3MiLCJrZXJuZWxIdHRwU2VydmVyUG9ydCI6NDQ0LCJ0aW1lb3V0U2Vjb25kcyI6NjAsImNyZWF0ZWRBdCI6IjIwMjUtMTItMTZUMjI6MDU6MTYuNzI2NzUxNDQzWiIsImltYWdlIjoib25rZXJuZWwva2VybmVsLWN1LXYyNDo0MDhiY2QxIiwic3RlYWx0aFByb3h5SWRlbnRpZmllciI6Ijg3NTY1X25YREZGQDIwNC4yNDIuMTc2LjU5OjYxMjM0IiwibGl2ZVNsdWciOiJ1NHFXMDE2Nm4yRTYiLCJwcml2YXRlSVAiOiIxNzIuMTYuMy4xMDUifX0.ODJ5NfJNQ5Bv91Pxm-bEdTx4saSLMYVtIsut9ugwJo0"
                ]
            },
            "browser-use": {
                "command": "npx",
                "args": [
                    "mcp-remote",
                    "https://api.browser-use.com/mcp",
                    "--header",
                    "X-Browser-Use-API-Key: bu_863ra40sgy4lKyyDnoda17nXYuevAHJ_mV11Kifm1vE"
                ]
            }
        },
        generate_mcp_tools=True,
    )
    await agent.load()

    print(f"Agent loaded: {agent}")

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
    system_prompt = """You are an AI assistant with access to a persistent sandbox environment through the SkillFS agent framework.

ENVIRONMENT SETUP:
- You have access to a live E2B sandbox (cloud-based Linux container)
- The sandbox has a Git repository initialized at /home/user/repo
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
/home/user/repo/
├── src/
│   ├── skillfs/         # SkillFS framework (connection managers, etc.)
│   ├── skills/          # Custom agent skills/capabilities
│   ├── servers/         # MCP server tool wrappers (e.g., playwright, browser_use)
│   └── __init__.py
├── tests/
├── pyproject.toml       # Project config - managed by uv
└── .venv/               # Virtual environment - managed by uv

IMPORTING MCP SERVERS:
MCP server tools are in src/servers/<server_name>/. To use them:
1. Import the server module: from src.servers.<server_name> import connect, disconnect, <tool_name>
2. Connect first: await connect()
3. Use tools: result = await <tool_name>(...)
4. Disconnect when done: await disconnect()

EXAMPLES:
- List files: run_command("ls -la /home/user/repo/src/servers")
- Run a Python script: run_command("cd /home/user/repo && uv run python my_script.py")
- Run a module: run_command("cd /home/user/repo && uv run python -m src.skills.my_skill")
- Add a package: run_command("cd /home/user/repo && uv add requests")
- Test MCP server: run_command("cd /home/user/repo && uv run python -c 'from src.servers.playwright import connect; print(connect)'")

BEST PRACTICES:
1. ALWAYS use `uv run python` to run Python code
2. Use run_command to explore before making changes (ls, cat, etc.)
3. Create skills in src/skills/ as reusable Python modules
4. Import using absolute paths: from src.servers.xxx import ...
5. The repo is a Git repository - all changes are tracked

When the session ends, all your work will be committed to the Git repo and saved to persistent storage."""

    # Initialize conversation with system prompt
    messages = []

    print("\n=== Agent Ready ===")
    print("Claude has access to the sandbox environment.")
    print("Type your requests (or 'quit' to exit)\n")
    print("System context: Persistent E2B sandbox with Git repo at /home/user/repo")
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
