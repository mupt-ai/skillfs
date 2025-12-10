from typing import Any
from textwrap import dedent, indent


def tool_to_python_function(tool: Any) -> str:
    """
    Convert an MCP tool object to a Python function definition string.

    Args:
        tool: An MCP tool object with name, description, and inputSchema

    Returns:
        A string containing the complete Python function definition
    """
    # Generate function signature
    params = []
    arg_props = []

    if hasattr(tool, 'inputSchema') and tool.inputSchema:
        schema = tool.inputSchema
        if 'properties' in schema:
            for prop_name, prop_info in schema['properties'].items():
                prop_type = prop_info.get('type', 'Any')
                # Map JSON schema types to Python types
                type_mapping = {
                    'string': 'str',
                    'number': 'float',
                    'integer': 'int',
                    'boolean': 'bool',
                    'array': 'list',
                    'object': 'dict'
                }
                python_type = type_mapping.get(prop_type, 'Any')

                # Check if required
                required = schema.get('required', [])
                if prop_name in required:
                    params.append(f"{prop_name}: {python_type}")
                else:
                    params.append(f"{prop_name}: {python_type} = None")

                arg_props.append(prop_name)

    params_str = ", ".join(params)
    description = tool.description if hasattr(tool, 'description') and tool.description else ""

    # Build arguments dict
    if arg_props:
        arguments_dict = "{\n" + "".join([f'                "{prop}": {prop},\n' for prop in arg_props]) + "            }"
        arguments_section = f"""\
            arguments = {arguments_dict}
            # Remove None values
            arguments = {{k: v for k, v in arguments.items() if v is not None}}"""
    else:
        arguments_section = "arguments = {}"

    return dedent(f'''\
        async def {tool.name}({params_str}) -> Any:
            """
            {description}
            """
            server_cfg = config["mcpServers"]["chrome-devtools"]
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
