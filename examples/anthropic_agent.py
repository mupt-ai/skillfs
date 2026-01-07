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
from skillfs.runners.tools import create_load_skill_tool
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
        # generate_mcp_tools=True,
        # skills={
        #     "github": [
        #         "https://github.com/agentskills/agentskills",
        #         {
        #             "url": "https://github.com/anthropics/claude-cookbooks",
        #             "path": "skills/custom_skills/creating-financial-models"
        #         },
        #         {
        #             "url": "https://github.com/anthropics/claude-cookbooks",
        #             "ref": "pedram/fix-notebook-standards",
        #             "path": "skills/custom_skills/applying-brand-guidelines"
        #         }
        #     ]
        # },
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

    # Create load_skill tool with dynamic schema (includes discovered skills in description)
    load_skill_schema, load_skill_handler = create_load_skill_tool(catalog)

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
        {
            "name": "read_file",
            "description": "Read file contents as text. Returns the file content as a string.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file in the sandbox",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Maximum bytes to read (optional, for large files)",
                    },
                },
                "required": ["path"],
            },
        },
        {
            "name": "glob",
            "description": """Find files matching a glob pattern. Patterns are matched relative to root; use **/ for recursive matches.
Examples: "*.py" matches top-level .py files; "**/*.py" matches recursively.
Skips hidden files/directories by default (use dot=true to include).""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '*.py', '**/*.md', 'src/**/*.py')",
                    },
                    "root": {
                        "type": "string",
                        "description": "Base directory to search from (default: repo root)",
                    },
                    "dot": {
                        "type": "boolean",
                        "description": "Include dotfiles/directories (default: false)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return",
                    },
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "grep",
            "description": """Search file contents for a pattern. Returns matches with file path, line number, column, and matching text.
Uses regex by default; set regex=false for literal string matching.
Use include to filter files (e.g., "**/*.py" for Python files only).""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (regex by default, or literal if regex=false)",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search in (default: repo root)",
                    },
                    "include": {
                        "type": "string",
                        "description": "Glob pattern to filter files (e.g., '**/*.py')",
                    },
                    "ignore_case": {
                        "type": "boolean",
                        "description": "Case-insensitive search (default: false)",
                    },
                    "regex": {
                        "type": "boolean",
                        "description": "Treat pattern as regex (default: true)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum matches to return",
                    },
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "write_file",
            "description": """Write content to a file. Creates the file if it doesn't exist, or overwrites if it does.
Parent directories are created automatically. Use this for creating new files or completely replacing file contents.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Allow overwriting existing files (default: true)",
                    },
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "edit_file",
            "description": """Edit a file by replacing exact string matches. Use this for surgical edits to existing files.
By default, requires exactly one match of old_string in the file. Set replace_all=true to replace all occurrences.
The old_string must match exactly (including whitespace and indentation).""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file to edit",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Exact string to find and replace (must exist in file)",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement string (can be empty to delete)",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences instead of requiring exactly one (default: false)",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
        # Dynamic load_skill tool (schema includes discovered skills)
        load_skill_schema,
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
- run_command: Execute any shell command in the sandbox
- read_file: Read file contents directly (faster than cat)
- write_file: Create new files or overwrite existing ones
- edit_file: Make surgical edits to existing files (find and replace)
- glob: Find files by pattern (e.g., "**/*.py" for all Python files)
- grep: Search file contents with regex or literal patterns
- load_skill: Load detailed instructions for a specific skill (see available skills in tool description)
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
- Find all Python files: glob(pattern="**/*.py")
- Search for imports: grep(pattern="import asyncio", include="**/*.py")
- Read a file: read_file(path="{repo_root}/pyproject.toml")
- Write a new file: write_file(path="{repo_root}/src/skills/my_skill.py", content="...")
- Edit an existing file: edit_file(path="{repo_root}/src/skills/my_skill.py", old_string="old code", new_string="new code")
- Run a Python script: run_command("cd {repo_root} && uv run python my_script.py")
- Run a module: run_command("cd {repo_root} && uv run python -m src.skills.my_skill")
- Add a package: run_command("cd {repo_root} && uv add requests")

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
    print(f"Tools: run_command, read_file, write_file, edit_file, glob, grep, load_skill ({num_skills} skills) | MCP: Playwright, browser-use\n")

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
                    tool_result = None

                    if tool_name == "run_command":
                        command = tool_input.get("command")
                        cwd = tool_input.get("cwd")

                        print(f"\n[TOOL USED: Executing: {command}]", flush=True)

                        # Run the command in the agent's sandbox
                        result = agent.run_command(command, cwd=cwd)

                        tool_result = {
                            "stdout": result.logs,
                            "stderr": result.error or "",
                            "exit_code": result.exit_code,
                        }

                        print(f"[Exit code: {result.exit_code}]", flush=True)
                        if result.logs:
                            print(f"[Output preview: {result.logs[:200]}...]", flush=True)

                    elif tool_name == "read_file":
                        path = tool_input.get("path")
                        max_bytes = tool_input.get("max_bytes")

                        print(f"\n[TOOL USED: Reading file: {path}]", flush=True)

                        try:
                            content = sandbox.read_file_text(path, max_bytes=max_bytes)
                            tool_result = {"content": content}
                            print(f"[Read {len(content)} chars]", flush=True)
                        except FileNotFoundError:
                            tool_result = {"error": f"File not found: {path}"}
                            print(f"[Error: File not found]", flush=True)
                        except Exception as e:
                            tool_result = {"error": str(e)}
                            print(f"[Error: {e}]", flush=True)

                    elif tool_name == "glob":
                        pattern = tool_input.get("pattern")
                        root = tool_input.get("root", ".")
                        dot = tool_input.get("dot", False)
                        max_results = tool_input.get("max_results")

                        print(f"\n[TOOL USED: Glob: {pattern} in {root}]", flush=True)

                        try:
                            paths = sandbox.glob(
                                pattern,
                                root=root,
                                dot=dot,
                                max_results=max_results,
                            )
                            tool_result = {"paths": paths, "count": len(paths)}
                            print(f"[Found {len(paths)} files]", flush=True)
                        except FileNotFoundError as e:
                            tool_result = {"error": str(e), "paths": []}
                            print(f"[Error: {e}]", flush=True)
                        except ValueError as e:
                            tool_result = {"error": str(e), "paths": []}
                            print(f"[Error: {e}]", flush=True)

                    elif tool_name == "grep":
                        pattern = tool_input.get("pattern")
                        path = tool_input.get("path", ".")
                        include = tool_input.get("include")
                        ignore_case = tool_input.get("ignore_case", False)
                        regex = tool_input.get("regex", True)
                        max_results = tool_input.get("max_results")

                        print(f"\n[TOOL USED: Grep: '{pattern}' in {path}]", flush=True)

                        try:
                            matches = sandbox.grep(
                                pattern,
                                path=path,
                                include=include,
                                ignore_case=ignore_case,
                                regex=regex,
                                max_results=max_results,
                            )
                            # Convert GrepMatch objects to dicts
                            tool_result = {
                                "matches": [
                                    {
                                        "path": m.path,
                                        "line": m.line,
                                        "column": m.column,
                                        "text": m.text,
                                    }
                                    for m in matches
                                ],
                                "count": len(matches),
                            }
                            print(f"[Found {len(matches)} matches]", flush=True)
                        except FileNotFoundError as e:
                            tool_result = {"error": str(e), "matches": []}
                            print(f"[Error: {e}]", flush=True)
                        except ValueError as e:
                            tool_result = {"error": str(e), "matches": []}
                            print(f"[Error: {e}]", flush=True)

                    elif tool_name == "write_file":
                        path = tool_input.get("path")
                        content = tool_input.get("content")
                        overwrite = tool_input.get("overwrite", True)

                        print(f"\n[TOOL USED: Writing file: {path}]", flush=True)

                        try:
                            result = sandbox.write_file(
                                path,
                                content,
                                overwrite=overwrite,
                            )
                            tool_result = {
                                "path": result.path,
                                "bytes_written": result.bytes_written,
                                "created": result.created,
                            }
                            action = "Created" if result.created else "Overwrote"
                            print(f"[{action} {result.bytes_written} bytes]", flush=True)
                        except FileExistsError:
                            tool_result = {"error": f"File already exists: {path} (set overwrite=true to replace)"}
                            print(f"[Error: File exists]", flush=True)
                        except Exception as e:
                            tool_result = {"error": str(e)}
                            print(f"[Error: {e}]", flush=True)

                    elif tool_name == "edit_file":
                        path = tool_input.get("path")
                        old_string = tool_input.get("old_string")
                        new_string = tool_input.get("new_string")
                        replace_all = tool_input.get("replace_all", False)

                        print(f"\n[TOOL USED: Editing file: {path}]", flush=True)

                        try:
                            result = sandbox.edit_file(
                                path,
                                old_string,
                                new_string,
                                replace_all=replace_all,
                            )
                            tool_result = {
                                "path": result.path,
                                "replacements_made": result.replacements_made,
                                "bytes_before": result.bytes_before,
                                "bytes_after": result.bytes_after,
                            }
                            print(f"[Made {result.replacements_made} replacement(s)]", flush=True)
                        except FileNotFoundError:
                            tool_result = {"error": f"File not found: {path}"}
                            print(f"[Error: File not found]", flush=True)
                        except ValueError as e:
                            tool_result = {"error": str(e)}
                            print(f"[Error: {e}]", flush=True)
                        except Exception as e:
                            tool_result = {"error": str(e)}
                            print(f"[Error: {e}]", flush=True)

                    elif tool_name == "load_skill":
                        skill_name = tool_input.get("name")

                        print(f"\n[TOOL USED: Loading skill: {skill_name}]", flush=True)

                        tool_result = load_skill_handler(name=skill_name)
                        if "error" in tool_result:
                            print(f"[Error: {tool_result['error']}]", flush=True)
                        else:
                            print(f"[Loaded {tool_result['length']} chars]", flush=True)

                    else:
                        tool_result = {"error": f"Unknown tool: {tool_name}"}
                        print(f"\n[Unknown tool: {tool_name}]", flush=True)

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
