"""Load skill tool - load full skill content by name from the skill catalog.

This tool enables progressive disclosure of skills: agents see lightweight metadata
in the tool description, then call this tool to load the full SKILL.md content
when they need detailed instructions for a specific skill.
"""

from typing import Any, Callable, Dict

from skillfs.skills.catalog import SkillCatalog


def build_schema(catalog: SkillCatalog) -> Dict[str, Any]:
    """Build the tool schema with available skills listed in the description.

    The schema includes a dynamic description that lists all available skills
    from the catalog, enabling the LLM to make informed decisions about which
    skill to load.

    Args:
        catalog: The SkillCatalog containing discovered skills.

    Returns:
        Tool schema dict for the Anthropic API.
    """
    # Build the skills documentation for the description
    skills_doc = catalog.format_for_tool_description()

    return {
        "name": "load_skill",
        "description": f"""Load the full content of a skill by name.

{skills_doc}

Call this tool when you need detailed instructions for a task that matches one of the available skills.
The skill content includes step-by-step guidance, code examples, and implementation details.
Only load skills that are relevant to your current task to minimize context usage.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the skill to load (from the available skills list)",
                },
            },
            "required": ["name"],
        },
    }


def build_handler(catalog: SkillCatalog) -> Callable[..., Dict[str, Any]]:
    """Build a load_skill handler for the given skill catalog.

    Args:
        catalog: The SkillCatalog to load skills from.

    Returns:
        Handler function that loads skill content by name.
    """

    def handle_load_skill(
        name: str,
        **_: Any,
    ) -> Dict[str, Any]:
        """Load full skill content by name."""
        # Check if skill exists in catalog
        if name not in catalog:
            available = [s.name for s in catalog.list_skills()]
            return {
                "error": f"Skill '{name}' not found. Available skills: {available}"
            }

        # Load the full skill content
        content = catalog.get_skill(name)
        if content is None:
            return {"error": f"Failed to load skill content for '{name}'"}

        # Get metadata for additional context
        skill_meta = catalog.get_metadata(name)

        result: Dict[str, Any] = {
            "name": name,
            "content": content,
            "length": len(content),
        }

        # Include metadata if available
        if skill_meta:
            result["location"] = skill_meta.location
            if skill_meta.description:
                result["description"] = skill_meta.description

        return result

    return handle_load_skill


def create_load_skill_tool(
    catalog: SkillCatalog,
) -> tuple[Dict[str, Any], Callable[..., Dict[str, Any]]]:
    """Create the load_skill tool schema and handler.

    This is a convenience function that returns both the schema and handler
    together, similar to how other parameterized tools work.

    Args:
        catalog: The SkillCatalog to use for skill discovery and loading.

    Returns:
        Tuple of (schema, handler).

    Example:
        >>> catalog = SkillCatalog(sandbox=sandbox)
        >>> await catalog.scan()
        >>> schema, handler = create_load_skill_tool(catalog)
        >>> tools.append(schema)
        >>> handlers["load_skill"] = handler
    """
    schema = build_schema(catalog)
    handler = build_handler(catalog)
    return schema, handler
