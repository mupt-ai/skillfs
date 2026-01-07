"""Skill catalog for discovering and indexing SKILL.md files.

The catalog scans directories in the sandbox for SKILL.md files,
extracts frontmatter metadata, and provides methods for:
- Listing all available skills
- Loading full skill content on-demand
- Formatting skill metadata for tool descriptions
"""

import logging
from typing import Dict, List, Optional

from skillfs.sandboxes.base import SandboxConnection
from skillfs.skills.parser import SkillMetadata, SkillParseError, parse_yaml_frontmatter

logger = logging.getLogger(__name__)


# Default directories to scan for SKILL.md files (relative to repo root)
DEFAULT_SKILL_DIRS = ["src/skills", "src/servers"]


class SkillCatalog:
    """Catalog of skills discovered from SKILL.md files in the sandbox.

    The catalog maintains lightweight metadata (name, description, location)
    for all discovered skills. Full content is loaded on-demand when
    `get_skill()` is called.
    """

    def __init__(
        self,
        sandbox: SandboxConnection,
        repo_root: Optional[str] = None,
        skill_dirs: Optional[List[str]] = None,
    ):
        """Initialize the skill catalog.

        Args:
            sandbox: Connection to the sandbox for file operations
            repo_root: Root path of the repository in the sandbox.
                If None, uses sandbox.default_repo_root.
            skill_dirs: Directories to scan for SKILL.md files.
                       Defaults to ["src/skills", "src/servers"]
        """
        self.sandbox = sandbox
        self.repo_root = repo_root if repo_root is not None else sandbox.default_repo_root
        self.skill_dirs = skill_dirs if skill_dirs is not None else DEFAULT_SKILL_DIRS.copy()
        self._skills: Dict[str, SkillMetadata] = {}

    async def scan(self) -> int:
        """Scan configured directories for SKILL.md files and build catalog.

        Searches each directory in `skill_dirs` for SKILL.md files,
        parses their frontmatter, and stores metadata. Duplicate skill
        names are logged as warnings; first-discovered wins.

        Returns:
            Number of skills discovered

        Note:
            This clears any previously cached skills before scanning.
        """
        self._skills.clear()
        discovered = 0

        for skill_dir in self.skill_dirs:
            full_path = f"{self.repo_root}/{skill_dir}"
            discovered += await self._scan_directory(full_path)

        logger.info(f"Skill catalog scan complete: {discovered} skills found")
        return discovered

    async def _scan_directory(self, directory: str) -> int:
        """Scan a directory for SKILL.md files using glob pattern.

        Args:
            directory: Absolute path to scan in the sandbox

        Returns:
            Number of skills discovered in this directory
        """
        discovered = 0

        # Check if directory exists
        result = self.sandbox.run_command(f"test -d {directory} && echo 'exists'")
        if "exists" not in result.logs:
            logger.debug(f"Directory {directory} does not exist, skipping")
            return 0

        # Find all SKILL.md files recursively (portable across bash/zsh)
        # Using -print0 for null-delimited output handles edge cases (filenames with newlines)
        result = self.sandbox.run_command(
            f"find '{directory}' -name 'SKILL.md' -type f -print0 2>/dev/null"
        )

        if result.exit_code != 0 or not result.logs.strip():
            return 0

        # Split on null bytes for robust parsing
        skill_paths = [p for p in result.logs.rstrip('\0').split('\0') if p]

        for skill_path in skill_paths:
            metadata = await self._load_skill_metadata(skill_path)
            if metadata:
                # Check for duplicates
                if metadata.name in self._skills:
                    existing = self._skills[metadata.name]
                    logger.warning(
                        f"Duplicate skill name '{metadata.name}': "
                        f"{existing.location} (kept), {skill_path} (skipped)"
                    )
                    continue

                self._skills[metadata.name] = metadata
                discovered += 1
                logger.debug(f"Discovered skill: {metadata.name} at {skill_path}")

        return discovered

    async def _load_skill_metadata(self, path: str) -> Optional[SkillMetadata]:
        """Load and parse frontmatter from a SKILL.md file.

        Uses sed to extract only the YAML frontmatter (between --- delimiters)
        rather than reading the entire file. 

        Args:
            path: Absolute path to SKILL.md in the sandbox

        Returns:
            SkillMetadata if successful, None otherwise
        """
        try:
            # Extract only the YAML frontmatter between --- delimiters
            result = self.sandbox.run_command(
                f"sed -n '2,/^---$/p' '{path}' | head -n -1"
            )
            if result.exit_code != 0:
                logger.warning(f"SKILL.md not found at {path}")
                return None

            yaml_content = result.logs
            if not yaml_content.strip():
                logger.warning(f"SKILL.md at {path} has empty frontmatter")
                return None

            return parse_yaml_frontmatter(yaml_content, path)
        except SkillParseError as e:
            logger.warning(f"Failed to parse SKILL.md: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error loading {path}: {e}")
            return None

    def list_skills(self) -> List[SkillMetadata]:
        """Get list of all discovered skills.

        Returns:
            List of SkillMetadata
        """
        return list(self._skills.values())

    def get_metadata(self, name: str) -> Optional[SkillMetadata]:
        """Get skill metadata by name.

        Args:
            name: Skill name

        Returns:
            SkillMetadata if found, None otherwise
        """
        return self._skills.get(name)

    def get_skill(self, name: str) -> Optional[str]:
        """Get full skill content by name.

        Reads and returns the raw SKILL.md file content from the sandbox.

        Args:
            name: Skill name

        Returns:
            Raw SKILL.md content as string, or None if not found
        """
        metadata = self._skills.get(name)
        if not metadata:
            return None

        try:
            result = self.sandbox.run_command(f"cat '{metadata.location}'")
            if result.exit_code != 0:
                logger.warning(f"Failed to read skill file {metadata.location}: {result.error}")
                return None
            return result.logs
        except Exception as e:
            logger.warning(f"Error loading skill content for {name}: {e}")
            return None

    def format_for_tool_description(self) -> str:
        """Format skill catalog for embedding in tool description.

        Returns a string suitable for including in the `skill` tool's
        description field, listing all available skills with their
        names and descriptions.

        Returns:
            Formatted string with available skills, or message if none
        """
        skills = self.list_skills()

        if not skills:
            return "No skills are currently available."

        lines = [
            "Load a skill to get detailed instructions for a specific task.",
            "Skills provide specialized knowledge and step-by-step guidance.",
            "Use this when a task matches an available skill's description.",
            "",
            "<available_skills>",
        ]

        for skill in skills:
            lines.append("  <skill>")
            lines.append(f"    <name>{skill.name}</name>")
            lines.append(f"    <description>{skill.description}</description>")
            if skill.short_description:
                lines.append(f"    <short_description>{skill.short_description}</short_description>")
            lines.append(f"    <location>{skill.location}</location>")
            lines.append("  </skill>")

        lines.append("</available_skills>")

        return "\n".join(lines)

    def __len__(self) -> int:
        """Return number of skills in catalog."""
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        """Check if a skill exists in catalog."""
        return name in self._skills

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"SkillCatalog(skills={len(self._skills)}, dirs={self.skill_dirs})"
