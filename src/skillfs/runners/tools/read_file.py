"""Read file tool - read file contents."""

from typing import Any, Callable, Dict, Optional

from skillfs.sandboxes.base import SandboxConnection


SCHEMA = {
    "name": "read_file",
    "description": """Read the contents of a file from the codebase.

Use this tool after finding files with glob or grep to examine their full contents.
The path must be an absolute path to the file. For large files, use max_bytes to limit
the amount of data read and avoid overwhelming context.

Returns the file content as text (decoded as UTF-8) along with the character length.
If the file does not exist, returns an error. Binary files or files with invalid UTF-8
will cause a decode error - these should be read via run_command with base64 encoding.
Use this tool to understand implementation details, verify code patterns, or gather context.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file",
            },
            "max_bytes": {
                "type": "integer",
                "description": "Maximum bytes to read (for large files)",
            },
        },
        "required": ["path"],
    },
}


def build_handler(sandbox: SandboxConnection) -> Callable[..., Dict[str, Any]]:
    """Build a read_file handler for the given sandbox."""

    def handle_read_file(
        path: str,
        max_bytes: Optional[int] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            content = sandbox.read_file_text(path, max_bytes=max_bytes)
            return {"content": content, "length": len(content)}
        except FileNotFoundError:
            return {"error": f"File not found: {path}"}
        except UnicodeDecodeError:
            return {"error": f"File contains invalid UTF-8 (binary file?): {path}"}
        except ValueError as e:
            # Handles non-absolute path errors
            return {"error": str(e)}
        except Exception as e:
            return {"error": str(e)}

    return handle_read_file
