"""Grep tool - search file contents."""

from typing import Any, Callable, Dict, Optional

from skillfs.sandboxes.base import SandboxConnection


SCHEMA = {
    "name": "grep",
    "description": """Search file contents for a text pattern across the codebase.

Use this tool to find specific code patterns, function definitions, imports, or text within files.
By default, the pattern is treated as a regular expression. Set regex=false for literal string matching.

SEARCH BEHAVIOR:
- If path is a directory: searches recursively under it
- If path is a file: searches only that file (include parameter is ignored)
- Results are sorted by (path, line, column) for determinism

RESULTS FORMAT:
Each match includes: file path, line number (1-based), column (1-based byte offset), and matching line text.

Use the include parameter to filter by file type (e.g., include="**/*.py" for Python files only).
Returns matches as a list with count. If no matches found, returns an empty list (not an error).
Use glob first to find files, then grep to search contents, then read_file to examine full context.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Search pattern (regex by default, or literal if regex=false)",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search (default: repo root)",
            },
            "include": {
                "type": "string",
                "description": "Glob to filter files (e.g., '**/*.py')",
            },
            "ignore_case": {
                "type": "boolean",
                "description": "Case-insensitive search (default: false)",
            },
            "regex": {
                "type": "boolean",
                "description": "Treat pattern as regex (default: true)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum matches to return",
            },
        },
        "required": ["pattern"],
    },
}


def build_handler(sandbox: SandboxConnection) -> Callable[..., Dict[str, Any]]:
    """Build a grep handler for the given sandbox."""

    def handle_grep(
        pattern: str,
        path: Optional[str] = None,
        include: Optional[str] = None,
        ignore_case: bool = False,
        regex: bool = True,
        max_results: Optional[int] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            matches = sandbox.grep(
                pattern,
                path=path or ".",
                include=include,
                ignore_case=ignore_case,
                regex=regex,
                max_results=max_results,
            )
            return {
                "matches": [
                    {
                        "path": m.path,
                        "line": m.line,
                        "column": m.column,
                        "text": m.text,
                    }
                    for m in matches
                ],
                "count": len(matches),
            }
        except FileNotFoundError as e:
            return {"error": str(e), "matches": []}
        except ValueError as e:
            # Handles empty/invalid patterns or include globs
            return {"error": str(e), "matches": []}
        except Exception as e:
            return {"error": str(e), "matches": []}

    return handle_grep
