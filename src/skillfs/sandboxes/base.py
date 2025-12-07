"""Base abstractions for sandbox environments."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Dict, List
from pathlib import Path


@dataclass
class ExecutionResult:
    """Result of code execution in a sandbox."""

    logs: str
    """Standard output and error logs from execution."""

    error: Optional[str] = None
    """Error message if execution failed."""

    results: Optional[List[Any]] = None
    """Execution results (e.g., cell outputs for notebook environments)."""

    exit_code: Optional[int] = None
    """Process exit code if applicable."""


@dataclass
class SandboxConfig:
    """Configuration for sandbox creation and lifecycle."""

    timeout: int = 300
    """Sandbox lifetime in seconds (default: 5 minutes)."""

    api_key: Optional[str] = None
    """API key for sandbox service (if required)."""

    metadata: Dict[str, Any] = None
    """Additional provider-specific configuration."""

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SandboxConnection(ABC):
    """Abstract base class for sandbox connections.

    This provides a unified interface for interacting with different
    sandbox environments (E2B, Modal, Docker, etc.).
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        """Initialize sandbox connection with optional configuration.

        Args:
            config: Sandbox configuration. If None, uses defaults.
        """
        self.config = config or SandboxConfig()
        self._is_alive = False

    @classmethod
    @abstractmethod
    def create(cls, config: Optional[SandboxConfig] = None) -> "SandboxConnection":
        """Create and initialize a new sandbox instance.

        Args:
            config: Optional sandbox configuration.

        Returns:
            A connected and ready sandbox instance.
        """
        pass

    @abstractmethod
    def run_code(self, code: str, language: str = "python") -> ExecutionResult:
        """Execute code in the sandbox environment.

        Args:
            code: Source code to execute.
            language: Programming language (default: python).

        Returns:
            Execution result with logs and outputs.
        """
        pass

    @abstractmethod
    def upload_file(self, local_path: Path, remote_path: str) -> None:
        """Upload a file to the sandbox filesystem.

        Args:
            local_path: Path to local file.
            remote_path: Destination path in sandbox.
        """
        pass

    @abstractmethod
    def download_file(self, remote_path: str, local_path: Path) -> None:
        """Download a file from the sandbox filesystem.

        Args:
            remote_path: Path in sandbox filesystem.
            local_path: Local destination path.
        """
        pass

    @abstractmethod
    def list_files(self, path: str = "/") -> List[str]:
        """List files in a sandbox directory.

        Args:
            path: Directory path to list (default: root).

        Returns:
            List of file paths.
        """
        pass

    @abstractmethod
    def run_command(self, command: str, cwd: Optional[str] = None) -> ExecutionResult:
        """Execute a shell command in the sandbox environment.

        Args:
            command: Shell command to execute.
            cwd: Working directory to run the command (optional).

        Returns:
            Execution result with stdout, stderr, and exit code.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Terminate and cleanup the sandbox instance."""
        pass

    @property
    def is_alive(self) -> bool:
        """Check if sandbox is currently active."""
        return self._is_alive

    def __enter__(self) -> "SandboxConnection":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup sandbox."""
        self.close()
