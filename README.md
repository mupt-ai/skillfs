# SkillFS

Persistent AI agent runtime with Git-based state management and isolated sandbox execution.

## Overview

SkillFS provides infrastructure for building AI agents that:

- **Persist across sessions** - Agent state is stored as Git bundles in cloud storage
- **Run in isolated sandboxes** - Execute code safely in E2B containers
- **Compose via runners** - Build agents from configurable templates with tool delegation
- **Bridge MCP to sandboxes** - Convert MCP servers to Python scripts with SKILL.md for sandbox use


## Installation

```bash
pip install skillfs
```

You'll also need:
- An [E2B](https://e2b.dev) API key for sandbox execution
- An LLM API key (e.g., Anthropic) for agent reasoning

## Quick Start

```python
import asyncio
from skillfs.sandboxes import E2BSandbox, SandboxConfig
from skillfs.runners import AnthropicProvider, MainRunner, SearchRunner

async def main():
    # Create sandbox
    sandbox = E2BSandbox.create(config=SandboxConfig(timeout=300))

    # Create LLM provider
    provider = AnthropicProvider(api_key="sk-ant-...", model="claude-sonnet-4-5-20250929")

    # Create a runner with tools and subrunners
    runner = MainRunner(
        name="assistant",
        description="General assistant",
        system_prompt="You are a helpful coding assistant.",
        sandbox=sandbox,
        provider=provider,
        tools=["glob", "grep", "read_file", "write_file"],
        subrunners={"search": SearchRunner},
    )

    result = await runner.run("Find all Python files that handle authentication")
    print(result.message)

    sandbox.close()

asyncio.run(main())
```

## Runners

Runners are provider-agnostic agent loops. `MainRunner` is a configurable template; specialized runners like `SearchRunner` extend it with fixed configurations.

### MainRunner

Configure tools, system prompt, and subrunners at instantiation:

```python
from skillfs.runners import MainRunner, SearchRunner

runner = MainRunner(
    name="orchestrator",
    description="Main agent that delegates tasks",
    system_prompt="You coordinate tasks between specialists...",
    sandbox=sandbox,
    provider=provider,
    tools=["glob", "grep", "read_file", "write_file", "edit_file", "run_command"],
    subrunners={
        "search": SearchRunner,
        # Use a different provider for a subrunner:
        "fast_search": {"class": SearchRunner, "provider": haiku_provider},
    },
)
```

### SearchRunner

A specialized runner for codebase search with structured output:

```python
from skillfs.runners import SearchRunner

search = SearchRunner(sandbox=sandbox, provider=provider)
result = await search.run("Find error handling code")

# result.data contains typed SearchResult with matches
for match in result.data.matches:
    print(f"{match.path}: {match.relevance}")
```

### Creating Custom Runners

Extend `MainRunner` with fixed configuration and custom result parsing:

```python
class MyRunner(MainRunner):
    name = "my_runner"
    description = "Does something specific"

    def __init__(self, sandbox, provider, max_turns=20):
        super().__init__(
            name=self.name,
            description=self.description,
            system_prompt="Your instructions here...",
            sandbox=sandbox,
            provider=provider,
            tools=["glob", "read_file"],
            output_schema=MY_OUTPUT_SCHEMA,  # For structured output
        )

    async def run(self, task: str) -> AgentResult:
        result = await super().run(task)
        return self._parse_result(result)  # Custom parsing
```

## Tools

Built-in sandbox tools available to runners:

- `glob`: Find files by pattern
- `grep`: Search file contents (regex)
- `read_file`: Read file contents
- `write_file`: Create/overwrite files
- `edit_file`: Make targeted string replacements
- `run_command`: Execute shell commands

Dynamic tools (auto-created when configured):
- `call_subrunner` - Delegate to specialist agents
- `load_skill` - Load skill instructions on-demand

## Agents & Persistence

For long-running agents that need state persistence:

```python
from skillfs.agents import Agent
from skillfs.storage import LocalBundleStore

store = LocalBundleStore(directory="/tmp/agents")

agent = Agent(
    agent_id="my-agent",
    sandbox=sandbox,
    store=store,
)
await agent.load()   # Restore from storage if exists

# ... agent does work ...

agent.save()         # Commit and upload Git bundle
```

### Storage Backends

```python
# Local filesystem (development)
from skillfs.storage import LocalBundleStore
store = LocalBundleStore(directory="/tmp/agents")

# Google Cloud Storage (production)
from skillfs.storage import GCSBundleStore
store = GCSBundleStore(bucket="my-bucket", prefix="agents/")
```

## Skill-based MCP Integration

Generate Python wrappers and SKILL.md for MCP servers to use inside sandboxes:

```python
agent = Agent(
    agent_id="browser-agent",
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
await agent.load()
```

## Examples

See `examples/` for complete working examples.

## License

MIT