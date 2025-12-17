"""Local filesystem storage backend for agent bundles."""

import logging
import shutil
from pathlib import Path

from skillfs.storage.base import BundleStore

logger = logging.getLogger(__name__)


class LocalBundleStore(BundleStore):
    """Store agent bundles in a local directory.

    This is a simple storage backend that saves bundles to a local filesystem
    directory. Useful for development, testing, or single-machine deployments.

    Example:
        >>> store = LocalBundleStore("/tmp/agent-bundles")
        >>> store.upload_bundle("agent-001", Path("/tmp/my-bundle.bundle"))
        >>> store.download_bundle("agent-001", Path("/tmp/restored.bundle"))
        True
    """

    def __init__(self, directory: str | Path, prefix: str = ""):
        """
        Initialize the local bundle store.

        Args:
            directory: Base directory where bundles will be stored.
                       Will be created if it doesn't exist.
            prefix: Optional prefix to add to bundle paths (e.g., "prod/", "dev/").
        """
        self.directory = Path(directory)
        self.prefix = prefix.strip("/")

        # Create the directory if it doesn't exist
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"LocalBundleStore initialized at {self._storage_dir}")

    @property
    def _storage_dir(self) -> Path:
        """Get the full storage directory including prefix."""
        if self.prefix:
            return self.directory / self.prefix
        return self.directory

    def key_for_agent(self, agent_id: str) -> str:
        """Generate the storage key (filename) for an agent's bundle.

        Args:
            agent_id: The agent identifier.

        Returns:
            The bundle filename.
        """
        return f"{agent_id}.bundle"

    def _path_for_agent(self, agent_id: str) -> Path:
        """Get the full filesystem path for an agent's bundle.

        Args:
            agent_id: The agent identifier.

        Returns:
            Full path to the bundle file.
        """
        return self._storage_dir / self.key_for_agent(agent_id)

    def download_bundle(self, agent_id: str, dest: Path) -> bool:
        """Copy an agent's bundle to the destination path.

        Args:
            agent_id: The agent identifier.
            dest: Local path where bundle should be copied.

        Returns:
            True if bundle was copied, False if bundle doesn't exist.

        Raises:
            RuntimeError: If copy fails for reasons other than not existing.
        """
        src_path = self._path_for_agent(agent_id)

        if not src_path.exists():
            logger.debug(f"Bundle not found for agent {agent_id} at {src_path}")
            return False

        try:
            # Ensure destination directory exists
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Copy the bundle
            shutil.copy2(src_path, dest)
            logger.info(f"Downloaded bundle for agent {agent_id} to {dest}")
            return True
        except Exception as e:
            logger.error(f"Failed to download bundle for {agent_id}: {e}")
            raise RuntimeError(f"Failed to download bundle: {e}") from e

    def upload_bundle(self, agent_id: str, src: Path) -> None:
        """Copy a bundle to the storage directory.

        Args:
            agent_id: The agent identifier.
            src: Local path to the bundle file.

        Raises:
            FileNotFoundError: If source bundle doesn't exist.
            RuntimeError: If copy fails.
        """
        if not src.exists():
            raise FileNotFoundError(f"Source bundle not found: {src}")

        dest_path = self._path_for_agent(agent_id)

        try:
            # Ensure storage directory exists
            self._storage_dir.mkdir(parents=True, exist_ok=True)

            # Copy the bundle
            shutil.copy2(src, dest_path)
            logger.info(f"Uploaded bundle for agent {agent_id} to {dest_path}")
        except Exception as e:
            logger.error(f"Failed to upload bundle for {agent_id}: {e}")
            raise RuntimeError(f"Failed to upload bundle: {e}") from e

    def exists(self, agent_id: str) -> bool:
        """Check if a bundle exists for the given agent.

        Args:
            agent_id: The agent identifier.

        Returns:
            True if bundle exists, False otherwise.
        """
        return self._path_for_agent(agent_id).exists()

    def delete(self, agent_id: str) -> bool:
        """Delete an agent's bundle.

        Args:
            agent_id: The agent identifier.

        Returns:
            True if bundle was deleted, False if it didn't exist.
        """
        path = self._path_for_agent(agent_id)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted bundle for agent {agent_id}")
            return True
        return False

    def list_agents(self) -> list[str]:
        """List all agent IDs with stored bundles.

        Returns:
            List of agent IDs.
        """
        agents = []
        for path in self._storage_dir.glob("*.bundle"):
            agent_id = path.stem  # filename without .bundle extension
            agents.append(agent_id)
        return sorted(agents)
