#!/usr/bin/env python3
"""Simple shell interface for the Agent sandbox.

This script provides a basic shell-like interface that:
- Initializes an agent with a sandbox and storage
- Continuously prompts the user for commands to run
- Executes commands in the sandbox and displays results
"""

import asyncio
import os
from pathlib import Path
from skillfs.storage.local import LocalBundleStore

from skillfs.agents import Agent
from skillfs.sandboxes import E2BSandbox, SandboxConfig


async def main():
    """Run the simple shell example."""
    # Create sandbox
    print("Creating sandbox...")
    sandbox = E2BSandbox.create(config=SandboxConfig(timeout=3000))

    # Setup storage backend
    store = LocalBundleStore(directory="/tmp/agent-bundles", prefix="agents/")

    # Create and load agent
    print("Initializing agent...")
    agent = Agent(
        agent_id="shell-agent-003",
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
    print("\n=== Shell Ready ===")
    print("Type commands to execute in the sandbox (or 'quit'/'exit' to finish)\n")

    # Get current working directory info
    pwd_result = agent.run_command("pwd")
    current_dir = pwd_result.logs.strip() if pwd_result.logs else "/home/user/repo"
    print(f"Current directory: {current_dir}\n")

    while True:
        try:
            # Get user input
            user_input = input("$ ").strip()
            
            if user_input.lower() in ["quit", "exit", "q"]:
                break

            if not user_input:
                continue

            # Parse command for optional cwd
            parts = user_input.split(" | ")
            if len(parts) > 1:
                # Support for "cd /path | command" syntax
                if parts[0].startswith("cd "):
                    cwd = parts[0][3:].strip()
                    command = " | ".join(parts[1:])
                else:
                    command = user_input
                    cwd = None
            else:
                command = user_input
                cwd = None

            # Handle cd commands specially to update prompt context
            if command.startswith("cd "):
                cwd = command[3:].strip()
                result = agent.run_command(f"cd {cwd} && pwd")
                if result.exit_code == 0:
                    current_dir = result.logs.strip()
                    print(current_dir)
                else:
                    print(f"Error: {result.error or 'Failed to change directory'}")
                continue

            # Execute the command
            result = agent.run_command(command, cwd=cwd)

            # Display results
            if result.logs:
                print(result.logs, end="")
            
            if result.error:
                print(result.error, end="", file=os.sys.stderr)

            # Show exit code if non-zero
            if result.exit_code != 0:
                print(f"\n[Exit code: {result.exit_code}]", file=os.sys.stderr)

            print()  # Empty line after output

        except KeyboardInterrupt:
            print("\n\nInterrupted. Type 'quit' to exit.")
        except Exception as e:
            print(f"Error: {e}")

    # Save agent state
    print("\nSaving agent state...")
    agent.save(commit_message="Shell session completed")

    # Cleanup
    print("Closing sandbox...")
    sandbox.close()

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
