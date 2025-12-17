"""Connection manager for MCP servers.

Provides shared, persistent connections to MCP servers instead of
creating new connections for each tool call.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPConnectionManager:
    """Manages a shared connection to an MCP server.

    This class establishes a single connection to an MCP server and provides
    access to the session for making tool calls. The connection is lazily
    initialized on first use and can be explicitly closed.

    Example usage:
        # Initialize the connection manager
        manager = MCPConnectionManager(
            command="npx",
            args=["@playwright/mcp@latest"],
        )

        # Connect to the server
        await manager.connect()

        # Get the session and make tool calls
        session = await manager.get_session()
        result = await session.call_tool("browser_navigate", {"url": "https://example.com"})

        # Clean up when done
        await manager.disconnect()

    Or use as an async context manager:
        async with MCPConnectionManager(command="npx", args=["..."]) as manager:
            session = await manager.get_session()
            result = await session.call_tool("tool_name", {})
    """

    def __init__(
        self,
        command: str,
        args: Optional[list] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize the connection manager.

        Args:
            command: Command to run the MCP server
            args: Optional command-line arguments
            env: Optional environment variables
        """
        self.command = command
        self.args = args or []
        self.env = env
        self._session: Optional[ClientSession] = None
        self._client_context = None
        self._session_context = None
        self._read = None
        self._write = None
        self._connected = False
        self._lock = asyncio.Lock()

    async def connect(self) -> "MCPConnectionManager":
        """
        Establish connection to the MCP server.

        Returns:
            Self for method chaining

        Raises:
            Exception: If connection fails
        """
        async with self._lock:
            if self._connected:
                return self

            logger.info(f"Connecting to MCP server: {self.command} {' '.join(self.args)}")

            params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env,
            )

            # Create and enter the stdio client context
            self._client_context = stdio_client(params)
            self._read, self._write = await self._client_context.__aenter__()

            # Create and enter the session context
            self._session_context = ClientSession(self._read, self._write)
            self._session = await self._session_context.__aenter__()

            # Initialize the session
            await self._session.initialize()
            self._connected = True

            logger.info("Successfully connected to MCP server")
            return self

    async def disconnect(self) -> None:
        """
        Close the connection to the MCP server.
        """
        async with self._lock:
            if not self._connected:
                return

            logger.info("Disconnecting from MCP server")

            try:
                if self._session_context:
                    await self._session_context.__aexit__(None, None, None)
                if self._client_context:
                    await self._client_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self._session = None
                self._session_context = None
                self._client_context = None
                self._read = None
                self._write = None
                self._connected = False

    async def get_session(self) -> ClientSession:
        """
        Get the MCP session, connecting if necessary.

        Returns:
            The active ClientSession

        Raises:
            RuntimeError: If not connected and auto-connect fails
        """
        if not self._connected:
            await self.connect()

        if self._session is None:
            raise RuntimeError("MCP session not available")

        return self._session

    @property
    def is_connected(self) -> bool:
        """Check if currently connected to the server."""
        return self._connected

    async def __aenter__(self) -> "MCPConnectionManager":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def list_tools(self) -> list:
        """
        List available tools from the connected server.

        Returns:
            List of tool definitions
        """
        session = await self.get_session()
        result = await session.list_tools()
        return result.tools if hasattr(result, 'tools') else []


def generate_connection_manager_code(
    command: str,
    args: Optional[list] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    """
    Generate Python code that creates and manages an MCPConnectionManager.

    This generates the boilerplate code needed for the generated tool files.

    Args:
        command: Command to run the MCP server
        args: Optional command-line arguments
        env: Optional environment variables

    Returns:
        Python code as a string
    """
    args_str = repr(args or [])
    env_str = repr(env) if env else "None"

    return f'''# Connection manager for this MCP server
_connection_manager = MCPConnectionManager(
    command={repr(command)},
    args={args_str},
    env={env_str},
)


async def connect():
    """Connect to the MCP server. Call this before using any tools."""
    await _connection_manager.connect()


async def disconnect():
    """Disconnect from the MCP server. Call this when done."""
    await _connection_manager.disconnect()


def get_connection_manager() -> MCPConnectionManager:
    """Get the connection manager instance."""
    return _connection_manager
'''
