"""E2B sandbox implementation."""

import os
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

from e2b_code_interpreter import Sandbox

from skillfs.sandboxes.base import (
    SandboxConnection,
    SandboxConfig,
    ExecutionResult,
)

# Load environment variables for E2B API key
load_dotenv()


class E2BSandbox(SandboxConnection):
    """E2B Code Interpreter sandbox implementation.

    Example:
        >>> from skillfs.sandboxes import E2BSandbox
        >>> sandbox = E2BSandbox.create()
        >>> result = sandbox.run_code("print('hello world')")
        >>> print(result.logs)
        hello world
        >>> sandbox.close()

        Or using context manager:
        >>> with E2BSandbox.create() as sandbox:
        ...     result = sandbox.run_code("x = 2 + 2\\nprint(x)")
        ...     print(result.logs)
        4
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        """Initialize E2B sandbox configuration.

        Args:
            config: Sandbox configuration with E2B-specific settings.
        """
        super().__init__(config)
        self._sandbox: Optional[Sandbox] = None

    @classmethod
    def create(cls, config: Optional[SandboxConfig] = None) -> "E2BSandbox":
        """Create and initialize a new E2B sandbox instance.

        Args:
            config: Optional sandbox configuration. Uses environment
                   variables (E2B_API_KEY) if api_key not provided.

        Returns:
            A connected E2B sandbox instance.

        Raises:
            ValueError: If E2B API key is not configured.
        """
        instance = cls(config)

        # Get API key from config or environment
        api_key = instance.config.api_key or os.getenv("E2B_API_KEY")
        if not api_key:
            raise ValueError(
                "E2B API key not found. Set E2B_API_KEY environment variable "
                "or provide in SandboxConfig."
            )

        # Create E2B sandbox (timeout is applied per run_code call)
        instance._sandbox = Sandbox.create(
            api_key=api_key,
            timeout=instance.config.timeout,
        )

        instance._is_alive = True

        return instance

    def run_code(self, code: str, language: str = "python") -> ExecutionResult:
        """Execute Python code in the E2B sandbox.

        Args:
            code: Python source code to execute.
            language: Programming language (only 'python' supported).

        Returns:
            ExecutionResult with logs and output from execution.

        Raises:
            RuntimeError: If sandbox is not alive.
            ValueError: If language is not 'python'.
        """
        if not self.is_alive or not self._sandbox:
            raise RuntimeError("Sandbox is not active. Call create() first.")

        if language != "python":
            raise ValueError(f"E2B only supports Python, got: {language}")

        # Execute code in sandbox with timeout from config
        execution = self._sandbox.run_code(code, language=language, timeout=self.config.timeout)

        # Extract results
        logs = "\n".join(execution.logs.stdout + execution.logs.stderr)
        error = execution.error.value if execution.error else None
        results = execution.results if hasattr(execution, "results") else None

        return ExecutionResult(
            logs=logs,
            error=error,
            results=results,
        )

    def upload_file(self, local_path: Path, remote_path: str) -> None:
        """Upload a file to the E2B sandbox filesystem.

        Args:
            local_path: Path to local file.
            remote_path: Destination path in sandbox.

        Raises:
            RuntimeError: If sandbox is not alive.
            FileNotFoundError: If local file doesn't exist.
        """
        if not self.is_alive or not self._sandbox:
            raise RuntimeError("Sandbox is not active.")

        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        # Read local file and write to sandbox
        with open(local_path, "rb") as f:
            content = f.read()

        self._sandbox.files.write(remote_path, content)

    def download_file(self, remote_path: str, local_path: Path) -> None:
        """Download a file from the E2B sandbox filesystem.

        Args:
            remote_path: Path in sandbox filesystem.
            local_path: Local destination path.

        Raises:
            RuntimeError: If sandbox is not alive.
        """
        if not self.is_alive or not self._sandbox:
            raise RuntimeError("Sandbox is not active.")

        # Read from sandbox as bytes to handle both text and binary files
        content = self._sandbox.files.read(remote_path, format="bytes")

        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(content)

    def list_files(self, path: str = "/") -> List[str]:
        """List files in an E2B sandbox directory.

        Args:
            path: Directory path to list (default: root).

        Returns:
            List of file paths in the directory.

        Raises:
            RuntimeError: If sandbox is not alive.
        """
        if not self.is_alive or not self._sandbox:
            raise RuntimeError("Sandbox is not active.")

        files = self._sandbox.files.list(path)
        return [f.path if hasattr(f, "path") else str(f) for f in files]

    def run_command(self, command: str, cwd: Optional[str] = None) -> ExecutionResult:
        """Execute a shell command in the E2B sandbox.

        Args:
            command: Shell command to execute.
            cwd: Working directory to run the command (optional).

        Returns:
            ExecutionResult with stdout, stderr, and exit code.

        Raises:
            RuntimeError: If sandbox is not alive.
        """
        if not self.is_alive or not self._sandbox:
            raise RuntimeError("Sandbox is not active. Call create() first.")

        # Execute command using E2B's commands.run API
        result = self._sandbox.commands.run(
            cmd=command,
            cwd=cwd,
            timeout=self.config.timeout,
        )

        return ExecutionResult(
            logs=result.stdout,
            error=result.stderr if result.stderr else None,
            exit_code=result.exit_code,
        )

    def close(self) -> None:
        """Terminate and cleanup the E2B sandbox instance."""
        if self._sandbox and self._is_alive:
            self._sandbox.kill()
            self._is_alive = False
            self._sandbox = None
