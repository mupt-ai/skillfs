"""Base abstractions for sandbox environments."""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SandboxCommandError(RuntimeError):
    """Error raised when a sandbox command execution fails.

    Use this for distinguishing tool/sandbox failures from "no results" cases.
    This allows callers to selectively catch and retry execution failures
    while treating empty results as normal outcomes.
    """

    def __init__(
        self,
        message: str,
        *,
        cmd: str,
        cwd: str,
        exit_code: int,
        stderr: Optional[str] = None,
    ):
        super().__init__(message)
        self.cmd = cmd
        self.cwd = cwd
        self.exit_code = exit_code
        self.stderr = stderr


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


@dataclass(frozen=True)
class GrepMatch:
    """A single match from a grep search."""

    path: str
    """Absolute path to the file containing the match."""

    line: int
    """Line number (1-based)."""

    text: str
    """The matching line content."""

    column: Optional[int] = None
    """Column number of match start (1-based), if available."""


@dataclass(frozen=True)
class WriteResult:
    """Result of a file write operation."""

    path: str
    """Absolute path to the file that was written."""

    bytes_written: int
    """Number of bytes written to the file."""

    created: bool
    """True if a new file was created, False if existing file was overwritten."""


@dataclass(frozen=True)
class EditResult:
    """Result of a file edit operation."""

    path: str
    """Absolute path to the file that was edited."""

    replacements_made: int
    """Number of replacements performed."""

    bytes_before: int
    """File size in bytes before editing."""

    bytes_after: int
    """File size in bytes after editing."""


@dataclass
class SandboxConfig:
    """Configuration for sandbox creation and lifecycle."""

    timeout: int = 300
    """Sandbox lifetime in seconds (default: 5 minutes)."""

    api_key: Optional[str] = None
    """API key for sandbox service (if required)."""

    envs: Optional[Dict[str, str]] = None
    """Environment variables to set in the sandbox."""

    metadata: Dict[str, Any] = None
    """Additional provider-specific configuration."""

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.envs is None:
            self.envs = {}


class SandboxConnection(ABC):
    """Abstract base class for sandbox connections.

    This provides a unified interface for interacting with different
    sandbox environments (E2B, Modal, Docker, etc.).
    """

    # Default repository root path. Subclasses must override with their
    # implementation-specific default (e.g., E2BSandbox uses "/home/user/repo").
    DEFAULT_REPO_ROOT: Optional[str] = None

    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
        default_repo_root: Optional[str] = None,
    ):
        """Initialize sandbox connection with optional configuration.

        Args:
            config: Sandbox configuration. If None, uses defaults.
            default_repo_root: Override the default repository root path.
                If None, uses the class-level DEFAULT_REPO_ROOT.
        """
        self.config = config or SandboxConfig()
        self._default_repo_root = default_repo_root or self.DEFAULT_REPO_ROOT
        if self._default_repo_root is None:
            raise ValueError(
                "default_repo_root must be provided (backend has no default)"
            )
        self._is_alive = False

    @property
    def default_repo_root(self) -> str:
        """Default repository root path for this sandbox."""
        return self._default_repo_root

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
    def read_file_bytes(self, path: str, max_bytes: Optional[int] = None) -> bytes:
        """Read file contents as bytes from the sandbox filesystem.

        Note: Backends may enforce max_bytes either during transfer (preferred)
        or by truncating after read.

        Args:
            path: Absolute path to file in sandbox.
            max_bytes: Maximum bytes to read (safety limit). None for no limit.

        Returns:
            File contents as bytes.

        Raises:
            FileNotFoundError: If file doesn't exist.
            RuntimeError: If sandbox is not alive.
        """
        pass

    def read_file_text(
        self,
        path: str,
        encoding: str = "utf-8",
        errors: str = "strict",
        max_bytes: Optional[int] = None,
    ) -> str:
        """Read file contents as text from the sandbox filesystem.

        Convenience wrapper around read_file_bytes that decodes to string.

        Args:
            path: Absolute path to file in sandbox.
            encoding: Text encoding (default: utf-8).
            errors: How to handle decode errors:
                - "strict": raise on invalid bytes (default, good for source files)
                - "replace": substitute invalid bytes with replacement char
                - "ignore": drop invalid bytes (rarely what you want)
            max_bytes: Maximum bytes to read (safety limit). None for no limit.

        Returns:
            File contents as string.
        """
        return self.read_file_bytes(path, max_bytes).decode(encoding, errors=errors)

    @abstractmethod
    def glob(
        self,
        pattern: str,
        root: str = ".",
        *,
        absolute: bool = True,
        dot: bool = False,
        follow_symlinks: bool = False,
        max_results: Optional[int] = None,
    ) -> List[str]:
        """Find files matching a glob pattern.

        Semantics:
        - `root` is the base directory to search under
        - `pattern` is interpreted relative to `root`
        - Relative `root` (e.g., ".") is resolved against the sandbox's workspace root
        - Example: glob("**/*.md", root="/repo/src") searches /repo/src/**/*.md
        - Supports ** for recursive matching
        - Does NOT support {a,b} brace expansion
        - If dot=False, paths with any segment starting with . are excluded
          unless the pattern segment explicitly starts with .
        - If dot=True, hidden files/dirs are eligible for matching and traversal
        - Results are sorted lexicographically, then truncated if max_results set

        Args:
            pattern: Glob pattern (e.g., "*.py", "**/*.md", "SKILL.md").
            root: Base directory to search from. Relative paths resolved to workspace root.
            absolute: Whether to return absolute paths (default: True).
            dot: Whether to match dotfiles/directories (default: False).
            follow_symlinks: Whether to follow symlinks (default: False).
            max_results: Maximum results to return (truncated after sorting).

        Returns:
            List of matching file paths, sorted lexicographically.

        Raises:
            FileNotFoundError: If root directory doesn't exist.
            ValueError: If pattern is empty or invalid.
            SandboxCommandError: If the underlying search operation fails.
        """
        pass

    @abstractmethod
    def grep(
        self,
        pattern: str,
        path: str = ".",
        *,
        include: Optional[str] = None,
        ignore_case: bool = False,
        regex: bool = True,
        max_results: Optional[int] = None,
    ) -> List[GrepMatch]:
        """Search file contents for a pattern.

        Semantics:
        - If `path` is a file: search only that file (include is ignored)
        - If `path` is a directory: search recursively under it
        - Relative `path` (e.g., ".") is resolved against the sandbox's workspace root
        - `include` filters files by path relative to `path` (e.g., "**/*.py")
        - Results are ordered by (path, line, column) for determinism
          - column=None is treated as 0 for sorting purposes
          - column is 1-based byte offset, not Unicode codepoint
        - If max_results set, all matches are gathered, sorted, then truncated to first N

        Args:
            pattern: Pattern to search for (regex or literal depending on `regex` flag).
            path: File or directory to search in. Relative paths resolved to workspace root.
            include: Glob pattern to filter files, matched against path relative to `path`.
            ignore_case: Whether to ignore case in pattern matching.
            regex: If True, treat pattern as regex. If False, treat as literal string.
            max_results: Maximum matches to return (truncated after sorting).

        Returns:
            List of GrepMatch objects with path, line number, and matched text.

        Raises:
            FileNotFoundError: If path doesn't exist.
            ValueError: If pattern or include is empty or invalid.
            SandboxCommandError: If the underlying search operation fails.
        """
        pass

    @abstractmethod
    def write_file(
        self,
        path: str,
        content: str | bytes,
        *,
        create_dirs: bool = True,
        overwrite: bool = True,
        encoding: str = "utf-8",
    ) -> WriteResult:
        """Write content to a file in the sandbox filesystem.

        Semantics:
        - Relative paths are resolved against the sandbox's workspace root
        - If content is str, it is encoded using the specified encoding
        - If content is bytes, encoding is ignored and bytes are written directly
        - If create_dirs=True, parent directories are created as needed
        - If overwrite=False and file exists, raises FileExistsError
        - If path points to an existing directory, raises IsADirectoryError

        Args:
            path: File path (absolute or relative to workspace root).
            content: Content to write (str or bytes).
            create_dirs: Create parent directories if they don't exist (default: True).
            overwrite: Allow overwriting existing files (default: True).
            encoding: Encoding to use when content is str (default: utf-8).

        Returns:
            WriteResult with path, bytes_written, and created flag.

        Raises:
            ValueError: If path is empty.
            FileExistsError: If overwrite=False and file already exists.
            IsADirectoryError: If path points to an existing directory.
            RuntimeError: If sandbox is not alive or directory creation fails.
        """
        pass

    @abstractmethod
    def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        *,
        replace_all: bool = False,
        allow_no_match: bool = False,
        expected_replacements: Optional[int] = None,
        encoding: str = "utf-8",
    ) -> EditResult:
        """Edit a file by replacing exact string matches.

        Semantics:
        - Relative paths are resolved against the sandbox's workspace root
        - Matching is exact (byte-for-byte after encoding), not fuzzy
        - If replace_all=False (default), exactly one match is required
        - If replace_all=True, all matches are replaced
        - expected_replacements asserts an exact match count; errors if different
        - expected_replacements=0 asserts old_string is ABSENT: succeeds only if
          there are 0 matches; errors if any matches exist
        - To "remove if present, ignore if absent," use allow_no_match=True
          (with expected_replacements=None)

        Args:
            path: File path (absolute or relative to workspace root).
            old_string: Exact string to find and replace. Must not be empty.
            new_string: Replacement string. May be empty to delete matches.
            replace_all: If True, replace all occurrences. If False, require exactly one match.
            allow_no_match: If True, return success (no-op) when old_string is not found.
                Use for idempotent edits like "remove if present." Typically combined
                with replace_all=True for cleanup. Default: False.
            expected_replacements: Optional guard - assert exact match count.
                Use expected_replacements=0 to assert old_string is absent.
            encoding: Encoding for reading and writing the file (default: utf-8).

        Returns:
            EditResult with path, replacements_made, bytes_before, and bytes_after.

        Raises:
            ValueError: If old_string is empty, old_string == new_string,
                allow_no_match is combined with expected_replacements, or match
                count doesn't satisfy constraints (not exactly 1 when
                replace_all=False, or doesn't match expected_replacements).
            FileNotFoundError: If file doesn't exist.
            IsADirectoryError: If path points to a directory.
            RuntimeError: If sandbox is not alive.
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

    async def upload_directory(
        self,
        local_dir: Path,
        remote_dir: str,
        exclude: Optional[set[str]] = None,
    ) -> None:
        """Upload a directory recursively to the sandbox with parallel file uploads.

        Args:
            local_dir: Local directory path to upload
            remote_dir: Remote path in sandbox where directory should be uploaded
            exclude: Optional set of file/directory names to exclude at all levels
                    (e.g., {".git", "__pycache__", ".DS_Store"})

        Raises:
            RuntimeError: If directory creation or file upload fails
        """
        exclude = exclude or set()

        # Create the remote directory
        result = self.run_command(f"mkdir -p {remote_dir}")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create remote directory {remote_dir}: {result.error}")

        # Collect all files to upload, filtering excluded items
        upload_tasks = []
        for root, dirs, files in os.walk(local_dir):
            # Filter out excluded directories in-place (prevents os.walk from descending)
            dirs[:] = [d for d in dirs if d not in exclude]

            for file in files:
                # Skip excluded files
                if file in exclude:
                    continue

                local_file = Path(root) / file
                # Calculate relative path from local_dir
                rel_path = local_file.relative_to(local_dir)
                remote_file = f"{remote_dir}/{rel_path}"

                upload_tasks.append((local_file, remote_file))

        # Create all necessary parent directories first
        parent_dirs = set()
        for _, remote_file in upload_tasks:
            remote_parent = str(Path(remote_file).parent)
            if remote_parent != remote_dir:
                parent_dirs.add(remote_parent)

        # Create parent directories
        for parent_dir in parent_dirs:
            result = self.run_command(f"mkdir -p {parent_dir}")
            if result.exit_code != 0:
                logger.warning(f"Failed to create {parent_dir}: {result.error}")

        # Upload all files in parallel
        async def upload_file_async(local_file: Path, remote_file: str) -> None:
            await asyncio.to_thread(self.upload_file, local_file, remote_file)
            logger.debug(f"Uploaded {local_file} to {remote_file}")

        await asyncio.gather(*[
            upload_file_async(local_file, remote_file)
            for local_file, remote_file in upload_tasks
        ])

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
