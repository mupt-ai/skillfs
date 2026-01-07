"""Glob tool - find files by pattern."""

from typing import Any, Callable, Dict, Optional

from skillfs.sandboxes.base import SandboxConnection

SCHEMA = {
    "name": "glob",
    "description": """Find files matching a glob pattern in the codebase.

Use this tool to discover files by name pattern before reading or searching their contents.
Patterns are matched relative to the root directory. Returns absolute paths sorted lexicographically.

PATTERN EXAMPLES:
- "*.py" matches ONLY top-level .py files (not in subdirectories)
- "**/*.py" matches .py files recursively in all subdirectories
- "src/**/*.ts" matches .ts files under src/ directory
- "SKILL.md" matches only SKILL.md in root (not recursive)

NOTE: Does NOT support {a,b} brace expansion syntax.

Hidden files/directories (starting with .) are skipped by default unless the pattern explicitly
includes them (e.g., "**/.gitignore" will match even with dot=false). Set dot=true to include all hidden files.
Returns a list of matching paths and a count. If no files match, returns an empty list (not an error).
Use this tool first to understand codebase structure, then grep for content search or read_file for contents.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts')",
            },
            "root": {
                "type": "string",
                "description": "Base directory (default: repo root)",
            },
            "dot": {
                "type": "boolean",
                "description": "Include dotfiles/directories (default: false)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return",
            },
        },
        "required": ["pattern"],
    },
}


def build_handler(sandbox: SandboxConnection) -> Callable[..., Dict[str, Any]]:
    """Build a glob handler for the given sandbox."""

    def handle_glob(
        pattern: str,
        root: Optional[str] = None,
        dot: bool = False,
        max_results: Optional[int] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            paths = sandbox.glob(
                pattern,
                root=root or ".",
                dot=dot,
                max_results=max_results,
            )
            return {"paths": paths, "count": len(paths)}
        except FileNotFoundError as e:
            return {"error": str(e), "paths": []}
        except ValueError as e:
            # Handles empty/invalid patterns
            return {"error": str(e), "paths": []}
        except Exception as e:
            return {"error": str(e), "paths": []}

    return handle_glob
