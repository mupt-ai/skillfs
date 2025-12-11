from typing import Any, List
from textwrap import dedent, indent


class MCPToolWrapperGenerator:
    """Generator for creating Python function wrappers from MCP tool definitions"""

    JSON_TO_PYTHON_TYPE_MAPPING = {
        'string': 'str',
        'number': 'float',
        'integer': 'int',
        'boolean': 'bool',
        'array': 'list',
        'object': 'dict'
    }

    def __init__(self, server_name: str = "chrome-devtools"):
        """
        Initialize the MCP tool wrapper generator.

        Args:
            server_name: The name of the MCP server configuration to use
        """
        self.server_name = server_name

    def _extract_function_signature(self, tool: Any) -> tuple[str, List[str]]:
        """
        Extract function signature parameters from tool input schema.

        Args:
            tool: An MCP tool object with inputSchema

        Returns:
            A tuple of (params_string, arg_property_names)
        """
        params = []
        arg_props = []

        if hasattr(tool, 'inputSchema') and tool.inputSchema:
            schema = tool.inputSchema
            if 'properties' in schema:
                required = schema.get('required', [])

                for prop_name, prop_info in schema['properties'].items():
                    prop_type = prop_info.get('type', 'Any')
                    python_type = self.JSON_TO_PYTHON_TYPE_MAPPING.get(prop_type, 'Any')

                    # Add parameter with or without default value
                    if prop_name in required:
                        params.append(f"{prop_name}: {python_type}")
                    else:
                        params.append(f"{prop_name}: {python_type} = None")

                    arg_props.append(prop_name)

        params_str = ", ".join(params)
        return params_str, arg_props

    def _generate_arguments_section(self, arg_props: List[str]) -> str:
        """
        Generate the arguments dictionary construction code.

        Args:
            arg_props: List of argument property names

        Returns:
            Code string for building the arguments dictionary
        """
        if not arg_props:
            return "arguments = {}"

        arguments_dict = "{\n" + "".join([
            f'                "{prop}": {prop},\n'
            for prop in arg_props
        ]) + "            }"

        return f"""\
            arguments = {arguments_dict}
            # Remove None values
            arguments = {{k: v for k, v in arguments.items() if v is not None}}"""

    def tool_to_python_function(self, tool: Any) -> str:
        """
        Convert an MCP tool object to a Python function definition string.

        Args:
            tool: An MCP tool object with name, description, and inputSchema

        Returns:
            A string containing the complete Python function definition
        """
        params_str, arg_props = self._extract_function_signature(tool)
        description = tool.description if hasattr(tool, 'description') and tool.description else ""
        arguments_section = self._generate_arguments_section(arg_props)

        return dedent(f'''\
            async def {tool.name}({params_str}) -> Any:
                """
                {description}
                """
                server_cfg = config["mcpServers"]["{self.server_name}"]
                params = StdioServerParameters(
                    command=server_cfg["command"],
                    args=server_cfg["args"],
                    env=None,
                )
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        {indent(arguments_section, "        ").strip()}
                        result = await session.call_tool(
                            "{tool.name}",
                            arguments=arguments,
                        )
                        return result''')

    def generate_multiple_wrappers(self, tools: List[Any]) -> List[str]:
        """
        Generate Python function wrappers for multiple MCP tools.

        Args:
            tools: List of MCP tool objects

        Returns:
            List of Python function definition strings
        """
        return [self.tool_to_python_function(tool) for tool in tools]


# Maintain backward compatibility with existing function-based API
def tool_to_python_function(tool: Any, server_name: str = "chrome-devtools") -> str:
    """
    Convert an MCP tool object to a Python function definition string.

    Args:
        tool: An MCP tool object with name, description, and inputSchema
        server_name: The name of the MCP server configuration to use

    Returns:
        A string containing the complete Python function definition
    """
    generator = MCPToolWrapperGenerator(server_name=server_name)
    return generator.tool_to_python_function(tool)
