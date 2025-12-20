"""Connection manager for MCP servers.

Provides shared, persistent connections to MCP servers instead of
creating new connections for each tool call.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

def generate_connection_manager_code(
    command: str,
    args: Optional[list] = None,
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

    return f'''# Connection manager for this MCP server
_connection_manager = MCPConnectionManager(
    command={repr(command)},
    args={args_str},
    env=os.environ,
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
