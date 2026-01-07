# SkillFS

Bash is all you need.

A persistent, version-controlled sandbox for AI agents. Runs on [E2B](https://e2b.dev) with every change tracked in git.

```
Agent works → commits progress → session ends
            ↓
Next session → restores state → continues where it left off
            ↓
git log     → full history of everything it did
```


## Installation

```bash
pip install skillfs
```

You'll also need:
- An [E2B](https://e2b.dev) API key for sandbox execution
- An LLM API key (e.g., Anthropic) if using runners

## Quick Start

```python
import asyncio
from skillfs.workspaces import Workspace
from skillfs.sandboxes import E2BSandbox, SandboxConfig
from skillfs.storage import LocalBundleStore

async def main():
    sandbox = E2BSandbox.create(config=SandboxConfig(timeout=300))
    store = LocalBundleStore(directory="/tmp/workspaces")

    workspace = Workspace(
        workspace_id="my-workspace",
        sandbox=sandbox,
        store=store,
    )

    await workspace.load()  # Restore from previous session if exists

    # Use the sandbox directly
    sandbox.run_command("echo 'Hello, world!' > hello.txt")
    sandbox.run_command("cat hello.txt")

    workspace.save()  # Commit and upload git bundle
    sandbox.close()

asyncio.run(main())
```

## Workspace

Workspace handles persistence. It manages:
- Loading state from storage (git bundles)
- Saving state back to storage
- Setting up MCP servers
- Managing skills

```python
from skillfs.workspaces import Workspace

workspace = Workspace(
    workspace_id="my-workspace",
    sandbox=sandbox,
    store=store,
    mcp_servers={
        "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}
    },
    generate_mcp_tools=True,
)

await workspace.load()
# ... do work with sandbox ...
workspace.save()
```

### Storage Backends

```python
# Local filesystem (development)
from skillfs.storage import LocalBundleStore
store = LocalBundleStore(directory="/tmp/workspaces")

# Google Cloud Storage (production)
from skillfs.storage import GCSBundleStore
store = GCSBundleStore(bucket="my-bucket", prefix="workspaces/")
```

## Runners (Optional)

Runners are LLM loops that work with the sandbox. Workspace handles persistence, Runner handles agent logic.

```python
from skillfs.workspaces import Workspace
from skillfs.runners import AnthropicProvider, MainRunner

# Workspace: persistence
workspace = Workspace(workspace_id="my-workspace", sandbox=sandbox, store=store)
await workspace.load()

# Runner: LLM loop (uses same sandbox)
provider = AnthropicProvider(api_key="sk-ant-...", model="claude-sonnet-4-5-20250929")
runner = MainRunner(
    name="assistant",
    description="General assistant",
    system_prompt="You are a helpful assistant.",
    sandbox=sandbox,
    provider=provider,
    tools=["glob", "grep", "read_file", "write_file"],
)

result = await runner.run("Find all Python files")
print(result.message)

workspace.save()
```

### Tools

Built-in sandbox tools available to runners:

- `glob`: Find files by pattern
- `grep`: Search file contents (regex)
- `read_file`: Read file contents
- `write_file`: Create/overwrite files
- `edit_file`: Make targeted string replacements
- `run_command`: Execute shell commands

## MCP Integration

Generate Python wrappers for MCP servers inside the sandbox:

```python
workspace = Workspace(
    workspace_id="browser-workspace",
    sandbox=sandbox,
    store=store,
    mcp_servers={
        "playwright": {
            "command": "npx",
            "args": ["@playwright/mcp@latest"]
        }
    },
    generate_mcp_tools=True,
)
await workspace.load()

# MCP tools are now available at src/servers/playwright/
```

## Examples

**[`examples/browser_agent.py`](examples/browser_agent.py)** - Browser automation with Playwright MCP.

**[`examples/example_with_runners.py`](examples/example_with_runners.py)** - Using Workspace with Runners.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export E2B_API_KEY=e2b_...
python examples/browser_agent.py
```

## License

MIT
