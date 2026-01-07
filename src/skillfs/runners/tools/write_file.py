"""Write file tool - create or overwrite files."""

from typing import Any, Callable, Dict, Optional

from skillfs.sandboxes.base import SandboxConnection

SCHEMA = {
    "name": "write_file",
    "description": """Write content to a file in the sandbox filesystem.

Use this tool to create NEW files or COMPLETELY REPLACE existing file contents.
Parent directories are created automatically. Content is encoded as UTF-8.

WHEN TO USE:
- Creating a new file from scratch: use write_file
- Replacing entire file contents: use write_file
- Making surgical edits (find/replace): use edit_file instead

Returns the path, bytes written, and whether a new file was created (vs overwritten).
If overwrite=false and the file exists, returns an error.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
            "overwrite": {
                "type": "boolean",
                "description": "Allow overwriting existing files (default: true)",
            },
        },
        "required": ["path", "content"],
    },
}


def build_handler(sandbox: SandboxConnection) -> Callable[..., Dict[str, Any]]:
    """Build a write_file handler for the given sandbox."""

    def handle_write_file(
        path: str,
        content: str,
        overwrite: bool = True,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            result = sandbox.write_file(
                path,
                content,
                overwrite=overwrite,
            )
            return {
                "path": result.path,
                "bytes_written": result.bytes_written,
                "created": result.created,
            }
        except FileExistsError:
            return {"error": f"File already exists: {path} (set overwrite=true to replace)"}
        except IsADirectoryError:
            return {"error": f"Path is a directory: {path}"}
        except Exception as e:
            return {"error": str(e)}

    return handle_write_file
