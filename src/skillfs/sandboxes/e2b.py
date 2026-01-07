"""E2B sandbox implementation."""

import json
import os
import posixpath
import shlex
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

from e2b_code_interpreter import Sandbox

from skillfs.constants import E2B_DEFAULT_REPO_ROOT
from skillfs.sandboxes.base import (
    SandboxConnection,
    SandboxConfig,
    SandboxCommandError,
    ExecutionResult,
    GrepMatch,
    WriteResult,
    EditResult,
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

        To use a custom template:
        >>> config = SandboxConfig(metadata={"template": "your-template-id"})
        >>> sandbox = E2BSandbox.create(config=config)
    """

    DEFAULT_REPO_ROOT = E2B_DEFAULT_REPO_ROOT
    DEFAULT_TEMPLATE = "f2p2ivjafffh63exstg0"
    """Default E2B template with uv preinstalled."""

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

        # Get template from config metadata or use default
        template = instance.config.metadata.get("template", cls.DEFAULT_TEMPLATE)

        # Create E2B sandbox (timeout is applied per run_code call)
        instance._sandbox = Sandbox.create(
            api_key=api_key,
            template=template,
            envs=instance.config.envs or {}
        )

        instance._is_alive = True

        # Install ripgrep for grep operations
        instance._sandbox.commands.run("sudo apt-get install -y ripgrep")

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
        # E2B raises CommandExitException for non-zero exit codes, so we catch it
        try:
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
        except Exception as e:
            # Handle CommandExitException and other errors
            # Extract stdout, stderr, and exit code if available
            error_msg = str(e)
            exit_code = 1

            # Try to parse the error message for details
            if hasattr(e, 'exit_code'):
                exit_code = e.exit_code

            # Extract stdout and stderr if available
            stdout = getattr(e, 'stdout', '')
            stderr = getattr(e, 'stderr', error_msg)

            return ExecutionResult(
                logs=stdout,
                error=stderr,
                exit_code=exit_code,
            )

    @property
    def _normalized_repo_root(self) -> str:
        """Normalized default_repo_root with no trailing slash."""
        return self.default_repo_root.rstrip("/") or "/"

    def _resolve_path(self, path: str) -> str:
        """Resolve a path, making relative paths absolute against repo root.

        Args:
            path: Path to resolve (absolute or relative).

        Returns:
            Absolute path, normalized with no trailing slash.

        Raises:
            ValueError: If relative path contains '..' traversal.
        """
        if path in ("", "."):
            return self._normalized_repo_root

        if path.startswith("/"):
            return posixpath.normpath(path).rstrip("/") or "/"

        # Reject path traversal for agent safety (check actual segments, not substrings)
        if any(segment == ".." for segment in path.split("/")):
            raise ValueError(f"Relative path must not contain '..': {path}")

        # Strip leading "./" prefix properly (not lstrip which removes chars)
        if path.startswith("./"):
            path = path[2:]

        joined = posixpath.join(self._normalized_repo_root, path)
        return posixpath.normpath(joined).rstrip("/") or "/"

    def _anchor_glob(self, pattern: str) -> str:
        """Anchor a glob pattern to match relative to search root.

        Ripgrep uses gitignore-style semantics where unanchored patterns
        can match at any depth. Prefixing with '/' anchors them.

        Args:
            pattern: Glob pattern to anchor.

        Returns:
            Anchored pattern (prefixed with '/' if not already).
        """
        # Handle negation patterns (e.g., "!**/node_modules/**")
        if pattern.startswith("!"):
            return "!" + self._anchor_glob(pattern[1:])
        if pattern.startswith("/"):
            return pattern
        return "/" + pattern

    def _rg_err(
        self,
        action: str,
        *,
        cmd: str,
        cwd: str,
        result: ExecutionResult,
    ) -> str:
        """Format a ripgrep error message with context.

        Prefers stderr (result.error) over stdout (result.logs) for the detail.

        Args:
            action: Action being performed (e.g., "glob", "grep").
            cmd: The command that was run.
            cwd: Working directory the command ran in.
            result: ExecutionResult from run_command.

        Returns:
            Formatted error message string.
        """
        detail = (result.error or result.logs or "").strip()
        if not detail:
            detail = f"(no stderr/stdout; exit_code={result.exit_code})"
        return (
            f"{action} failed (exit_code={result.exit_code}) "
            f"cwd={cwd!r} cmd={cmd!r}: {detail}"
        )

    def _rg_json_str(self, obj: dict, *, is_path: bool = False) -> str:
        """Extract string from ripgrep JSON object that may be text or base64 bytes.

        ripgrep --json outputs strings as either {"text": "..."} for valid UTF-8
        or {"bytes": "<base64>"} for non-UTF-8 (e.g., binary paths or content).

        Args:
            obj: JSON object with either "text" or "bytes" key.
            is_path: If True, use os.fsdecode for filesystem path semantics.
                If False, use surrogateescape for content preservation.

        Returns:
            Decoded string.
        """
        import base64

        if "text" in obj:
            return obj["text"]
        if "bytes" in obj:
            raw = base64.b64decode(obj["bytes"])
            if is_path:
                # Use filesystem decoding for paths (handles platform-specific encoding)
                return os.fsdecode(raw)
            else:
                # Use surrogateescape for content to preserve non-UTF-8 bytes
                return raw.decode("utf-8", errors="surrogateescape")
        return ""

    def read_file_bytes(self, path: str, max_bytes: Optional[int] = None) -> bytes:
        """Read file contents as bytes from the E2B sandbox filesystem.

        Note: Currently truncates after transfer. For large files, consider
        using run_command with head -c for bandwidth efficiency.

        Args:
            path: Absolute path to file in sandbox.
            max_bytes: Maximum bytes to read (must be non-negative if provided).
                Truncated after transfer.

        Returns:
            File contents as bytes.

        Raises:
            ValueError: If path is not absolute or max_bytes is negative.
            FileNotFoundError: If file doesn't exist.
            RuntimeError: If sandbox is not alive.
        """
        if not self.is_alive or not self._sandbox:
            raise RuntimeError("Sandbox is not active.")

        if not path.startswith("/"):
            raise ValueError(f"Path must be absolute, got: {path}")

        if max_bytes is not None and max_bytes < 0:
            raise ValueError(f"max_bytes must be non-negative, got: {max_bytes}")

        try:
            content = self._sandbox.files.read(path, format="bytes")
        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "no such file" in error_str:
                raise FileNotFoundError(f"File not found: {path}")
            raise

        if max_bytes is not None:
            content = content[:max_bytes]

        # E2B returns bytearray; convert to bytes for correct return type
        return bytes(content)

    def read_file_text(
        self,
        path: str,
        encoding: str = "utf-8",
        errors: str = "strict",
        max_bytes: Optional[int] = None,
    ) -> str:
        """Read file contents as text from the E2B sandbox filesystem.

        Convenience wrapper around read_file_bytes that decodes to string.

        Args:
            path: Absolute path to file in sandbox.
            encoding: Text encoding (default: utf-8).
            errors: How to handle decode errors:
                - "strict": raise on invalid bytes (default, good for source)
                - "replace": substitute invalid bytes with replacement char
                - "ignore": drop invalid bytes (rarely what you want)
            max_bytes: Maximum bytes to read (safety limit). None for no limit.

        Returns:
            File contents as string.

        Raises:
            ValueError: If path is not absolute or max_bytes is negative.
            FileNotFoundError: If file doesn't exist.
            RuntimeError: If sandbox is not alive.
            UnicodeDecodeError: If decoding fails and errors="strict".
        """
        return self.read_file_bytes(path, max_bytes).decode(encoding, errors=errors)

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
        """Find files matching a glob pattern in E2B sandbox.

        Uses ripgrep (rg --files --glob) for proper ** support. Note that
        ripgrep's --glob filtering overrides other ignore rules.

        Semantics:
        - Patterns are matched relative to `root`; use **/ for recursive matches
        - Example: "*.py" matches only top-level .py files; "**/*.py" is recursive
        - Skips hidden files/directories by default; set dot=True to include them

        Args:
            pattern: Glob pattern (e.g., "*.py", "**/*.md", "src/**/*.py").
            root: Base directory to search from. Relative paths resolved to
                default_repo_root.
            absolute: Whether to return absolute paths (default: True).
            dot: Whether to match dotfiles/directories (default: False).
            follow_symlinks: Whether to follow symlinks (default: False).
            max_results: Maximum results to return.

        Returns:
            List of matching file paths, sorted lexicographically.

        Raises:
            FileNotFoundError: If root directory doesn't exist.
            ValueError: If pattern is empty or a bare '!'.
            SandboxCommandError: If ripgrep fails (invalid pattern, etc.).
        """
        if not self.is_alive or not self._sandbox:
            raise RuntimeError("Sandbox is not active.")

        if not pattern:
            raise ValueError("pattern must be non-empty")

        if pattern == "!":
            raise ValueError("pattern must not be a bare '!'")

        root_abs = self._resolve_path(root)

        # Check if root exists (consistency with grep)
        exists = self.run_command(f"test -d {shlex.quote(root_abs)}").exit_code == 0
        if not exists:
            raise FileNotFoundError(f"Directory not found: {root_abs}")

        # Anchor pattern to match "relative to root" semantics
        glob_pat = self._anchor_glob(pattern)

        args = ["rg", "--files", "--color", "never"]
        if follow_symlinks:
            args.append("--follow")
        if dot:
            args.append("--hidden")

        args += ["--glob", glob_pat]

        cmd = " ".join(shlex.quote(a) for a in args)

        # Run with cwd=root_abs so glob is relative to root
        result = self.run_command(cmd, cwd=root_abs)

        # Handle ripgrep exit codes properly
        # Exit code 1 = no files matched (not an error)
        if result.exit_code == 1:
            return []

        # Exit code 2 = error (invalid glob, bad args, etc.)
        # Any other nonzero exit => SandboxCommandError
        if result.exit_code != 0:
            raise SandboxCommandError(
                self._rg_err("glob", cmd=cmd, cwd=root_abs, result=result),
                cmd=cmd,
                cwd=root_abs,
                exit_code=result.exit_code,
                stderr=result.error,
            )

        # Success: parse output. Empty output => no matches => []
        if not result.logs.strip():
            return []

        # rg outputs relative paths; make absolute if requested
        paths = []
        for p in result.logs.splitlines():
            if not p:
                continue
            if absolute:
                # Join with root_abs and normalize
                p = posixpath.normpath(posixpath.join(root_abs, p))
            paths.append(p)

        paths.sort()

        if max_results is not None:
            paths = paths[:max_results]

        return paths

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
        """Search file contents for a pattern in E2B sandbox.

        Uses ripgrep with --json for structured output including column.
        Note that ripgrep's --glob filtering overrides other ignore rules.

        Semantics:
        - If `path` is a file: search only that file (include is ignored)
        - If `path` is a directory: search recursively under it
        - Relative `path` is resolved against default_repo_root
        - `include` filters files by glob (e.g., "**/*.py" for recursive)
        - Column is 1-based byte offset of first submatch, not Unicode char

        Args:
            pattern: Pattern to search for (regex or literal per `regex` flag).
            path: File or directory to search in.
            include: Glob pattern to filter files (e.g., "**/*.py").
            ignore_case: Whether to ignore case.
            regex: If True, treat as regex. If False, treat as literal.
            max_results: Maximum matches to return.

        Returns:
            List of GrepMatch objects with absolute paths, sorted by
            (path, line, column).

        Raises:
            FileNotFoundError: If path doesn't exist.
            ValueError: If pattern or include is empty or a bare '!'.
            SandboxCommandError: If ripgrep fails (invalid pattern, etc.).
        """
        if not self.is_alive or not self._sandbox:
            raise RuntimeError("Sandbox is not active.")

        if not pattern:
            raise ValueError("pattern must be non-empty")

        if include is not None and not include:
            raise ValueError("include must be non-empty if provided")

        if include == "!":
            raise ValueError("include must not be a bare '!'")

        target = self._resolve_path(path)

        # Check if target exists
        exists = self.run_command(f"test -e {shlex.quote(target)}").exit_code == 0
        if not exists:
            raise FileNotFoundError(f"Path not found: {target}")

        # Check if target is a file or directory
        is_file = self.run_command(f"test -f {shlex.quote(target)}").exit_code == 0

        if is_file:
            cwd = posixpath.dirname(target) or "/"
            search_target = posixpath.basename(target)
        else:
            cwd = target
            search_target = "."

        args = ["rg", "--json", "--color", "never"]
        if ignore_case:
            args.append("--ignore-case")
        if not regex:
            args.append("--fixed-strings")
        if include and not is_file:
            # Anchor include pattern to match semantics
            args += ["--glob", self._anchor_glob(include)]

        # Use -e to safely handle patterns starting with '-'
        # Use -- to separate options from positional args (handles filenames starting with '-')
        args += ["-e", pattern, "--", search_target]

        cmd = " ".join(shlex.quote(a) for a in args)
        result = self.run_command(cmd, cwd=cwd)

        # Handle ripgrep exit codes properly
        # Exit code 1 = no matches (not an error)
        if result.exit_code == 1:
            return []

        # Exit code 2 = error (invalid regex, bad args, etc.)
        # Any other nonzero exit => SandboxCommandError for consistency
        if result.exit_code != 0:
            raise SandboxCommandError(
                self._rg_err("grep", cmd=cmd, cwd=cwd, result=result),
                cmd=cmd,
                cwd=cwd,
                exit_code=result.exit_code,
                stderr=result.error,
            )

        # exit_code == 0 => parse JSON lines
        if not result.logs.strip():
            return []

        matches: List[GrepMatch] = []
        for line in result.logs.splitlines():
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") != "match":
                continue

            data = obj["data"]
            # rg outputs relative paths; make absolute
            # Use _rg_json_str to handle both "text" and "bytes" (base64) output
            file_path = self._rg_json_str(data["path"], is_path=True)
            if not file_path.startswith("/"):
                file_path = posixpath.normpath(posixpath.join(cwd, file_path))
            line_num = data["line_number"]
            text = self._rg_json_str(data["lines"]).rstrip("\n")

            # Use the first submatch for column (byte offset, 1-based)
            col = None
            subs = data.get("submatches") or []
            if subs:
                col = subs[0].get("start")
                if col is not None:
                    col = int(col) + 1  # Convert to 1-based

            matches.append(GrepMatch(
                path=file_path,
                line=int(line_num),
                text=text,
                column=col,
            ))

        matches.sort(key=lambda m: (m.path, m.line, m.column or 0))

        if max_results is not None:
            matches = matches[:max_results]

        return matches

    def write_file(
        self,
        path: str,
        content: str | bytes,
        *,
        create_dirs: bool = True,
        overwrite: bool = True,
        encoding: str = "utf-8",
    ) -> WriteResult:
        """Write content to a file in the E2B sandbox filesystem.

        Uses E2B's native files.write() for bit-perfect fidelity.

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
            FileNotFoundError: If create_dirs=False and parent directory doesn't exist.
            FileExistsError: If overwrite=False and file already exists.
            IsADirectoryError: If path points to an existing directory.
            UnicodeEncodeError: If content is str and cannot be encoded with the specified encoding.
            RuntimeError: If sandbox is not alive or directory creation fails.
        """
        if not self.is_alive or not self._sandbox:
            raise RuntimeError("Sandbox is not active.")

        if not path:
            raise ValueError("path must be non-empty")

        abs_path = self._resolve_path(path)

        # Check if path is an existing directory
        is_dir = self.run_command(f"test -d {shlex.quote(abs_path)}").exit_code == 0
        if is_dir:
            raise IsADirectoryError(f"Path is a directory: {abs_path}")

        # Check if file exists (for created flag and overwrite check)
        file_exists = self.run_command(f"test -f {shlex.quote(abs_path)}").exit_code == 0

        # Reject special file types (device files, sockets, named pipes, etc.)
        path_exists = self.run_command(f"test -e {shlex.quote(abs_path)}").exit_code == 0
        if path_exists and not file_exists and not is_dir:
            raise OSError(f"Path exists but is not a regular file or directory: {abs_path}")

        if file_exists and not overwrite:
            raise FileExistsError(f"File already exists: {abs_path}")

        # Handle parent directory creation
        # Note: E2B's files.write() auto-creates directories, so we must enforce
        # create_dirs=False by checking parent exists BEFORE calling write
        parent_dir = posixpath.dirname(abs_path)
        if parent_dir and parent_dir != "/":
            parent_exists = self.run_command(f"test -d {shlex.quote(parent_dir)}").exit_code == 0
            if not parent_exists:
                if not create_dirs:
                    raise FileNotFoundError(f"Parent directory not found: {parent_dir}")
                # create_dirs=True: explicitly create (though E2B would do it anyway)
                result = self.run_command(f"mkdir -p {shlex.quote(parent_dir)}")
                if result.exit_code != 0:
                    raise RuntimeError(
                        f"Failed to create parent directory {parent_dir}: {result.error}"
                    )

        # Encode content if it's a string
        if isinstance(content, str):
            content_bytes = content.encode(encoding)
        else:
            content_bytes = content

        self._sandbox.files.write(abs_path, content_bytes)

        return WriteResult(
            path=abs_path,
            bytes_written=len(content_bytes),
            created=not file_exists,
        )

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

        Reads the file, performs exact string replacement, and writes back
        using E2B's native files.write() for bit-perfect fidelity.

        Semantics:
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
            ValueError: If path is empty, old_string is empty, old_string == new_string,
                allow_no_match is combined with expected_replacements, or match count
                doesn't satisfy constraints.
            FileNotFoundError: If file doesn't exist.
            IsADirectoryError: If path points to a directory.
            UnicodeDecodeError: If file cannot be decoded with the specified encoding.
            UnicodeEncodeError: If new content cannot be encoded with the specified encoding.
            RuntimeError: If sandbox is not alive.
        """
        if not self.is_alive or not self._sandbox:
            raise RuntimeError("Sandbox is not active.")

        # Validate inputs
        if not path:
            raise ValueError("path must be non-empty")

        if not old_string:
            raise ValueError("old_string must not be empty")

        if old_string == new_string:
            raise ValueError("old_string and new_string must be different")

        if allow_no_match and expected_replacements is not None:
            raise ValueError(
                "allow_no_match cannot be used with expected_replacements; "
                "set expected_replacements=None or drop allow_no_match"
            )

        if expected_replacements is not None and expected_replacements < 0:
            raise ValueError(
                f"expected_replacements must be >= 0, got: {expected_replacements}"
            )

        abs_path = self._resolve_path(path)

        # Check if path is a directory
        is_dir = self.run_command(f"test -d {shlex.quote(abs_path)}").exit_code == 0
        if is_dir:
            raise IsADirectoryError(f"Path is a directory: {abs_path}")

        # Check if file exists
        file_exists = self.run_command(f"test -f {shlex.quote(abs_path)}").exit_code == 0
        if not file_exists:
            raise FileNotFoundError(f"File not found: {abs_path}")

        # Read current content
        try:
            raw_bytes = bytes(self._sandbox.files.read(abs_path, format="bytes"))
            content = raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            raise  # Let caller handle decode errors
        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "no such file" in error_str:
                raise FileNotFoundError(f"File not found: {abs_path}")
            raise

        # Use original byte length (not re-encoded) for accurate file size
        bytes_before = len(raw_bytes)

        # Count occurrences
        count = content.count(old_string)

        # Validate count against constraints
        if count == 0:
            # No-op success cases:
            # - expected_replacements=0: "assert absent" passed
            # - allow_no_match=True: idempotent edit, nothing to remove
            if expected_replacements == 0 or allow_no_match:
                return EditResult(
                    path=abs_path,
                    replacements_made=0,
                    bytes_before=bytes_before,
                    bytes_after=bytes_before,
                )
            raise ValueError(
                "old_string not found in file (set allow_no_match=True to treat as no-op)"
            )

        if not replace_all and count > 1:
            raise ValueError(
                f"old_string found {count} times (expected exactly 1 match, "
                f"use replace_all=True to replace all)"
            )

        if expected_replacements is not None and count != expected_replacements:
            raise ValueError(
                f"Expected {expected_replacements} replacements but found {count} matches"
            )

        # Perform replacement
        if replace_all:
            new_content = content.replace(old_string, new_string)
            replacements_made = count
        else:
            # Replace exactly one occurrence (first one)
            # Note: count is guaranteed to be 1 here (0 and >1 cases rejected above)
            new_content = content.replace(old_string, new_string, 1)
            replacements_made = 1

        # Write back using E2B's native API
        new_content_bytes = new_content.encode(encoding)
        self._sandbox.files.write(abs_path, new_content_bytes)

        return EditResult(
            path=abs_path,
            replacements_made=replacements_made,
            bytes_before=bytes_before,
            bytes_after=len(new_content_bytes),
        )

    def close(self) -> None:
        """Terminate and cleanup the E2B sandbox instance."""
        if self._sandbox and self._is_alive:
            self._sandbox.kill()
            self._is_alive = False
            self._sandbox = None
