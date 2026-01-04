"""Parser for SKILL.md files with YAML frontmatter.

This module extracts metadata from SKILL.md files following the format:

```markdown
---
name: skill_name
description: What this skill does
metadata:
  short-description: An optional, brief description for users.
---

# Skill Title

Content here...
```
"""

import logging
from dataclasses import dataclass
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """Metadata extracted from a SKILL.md file's frontmatter.

    Attributes:
        name: Unique identifier for the skill (required)
        description: Brief description of what the skill does (required)
        location: Path to the SKILL.md file
        short_description: An optional, brief description for users
    """

    name: str
    description: str
    location: str
    short_description: Optional[str] = None


class SkillParseError(Exception):
    """Raised when a SKILL.md file cannot be parsed."""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"Failed to parse {path}: {message}")


def parse_yaml_frontmatter(yaml_content: str, path: str) -> Optional[SkillMetadata]:
    """Parse YAML frontmatter directly.

    Used during catalog building when frontmatter has been extracted.
    Only parses metadata fields (name, description, short-description).

    Args:
        yaml_content: Raw YAML content (between --- delimiters, without the delimiters)
        path: Path to the file (for location tracking)

    Returns:
        SkillMetadata if valid, None if missing required fields

    Raises:
        SkillParseError: If the YAML cannot be parsed
    """
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise SkillParseError(
            path=path,
            message=f"Failed to parse YAML frontmatter: {e}",
        )

    if not data or not isinstance(data, dict):
        logger.warning(f"SKILL.md at {path} has empty or invalid frontmatter, skipping")
        return None

    name = data.get("name")
    description = data.get("description")

    # Extract optional metadata.short-description
    metadata_section = data.get("metadata", {})
    short_description = metadata_section.get("short-description") if metadata_section else None

    if not name:
        logger.warning(f"SKILL.md at {path} missing required 'name' field, skipping")
        return None

    if not description:
        logger.warning(f"SKILL.md at {path} missing required 'description' field, skipping")
        return None

    return SkillMetadata(
        name=str(name),
        description=str(description),
        location=path,
        short_description=str(short_description) if short_description else None,
    )
