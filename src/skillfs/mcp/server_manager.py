"""Manager for MCP server tool generation and file creation."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from skillfs.mcp.generate_tool_wrapper import MCPToolWrapperGenerator

logger = logging.getLogger(__name__)


class MCPServerManager:
    """Manages MCP server definitions and generates tool wrapper files."""

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
    ) -> List[Any]:
        """
        Fetch available tools from an MCP server.

        Args:
            server_name: Name of the MCP server
            command: Command to run the MCP server
            args: Optional command-line arguments
            env: Optional environment variables

        Returns:
            List of tool definitions from the server

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
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    tools = result.tools if hasattr(result, 'tools') else []
                    logger.info(f"Found {len(tools)} tools in {server_name}")
        except Exception as e:
            logger.error(f"Failed to fetch tools from {server_name}: {e}")
            raise

        return tools

    def generate_server_files(
        self,
        server_name: str,
        tools: List[Any],
        config: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Generate a directory with individual files for each MCP server tool.

        Args:
            server_name: Name of the MCP server
            tools: List of tool definitions
            config: Optional MCP server configuration

        Returns:
            Path to the generated server directory
        """
        logger.info(f"Generating files for server: {server_name}")

        # Create server directory
        server_dir = self.servers_dir / server_name
        server_dir.mkdir(parents=True, exist_ok=True)

        # Initialize the tool wrapper generator
        generator = MCPToolWrapperGenerator(server_name=server_name)

        # Generate individual tool files
        for tool in tools:
            tool_name = tool.name if hasattr(tool, 'name') else str(tool)
            file_path = server_dir / f"{tool_name}.py"

            logger.info(f"Generating tool file: {file_path}")

            # Generate the function wrapper
            function_code = generator.tool_to_python_function(tool)

            # Create the complete file content with imports
            file_content = self._create_tool_file_content(
                function_code=function_code,
                server_name=server_name,
                config=config
            )

            # Write the file
            file_path.write_text(file_content)
            logger.info(f"Created tool file: {file_path}")

        # Create __init__.py to make it a package
        init_file = server_dir / "__init__.py"
        init_content = self._create_init_file(tools, server_name)
        init_file.write_text(init_content)

        logger.info(f"Generated {len(tools)} tool files in {server_dir}")
        return server_dir

    def _create_tool_file_content(
        self,
        function_code: str,
        server_name: str,
        config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create the complete content for a tool file including imports.

        Args:
            function_code: The generated function code
            server_name: Name of the MCP server
            config: Optional MCP server configuration

        Returns:
            Complete file content as a string
        """
        config_json = json.dumps(config or {}, indent=4) if config else "{}"

        return f'''"""Auto-generated MCP tool wrapper for {server_name}."""

from typing import Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# MCP Server Configuration
config = {config_json}


{function_code}
'''

    def _create_init_file(self, tools: List[Any], server_name: str) -> str:
        """
        Create __init__.py content that exports all tools.

        Args:
            tools: List of tool definitions
            server_name: Name of the MCP server

        Returns:
            Content for __init__.py file
        """
        tool_names = [
            tool.name if hasattr(tool, 'name') else str(tool)
            for tool in tools
        ]

        imports = "\n".join([
            f"from .{name} import {name}"
            for name in tool_names
        ])

        all_exports = ", ".join([f'"{name}"' for name in tool_names])

        return f'''"""Auto-generated MCP tools for {server_name}."""

{imports}

__all__ = [{all_exports}]
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

        # Fetch tools from the server
        tools = await self.fetch_tools_from_server(
            server_name=server_name,
            command=command,
            args=args,
            env=env
        )

        # Generate files for the tools
        server_dir = self.generate_server_files(
            server_name=server_name,
            tools=tools,
            config={"mcpServers": {server_name: server_config}}
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
