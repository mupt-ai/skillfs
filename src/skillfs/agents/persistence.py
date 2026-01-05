"""Agent state persistence using Git bundles and cloud storage.

This module provides high-level functions for saving and loading agent state
between sandbox sessions. It orchestrates GitRepo operations, file transfers,
and cloud storage uploads/downloads.
"""

import logging
from datetime import datetime, timezone
import shlex
from shlex import quote
from pathlib import Path
from tempfile import TemporaryDirectory

from skillfs.repositories.git_repo import GitRepo
from skillfs.sandboxes.base import SandboxConnection
from skillfs.storage.base import BundleStore

logger = logging.getLogger(__name__)

# Bundle path template inside sandbox
BUNDLE_PATH_TEMPLATE = "/tmp/skillfs-bundles/{agent_id}.bundle"

def load_agent_state(
    agent_id: str,
    sandbox: SandboxConnection,
    bundle_store: BundleStore,
    repo_root: str | None = None,
) -> GitRepo:
    """Load agent state from cloud storage into sandbox.

    If a bundle exists for the agent in cloud storage, it downloads and restores
    it into the sandbox. Otherwise, initializes a fresh repository with the
    SkillFS directory structure.

    Args:
        agent_id: Unique identifier for the agent.
        sandbox: Active sandbox connection.
        bundle_store: Cloud storage for bundles.
        repo_root: Path inside sandbox for the repository.
            If None, uses sandbox.default_repo_root.

    Returns:
        GitRepo instance connected to the restored or initialized repository.

    Raises:
        RuntimeError: If bundle download, upload, or git operations fail.
    """
    logger.info(f"Loading state for agent {agent_id}")

    # Resolve repo_root from sandbox if not provided
    resolved_root = repo_root if repo_root is not None else sandbox.default_repo_root

    # Create GitRepo instance (validates git is available)
    git_repo = GitRepo(sandbox, root=resolved_root)

    # Try to download existing bundle from cloud storage
    with TemporaryDirectory() as tmpdir:
        local_bundle = Path(tmpdir) / f"{agent_id}.bundle"

        if bundle_store.download_bundle(agent_id, local_bundle):
            # Bundle exists - restore from it
            logger.info("Restoring agent state from existing bundle")

            # Upload bundle from host to sandbox
            remote_bundle = BUNDLE_PATH_TEMPLATE.format(agent_id=agent_id)

            # Ensure target directory exists in sandbox
            bundle_dir = remote_bundle.rsplit("/", 1)[0] if "/" in remote_bundle else "."
            bundle_dir_q = quote(bundle_dir)
            mkdir_result = sandbox.run_command(f"mkdir -p {bundle_dir_q}")
            if mkdir_result.exit_code != 0:
                raise RuntimeError(
                    f"Failed to create bundle directory in sandbox: {mkdir_result.error}"
                )

            # Guard: resolved_root must be empty or absent before restore
            escaped_root = shlex.quote(resolved_root)
            empty_check = (
                f"if [ -d {escaped_root} ] && [ -n \"$(ls -A {escaped_root} 2>/dev/null)\" ]; "
                f"then echo NONEMPTY; fi; exit 0"
            )
            empty_result = sandbox.run_command(empty_check)
            if empty_result.exit_code != 0:
                raise RuntimeError(
                    f"Failed to check repo_root emptiness: {empty_result.error or empty_result.logs}"
                )
            if "NONEMPTY" in (empty_result.logs or ""):
                raise RuntimeError(
                    f"Cannot restore into non-empty repo_root: {resolved_root}. "
                    "Please provide an empty or nonexistent directory."
                )

            sandbox.upload_file(local_bundle, remote_bundle)

            # Restore repository from bundle
            git_repo.restore_from_bundle(remote_bundle, checkout_dir=resolved_root)

            logger.info("Agent state restored successfully")
        else:
            # No bundle exists - initialize fresh repository
            logger.info("No existing bundle found, initializing fresh repository")
            git_repo.init_empty()
            logger.info("Fresh repository initialized")

    return git_repo


def save_agent_state(
    agent_id: str,
    sandbox: SandboxConnection,
    git_repo: GitRepo,
    bundle_store: BundleStore,
    commit_message: str | None = None,
) -> None:
    """Save agent state from sandbox to cloud storage.

    Commits any pending changes, creates a git bundle, and uploads it to
    cloud storage for persistence across sandbox sessions.

    Args:
        agent_id: Unique identifier for the agent.
        sandbox: Active sandbox connection.
        git_repo: GitRepo instance managing the repository.
        bundle_store: Cloud storage for bundles.
        commit_message: Optional custom commit message. If None, generates
                       a default message with timestamp.

    Raises:
        RuntimeError: If git operations, file transfer, or upload fails.
    """
    logger.info(f"Saving state for agent {agent_id}")

    # Generate default commit message if not provided
    if commit_message is None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        commit_message = f"Auto-checkpoint for agent {agent_id} at {timestamp}"

    # Stage all changes
    logger.info("Staging changes")
    git_repo.add_all()

    # Commit changes
    result = git_repo.commit(commit_message)
    if result.exit_code == 0:
        logger.info("Changes committed successfully")
    else:
        # Fail only if the error is not the expected "nothing to commit" case
        msg_lower = (result.logs or "").lower()
        if "nothing to commit" in msg_lower:
            logger.info("No changes to commit, creating bundle from current state")
        else:
            raise RuntimeError(
                f"Git commit failed: {result.error or result.logs or 'unknown error'}"
            )

    # Create bundle inside sandbox
    remote_bundle = BUNDLE_PATH_TEMPLATE.format(agent_id=agent_id)
    logger.info(f"Creating bundle at {remote_bundle}")
    git_repo.create_bundle(remote_bundle)

    # Download bundle from sandbox to host
    with TemporaryDirectory() as tmpdir:
        local_bundle = Path(tmpdir) / f"{agent_id}.bundle"
        logger.info("Downloading bundle from sandbox to host")
        sandbox.download_file(remote_bundle, local_bundle)

        # Upload bundle to cloud storage
        logger.info("Uploading bundle to cloud storage")
        bundle_store.upload_bundle(agent_id, local_bundle)

    logger.info(f"Agent state saved successfully for {agent_id}")
