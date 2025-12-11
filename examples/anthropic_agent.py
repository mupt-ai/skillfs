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

import anthropic
from skillfs.agents import Agent
from skillfs.sandboxes import E2BSandbox, SandboxConfig
from skillfs.storage.gcs import GCSBundleStore


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
    store = GCSBundleStore(bucket="dari_dev_test_bucket", prefix="agents/")

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
                    "wss://proxy.iad-elated-ellis.onkernel.com:8443/browser/cdp?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3OTY5NjEwNzYsInNlc3Npb24iOnsiaWQiOiJ0bjRqZmp0NGU0aHlxYTVidmloZ2lsamQiLCJjZHBQb3J0Ijo5MjIyLCJjZHBXc1BhdGgiOiIvZGV2dG9vbHMvYnJvd3Nlci9jYTU5ZDhiMS05MzRlLTRhZWUtOTY2MC0xZjc0ZDI0NDcxZTgiLCJpbnN0YW5jZU5hbWUiOiJicm93c2VyLXN0ZWFsdGgtcHJvZHVjdGlvbi00NTQtcHJpbWUtdGFuay01ODM0IiwiZnFkbiI6IndhbmRlcmluZy1iYW5hbmEtZXVpcWgweTgucHJvZC1pYWQtdW5pa3JhZnQtNC5vbmtlcm5lbC5hcHAiLCJtZXRybyI6Imh0dHBzOi8vYXBpLnByb2QtaWFkLXVuaWtyYWZ0LTQub25rZXJuZWwucnVuL3YxIiwidXNlcklkIjoiemg5MTh1eXEzdm16cjEwbXhkeGNqdjluIiwib3JnSWQiOiJvbzRucTNnYjg3ZDluNjEycGdodTNpMG4iLCJzdGVhbHRoIjp0cnVlLCJoZWFkbGVzcyI6ZmFsc2UsInJlcGxheVByZWZpeCI6InMzOi8va2VybmVsLWFwaS1wcm9kL3Nlc3Npb25yZXBsYXlzL29vNG5xM2diODdkOW42MTJwZ2h1M2kwbi90bjRqZmp0NGU0aHlxYTVidmloZ2lsamQiLCJrZXJuZWxIdHRwU2VydmVyUG9ydCI6NDQ0LCJ0aW1lb3V0U2Vjb25kcyI6NjAsImNyZWF0ZWRBdCI6IjIwMjUtMTItMTFUMDM6NTE6MTYuMDg2MTc3MzI4WiIsImltYWdlIjoib25rZXJuZWwva2VybmVsLWN1LXYyNDo0MDhiY2QxIiwic3RlYWx0aFByb3h5SWRlbnRpZmllciI6Ijg3NTY1X25YREZGQDE0NC4xNjguOS4xMzc6NjEyMzQiLCJsaXZlU2x1ZyI6InBCREV0OWVWcVZYTSIsInByaXZhdGVJUCI6IjE3Mi4xNi4xLjEwMSJ9fQ.wgOQFsOzZdLiV1-yUHZwZkiYUjf3k9vKPx5r4Rzkeeo"
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
- MCP servers are set up and their tools are available in the repo at src/servers/
- All your work is automatically versioned and can persist across sessions
- The agent state (files, code, changes) is stored in Google Cloud Storage

CAPABILITIES:
- You can execute ANY shell command via the run_command tool
- You have full read/write access to the filesystem
- You can install packages, run scripts, create files, etc.
- Python, Node.js, and common dev tools are pre-installed
- MCP tools (like Playwright) are available as Python modules in the repo
- When running Python, always run with uv
- Make sure you import with absolute paths, not relative paths

WORKING DIRECTORY STRUCTURE:
/home/user/repo/
├── src/
│   ├── skills/          # Custom agent skills/capabilities
│   ├── servers/         # MCP server tool wrappers
│   └── __init__.py
├── tests/
└── pyproject.toml

BEST PRACTICES:
1. Use run_command to explore before making changes (ls, cat, etc.)
2. Create skills in src/skills/ as reusable Python modules
3. Write tests for your code when appropriate
4. The repo is a Git repository - all changes are tracked
5. Be efficient - you can chain commands with && or use scripts
6. Check exit codes to verify command success
7. For complex tasks, break them into smaller commands

EXAMPLES:
- Read a file: run_command("cat /home/user/repo/src/skills/example.py")
- Install package: run_command("cd /home/user/repo && pip install requests")
- Create a skill: run_command("cat > /home/user/repo/src/skills/new_skill.py << 'EOF'\\n<code>\\nEOF")
- Run Python: run_command("cd /home/user/repo && python -m src.skills.my_skill")
- List files: run_command("ls -la /home/user/repo/src")

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
