"""Run command tool - execute shell commands in the sandbox."""

from typing import Any, Callable, Dict, Optional

from skillfs.sandboxes.base import SandboxConnection

SCHEMA = {
    "name": "run_command",
    "description": """Execute a shell command in the sandbox environment.

Use this tool to run shell commands like running scripts or any system commands.
The command runs in a bash shell with access to the full sandbox filesystem.

BEHAVIOR:
- Working directory defaults to the repo root if cwd is not specified
- Commands may timeout for very long-running operations
- Exit code 0 indicates success; non-zero indicates failure

Returns stdout, stderr, and exit code. Use this tool for system operations
that can't be done with the specialized file tools (glob, grep, read_file, write_file, edit_file, etc.).
Prefer the specialized tools when possible as they provide structured output and better error handling.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute (e.g., 'ls -la', 'uv run python script.py')",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the command (default: repo root)",
            },
        },
        "required": ["command"],
    },
}


def build_handler(sandbox: SandboxConnection) -> Callable[..., Dict[str, Any]]:
    """Build a run_command handler for the given sandbox."""

    def handle_run_command(
        command: str,
        cwd: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            result = sandbox.run_command(command, cwd=cwd)
            return {
                "stdout": result.logs,
                "stderr": result.error or "",
                "exit_code": result.exit_code,
            }
        except Exception as e:
            return {"error": str(e)}

    return handle_run_command
