"""Edit file tool - make targeted edits to existing files."""

from typing import Any, Callable, Dict, Optional

from skillfs.sandboxes.base import SandboxConnection

SCHEMA = {
    "name": "edit_file",
    "description": """Edit an existing file by replacing exact string matches.

Use this tool to make targeted, surgical edits to files - finding and replacing specific text.
The old_string must match EXACTLY, including all whitespace and indentation (byte-for-byte matching).
For creating new files or completely replacing file contents, use write_file instead.

MATCHING RULES:
- By default, exactly ONE match of old_string must exist in the file
- Set replace_all=true to replace all occurrences (any number of matches allowed)
- If old_string is not found, returns an error unless allow_no_match=true
- old_string and new_string must be different (cannot be equal)

SPECIAL CASES:
- allow_no_match=true: For idempotent edits like "remove if present, ignore if absent"
- expected_replacements=N: Assert exactly N matches exist (use =0 to assert string is absent)

Returns the path, number of replacements made, and file sizes before/after.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to edit",
            },
            "old_string": {
                "type": "string",
                "description": "Exact text to find and replace (must match byte-for-byte including whitespace)",
            },
            "new_string": {
                "type": "string",
                "description": "Text to replace old_string with (can be empty to delete the matched text)",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences; when false, exactly one match is required (default: false)",
            },
            "allow_no_match": {
                "type": "boolean",
                "description": "Allow edit to succeed even if old_string is not found (default: false)",
            },
            "expected_replacements": {
                "type": "integer",
                "description": "If specified, fail unless exactly this many replacements are made",
            },
        },
        "required": ["path", "old_string", "new_string"],
    },
}


def build_handler(sandbox: SandboxConnection) -> Callable[..., Dict[str, Any]]:
    """Build an edit_file handler for the given sandbox."""

    def handle_edit_file(
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        allow_no_match: bool = False,
        expected_replacements: Optional[int] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            result = sandbox.edit_file(
                path,
                old_string,
                new_string,
                replace_all=replace_all,
                allow_no_match=allow_no_match,
                expected_replacements=expected_replacements,
            )
            return {
                "path": result.path,
                "replacements_made": result.replacements_made,
                "bytes_before": result.bytes_before,
                "bytes_after": result.bytes_after,
            }
        except FileNotFoundError:
            return {"error": f"File not found: {path}"}
        except IsADirectoryError:
            return {"error": f"Path is a directory: {path}"}
        except ValueError as e:
            # Handles "not found" and "expected_replacements" mismatches
            return {"error": str(e)}
        except Exception as e:
            return {"error": str(e)}

    return handle_edit_file
