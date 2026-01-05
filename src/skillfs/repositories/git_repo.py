"""Git repository management inside sandbox environments."""

import logging
from dataclasses import dataclass
from typing import Optional
import uuid
import shlex

from skillfs.repositories.constants import (
    DEFAULT_GIT_USER_EMAIL,
    DEFAULT_GIT_USER_NAME,
    DEFAULT_GITIGNORE,
)
from skillfs.sandboxes.base import ExecutionResult, SandboxConnection

logger = logging.getLogger(__name__)


@dataclass
class GitRepo:
    """Manages a Git repository inside a sandbox environment.

    This class provides Git operations via SandboxConnection.run_command,
    abstracting common patterns like init, restore from bundle, commit, etc.

    Example:
        >>> from skillfs.sandboxes import E2BSandbox
        >>> from skillfs.repositories import GitRepo
        >>> sandbox = E2BSandbox.create()
        >>> git_repo = GitRepo(sandbox, root="/home/user/repo")
        >>> git_repo.init_empty()
        >>> git_repo.add_all()
        >>> git_repo.commit("Initial commit")
    """

    sandbox: SandboxConnection
    root: Optional[str] = None

    def __post_init__(self) -> None:
        """Resolve root from sandbox default if not provided, verify git is available."""
        if self.root is None:
            self.root = self.sandbox.default_repo_root

        logger.debug("Checking git availability in sandbox")
        result = self.sandbox.run_command("git --version")
        if result.exit_code != 0:
            raise RuntimeError(
                "git is not available in the sandbox environment. "
                "Please ensure git is installed."
            )
        logger.debug(f"Git available: {result.logs.strip()}")

    def _run(self, command: str) -> ExecutionResult:
        """Run a git command in the repository root directory.

        Args:
            command: Git command to execute (without 'cd' prefix).

        Returns:
            ExecutionResult from the command execution.
        """
        return self.sandbox.run_command(command, cwd=self.root)

    @staticmethod
    def _quote(path: str) -> str:
        """Shell-quote a path/argument for safe interpolation."""
        return shlex.quote(path)

    def init_empty(self) -> None:
        """Initialize the repository by cloning a template with no remote.

        Clones https://github.com/mupt-ai/agent-runtime-template.git into the repo root, 
        removes the remote, and sets local user config. Overwrites root directory if not empty.

        Raises:
            RuntimeError: If the Git operations fail.
        """
        logger.info(f"Cloning agent-runtime-template repo into {self.root}")

        # Create root directory (if needed)
        result = self.sandbox.run_command(f"mkdir -p {self._quote(self.root)}")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create directory {self.root}: {result.error}")

        # Clone template repo into root
        result = self.sandbox.run_command(
            f"git clone --depth=1 https://github.com/mupt-ai/agent-runtime-template.git {self._quote(self.root)}"
        )
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to clone template repo: {result.error}")

        # Remove .git dir within the repo and re-init to prevent remote linkage/history retention
        result = self._run("rm -rf .git")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to remove .git after clone: {result.error}")

        # Re-initialize as a new repo
        result = self._run("git init .")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to reinitialize git repository: {result.error}")

        # Set default user config (local to this repo, as before)
        result = self._run(f'git config user.name "{DEFAULT_GIT_USER_NAME}"')
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to set git user.name: {result.error}")

        result = self._run(f'git config user.email "{DEFAULT_GIT_USER_EMAIL}"')
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to set git user.email: {result.error}")

        logger.info("Repository initialized from template with no remote.")

    def restore_from_bundle(
        self, bundle_path: str, checkout_dir: Optional[str] = None
    ) -> None:
        """Restore a Git repository from a bundle file.

        Args:
            bundle_path: Path to the bundle file inside the sandbox.
            checkout_dir: Directory to clone into (defaults to self.root).

        Raises:
            RuntimeError: If git clone from bundle fails.
        """
        target_dir = checkout_dir or self.root
        logger.info(f"Restoring Git repository from bundle {bundle_path} to {target_dir}")

        # Ensure parent directory exists
        parent_dir = target_dir.rsplit("/", 1)[0] if "/" in target_dir else "/"
        result = self.sandbox.run_command(f"mkdir -p {self._quote(parent_dir)}")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create parent directory: {result.error}")

        # Clone from bundle
        result = self.sandbox.run_command(
            f"git clone {self._quote(bundle_path)} {self._quote(target_dir)}"
        )
        if result.exit_code != 0:
            raise RuntimeError(
                f"Failed to restore repository from bundle: {result.error}\n{result.logs}"
            )

        # Set git user config (needed for commits in restored repo)
        result = self._run(f'git config user.name "{DEFAULT_GIT_USER_NAME}"')
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to set git user.name: {result.error}")

        result = self._run(f'git config user.email "{DEFAULT_GIT_USER_EMAIL}"')
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to set git user.email: {result.error}")

        logger.info("Git repository restored successfully")

    def status(self) -> str:
        """Get short git status output.

        Returns:
            Git status output as a string.

        Raises:
            RuntimeError: If git status fails.
        """
        result = self._run("git status --short")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to get git status: {result.error}")
        return result.logs

    def diff(self) -> str:
        """Get git diff output showing unstaged changes.

        Returns:
            Git diff output as a string.

        Raises:
            RuntimeError: If git diff fails.
        """
        result = self._run("git diff")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to get git diff: {result.error}")
        return result.logs

    def add_all(self, paths: Optional[list[str]] = None) -> None:
        """Stage changes for commit.

        Args:
            paths: Optional list of specific paths to stage.
                  If None, stages all changes (git add -A).

        Raises:
            RuntimeError: If git add fails.
        """
        if paths is None:
            cmd = "git add -A"
            logger.debug("Staging all changes")
        else:
            quoted = [self._quote(p) for p in paths]
            paths_str = " ".join(quoted)
            cmd = f"git add {paths_str}"
            logger.debug(f"Staging paths: {paths}")

        result = self._run(cmd)
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to stage changes: {result.error}")

    def commit(self, message: str) -> ExecutionResult:
        """Commit staged changes.

        Args:
            message: Commit message.

        Returns:
            ExecutionResult from git commit (allows inspecting "nothing to commit").

        Note:
            Unlike other methods, this returns ExecutionResult instead of raising
            on "nothing to commit" scenarios, allowing callers to handle gracefully.
        """
        logger.info(f"Creating commit: {message[:50]}...")

        # Write message to temp file in /tmp, then commit using -F to avoid escaping issues
        tmp_dir = "/tmp/skillfs-commit-msgs"
        tmp_dir_q = self._quote(tmp_dir)
        msg_file = f"{tmp_dir}/{str(uuid.uuid4().hex)}.msg"
        msg_file_q = self._quote(msg_file)

        # Ensure temp directory exists
        mkdir_res = self.sandbox.run_command(f"mkdir -p {tmp_dir_q}")
        if mkdir_res.exit_code != 0:
            raise RuntimeError(f"Failed to create temp dir for commit message: {mkdir_res.error}")

        # Write message to file (escape single quotes in the message)
        escaped_msg = message.replace("'", "'\\''")
        write_cmd = f"printf '%s' '{escaped_msg}' > {msg_file_q}"
        result = self.sandbox.run_command(write_cmd)
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to write commit message: {result.error}")

        # Commit using the message file
        result = self._run(f"git commit -F {msg_file_q}")

        # Clean up temp file
        self.sandbox.run_command(f"rm -f {msg_file_q}")

        # Log the result but don't raise on "nothing to commit"
        if result.exit_code != 0:
            if "nothing to commit" in result.logs.lower():
                logger.info("No changes to commit")
            else:
                logger.warning(f"Commit failed: {result.error}")
        else:
            logger.info("Commit created successfully")

        return result

    def create_bundle(self, bundle_path: str) -> str:
        """Create a Git bundle from the repository.

        Args:
            bundle_path: Path where bundle file should be created (inside sandbox).

        Returns:
            The bundle_path on success.

        Raises:
            RuntimeError: If git bundle create fails.
        """
        logger.info(f"Creating Git bundle at {bundle_path}")

        # Ensure parent directory exists
        # Allow bare filenames (no directory component) by defaulting to current dir
        bundle_dir = bundle_path.rsplit("/", 1)[0] if "/" in bundle_path else "."
        result = self.sandbox.run_command(f"mkdir -p {self._quote(bundle_dir)}")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create bundle directory: {result.error}")

        # Create bundle with all refs
        result = self._run(f"git bundle create {self._quote(bundle_path)} --all")
        if result.exit_code != 0:
            raise RuntimeError(
                f"Failed to create git bundle: {result.error}\n{result.logs}"
            )

        logger.info("Git bundle created successfully")
        return bundle_path
