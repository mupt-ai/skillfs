"""Manager for MCP server tool generation and file creation."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from skillfs.mcp.generate_tool_wrapper import MCPToolWrapperGenerator
from skillfs.mcp.connection_manager import generate_connection_manager_code

logger = logging.getLogger(__name__)


class MCPServerManager:
    """Manages MCP server definitions and generates tool wrapper files.

    Generated files use a shared connection manager pattern where:
    1. Each server package has a single MCPConnectionManager instance
    2. All tool functions use the shared session from the connection manager
    3. Users must call connect() before using tools and disconnect() when done
    """

    def __init__(self, servers_dir: Path):
        """
        Initialize the MCP server manager.

        Args:
            servers_dir: Directory where server tool files will be generated
        """
        self.servers_dir = Path(servers_dir)
        self.servers_dir.mkdir(parents=True, exist_ok=True)

    async def fetch_tools_from_server(
        self,
        server_name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None
    ) -> tuple[List[Any], Optional[str]]:
        """
        Fetch available tools from an MCP server.

        Args:
            server_name: Name of the MCP server
            command: Command to run the MCP server
            args: Optional command-line arguments
            env: Optional environment variables

        Returns:
            Tuple of (tools list, server instructions or None)

        Raises:
            Exception: If unable to connect to or list tools from the server
        """
        logger.info(f"Fetching tools from MCP server: {server_name}")

        params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
        )

        tools = []
        instructions = None
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    init_result = await session.initialize()
                    # Extract server-provided instructions for LLMs
                    if hasattr(init_result, 'instructions') and init_result.instructions:
                        instructions = init_result.instructions
                        logger.info(f"Server {server_name} provided instructions")
                    result = await session.list_tools()
                    tools = result.tools if hasattr(result, 'tools') else []
                    logger.info(f"Found {len(tools)} tools in {server_name}")
        except Exception as e:
            logger.error(f"Failed to fetch tools from {server_name}: {e}")
            raise

        return tools, instructions

    def _normalize_server_name(self, server_name: str) -> str:
        """Normalize server name to be a valid Python identifier.

        Replaces hyphens with underscores so the generated directory
        can be imported as a Python module.

        Args:
            server_name: Original server name (may contain hyphens)

        Returns:
            Normalized name safe for Python imports

        Raises:
            ValueError: If the normalized name is not a valid Python identifier
        """
        normalized = server_name.replace("-", "_")
        if not normalized.isidentifier():
            raise ValueError(
                f"Server name '{server_name}' cannot be normalized to a valid "
                f"Python identifier (got '{normalized}'). Use only letters, "
                "digits, hyphens, and underscores, and don't start with a digit."
            )
        return normalized

    def generate_server_files(
        self,
        server_name: str,
        tools: List[Any],
        server_config: Dict[str, Any],
        instructions: Optional[str] = None
    ) -> Path:
        """
        Generate a directory with tool wrapper files for an MCP server.

        The generated package structure follows the Agent Skills standard:
        - SKILL.md: Skill metadata with YAML frontmatter
        - __init__.py: Exports all tools, connect(), disconnect(), and get_connection_manager()
        - tools/: Directory containing individual tool wrapper files
          - __init__.py: Exports all tool functions
          - Each tool gets its own file that uses the shared connection manager

        Args:
            server_name: Name of the MCP server
            tools: List of tool definitions
            server_config: Server configuration with 'command', 'args', 'env'
            instructions: Optional server-provided instructions for LLMs

        Returns:
            Path to the generated server directory
        """
        # Normalize server name to be a valid Python package name
        normalized_name = self._normalize_server_name(server_name)
        logger.info(f"Generating files for server: {server_name} (as {normalized_name})")

        # Create server directory with normalized name
        server_dir = self.servers_dir / normalized_name
        server_dir.mkdir(parents=True, exist_ok=True)

        # Create tools subdirectory
        tools_dir = server_dir / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)

        # Initialize the tool wrapper generator
        generator = MCPToolWrapperGenerator(server_name=server_name)

        # Generate individual tool files in tools/ subdirectory
        for tool in tools:
            tool_name = tool.name if hasattr(tool, 'name') else str(tool)
            file_path = tools_dir / f"{tool_name}.py"

            logger.info(f"Generating tool file: {file_path}")

            # Generate the function wrapper
            function_code = generator.tool_to_python_function(tool)

            # Create the complete file content with imports
            file_content = self._create_tool_file_content(
                function_code=function_code,
                tool_name=tool_name,
            )

            # Write the file
            file_path.write_text(file_content)
            logger.info(f"Created tool file: {file_path}")

        # Create tools/__init__.py with tool exports
        tools_init_file = tools_dir / "__init__.py"
        tools_init_content = self._create_tools_init_file(tools)
        tools_init_file.write_text(tools_init_content)

        # Create SKILL.md with frontmatter
        skill_file = server_dir / "SKILL.md"
        skill_content = self._create_skill_md(server_name, normalized_name, tools, instructions)
        skill_file.write_text(skill_content)
        logger.info(f"Created SKILL.md: {skill_file}")

        # Create __init__.py with connection manager and all tool exports
        init_file = server_dir / "__init__.py"
        init_content = self._create_init_file(tools, normalized_name, server_config)
        init_file.write_text(init_content)

        logger.info(f"Generated {len(tools)} tool files in {server_dir}")
        return server_dir

    def _create_tool_file_content(
        self,
        function_code: str,
        tool_name: str,
    ) -> str:
        """
        Create the content for an individual tool file.

        Each tool file imports the connection manager from the parent package's __init__.py.

        Args:
            function_code: The generated function code
            tool_name: Name of the tool

        Returns:
            Complete file content as a string
        """
        return f'''"""Auto-generated MCP tool wrapper: {tool_name}"""

from typing import Any

# Import the shared connection manager from the parent package
from .. import _connection_manager


{function_code}
'''

    def _create_tools_init_file(self, tools: List[Any]) -> str:
        """
        Create __init__.py content for the tools subdirectory.

        Args:
            tools: List of tool definitions

        Returns:
            Content for tools/__init__.py file
        """
        tool_names = [
            tool.name if hasattr(tool, 'name') else str(tool)
            for tool in tools
        ]

        # Generate imports for all tools
        tool_imports = "\n".join([
            f"from .{name} import {name}"
            for name in tool_names
        ])

        # Generate __all__ list
        all_exports_str = ", ".join([f'"{name}"' for name in tool_names])

        return f'''"""Auto-generated tool exports."""

{tool_imports}

__all__ = [{all_exports_str}]
'''

    def _create_skill_md(
        self,
        server_name: str,
        normalized_name: str,
        tools: List[Any],
        instructions: Optional[str] = None
    ) -> str:
        """
        Create SKILL.md content with YAML frontmatter.

        Tools are linked to their implementation files for progressive disclosure.

        Args:
            server_name: Original server name
            normalized_name: Python-safe normalized name
            tools: List of tool definitions
            instructions: Optional server-provided instructions for LLMs

        Returns:
            Content for SKILL.md file
        """
        # Build tool list with links to implementation files
        tool_entries = []
        for tool in tools:
            tool_name = tool.name if hasattr(tool, 'name') else str(tool)
            # Link to the tool's Python file for progressive disclosure
            tool_entries.append(f"- [`{tool_name}`](tools/{tool_name}.py)")

        tool_list = "\n".join(tool_entries)

        first_tool = tools[0].name if tools and hasattr(tools[0], 'name') else 'tool_name'

        # Build instructions section only if provided
        instructions_section = ""
        if instructions:
            instructions_section = f"""
## Recommended Instructions Derived from the Server

> {instructions}
"""

        return f'''---
name: {normalized_name}
description: Tools provided by the MCP server {server_name}
---

# {server_name}

This skill provides tools from the `{server_name}` MCP server.

## Available Tools

{tool_list}

## Usage

```python
from src.servers.{normalized_name} import connect_{normalized_name}, disconnect_{normalized_name}
from src.servers.{normalized_name}.tools import {first_tool}

# Connect to the server first
await connect_{normalized_name}()

# Use the tools
result = await {first_tool}(...)

# Disconnect when done
await disconnect_{normalized_name}()
```
{instructions_section}'''

    def _create_init_file(
        self,
        tools: List[Any],
        normalized_name: str,
        server_config: Dict[str, Any]
    ) -> str:
        """
        Create __init__.py content with connection manager and tool exports.

        Args:
            tools: List of tool definitions
            normalized_name: Python-safe normalized server name
            server_config: Server configuration

        Returns:
            Content for __init__.py file
        """
        tool_names = [
            tool.name if hasattr(tool, 'name') else str(tool)
            for tool in tools
        ]

        # Generate imports for all tools from .tools subpackage
        tool_imports = "\n".join([
            f"from .tools.{name} import {name}"
            for name in tool_names
        ])

        # Generate __all__ list with server-specific connect/disconnect
        all_exports = [f"connect_{normalized_name}", f"disconnect_{normalized_name}"] + tool_names
        all_exports_str = ", ".join([f'"{name}"' for name in all_exports])

        # Generate connection manager code
        connection_manager_code = generate_connection_manager_code(
            command=server_config.get("command", ""),
            args=server_config.get("args", []),
            server_name=normalized_name,
        )

        return f'''"""Auto-generated MCP tools for {normalized_name}.

Usage:
    from src.servers.{normalized_name} import connect_{normalized_name}, disconnect_{normalized_name}, {tool_names[0] if tool_names else 'tool_name'}

    # Connect to the server first
    await connect_{normalized_name}()

    # Use the tools
    result = await {tool_names[0] if tool_names else 'tool_name'}(...)

    # Disconnect when done
    await disconnect_{normalized_name}()
"""

from typing import Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.manager import MCPConnectionManager
import os

{connection_manager_code}

# Import all tool functions from tools/ subdirectory
{tool_imports}

__all__ = [{all_exports_str}]
'''

    async def setup_server_from_config(
        self,
        server_name: str,
        server_config: Dict[str, Any]
    ) -> Path:
        """
        Setup MCP server from configuration and generate tool files.

        Args:
            server_name: Name of the MCP server
            server_config: Server configuration with 'command', 'args', 'env'

        Returns:
            Path to the generated server directory

        Example:
            >>> manager = MCPServerManager(Path("src/servers"))
            >>> config = {
            ...     "command": "npx",
            ...     "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            ...     "env": {}
            ... }
            >>> await manager.setup_server_from_config("filesystem", config)
        """
        logger.info(f"Setting up MCP server from config: {server_name}")

        command = server_config.get("command")
        args = server_config.get("args", [])
        env = server_config.get("env")

        if not command:
            raise ValueError(f"Server config for {server_name} must include 'command'")

        # Fetch tools and instructions from the server
        tools, instructions = await self.fetch_tools_from_server(
            server_name=server_name,
            command=command,
            args=args,
            env=env
        )

        # Generate files for the tools
        server_dir = self.generate_server_files(
            server_name=server_name,
            tools=tools,
            server_config=server_config,
            instructions=instructions,
        )

        return server_dir

    async def setup_multiple_servers(
        self,
        servers_config: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Path]:
        """
        Setup multiple MCP servers from a configuration dictionary.

        Args:
            servers_config: Dictionary mapping server names to their configs

        Returns:
            Dictionary mapping server names to their generated directories

        Example:
            >>> manager = MCPServerManager(Path("src/servers"))
            >>> config = {
            ...     "filesystem": {
            ...         "command": "npx",
            ...         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
            ...     },
            ...     "brave-search": {
            ...         "command": "npx",
            ...         "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            ...         "env": {"BRAVE_API_KEY": "your-key"}
            ...     }
            ... }
            >>> await manager.setup_multiple_servers(config)
        """
        logger.info(f"Setting up {len(servers_config)} MCP servers")

        results = {}
        for server_name, server_config in servers_config.items():
            try:
                server_dir = await self.setup_server_from_config(
                    server_name=server_name,
                    server_config=server_config
                )
                results[server_name] = server_dir
            except Exception as e:
                logger.error(f"Failed to setup server {server_name}: {e}")
                raise

        logger.info(f"Successfully setup {len(results)} MCP servers")
        return results
